#!/usr/bin/env python3
"""Compile a census against unchanged generated fixtures in disposable overlays.

This is source-compatibility evidence, not a generated-project or runtime pass.
The owning BSP/header comes from baseline (or the immutable before snapshot),
never the project's installed BSP. Only PDSC-owned sources selected by a real
fixture's compile database are compiled. Missing fixtures are blockers.
"""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from build_ra8p1_packs import disclaimer_equivalent
ARCHIVE_SHA256 = "99c4abae6239a68171fcbff86070971f591f0a8945e90a50eb07d87843bee363"
RELEASE_PACK = "internal/projectgen/ra/packs/Renesas.RA.5.9.0.pack"
DEVICE_HEADER = "ra/fsp/src/bsp/cmsis/Device/RENESAS/Include/R7KA8P1KF.h"
HAL_PREFIXES = ("ra/fsp/inc/api/", "ra/fsp/inc/instances/")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError("Unsafe source path: " + name)
    return path


def is_hal(name):
    return name.startswith(HAL_PREFIXES) or (
        name.startswith("ra/fsp/src/") and not name.startswith("ra/fsp/src/bsp/"))


class OriginalSources(dict):
    """Common pack authority plus exact bytes of each census component owner."""

    def __init__(self):
        super().__init__()
        self.components = {}


def original_sources(root, modules=()):
    archive = root / "reference/vendor/FSP_Packs_v5.9.0.zip"
    if digest(archive.read_bytes()) != ARCHIVE_SHA256:
        raise ValueError("Original release archive hash mismatch")
    entries = {RELEASE_PACK: None}
    for module in modules:
        for component in module.get("components", []):
            entry = component["archive_entry"]
            safe_path(entry)
            expected = component["pack_sha256"]
            if entries.get(entry) not in (None, expected):
                raise ValueError("Conflicting original pack provenance: " + entry)
            entries[entry] = expected
    sources = OriginalSources()
    owners = {}
    with ZipFile(archive) as release:
        for entry, expected in sorted(entries.items()):
            data = release.read(entry)
            if expected and digest(data) != expected:
                raise ValueError("Original component pack hash mismatch: " + entry)
            with ZipFile(BytesIO(data)) as pack:
                for name in pack.namelist():
                    if name.startswith("ra/fsp/") and not name.endswith("/"):
                        safe_path(name)
                        content = pack.read(name)
                        owners.setdefault(name, {})[entry] = content
                for module in modules:
                    selected = sources.components.setdefault(module.get("name"), {})
                    for component in module.get("components", []):
                        if component["archive_entry"] != entry:
                            continue
                        if component.get("pdsc") and digest(pack.read(component["pdsc"])) != component["pdsc_sha256"]:
                            raise ValueError("Original PDSC hash mismatch: " + component["pdsc"])
                        for record in component.get("files", []):
                            if record["category"] not in ("source", "header"):
                                continue
                            name = record["name"]
                            safe_path(name)
                            content = pack.read(name)
                            if digest(content) != record["sha256"]:
                                raise ValueError("Original PDSC-selected file hash mismatch: " + name)
                            if name in selected and selected[name] != content and not disclaimer_equivalent([selected[name], content]):
                                raise ValueError("Conflicting original component source: " + name)
                            selected.setdefault(name, content)
    for name, variants in owners.items():
        values = set(variants.values())
        if len(values) == 1:
            sources[name] = next(iter(values))
        elif RELEASE_PACK in variants and disclaimer_equivalent(values):
            sources[name] = variants[RELEASE_PACK]
        else:
            raise ValueError("Conflicting original source ownership: " + name)
    return sources


def candidate_sources(root, phase):
    if phase == "before":
        with ZipFile(root / "validation/ra8p1/compatibility/before-inputs.zip") as frozen:
            return {name.removeprefix("baseline/"): frozen.read(name)
                    for name in frozen.namelist() if name.startswith("baseline/ra/fsp/") and not name.endswith("/")}
    return {path.relative_to(root / "baseline").as_posix(): path.read_bytes()
            for path in (root / "baseline/ra/fsp").rglob("*") if path.is_file()}


def source_overlay(candidate, stock, source_set):
    # Candidate-only APIs/drivers must not leak into the pristine-source gate.
    merged = {name: data for name, data in candidate.items() if source_set != "stock" or not is_hal(name)}
    if source_set == "stock":
        merged.update({name: data for name, data in stock.items() if is_hal(name)})
    return merged


def row_source(row):
    path = Path(row["file"])
    return path if path.is_absolute() else Path(row["directory"]) / path


def command_for(row, project, tree, source, output):
    args = row.get("arguments") or shlex.split(row["command"])
    if args.count("-o") != 1 or "-c" not in args:
        raise ValueError("Expected recorded compiler source/output arguments")
    mapped = [arg.replace(str(project) + "/", str(tree) + "/") for arg in args]
    mapped[mapped.index("-o") + 1] = str(output)
    old_mapped = str(row["file"]).replace(str(project) + "/", str(tree) + "/")
    if old_mapped not in mapped:
        raise ValueError("Recorded source is missing from command")
    mapped[mapped.index(old_mapped)] = str(tree / source)
    if source.endswith((".S", ".s")) and "-x" in mapped:
        index = mapped.index("-x")
        mapped[index + 1] = "assembler-with-cpp" if source.endswith(".S") else "assembler"
    mapped += ["-Werror=incompatible-pointer-types", "-Werror=implicit-function-declaration"]
    return mapped


def compiler_variant_reason(source, args):
    compiler = Path(args[0]).name.lower()
    if "gcc" not in compiler:
        raise ValueError("Only recorded GNU compiler commands are supported: " + args[0])
    if re.search(r"(?:^|/)(?:iar|ac6|armclang|ccrx)(?:/|$)", source, re.I) or Path(source).name == "tx_iar.c":
        return "Compiler-specific non-GNU port; not a GCC translation unit"
    return None


def fixture_inputs(project):
    return {path.relative_to(project).as_posix(): digest(path.read_bytes())
            for folder in ("ra_gen", "ra_cfg") for path in sorted((project / folder).rglob("*")) if path.is_file()}


def dependency_hashes(depfile, tree, project, cwd):
    if not depfile.exists():
        raise ValueError("Compiler produced no dependency evidence")
    text = depfile.read_text().replace("\\\n", " ")
    if ":" not in text:
        raise ValueError("Malformed compiler dependency evidence")
    result = {}
    # Only the first rule is the object's dependencies; -MP may add empty rules.
    dependencies = text.split(":", 1)[1].split("\n\n", 1)[0]
    for name in shlex.split(dependencies):
        if name.endswith(":"):
            break
        path = Path(name)
        path = (cwd / path).resolve() if not path.is_absolute() else path.resolve()
        if path.is_relative_to(project):
            raise ValueError("Compiler consumed an original project input outside the disposable overlay: " + str(path))
        key = "$PROJECT/" + path.relative_to(tree).as_posix() if path.is_relative_to(tree) else str(path)
        result[key] = digest(path.read_bytes())
    return result


def source_paths(module, sources):
    if "source_paths" in module:
        paths = module["source_paths"]
    else:
        paths = sorted(path for path in sources if path.startswith("ra/fsp/src/" + module["name"] + "/")
                       and path.endswith((".c", ".S", ".s")))
    owned = {record["name"] for component in module.get("components", []) for record in component.get("files", [])
             if record["category"] == "source"}
    if module.get("original_release") and set(paths) != owned:
        raise ValueError("Census source_paths differ from original PDSC source inventory: " + module["name"])
    return paths


def compile_project(root, project, modules, source_set, phase, stock, candidate):
    project = project.resolve()
    database = project / "Debug/compile_commands.json"
    rows = json.loads(database.read_text())
    if not rows:
        raise ValueError("Empty generated compile database")
    selected_rows = {row_source(item).resolve().relative_to(project).as_posix(): item for item in rows}
    all_args = [arg for item in rows for arg in (item.get("arguments") or shlex.split(item["command"]))]
    cores = sorted({arg.split("=", 1)[1] for arg in all_args if arg.startswith("-D_RA_CORE=")})
    if len(cores) != 1:
        raise ValueError("Fixture must select exactly one recorded _RA_CORE: " + str(project))
    sources = source_overlay(candidate, stock, source_set)
    generated = fixture_inputs(project)
    results = {}
    with tempfile.TemporaryDirectory(prefix="ra8p1-compat-") as temporary:
        tree = Path(temporary) / "project"
        shutil.copytree(project, tree, ignore=shutil.ignore_patterns("Debug", ".git"))
        (tree / "Debug").mkdir()
        # Remove installed HAL/BSP bytes rather than leave stale or candidate-only
        # headers reachable when an owning source set no longer contains them.
        shutil.rmtree(tree / "ra/fsp", ignore_errors=True)
        for name, data in sources.items():
            safe_path(name)
            target = tree / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        for module in modules:
            name = module["name"]
            paths = source_paths(module, candidate)
            classification = module.get("classification", "unclassified")
            result = {"source_set": source_set, "phase": phase, "sources": {}, "classification": classification,
                      "selected_sources": [], "unselected_sources": sorted(set(paths) - set(selected_rows))}
            if classification in ("absent", "variant-mismatch"):
                result.update(status="not-applicable" if classification == "absent" else "variant-mismatch",
                              reason=module["reason"])
                results[name] = result
                continue
            if source_set == "stock" and (module.get("original_release") is False or (paths and not any(path in stock for path in paths))):
                result.update(status="not-applicable", reason="No matching original-release implementation; candidate/hardware gap only")
                results[name] = result
                continue
            selected = sorted(set(paths) & set(selected_rows))
            result["selected_sources"] = selected
            if not selected:
                result.update(status="blocked", reason="No generated fixture selects PDSC translation units" if paths else
                              "No translation units: header/library-only component or unimplemented hardware/mode needs a dedicated gate",
                              required_factories=module.get("module_ids", [module.get("module_id")]),
                              generated_stack_prerequisites=module.get("generated_stack_prerequisites", []))
                results[name] = result
                continue
            exact = getattr(stock, "components", {}).get(name, {}) if source_set == "stock" else {}
            for path, data in exact.items():
                target = tree / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            for index, source in enumerate(selected):
                safe_path(source)
                selected_row = selected_rows[source]
                args = selected_row.get("arguments") or shlex.split(selected_row["command"])
                excluded = compiler_variant_reason(source, args)
                if excluded:
                    result["sources"][source] = {"status": "excluded", "reason": excluded}
                    continue
                if source not in sources:
                    result["sources"][source] = {"status": "blocked", "reason": "PDSC-selected source absent from owning source set"}
                    continue
                output = tree / "Debug" / f"{name}-{index}.o"
                command = command_for(selected_row, project, tree, source, output)
                for include in module.get("include_paths", []):
                    safe_path(include)
                    command.append("-I" + str(tree / include))
                depfile = output.with_suffix(".d")
                command += ["-MD", "-MF", str(depfile)]
                recorded_cwd = Path(selected_row["directory"]).resolve()
                cwd = tree / recorded_cwd.relative_to(project)
                cwd.mkdir(parents=True, exist_ok=True)
                completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=120)
                diagnostics = (completed.stdout + completed.stderr).replace(str(tree), "$PROJECT")
                symbols = None
                deps = {}
                if completed.returncode == 0:
                    nm = Path(command[0]).with_name("arm-none-eabi-nm")
                    listed = subprocess.run([str(nm), "--defined-only", str(output)], capture_output=True, text=True, timeout=30)
                    if listed.returncode:
                        raise ValueError("Cannot inspect compiled module symbols: " + listed.stderr)
                    # Ignore absolute/debug/file and local ARM mapping symbols.
                    symbols = [line for line in listed.stdout.splitlines()
                               if re.search(r"\s[bdgrstvwBDGRSTVW]\s+(?!\$)", line)]
                    deps = dependency_hashes(depfile, tree, project, cwd)
                    if symbols and DEVICE_HEADER in candidate:
                        for required in (DEVICE_HEADER, "ra/fsp/src/bsp/mcu/ra8p1/bsp_feature.h"):
                            if deps.get("$PROJECT/" + required) != digest(candidate[required]):
                                raise ValueError("Compile did not consume the owning target BSP/header: " + required)
                missing = re.findall(r"fatal error: ([^\n]+?): No such file or directory", diagnostics)
                status = "pass" if completed.returncode == 0 else ("blocked" if missing else "fail")
                if status == "pass" and not symbols:
                    status = "inactive"
                result["sources"][source] = {
                    "status": status, "returncode": completed.returncode,
                    "source_sha256": digest((tree / source).read_bytes()),
                    "original_pdsc_sha256": digest(exact[source]) if source in exact else None,
                    "command": [arg.replace(str(tree), "$PROJECT") for arg in command],
                    "recorded_command": args, "directory": str(cwd).replace(str(tree), "$PROJECT"),
                    "compiler_sha256": digest(Path(command[0]).read_bytes()),
                    "dependencies_sha256": deps, "diagnostics": diagnostics, "missing_dependencies": missing,
                    "reason": "Generated configuration or original dependency missing" if missing else
                              ("Inactive/empty translation unit; not compatibility evidence" if status == "inactive" else None),
                    "defined_symbols": symbols,
                }
            states = {item["status"] for item in result["sources"].values()}
            result["status"] = "fail" if "fail" in states else ("blocked" if "blocked" in states or "pass" not in states else "pass")
            if states <= {"inactive", "excluded"}:
                result["reason"] = "All selected translation units are inactive/empty or excluded in this configuration"
            results[name] = result
            # Keep every stock attempt independent of the previously visited component.
            for path in exact:
                if path in sources:
                    (tree / path).write_bytes(sources[path])
                else:
                    (tree / path).unlink()
        if fixture_inputs(tree) != generated or fixture_inputs(project) != generated:
            raise ValueError("Generated ra_cfg/ra_gen changed during compatibility gate")
    return {"project": str(project.relative_to(root)), "core": cores[0], "source_set": source_set, "phase": phase,
            "configuration_sha256": digest((project / "configuration.xml").read_bytes()),
            "compile_database_sha256": digest(database.read_bytes()),
            "device_header_sha256": digest(candidate[DEVICE_HEADER]) if DEVICE_HEADER in candidate else None,
            "owning_bsp_sha256": {name: digest(data) for name, data in candidate.items()
                                  if name.startswith(("ra/fsp/src/bsp/mcu/ra8p1/", "ra/fsp/src/bsp/cmsis/Device/RENESAS/Include/R7KA8P1"))},
            "generated_inputs": generated, "modules": results}


def aggregate_reports(reports, modules, source_sets, cores):
    aggregate = {}
    for source_set in source_sets:
        aggregate[source_set] = {}
        for module in modules:
            name = module["name"]
            cells = {}
            for core in cores:
                attempts = [(report["project"], report["modules"][name]) for report in reports
                            if report["source_set"] == source_set and report["core"] == core
                            and name in report["modules"]]
                statuses = {item["status"] for _, item in attempts}
                report_only = module.get("classification") in ("absent", "variant-mismatch") or (
                    source_set == "stock" and module.get("original_release") is False)
                if report_only:
                    status = "variant-mismatch" if module.get("classification") == "variant-mismatch" else "not-applicable"
                else:
                    # A real compile failure in any selected configuration remains a
                    # failure even when a second fixture happens to compile.
                    status = "fail" if "fail" in statuses else ("pass" if "pass" in statuses else "blocked")
                cells[core] = {"status": status, "passing_projects": [project for project, item in attempts if item["status"] == "pass"],
                               "failed_projects": [project for project, item in attempts if item["status"] == "fail"],
                               "reasons": sorted({item["reason"] for _, item in attempts if item.get("reason")}),
                               "missing_dependencies": sorted({missing for _, item in attempts for source in item["sources"].values()
                                                               for missing in source.get("missing_dependencies", [])})}
            states = {cell["status"] for cell in cells.values()}
            status = "fail" if "fail" in states else ("blocked" if "blocked" in states else next(iter(states)))
            aggregate[source_set][name] = {"classification": module.get("classification"), "status": status, "cores": cells}
    return aggregate


def exit_status(aggregate):
    states = {item["status"] for source_set in aggregate.values() for item in source_set.values()}
    return 1 if "fail" in states else (2 if "blocked" in states else 0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, action="append", required=True)
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    parser.add_argument("--source-set", choices=("stock", "candidate"), action="append")
    parser.add_argument("--module", action="append")
    parser.add_argument("--core", choices=("CM85", "CM33"), action="append", help="Required coverage cores; default: census target cores")
    parser.add_argument("--census", type=Path, default=ROOT / "tools/ra8p1/compatibility_census.json")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.report.exists():
        parser.error("Refusing to overwrite existing evidence: " + str(args.report))
    if args.report.name.startswith("before") and args.phase != "before":
        parser.error("Before evidence is immutable; choose a new after report")
    if args.census.exists():
        census = json.loads(args.census.read_text())
        modules = census["modules"]
    elif args.module:
        census = {}
        modules = [{"name": name} for name in args.module]
    else:
        parser.error("A census or explicit modules are required")
    if args.module:
        selected = set(args.module)
        modules = [module for module in modules if module["name"] in selected]
        if {module["name"] for module in modules} != selected:
            parser.error("Requested module is missing from census")
    stock = original_sources(ROOT, modules)
    candidate = candidate_sources(ROOT, args.phase)
    source_sets = list(dict.fromkeys(args.source_set or ["stock", "candidate"]))
    cores = list(dict.fromkeys(args.core or census.get("target", {}).get("cores", ["CM85", "CM33"])))
    reports = []
    for project in dict.fromkeys(args.project):
        for source_set in source_sets:
            report = compile_project(ROOT, project, modules, source_set, args.phase, stock, candidate)
            reports.append(report)
            counts = {status: sum(item["status"] == status for item in report["modules"].values())
                      for status in ("pass", "fail", "blocked", "not-applicable", "variant-mismatch")}
            print(project.name, source_set, counts)
    aggregate = aggregate_reports(reports, modules, source_sets, cores)
    status = exit_status(aggregate)
    result = {"schema": 2, "scope": "Source compile only in disposable owning-BSP overlays; no generated build/link/runtime claim",
              "phase": args.phase, "original_archive_sha256": ARCHIVE_SHA256,
              "census_sha256": digest(args.census.read_bytes()) if args.census.exists() else None,
              "required_cores": cores, "source_sets": source_sets, "aggregate": aggregate, "exit_status": status,
              "source_set_exit_status": {name: exit_status({name: rows}) for name, rows in aggregate.items()}, "reports": reports}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x") as output:
        output.write(json.dumps(result, indent=2) + "\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
