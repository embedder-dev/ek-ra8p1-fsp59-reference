"""Resource-contract checks; GNU linker probes are not FSP/runtime validation."""
from io import BytesIO
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

from ra8p1 import prepare_pack_resources as resources

ROOT = Path(__file__).resolve().parents[1]

# Captured from CPU0 r004 Debug/memory_regions.ld. e2 omits physical aliases:
# OPTION_SETTING_S and the FLASH_NS/RAM_NS/ITCM_NS/DTCM_NS entries are not emitted.
GENERATED_MEMORY_REGIONS = """
OPTION_SETTING_START = 0x02C9F000;
OPTION_SETTING_LENGTH = 0x400;
FLASH_START = 0x02000000;
FLASH_LENGTH = 0x80000;
RAM_START = 0x22000000;
RAM_LENGTH = 0xD0000;
ITCM_START = 0x00000000;
ITCM_LENGTH = 0x20000;
DTCM_START = 0x20000000;
DTCM_LENGTH = 0x20000;
FLASH_CPU1_START = 0x02080000;
FLASH_CPU1_LENGTH = 0x80000;
RAM_CPU1_START = 0x220D0000;
RAM_CPU1_LENGTH = 0xD0000;
CTCM_CPU1_START = 0x2A000000;
CTCM_CPU1_LENGTH = 0x10000;
STCM_CPU1_START = 0x2A010000;
STCM_CPU1_LENGTH = 0x10000;
OPTION_SETTING_NS_START = 0x12C9F400;
OPTION_SETTING_NS_LENGTH = 0x400;
DATA_FLASH_START = 0x00000000;
DATA_FLASH_LENGTH = 0x0;
OPTION_SETTING_DATA_FLASH_S_START = 0x00000000;
OPTION_SETTING_DATA_FLASH_S_LENGTH = 0x0;
ID_CODE_START = 0x00000000;
ID_CODE_LENGTH = 0x0;
SDRAM_START = 0x00000000;
SDRAM_LENGTH = 0x0;
QSPI_FLASH_START = 0x00000000;
QSPI_FLASH_LENGTH = 0x0;
OSPI_DEVICE_0_START = 0x00000000;
OSPI_DEVICE_0_LENGTH = 0x0;
OSPI_DEVICE_1_START = 0x00000000;
OSPI_DEVICE_1_LENGTH = 0x0;
NS_OFFSET_START = 0x10000000;
NS_OFFSET_LENGTH = 0x0;
"""

# CPU1 r006 receives these generic ranges from its preceding Smart Bundle;
# the pack's CPU1 linker must still enforce the independent physical allocation.
GENERATED_CPU1_MEMORY_REGIONS = (GENERATED_MEMORY_REGIONS
    .replace("OPTION_SETTING_START = 0x02C9F000;", "OPTION_SETTING_START = 0x02C9F400;")
    .replace("OPTION_SETTING_LENGTH = 0x400;", "OPTION_SETTING_LENGTH = 0x0;")
    .replace("FLASH_START = 0x02000000;", "FLASH_START = 0x02008000;")
    .replace("FLASH_LENGTH = 0x80000;", "FLASH_LENGTH = 0x78000;")
    .replace("RAM_START = 0x22000000;", "RAM_START = 0x22002000;")
    .replace("RAM_LENGTH = 0xD0000;", "RAM_LENGTH = 0xCE000;"))


class PackResourcesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((ROOT / "validation/ra8p1/memory-contract.json").read_text())
        cls.stock = resources.original_packs(ROOT)
        cls.files = resources.resource_files(cls.stock, cls.contract)
        cls.temporary = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temporary.name)
        cls.missing = resources.prepare(ROOT, cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_part_header_and_single_part_component(self):
        pdsc = ET.fromstring(self.files["Renesas.RA_mcu_ra8p1.pdsc"])
        self.assertEqual([resources.PART], [n.get("Cvariant") for n in pdsc.findall("./components/component") if n.get("Cvariant")])
        self.assertIn(b"R7KA8P1KF.h", self.files["Renesas.RA_mcu_ra8p1.pdsc"])
        self.assertEqual({"device", "fsp", "events"}, {n.get("Csub") for n in pdsc.findall("./components/component")})

    def test_pg_xmi_preserves_host_required_namespace_prefixes(self):
        original = self.stock["mcu_ra8m1"][".mcu/.devices/pg/pgra8m1.xmi"]
        candidate = self.files[".mcu/.devices/pg/pgra8p1.xmi"]
        for declaration in (b'xmlns:projgen="http:///projgen.ecore"',
                            b'xmlns:xmi="http://www.omg.org/XMI"',
                            b'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
                            b'xmi:version="2.0"'):
            self.assertIn(declaration, original)
            self.assertIn(declaration, candidate)
        self.assertIn(b"<projgen:Container", candidate)
        self.assertNotIn(b"ns0:", candidate)
        self.assertNotIn(b"ns1:", candidate)

    def test_toolchain_core_specific_linker_entries(self):
        pdsc = ET.fromstring(self.files["Renesas.RA_mcu_ra8p1.pdsc"])
        entries = {(n.get("name"), n.get("condition")) for n in pdsc.findall(".//file[@category='linkerScript']")}
        expected = set()
        for compiler, suffix in (("GCC", "ld"), ("CLANG", "lld"), ("IAR", "icf"), ("ARMCC", "scat")):
            for core, cpu in (("CM85", "Cortex-M85"), ("CM33", "Cortex-M33")):
                condition = "Only_" + core + "_and_" + compiler
                expected.add(("script/fsp" + ("_cpu1" if core == "CM33" else "") + "." + suffix, condition))
                if compiler == "ARMCC":
                    expected.add(("script/ac6/fsp_keep.via", condition))
                node = pdsc.find("./conditions/condition[@id='" + condition + "']")
                self.assertEqual(cpu, node.find("require[@Dcore]").get("Dcore"))
                self.assertEqual(compiler, node.find("require[@Tcompiler]").get("Tcompiler"))
        self.assertEqual(expected, entries)

    def test_physical_memory_and_ns_aliases(self):
        for key, limit in (("MRAM", 0x100000), ("SRAM", 0x1a0000)):
            physical = self.contract["physical"][key]
            base = int(physical["start"], 0)
            self.assertEqual(limit, int(physical["size"], 0))
            self.assertEqual(0x10000000, int(physical["ns_start"], 0) - base)
            intervals = []
            for core in self.contract["cores"].values():
                region = core[key]
                start, size = int(region["start"], 0), int(region["size"], 0)
                self.assertGreater(size, 0)
                self.assertGreaterEqual(start, base)
                self.assertLessEqual(start + size, base + limit)
                intervals.append((start, start + size))
            intervals.sort()
            self.assertEqual(intervals[0][1], intervals[1][0])
            self.assertEqual((base, base + limit), (intervals[0][0], intervals[1][1]))

    def test_core_local_tcm_aliases_are_distinct_physical_banks(self):
        bus_ranges = []
        for core, size in (("CM85", 0x20000), ("CM33", 0x10000)):
            for name, local in (("ITCM", 0), ("DTCM", 0x20000000)):
                region = self.contract["cores"][core][name]
                self.assertEqual(local, int(region["start"], 0))
                self.assertEqual(size, int(region["size"], 0))
                address = int(region["bus_alias"], 0)
                bus_ranges.append((address, address + size))
        bus_ranges.sort()
        for left, right in zip(bus_ranges, bus_ranges[1:]):
            self.assertLessEqual(left[1], right[0])

    def test_zone_and_debug_core_identity_no_sibling_registers(self):
        zone = ET.fromstring(self.files[".mcu/.devices/zone/" + resources.PART + ".rzone"])
        self.assertEqual({"CM85": "Cortex-M85", "CM33": "Cortex-M33"}, {n.get("Pname"): n.get("Dcore") for n in zone.findall("./device/processor")})
        self.assertEqual({"CM85": "r1p1", "CM33": "r0p4"},
                         {n.get("Pname"): n.get("DcoreVersion") for n in zone.findall("./device/processor")})
        original_processor = ET.fromstring(self.stock["mcu_ra8m1"][".mcu/.devices/zone/R7FA8M1AHECBD.rzone"]).find("./device/processor")
        for processor in zone.findall("./device/processor"):
            self.assertTrue(original_processor.attrib.keys() <= processor.attrib.keys())
        self.assertEqual([], list(zone.find("./resources/peripherals")))
        debug = ET.fromstring(self.files[".mcu/.devices/dbg/dbgra8p1.xml"])
        self.assertEqual({"-t R7KA8P1KF_CPU0", "-t R7KA8P1KF_CPU1"}, {n.text for n in debug.findall("./device/server/params/param")})
        gdb = ET.fromstring(self.files[".mcu/.devices/gdb/ra8p1.5.9.0.xml"])
        self.assertEqual({"CM85", "CM33"}, {n.get("armFamily") for n in gdb.findall("./Devices/Device")})
        self.assertEqual([], gdb.findall(".//MonitorRegister"))
        self.assertEqual([], gdb.findall(".//PartNumber"))
        for monitor in gdb.findall(".//MemMonitor"):
            self.assertIn(monitor.get("address"), {x["address"] for x in self.contract["options"].values()})
            self.assertEqual("false", monitor.get("write"))

    def test_tooling_closure_and_no_svd_or_e2_claim(self):
        for pack in (resources.MCU, resources.BOARD):
            folder = self.output / pack
            support = ET.parse(folder / "toolingSupport.xml")
            for item in support.findall("file"):
                if item.get("supportType") == "Modules" and not (folder / item.text).is_file():
                    self.assertIn("baseline/" + item.text[1:], self.missing)
                else:
                    self.assertTrue((folder / item.text).is_file(), item.text)
                self.assertNotIn(item.get("supportType"), ("IoFiles", "DBGDeviceE2", "DBGDeviceE2Lite"))

    def test_full_pack_dependency_closure(self):
        if self.missing:
            self.skipTest("Other owners' pending inputs: " + ", ".join(self.missing))
        for folder in self.output.iterdir():
            names = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
            if folder.name == resources.MAIN:
                names.update(self.stock["main"])
            pdsc = ET.parse(next(folder.glob("*.pdsc")))
            for entry in pdsc.findall("./components/component/files/file"):
                if not entry.get("name").endswith("/"):
                    self.assertIn(entry.get("name"), names)
            for component in pdsc.findall("./components/component"):
                key = "##".join(component.get(k, "") for k in ("Cvendor", "Cclass", "Cgroup", "Csub", "Cvariant", "Cversion"))
                self.assertIn(".module_descriptions/" + key + ".xml", names)

    def test_new_driver_components_own_all_current_driver_inputs(self):
        folder = self.output / resources.MAIN
        pdsc = ET.parse(folder / "Renesas.RA.pdsc")
        support = ET.parse(folder / "toolingSupport.xml")
        registered = {n.text for n in support.findall("file[@supportType='Modules']")}
        for driver in resources.DRIVER_COMPONENTS:
            component = pdsc.find("./components/component[@Csub='" + driver + "']")
            self.assertIsNotNone(component, driver)
            self.assertEqual("HAL Drivers", component.get("Cclass"))
            self.assertEqual("all", component.get("Cgroup"))
            mdf = ".module_descriptions/Renesas##HAL Drivers##all##" + driver + "####5.9.0.xml"
            self.assertIn(mdf, registered)
            self.assertEqual((ROOT / "baseline" / mdf[1:]).read_bytes(), (folder / mdf).read_bytes())
            owned = {n.get("name") for n in component.findall("./files/file")}
            for path in (ROOT / "baseline/ra/fsp/src" / driver).rglob("*"):
                if path.is_file() and path.suffix in (".c", ".h"):
                    name = path.relative_to(ROOT / "baseline").as_posix()
                    self.assertIn(name, owned)
                    self.assertEqual(path.read_bytes(), (folder / name).read_bytes())
            self.assertIn("ra/fsp/inc/instances/" + driver + ".h", owned)
            api = "ra/fsp/inc/api/" + driver + "_api.h"
            if (ROOT / "baseline" / api).is_file():
                self.assertIn(api, owned)

    def test_driver_overlay_preserves_every_original_component_and_support_entry(self):
        folder = self.output / resources.MAIN
        for name, path in (("Renesas.RA.pdsc", "./components/component"), ("toolingSupport.xml", "./*")):
            old = ET.fromstring(self.stock["main"][name]).findall(path)
            new = ET.parse(folder / name).findall(path)
            self.assertEqual(len(old) + len(resources.DRIVER_COMPONENTS), len(new))
            for before, after in zip(old, new):
                self.assertEqual(ET.tostring(before).rstrip(), ET.tostring(after).rstrip())

    def test_option_length_references_close_with_actual_generated_symbols(self):
        generated = set(re.findall(r"^\s*([A-Z][A-Z0-9_]*)\s*=", GENERATED_MEMORY_REGIONS, re.M))
        self.assertNotIn("OPTION_SETTING_S_LENGTH", generated)
        self.assertNotIn("ITCM_NS_START", generated)
        for name in ("script/fsp.ld", "script/fsp_cpu1.ld"):
            text = self.files[name].decode()
            defined = generated | set(re.findall(r"^\s*([A-Z_][A-Z0-9_]*)\s*=", text, re.M))
            referenced = set(re.findall(r"\bOPTION_SETTING[A-Z_]*_LENGTH\b", text))
            self.assertEqual(set(), referenced - defined, name)
            self.assertNotIn("OPTION_SETTING_S_LENGTH", text)
            self.assertIn("&& (OPTION_SETTING_LENGTH != 0)", text)

    def test_supplied_pin_model_is_byte_identical(self):
        for kind in ("pinmapping", "pinconfig"):
            source = ROOT / ".embedder/pin-model" / kind
            for path in source.iterdir():
                if path.is_file():
                    self.assertEqual(path.read_bytes(), (self.output / resources.MCU / ".mcu" / ("." + kind) / path.name).read_bytes())

    def test_linker_preserves_original_sections_not_original_options(self):
        stock = self.stock["mcu_ra8m1"]["script/fsp.ld"].decode().replace("\r\n", "\n")
        for name in ("script/fsp.ld", "script/fsp_cpu1.ld"):
            text = self.files[name].decode()
            first, last = stock.index("/* Library configurations */"), stock.index("    /* Symbol required for RA Configuration tool. */\n    __tz_OPTION_SETTING_S =")
            normalized = re.sub(r" :ra8p1_load_[0-9]+", "", text)
            normalized = re.sub(r"\nPHDRS\n\{\n(?:  ra8p1_load_[0-9]+ PT_LOAD;\n)+}\n", "", normalized)
            self.assertIn(stock[first:last], normalized)
            self.assertIn("Unported or secondary-core option settings", text)
            self.assertNotIn("0x0300", text)


@unittest.skipUnless(shutil.which("arm-none-eabi-as") and shutil.which("arm-none-eabi-ld"), "ARM GNU binutils not installed")
class GnuLinkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((ROOT / "validation/ra8p1/memory-contract.json").read_text())
        cls.files = resources.resource_files(resources.original_packs(ROOT), cls.contract)

    def link(self, core="CM85", option=None, bss=16, extra="", memory_extra="",
             memory_regions=GENERATED_MEMORY_REGIONS):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        directory = Path(temp.name)
        script = "script/fsp.ld" if core == "CM85" else "script/fsp_cpu1.ld"
        (directory / "fsp.ld").write_bytes(self.files[script])
        (directory / "memory_regions.ld").write_text(memory_regions + memory_extra)
        # Empty archive fixtures isolate linker semantics from libc availability.
        for name in ("libgcc.a", "libc.a", "libm.a"):
            (directory / name).write_bytes(b"!<arch>\n")
        asm = '.syntax unified\n.thumb\n.global Reset_Handler\n.section .text.Reset_Handler,"ax"\n.thumb_func\nReset_Handler: b .\n.section .fixed_vectors,"a"\n.global __Vectors\n__Vectors:\n.word 0x22000100\n.word Reset_Handler\n.section .stack,"aw",%nobits\n.space 512\n.section .bss,"aw",%nobits\n.space ' + str(bss) + '\n'
        if option:
            asm += '.section ' + option + ',"a"\n.word 0xffffffff\n'
        (directory / "probe.s").write_text(asm + extra)
        # This common Thumb fixture checks allocation, not CPU instruction support.
        result = subprocess.run([shutil.which("arm-none-eabi-as"), "-mthumb", "probe.s", "-o", "probe.o"], cwd=directory, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        result = subprocess.run([shutil.which("arm-none-eabi-ld"), "-L.", "-T", "fsp.ld", "probe.o", "-Map=probe.map", "-o", "probe.elf"], cwd=directory, capture_output=True, text=True)
        return result, directory

    def test_generated_memory_fixture_preserves_ns_ram_reservation_semantics(self):
        for core in ("CM85", "CM33"):
            for settings, expected in (("", 0), ("RAM_NS_BUFFER_LENGTH = 0x100;\n", 1),
                                       ("PROJECT_NONSECURE = 1;\nRAM_NS_BUFFER_LENGTH = 0x100;\n", 0)):
                with self.subTest(core=core, settings=settings):
                    result, directory = self.link(core, memory_extra=settings)
                    if "PROJECT_NONSECURE" in settings:
                        self.assertNotEqual(0, result.returncode)
                        self.assertIn("RA8P1 Non-secure partitions are not qualified", result.stderr)
                    else:
                        self.assertEqual(0, result.returncode, result.stderr)
                        self.assertEqual(expected, self.symbols(directory)["__RESERVE_NS_RAM"])

    def test_cpu1_actual_preceding_bundle_regions_do_not_override_physical_contract(self):
        result, directory = self.link("CM33", memory_regions=GENERATED_CPU1_MEMORY_REGIONS)
        self.assertEqual(0, result.returncode, result.stderr)
        symbols = self.symbols(directory)
        for name, value in (("FLASH_START", 0x02080000), ("FLASH_LENGTH", 0x80000),
                            ("RAM_START", 0x220d0000), ("RAM_LENGTH", 0xd0000),
                            ("ITCM_LENGTH", 0x10000), ("DTCM_LENGTH", 0x10000)):
            self.assertEqual(value, symbols[name])
        self.assertEqual(0x02080000, symbols["__Vectors"])
        self.assertEqual(0x220d0000, symbols["__bss_start__"])

    def test_nonsecure_images_fail_closed_without_qualified_partitions(self):
        for core in ("CM85", "CM33"):
            with self.subTest(core=core):
                result, _ = self.link(core, memory_extra="PROJECT_NONSECURE = 1;\n")
                self.assertNotEqual(0, result.returncode)
                self.assertIn("RA8P1 Non-secure partitions are not qualified", result.stderr)

    def test_cpu0_and_cpu1_link_disjoint(self):
        for core in ("CM85", "CM33"):
            result, directory = self.link(core)
            self.assertEqual(0, result.returncode, result.stderr)
            content = (directory / "probe.map").read_text()
            region = self.contract["cores"][core]
            self.assertIn(region["MRAM"]["start"].lower(), content.lower())
            self.assertIn(region["SRAM"]["start"].lower(), content.lower())

    def symbols(self, directory):
        if not shutil.which("arm-none-eabi-nm"):
            self.skipTest("ARM GNU nm not installed")
        result = subprocess.run([shutil.which("arm-none-eabi-nm"), "--defined-only", "probe.elf"],
                                cwd=directory, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        return {fields[2]: int(fields[0], 16) for line in result.stdout.splitlines()
                if len(fields := line.split()) == 3}

    def test_cpu1_actual_startup_tcm_symbols_bind_local_vmas_and_secondary_lmas(self):
        source = (ROOT / "baseline/ra/fsp/src/bsp/cmsis/Device/RENESAS/Source/system.c").read_text()
        function = re.search(r"static void bsp_init_ctcm \(void\)\s*\{(.*?)\n\}", source, re.S)
        self.assertIsNotNone(function, "CPU1 startup function missing")
        referenced = set(re.findall(r"__(?:itcm|dtcm|ctcm|stcm)_[a-z_]+", function.group(1)))
        expected = {"__itcm_data_init_start", "__itcm_data_init_end", "__itcm_data_start",
                    "__dtcm_data_init_start", "__dtcm_data_init_end", "__dtcm_data_start",
                    "__dtcm_bss_start", "__dtcm_bss_end"}
        self.assertEqual(expected, referenced, "Startup/linker contract changed")
        extra = '.section .rodata.startup_tcm_contract,"a"\n'
        extra += ''.join('.word ' + name + '\n' for name in sorted(referenced))
        extra += '.section .itcm_data,"ax"\n.space 16\n.section .dtcm_data,"aw"\n.space 16\n.section .dtcm_bss,"aw",%nobits\n.space 16\n'
        result, directory = self.link("CM33", extra=extra)
        self.assertEqual(0, result.returncode, result.stderr)
        symbols = self.symbols(directory)
        self.assertEqual(0, symbols["__itcm_data_start"])
        self.assertEqual(0x20000000, symbols["__dtcm_data_start"])
        self.assertEqual(0x20000010, symbols["__dtcm_bss_start"])
        self.assertEqual(0x20000020, symbols["__dtcm_bss_end"])
        for name in ("itcm", "dtcm"):
            self.assertEqual(16, symbols["__" + name + "_data_init_end"] - symbols["__" + name + "_data_init_start"])
            self.assertGreaterEqual(symbols["__" + name + "_data_init_start"], 0x02080000)
            self.assertLessEqual(symbols["__" + name + "_data_init_end"], 0x02100000)
        self.assertEqual(0x02080000, symbols["__Vectors"])
        self.assertEqual(0x220d0000, symbols["__bss_start__"])
        for region, start, size in (("FLASH", 0x02080000, 0x80000), ("RAM", 0x220d0000, 0xd0000),
                                    ("ITCM", 0, 0x10000), ("DTCM", 0x20000000, 0x10000)):
            self.assertEqual(start, symbols[region + "_START"])
            self.assertEqual(size, symbols[region + "_LENGTH"])

    def test_cpu0_actual_security_tcm_symbols_resolve(self):
        source = (ROOT / "baseline/ra/fsp/src/bsp/mcu/all/bsp_security.c").read_text()
        referenced = set(re.findall(r"__tz_(?:ITCM|DTCM|CTCM|STCM)_[SN]\b", source))
        self.assertEqual({"__tz_ITCM_S", "__tz_ITCM_N", "__tz_DTCM_S", "__tz_DTCM_N"}, referenced,
                         "Security/linker TCM contract changed")
        extra = '.section .rodata.security_tcm_contract,"a"\n'
        extra += ''.join('.word ' + name + '\n' for name in sorted(referenced))
        extra += '.section .itcm_data,"ax"\n.space 16\n.section .dtcm_data,"aw"\n.space 16\n'
        result, directory = self.link("CM85", extra=extra)
        self.assertEqual(0, result.returncode, result.stderr)
        symbols = self.symbols(directory)
        self.assertEqual(0, symbols["__tz_ITCM_S"])
        # e2 omits the physical NS aliases, so the stock alignment rule applies.
        self.assertEqual(0x2000, symbols["__tz_ITCM_N"])
        self.assertEqual(0x20000000, symbols["__tz_DTCM_S"])
        self.assertGreaterEqual(symbols["__tz_DTCM_N"], symbols["__dtcm_data_end"])
        self.assertLessEqual(symbols["__tz_DTCM_N"], 0x20020000)

    def test_cpu1_tcm_and_shared_partitions_enforce_boundaries(self):
        for section, region in ((".itcm_data", "ITCM"), (".dtcm_bss", "DTCM")):
            for size, valid in ((0x10000, True), (0x10001, False)):
                with self.subTest(section=section, size=size):
                    flags = '"ax"' if region == "ITCM" else '"aw",%nobits'
                    result, _ = self.link("CM33", extra='.section ' + section + ',' + flags + '\n.space ' + str(size) + '\n')
                    self.assertEqual(valid, result.returncode == 0, result.stderr)
                    if not valid:
                        self.assertIn(region, result.stderr)
        result, directory = self.link("CM33", bss=0xd0000 - 512)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(0x221a0000, self.symbols(directory)["__StackTop"])
        result, _ = self.link("CM33", bss=0xd0000 - 511)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("RAM", result.stderr)
        result, _ = self.link("CM33", extra='.section .rodata.secondary_overflow,"a"\n.space 0x80000\n')
        self.assertNotEqual(0, result.returncode)
        self.assertIn("FLASH", result.stderr)

    def load_segments(self, directory):
        elf = (directory / "probe.elf").read_bytes()
        self.assertEqual(b"\x7fELF\x01\x01", elf[:6])
        offset, = struct.unpack_from("<I", elf, 28)
        size, count = struct.unpack_from("<HH", elf, 42)
        segments = [struct.unpack_from("<IIIIIIII", elf, offset + n * size) for n in range(count)]
        return [dict(zip(("type", "offset", "vaddr", "paddr", "filesz", "memsz", "flags", "align"), p))
                for p in segments if p[0] == 1 and p[5]]

    def test_sparse_option_words_have_independent_exact_load_segments(self):
        extra = ''.join('.section ' + section + ',"a"\n.word 0xffffffff\n'
                        for section in self.contract["options"])
        result, directory = self.link(extra=extra)
        self.assertEqual(0, result.returncode, result.stderr)
        words = {int(info["address"], 0) for info in self.contract["options"].values()}
        seen = set()
        for segment in self.load_segments(directory):
            if not (0x02c9f000 <= segment["paddr"] < 0x02c9f800
                    or 0x12c9f000 <= segment["paddr"] < 0x12c9f800):
                continue
            self.assertIn(segment["paddr"], words)
            self.assertEqual(4, segment["filesz"])
            self.assertEqual(4, segment["memsz"])
            self.assertEqual(segment["paddr"], segment["vaddr"])
            self.assertEqual(4, segment["flags"])
            seen.add(segment["paddr"])
        self.assertEqual(words, seen)

    def test_ram_code_keeps_stock_copy_range_and_truthful_segment_flags(self):
        extra = '.section .code_in_ram,"ax"\n.space 16\n.section .data,"aw"\n.word 0x12345678\n'
        for core in ("CM85", "CM33"):
            result, directory = self.link(core, extra=extra)
            self.assertEqual(0, result.returncode, result.stderr)
            symbols = self.symbols(directory)
            data_start = symbols["__data_start__"]
            self.assertEqual(data_start, symbols["__Code_In_RAM_Start"])
            self.assertEqual(data_start + 16, symbols["__Code_In_RAM_End"])
            data_segments = [p for p in self.load_segments(directory) if p["vaddr"] == data_start and p["filesz"]]
            self.assertEqual(1, len(data_segments))
            segment = data_segments[0]
            self.assertEqual(symbols["__etext"], segment["paddr"])
            self.assertEqual(symbols["__data_end__"] - data_start, segment["filesz"])
            self.assertEqual(7, segment["flags"], "Do not conceal mixed code/data RWX permissions")

    def test_each_supported_option_word_has_manual_address(self):
        for option, info in self.contract["options"].items():
            result, directory = self.link(option=option)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn(info["address"][2:], (directory / "probe.map").read_text().lower())

    def test_unported_option_and_secondary_options_fail(self):
        for core, option in (("CM85", ".option_setting_banksel"), ("CM33", ".option_setting_ofs0")):
            result, _ = self.link(core, option)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("Unported or secondary-core option settings", result.stderr)

    def test_oversized_ram_fails_link(self):
        for core in ("CM85", "CM33"):
            result, _ = self.link(core, bss=0xd0000 + 1)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("RAM", result.stderr)


if __name__ == "__main__":
    unittest.main()
