#!/usr/bin/env python3
"""Recompile only changed shared TUs in frozen stock configurations, without e2.

The archive hash pins configs, includes, GNU commands and captured objects.
Pristine selected sources/headers must match nested baseline HEAD. Candidate
bytes are snapshotted from their owning baseline paths into the scratch copy.
This is an object regression, not a generated-project build or a runtime test.
Opt-in --direct controls use only original-release packs, native MDF-derived C
configs and a documented HOCO-only scratch clock choice. Their generated IDE
controls stay explicitly unverified; no installed pack or host cache is read.
Generated controls are separately labelled: pristine HEAD versus current shared
sources using actual candidate-generated configs, NOT a stock-generated capture.
Only --capture-generated invokes e2, restricted to lane 2 and owned fixtures.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import struct
import subprocess
import tarfile
import tempfile
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = Path("validation/ra8p1/regression/fixtures.json")
# The production WDT host matrix already checks legacy executable equivalence.
EXCLUDED = {"ra/fsp/src/r_wdt/r_wdt.c"}
LAZY = {
    "ra8d1": ("EK-RA8D1", "M85 display-class startup/TCM, PLLCCR type 3"),
    "ra4m2": ("EK-RA4M2", "M33 legacy TrustZone and PLLCCR type 1"),
    "ra4m1": ("EK-RA4M1", "M4 non-TrustZone, region-0 MPU mask and PLLCCR type 2"),
    "ra0e1": ("FPB-RA0E1", "M23 no cache/FPU, register-set-B clocks and no PLL"),
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def run(command, *, cwd=None, diagnostics=False):
    result = subprocess.run(command, cwd=cwd, capture_output=True, timeout=60)
    if result.returncode:
        raise ValueError(f"Command failed ({result.returncode}): {shlex.join(map(str, command))}\n"
                         + result.stdout.decode(errors="replace")
                         + result.stderr.decode(errors="replace"))
    return result.stdout + result.stderr if diagnostics else result.stdout


def snapshot(root, manifest):
    baseline = root / "baseline"
    head = run(["git", "-C", str(baseline), "rev-parse", "HEAD"]).decode().strip()
    if head != manifest["baseline_commit"]:
        raise ValueError(f"Nested baseline HEAD moved: {head}")
    paths = run(["git", "-C", str(baseline), "diff", "--name-only", "-z", "HEAD", "--", "ra/fsp"])
    changed = {}
    for name in paths.decode().split("\0"):
        if name and Path(name).suffix in (".c", ".h"):
            original = run(["git", "-C", str(baseline), "show", f"HEAD:{name}"])
            current = (baseline / name).read_bytes()
            if current != original:
                changed[name] = (original, current)
    if not any(name.endswith(".c") and name not in EXCLUDED for name in changed):
        raise ValueError("No changed shared production translation units to compare")
    return changed


def readonly_sections(data):
    """ARM ELF32 allocated executable/constant bytes plus symbolic relocations.

    Debug, writable RAM and ELF bookkeeping are deliberately outside this gate.
    Relocation symbol names/locations are compared too: identical BL placeholder
    bytes alone must not hide a changed call target. No relocation is masked.
    """
    if data[:7] != b"\x7fELF\x01\x01\x01":
        raise ValueError("Expected a little-endian ELF32 ARM relocatable object")
    header = struct.unpack_from("<HHIIIIIHHHHHH", data, 16)
    if header[:2] != (1, 40) or header[10] != 40 or not header[11]:
        raise ValueError("Expected an ARM ET_REL object with section headers")
    start, count, names_index = header[5], header[11], header[12]
    sections = [struct.unpack_from("<IIIIIIIIII", data, start + 40 * i) for i in range(count)]

    def contents(section):
        offset, size = section[4:6]
        if offset + size > len(data):
            raise ValueError("Truncated ELF section")
        return data[offset:offset + size]

    def string(table, offset):
        return table[offset:table.index(b"\0", offset)].decode()

    names = contents(sections[names_index])
    labels = [string(names, s[0]) for s in sections]
    selected = {i for i, s in enumerate(sections) if s[2] & 2 and not s[2] & 1
                and s[1] != 8 and s[5]}  # SHF_ALLOC, !SHF_WRITE, !SHT_NOBITS
    result = {}
    for i in selected:
        section = sections[i]
        if labels[i] in result:
            raise ValueError("Duplicate allocated section: " + labels[i])
        result[labels[i]] = {
            "kind": "executable" if section[2] & 4 else "constant",
            "type": section[1], "flags": section[2], "alignment": section[8],
            "size": section[5], "sha256": sha256(contents(section)), "relocations": [],
        }
    for section in sections:
        if section[1] not in (4, 9) or section[7] not in selected:  # RELA / REL
            continue
        symbols = sections[section[6]]
        strings = contents(sections[symbols[6]])
        step = 12 if section[1] == 4 else 8
        raw = contents(section)
        for offset in range(0, len(raw), step):
            location, info = struct.unpack_from("<II", raw, offset)
            symbol = struct.unpack_from("<IIIBBH", data, symbols[4] + (info >> 8) * symbols[9])
            name, value, size, flags, other, index = symbol
            target_section = labels[index] if index < count else index
            relocation = [location, info & 255, string(strings, name), target_section,
                          value, size, flags, other]
            if step == 12:
                relocation.append(struct.unpack_from("<i", raw, offset + 8)[0])
            result[labels[section[7]]]["relocations"].append(relocation)
    if not result:
        # A legitimately empty conditional TU is still compared byte-for-byte
        # across its empty section set; fixture-level nonempty checks follow.
        return {}
    return result


def compare(reference, candidate, description):
    before, after = readonly_sections(reference), readonly_sections(candidate)
    different = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
    if different:
        raise ValueError(description + ": executable/constant section drift: " + ", ".join(different))
    return after


def unpack_fixture(root, spec, destination):
    archive = root / spec["archive"]
    if sha256(archive.read_bytes()) != spec["sha256"]:
        raise ValueError("Frozen fixture archive hash drift: " + spec["archive"])
    with tarfile.open(archive) as package:
        seen = set()
        for member in package.getmembers():
            path = PurePosixPath(member.name)
            if (path.is_absolute() or ".." in path.parts or not path.parts
                    or path.parts[0] != spec["archive_root"]):
                raise ValueError("Unsafe fixture archive path: " + member.name)
            if member.isdir():
                continue
            if not member.isfile() or member.name in seen:
                raise ValueError("Non-regular or duplicate fixture entry: " + member.name)
            seen.add(member.name)
            target = destination.joinpath(*path.parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(package.extractfile(member).read())


def compile_command(row, tree, output):
    args = row.get("arguments") or shlex.split(row["command"])
    original = Path(row["directory"]).parent
    source = Path(row["file"]).relative_to(original)
    if "-c" not in args or args.count("-o") != 1:
        raise ValueError("Fixture does not record a unique compile/output command")
    # Only paths move. Keep optimization, ABI, defines, warnings and includes.
    mapped = [arg.replace(str(original) + "/", str(tree) + "/") for arg in args]
    mapped[mapped.index("-o") + 1] = str(output)
    if str(tree / source) not in mapped:
        raise ValueError("Recorded source is absent from compile command")
    working = tree / Path(row["directory"]).relative_to(original)
    return mapped, working, source


def check_fixture(root, spec, changed, compiler_version):
    with tempfile.TemporaryDirectory(prefix="fsp-stock-regression-") as temp:
        scratch = Path(temp)
        tree = scratch / "project"
        unpack_fixture(root, spec, tree)
        database = tree / "Debug/compile_commands.json"
        rows = json.loads(database.read_text())
        family = tree / "ra_cfg/fsp_cfg/bsp/bsp_mcu_family_cfg.h"
        if f"#define BSP_MCU_GROUP_{spec['group']} (1)" not in family.read_text():
            raise ValueError("Wrong stock fixture MCU group: " + spec["group"])
        # The hash-pinned archive is the stock evidence. Its former live project
        # may be refreshed/reconfigured for a separately labelled candidate build.
        selected = []
        for row in rows:
            original = Path(row["directory"]).parent
            relative = Path(row["file"]).relative_to(original).as_posix()
            if relative in changed and relative.endswith(".c") and relative not in EXCLUDED:
                selected.append((relative, row))
        if not selected:
            raise ValueError("Fixture has no changed shared TU commands")
        overlaid = {}
        for relative, (pristine, current) in changed.items():
            target = tree / relative
            if target.is_file():
                if target.read_bytes() != pristine:
                    raise ValueError("Captured source/header differs from pristine HEAD: " + relative)
                target.write_bytes(pristine)
                overlaid[relative] = {"pristine_sha256": sha256(pristine), "current_sha256": sha256(current)}
        compiler = (selected[0][1].get("arguments") or shlex.split(selected[0][1]["command"]))[0]
        version = run([compiler, "-dumpfullversion"]).decode().strip()
        if version != compiler_version:
            raise ValueError(f"Recorded GNU compiler version drift: {version}, expected {compiler_version}")
        result = {"scope": "Frozen original-stock archive comparison; live project is independent candidate work",
                  "archive": spec["archive"], "archive_sha256": spec["sha256"],
                  "configuration_sha256": sha256((tree / "configuration.xml").read_bytes()),
                  "compile_commands_sha256": sha256(database.read_bytes()),
                  "compiler": compiler, "compiler_version": version,
                  "compiler_sha256": sha256(Path(compiler).read_bytes()),
                  "owning_source_overlay": overlaid, "translation_units": {}}
        originals = {}
        for relative, row in selected:
            output = scratch / (Path(relative).stem + ".pristine.o")
            command, cwd, _ = compile_command(row, tree, output)
            if command[0] != compiler:
                raise ValueError("Fixture records mixed compilers")
            diagnostics = run(command, cwd=cwd, diagnostics=True).decode(errors="replace")
            captured = tree / "Debug" / Path(relative).with_suffix(".o")
            original = output.read_bytes()
            compare(captured.read_bytes(), original, "Captured versus recompiled HEAD " + relative)
            originals[relative] = original
            result["translation_units"][relative] = {
                "captured_object_sha256": sha256(captured.read_bytes()),
                "pristine_object_sha256": sha256(original),
                "command": [arg.replace(str(scratch), "$SCRATCH") for arg in command],
                "pristine_diagnostics": diagnostics,
            }
        for relative in overlaid:
            (tree / relative).write_bytes(changed[relative][1])
        for relative, row in selected:
            output = scratch / (Path(relative).stem + ".candidate.o")
            command, cwd, _ = compile_command(row, tree, output)
            diagnostics = run(command, cwd=cwd, diagnostics=True).decode(errors="replace")
            current = output.read_bytes()
            sections = compare(originals[relative], current, "Current versus HEAD " + relative)
            result["translation_units"][relative].update({
                "candidate_object_sha256": sha256(current), "sections": sections,
                "candidate_diagnostics": diagnostics, "matches_head_and_capture": True,
            })
        if not any(tu["sections"] for tu in result["translation_units"].values()):
            raise ValueError("Fixture comparison contains no executable/constant bytes")
        result["success"] = True
        return result


def stock_packs(root, manifest):
    """Read only the original 5.9 release; never consult installed support areas."""
    spec = manifest["stock_release"]
    provenance = json.loads((root / "reference/provenance.json").read_text())["baseline"]["archive"]
    if (spec["archive"], spec["sha256"]) != (provenance["path"], provenance["sha256"]):
        raise ValueError("Stock release is not the preserved provenance archive")
    data = (root / spec["archive"]).read_bytes()
    if sha256(data) != spec["sha256"]:
        raise ValueError("Original release archive hash drift")
    result = {}
    names = ["Renesas.RA", "Arm.CMSIS6"]
    for device in ("ra8m1", "ra6t2", *LAZY):
        board = device + ("_mck" if device == "ra6t2" else "_fpb" if device == "ra0e1" else "_ek")
        names.extend(("Renesas.RA_mcu_" + device, "Renesas.RA_board_" + board))
    with zipfile.ZipFile(io.BytesIO(data)) as release:
        for name in names:
            version = "6.1.0+fsp.5.9.0" if name == "Arm.CMSIS6" else "5.9.0"
            packed = release.read(f"internal/projectgen/ra/packs/{name}.{version}.pack")
            with zipfile.ZipFile(io.BytesIO(packed)) as pack:
                result[name] = (sha256(packed), {n: pack.read(n) for n in pack.namelist()
                                                if not n.endswith("/") and (n.endswith((".h", ".c", ".pdsc"))
                                                                          or n.startswith(".module_descriptions/"))})
    return result


def pack_control_inventory(root, manifest, changed, packs):
    """No compiler, extraction or IDE: declare the precise changed-TU slice first."""
    result = lazy_dependencies(root)
    shared = packs["Renesas.RA"][1]
    for device, entry in result.items():
        mcu = packs["Renesas.RA_mcu_" + device][1]
        board = device + ("_fpb" if device == "ra0e1" else "_ek")
        board_files = packs["Renesas.RA_board_" + board][1]
        board_mdf = ET.fromstring(board_files[f".module_descriptions/Renesas##BSP##Board##{board}####5.9.0.xml"])
        entry["part"] = board_mdf.find("board").get("device")
        native = ET.fromstring(mcu[f".module_descriptions/Renesas##BSP##{device}##device####5.9.0.xml"])
        interfaces = {item.get("interface") for item in native.findall("./bsp/provides")}
        selected = [name for name in changed if name.endswith(".c") and name not in EXCLUDED and name in mcu]
        cgc = "ra/fsp/src/r_cgc/r_cgc.c"
        if cgc in changed and cgc in shared and "interface.mcu.cgc" in interfaces:
            selected.append(cgc)
        entry["changed_translation_units"] = sorted(selected)
        cores = [i.rsplit(".", 1)[1] for i in interfaces if i.startswith("interface.mcu.core.")]
        if len(cores) != 1:
            raise ValueError("Ambiguous original MCU core")
        entry["core"] = cores[0]
        entry["not_applicable"] = {"ra/fsp/src/r_adc_b/r_adc_b.c": "No ADC_B interface on this stock MCU"}
        entry["direct_scope"] = "Original-pack sources/headers with MDF-derived scratch C test configuration; NOT an e2-generated fixture"
        entry["clock_scope"] = "HOCO-only C test configuration using native family HOCO option; not board-default clock qualification"
        entry["generated_control"] = "unverified: original-stock generated configuration/commands/objects not captured; r006 candidate-generated controls are a separate evidence class"
    return result


def render_config(config, properties):
    """Only literal original-MDF substitutions; reject template-language guesses."""
    local = dict(properties)
    for prop in config.findall("property"):
        chosen = properties.get(prop.get("id"), prop.get("default"))
        if chosen is None:
            raise ValueError("Missing original MDF default: " + prop.get("id"))
        options = {opt.get("id"): opt.get("value") for opt in prop.findall("option")}
        local[prop.get("id")] = options.get(chosen, chosen)
        if "bitmapPrefix" in prop.attrib:
            if chosen != "0U":
                raise ValueError("Only empty original bitmap defaults are supported")
            local[prop.get("id")] = ""
    for prop in config.findall("property"):
        if prop.find("export") is not None:
            key = prop.get("id")
            if key in {f"config.bsp.common.id{i}" for i in range(1, 5)} | {"config.bsp.common.id_fixed"}:
                if local.get("config.bsp.common.id_mode") != "0xFFFFFFFF":
                    raise ValueError("Only original unprotected ID-code export is supported")
                local[key] = "F" * (32 if key.endswith("id_fixed") else 8)
            else:
                raise ValueError("Unsupported original property export: " + key)
    content = config.findtext("content", "")

    def replace(match):
        key = match.group(1)
        if key.startswith("interface."):
            return "RA_NOT_DEFINED"  # No peripheral instances or RTOS in this C-only control.
        if key not in local:
            raise ValueError("Unresolved original MDF substitution: " + key)
        return local[key]

    content = re.sub(r"\$\{([^}]+)\}", replace, content)
    if "${" in content or "[#" in content or "[/#" in content:
        raise ValueError("Original MDF needs unsupported configurator template evaluation")
    guard = Path(config.get("path")).stem.upper() + "_H_"
    return f"/* Original FSP5.9 MDF-derived scratch control; NOT e2-generated. */\n#ifndef {guard}\n#define {guard}\n{content}\n#endif\n".encode()


def write_pack_headers(tree, files, translation_units):
    for name, data in files.items():
        if name.startswith("ra/") and (name.endswith(".h") or name in translation_units):
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Unsafe original pack source path")
            target = tree / name
            if target.is_file() and target.read_bytes() != data:
                raise ValueError("Conflicting original pack ownership: " + name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)


def prepare_pack_control(tree, device, entry, packs, captured):
    """Construct C-only inputs in scratch, preserving every original source byte."""
    mcu = packs["Renesas.RA_mcu_" + device][1]
    board = device + ("_fpb" if device == "ra0e1" else "_ek")
    board_files = packs["Renesas.RA_board_" + board][1]
    shared = packs["Renesas.RA"][1]
    for files in (shared, mcu, board_files, packs["Arm.CMSIS6"][1]):
        write_pack_headers(tree, files, entry["changed_translation_units"])
    prefix = ".module_descriptions/"
    board_config = ET.fromstring(board_files[prefix + f"Renesas##BSP##Board##{board}####5.9.0##configuration.xml"])
    properties = {p.get("id"): p.get("value") for p in board_config.findall("./raBspConfiguration/config/property")}
    # These are supported original options, chosen to exercise real SDRAM code
    # and CGC parameter checks. They do not change any archived generated control.
    if "config.bsp.fsp.sdram.enabled" in mcu[prefix + f"Renesas##BSP##{device}##fsp####5.9.0.xml"].decode():
        properties["config.bsp.fsp.sdram.enabled"] = "config.bsp.fsp.sdram.enabled.enabled"
    properties["config.driver.cgc.param_checking_enable"] = "config.driver.cgc.param_checking_enable.enabled"
    # The release template references this host-owned value without declaring a
    # property. This direct C control explicitly disables optional low-voltage mode.
    properties["config.driver.cgc.low_voltage_mode"] = "0"
    documents = [
        (shared, "Renesas##Common##all##fsp_common####5.9.0.xml", "config.bsp.ra"),
        (shared, "Renesas##HAL Drivers##all##r_cgc####5.9.0.xml", "config.driver.cgc"),
        (mcu, f"Renesas##BSP##{device}##device####5.9.0.xml", f"config.bsp.{device}"),
        (mcu, f"Renesas##BSP##{device}##device##{entry['part']}##5.9.0.xml", f"config.bsp.{device}.{entry['part']}"),
        (mcu, f"Renesas##BSP##{device}##fsp####5.9.0.xml", f"config.bsp.{device}.fsp"),
    ]
    board_mdf = ET.fromstring(board_files[prefix + f"Renesas##BSP##Board##{board}####5.9.0.xml"])
    documents.append((board_files, f"Renesas##BSP##Board##{board}####5.9.0.xml", board_mdf.find("board").get("config")))
    configs = {}
    family_text = ""
    for files, name, config_id in documents:
        element = ET.fromstring(files[prefix + name]).find(f"config[@id='{config_id}']")
        if element is None:
            raise ValueError("Missing original configuration: " + config_id)
        content = render_config(element, properties)
        relative = "ra_cfg/" + element.get("path")
        target = tree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        configs[relative] = {"sha256": sha256(content), "origin": name, "content": content.decode()}
        if relative.endswith("bsp_mcu_family_cfg.h"):
            family_text = content.decode()
    # Reuse the actual captured empty vector table and macro vocabulary only;
    # native family/part/capability data all come from this device's original pack.
    for relative in ("ra_gen/vector_data.h", "ra_gen/bsp_clock_cfg.h"):
        content = (captured / relative).read_bytes()
        target = tree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        configs[relative] = {"captured_sha256": sha256(content)}
    clock = tree / "ra_gen/bsp_clock_cfg.h"
    text = clock.read_text()
    frequencies = {int(hz): int(option) for option, hz in re.findall(
        r"BSP_CFG_HOCO_FREQUENCY == (\d+)\s*\n\s*#define BSP_HOCO_HZ\s*\((\d+)\)", family_text)}
    node = board_config.find("./raClockConfiguration/node[@id='board.clock.hoco.freq']")
    hoco_hz = int(node.get("option").rsplit(".", 1)[1][:-1]) * 1000000 if node is not None else min(frequencies)
    if hoco_hz not in frequencies:
        raise ValueError("Native HOCO option is not declared in original family MDF")
    replacements = {"BSP_CFG_HOCO_FREQUENCY": str(frequencies[hoco_hz]),
                    "BSP_CFG_CLOCK_SOURCE": "BSP_CLOCKS_SOURCE_CLOCK_HOCO", "BSP_CFG_SDCLK_OUTPUT": "0",
                    "BSP_CFG_BCLK_OUTPUT": "0"}
    for macro in re.findall(r"^#define (BSP_CFG_\w+)", text, re.M):
        if macro.endswith("_SOURCE") and macro != "BSP_CFG_CLOCK_SOURCE":
            replacements[macro] = "BSP_CLOCKS_CLOCK_DISABLED"
        elif macro.endswith("_FREQUENCY_HZ"):
            replacements[macro] = "0"
        elif macro.endswith("_DIV") and any(x in macro for x in ("ICLK", "PCLK", "FCLK", "CPUCLK")):
            replacements[macro] = "BSP_CLOCKS_SYS_CLOCK_DIV_1"
    for macro, value in replacements.items():
        text, count = re.subn(r"^#define " + macro + r" .*$", f"#define {macro} ({value})", text, flags=re.M)
        if count != 1:
            raise ValueError("Ambiguous captured clock macro: " + macro)
    removed = []
    if "BSP_CFG_SDRAM_ENABLED" not in family_text:
        text = re.sub(r"^#define BSP_CFG_SDCLK_OUTPUT .*\n", "", text, flags=re.M)
        removed.append("BSP_CFG_SDCLK_OUTPUT")
    additions = {"BSP_CFG_LCDCLK_SOURCE": "BSP_CLOCKS_CLOCK_DISABLED",
                 "BSP_CFG_LCDCLK_DIV": "BSP_CLOCKS_SYS_CLOCK_DIV_1"}
    if device == "ra0e1":
        removed.append("BSP_CFG_ICLK_DIV")
        text = re.sub(r"^#define BSP_CFG_ICLK_DIV .*\n", "", text, flags=re.M)
        additions.update({"BSP_CFG_HOCO_DIV": "BSP_CLOCKS_SYS_CLOCK_DIV_1",
                          "BSP_CFG_MOCO_DIV": "BSP_CLOCKS_SYS_CLOCK_DIV_1",
                          "BSP_CFG_XTAL_DIV": "BSP_CLOCKS_SYS_CLOCK_DIV_1",
                          "BSP_CFG_FSXP_SOURCE": "BSP_CLOCKS_SOURCE_CLOCK_SUBCLOCK",
                          "BSP_CFG_CLKOUT1_SOURCE": "BSP_CLOCKS_CLOCK_DISABLED"})
    text = text.replace("#endif /* BSP_CLOCK_CFG_H_ */", "\n".join(
        f"#define {macro} ({value})" for macro, value in additions.items()) + "\n#endif /* BSP_CLOCK_CFG_H_ */")
    clock.write_text(text)
    configs["ra_gen/bsp_clock_cfg.h"].update({"sha256": sha256(clock.read_bytes()), "content": text,
                                            "scratch_overrides": replacements, "scratch_additions": additions,
                                            "scratch_removals": removed})
    return configs


def check_pack_control(root, manifest, device, entry, changed, packs):
    with tempfile.TemporaryDirectory(prefix="fsp-original-pack-control-") as temp:
        scratch = Path(temp)
        captured = scratch / "captured"
        unpack_fixture(root, manifest["fixtures"]["ra8m1"], captured)
        tree = scratch / "project"
        configs = prepare_pack_control(tree, device, entry, packs, captured)
        # Native CPU selection is read from original MCU MDF, not a family guess.
        cpu_options = {
            "cm85": ["-mcpu=cortex-m85+nopacbti", "-mfloat-abi=hard"],
            "cm33": ["-mcpu=cortex-m33", "-mfloat-abi=hard", "-mfpu=fpv5-sp-d16"],
            "cm4": ["-mcpu=cortex-m4", "-mfloat-abi=hard", "-mfpu=fpv4-sp-d16"],
            "cm23": ["-mcpu=cortex-m23", "-mfloat-abi=soft"],
        }
        rows = json.loads((captured / "Debug/compile_commands.json").read_text())
        row = next(r for r in rows if r["file"].endswith("/bsp_clocks.c"))
        original_root = Path(row["directory"]).parent
        template = shlex.split(row["command"])
        template = [arg for arg in template if not arg.startswith(("-mcpu=", "-mfloat-abi=", "-mfpu=", "-D_RA_CORE="))]
        template[1:1] = cpu_options[entry["core"]] + ["-D_RA_CORE=" + entry["core"].upper()]
        compiler = template[0]
        version = run([compiler, "-dumpfullversion"]).decode().strip()
        if version != manifest["compiler_version"]:
            raise ValueError("Recorded GNU compiler version drift")
        (tree / "Debug").mkdir(parents=True, exist_ok=True)
        (tree / "src").mkdir(exist_ok=True)
        overlaid = {}
        for relative, (pristine, current) in changed.items():
            path = tree / relative
            if path.is_file():
                if path.read_bytes() != pristine:
                    raise ValueError("Original-release source/header differs from HEAD: " + relative)
                overlaid[relative] = {"pristine_sha256": sha256(pristine), "current_sha256": sha256(current)}
        result = {"scope": entry["direct_scope"], "generated_control": entry["generated_control"],
                  "clock_scope": entry["clock_scope"], "core": entry["core"], "part": entry["part"],
                  "release_archive_sha256": manifest["stock_release"]["sha256"],
                  "pack_sha256": {name: pair[0] for name, pair in packs.items()
                                  if name in ("Renesas.RA", "Arm.CMSIS6", "Renesas.RA_mcu_" + device,
                                              "Renesas.RA_board_" + device + ("_fpb" if device == "ra0e1" else "_ek"))},
                  "compiler": compiler, "compiler_version": version,
                  "compiler_sha256": sha256(Path(compiler).read_bytes()), "configs": configs,
                  "owning_source_overlay": overlaid, "translation_units": {}}
        originals = {}
        for current_side in (False, True):
            if current_side:
                for relative in overlaid:
                    (tree / relative).write_bytes(changed[relative][1])
            for relative in entry["changed_translation_units"]:
                args = [arg.replace(str(original_root) + "/", str(tree) + "/") for arg in template]
                args[args.index(str(tree / "ra/fsp/src/bsp/mcu/all/bsp_clocks.c"))] = str(tree / relative)
                output = scratch / (Path(relative).stem + (".current.o" if current_side else ".stock.o"))
                args[args.index("-o") + 1] = str(output)
                diagnostics = run(args, cwd=tree / "Debug", diagnostics=True).decode(errors="replace").replace(str(scratch), "$SCRATCH")
                data = output.read_bytes()
                if not current_side:
                    originals[relative] = data
                    result["translation_units"][relative] = {
                        "stock_object_sha256": sha256(data), "stock_diagnostics": diagnostics,
                        "command": [arg.replace(str(scratch), "$SCRATCH") for arg in args],
                    }
                else:
                    sections = compare(originals[relative], data, device + " original-pack versus current " + relative)
                    result["translation_units"][relative].update({
                        "current_object_sha256": sha256(data), "current_diagnostics": diagnostics,
                        "sections": sections, "matches_pristine_original_release": True,
                        "conditional_empty": not bool(sections),
                    })
        # Empty unsupported TUs are reported, never counted as exercised code.
        cgc = result["translation_units"].get("ra/fsp/src/r_cgc/r_cgc.c")
        if cgc and not any(s["kind"] == "executable" for s in cgc["sections"].values()):
            raise ValueError("Direct CGC control did not compile executable code")
        if device == "ra8d1":
            sdram = result["translation_units"].get("ra/fsp/src/bsp/mcu/all/bsp_sdram.c")
            if sdram and ".text.R_BSP_SdramInit" not in sdram["sections"]:
                raise ValueError("Direct SDRAM control did not compile the enabled legacy path")
        result["success"] = True
        return result


def review_metadata(root, manifest, candidate_path=None):
    """Review old metadata bytes and shared defaults against the original release."""
    packs = stock_packs(root, manifest)
    candidate_path = candidate_path or root / manifest["generated_candidate_manifest"]
    candidate = json.loads(candidate_path.read_text())
    result = {"candidate_manifest_sha256": sha256(candidate_path.read_bytes()),
              "old_metadata": {}, "shared_defaults": {}}
    for name, (_, files) in packs.items():
        if name == "Arm.CMSIS6":
            continue
        candidate_name = name + ".5.9.0.pack"
        candidate_spec = candidate["packs"].get(candidate_name)
        if candidate_spec:
            archive = candidate_path.parent / candidate_name
            if sha256(archive.read_bytes()) != candidate_spec["sha256"]:
                raise ValueError("Frozen candidate pack hash drift: " + candidate_name)
            with zipfile.ZipFile(archive) as package:
                current = {n: package.read(n) for n in files if n.startswith(".module_descriptions/")}
        else:
            current = files  # Unmodified board pack retained from the verified stock installation.
        for path, original in files.items():
            if not path.startswith(".module_descriptions/"):
                continue
            if name != "Renesas.RA":
                if current[path] != original:
                    raise ValueError("Older-device metadata drift: " + path)
                local = root / "baseline/module_descriptions" / Path(path).name
                if local.read_bytes() != original:
                    raise ValueError("Owning older-device metadata drift: " + path)
                result["old_metadata"][path] = sha256(original)
                continue
            before, after = ET.fromstring(original), ET.fromstring(current[path])
            old_defaults = {e.get("id"): e.get("default") for e in before.iter("property")}
            new_defaults = {e.get("id"): e.get("default") for e in after.iter("property")}
            if any(new_defaults.get(k) != v for k, v in old_defaults.items()):
                raise ValueError("Existing shared MDF default drift: " + path)
            old_constraints = [e.text for e in before.iter("constraint")]
            new_constraints = [e.text for e in after.iter("constraint")]
            if any(new_constraints.count(c) < old_constraints.count(c) for c in old_constraints):
                raise ValueError("Existing shared MDF constraint removed/changed: " + path)
            for tag in ("guard", "nsc", "signal"):
                if [ET.tostring(e) for e in before.iter(tag)] != [ET.tostring(e) for e in after.iter(tag)]:
                    raise ValueError("Existing shared MDF guard/NSC/signal drift: " + path)
            if current[path] != original:
                if "##r_adc_b##" not in path:
                    raise ValueError("Unreviewed shared MDF change: " + path)
                old_exports = {e.get("id"): e.findtext("export") for e in before.iter("property")}
                new_exports = {e.get("id"): e.findtext("export") for e in after.iter("property")}
                for key, value in old_exports.items():
                    if new_exports[key] != value:
                        index = key.removeprefix("module.driver.adc.user_gain_")
                        neutral = value
                        if index in tuple(map(str, range(8))) and value:
                            neutral = value.replace(f"ADUGTR{index}_UGAINI_Pos", "ADUGTR_UGAIN_INTEGER_Pos").replace(
                                f"ADUGTR{index}_UGAINF_Msk", "ADUGTR_UGAIN_FRACTIONAL_Msk")
                        wrapper = (value and new_exports[key] and
                                   "testExists(\"${interface.mcu.adc_b.adc16h}\")" in new_exports[key]
                                   and new_exports[key].endswith(": " + value + ")"))
                        if not (index in tuple(map(str, range(8))) and value
                                and (wrapper or new_exports[key] == neutral)):
                            raise ValueError("Legacy shared MDF export changed: " + key)
            result["shared_defaults"][path] = {
                "existing_properties": len(old_defaults), "defaults_unchanged": True,
                "existing_constraints_unchanged": True, "guards_nsc_signals_unchanged": True,
                "bytes_unchanged": current[path] == original,
                "sha256": sha256(current[path]),
            }
    return result


def check_module_gates(root, spec):
    data = (root / spec["log"]).read_bytes()
    if sha256(data) != spec["sha256"]:
        raise ValueError("Older-device live module gate evidence drift")
    text = data.decode()
    for driver in spec["drivers"]:
        if f"--creatable {driver} --lane 2" not in text or f'0 modules matching "{driver}"' not in text:
            raise ValueError("New-only module not proven absent from live creatable list: " + driver)
    return {"project": spec["project"], "log": spec["log"], "sha256": spec["sha256"],
            "not_creatable": spec["drivers"], "scope": "Live configurator query on RA8D1; not schema inference"}


def capture_generated(root, manifest):
    """Configure/clean-build the six refreshed existing controls on lane 2 only."""
    folder = root / MANIFEST.parent
    final = manifest["final_generated"]
    revision = final["revision"]
    candidate_path = root / final["candidate_manifest"]
    records = final.setdefault("fixtures", {})
    changed = snapshot(root, manifest)
    candidate = json.loads(candidate_path.read_text())
    allowed = {}
    for pack in candidate["packs"].values():
        for path, digest in pack["entries"].items():
            allowed.setdefault(path, set()).add(digest)

    def e2(label, *args):
        command = ["embedder", "e2", *map(str, args), "--lane", "2"]
        completed = subprocess.run(command, cwd=root, capture_output=True, timeout=600)
        output = completed.stdout.decode() + completed.stderr.decode()
        print(output, end="", flush=True)
        log = folder / (revision + "-" + label + ".log")
        log.write_text(shlex.join(command) + "\n" + output)
        if completed.returncode:
            raise ValueError("e2 failed; see " + str(log))
        return output, log.relative_to(root).as_posix()

    try:
        initial, _ = e2("packs-before", "packs", "verify", "--fsp", "5.9.0")
        if "candidate" not in initial or "all two layers match" not in initial:
            raise ValueError("Frozen candidate pack verification failed")
        metadata = review_metadata(root, manifest, candidate_path)
        (folder / (revision + "-metadata-review.json")).write_text(json.dumps(metadata, indent=2) + "\n")
        for device, relative_project in final["projects"].items():
            project = root / relative_project
            if not (project / ".project").is_file():
                raise ValueError("Existing control is missing; creation is not allowed: " + relative_project)
            name = ET.parse(project / ".project").findtext("name")
            e2(device + "-sources-before", "packs", "verify", "--fsp", "5.9.0", "--project", project)
            additions = ["--add", "r_cgc:g_cgc0"]
            if device != "ra0e1":
                additions += ["--add", "r_wdt:g_wdt0"]
            e2(device + "-modules", "config", "set", project, *additions)
            for checking in ("enabled", "disabled"):
                key = device + "_checks_" + ("on" if checking == "enabled" else "off")
                e2(key + "-config", "config", "set", project, "--bsp", "checking=" + checking)
                output, log = e2(key + "-build", "build", project, "--rebuild")
                if "verified: yes" not in output or "clean: ok, 0 errors, 0 warnings" not in output:
                    raise ValueError("Expected verified actual clean-build: " + key)
                for path, (_, current) in changed.items():
                    target = project / path
                    if target.is_file() and (target.read_bytes() != current or sha256(current) not in allowed.get(path, set())):
                        raise ValueError("Final generated source does not match frozen owner/pack: " + path)
                archive = folder / (key + "-" + revision + "-generated.tar.gz")
                if archive.exists():
                    raise ValueError("Refusing to overwrite frozen candidate evidence: " + str(archive))
                # Only the project-owned directories; no nested regression projects.
                with tarfile.open(archive, "w:gz") as package:
                    for child in sorted(project.iterdir()):
                        if child.name.startswith("regression_") and child.is_dir():
                            continue
                        package.add(child, arcname=name + "/" + child.name)
                records[key] = {"archive": archive.relative_to(root).as_posix(),
                                "sha256": sha256(archive.read_bytes()), "archive_root": name,
                                "project": relative_project, "group": device.upper(), "candidate_revision": revision,
                                "checks": int(checking == "enabled"), "build_log": log,
                                "build_log_sha256": sha256((root / log).read_bytes()),
                                "candidate_manifest_sha256": metadata["candidate_manifest_sha256"],
                                "scope": revision + " candidate-generated configuration; not original stock capture"}
                (root / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
            e2(device + "-sources-after", "packs", "verify", "--fsp", "5.9.0", "--project", project)
        e2("packs-after", "packs", "verify", "--fsp", "5.9.0")
        if snapshot(root, manifest) != changed:
            raise ValueError("Production inputs changed during fixture capture")
    finally:
        e2("lane2-stopped", "daemon", "stop")


def check_generated_fixture(root, spec, changed, compiler_version, candidate_manifest):
    """Pristine/current compile with identical actual candidate-generated inputs."""
    revision = spec.get("candidate_revision", "r006")
    if sha256(candidate_manifest.read_bytes()) != spec["candidate_manifest_sha256"]:
        raise ValueError("Frozen generated-control candidate manifest drift")
    if sha256((root / spec["build_log"]).read_bytes()) != spec["build_log_sha256"]:
        raise ValueError("Generated clean-build evidence drift")
    log = (root / spec["build_log"]).read_text()
    if "verified: yes" not in log or "clean: ok" not in log:
        raise ValueError("Generated control has no verified clean-build evidence")
    with tempfile.TemporaryDirectory(prefix="fsp-generated-regression-") as temp:
        scratch = Path(temp)
        tree = scratch / "project"
        unpack_fixture(root, spec, tree)
        cfg = (tree / "ra_cfg/fsp_cfg/bsp/bsp_cfg.h").read_text()
        if f"#define BSP_CFG_PARAM_CHECKING_ENABLE ({spec['checks']})" not in cfg:
            raise ValueError("Generated parameter checking differs from fixture label")
        family = (tree / "ra_cfg/fsp_cfg/bsp/bsp_mcu_family_cfg.h").read_text()
        if f"#define BSP_MCU_GROUP_{spec['group']} (1)" not in family:
            raise ValueError("Wrong generated fixture MCU group")
        database = tree / "Debug/compile_commands.json"
        rows = json.loads(database.read_text())
        selected = []
        for row in rows:
            relative = Path(row["file"]).relative_to(Path(row["directory"]).parent).as_posix()
            if relative in changed and relative.endswith(".c"):
                selected.append((relative, row))
        if not selected or not any(p.endswith("/r_cgc.c") for p, _ in selected):
            raise ValueError("Generated regression must compile changed CGC and BSP TUs")
        if spec["group"] != "RA0E1" and not any(p.endswith("/r_wdt.c") for p, _ in selected):
            raise ValueError("Generated watchdog-capable control is missing WDT")
        # CGC is common data, not hal_data.c: validate the actual instance despite
        # the CLI's generic per-stack hal_data.c warning for this common module.
        if "const cgc_instance_t g_cgc0 =" not in (tree / "ra_gen/common_data.c").read_text():
            raise ValueError("Generated CGC instance is absent from common_data.c")
        if spec["group"] != "RA0E1" and "const wdt_instance_t g_wdt0 =" not in (tree / "ra_gen/hal_data.c").read_text():
            raise ValueError("Generated WDT instance is absent from hal_data.c")
        compiler = (selected[0][1].get("arguments") or shlex.split(selected[0][1]["command"]))[0]
        version = run([compiler, "-dumpfullversion"]).decode().strip()
        if version != compiler_version:
            raise ValueError("Recorded generated compiler version drift")
        candidate = json.loads(candidate_manifest.read_text())
        allowed = {}
        for pack in candidate["packs"].values():
            for path, digest in pack["entries"].items():
                allowed.setdefault(path, set()).add(digest)
        overlay = {}
        for path, (pristine, current) in changed.items():
            target = tree / path
            if target.is_file():
                packed_sha256 = sha256(target.read_bytes())
                if packed_sha256 not in allowed.get(path, set()):
                    raise ValueError("Generated source is not in frozen " + revision + " pack: " + path)
                if revision == "r008" and sha256(current) != packed_sha256:
                    raise ValueError("Final owning source differs from frozen r008 generated source: " + path)
                overlay[path] = {"pristine_sha256": sha256(pristine), "current_sha256": sha256(current),
                                 "generated_sha256": packed_sha256,
                                 "current_owner_matches_candidate": sha256(current) == packed_sha256}
        result = {"scope": "Pristine HEAD shared sources versus current, both using actual " + revision + "-generated ra_cfg; NOT original generated stock capture",
                  "candidate_revision": revision,
                  "archive": spec["archive"], "archive_sha256": spec["sha256"], "checks": spec["checks"],
                  "compiler": compiler, "compiler_version": version, "compiler_sha256": sha256(Path(compiler).read_bytes()),
                  "candidate_manifest_sha256": spec["candidate_manifest_sha256"], "build_log": spec["build_log"],
                  "configuration_sha256": sha256((tree / "configuration.xml").read_bytes()),
                  "compile_commands_sha256": sha256(database.read_bytes()), "owning_source_overlay": overlay,
                  "generated_inputs": {p.relative_to(tree).as_posix(): sha256(p.read_bytes())
                                       for dirname in ("ra_cfg", "ra_gen") for p in (tree / dirname).rglob("*") if p.is_file()},
                  "translation_units": {}}
        originals = {}
        for pristine_side in (True, False):
            for path in overlay:
                (tree / path).write_bytes(changed[path][0 if pristine_side else 1])
            for path, row in selected:
                output = scratch / (Path(path).stem + (".pristine.o" if pristine_side else ".current.o"))
                args, cwd, _ = compile_command(row, tree, output)
                if args[0] != compiler:
                    raise ValueError("Generated fixture records mixed compilers")
                diagnostics = run(args, cwd=cwd, diagnostics=True).decode().replace(str(scratch), "$SCRATCH")
                data = output.read_bytes()
                if pristine_side:
                    originals[path] = data
                    result["translation_units"][path] = {"pristine_object_sha256": sha256(data),
                        "pristine_diagnostics": diagnostics, "command": [a.replace(str(scratch), "$SCRATCH") for a in args]}
                else:
                    captured = (tree / "Debug" / Path(path).with_suffix(".o")).read_bytes()
                    compare(captured, data, "Generated candidate capture versus recompile " + path)
                    sections = compare(originals[path], data, "Pristine versus current in candidate config " + path)
                    result["translation_units"][path].update({"current_object_sha256": sha256(data),
                        "current_diagnostics": diagnostics, "captured_candidate_object_sha256": sha256(captured),
                        "matches_pristine_in_generated_config": True, "matches_candidate_capture": True,
                        "conditional_empty": not bool(sections), "sections": sections})
        if spec["group"] == "RA6T2" and revision == "r008":
            result["legacy_gain_aliases"] = check_legacy_gain_aliases(tree, scratch, selected)
        result["success"] = True
        return result


def check_legacy_gain_aliases(tree, scratch, selected):
    """Compile-prove every neutral gain field equals the native legacy definition."""
    source = scratch / "legacy_gain_aliases.c"
    assertions = ['#include "r_adc_b.h"']
    fields = (("INTEGER_Pos", "UGAINI_Pos"), ("INTEGER_Msk", "UGAINI_Msk"),
              ("FRACTIONAL_Pos", "UGAINF_Pos"), ("FRACTIONAL_Msk", "UGAINF_Msk"))
    for index in range(8):
        for neutral, legacy in fields:
            assertions.append(f'_Static_assert(R_ADC_B0_ADUGTR_UGAIN_{neutral} == '
                              f'R_ADC_B0_ADUGTR{index}_{legacy}, "legacy gain {index} {legacy}");')
    source.write_text("\n".join(assertions) + "\n")
    path, row = next((path, row) for path, row in selected if path.endswith("/r_adc_b.c"))
    args, cwd, _ = compile_command(row, tree, scratch / "legacy_gain_aliases.o")
    args[args.index(str(tree / path))] = str(source)
    diagnostics = run(args, cwd=cwd, diagnostics=True).decode()
    return {"assertions": 32, "source": source.read_text(), "diagnostics": diagnostics,
            "command": [arg.replace(str(scratch), "$SCRATCH") for arg in args], "success": True}


def lazy_dependencies(root):
    result = {}
    for device, (board, reason) in LAZY.items():
        name = f"stock_{device}_regression"
        parent = "validation/ra8p1/regression/controls"
        project = f"{parent}/{name}"
        result[device] = {
            "status": "fixture_missing" if not (root / project / "Debug/compile_commands.json").is_file()
                      else "fixture_present_but_not_hash_registered",
            "reason": reason,
            "precondition": "Parent must use isolated pristine stock FSP 5.9.0; no candidate packs/sources.",
            "parent_next_commands": [
                "embedder e2 packs verify --fsp 5.9.0",
                f"embedder e2 project create {name} --fsp 5.9.0 --board {board} --location {parent} --no-build",
                f"embedder e2 config set {project} --add r_cgc:g_cgc0 --build",
                f"tar -czf validation/ra8p1/regression/{name}-before.tar.gz -C {parent} {name}",
                f"shasum -a 256 validation/ra8p1/regression/{name}-before.tar.gz",
            ],
            "after_capture": "Register archive path/root/hash/project/group in fixtures.json, then rerun this tool.",
            "direct_next_command": f"python3 tools/ra8p1/regression.py --direct {device} --report validation/ra8p1/regression/results.json",
        }
    return result


def regress(root=ROOT, fixtures=None, direct=(), generated=False):
    root = Path(root)
    manifest = json.loads((root / MANIFEST).read_text())
    if manifest["schema"] != 1:
        raise ValueError("Unsupported regression manifest schema")
    changed = snapshot(root, manifest)
    report = {"scope": "Offline changed shared TU comparisons; frozen e2 logs separately evidence candidate-generated builds; no target-runtime claim",
              "baseline_commit": manifest["baseline_commit"], "fixtures": {},
              "excluded": sorted(EXCLUDED & changed.keys()), "lazy_dependencies": lazy_dependencies(root)}
    names = fixtures or list(manifest["fixtures"])
    covered = set()
    for name in names:
        try:
            entry = check_fixture(root, manifest["fixtures"][name], changed, manifest["compiler_version"])
            covered.update(entry["translation_units"])
        except (ValueError, OSError, struct.error) as error:
            entry = {"success": False, "error": str(error)}
        report["fixtures"][name] = entry
    report["uncovered_changed_translation_units"] = sorted(
        name for name in changed if name.endswith(".c") and name not in covered and name not in EXCLUDED)
    report["pack_controls"] = {}
    if direct:
        packs = stock_packs(root, manifest)
        inventory = pack_control_inventory(root, manifest, changed, packs)
        report["lazy_dependencies"] = inventory
        for device in direct:
            try:
                entry = check_pack_control(root, manifest, device, inventory[device], changed, packs)
                covered.update(entry["translation_units"])
            except (ValueError, OSError, struct.error) as error:
                entry = {"success": False, "error": str(error)}
            report["pack_controls"][device] = entry
    report["generated_fixtures"] = {}
    if generated:
        if generated == "r008":
            final = manifest["final_generated"]
            specs, devices = final["fixtures"], final["projects"]
            candidate_path = root / final["candidate_manifest"]
            revision = final["revision"]
        else:
            specs, devices = manifest["generated_fixtures"], LAZY
            candidate_path = root / manifest["generated_candidate_manifest"]
            revision = "r006"
        report["generated_revision"] = revision
        report["metadata_review"] = review_metadata(root, manifest, candidate_path)
        report["older_module_gates"] = check_module_gates(root, manifest["older_module_gates"])
        for name, spec in specs.items():
            try:
                entry = check_generated_fixture(root, spec, changed, manifest["compiler_version"], candidate_path)
                covered.update(entry["translation_units"])
            except (ValueError, OSError, struct.error) as error:
                entry = {"success": False, "error": str(error)}
            report["generated_fixtures"][name] = entry
        required = {device + "_checks_" + mode for device in devices for mode in ("on", "off")}
        report["missing_generated_fixtures"] = sorted(required - report["generated_fixtures"].keys())
    report["uncovered_by_any_object_control"] = sorted(
        name for name in changed if name.endswith(".c") and name not in covered and name not in EXCLUDED)
    # Reject an invalid evidence snapshot if another writer changed production inputs mid-run.
    final = snapshot(root, manifest)
    unstable = sorted(name for name in changed.keys() | final.keys() if changed.get(name) != final.get(name))
    report["changed_during_run"] = unstable
    report["success"] = bool(names) and not unstable and not report.get("missing_generated_fixtures") and all(
        v["success"] for v in list(report["fixtures"].values()) + list(report["pack_controls"].values())
        + list(report["generated_fixtures"].values()))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", action="append", help="Fixture name from fixtures.json; defaults to all")
    parser.add_argument("--inventory", action="store_true", help="Read-only original-pack changed-TU inventory; no compiler")
    parser.add_argument("--direct", action="append", choices=["all"] + list(LAZY),
                        help="Opt-in native original-pack scratch controls, not generated builds")
    parser.add_argument("--report", type=Path, help="Write JSON evidence under validation/ra8p1/regression")
    parser.add_argument("--generated", nargs="?", const="r008", choices=("r006", "r008"),
                        help="Compare archived candidate-generated controls (default r008)")
    parser.add_argument("--capture-generated", action="store_true", help="Configure/clean-build six existing refreshed r008 controls on lane 2, then stop lane")
    args = parser.parse_args()
    if args.capture_generated:
        manifest = json.loads((ROOT / MANIFEST).read_text())
        capture_generated(ROOT, manifest)
        return 0
    if args.inventory:
        manifest = json.loads((ROOT / MANIFEST).read_text())
        report = pack_control_inventory(ROOT, manifest, snapshot(ROOT, manifest), stock_packs(ROOT, manifest))
    else:
        devices = list(LAZY) if args.direct and "all" in args.direct else args.direct or ()
        report = regress(fixtures=args.fixture, direct=devices, generated=args.generated)
    if args.report:
        destination = args.report.resolve()
        destination.relative_to((ROOT / MANIFEST.parent).resolve())
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2) + "\n")
    if args.inventory:
        print(json.dumps(report, indent=2))
        return 0
    for name, fixture in report["fixtures"].items():
        if fixture["success"]:
            print(f"{name}: PASS {len(fixture['translation_units'])} changed TUs match pristine HEAD and captured objects")
        else:
            print(f"{name}: FAIL {fixture['error']}")
    for name, fixture in report["pack_controls"].items():
        if fixture["success"]:
            print(f"{name}: PASS {len(fixture['translation_units'])} original-pack scratch TUs; original-stock generated capture UNVERIFIED")
        else:
            print(f"{name}: FAIL {fixture['error']}")
    for name, fixture in report["generated_fixtures"].items():
        if fixture["success"]:
            print(f"{name}: PASS {len(fixture['translation_units'])} pristine/current TUs in actual candidate-generated config")
        else:
            print(f"{name}: FAIL {fixture['error']}")
    print("Uncovered by original-stock captures: " + ", ".join(report["uncovered_changed_translation_units"]))
    if report["changed_during_run"]:
        print("Inputs changed during run: " + ", ".join(report["changed_during_run"]))
    if report["generated_fixtures"]:
        print("Frozen " + report["generated_revision"] + " candidate-generated configurations are not original-stock generated captures.")
    else:
        print("Lazy stock fixtures: " + ", ".join(report["lazy_dependencies"]) + " (not passed; --inventory gives parent commands)")
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
