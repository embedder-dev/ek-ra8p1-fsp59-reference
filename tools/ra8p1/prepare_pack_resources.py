#!/usr/bin/env python3
"""Stage the RA8P1 pack trees from original 5.9 structures and owned sources.

No IDE access. The only release input is reference/vendor/FSP_Packs_v5.9.0.zip.
Run again after the other owners finish their baseline sources; absent inputs
are reported, never replaced by sibling firmware or dummy register definitions.
"""
import argparse
from copy import deepcopy
from io import BytesIO
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile

if __package__:
    from .linker_commercial import commercial_files
else:
    from linker_commercial import commercial_files

ROOT = Path(__file__).resolve().parents[2]
VERSION = "5.9.0"
PART = "R7KA8P1KFLCAC"
BASE = "internal/projectgen/ra/packs/"
MCU = "Renesas.RA_mcu_ra8p1.5.9.0"
BOARD = "Renesas.RA_board_ra8p1_ek.5.9.0"
MAIN = "Renesas.RA.5.9.0"
DRIVER_COMPONENTS = {
    "r_mram": ("r_flash_hp", "MRAM", ("r_flash_api.h",)),
    "r_dac_b": ("r_dac", "12-bit D/A Converter B", ("r_dac_api.h",)),
    "r_pdm": ("r_ssi", "Pulse Density Modulation Interface", ("r_pdm_api.h",)),
}


def xml_bytes(node):
    # e2's XMI loader requires the original literal xmi:version prefix.
    for prefix, uri in (("projgen", "http:///projgen.ecore"),
                        ("xmi", "http://www.omg.org/XMI"),
                        ("xsi", "http://www.w3.org/2001/XMLSchema-instance")):
        ET.register_namespace(prefix, uri)
    ET.indent(node, space="  ")
    return ET.tostring(node, encoding="utf-8", xml_declaration=True) + b"\n"


def original_packs(root):
    archive = root / "reference/vendor/FSP_Packs_v5.9.0.zip"
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != "99c4abae6239a68171fcbff86070971f591f0a8945e90a50eb07d87843bee363":
            raise ValueError("Original FSP 5.9.0 release archive hash mismatch")
    with ZipFile(archive) as release:
        result = {}
        for kind in ("mcu_ra8m1", "mcu_ra6m5", "board_ra8m1_ek", "main"):
            basename = "Renesas.RA.5.9.0.pack" if kind == "main" else "Renesas.RA_" + kind + ".5.9.0.pack"
            with ZipFile(BytesIO(release.read(BASE + basename))) as pack:
                result[kind] = {n: pack.read(n) for n in pack.namelist() if not n.endswith("/")}
    return result


def adapt(text):
    return (text.replace("R7FA8M1AHECBD", PART).replace("R7FA8M1AH", "R7KA8P1KF")
            .replace("RA8M1", "RA8P1").replace("ra8m1", "ra8p1"))


def descriptor(stock, board=False):
    tree = ET.fromstring(adapt(stock.decode()))
    components = tree.find("components")
    for component in list(components):
        if component.get("Cvariant") and component.get("Cvariant") != PART:
            components.remove(component)
            continue
        files = component.find("files")
        seen = set()
        for item in list(files):
            name = item.get("name", "")
            if (item.get("condition") not in (None, "", "Only_GCC")
                    or name in seen
                    or (board and name.endswith("/board_ethernet_phy.h"))):
                files.remove(item)
            else:
                seen.add(name)
    conditions = tree.find("conditions")
    if conditions is not None:
        for condition in list(conditions):
            if condition.get("id") != "Only_GCC":
                conditions.remove(condition)
    if not board:
        files = tree.find("./components/component[@Csub='fsp']/files")
        linker = files.find("file[@category='linkerScript']")
        files.remove(linker)
        for compiler, suffix in (("GCC", "ld"), ("CLANG", "lld"), ("IAR", "icf"), ("ARMCC", "scat")):
            for core, cpu in (("CM85", "Cortex-M85"), ("CM33", "Cortex-M33")):
                identifier = "Only_" + core + "_and_" + compiler
                condition = ET.SubElement(conditions, "condition", id=identifier)
                ET.SubElement(condition, "require", Dcore=cpu)
                ET.SubElement(condition, "require", Tcompiler=compiler)
                entry = deepcopy(linker)
                entry.set("name", "script/fsp" + ("_cpu1" if core == "CM33" else "") + "." + suffix)
                entry.set("condition", identifier)
                files.append(entry)
                if compiler == "ARMCC":
                    companion = deepcopy(entry)
                    companion.set("name", "script/ac6/fsp_keep.via")
                    files.append(companion)
    return tree


def linker_script(stock, contract, core):
    """Keep the stock startup/data/stack sections; replace device allocation/OFS."""
    text = stock.decode().replace("\r\n", "\n")
    cfg = contract["cores"][core]
    # e2 emits the RA8P1 secure option region as OPTION_SETTING; its physical
    # OPTION_SETTING_S alias is not exported to memory_regions.ld.
    reserve_option_length = "(OPTION_SETTING_S_LENGTH != 0)"
    if text.count(reserve_option_length) != 1:
        raise ValueError("Original linker NS-RAM option-region contract changed")
    text = text.replace(reserve_option_length, "(OPTION_SETTING_LENGTH != 0)")
    # Allocation belongs to the pack, not a stale generated memory_regions.ld.
    for name, region in (("FLASH", "MRAM"), ("RAM", "SRAM")):
        start, size = cfg[region]["start"], cfg[region]["size"]
        if name == "FLASH":
            text = text.replace("ORIGIN = FLASH_ORIGIN, LENGTH = LIMITED_FLASH_LENGTH",
                                "ORIGIN = " + start + ", LENGTH = " + size)
        else:
            text = text.replace("ORIGIN = RAM_START, LENGTH = RAM_LENGTH",
                                "ORIGIN = " + start + ", LENGTH = " + size)
    # The original script's RAM boundary symbols must describe this core too.
    override = "\n/* RA8P1 HM 5.1: deterministic disjoint core allocations. */\n"
    for key, region in (("FLASH", "MRAM"), ("RAM", "SRAM"), ("ITCM", "ITCM"), ("DTCM", "DTCM")):
        override += "{0}_START = {1};\n{0}_LENGTH = {2};\n".format(key, cfg[region]["start"], cfg[region]["size"])
    text = text.replace("INCLUDE memory_regions.ld", "INCLUDE memory_regions.ld\n" + override)
    # Do not inherit RA8M1's option map, gap fill or flash/security registers.
    a = text.index("  OPTION_SETTING (r)")
    b = text.index("  ID_CODE (rx)", a)
    text = text[:a] + ("  OPTION_SETTING (r) : ORIGIN = 0x02c9f000, LENGTH = 0x400\n"
                       "  OPTION_SETTING_NS (r) : ORIGIN = 0x12c9f400, LENGTH = 0x400\n") + text[b:]
    a = text.index("    /* Symbol required for RA Configuration tool. */\n    __tz_OPTION_SETTING_S =")
    text = text[:a]
    text += "    /* HM 7.2.1-7.2.7: only explicitly ported option words. */\n"
    text += "    __tz_OPTION_SETTING_S = 0x02c9f000;\n    __tz_OPTION_SETTING_N = 0x02c9f400;\n"
    text += "    __tz_OPTION_SETTING_S_S = 0x02c9f000;\n    __tz_OPTION_SETTING_S_N = 0x02c9f400;\n"
    text += "    __tz_OPTION_SETTING_DATA_FLASH_S_S = 0;\n    __tz_OPTION_SETTING_DATA_FLASH_S_N = 0;\n"
    for section, info in contract["options"].items():
        if core != info["owner"]:
            continue
        region = "OPTION_SETTING_NS" if int(info["address"], 0) >= 0x10000000 else "OPTION_SETTING"
        text += "    {0} {1} : {{ KEEP(*({0})) }} > {2}\n".format(section, info["address"], region)
        text += '    ASSERT(SIZEOF({0}) <= 4, "RA8P1 option word overflow: {0}")\n'.format(section)
    text += "    .unsupported_option_settings : { KEEP(*(.option_setting*)) } > FLASH\n"
    text += '    ASSERT(SIZEOF(.unsupported_option_settings) == 0, "Unported or secondary-core option settings")\n'
    text += "}\n"
    text += 'ASSERT(!DEFINED(PROJECT_NONSECURE), "RA8P1 Non-secure partitions are not qualified; use the flat CPU0/CPU1 allocation")\n'
    text += 'ASSERT(ORIGIN(FLASH) >= 0x02000000 && ORIGIN(FLASH) + LENGTH(FLASH) <= 0x02100000, "MRAM bounds")\n'
    text += 'ASSERT(ORIGIN(RAM) >= 0x22000000 && ORIGIN(RAM) + LENGTH(RAM) <= 0x221a0000, "SRAM bounds")\n'
    # Declaring PHDRS disables GNU's automatic segment creation. Give each
    # allocated output its own segment so sparse option words never include
    # reserved bytes, without changing section flags or startup copy ranges.
    loads = []
    def load_segment(match):
        name = "ra8p1_load_" + str(len(loads))
        loads.append("  " + name + " PT_LOAD;\n")
        return match.group(0) + " :" + name
    text = re.sub(r"} > [A-Z][A-Z0-9_]*(?: AT > [A-Z][A-Z0-9_]*)?", load_segment, text)
    if text.count("\nSECTIONS\n{") != 1 or not loads:
        raise ValueError("Original linker allocated-section contract changed")
    text = text.replace("\nSECTIONS\n{", "\nPHDRS\n{\n" + "".join(loads) + "}\n\nSECTIONS\n{")
    return text.encode()


def resource_files(stock, contract):
    files = {}
    mcu = stock["mcu_ra8m1"]
    pdsc = descriptor(mcu["Renesas.RA_mcu_ra8m1.pdsc"])
    files["Renesas.RA_mcu_ra8p1.pdsc"] = xml_bytes(pdsc)
    pg = ET.fromstring(mcu[".mcu/.devices/pg/pgra8m1.xmi"])
    cpu = pg.find("./Target/CpuType/Cpu")
    cpu.set("shortName", "RA8P1")
    for pins in list(cpu.findall("PinCountRZTC")):
        cpu.remove(pins)
    pins = ET.SubElement(cpu, "PinCountRZTC", shortName="RA8P1 - 289 Pin", isUsedInPG="true", PinNumber="289")
    ET.SubElement(pins, "Device", shortName=PART, DeviceCommand="R7KA8P1KF")
    files[".mcu/.devices/pg/pgra8p1.xmi"] = xml_bytes(pg)
    memory = ET.fromstring(mcu[".mcu/.devices/pg/memoryr7fa8m1ahecbd.xmi"])
    mmap = memory.find("memoryMap")
    mmap.set("device", PART)
    for item, name in zip(mmap.findall("memoryArea"), ("MRAM", "SRAM")):
        info = contract["physical"][name]
        item.set("startAddress", info["start"])
        item.set("endAddress", hex(int(info["start"], 0) + int(info["size"], 0)))
    files[".mcu/.devices/pg/memoryr7ka8p1kflcac.xmi"] = xml_bytes(memory)
    dbg = ET.fromstring(mcu[".mcu/.devices/dbg/dbgra8m1.xml"])
    template = deepcopy(dbg.find("device"))
    for item in list(dbg):
        dbg.remove(item)
    for name in ("R7KA8P1KF", "R7KA8P1KF_CPU0", "R7KA8P1KF_CPU1"):
        item = deepcopy(template)
        item.find("name").text = name
        item.find("./server/params/param").text = "-t " + (name if "_CPU" in name else "R7KA8P1KF_CPU0")
        dbg.append(item)
    files[".mcu/.devices/dbg/dbgra8p1.xml"] = xml_bytes(dbg)
    gdb = ET.fromstring(mcu[".mcu/.devices/gdb/ra8m1.5.9.0.xml"])
    devices = gdb.find("Devices")
    template = deepcopy(devices.find("Device"))
    for item in list(devices):
        devices.remove(item)
    for core in ("CM85", "CM33"):
        cfg = contract["cores"][core]
        item = deepcopy(template)
        item.attrib.update(cpuName=cfg["debugger"], mcuFile=cfg["debugger"] + ".mcu", armFamily=core)
        if core == "CM33":
            item.attrib.pop("mve", None)
            item.attrib.pop("pacbti", None)
        for child in list(item):
            item.remove(child)
        # No inherited security monitor, unknown part-id location or dummy SFR.
        if core == "CM85":
            for section, info in contract["options"].items():
                ET.SubElement(item, "MemMonitor", address=info["address"], size="4", name=section[16:], write="false")
        devices.append(item)
    files[".mcu/.devices/gdb/ra8p1.5.9.0.xml"] = xml_bytes(gdb)
    zone = ET.fromstring(mcu[".mcu/.devices/zone/R7FA8M1AHECBD.rzone"])
    device = zone.find("device")
    device.set("Dname", "R7KA8P1KF")
    proc = deepcopy(device.find("processor"))
    for child in list(device):
        device.remove(child)
    for core in ("CM85", "CM33"):
        item = deepcopy(proc)
        item.attrib.update(Pname=core, Dcore=contract["cores"][core]["compiler"].replace("cortex", "Cortex").replace("m", "M"),
                           Dclock=str(contract["cores"][core]["max_clock_hz"]), DnumInterrupts="96")
        # Required by the stock zone schema; CPU revisions are HM 2.1.1 p.111.
        item.set("DcoreVersion", {"CM85": "r1p1", "CM33": "r0p4"}[core])
        device.append(item)
    memories = zone.find("./resources/memories")
    for child in list(memories):
        memories.remove(child)
    def mem(name, start, size, kind="ROM", **attrs):
        ET.SubElement(memories, "memory", name=name, start=start, size=size, type=kind, security=attrs.pop("security", ""), **attrs)
    cpu0 = contract["cores"]["CM85"]
    for name, key, kind in (("FLASH", "MRAM", "ROM"), ("RAM", "SRAM", "RAM"), ("ITCM", "ITCM", "ROM"), ("DTCM", "DTCM", "RAM")):
        mem(name, cpu0[key]["start"], cpu0[key]["size"], kind)
        mem(name + "_NS", hex(int(cpu0[key]["start"], 0) + 0x10000000), cpu0[key]["size"], kind, physical=cpu0[key]["start"], security="n")
    cpu1 = contract["cores"]["CM33"]
    mem("FLASH_CPU1", cpu1["MRAM"]["start"], cpu1["MRAM"]["size"])
    mem("RAM_CPU1", cpu1["SRAM"]["start"], cpu1["SRAM"]["size"], "RAM")
    mem("CTCM_CPU1", cpu1["ITCM"]["bus_alias"], cpu1["ITCM"]["size"], "RAM")
    mem("STCM_CPU1", cpu1["DTCM"]["bus_alias"], cpu1["DTCM"]["size"], "RAM")
    mem("OPTION_SETTING", "0x02c9f000", "0x400")
    mem("OPTION_SETTING_S", "0x02c9f000", "0x400", physical="0x02c9f000")
    mem("OPTION_SETTING_NS", "0x12c9f400", "0x400")
    # Keep names consumed by the 5.9 script; zero size means unavailable, not fitted memory.
    for name in ("DATA_FLASH", "OPTION_SETTING_DATA_FLASH_S", "ID_CODE", "SDRAM", "QSPI_FLASH", "OSPI_DEVICE_0", "OSPI_DEVICE_1"):
        mem(name, "0x0", "0x0", "RAM" if name == "SDRAM" else "ROM")
    mem("NS_OFFSET", "0x10000000", "0x0")
    # Peripheral/security attribution is not ported by a memory-only resource.
    peripherals = zone.find("./resources/peripherals")
    peripherals.clear()
    files[".mcu/.devices/zone/" + PART + ".rzone"] = xml_bytes(zone)
    files["script/fsp.ld"] = linker_script(mcu["script/fsp.ld"], contract, "CM85")
    files["script/fsp_cpu1.ld"] = linker_script(mcu["script/fsp.ld"], contract, "CM33")
    # Use each core's stock toolchain script, retaining LLVM TLS/runtime support.
    for core, name, sibling in (("CM85", "fsp.lld", mcu),
                                ("CM33", "fsp_cpu1.lld", stock["mcu_ra6m5"])):
        llvm = sibling["script/fsp.lld"].decode().replace("\r\n", "\n")
        if core == "CM33":
            # Carry the RA8P1 GCC section/symbol contract into the CM33 template.
            primary = mcu["script/fsp.lld"].decode().replace("\r\n", "\n")
            for section, following in (("nocache", "    .bss :"),
                                        ("nocache_sdram", "    /* Symbol required for RA Configuration tool. */")):
                start = primary.index("    . = .;\n    __" + section + "_pre_location")
                end = primary.index("    . = (SIZEOF(." + section + ")", start)
                end = primary.index("\n", end) + 1
                block = primary[start:end]
                anchor = llvm.index(following, llvm.index("    .sdram") if section.endswith("sdram") else 0)
                llvm = llvm[:anchor] + block + "\n" + llvm[anchor:]
            llvm = llvm.replace("__tz_FLASH_C", "__FLASH_NSC_START").replace("__tz_RAM_C", "__RAM_NSC_START")
        llvm = llvm.replace("INCLUDE memory_regions.lld", "INCLUDE memory_regions.ld")
        files["script/" + name] = linker_script(llvm.encode(), contract, core).replace(
            b"INCLUDE memory_regions.ld", b"INCLUDE memory_regions.lld")
    files.update(commercial_files(mcu, stock["mcu_ra6m5"], contract))
    return files


def driver_overlay(root, stock):
    """Extend the original HAL owner; leave every pre-existing entry unchanged."""
    pdsc = ET.fromstring(stock["Renesas.RA.pdsc"])
    components = pdsc.find("components")
    additions, registrations, files, missing = [], [], {}, []
    for driver, (sibling, description, apis) in DRIVER_COMPONENTS.items():
        mdf = ".module_descriptions/Renesas##HAL Drivers##all##" + driver + "####5.9.0.xml"
        source = root / "baseline/ra/fsp/src" / driver
        instance = "ra/fsp/inc/instances/" + driver + ".h"
        api = "ra/fsp/inc/api/" + driver + "_api.h"
        if not (source.exists() or (root / "baseline" / instance).exists()
                or (root / "baseline" / mdf[1:]).exists()
                or (root / "baseline" / api).exists()):
            continue
        if components.find("component[@Csub='" + driver + "']") is not None:
            raise ValueError("Expected a new 5.9 HAL component: " + driver)
        template = components.find("component[@Csub='" + sibling + "']")
        if template is None:
            raise ValueError("Missing original HAL structural template: " + sibling)
        component = deepcopy(template)
        component.set("Csub", driver)
        component.find("description").text = description
        entries = {instance, "ra/fsp/src/" + driver + "/" + driver + ".c"}
        entries.update("ra/fsp/inc/api/" + name for name in apis)
        if source.is_dir():
            entries.update(p.relative_to(root / "baseline").as_posix()
                           for p in source.rglob("*") if p.is_file() and p.suffix in (".c", ".h"))
        if (root / "baseline" / api).is_file():
            entries.add(api)
        owned = component.find("files")
        template_file = deepcopy(owned.find("file"))
        owned.clear()
        for entry in sorted(entries):
            item = deepcopy(template_file)
            item.set("name", entry)
            item.set("category", "source" if entry.endswith(".c") else "header")
            owned.append(item)
        additions.append(xml_bytes(component).decode().split("\n", 1)[1])
        registrations.append('  <file supportType="Modules" version="5.9.0">' + mdf + '</file>\n')
        for entry in sorted(entries | {mdf}):
            src = root / "baseline" / (entry[1:] if entry.startswith(".module_descriptions/") else entry)
            if src.is_file():
                files[entry] = src.read_bytes()
            else:
                missing.append(str(src.relative_to(root)))
    if additions:
        # Text insertion preserves all original component/support bytes, including
        # platformCompanions and restrictions unrelated to this candidate.
        files["Renesas.RA.pdsc"] = stock["Renesas.RA.pdsc"].replace(
            b"</components>", "".join(additions).encode() + b"</components>")
        files["toolingSupport.xml"] = stock["toolingSupport.xml"].replace(
            b"</toolingSupport>", "".join(registrations).encode() + b"</toolingSupport>")
    return files, missing


def prepare(root=ROOT, output=None):
    root = Path(root)
    output = Path(output) if output else root / "pack_sources/ra8p1"
    contract = json.loads((root / "validation/ra8p1/memory-contract.json").read_text())
    stock = original_packs(root)
    mcu = resource_files(stock, contract)
    board_pdsc = descriptor(stock["board_ra8m1_ek"]["Renesas.RA_board_ra8m1_ek.pdsc"], board=True)
    board = {"Renesas.RA_board_ra8p1_ek.pdsc": xml_bytes(board_pdsc)}
    missing = []
    for label, files in ((MCU, mcu), (BOARD, board)):
        pdsc = ET.fromstring(next(data for name, data in files.items() if name.endswith(".pdsc")))
        support = ET.Element("toolingSupport", family="ra", platform="platform.rafsp")
        for component in pdsc.findall("./components/component"):
            key = "##".join(component.get(k, "") for k in ("Cvendor", "Cclass", "Cgroup", "Csub", "Cvariant", "Cversion"))
            name = ".module_descriptions/" + key + ".xml"
            ET.SubElement(support, "file", supportType="Modules", version=VERSION).text = name
            src = root / "baseline" / name[1:]
            if src.is_file():
                files[name] = src.read_bytes()
            else:
                missing.append(str(src.relative_to(root)))
            for item in component.findall("./files/file"):
                entry = item.get("name", "")
                if entry.endswith("/") or entry in files:
                    continue
                src = root / "baseline" / entry
                if src.is_file():
                    files[entry] = src.read_bytes()
                else:
                    missing.append(str(src.relative_to(root)))
        if label == BOARD:
            name = ".module_descriptions/Renesas##BSP##Board##ra8p1_ek####5.9.0##configuration.xml"
            ET.SubElement(support, "file", supportType="Modules", version=VERSION).text = name
            src = root / "baseline" / name[1:]
            if src.is_file():
                files[name] = src.read_bytes()
            else:
                missing.append(str(src.relative_to(root)))
        else:
            for folder, kind in (("pinmapping", "PinMapping"), ("pinconfig", "PinConfig")):
                for src in sorted((root / ".embedder/pin-model" / folder).glob("*")):
                    if src.is_file():
                        files[".mcu/." + folder + "/" + src.name] = src.read_bytes()
            for name in sorted(files):
                kind = None
                if name.startswith(".mcu/.devices/pg/"): kind = "PGDevice"
                elif name.startswith(".mcu/.devices/dbg/"): kind = "DBGDeviceJLink"
                elif name.startswith(".mcu/.devices/gdb/"): kind = "GDBDevice"
                elif name.startswith(".mcu/.devices/zone/"): kind = "CMSISZoneResource"
                elif name.startswith(".mcu/.pinmapping/"): kind = "PinMapping"
                elif name.startswith(".mcu/.pinconfig/"): kind = "PinConfig"
                if kind:
                    ET.SubElement(support, "file", supportType=kind, version=VERSION).text = name
        files["toolingSupport.xml"] = xml_bytes(support)
        for name, data in sorted(files.items()):
            path = output / label / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    drivers, absent = driver_overlay(root, stock["main"])
    missing.extend(absent)
    for name, data in sorted(drivers.items()):
        path = output / MAIN / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return sorted(set(missing))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    missing = prepare(args.root, args.output)
    print(json.dumps({"output": str(args.output or args.root / "pack_sources/ra8p1"), "missing_owned_inputs": missing}, indent=2))
    return 2 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
