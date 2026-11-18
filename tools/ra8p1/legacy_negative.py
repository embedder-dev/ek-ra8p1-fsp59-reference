#!/usr/bin/env python3
"""Measure pristine legacy SCI/DAC rejection using real generated control configs.

No IDE or pack operations. No configuration, register definitions or aliases are
synthesized. A completed negative measurement is not a compatibility pass.
"""
import argparse
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from ra8p1 import compatibility as gate

DRIVERS = {
    "r_sci_uart": {"factory": "module.driver.uart_on_sci_uart", "config": "r_sci_uart_cfg.h",
                   "register": r"\bR_SCI(?:[0-9][A-Za-z0-9_]*|_Type)\b"},
    "r_dac": {"factory": "module.driver.dac_on_dac", "config": "r_dac_cfg.h",
              "register": r"\bR_DAC(?:[0-9][A-Za-z0-9_]*|_Type)?\b"},
}


def identity(project):
    model = ET.fromstring((project / "configuration.xml").read_bytes())
    return {item.attrib["key"]: item.attrib["value"] for item in model.findall("./generalSettings/option")}, model


def control_config(project, name):
    project = project.resolve()
    expected = DRIVERS[name]
    config = project / "ra_cfg/fsp_cfg" / expected["config"]
    if not config.is_file():
        raise ValueError("Missing genuine generated control header: " + str(config))
    settings, model = identity(project)
    if settings.get("#FSPVersion#") != "5.9.0" or settings.get("CPU") in (None, "RA8P1"):
        raise ValueError("Control must be an older-device FSP 5.9.0 generated project")
    if not any(stack.get("module", "").startswith(expected["factory"] + ".") or stack.get("module") == expected["factory"]
               for stack in model.iter("stack")):
        raise ValueError("Control model does not select the original factory: " + expected["factory"])
    database = project / "Debug/compile_commands.json"
    rows = json.loads(database.read_text())
    source = "ra/fsp/src/" + name + "/" + name + ".c"
    if not any(gate.row_source(row).resolve() == project / source for row in rows):
        raise ValueError("Control compile database does not select original translation unit: " + source)
    data = config.read_bytes()
    if b"generated" not in data[:200].lower():
        raise ValueError("Control header lacks its configurator-generated marker")
    return data, {"project": str(project), "settings": settings, "header": str(config), "header_sha256": gate.digest(data),
                  "configuration_sha256": gate.digest((project / "configuration.xml").read_bytes()),
                  "compile_database_sha256": gate.digest(database.read_bytes())}


def diagnose(name, returncode, diagnostics, preprocess_returncode, dependency_errors=()):
    if re.search(r"fatal error:.*No such file or directory", diagnostics):
        return "blocked", "Missing configuration/dependency is not variant evidence", []
    if dependency_errors or preprocess_returncode:
        return "blocked", "; ".join(dependency_errors) or "Preprocessing failed; generated dependency chain is unproven", []
    if returncode == 0:
        return "unexpected-compile", "Legacy source compiled: no measured variant rejection", []
    register_errors = [line for line in diagnostics.splitlines() if "error:" in line
                       and re.search(DRIVERS[name]["register"], line.split("did you mean", 1)[0])]
    if not register_errors:
        return "unrelated-failure", "Compile failed without a measured legacy register/type diagnostic", []
    return "measured-negative", "Pristine legacy register/type contract rejected after real generated configuration was consumed", register_errors


def measure(root, target, name, control, stock, candidate):
    target = target.resolve()
    settings, _ = identity(target)
    if settings.get("CPU") != "RA8P1" or settings.get("#FSPVersion#") != "5.9.0":
        raise ValueError("Target must be a generated RA8P1 FSP 5.9.0 project")
    database = target / "Debug/compile_commands.json"
    rows = json.loads(database.read_text())
    row = next((item for item in rows if item["file"].endswith("/r_ioport.c")), None)
    if row is None:
        raise ValueError("Target has no real generated r_ioport compiler command")
    args = row.get("arguments") or shlex.split(row["command"])
    cores = {arg.split("=", 1)[1] for arg in args if arg.startswith("-D_RA_CORE=")}
    if len(cores) != 1 or settings.get("Core") not in cores:
        raise ValueError("Target core and recorded compiler flags disagree")
    core = next(iter(cores))
    result = {"target": str(target.relative_to(root)), "core": core, "driver": name, "compatible": False,
              "target_configuration_sha256": gate.digest((target / "configuration.xml").read_bytes()),
              "target_compile_database_sha256": gate.digest(database.read_bytes()), "recorded_target_command": args}
    try:
        cfg, provenance = control_config(control, name)
    except (FileNotFoundError, ValueError) as error:
        return dict(result, status="blocked", reason=str(error), compiler_invoked=False)
    result["control"] = provenance
    source = "ra/fsp/src/" + name + "/" + name + ".c"
    exact = stock.components[name]
    overlay = gate.source_overlay(candidate, stock, "stock")
    overlay.update(exact)
    generated = gate.fixture_inputs(target)
    control_generated = gate.fixture_inputs(control)
    with tempfile.TemporaryDirectory(prefix="ra8p1-legacy-negative-") as temporary:
        tree = Path(temporary) / "target"
        shutil.copytree(target, tree, ignore=shutil.ignore_patterns("Debug", ".git"))
        shutil.rmtree(tree / "ra/fsp")
        for path, data in overlay.items():
            gate.safe_path(path)
            destination = tree / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        # Control headers live outside ra_cfg/ra_gen and are copied byte-for-byte.
        extra = tree / "legacy-control-cfg"
        extra.mkdir()
        config = extra / DRIVERS[name]["config"]
        config.write_bytes(cfg)
        if (tree / "ra_cfg/fsp_cfg" / config.name).exists():
            raise ValueError("Target unexpectedly contains a legacy config; refusing ambiguous selection")
        debug = tree / "Debug"
        debug.mkdir()
        output = debug / (name + ".o")
        command = gate.command_for(row, target, tree, source, output) + ["-I" + str(extra), "-H"]
        recorded_cwd = Path(row["directory"]).resolve()
        cwd = tree / recorded_cwd.relative_to(target)
        cwd.mkdir(parents=True, exist_ok=True)
        compiled = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=120)
        diagnostics = (compiled.stdout + compiled.stderr).replace(str(tree), "$PROJECT")
        preprocess = command.copy()
        preprocess[preprocess.index("-c")] = "-E"
        preprocess[preprocess.index("-o") + 1] = str(debug / (name + ".i"))
        depfile = debug / (name + ".d")
        preprocess += ["-MD", "-MF", str(depfile)]
        processed = subprocess.run(preprocess, cwd=cwd, capture_output=True, text=True, timeout=120)
        dependency_errors = []
        dependencies = {}
        if processed.returncode == 0:
            try:
                dependencies = gate.dependency_hashes(depfile, tree, target, cwd)
            except (ValueError, FileNotFoundError) as error:
                dependency_errors.append(str(error))
            required = {gate.DEVICE_HEADER: candidate[gate.DEVICE_HEADER],
                        "ra/fsp/src/bsp/mcu/ra8p1/bsp_feature.h": candidate["ra/fsp/src/bsp/mcu/ra8p1/bsp_feature.h"],
                        "legacy-control-cfg/" + config.name: cfg, source: exact[source],
                        "ra/fsp/inc/instances/" + name + ".h": exact["ra/fsp/inc/instances/" + name + ".h"]}
            api = "ra/fsp/inc/api/" + ("r_uart_api.h" if name == "r_sci_uart" else "r_dac_api.h")
            required[api] = exact[api]
            for path, data in required.items():
                if dependencies.get("$PROJECT/" + path) != gate.digest(data):
                    dependency_errors.append("Expected owning/config/original input was not consumed: " + path)
        status, reason, errors = diagnose(name, compiled.returncode, diagnostics, processed.returncode, dependency_errors)
        result.update(status=status, reason=reason, compiler_invoked=True, compiler_returncode=compiled.returncode,
                      preprocessing_returncode=processed.returncode, register_type_diagnostics=errors, diagnostics=diagnostics,
                      preprocessing_diagnostics=(processed.stdout + processed.stderr).replace(str(tree), "$PROJECT"),
                      command=[arg.replace(str(tree), "$PROJECT") for arg in command],
                      preprocessing_command=[arg.replace(str(tree), "$PROJECT") for arg in preprocess],
                      directory=str(cwd).replace(str(tree), "$PROJECT"), compiler_sha256=gate.digest(Path(command[0]).read_bytes()),
                      original_component_inputs_sha256={path: gate.digest(data) for path, data in exact.items()},
                      dependencies_sha256=dependencies, generated_target_inputs_sha256=generated,
                      owning_device_header_sha256=gate.digest(candidate[gate.DEVICE_HEADER]))
        if gate.fixture_inputs(tree) != generated or gate.fixture_inputs(target) != generated or gate.fixture_inputs(control) != control_generated:
            raise ValueError("Original or disposable generated configuration inputs changed")
    return result


def preparation_commands(control):
    parent = str(control.parent)
    name = control.name
    return [shlex.join(["embedder", "e2", "--lane", "0", "project", "create", name, "--fsp", "5.9.0", "--board", "EK-RA4M1",
                        "--location", parent, "--no-build"]),
            shlex.join(["embedder", "e2", "--lane", "0", "config", "set", str(control), "--add", "r_sci_uart:g_legacy_uart", "--prop", "channel=0"]),
            shlex.join(["embedder", "e2", "--lane", "0", "config", "set", str(control), "--add", "r_dac:g_legacy_dac", "--prop", "channel=0", "--build"])]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append", required=True)
    parser.add_argument("--control", type=Path, required=True, help="Existing older-device generated FSP 5.9.0 project with both legacy stacks")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.report.exists():
        parser.error("Refusing to overwrite existing evidence: " + str(args.report))
    census = json.loads((ROOT / "tools/ra8p1/compatibility_census.json").read_text())
    modules = [module for module in census["modules"] if module["name"] in DRIVERS]
    stock = gate.original_sources(ROOT, modules)
    candidate = gate.candidate_sources(ROOT, "after")
    results = [measure(ROOT, target, name, args.control, stock, candidate) for target in args.target for name in DRIVERS]
    states = {item["status"] for item in results}
    cores = {item["core"] for item in results}
    exit_status = 1 if states & {"unexpected-compile", "unrelated-failure"} else (
        2 if "blocked" in states or cores != {"CM85", "CM33"} else 0)
    report = {"schema": 1, "scope": "Measured negative legacy source compilation only; never a firmware compatibility pass",
              "original_archive_sha256": gate.ARCHIVE_SHA256, "results": results, "exit_status": exit_status,
              "required_cores": ["CM85", "CM33"], "preparation_commands_for_parent_only": preparation_commands(args.control)}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x") as output:
        output.write(json.dumps(report, indent=2) + "\n")
    for item in results:
        print(item["core"], item["driver"], item["status"], item["reason"])
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())
