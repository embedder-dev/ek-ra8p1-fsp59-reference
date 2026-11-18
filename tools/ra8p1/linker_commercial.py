"""Derive RA8P1 commercial linker resources from original FSP 5.9 siblings.

No filesystem or IDE side effects. The caller owns pack publication. Compiler
startup conventions stay native: IAR manual initialization blocks and Arm
Image$$/Load$$ execution regions are not replaced with GNU runtime symbols.
"""
import hashlib
import re


_SOURCE_HASHES = {
    "CM85": (
        "e3e7df0fa129e26307641258e160a187f474587ee032555f5f5dd6485068f112",
        "71c574a4c5f5da3eb6587e8bbfec421bb6d950421ee645a4bd2cb8de94ac800d",
    ),
    "CM33": (
        "d39d63e93705a8ce5eb66c494d96996ae0e2f968de8d10a2ef1ce791e997b8fa",
        "c6849fde94fd98f869c76eb95432ee4298cc5800a4c11aef69519bf94ddc5700",
    ),
}
_VIA_HASH = "7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6"
_OPTION_SYMBOLS = {
    "__tz_OPTION_SETTING_S": "0x02c9f000",
    "__tz_OPTION_SETTING_N": "0x02c9f400",
    "__tz_OPTION_SETTING_S_S": "0x02c9f000",
    "__tz_OPTION_SETTING_S_N": "0x02c9f400",
    "__tz_OPTION_SETTING_DATA_FLASH_S_S": "0",
    "__tz_OPTION_SETTING_DATA_FLASH_S_N": "0",
}
_ALLOCATION = (("FLASH", "MRAM"), ("RAM", "SRAM"),
               ("ITCM", "ITCM"), ("DTCM", "DTCM"))


def _number(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def _replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Original commercial linker anchor changed: " + old)
    return text.replace(old, new)


def _source(stock, core, path):
    expected = (_VIA_HASH if path.endswith(".via") else
                _SOURCE_HASHES[core][path.endswith(".scat")])
    data = stock[path]
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("Not the original FSP 5.9 " + core + " " + path)
    return data.decode("utf-8").replace("\r\n", "\n")


def _allocations(cfg):
    for name, key in _ALLOCATION:
        for suffix, field in (("START", "start"), ("LENGTH", "size")):
            yield name + "_" + suffix, hex(_number(cfg[key][field]))
    for key in ("ITCM", "DTCM"):
        yield key + "_BUS_ALIAS", hex(_number(cfg[key]["bus_alias"]))


def _validate_contract(contract):
    for region in ("MRAM", "SRAM"):
        physical = contract["physical"][region]
        low = _number(physical["start"])
        high = low + _number(physical["size"])
        previous = low
        for core in ("CM85", "CM33"):
            item = contract["cores"][core][region]
            start, size = _number(item["start"]), _number(item["size"])
            if size <= 0 or not previous <= start < start + size <= high:
                raise ValueError("Invalid or overlapping " + region + " allocation")
            previous = start + size
    for core in ("CM85", "CM33"):
        for region in ("ITCM", "DTCM"):
            item = contract["cores"][core][region]
            if _number(item["size"]) <= 0 or any(
                    _number(item[key]) % 16 for key in ("start", "size", "bus_alias")):
                raise ValueError("Invalid TCM allocation")
    addresses = set()
    for section, item in contract["options"].items():
        address = _number(item["address"])
        if (not re.fullmatch(r"\.option_setting_[a-z0-9_]+", section)
                or item["owner"] != "CM85" or item["size"] != 4
                or address % 4 or address in addresses
                or not (0x02c9f000 <= address <= 0x02c9f3fc
                        or 0x12c9f400 <= address <= 0x12c9f7fc)):
            raise ValueError("Invalid sparse option word: " + section)
        addresses.add(address)


def _iar(text, cm85, cfg, options, core):
    # ICF symbols cannot be redefined. Keep the generated include intact but
    # use pack-owned names, even when a preceding bundle exports CPU0 ranges.
    names = {name: "RA8P1_" + name for name, _ in _allocations(cfg)}
    text = re.sub(r"\b(?:" + "|".join(names) + r")\b",
                  lambda m: names[m.group()], text)
    for name, value in (("FLASH_ORIGIN", "RA8P1_FLASH_START"),
                        ("LIMITED_FLASH_LENGTH", "RA8P1_FLASH_LENGTH")):
        text = re.sub(r"define symbol " + name + r"\s*=\s*[^;]+;",
                      "define symbol " + name + " = " + value + ";", text)
    prefix = '\n/* RA8P1 HM 5.1: pack-owned, disjoint flat allocations. */\n'
    prefix += ''.join("define exported symbol RA8P1_" + name + " = " + value + ";\n"
                      for name, value in _allocations(cfg))
    prefix += ('check that !isdefinedsymbol(PROJECT_NONSECURE) && '
               '!isdefinedsymbol(PROJECT_SECURE), "RA8P1 flat CPU0/CPU1 allocation only";\n')
    text = _replace(text, 'include "memory_regions.icf";',
                    'include "memory_regions.icf";\n' + prefix)
    text = text.replace("Image$$__tz_FLASH_C", "Image$$__FLASH_NSC_START")
    text = text.replace("Image$$__tz_RAM_C", "Image$$__RAM_NSC_START")
    text = _replace(text,
        "  place at start of FLASH_region  { ro section .fixed_vectors* };\n"
        "  place in FLASH_region           { ro section .application_vectors* };",
        "  define block RA8P1_VECTORS with alignment = 128, fixed order {\n"
        "    ro section .fixed_vectors*, ro section .application_vectors*\n  };\n"
        "  place at start of FLASH_region { block RA8P1_VECTORS };")
    if core == "CM33":
        # RA6M5 has the same native TCM blocks but no cache. Shared RA8P1
        # sections still require the same placement/alignment on both cores.
        for block, anchor in (("NOCACHE", "place in RAM_region     { last section FREE_MEM };"),
                              ("NOCACHE_SDRAM", "/************************ QSPI Memory")):
            snippet = re.search(r"define block " + block + r" .*?\nplace in [^;]+;",
                                cm85, re.S).group()
            text = _replace(text, anchor, snippet + "\n" + anchor)
    # Size-based regions cannot wrap from zero to 0xffffffff when unavailable.
    for region, start, size in (("DF_region", "DATA_FLASH_START", "DATA_FLASH_LENGTH"),
                                ("SDRAM_region", "SDRAM_START", "SDRAM_LENGTH"),
                                ("QSPI_region", "QSPI_FLASH_START", "QSPI_FLASH_PRV_LENGTH"),
                                ("OSPI_DEVICE_0_region", "OSPI_DEVICE_0_START", "OSPI_DEVICE_0_PRV_LENGTH"),
                                ("OSPI_DEVICE_1_region", "OSPI_DEVICE_1_START", "OSPI_DEVICE_1_PRV_LENGTH")):
        text, count = re.subn(r"define region " + region + r"\s*= mem:\[[^\]]+\];",
                             "define region " + region + " = mem:[from " + start + " size " + size + "];", text)
        if count != 1:
            raise ValueError("Missing original ICF region " + region)
    a = text.index("/************************ ID CODE Memory")
    b = text.index("/************************ ITCM Memory", a)
    replacement = ("define region ID_CODE_region = mem:[from ID_CODE_START size ID_CODE_LENGTH];\n"
                   "place in ID_CODE_region { ro section .id_code };\n"
                   "define exported symbol __tz_ID_CODE_S = ID_CODE_START;\n"
                   "define exported symbol __tz_ID_CODE_N = ID_CODE_START;\n"
                   "define region OPTION_SETTING_region = mem:[from 0x02c9f000 size 0x400];\n"
                   "define region OPTION_SETTING_NS_region = mem:[from 0x12c9f400 size 0x400];\n")
    for symbol, value in _OPTION_SYMBOLS.items():
        replacement += "define exported symbol " + symbol + " = " + value + ";\n"
    owned = [s for s, info in options.items() if info["owner"] == core]
    for section in owned:
        name = section[1:].upper()
        replacement += ("define block " + name + " with maximum size = 4 { ro section " + section + " };\n"
                        "place at address mem:" + options[section]["address"] + " { block " + name + " };\n")
    replacement += "keep { section .option_setting* };\n"
    replacement += "define block UNSUPPORTED_OPTION_SETTINGS { section .option_setting* }"
    if owned:
        replacement += " except { " + ", ".join("section " + s for s in owned) + " }"
    replacement += (";\nplace in FLASH_region { block UNSUPPORTED_OPTION_SETTINGS };\n"
                    'check that size(block UNSUPPORTED_OPTION_SETTINGS) == 0, "Unported or secondary-core option settings";\n\n')
    text = text[:a] + replacement + text[b:]
    text = _replace(text, "  place in ITCM_region {", "  place at start of ITCM_region {")
    text = _replace(text, "  place in DTCM_region {\n    block DTCM_DATA,\n    block DTCM_BSS\n  };",
                    "  define block DTCM_CONTENT with fixed order { block DTCM_DATA, block DTCM_BSS };\n"
                    "  place at start of DTCM_region { block DTCM_CONTENT };")
    # Preserve the compiler's init-image names and zero-fill rules. These
    # sections must never acquire a startup copy merely by being retained.
    text += ("\ndo not initialize { section .noinit*, section .nocache*, section .ns_buffer*, "
             "section .ospi_device_0_no_load*, section .ospi_device_1_no_load*, "
             "section .sdram*, section .frame* };\n")
    return text.encode()


def _scatter(text, cm85, cfg, options, core):
    text = _replace(text, "-mcpu=cortex-m4", "-mcpu=" + cfg["compiler"])
    overrides = "\n; RA8P1 HM 5.1: pack-owned, disjoint flat allocations.\n"
    for name, value in _allocations(cfg):
        overrides += "#undef " + name + "\n#define " + name + " " + value + "\n"
    for name, value in (("FLASH_S_START", "FLASH_START"), ("RAM_S_START", "RAM_START")):
        overrides += "#undef " + name + "\n#define " + name + " " + value + "\n"
    overrides += ('#if defined(PROJECT_NONSECURE) || defined(PROJECT_SECURE)\n'
                  '#error RA8P1 flat CPU0/CPU1 allocation only\n#endif\n')
    text = _replace(text, '#include "memory_regions.scat"',
                    '#include "memory_regions.scat"\n' + overrides)
    for name, value in (("FLASH_ORIGIN", "FLASH_START"), ("LIMITED_FLASH_LENGTH", "FLASH_LENGTH")):
        text = re.sub(r"(?m)^#define " + name + r"[^\n]+", "#define " + name + " " + value, text)
    text = _replace(text, "(OPTION_SETTING_S_LENGTH != 0)", "(OPTION_SETTING_LENGTH != 0)")
    text = text.replace("__tz_FLASH_C ", "__FLASH_NSC_START ").replace("__tz_RAM_C ", "__RAM_NSC_START ")
    if core == "CM33":
        for block, next_block in (("NOCACHE", "ARM_LIB_HEAP"), ("NOCACHE_SDRAM", "__tz_SDRAM_N")):
            a = cm85.index("  " + block + " +0 ")
            b = cm85.index("  " + next_block + " ", a)
            text = _replace(text, "  " + next_block + " ", cm85[a:b] + "  " + next_block + " ")
    a = text.index("#if OPTION_SETTING_LENGTH != 0\nLOAD_REGION_OPTION_SETTING")
    b = text.index("LOAD_REGION_DATA_FLASH", a)
    replacement = "LOAD_REGION_OPTION_BOUNDARIES 0x02c9f000\n{\n"
    for symbol, value in _OPTION_SYMBOLS.items():
        replacement += "  " + symbol + " " + value + " EMPTY 0\n  {\n  }\n"
    replacement += "}\n\n"
    for section, info in options.items():
        if info["owner"] != core:
            continue
        name = section[1:].upper()
        address = info["address"]
        replacement += ("LOAD_REGION_" + name + " " + address + " 4\n{\n  " + name + " " + address
                        + " FIXED 4\n  {\n    *(" + section + ")\n  }\n}\n\n")
    text = text[:a] + replacement + text[b:]
    a = text.index("#if ID_CODE_OVERLAP == 0")
    b = text.index("LOAD_REGION_OPTION_BOUNDARIES", a)
    text = text[:a] + ("LOAD_REGION_ID_CODE ID_CODE_START ID_CODE_LENGTH\n{\n"
        "  __tz_ID_CODE_S ID_CODE_START EMPTY 0\n  {\n  }\n"
        "  __tz_ID_CODE_N ID_CODE_START EMPTY 0\n  {\n  }\n"
        "  ID_CODE ID_CODE_START FIXED ID_CODE_LENGTH\n  {\n    *(.id_code*)\n  }\n}\n\n") + text[b:]
    text = _replace(text, "RAM_LIMIT RAM_START + RAM_LENGTH EMPTY 4",
                    "RAM_LIMIT RAM_START + RAM_LENGTH EMPTY 0")
    text = _replace(text, "  SDRAM +0 FIXED", "  SDRAM +0 UNINIT NOCOMPRESS SDRAM_LENGTH")
    # Exact option selectors above win over this catch-all, which in turn
    # wins over .ANY(+RO). --keep prevents dead stripping the rejected input.
    text = _replace(text, "  RO_CODE_DATA +0 FIXED", "  UNSUPPORTED_OPTION_SETTINGS +0\n  {\n"
                    "    *(.option_setting*)\n  }\n"
                    "  ScatterAssert(ImageLength(UNSUPPORTED_OPTION_SETTINGS) == 0)\n\n  RO_CODE_DATA +0 FIXED")
    for index in (0, 1):
        text = _replace(text, f"OSPI_DEVICE_{index}_NO_LOAD OSPI_DEVICE_{index}_START UNINIT NOCOMPRESS",
                        f"OSPI_DEVICE_{index}_NO_LOAD OSPI_DEVICE_{index}_START UNINIT NOCOMPRESS OSPI_DEVICE_{index}_PRV_LENGTH")
    # Stock AC6 lacks explicit non-retentive external sections; give them an
    # internal MRAM load image instead of allowing .ANY to orphan them there.
    extra = ""
    for region, prefix, length in (("QSPI_FLASH", "qspi", "QSPI_FLASH_PRV_LENGTH"),
                                    ("OSPI_DEVICE_0", "ospi_device_0", "OSPI_DEVICE_0_PRV_LENGTH"),
                                    ("OSPI_DEVICE_1", "ospi_device_1", "OSPI_DEVICE_1_PRV_LENGTH")):
        name = prefix.upper() + "_NON_RETENTIVE"
        extra += ("  " + name + " ImageLimit(" + region + ") NOCOMPRESS (" + length
                  + " - ImageLength(" + region + "))\n  {\n    *(" + "." + prefix + "_non_retentive*)\n  }\n")
    # Insert before the closing brace of the first load region, retaining
    # the original TCM regions and native load-limit padding symbols.
    marker = "\n}\n\nLOAD_REGION_NSC_FLASH"
    text = _replace(text, marker, "\n" + extra + "}\n\nLOAD_REGION_NSC_FLASH")
    text += ("\nScatterAssert(ImageLimit(RAM_END) <= RAM_START + RAM_LENGTH)\n"
             "ScatterAssert(ImageLimit(ITCM_PAD) <= ITCM_START + ITCM_LENGTH)\n"
             "ScatterAssert(ImageLimit(DTCM_BSS_PAD) <= DTCM_START + DTCM_LENGTH)\n"
             "ScatterAssert(ImageLimit(NOCACHE_SDRAM_PAD) <= SDRAM_START + SDRAM_LENGTH)\n")
    return text.encode()


def commercial_files(stock_cm85: dict, stock_cm33: dict, contract: dict) -> dict:
    """Return ICF/scatter scripts and one shared AC6 retention response file.

    Inputs are archive-entry dictionaries, not paths: CM85 must be the original
    RA8M1 5.9.0 MCU pack and CM33 the original RA6M5 5.9.0 MCU pack. No compiler,
    project generation, installation, or firmware qualification is implied.
    """
    _validate_contract(contract)
    sources = {core: {path: _source(stock, core, path) for path in
                     ("script/fsp.icf", "script/fsp.scat", "script/ac6/fsp_keep.via")}
               for core, stock in (("CM85", stock_cm85), ("CM33", stock_cm33))}
    files = {}
    for core, suffix in (("CM85", ""), ("CM33", "_cpu1")):
        cfg = contract["cores"][core]
        for extension, adapt in (("icf", _iar), ("scat", _scatter)):
            path = "script/fsp." + extension
            files["script/fsp" + suffix + "." + extension] = adapt(
                sources[core][path], sources["CM85"][path], cfg, contract["options"], core)
    retained = (".fixed_vectors*", ".application_vectors*", ".option_setting*", ".version",
                ".init", ".fini", ".usb_*", ".itcm_data*", ".dtcm_data*", ".bss.dtcm_bss*",
                ".code_in_*", ".qspi_*", ".ospi_device_*", ".bss.noinit*", ".bss.nocache*",
                ".ns_buffer*", ".bss.heap*", ".bss.stack*", ".data_flash*", ".sdram*",
                ".bss.sdram*", ".frame*", ".id_code*")
    files["script/ac6/fsp_keep.via"] = (sources["CM85"]["script/ac6/fsp_keep.via"]
        + ''.join("--keep=*(" + section + ")\n" for section in retained)).encode()
    return files
