#!/usr/bin/env python3
"""Offline compatibility-follow-up regression; never invokes e2 or edits controls.

Consume new, immutable generated-control archives only after the parent freezes
and installs the candidate. Original-release and candidate code use the SAME
recorded compiler command and generated inputs; debug/writable sections are not
compared. Historical r008 evidence is deliberately left in its original tree.
"""
import argparse
import ast
import io
import json
from pathlib import Path
import re
import shlex
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from . import regression

ROOT = regression.ROOT
ICU = "ra/fsp/src/r_icu/r_icu.c"
PORTS = ("rm_freertos_port", "rm_threadx_port")
SOURCE_SUFFIXES = (".c", ".S", ".s")
CONTROL_DRIVERS = {
    "ra8m1": ("r_icu", "r_agt", "r_i3c", "r_lpm", "r_lvd", "r_sci_b_spi"),
    "ra6t2": ("r_icu", "r_agt", "r_lpm", "r_lvd", "r_sci_b_spi"),
    "ra8d1": ("r_icu", "r_agt", "r_i3c", "r_glcdc", "r_mipi_dsi", "r_lpm", "r_lvd", "r_sci_b_spi"),
    "ra4m2": ("r_icu", "r_agt", "r_lpm", "r_lvd"),
    "ra4m1": ("r_icu", "r_agt", "r_lpm", "r_lvd"),
    "ra0e1": ("r_icu", "r_lpm", "r_lvd"),
}
CAPABILITY_UNITS = tuple(sorted({f"ra/fsp/src/{driver}/{driver}.c"
                                 for drivers in CONTROL_DRIVERS.values() for driver in drivers}))
CHECK_MACROS = {path: Path(path).stem.removeprefix("r_").upper() + "_CFG_PARAM_CHECKING_ENABLE"
                for path in CAPABILITY_UNITS}
CLOCKS = "ra/fsp/src/bsp/mcu/all/bsp_clocks.c"
LEGACY_CAPABILITIES = {
    CLOCKS: ("BSP_FEATURE_CGC_HAS_MRAM_CLOCKS",),
    "ra/fsp/src/r_agt/r_agt.c": ("BSP_FEATURE_AGT_REGISTER_TYPE",),
}


def control_units(device, units):
    required = {CLOCKS, *(f"ra/fsp/src/{driver}/{driver}.c" for driver in CONTROL_DRIVERS[device])}
    if device == "ra8d1":
        required.add("ra/fsp/src/bsp/mcu/all/bsp_sdram.c")
    return sorted(set(units) & required)


def integer_macro(values, name):
    """Resolve generated checking aliases, not arbitrary preprocessor expressions."""
    seen = set()
    while name not in seen:
        seen.add(name)
        value = values.get(name, "").strip("() \t")
        if re.fullmatch(r"[0-9]+[uUlL]*", value):
            return int(value.rstrip("uUlL"))
        if not re.fullmatch(r"[A-Za-z_]\w*", value):
            break
        name = value
    raise ValueError("Unresolved generated integer macro: " + name)


def validate_legacy_capabilities(path, values):
    for name in LEGACY_CAPABILITIES.get(path, ()):
        if integer_macro(values, name) != 0:
            raise ValueError("Legacy control selected target-only capability: " + name)


def original_files(root, historical):
    """Read selected source/header inputs from the hash-verified 5.9 release."""
    # This also checks the archive identity against preserved provenance.
    packs = regression.stock_packs(root, historical)
    result = {}
    for _, files in packs.values():
        for name, data in files.items():
            if name.startswith("ra/"):
                if name in result and result[name] != data:
                    raise ValueError("Conflicting original pack owners: " + name)
                result[name] = data
    # Include actual kernel dependencies and assembler omitted by the old reader.
    archive = root / historical["stock_release"]["archive"]
    with zipfile.ZipFile(archive) as release:
        for basename in ("Renesas.RA.5.9.0", "Amazon.FreeRTOS-Kernel.11.1.0+fsp.5.9.0",
                         "Microsoft.ThreadX.6.4.0+fsp.5.9.0"):
            name = "internal/projectgen/ra/packs/" + basename + ".pack"
            with zipfile.ZipFile(io.BytesIO(release.read(name))) as pack:
                for name in pack.namelist():
                    prefix = "ra/fsp/" if basename.startswith("Renesas.RA.") else (
                        "ra/aws/" if basename.startswith("Amazon.") else "ra/microsoft/")
                    if name.startswith(prefix) and name.endswith((".h", *SOURCE_SUFFIXES)):
                        data = pack.read(name)
                        if name in result and result[name] != data:
                            raise ValueError("Conflicting original pack owners: " + name)
                        result[name] = data
    return result


def current_owner_bytes(root, name):
    owner = root / "baseline" / name
    if not owner.is_file():
        raise ValueError("Missing current owning input: " + name)
    try:
        return owner.read_bytes()
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError) as error:
        raise ValueError("Missing current owning input: " + name) from error


def changed_inputs(root, original):
    changed = {}
    for name, data in original.items():
        if name.startswith("ra/fsp/") and name.endswith((".h", *SOURCE_SUFFIXES)):
            current = current_owner_bytes(root, name)
            if current != data:
                changed[name] = (data, current)
    return changed


def source_rows(rows):
    result = {}
    for row in rows:
        path = Path(row["file"]).relative_to(Path(row["directory"]).parent).as_posix()
        if path in result:
            raise ValueError("Duplicate generated compile command: " + path)
        result[path] = row
    return result


def affected_units(changed, original):
    units = {name for name in changed if name.endswith(SOURCE_SUFFIXES)}
    for port in PORTS:
        prefix = "ra/fsp/src/" + port + "/"
        if any(name.startswith(prefix) for name in changed):
            # GNU C port files are selected by the real generated database. A
            # header-only adaptation must still cause these owners to be tested.
            units.update(name for name in original if name.startswith(prefix)
                         and name.endswith(SOURCE_SUFFIXES))
    return sorted(units)


def inventory(root=ROOT):
    historical = json.loads((root / regression.MANIFEST).read_text())
    original = original_files(root, historical)
    changed = changed_inputs(root, original)
    units = affected_units(changed, original)
    controls = {}
    for device, relative in historical["final_generated"]["projects"].items():
        project = root / relative
        rows = source_rows(json.loads((project / "Debug/compile_commands.json").read_text()))
        feature = (project / f"ra/fsp/src/bsp/mcu/{device}/bsp_feature.h").read_text()
        match = re.search(r"#define\s+BSP_FEATURE_BSP_HAS_SP_MON\s+\((\d+)UL\)", feature)
        controls[device] = {
            "project": relative, "status": "pending-final-candidate",
            "recorded_changed_units": sorted(set(units) & rows.keys()),
            "icu_command_present": ICU in rows,
            "capability_commands": {path: path in rows for path in CAPABILITY_UNITS},
            "rtos_commands": sorted(name for name in rows if any("/" + p + "/" in name for p in PORTS)),
            "stack_monitor_capability": int(match[1]) if match else None,
            "required_configuration": ["Add " + Path(path).stem + " through configurator"
                                       for path in control_units(device, CAPABILITY_UNITS) if path not in rows],
        }
    return {"schema": 1, "scope": "Read-only configuration inventory; NOT regression results",
            "historical_revision": "r008 (not current compatibility evidence)",
            "changed_translation_units": units,
            "changed_rtos_inputs": sorted(name for name in changed if any("/" + p + "/" in name for p in PORTS)),
            "controls": controls,
            "blockers": ["Parent has not released a frozen, installed final candidate",
                         "All affected controls need fresh checks-on/off generation and clean links",
                         "Changed RTOS ports require real kernel/generated port configs; RA4M1 exercises SPMON=1"],
            "success": False}


def validate_evidence(root, spec, candidate_manifest):
    if regression.sha256(candidate_manifest.read_bytes()) != spec["candidate_manifest_sha256"]:
        raise ValueError("Frozen candidate manifest drift")
    log = (root / spec["build_log"]).read_bytes()
    if regression.sha256(log) != spec["build_log_sha256"]:
        raise ValueError("Generated build evidence drift")
    if b"verified: yes" not in log or b"clean: ok" not in log:
        raise ValueError("No verified clean generated build")
    if spec["checks"] not in (0, 1):
        raise ValueError("Parameter checking must be 0 or 1")
    if not spec.get("required_translation_units"):
        raise ValueError("Explicit required translation units are missing")


def macro_values(command, cwd):
    """Inspect active branches without adding defines or altering generated files."""
    args = list(command)
    index = args.index("-o")
    del args[index:index + 2]
    args.remove("-c")
    args += ["-E", "-dM"]
    text = regression.run(args, cwd=cwd).decode()
    return dict(re.findall(r"^#define ([A-Za-z_]\w*)[ \t]*(.*)$", text, re.M))


def preserve_captured_file_macros(command, row, tree):
    """Restore the native response-file source spelling; never rewrite constants."""
    captured_root = Path(row["directory"]).parent
    source = Path(row["file"]).relative_to(captured_root)
    cwd = tree / Path(row["directory"]).relative_to(captured_root)
    response = cwd / source.with_suffix(".o.in")
    if not response.is_file():
        return command
    native = shlex.split(response.read_text())[-1]
    if Path(native).is_absolute() or (cwd / native).resolve() != (tree / source).resolve():
        raise ValueError("Native response-file source differs from compile database: " + str(source))
    return [native if arg == str(tree / source) else arg for arg in command]


def kernel_inputs(tree, required, original):
    checked = {}
    for port, folder, header in (("rm_freertos_port", "ra/aws/FreeRTOS/FreeRTOS", "FreeRTOS.h"),
                                 ("rm_threadx_port", "ra/microsoft/azure-rtos/threadx", "tx_api.h")):
        if not any("/" + port + "/" in path for path in required):
            continue
        if original is None or not any((tree / folder).rglob(header)):
            raise ValueError("Missing hash-verified original kernel inputs for " + port)
        for path in (tree / folder).rglob("*"):
            if path.is_file() and path.suffix in (".h", *SOURCE_SUFFIXES):
                name = path.relative_to(tree).as_posix()
                data = path.read_bytes()
                if original.get(name) != data:
                    raise ValueError("Kernel dependency differs from original release: " + name)
                checked[name] = regression.sha256(data)
    return checked


def check_fixture(root, spec, changed, compiler_version, candidate_manifest, original=None, *, working_tree=False):
    validate_evidence(root, spec, candidate_manifest)
    candidate = json.loads(candidate_manifest.read_text())
    allowed = {}
    for pack in candidate["packs"].values():
        for path, digest in pack["entries"].items():
            allowed.setdefault(path, set()).add(digest)
    with tempfile.TemporaryDirectory(prefix="fsp-compat-regression-") as temp:
        scratch = Path(temp)
        tree = scratch / "project"
        regression.unpack_fixture(root, spec, tree)
        database = tree / "Debug/compile_commands.json"
        rows = source_rows(json.loads(database.read_text()))
        required = set(spec["required_translation_units"])
        required.update(path for path in rows if path in changed and path.endswith(SOURCE_SUFFIXES))
        missing = sorted(required - rows.keys())
        if missing:
            raise ValueError("Missing real generated commands (no borrowed flags): " + ", ".join(missing))
        if not required <= changed.keys():
            raise ValueError("Required unit has no original-release/current owner inputs")
        unknown_options = set(spec.get("macro_expectations", {})) - required
        if unknown_options:
            raise ValueError("Option expectations name uncompiled units: " + ", ".join(sorted(unknown_options)))
        cfg = (tree / "ra_cfg/fsp_cfg/bsp/bsp_cfg.h").read_text()
        if f"#define BSP_CFG_PARAM_CHECKING_ENABLE ({spec['checks']})" not in cfg:
            raise ValueError("Generated parameter checking differs from label")
        family = (tree / "ra_cfg/fsp_cfg/bsp/bsp_mcu_family_cfg.h").read_text()
        if f"#define BSP_MCU_GROUP_{spec['group']} (1)" not in family:
            raise ValueError("Wrong generated MCU group")
        kernels = kernel_inputs(tree, required, original)
        overlay = {}
        for path, (pristine, current) in changed.items():
            target = tree / path
            if target.is_file():
                digest = regression.sha256(target.read_bytes())
                if digest not in allowed.get(path, set()):
                    raise ValueError("Frozen project/pack mismatch: " + path)
                owner_digest = regression.sha256(current)
                if not working_tree and digest != owner_digest:
                    raise ValueError("Frozen owner/project/pack mismatch: " + path)
                overlay[path] = {"pristine_sha256": regression.sha256(pristine),
                                 "candidate_sha256": owner_digest, "generated_sha256": digest,
                                 "owner_matches_generated": digest == owner_digest}
        originals = {}
        units = {}
        macros = {}
        for side in (0, 1):
            for path in overlay:
                (tree / path).write_bytes(changed[path][side])
            for index, path in enumerate(sorted(required)):
                output = scratch / f"{index}.o"
                command, cwd, _ = regression.compile_command(rows[path], tree, output)
                command = preserve_captured_file_macros(command, rows[path], tree)
                version = regression.run([command[0], "-dumpfullversion"]).decode().strip()
                if version != compiler_version:
                    raise ValueError("Recorded compiler version drift: " + version)
                diagnostics = regression.run(command, cwd=cwd, diagnostics=True).decode().replace(str(scratch), "$SCRATCH")
                data = output.read_bytes()
                if not side:
                    originals[path] = data
                    units[path] = {"pristine_object_sha256": regression.sha256(data),
                                   "pristine_diagnostics": diagnostics,
                                   "command": [arg.replace(str(scratch), "$SCRATCH") for arg in command],
                                   "compiler_sha256": regression.sha256(Path(command[0]).read_bytes())}
                else:
                    captured = tree / "Debug" / Path(path).with_suffix(".o")
                    if not working_tree:
                        regression.compare(captured.read_bytes(), data, "Captured candidate " + path)
                    sections = regression.compare(originals[path], data, "Original release versus candidate " + path)
                    capture_matches = regression.readonly_sections(captured.read_bytes()) == sections
                    if (spec["group"] == "RA8D1" and path.endswith("/bsp_sdram.c") and
                            ".text.R_BSP_SdramInit" not in sections):
                        raise ValueError("RA8D1 control did not compile enabled legacy SDRAM code")
                    units[path].update(candidate_object_sha256=regression.sha256(data), candidate_diagnostics=diagnostics,
                                        captured_object_sha256=regression.sha256(captured.read_bytes()),
                                        matches_pristine=True, matches_candidate_capture=capture_matches,
                                        conditional_empty=not bool(sections), sections=sections)
                    expectations = spec.get("macro_expectations", {}).get(path, {})
                    if expectations or path in CHECK_MACROS or path in LEGACY_CAPABILITIES:
                        values = macros[path] = macro_values(command, cwd)
                        validate_legacy_capabilities(path, values)
                        if path in CHECK_MACROS:
                            if integer_macro(values, CHECK_MACROS[path]) != spec["checks"]:
                                raise ValueError("Active driver parameter checking differs from label: " + path)
                            if not any(section["kind"] == "executable" for section in sections.values()):
                                raise ValueError("Required driver comparison contains no executable bytes: " + path)
                        for macro, expected in expectations.items():
                            if values.get(macro) != expected:
                                raise ValueError(f"Active option mismatch {path}: {macro}={values.get(macro)!r}, expected {expected!r}")
        return {"success": True,
                "scope": ("Working-tree compile-only replay under historical generated flags; NOT a current generated build"
                          if working_tree else "Original release/current objects under identical real generated flags; not runtime evidence"),
                "current_generated_build_verified": not working_tree,
                "checks": spec["checks"], "group": spec["group"], "translation_units": units,
                "archive_sha256": spec["sha256"], "candidate_manifest_sha256": spec["candidate_manifest_sha256"],
                "original_kernel_inputs": kernels,
                "configuration_sha256": regression.sha256((tree / "configuration.xml").read_bytes()),
                "compile_commands_sha256": regression.sha256(database.read_bytes()), "owning_source_overlay": overlay,
                "active_options": {path: {name: values.get(name)
                                          for name in set(spec.get("macro_expectations", {}).get(path, {})) |
                                          set(LEGACY_CAPABILITIES.get(path, ())) |
                                          ({CHECK_MACROS[path], "BSP_CFG_PARAM_CHECKING_ENABLE"}
                                           if path in CHECK_MACROS else set())}
                                   for path, values in macros.items()},
                "generated_inputs": {p.relative_to(tree).as_posix(): regression.sha256(p.read_bytes())
                                     for folder in ("ra_cfg", "ra_gen") for p in (tree / folder).rglob("*") if p.is_file()}}


def coverage_gaps(fixtures, specs, units, devices):
    passed = {name: entry for name, entry in fixtures.items() if entry["success"]}
    covered = {path for entry in passed.values() for path in entry["translation_units"]}
    uncovered = sorted(set(units) - covered)
    missing = []
    for device in devices:
        for checks in (0, 1):
            matching = [entry for name, entry in passed.items()
                        if specs[name]["group"].lower() == device and specs[name]["checks"] == checks]
            required = control_units(device, units)
            absent = [path for path in required
                      if not any(path in entry["translation_units"] for entry in matching)]
            if not matching or absent:
                label = ", ".join("ICU" if path == ICU else Path(path).stem for path in absent)
                missing.append(f"{device}_checks_{checks} (including changed {label or 'controls'})")
    rtos = []
    for port in PORTS:
        paths = [path for path in units if "/" + port + "/" in path]
        if not paths:
            continue
        for checks in (0, 1):
            for path in paths:
                if not any(specs[name]["checks"] == checks and path in entry["translation_units"]
                           for name, entry in passed.items()):
                    rtos.append(f"{path}: parameter checks {checks}")
        options = [(name, values) for name, entry in passed.items()
                   for path, values in entry.get("active_options", {}).items() if path in paths]
        if not any(specs[name]["group"] == "RA4M1" and values.get("BSP_FEATURE_BSP_HAS_SP_MON") == "(1UL)"
                   for name, values in options):
            rtos.append(port + ": RA4M1 active BSP_FEATURE_BSP_HAS_SP_MON=(1UL)")
        if port == "rm_freertos_port":
            for value in ("0", "1"):
                if not any(values.get("configUSE_TICKLESS_IDLE") in (value, "(" + value + ")")
                           for _, values in options):
                    rtos.append(port + ": active configUSE_TICKLESS_IDLE=" + value)
        elif not any("TX_PORT_VENDOR_STACK_MONITOR_ENABLE" in values and
                     values["TX_PORT_VENDOR_STACK_MONITOR_ENABLE"] is not None for _, values in options):
            rtos.append(port + ": active TX_PORT_VENDOR_STACK_MONITOR_ENABLE")
    return uncovered, missing, rtos


def qualified_options(element, ancestors=()):
    """Keep repeated vendor option IDs scoped to their complete owning XML path."""
    if element.tag == "option":
        yield (ancestors, element.get("id"), element.get("value"))
    owner = ancestors + ((element.tag, element.get("id"), element.get("path")),)
    for child in element:
        yield from qualified_options(child, owner)


# These are selectors, not a general preprocessor or JavaScript evaluator. A
# caller must establish their values from every original MCU's owning inputs.
METADATA_ZERO = ("BSP_FEATURE_ADC_B_REGISTER_TYPE", "BSP_FEATURE_AGT_REGISTER_TYPE",
                 "BSP_FEATURE_MIPI_DSI_STATUS_CLEAR_TYPE", "BSP_FEATURE_BSP_HAS_SECONDARY_CORE")
METADATA_ABSENT = ("interface.mcu.adc_b.adc16h", "interface.mcu.agt.register_type.1",
                   "interface.mcu.i3c.restricted_command_set", "interface.mcu.icu.common_regs",
                   "interface.mcu.glcdc.global_gamma_switch", "interface.mcu.ra8p1.clock_limits",
                   "interface.mcu.ospi_b.1", "interface.mcu.sci_b.no_scksel", "interface.mcu.mipi_csi")
EMITTED_METADATA = ("guard", "nsc", "signal", "content", "header", "includes", "declarations",
                    "functions", "template", "api", "start", "entry")
# Longest tokens first: whitespace must never turn ++ into + +, alter a quoted
# callback/string, swallow an operator, or change a function-like #define.
METADATA_TOKEN = re.compile(
    r'(?m:^[ \t]*\#[^\n]*(?:\n|$))|\\\r?\n|/\*[\s\S]*?\*/|//[^\n]*|'
    r'''"(?:\\[\s\S]|[^"\\\n])*"|'(?:\\[\s\S]|[^'\\\n])*'|'''
    r'\$\{[^{}]*\}|[A-Za-z_]\w*|(?:\d|\.\d)(?:[eEpP][+-]|[\w.])*|'
    r'>>>=|===|!==|>>>|<<=|>>=|\.\.\.|\#\#|\*\*|\+\+|--|&&|\|\||==|!=|<=|>=|<<|>>|->|'
    r'\+=|-=|\*=|/=|%=|&=|\|=|\^=|=>|\?\?|[^\s]')


def metadata_tokens(text, *, javascript=False):
    tokens, previous_end = [], 0
    for match in METADATA_TOKEN.finditer(text):
        token = match[0]
        if token.startswith(("/*", "//")):
            continue
        if token in ('"', "'") or token == "\\":
            raise ValueError("Unrecognized shared MDF token/line continuation")
        if (javascript and tokens and "\n" in text[previous_end:match.start()] and
                (tokens[-1] in ("return", "throw", "break", "continue", "yield", "async", "++", "--") or
                 token in ("++", "--"))):
            tokens.append("<JS_LINE_TERMINATOR>")
        tokens.append(token.strip() if token.lstrip().startswith("#") else token)
        previous_end = match.end()
    return tokens


def legacy_template(text, proof):
    """Select reviewed zero-capability branches; leave every legacy gate intact."""
    tokens = metadata_tokens(text)

    def select(start, stop=False):
        output, index = [], start
        while index < len(tokens):
            token = tokens[index]
            directive = re.match(r"#\s*(if|ifdef|ifndef|elif|else|endif)\b(.*)", token)
            if not directive:
                output.append(token)
                index += 1
                continue
            kind, expression = directive.groups()
            if kind in ("else", "elif", "endif"):
                if stop:
                    return output, index
                raise ValueError("Unbalanced shared MDF template directive")
            branch, end = select(index + 1, True)
            if end == len(tokens):
                raise ValueError("Unterminated shared MDF template branch")
            alternatives = []
            while re.match(r"#\s*(?:else|elif)\b", tokens[end]):
                marker = tokens[end]
                body, finish = select(end + 1, True)
                alternatives.append((marker, body))
                end = finish
                if end == len(tokens):
                    raise ValueError("Unterminated shared MDF template alternative")
            closing = re.sub(r"/\*.*?\*/|//.*", "", tokens[end])
            if not re.fullmatch(r"#\s*endif\s*", closing):
                raise ValueError("Unexpected shared MDF template closing directive")
            value = None
            for macro in proof.get("zero_macros", ()):
                if kind == "if" and expression.strip() in (macro, macro + " == 1"):
                    value = False
            if (kind == "if" and "BSP_FEATURE_BSP_HAS_SECONDARY_CORE" in proof.get("zero_macros", ()) and
                    expression.strip() == "!BSP_FEATURE_BSP_HAS_SECONDARY_CORE || (BSP_CFG_CPU_CORE == 0)"):
                value = True
            if value is not None:
                if alternatives and (len(alternatives) != 1 or alternatives[0][0] != "#else"):
                    raise ValueError("Unexpected reviewed target branch alternative")
                output.extend(branch if value else alternatives[0][1] if alternatives else [])
            else:
                output.extend([token, *branch])
                for marker, body in alternatives:
                    output.extend([marker, *body])
                output.append(tokens[end])
            index = end + 1
        return output, index

    return tuple(select(0)[0])


def qualified_elements(element, tag, ancestors=()):
    """Owner paths retain repeated vendor ids and multiplicity, without ordinals."""
    if element.tag == tag or isinstance(tag, tuple) and element.tag in tag:
        yield ancestors, element
    owner = ancestors + ((element.tag, element.get("id"), element.get("path")),)
    for child in element:
        yield from qualified_elements(child, tag, owner)


def expression_contract(tokens, absent, *, boolean_context=False):
    """Fold only proven testExists gates, preserving opaque legacy expressions.

    This recognizes Boolean/conditional structure, not arithmetic or arbitrary
    JavaScript. Unknown leaves stay exact. No right-hand false gate may erase
    evaluation of a preceding unknown expression.
    """
    tokens = list(tokens)
    depth, top, pairs = [], [], {}
    for index, token in enumerate(tokens):
        if token in ("(", "[", "{"):
            depth.append((token, index))
        elif token in (")", "]", "}"):
            if not depth or depth[-1][0] != {")": "(", "]": "[", "}": "{"}[token]:
                raise ValueError("Unbalanced shared MDF expression")
            _, opening = depth.pop()
            pairs[opening] = index
        elif not depth:
            top.append(index)
    if depth:
        raise ValueError("Unbalanced shared MDF expression")
    if tokens and tokens[0] == "(" and pairs.get(0) == len(tokens) - 1:
        return expression_contract(tokens[1:-1], absent, boolean_context=boolean_context)
    if any(tokens[i] in (";", ",", "=", "=>", "??") for i in top):
        # Lower-precedence operators/statement boundaries cannot be swallowed by
        # a short-circuit proof. They remain opaque and will not equal true.
        return ("opaque", tuple(tokens))
    if "?" in [tokens[i] for i in top]:
        question = next(i for i in top if tokens[i] == "?")
        nesting = 0
        colon = None
        for index in top:
            if index <= question:
                continue
            if tokens[index] == "?":
                nesting += 1
            elif tokens[index] == ":":
                if nesting == 0:
                    colon = index
                    break
                nesting -= 1
        if colon is None:
            raise ValueError("Unbalanced shared MDF conditional")
        condition = expression_contract(tokens[:question], absent, boolean_context=True)
        yes = expression_contract(tokens[question + 1:colon], absent, boolean_context=boolean_context)
        no = expression_contract(tokens[colon + 1:], absent, boolean_context=boolean_context)
        return yes if condition is True else no if condition is False else ("?:", condition, yes, no)
    for operator, identity, decisive in (("||", False, True), ("&&", True, False)):
        cuts = [i for i in top if tokens[i] == operator]
        if cuts:
            parts, start = [], 0
            for end in [*cuts, len(tokens)]:
                part = expression_contract(tokens[start:end], absent, boolean_context=boolean_context)
                start = end + 1
                if part is identity and (not parts or boolean_context):
                    continue
                if part is decisive:
                    if not parts:
                        return decisive
                    parts.append(part)
                    break
                if isinstance(part, tuple) and part[0] == operator:
                    parts.extend(part[1])
                else:
                    parts.append(part)
            return identity if not parts else parts[0] if len(parts) == 1 else (operator, tuple(parts))
    if tokens[:1] == ["!"]:
        value = expression_contract(tokens[1:], absent, boolean_context=True)
        if isinstance(value, bool):
            return not value
    for interface in absent:
        if tokens == ["testExists", "(", '"${' + interface + '}"', ")"]:
            return False
    if (len(tokens) == 3 and tokens[1] in ("===", "!==") and
            not any("\\" in t or "${" in t for t in tokens)):
        try:
            left, right = ast.literal_eval(tokens[0]), ast.literal_eval(tokens[2])
        except (ValueError, SyntaxError):
            pass
        else:
            if isinstance(left, str) and isinstance(right, str):
                return (left == right) == (tokens[1] == "===")
    return ("opaque", tuple(tokens))


def literal_eval_script(tokens):
    """Decode only eval's literal-string concatenation, never execute MDF code."""
    if tokens[:2] != ["eval", "("] or tokens[-1:] != [")"]:
        return None
    argument = tokens[2:-1]
    if (not argument or len(argument) % 2 != 1 or any(token != "+" for token in argument[1::2]) or
            any(re.search(r'''\\[^\\'"bfnrtv0-7xu\n\r]''', token) for token in argument[::2])):
        return None
    try:
        values = [ast.literal_eval(token) for token in argument[::2]]
    except (ValueError, SyntaxError):
        return None
    return "".join(values) if all(isinstance(value, str) for value in values) else None


def metadata_expression(text, proof, *, boolean_context=False):
    tokens = metadata_tokens(text)
    defaults = {'"${' + key + '}"': json.dumps(value)
                for key, value in proof.get("new_property_defaults", {}).items()}
    tokens = [defaults.get(token, token) for token in tokens]
    script = literal_eval_script(tokens)
    absent = proof.get("absent_interfaces", ())
    if script is None:
        return expression_contract(tokens, absent, boolean_context=boolean_context)
    # Only these reviewed insertions have statement-level control flow. Exact
    # matching, including the target body, prevents hoisting/scope side effects
    # from being hidden by dropping an arbitrary if(false) statement.
    additions = {
        "interface.mcu.agt.register_type.1": (
            'if (testExists("${interface.mcu.agt.register_type.1}") && ("AGT_CLOCK_AGT_UNDERFLOW" == count_source_string)) { max_divider = 0; }',
            'if (testExists("${interface.mcu.agt.register_type.1}") && (("AGT_CLOCK_LOCO" == count_source_string) || ("AGT_CLOCK_SUBCLOCK" == count_source_string))) { var maximum_source = ("AGT_CLOCK_LOCO" == count_source_string) ? 36045 : 32768; while ((divider < 7) && (${board.clock.peripheral.agt} * Math.pow(2, divider) < 2 * maximum_source)) { period_counts /= 2; divider += 1; } }',
        ),
        "interface.mcu.i3c.restricted_command_set": (
            'if (testExists("${interface.mcu.i3c.restricted_command_set}") && result.actual_frequency > 12500000) { result.valid = false; result.comment_message += "Error: Push-Pull frequency exceeds 12.5 MHz. "; }',
        ),
    }
    tokens = metadata_tokens(script, javascript=True)
    for capability, snippets in additions.items():
        if capability not in absent:
            continue
        for snippet in snippets:
            selected = metadata_tokens(snippet)
            for index in range(len(tokens) - len(selected), -1, -1):
                if tokens[index:index + len(selected)] == selected:
                    del tokens[index:index + len(selected)]
    if "interface.mcu.agt.register_type.1" in absent:
        wrapper = metadata_tokens('if (!testExists("${interface.mcu.agt.register_type.1}") || (("AGT_CLOCK_LOCO" != count_source_string) && ("AGT_CLOCK_SUBCLOCK" != count_source_string))) { divider = 0; }')
        for index in range(len(tokens) - len(wrapper), -1, -1):
            if tokens[index:index + len(wrapper)] == wrapper:
                tokens[index:index + len(wrapper)] = metadata_tokens("divider = 0;")
    # ADC export scripts are straight-line assignments. Reduce only their RHS
    # ternaries; all statement names, order, strings, operations and dispatch
    # remain part of the comparison. Other scripts retain every surviving token.
    if "interface.mcu.adc_b.adc16h" in absent and "=" in tokens and not any(t in tokens for t in ("{", "}", "return", "throw")):
        statements = []
        start, depth = 0, 0
        for index, token in enumerate(tokens):
            depth += (token in ("(", "[", "{")) - (token in (")", "]", "}"))
            if token == ";" and depth == 0:
                statements.append(tokens[start:index])
                start = index + 1
        statements.append(tokens[start:])
        return ("script", tuple((tuple(row[:row.index("=") + 1]),
                                  expression_contract(row[row.index("=") + 1:], absent))
                                 if "=" in row else tuple(row) for row in statements))
    return ("script-tokens", tuple(tokens))


def shared_metadata_invariants(path, pristine, current, *, legacy_proof=None, rxie_options=None):
    """Require the original owner-qualified contracts on every proven legacy path."""
    proof = dict(legacy_proof or {})
    before, after = ET.fromstring(pristine), ET.fromstring(current)
    old_ids = {e.get("id") for e in before.iter("property")}
    proof["new_property_defaults"] = {e.get("id"): e.get("default") for e in after.iter("property")
                                      if e.get("id") not in old_ids and e.get("default") is not None}
    if rxie_options is not None:
        old_prop = before.findall(".//property[@id='" + RXIE + "']")
        new_prop = after.findall(".//property[@id='" + RXIE + "']")
        if (path != DSI_MDF or len(old_prop) != 1 or len(new_prop) != 1 or
                [xml_contract(e) for e in old_prop[0]] != rxie_options or
                len(new_prop[0]) != 1 or new_prop[0][0].tag != "select" or
                new_prop[0][0].attrib != {"enum": RXIE_ENUM} or len(new_prop[0][0])):
            raise ValueError("Existing shared MDF RXIE enum migration drift: " + path)
        old_prop[0][:] = []
    for tag, attribute in (("property", "default"), ("option", "value")):
        old, new = (list(qualified_options(tree)) if tag == "option" else
                    [(owner, element.get("id"), element.get(attribute))
                     for owner, element in qualified_elements(tree, tag)]
                    for tree in (before, after))
        for item in old:
            if item not in new:
                raise ValueError("Existing shared MDF " + attribute + " drift: " + path + ": " + repr(item))
            new.remove(item)

    def emitted(element):
        return (element.tag, sorted(element.attrib.items()), legacy_template(element.text or "", proof),
                legacy_template(element.tail or "", proof), tuple(emitted(child) for child in element))

    for tag in EMITTED_METADATA:
        if ([(owner, emitted(e)) for owner, e in qualified_elements(before, tag)] !=
                [(owner, emitted(e)) for owner, e in qualified_elements(after, tag)]):
            raise ValueError("Existing shared MDF " + tag + " drift: " + path)
    if ([(owner, emitted(e)) for owner, e in qualified_elements(before, EMITTED_METADATA)] !=
            [(owner, emitted(e)) for owner, e in qualified_elements(after, EMITTED_METADATA)]):
        raise ValueError("Existing shared MDF emitted order drift: " + path)
    for tag in ("option", "provides", "enum"):
        contract = (lambda e: (e.attrib, (e.text or "").strip())) if tag == "enum" else xml_contract
        remaining = [(owner, contract(e)) for owner, e in qualified_elements(after, tag)]
        for owner, e in qualified_elements(before, tag):
            item = (owner, contract(e))
            if item not in remaining:
                raise ValueError("Existing shared MDF " + tag + " contract drift: " + path)
            remaining.remove(item)
        if tag == "provides" and any(
                not owner or owner[-1][1] != "module.driver.ospi_on_ospi_b" or
                value[:3] != ("provides", [("interface", "interface.peripheral.ospi_b${module.driver.ospi_b.unit}")], "") or
                value[4] for owner, value in remaining):
            raise ValueError("Unreviewed added shared MDF capability export: " + path)
    rxie_export = '''eval('' +
        'var interrupts = "${module.driver.mipi_dsi.rxie}"; ' +
        'if ("${interface.mcu.mipi_dsi.rxier_no_rxte}" === "1") { ' +
        '    /* RXIER bit 13 is reserved; no tearing-effect trigger receive interrupt. */ ' +
        '    interrupts = interrupts.split("R_DSILINK_RXIER_RXTE_Msk").join("0U"); ' +
        '} ' +
        'interrupts')'''
    neutral_exports = []
    properties = list(qualified_elements(after, "property"))
    for owner, element in qualified_elements(before, "property"):
        key, value = element.get("id"), element.findtext("export")
        matches = [index for index, (parent, e) in enumerate(properties) if parent == owner and e.get("id") == key]
        if not matches:
            raise ValueError("Existing shared MDF property owner missing: " + str(key))
        _, target = properties.pop(matches[0])
        behavioral_attributes = lambda e: {k: v for k, v in e.attrib.items() if k not in ("display", "description")}
        if behavioral_attributes(element) != behavioral_attributes(target):
            raise ValueError("Existing shared MDF property attributes drift: " + str(key))
        exports = target.findall("export")
        if len(exports) > 1 or any(e.attrib or len(e) for e in exports):
            raise ValueError("Existing shared MDF export drift: " + str(key))
        replacement = target.findtext("export")
        if replacement == value:
            continue
        if ("##r_mipi_dsi##" in path and key == RXIE and value is None and replacement and
                metadata_tokens(replacement) == metadata_tokens(rxie_export)):
            neutral_exports.append(key)
            continue
        index = key.removeprefix("module.driver.adc.user_gain_") if key else ""
        neutral = (value.replace(f"ADUGTR{index}_UGAINI_Pos", "ADUGTR_UGAIN_INTEGER_Pos")
                   .replace(f"ADUGTR{index}_UGAINF_Msk", "ADUGTR_UGAIN_FRACTIONAL_Msk")) if value else None
        if (index in tuple(map(str, range(8))) and proof.get("adc_gain_aliases_verified") and
                value and replacement == neutral):
            neutral_exports.append(key)
            continue
        implicit = '"${' + key + '}"' if key else ""
        if metadata_expression(value if value is not None else implicit, proof) != metadata_expression(
                replacement if replacement is not None else implicit, proof):
            raise ValueError("Existing shared MDF export drift: " + str(key))
    if any(e.get("id") in old_ids for _, e in properties):
        raise ValueError("Added shared MDF property duplicates a legacy owner: " + path)
    selects = [(owner, xml_contract(e)) for owner, e in qualified_elements(after, "select")]
    for owner, e in qualified_elements(before, "select"):
        item = (owner, xml_contract(e))
        if item not in selects:
            raise ValueError("Existing shared MDF select drift: " + path)
        selects.remove(item)
    for owner, _ in selects:
        if owner[-1][0] != "property" or owner[-1][1] in old_ids and not (
                rxie_options is not None and owner[-1][1] == RXIE):
            raise ValueError("Added shared MDF select changes legacy options: " + path)
    for tree in (before, after):
        if any(not owner or owner[-1][0] != "property" for owner, _ in qualified_elements(tree, "export")):
            raise ValueError("Unreviewed non-property shared MDF export: " + path)
    dsi = any("##" + driver + "##" in path for driver in ("r_mipi_dsi", "r_mipi_phy"))
    extension = ('("${interface.mcu.mipi_dsi.external}" === "1") && '
                 '((testExists("${interface.mcu.feature_set.b}") && ("${interface.mcu.feature_set.b}" === "1")) || '
                 '(testExists("${interface.mcu.mipi_dsi}") && ("${interface.mcu.mipi_dsi}" === "1") && '
                 'testExists("${interface.mcu.dphycnt}") && ("${interface.mcu.dphycnt}" === "1")))')
    constraints = list(qualified_elements(after, "constraint"))
    extended = []
    for owner, element in qualified_elements(before, "constraint"):
        identical = next((i for i, (parent, e) in enumerate(constraints)
                          if parent == owner and xml_contract(e) == xml_contract(element)), None)
        if identical is not None:
            constraints.pop(identical)
            continue
        expected = metadata_expression(element.text or "", proof, boolean_context=True)
        found = None
        for index, (parent, replacement) in enumerate(constraints):
            if parent != owner or len(replacement) or len(element):
                continue
            attributes_equal = element.attrib == replacement.attrib
            equivalent = expected == metadata_expression(replacement.text or "", proof, boolean_context=True)
            # Capability-dependent range/alignment labels can change without
            # changing legacy admission; non-display attributes remain exact.
            display_only = ({k: v for k, v in element.attrib.items() if k != "display"} ==
                            {k: v for k, v in replacement.attrib.items() if k != "display"})
            target_gate = any('"${' + cap + '}"' in (replacement.text or "")
                              for cap in proof.get("absent_interfaces", ()))
            if equivalent and (attributes_equal or (display_only and target_gate)):
                found = index
                break
            originals = ('("${interface.mcu.mipi_dsi.external}" === "1") && ("${interface.mcu.feature_set.b}" === "1")',
                         '"${interface.mcu.mipi_dsi.external}" === "1" && ("${interface.mcu.feature_set.b}" === "1")')
            if (dsi and attributes_equal and element.get("display") == "Requires MIPI DSI peripheral" and
                    metadata_tokens(element.text or "") in [metadata_tokens(s) for s in originals] and
                    metadata_tokens(replacement.text or "") == metadata_tokens(extension)):
                extended.append(element.get("display"))
                found = index
                break
        if found is None:
            raise ValueError("Existing shared MDF constraint drift: " + path + ": " + str(element.get("display")))
        constraints.pop(found)
    for _, element in constraints:
        if len(element) or metadata_expression(element.text or "", proof, boolean_context=True) is not True:
            raise ValueError("Added shared MDF constraint affects legacy path: " + path + ": " + str(element.get("display")))
    requires = list(qualified_elements(after, "requires"))
    for owner, element in qualified_elements(before, "requires"):
        match = next((index for index, (parent, e) in enumerate(requires)
                      if parent == owner and xml_contract(e) == xml_contract(element)), None)
        if match is not None:
            requires.pop(match)
        elif not (dsi and extended and element.get("id") ==
                  "module.driver.mipi_dsi.requires.mipi_feature_set_hw" and
                  element.get("interface") == "interface.mcu.feature_set.b" and not len(element)):
            raise ValueError("Existing shared MDF requirement drift: " + path)
    if requires:
        raise ValueError("Added shared MDF requirement affects legacy path: " + path)
    return {"defaults_unchanged": True, "option_values_unchanged": True,
            "legacy_exports_preserved_or_neutral_alias": True,
            "guards_nsc_signals_unchanged": True, "legacy_config_templates_unchanged": True,
            "target_branches_qualified": bool(legacy_proof),
            "extended_constraints": extended, "legacy_neutral_exports": neutral_exports,
            "added_constraints": len(constraints),
            "bytes_unchanged": pristine == current, "sha256": regression.sha256(current)}


def legacy_rxie_enum(path, pristine, current, options):
    """The sole permitted old-BSP delta is the exact original ordered RXIE list."""
    before, after = ET.fromstring(pristine), ET.fromstring(current)
    enums = after.findall("./bsp/enum[@id='" + RXIE_ENUM + "']")
    if (len(enums) != 1 or enums[0].attrib != {"id": RXIE_ENUM, "default": ""} or
            [xml_contract(e) for e in enums[0]] != options):
        raise ValueError("Older-device RXIE enum drift: " + path)
    after.find("bsp").remove(enums[0])
    if xml_contract(before) != xml_contract(after):
        raise ValueError("Older-device metadata drift outside RXIE enum: " + path)


def verify_additive_header(path, original, current, prefix, zero_macros=()):
    """No moved conditions, includes, undefs or changed old definitions may hide a gate."""
    old_names = set(re.findall(rb"#define\s+(\w+)", original))
    retained, conditions = [], []
    for token in metadata_tokens(current.decode()):
        directive = re.match(r"#\s*(if|ifdef|ifndef|endif)\b(.*)", token)
        if directive:
            if directive[1] == "endif":
                if not conditions:
                    raise ValueError("Legacy header condition imbalance: " + path)
                conditions.pop()
            else:
                conditions.append(token)
        definition = re.match(r"#define\s+(\w+)\b", token)
        if definition and definition[1] in zero_macros and conditions != ["#ifndef BSP_FEATURE_H"]:
            raise ValueError("Metadata zero capability is conditional: " + path + ": " + definition[1])
        if definition and definition[1].startswith(prefix) and definition[1].encode() not in old_names:
            continue
        retained.append(token)
    if retained != metadata_tokens(original.decode()) or conditions:
        raise ValueError("Legacy header changed beyond additive definitions: " + path)


def metadata_legacy_proof(root, historical, load_pack, *, check_owning):
    """Verify actual original/current inputs, not a target-name-based exemption."""
    shared = regression.stock_packs(root, historical)["Renesas.RA"][1]
    options = [xml_contract(e) for e in ET.fromstring(shared[DSI_MDF]).findall(
        ".//property[@id='" + RXIE + "']/option")]
    if len(options) != 20:
        raise ValueError("Original RXIE option inventory drift")
    proof = {"zero_macros": METADATA_ZERO, "absent_interfaces": METADATA_ABSENT,
             "adc_gain_aliases_verified": False, "devices": {}, "rxie_options": options}
    with zipfile.ZipFile(root / historical["stock_release"]["archive"]) as release:
        names = sorted(name for name in release.namelist() if re.fullmatch(
            r"internal/projectgen/ra/packs/Renesas.RA_mcu_\w+\.5\.9\.0\.pack", name))
        if len(names) != 32:
            raise ValueError("Original legacy MCU inventory is not all 32 devices")
        for name in names:
            basename = Path(name).name
            with zipfile.ZipFile(io.BytesIO(release.read(name))) as package:
                current = load_pack(basename)
                feature = [f for f in package.namelist() if f.endswith("/bsp_feature.h")]
                if len(feature) != 1:
                    raise ValueError("Ambiguous original legacy feature owner: " + basename)
                path = feature[0]
                original = package.read(path)
                data = current.get(path, original)
                if check_owning and current_owner_bytes(root, path) != data:
                    raise ValueError("Owning legacy feature differs from frozen candidate: " + path)
                def definitions(raw):
                    return re.findall(rb"^\s*#define\s+(BSP_FEATURE_\w+)\s+([^\r\n]+)", raw, re.M)
                old, new = definitions(original), definitions(data)
                for item in old:
                    if new.count(item) != 1:
                        raise ValueError("Original legacy capability value drift: " + path + ": " + item[0].decode())
                for macro in METADATA_ZERO:
                    values = [value for key, value in new if key.decode() == macro]
                    if len(values) != 1 or values[0].strip() != b"(0UL)":
                        raise ValueError("Target-only metadata capability is not legacy zero: " + path + ": " + macro)
                verify_additive_header(path, original, data, "BSP_FEATURE_", METADATA_ZERO)
                dependency = str(Path(path).with_name("bsp_peripheral.h"))
                verify_additive_header(dependency, package.read(dependency),
                                       current.get(dependency, package.read(dependency)), "BSP_PERIPHERAL_")
                if check_owning and current_owner_bytes(root, dependency) != current.get(dependency, package.read(dependency)):
                    raise ValueError("Owning legacy feature include differs from frozen candidate: " + dependency)
                generic = [f for f in package.namelist() if re.search(r"##device####5\.9\.0\.xml$", f)]
                if len(generic) != 1:
                    raise ValueError("Original generic device owner missing or ambiguous: " + basename)
                interfaces = {e.get("interface") for e in ET.fromstring(package.read(generic[0])).iter("provides")}
                if {"interface.mcu.mipi_dsi", "interface.mcu.dphycnt"} <= interfaces:
                    parts = [f for f in package.namelist() if re.search(r"##device##[^#]+##5\.9\.0\.xml$", f)]
                    if not parts:
                        raise ValueError("Missing original DSI part admission owners")
                    for part in parts:
                        provided = [e.attrib for e in ET.fromstring(package.read(part)).iter("provides")]
                        if ({"interface": "interface.mcu.mipi_dsi.external"} in provided and
                                {"interface": "interface.mcu.feature_set.b"} not in provided):
                            raise ValueError("Extended DSI admission changes an original part's feature-set gate")
                for mdf in package.namelist():
                    if not mdf.startswith(".module_descriptions/") or mdf.endswith("/"):
                        continue
                    pristine = package.read(mdf)
                    modified = current.get(mdf, pristine)
                    if modified != pristine:
                        if mdf != ".module_descriptions/Renesas##BSP##ra8d1##fsp####5.9.0.xml":
                            raise ValueError("Older-device metadata drift: " + mdf)
                        legacy_rxie_enum(mdf, pristine, modified, options)
                    if check_owning and (root / "baseline/module_descriptions" / Path(mdf).name).read_bytes() != modified:
                        raise ValueError("Owning metadata differs from frozen candidate: " + mdf)
                    interfaces = {e.get("interface") for e in ET.fromstring(modified).iter("provides")}
                    unexpected = interfaces.intersection(METADATA_ABSENT)
                    if unexpected:
                        raise ValueError("Target-only interface exists on older MCU: " + mdf + ": " + repr(unexpected))
                # The neutral ADC aliases must match real 5.9 field positions and
                # masks, not just look like another spelling of their names.
                if basename == "Renesas.RA_mcu_ra6t2.5.9.0.pack":
                    header = "ra/fsp/src/bsp/cmsis/Device/RENESAS/Include/R7FA6T2BD.h"
                    original_header = package.read(header)
                    if current.get(header, original_header) != original_header:
                        raise ValueError("Original ADC register header drift: " + header)
                    for index in range(8):
                        for field, value in (("UGAINI_Pos", "22"), ("UGAINF_Msk", "0x3fffff")):
                            pattern = rb"#define\s+R_ADC_B0_ADUGTR" + str(index).encode() + b"_" + field.encode() + rb"\s+\(" + value.encode() + rb"UL\)"
                            if len(re.findall(pattern, original_header)) != 1:
                                raise ValueError("Original ADC gain field contract drift")
                proof["devices"][basename] = {"feature_sha256": regression.sha256(data),
                                               "original_feature_sha256": regression.sha256(original),
                                               "original_capabilities_preserved": len(old)}
    header = "ra/fsp/inc/instances/r_adc_b.h"
    data = load_pack("Renesas.RA.5.9.0.pack")[header]
    if check_owning and current_owner_bytes(root, header) != data:
        raise ValueError("Owning ADC alias header differs from frozen candidate")
    match = re.search(rb"#if BSP_FEATURE_ADC_B_REGISTER_TYPE == 1\r?\n(?:[ \t]*#define[^\n]*\n)+#else\r?\n((?:[ \t]*#define[^\n]*\n)+)#endif", data)
    expected = {b"R_ADC_B0_ADUGTR_UGAIN_INTEGER_Pos": b"22", b"R_ADC_B0_ADUGTR_UGAIN_FRACTIONAL_Msk": b"0x3FFFFF"}
    if not match:
        raise ValueError("Missing reviewed legacy ADC gain aliases")
    aliases = dict(re.findall(rb"#define\s+(\w+)\s+\(([^)]+)\)", match[1]))
    if any(aliases.get(key) != value for key, value in expected.items()):
        raise ValueError("Legacy ADC gain alias value drift")
    for key in expected:
        if (len(re.findall(rb"#\s*define\s+" + key + rb"\b", data)) != 2 or
                re.search(rb"#\s*undef\s+" + key + rb"\b", data)):
            raise ValueError("Legacy ADC gain alias redefined outside reviewed branches")
    proof["dsi_admission_legacy_equivalent"] = True
    proof["adc_gain_aliases_verified"] = True
    return proof


def review_metadata(root, historical, candidate_manifest, *, check_owning=True):
    candidate = json.loads(candidate_manifest.read_text())
    cache, proof = {}, None

    def load_pack(name):
        if name not in candidate["packs"]:
            return {}
        if name not in cache:
            spec = candidate["packs"][name]
            archive = candidate_manifest.parent / name
            if regression.sha256(archive.read_bytes()) != spec["sha256"]:
                raise ValueError("Frozen metadata pack hash drift: " + name)
            with zipfile.ZipFile(archive) as package:
                files = [item.filename for item in package.infolist() if not item.is_dir()]
                if len(files) != len(set(files)) or set(files) != spec["entries"].keys():
                    raise ValueError("Frozen metadata pack inventory drift: " + name)
                cache[name] = {path: package.read(path) for path in files}
            if any(regression.sha256(data) != spec["entries"][path] for path, data in cache[name].items()):
                raise ValueError("Frozen metadata entry hash drift: " + name)
        return cache[name]

    result = {"success": True, "candidate_manifest_sha256": regression.sha256(candidate_manifest.read_bytes()),
              "current_owning_metadata_checked": check_owning,
              "scope": ("Older BSP metadata identity and shared MDF legacy-contract invariants; not a schema validator"
                        if check_owning else "Immutable candidate versus original release metadata only; NOT current owning freshness"),
              "old_metadata": {}, "shared_defaults": {}}
    for name, (_, files) in regression.stock_packs(root, historical).items():
        if name == "Arm.CMSIS6":
            continue
        pack_name = name + ".5.9.0.pack"
        metadata = {path: data for path, data in files.items() if path.startswith(".module_descriptions/")}
        current = load_pack(pack_name) if pack_name in candidate["packs"] else metadata
        for path, pristine in metadata.items():
            data = current[path]
            owner = root / "baseline/module_descriptions" / Path(path).name
            if check_owning and owner.read_bytes() != data:
                raise ValueError("Owning metadata differs from frozen candidate: " + path)
            if name == "Renesas.RA":
                if pristine != data and proof is None:
                    proof = metadata_legacy_proof(root, historical, load_pack, check_owning=check_owning)
                migration = (proof["rxie_options"] if proof and path == DSI_MDF and
                             ET.fromstring(data).find(".//property[@id='" + RXIE + "']/select") is not None else None)
                result["shared_defaults"][path] = shared_metadata_invariants(
                    path, pristine, data, legacy_proof=proof, rxie_options=migration)
            elif pristine != data:
                if proof and path == ".module_descriptions/Renesas##BSP##ra8d1##fsp####5.9.0.xml":
                    legacy_rxie_enum(path, pristine, data, proof["rxie_options"])
                    result["old_metadata"][path] = {"sha256": regression.sha256(data), "original_rxie_enum_verified": True}
                else:
                    raise ValueError("Older-device metadata drift: " + path)
            else:
                result["old_metadata"][path] = regression.sha256(data)
    if proof:
        result["legacy_selector_proof"] = {key: value for key, value in proof.items() if key != "rxie_options"}
        # RTOS metadata has the same generated-template obligations as shared
        # drivers, and was not included by the older selected-pack reader.
        with zipfile.ZipFile(root / historical["stock_release"]["archive"]) as release:
            for name in ("Amazon.FreeRTOS-Kernel.11.1.0+fsp.5.9.0.pack", "Microsoft.ThreadX.6.4.0+fsp.5.9.0.pack"):
                with zipfile.ZipFile(io.BytesIO(release.read("internal/projectgen/ra/packs/" + name))) as package:
                    current = load_pack(name)
                    for path in package.namelist():
                        if not path.startswith(".module_descriptions/") or path.endswith("/"):
                            continue
                        pristine = package.read(path)
                        data = current.get(path, pristine)
                        if check_owning and (root / "baseline/module_descriptions" / Path(path).name).read_bytes() != data:
                            raise ValueError("Owning RTOS metadata differs from frozen candidate: " + path)
                        result["shared_defaults"][path] = shared_metadata_invariants(path, pristine, data, legacy_proof=proof)
    return result


def reuse_fixture(root, spec, entry, inputs, candidate):
    """Retain exact passed comparisons only while every recorded input is unchanged."""
    validate_evidence(root, spec, candidate)
    if (not entry.get("success") or not entry.get("current_generated_build_verified") or
            entry.get("group") != spec["group"] or entry.get("checks") != spec["checks"] or
            entry.get("archive_sha256") != spec["sha256"] or
            entry.get("candidate_manifest_sha256") != spec["candidate_manifest_sha256"]):
        raise ValueError("Reusable fixture identity drift")
    if regression.sha256((root / spec["archive"]).read_bytes()) != spec["sha256"]:
        raise ValueError("Reusable fixture archive drift")
    if not set(spec["required_translation_units"]) <= entry["translation_units"].keys():
        raise ValueError("Reusable fixture lacks required translation units")
    for path, pair in entry["owning_source_overlay"].items():
        if path not in inputs:
            raise ValueError("Missing reusable owning input: " + path)
        if (pair["pristine_sha256"] != regression.sha256(inputs[path][0]) or
                pair["candidate_sha256"] != regression.sha256(inputs[path][1]) or
                not pair["owner_matches_generated"]):
            raise ValueError("Reusable fixture owning inputs drift: " + path)
    for path, unit in entry["translation_units"].items():
        if (not unit["matches_pristine"] or not unit["matches_candidate_capture"] or
                regression.sha256(Path(unit["command"][0]).read_bytes()) != unit["compiler_sha256"]):
            raise ValueError("Reusable fixture comparison/compiler drift: " + path)
        values = entry.get("active_options", {}).get(path, {})
        validate_legacy_capabilities(path, values)
        for name, expected in spec.get("macro_expectations", {}).get(path, {}).items():
            if values.get(name) != expected:
                raise ValueError("Reusable fixture active option drift: " + name)
    return dict(entry, reused_unchanged_inputs=True)


def regress(root, manifest_path, *, working_tree=False, reuse_report=None):
    manifest = json.loads(manifest_path.read_text())
    historical = json.loads((root / regression.MANIFEST).read_text())
    original = original_files(root, historical)
    changed = changed_inputs(root, original)
    candidate = root / manifest["candidate_manifest"]
    before = {path: regression.sha256(data[1]) for path, data in changed.items()}
    previous = json.loads(reuse_report.read_text()) if reuse_report else None
    if previous and (working_tree or previous.get("mode") != "frozen-generated-candidate" or
                     not previous.get("owners_stable") or previous.get("owner_sha256") != before or
                     previous.get("candidate_manifest") != str(candidate.relative_to(root))):
        raise ValueError("Reusable report production inputs or candidate differ")
    fixtures = {}
    for name, spec in manifest["fixtures"].items():
        try:
            inputs = dict(changed)
            for path in spec["required_translation_units"]:
                if path not in inputs:
                    if path not in CAPABILITY_UNITS and not any("/" + port + "/" in path for port in PORTS):
                        raise ValueError("Unchanged unit outside control scope requested: " + path)
                    inputs[path] = (original[path], current_owner_bytes(root, path))
            retained = previous.get("fixtures", {}).get(name) if previous else None
            if retained and retained.get("success"):
                fixtures[name] = reuse_fixture(root, spec, retained, inputs, candidate)
            else:
                fixtures[name] = check_fixture(root, spec, inputs, historical["compiler_version"], candidate, original,
                                               working_tree=working_tree)
        except (ValueError, OSError, KeyError) as error:
            fixtures[name] = {"success": False, "error": str(error)}
    required_units = sorted(set(affected_units(changed, original)) | set(CAPABILITY_UNITS))
    uncovered, missing, rtos = coverage_gaps(fixtures, manifest["fixtures"], required_units,
                                             historical["final_generated"]["projects"])
    try:
        metadata = review_metadata(root, historical, candidate)
    except (ValueError, OSError, KeyError, ET.ParseError) as error:
        metadata = {"success": False, "error": str(error)}
    after = {path: regression.sha256(data[1]) for path, data in changed_inputs(root, original).items()}
    unstable = sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))
    stable = not unstable
    comparisons_passed = bool(fixtures) and not uncovered and not missing and not rtos and stable and all(
        item["success"] for item in fixtures.values())
    return {"schema": 1, "candidate_manifest": str(candidate.relative_to(root)), "fixtures": fixtures,
            "mode": "working-tree-compile-only" if working_tree else "frozen-generated-candidate",
            "owner_sha256": before,
            "reused_report": ({"path": str(reuse_report), "sha256": regression.sha256(reuse_report.read_bytes())}
                              if reuse_report else None),
            "uncovered_translation_units": uncovered, "missing_control_configurations": missing,
            "missing_rtos_options": rtos, "object_comparisons_passed": comparisons_passed,
            "current_generated_build_verified": comparisons_passed and not working_tree,
            "owners_stable": stable, "changed_during_run": unstable,
            "metadata_review": metadata,
            "success": comparisons_passed and metadata["success"] and not working_tree}


RXIE = "module.driver.mipi_dsi.rxie"
RXIE_ENUM = "enum.driver.mipi_dsi.rxie"
DSI_MDF = ".module_descriptions/Renesas##HAL Drivers##all##r_mipi_dsi####5.9.0.xml"


def xml_contract(element):
    """Compare XML structure/text, ignoring indentation and attribute ordering only."""
    return (element.tag, sorted(element.attrib.items()), (element.text or "").strip(),
            (element.tail or "").strip(), [xml_contract(child) for child in element])


def review_rxie_transfer(before, after):
    """Permit only the reviewed r013 RXIE move; preserve every legacy option value."""
    if before.keys() != after.keys():
        raise ValueError("Transfer pack inventory changed")
    old_dsi = ET.fromstring(before["Renesas.RA.5.9.0.pack"][DSI_MDF])
    options = old_dsi.findall(".//property[@id='" + RXIE + "']/option")
    if not options or len({option.get("id") for option in options}) != len(options):
        raise ValueError("Frozen RXIE options are missing or duplicated")
    changes = {}
    for pack, entries in before.items():
        if entries.keys() != after[pack].keys():
            raise ValueError("Transfer entry inventory changed: " + pack)
        for path, original in entries.items():
            current = after[pack][path]
            if original == current:
                continue
            label = pack + ":" + path
            if not path.startswith(".module_descriptions/"):
                raise ValueError("Transfer non-MDF input changed: " + label)
            if original.replace(b"\r\n", b"\n") == current.replace(b"\r\n", b"\n"):
                changes[label] = "line-endings-only"
                continue
            old, new = ET.fromstring(original), ET.fromstring(current)
            if path == DSI_MDF:
                prop = new.find(".//property[@id='" + RXIE + "']")
                legacy = old.find(".//property[@id='" + RXIE + "']")
                if (prop is None or legacy is None or prop.attrib != legacy.attrib or
                        len(prop) != 1 or prop[0].tag != "select" or
                        prop[0].attrib != {"enum": RXIE_ENUM}):
                    raise ValueError("Transfer RXIE select/default contract changed")
                # Replace only the reviewed property for whole-document comparison.
                prop[:] = list(legacy)
                prop.text = legacy.text
                kind = "RXIE-options-moved-to-device-enum"
            elif path in (".module_descriptions/Renesas##BSP##ra8d1##fsp####5.9.0.xml",
                          ".module_descriptions/Renesas##BSP##ra8p1##fsp####5.9.0.xml"):
                enums = new.findall(".//enum[@id='" + RXIE_ENUM + "']")
                if len(enums) != 1 or enums[0].attrib != {"id": RXIE_ENUM, "default": ""}:
                    raise ValueError("Transfer RXIE enum missing or ambiguous: " + label)
                expected = [dict(option.attrib) for option in options]
                if "##ra8p1##" in path:
                    for option in expected:
                        if option["id"] == RXIE + ".rxte":
                            option["value"] = "0U"
                if ([child.attrib for child in enums[0]] != expected or
                        any(child.tag != "option" or len(child) for child in enums[0])):
                    raise ValueError("Transfer RXIE enum IDs/values changed: " + label)
                parent = next(node for node in new.iter() if enums[0] in list(node))
                parent.remove(enums[0])
                kind = "RXIE-device-enum-added"
            elif path == ".module_descriptions/Renesas##BSP##ra8p1##device####5.9.0.xml":
                capability = old.findall(".//provides[@interface='interface.mcu.mipi_dsi.rxier_no_rxte']")
                if len(capability) != 1:
                    raise ValueError("Frozen RXIE capability missing or ambiguous")
                parent = next(node for node in old.iter() if capability[0] in list(node))
                parent.remove(capability[0])
                kind = "obsolete-target-export-capability-removed"
            else:
                raise ValueError("Transfer unreviewed MDF changed: " + label)
            if xml_contract(old) != xml_contract(new):
                raise ValueError("Transfer XML changed outside RXIE scope: " + label)
            changes[label] = kind
    return {"success": True, "non_metadata_entries_identical": True,
            "legacy_rxie_option_count": len(options), "changes": changes}


def fixture_transfer_fingerprint(tree):
    """Exact build-input inventory; excludes outputs and IDE-only bookkeeping."""
    files = {}
    for folder in ("ra", "ra_cfg", "ra_gen", "src", "script"):
        for path in sorted((tree / folder).rglob("*")):
            if path.is_symlink():
                raise ValueError("Transfer input symlink: " + str(path))
            if path.is_file():
                files[path.relative_to(tree).as_posix()] = regression.sha256(path.read_bytes())
    for name in ("configuration.xml", ".cproject"):
        files[name] = regression.sha256((tree / name).read_bytes())
    for path in [tree / "Debug/memory_regions.ld", *sorted((tree / "Debug").glob("*.elf.in"))]:
        if path.is_file():
            files[path.relative_to(tree).as_posix()] = regression.sha256(path.read_bytes())
    rows = source_rows(json.loads((tree / "Debug/compile_commands.json").read_text()))
    commands, native = {}, {}
    for path, row in sorted(rows.items()):
        if Path(path).suffix == ".ld":
            # e2 adds clang editor-only rows for linker scripts, without -c/-o.
            # Actual linker inputs are hashed above and under script/.
            continue
        command, cwd, _ = regression.compile_command(row, tree, tree / "transfer.o")
        command = preserve_captured_file_macros(command, row, tree)
        commands[path] = {"arguments": [arg.replace(str(tree), "$PROJECT") for arg in command],
                          "directory": str(cwd.relative_to(tree))}
        response = tree / "Debug" / Path(path).with_suffix(".o.in")
        if response.is_file():
            native[path] = regression.sha256(response.read_bytes())
    return {"files": files, "commands": commands, "native_response_files": native}


def compare_transfer_fingerprints(before, after):
    for category in ("files", "commands", "native_response_files"):
        old, new = before[category], after[category]
        changed = sorted(path for path in old.keys() | new.keys() if old.get(path) != new.get(path))
        if changed:
            raise ValueError("Transfer " + category + " drift: " + ", ".join(changed))
    return {"success": True, "build_inputs_identical": True,
            "file_count": len(before["files"]), "command_count": len(before["commands"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, help="New frozen fixture manifest; omission inventories gaps only")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--reuse-report", type=Path,
                        help="Reuse passed strict fixtures only after unchanged-input validation")
    parser.add_argument("--working-tree", action="store_true",
                        help="Compile-only replay of current owners under retained flags; never qualifies a current build")
    args = parser.parse_args(argv)
    if args.working_tree and not args.manifest:
        parser.error("--working-tree requires a retained fixture --manifest")
    if args.reuse_report and (not args.manifest or args.working_tree):
        parser.error("--reuse-report requires a strict fixture --manifest")
    report = regress(ROOT, args.manifest, working_tree=args.working_tree,
                     reuse_report=args.reuse_report) if args.manifest else inventory()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    if args.report.exists():
        raise ValueError("Refusing to overwrite retained evidence: " + str(args.report))
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print("PASS" if report["success"] else "PENDING/FAIL", args.report)
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
