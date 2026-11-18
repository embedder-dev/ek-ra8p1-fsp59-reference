#!/usr/bin/env python3
"""Compile complete FSP 5.9 RTOS ports with original, verified kernel inputs.

Consumes real e2 generated projects; never creates configuration headers, register
aliases, kernel substitutes or IDE state. All commands and diagnostics are retained.
A compile/link result is not scheduler, low-power or stack-fault runtime evidence.
"""
import argparse
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZipFile

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from ra8p1.compatibility import (ARCHIVE_SHA256, ROOT, candidate_sources, command_for,
                                     dependency_hashes, digest, safe_path, source_overlay)
    from ra8p1.regression import readonly_sections
else:
    from .compatibility import (ARCHIVE_SHA256, ROOT, candidate_sources, command_for,
                                dependency_hashes, digest, safe_path, source_overlay)
    from .regression import readonly_sections

PACKS = {
    "port": "Renesas.RA.5.9.0.pack",
    "freertos": "Amazon.FreeRTOS-Kernel.11.1.0+fsp.5.9.0.pack",
    "threadx": "Microsoft.ThreadX.6.4.0+fsp.5.9.0.pack",
}
MODULES = {"freertos": "rm_freertos_port", "threadx": "rm_threadx_port"}
KERNEL_PREFIXES = {"freertos": "ra/aws/FreeRTOS/FreeRTOS/Source/",
                   "threadx": "ra/microsoft/azure-rtos/threadx/"}
MACROS = ("BSP_CFG_CPU_CORE", "BSP_CFG_RTOS_IDLE_SLEEP", "BSP_CFG_PARAM_CHECKING_ENABLE",
          "BSP_FEATURE_BSP_HAS_PRCR_S", "BSP_FEATURE_BSP_HAS_SP_MON",
          "BSP_FEATURE_LPM_HAS_LPSCR", "configUSE_TICKLESS_IDLE",
          "RM_FREERTOS_PORT_CFG_HW_STACK_MONITOR_ENABLE", "RM_FREERTOS_PORT_PSPLIM_PRESENT",
          "RM_FREERTOS_PORT_PRV_USE_HW_STACK_MONITOR", "RM_THREADX_PORT_CFG_HW_STACK_MONITOR_ENABLE",
          "TX_PORT_PSPLIM_PRESENT", "TX_PORT_VENDOR_STACK_MONITOR_ENABLE")


def original_release(root):
    archive = root / "reference/vendor/FSP_Packs_v5.9.0.zip"
    if digest(archive.read_bytes()) != ARCHIVE_SHA256:
        raise ValueError("Original FSP 5.9 release archive hash mismatch")
    packs = {}
    with ZipFile(archive) as release:
        for key, pack_name in PACKS.items():
            data = release.read("internal/projectgen/ra/packs/" + pack_name)
            with ZipFile(BytesIO(data)) as pack:
                files = {name: pack.read(name) for name in pack.namelist() if not name.endswith("/")}
            for name in files:
                safe_path(name)
            pdsc = [name for name in files if name.endswith(".pdsc")]
            if len(pdsc) != 1:
                raise ValueError("Expected one original PDSC in " + pack_name)
            packs[key] = {"name": pack_name, "sha256": digest(data), "files": files,
                          "pdsc": ET.fromstring(files[pdsc[0]])}
    return packs


def port_paths(pack, module):
    components = [c for c in pack["pdsc"].findall(".//component") if c.get("Csub") == module]
    if len(components) != 1:
        raise ValueError("Expected unique original port component " + module)
    paths = []
    for item in components[0].findall("files/file"):
        if item.get("category") != "source":
            continue
        if item.get("condition") or item.get("select"):
            raise ValueError("Unreviewed conditional source selection: " + str(item.attrib))
        path = item.get("name")
        safe_path(path)
        paths.append(path)
    if not paths or len(paths) != len(set(paths)):
        raise ValueError("Empty or duplicate original port source set")
    return sorted(paths)


def selected_rows(project, rows, prefix):
    selected = {}
    for row in rows:
        path = Path(row["file"])
        if not path.is_absolute():
            path = Path(row["directory"]) / path
        relative = str(path.resolve().relative_to(project))
        if relative.startswith(prefix):
            if relative in selected:
                raise ValueError("Duplicate compile database source: " + relative)
            selected[relative] = row
    return selected


def dependencies(project, pack, rows, prefix):
    # The expected owner set comes from the release, not the surviving extraction.
    if "pdsc" in pack:
        expected = {f.get("name") for c in pack["pdsc"].findall(".//component")
                    if c.get("Cclass") == "RTOS" for f in c.findall("files/file")
                    if f.get("category") in ("source", "header") and f.get("name", "").startswith(prefix)}
    else:
        expected = {name for name in pack["files"] if name.startswith(prefix)}
    if not expected or expected - pack["files"].keys():
        raise ValueError("Original kernel archive owner is missing: " + prefix)
    hashes = {}
    for path in sorted((project / prefix).rglob("*")):
        if not path.is_file():
            continue
        name = str(path.relative_to(project))
        if not path.resolve().is_relative_to(project.resolve() / prefix):
            raise ValueError("Kernel owner resolves outside its project subtree: " + name)
        original = pack["files"].get(name)
        if original is None or path.read_bytes() != original:
            raise ValueError("Kernel file is not hash-identical to original release: " + name)
        hashes[name] = digest(original)
    if not hashes:
        raise ValueError("Real original kernel dependencies are missing: " + prefix)
    selected = selected_rows(project, rows, prefix)
    if not selected:
        raise ValueError("No real kernel translation units selected by generated project")
    if set(selected) - hashes.keys():
        raise ValueError("Selected kernel translation unit is missing from project")
    missing = expected - hashes.keys()
    if missing:
        raise ValueError("Required original kernel owner is missing: " + ", ".join(sorted(missing)))
    return {"pack": pack["name"], "pack_sha256": pack["sha256"],
            "files": hashes, "translation_units": sorted(selected)}


def consumed_kernel(deps, pack, prefix):
    owners = {name: digest(data) for name, data in pack["files"].items() if name.startswith(prefix)}
    basenames = {Path(name).name for name in owners}
    consumed = {}
    for name, sha256 in deps.items():
        relative = name.removeprefix("$PROJECT/")
        if relative.startswith(prefix):
            if owners.get(relative) != sha256:
                raise ValueError("Compiler-consumed kernel input is not hash-identical to its owner: " + name)
            consumed[relative] = sha256
        elif Path(name).name in basenames:
            raise ValueError("Compiler-consumed kernel owner substitution: " + name)
    return consumed


def macro_values(command, cwd):
    args = list(command)
    index = args.index("-o")
    del args[index:index + 2]
    args.remove("-c")
    completed = subprocess.run(args + ["-dM", "-E"], cwd=cwd, capture_output=True, text=True, timeout=120)
    if completed.returncode:
        return {"error": completed.stdout + completed.stderr}
    values = {}
    for line in completed.stdout.splitlines():
        parts = line.split(maxsplit=2)
        if len(parts) >= 2 and parts[1] in MACROS:
            values[parts[1]] = parts[2] if len(parts) == 3 else ""
    return values


def compile_fixture(root, project, rtos, phase, source_set, packs, candidate):
    project = project.resolve()
    rows = json.loads((project / "Debug/compile_commands.json").read_text())
    module = MODULES[rtos]
    paths = port_paths(packs["port"], module)
    port_rows = selected_rows(project, rows, "ra/fsp/src/" + module + "/")
    if sorted(port_rows) != paths:
        raise ValueError("Generated GCC source selection differs from original port PDSC")
    # PDSC kernel ownership is checked in addition to exact original archive hashes.
    kernel = dependencies(project, packs[rtos], rows, KERNEL_PREFIXES[rtos])
    kernel_paths = {f.get("name") for c in packs[rtos]["pdsc"].findall(".//component")
                    if c.get("Cclass") == "RTOS" for f in c.findall("files/file")
                    if f.get("category") == "source" and f.get("name", "").startswith(KERNEL_PREFIXES[rtos])}
    if set(kernel["translation_units"]) != kernel_paths:
        raise ValueError("Generated kernel selection differs from original RTOS PDSC")
    original = {name: data for name, data in packs["port"]["files"].items() if name.startswith("ra/fsp/")}
    sources = source_overlay(candidate, original, source_set)
    required = set(paths) | {p.relative_to(project).as_posix() for p in (project / "ra/fsp").rglob("*")
                             if p.is_file()}
    missing = required - sources.keys()
    if missing:
        raise ValueError("Required FSP owning source/header is missing: " + ", ".join(sorted(missing)))
    results = {}
    kernel["compiler_dependencies"] = {}
    kernel["dependency_scans"] = {}
    with tempfile.TemporaryDirectory(prefix="ra8p1-rtos-") as temporary:
        tree = Path(temporary) / "project"
        shutil.copytree(project, tree, ignore=shutil.ignore_patterns("Debug", ".git"))
        (tree / "Debug").mkdir()
        # A missing owner must never fall through to bytes copied from the project.
        shutil.rmtree(tree / "ra/fsp")
        for name, data in sources.items():
            safe_path(name)
            target = tree / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        kernel_rows = selected_rows(project, rows, KERNEL_PREFIXES[rtos])
        for index, source in enumerate(kernel["translation_units"]):
            depfile = tree / "Debug" / f"kernel-{index}.d"
            command = command_for(kernel_rows[source], project, tree, source, tree / "Debug/unused.o")
            output_index = command.index("-o")
            del command[output_index:output_index + 2]
            command.remove("-c")
            command += ["-M", "-MF", str(depfile), "-MT", "kernel"]
            completed = subprocess.run(command, cwd=tree / "Debug", capture_output=True, text=True, timeout=120)
            if completed.returncode:
                raise ValueError("Kernel compiler dependency scan failed: " + source + "\n" +
                                 completed.stdout + completed.stderr)
            deps = dependency_hashes(depfile, tree, project, tree / "Debug")
            consumed = consumed_kernel(deps, packs[rtos], KERNEL_PREFIXES[rtos])
            if source not in consumed:
                raise ValueError("Kernel compiler dependency scan omitted its source owner: " + source)
            kernel["compiler_dependencies"].update(consumed)
            kernel["dependency_scans"][source] = {
                "command": [arg.replace(str(tree), "$PROJECT") for arg in command],
                "dependencies_sha256": deps,
                "diagnostics": (completed.stdout + completed.stderr).replace(str(tree), "$PROJECT")}
        for index, source in enumerate(paths):
            command = command_for(port_rows[source], project, tree, source, tree / "Debug" / f"port-{index}.o")
            depfile = tree / "Debug" / f"port-{index}.d"
            command += ["-MD", "-MF", str(depfile)]
            # Keep __FILE__ identical between isolated original/candidate builds.
            command.append("-ffile-prefix-map=" + str(tree) + "=$PROJECT")
            if "-w" in command:
                command.remove("-w")
            completed = subprocess.run(command, cwd=tree / "Debug", capture_output=True, text=True, timeout=120)
            results[source] = {"status": "pass" if completed.returncode == 0 else "fail",
                               "returncode": completed.returncode, "sha256": digest((tree / source).read_bytes()),
                               "command": [arg.replace(str(tree), "$PROJECT") for arg in command],
                               "diagnostics": (completed.stdout + completed.stderr).replace(str(tree), "$PROJECT")}
            if completed.returncode == 0:
                deps = dependency_hashes(depfile, tree, project, tree / "Debug")
                kernel["compiler_dependencies"].update(consumed_kernel(deps, packs[rtos], KERNEL_PREFIXES[rtos]))
                results[source]["dependencies_sha256"] = deps
                results[source]["readonly_sections"] = readonly_sections(
                    (tree / "Debug" / f"port-{index}.o").read_bytes())
        first = paths[0]
        command = command_for(port_rows[first], project, tree, first, tree / "Debug/macros.o")
        macros = macro_values(command, tree / "Debug")
    return {"project": str(project.relative_to(root)), "rtos": rtos, "module": module,
            "phase": phase, "source_set": source_set, "source_paths": paths,
            "status": "pass" if all(r["status"] == "pass" for r in results.values()) else "fail",
            "configuration_sha256": digest((project / "configuration.xml").read_bytes()),
            "compile_database_sha256": digest((project / "Debug/compile_commands.json").read_bytes()),
            "generated_configs": {str(p.relative_to(project)): digest(p.read_bytes())
                                  for p in (project / "ra_cfg").rglob("*.h")},
            "kernel": kernel, "macros": macros, "sources": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", action="append", required=True, metavar="RTOS=PROJECT")
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    parser.add_argument("--source-set", choices=("stock", "candidate"), action="append")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.report.exists() or args.report.is_symlink():
        parser.error("Refusing to overwrite existing evidence: " + str(args.report))
    packs = original_release(ROOT)
    candidate = candidate_sources(ROOT, args.phase)
    reports = []
    for fixture in args.fixture:
        rtos, path = fixture.split("=", 1)
        if rtos not in MODULES:
            parser.error("Unknown RTOS " + rtos)
        for source_set in args.source_set or ("stock", "candidate"):
            report = compile_fixture(ROOT, Path(path), rtos, args.phase, source_set, packs, candidate)
            reports.append(report)
            print(Path(path).name, source_set, report["status"], len(report["sources"]), "port units,",
                  len(report["kernel"]["translation_units"]), "original kernel units")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x") as output:
        output.write(json.dumps({"schema": 1, "scope": "Compile only; no RTOS execution or power measurement",
                                 "original_release_sha256": ARCHIVE_SHA256, "reports": reports}, indent=2) + "\n")
    return int(any(r["status"] != "pass" for r in reports))


if __name__ == "__main__":
    raise SystemExit(main())
