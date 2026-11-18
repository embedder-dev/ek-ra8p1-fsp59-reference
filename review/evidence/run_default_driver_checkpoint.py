"""One r015 default-stack checkpoint; only embedder e2 owns FSP generation.

Fresh first-party hal_entry probes preserve the configurator's warm callbacks.
This script neither edits generated SDK/configuration files nor uses hardware.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def run(command, log):
    with log.open("x") as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=590)
    if result.returncode:
        raise RuntimeError(f"Exit {result.returncode}: {command}; see {log}")
    return log.read_text()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("driver", choices=("dac_b", "pdm", "wdt", "adc_b", "cgc"))
    args = parser.parse_args()
    driver = args.driver
    instance = {"dac_b": "g_dac_b0", "pdm": "g_pdm0", "wdt": "g_wdt0", "adc_b": "g_adc0", "cgc": "g_cgc0"}[driver]
    declarations = "volatile fsp_err_t review_result;\n"
    call = f"review_result = {instance}.p_api->open({instance}.p_ctrl, {instance}.p_cfg);"
    if driver == "wdt":
        declarations += "wdt_timeout_values_t review_timeout;\n"
        next_call = f"{instance}.p_api->timeoutGet({instance}.p_ctrl, &review_timeout)"
    elif driver == "cgc":
        declarations += "cgc_clock_t review_clock;\ncgc_divider_cfg_t review_dividers;\n"
        next_call = f"{instance}.p_api->systemClockGet({instance}.p_ctrl, &review_clock, &review_dividers)"
    else:
        next_call = f"{instance}.p_api->close({instance}.p_ctrl)"
    probe = declarations + "void hal_entry(void)\n{\n    " + call + "\n    if (FSP_SUCCESS == review_result)\n    {\n        review_result = " + next_call + ";\n    }\n    while (1) { __NOP(); }\n}"
    evidence = ROOT / "review/evidence"
    results = []
    for core, suffix in (("CM85", "cpu0"), ("CM33", "cpu1")):
        name = f"review_r015_{driver}_{suffix}"
        project = ROOT / "validation/ra8p1/review-drivers" / name
        if project.exists():
            raise RuntimeError("Fresh checkpoint refuses an existing project: " + str(project))
        command = ["embedder", "e2", "project", "create", name, "--location", str(project), "--fsp", "5.9.0", "--board", "EK-RA8P1", "--core", core, "--template", "Bare Metal - Minimal", "--debugger", "jlink", "--no-build"]
        if core == "CM33":
            command += ["--preceding", "review_r015_cpu0"]
        run(command, evidence / f"r015-{driver}-{suffix}-create.log")
        entry = project / "src/hal_entry.c"
        original = entry.read_text()
        match = re.search(r"void\s+hal_entry\s*\(\s*void\s*\)\s*\{", original)
        if match is None:
            raise RuntimeError("Expected fresh Minimal application entry")
        end, depth = match.end(), 1
        while depth:
            depth += (original[end] == "{") - (original[end] == "}")
            end += 1
        # Only the user-owned application function and probe declarations change.
        entry.write_text(original[:match.start()] + probe + original[end:])
        command = ["embedder", "e2", "config", "set", str(project), "--add", f"r_{driver}:{instance}", "--build"]
        log = evidence / f"r015-{driver}-{suffix}-default-first-build.log"
        output = run(command, log)
        if "verified: yes" not in output or "configurator problems: 0" not in output:
            raise RuntimeError("No verified default-stack build: " + str(log))
        results.append({"core": core, "project": str(project.relative_to(ROOT)), "log": str(log.relative_to(ROOT)), "verified": True})
    report = evidence / f"r015-{driver}-default-first-builds.json"
    with report.open("x") as stream:
        json.dump(results, stream, indent=2)
        stream.write("\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
