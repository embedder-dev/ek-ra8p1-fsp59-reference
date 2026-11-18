"""Static resource contracts, not IAR/Arm Compiler build or runtime evidence."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from zipfile import ZipFile

from ra8p1.linker_commercial import commercial_files


ROOT = Path(__file__).resolve().parents[1]


class CommercialLinkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((ROOT / "validation/ra8p1/memory-contract.json").read_text())
        cls.stock = []
        with ZipFile(ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip") as release:
            for sibling in ("ra8m1", "ra6m5"):
                path = "internal/projectgen/ra/packs/Renesas.RA_mcu_" + sibling + ".5.9.0.pack"
                with ZipFile(BytesIO(release.read(path))) as pack:
                    cls.stock.append({p: pack.read(p) for p in (
                        "script/fsp.icf", "script/fsp.scat", "script/ac6/fsp_keep.via")})
        cls.files = commercial_files(*cls.stock, cls.contract)

    def text(self, core, extension):
        suffix = "" if core == "CM85" else "_cpu1"
        return self.files["script/fsp" + suffix + "." + extension].decode()

    def test_exact_interface_determinism_and_no_input_mutation(self):
        stocks, contract = deepcopy(self.stock), deepcopy(self.contract)
        files = commercial_files(*stocks, contract)
        self.assertEqual({"script/fsp.icf", "script/fsp_cpu1.icf", "script/fsp.scat",
                          "script/fsp_cpu1.scat", "script/ac6/fsp_keep.via"}, set(files))
        self.assertEqual(self.files, files)
        self.assertEqual(self.stock, stocks)
        self.assertEqual(self.contract, contract)
        self.assertTrue(all(isinstance(data, bytes) for data in files.values()))
        self.assertLess(sum(map(len, files.values())), 100_000)

    def test_original_same_core_sibling_inputs_are_required(self):
        for core_index in (0, 1):
            for path in self.stock[core_index]:
                with self.subTest(core=core_index, path=path):
                    stocks = deepcopy(self.stock)
                    stocks[core_index][path] += b"\n"
                    with self.assertRaisesRegex(ValueError, "Not the original FSP 5.9"):
                        commercial_files(*stocks, self.contract)
        with self.assertRaisesRegex(ValueError, "Not the original FSP 5.9"):
            commercial_files(self.stock[0], self.stock[0], self.contract)

    def test_bad_memory_contracts_fail_closed(self):
        for kind in ("overlap", "physical", "tcm", "option", "option_overlap", "owner", "section"):
            contract = deepcopy(self.contract)
            if kind == "overlap":
                contract["cores"]["CM33"]["SRAM"]["start"] = "0x22000000"
            elif kind == "physical":
                contract["cores"]["CM33"]["MRAM"]["size"] = "0x90000"
            elif kind == "tcm":
                contract["cores"]["CM33"]["ITCM"]["size"] = "0xffff"
            elif kind == "option":
                contract["options"][".option_setting_ofs0"]["address"] = "0x0300a100"
            elif kind == "option_overlap":
                contract["options"][".option_setting_ofs2"]["address"] = "0x02c9f040"
            elif kind == "owner":
                contract["options"][".option_setting_ofs0"]["owner"] = "CM33"
            else:
                contract["options"][".bad;section"] = contract["options"].pop(".option_setting_ofs0")
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                commercial_files(*self.stock, contract)

    def test_core_regions_equal_gcc_and_contract_not_preceding_bundle(self):
        for core, suffix in (("CM85", ""), ("CM33", "_cpu1")):
            gcc = (ROOT / "pack_sources/ra8p1/Renesas.RA_mcu_ra8p1.5.9.0/script" /
                   ("fsp" + suffix + ".ld")).read_text()
            iar, arm = self.text(core, "icf"), self.text(core, "scat")
            for region, contract_key in (("FLASH", "MRAM"), ("RAM", "SRAM"),
                                         ("ITCM", "ITCM"), ("DTCM", "DTCM")):
                cfg = self.contract["cores"][core][contract_key]
                for symbol_suffix, field in (("START", "start"), ("LENGTH", "size")):
                    symbol, expected = region + "_" + symbol_suffix, int(cfg[field], 0)
                    gcc_value = re.search(r"^" + symbol + r" = (0x[0-9a-f]+);", gcc, re.M)
                    self.assertEqual(expected, int(gcc_value[1], 0))
                    self.assertIn("define exported symbol RA8P1_" + symbol + " = " + hex(expected) + ";", iar)
                    self.assertIn("#undef " + symbol + "\n#define " + symbol + " " + hex(expected), arm)
            # No token from a stale memory_regions.icf allocation is used by placement.
            iar_body = iar.split("/* Uncomment", 1)[1]
            for region in ("FLASH", "RAM", "ITCM", "DTCM"):
                self.assertNotRegex(iar_body, r"\b" + region + r"_(?:START|LENGTH)\b")
            self.assertIn("define region RAM_region        = mem:[from RA8P1_RAM_START to RAM_END];", iar)
            self.assertIn("LOAD_REGION_FLASH FLASH_ORIGIN ALIGN 0x80 LIMITED_FLASH_LENGTH", arm)
            self.assertIn("#define FLASH_ORIGIN FLASH_START", arm)
            self.assertIn("#define LIMITED_FLASH_LENGTH FLASH_LENGTH", arm)
            self.assertIn("ScatterAssert(ImageLimit(RAM_END) <= RAM_START + RAM_LENGTH)", arm)
            self.assertIn("RAM_LIMIT RAM_START + RAM_LENGTH EMPTY 0", arm)

    def test_tcm_local_not_bus_aliases_and_native_startup_symbols(self):
        for core in ("CM85", "CM33"):
            iar, arm = self.text(core, "icf"), self.text(core, "scat")
            for region in ("ITCM", "DTCM"):
                cfg = self.contract["cores"][core][region]
                self.assertIn("RA8P1_" + region + "_BUS_ALIAS = " + hex(int(cfg["bus_alias"], 0)), iar)
                self.assertIn("#define " + region + "_BUS_ALIAS " + hex(int(cfg["bus_alias"], 0)), arm)
                self.assertIn("define region " + region + "_region", iar)
                self.assertIn("place at start of " + region + "_region", iar)
                self.assertIn("define block " + region + "_DATA_INIT with alignment = 16, end alignment = 8", iar)
                self.assertIn(region + "_DATA +0 NOCOMPRESS " + region + "_LENGTH", arm)
                self.assertIn(region + "_PAD (ImageLimit(" + region + "_DATA)) FILL 0 NOCOMPRESS", arm)
                self.assertIn("LoadLimit(" + region + "_DATA) == LoadBase(" + region + "_PAD)", arm)
            self.assertIn("define block DTCM_CONTENT with fixed order { block DTCM_DATA, block DTCM_BSS };", iar)
            self.assertIn("zi section .dtcm_bss", iar)
            self.assertIn("*(.bss.dtcm_bss)", arm)
            self.assertIn("ScatterAssert(ImageLimit(DTCM_BSS_PAD) <= DTCM_START + DTCM_LENGTH)", arm)

    def test_native_runtime_and_shared_sram_sections_remain(self):
        for core in ("CM85", "CM33"):
            iar, arm = self.text(core, "icf"), self.text(core, "scat")
            for token in ("initialize manually { readwrite }", "do not initialize   { zeroinit }",
                          "section __DLIB_PERTHREAD", "section .code_in_ram_init", "section .fsp_dtc_vector_table",
                          "section HEAP", "section .stack", "section FREE_MEM", "block USB_DEV_DESC_BLK",
                          "define block NOCACHE with alignment = 32, end alignment = 32",
                          "section .ns_buffer*", "Image$$__FLASH_NSC_START", "Image$$__RAM_NSC_START"):
                self.assertIn(token, iar)
            for region in ("INIT_ARRAY", "DATA", "BSS", "ARM_LIB_HEAP", "ARM_LIB_STACK", "STACK",
                           "RAM_END", "DTC_VECTOR_TABLE", "NOCACHE", "NOCACHE_PAD"):
                self.assertRegex(arm, r"(?m)^  " + region + r" ")
            for section in (".data.*", ".data", ".code_in_ram", ".bss.fsp_dtc_vector_table", ".bss.noinit",
                            ".bss.nocache", ".bss.heap", ".bss.stack", ".bss.stack.thread", ".ns_buffer*"):
                self.assertIn("*(" + section + ")", arm)
            self.assertIn("__RAM_NSC_START RAM_NSC_START EMPTY 0", arm)
            self.assertIn("__FLASH_NSC_START FLASH_NSC_START EMPTY 0", arm)
            # The native toolchain entry points must not be replaced by GNU libc.
            self.assertNotIn("GROUP(libgcc", iar + arm)

    def test_gcc_region_boundary_names_and_native_startup_references_are_covered(self):
        source = (ROOT / "baseline/ra/fsp/src/bsp/cmsis/Device/RENESAS/Source/system.c").read_text()
        arm_references = set(re.findall(r"extern (?:uint32_t|void).*?(?:Image|Load)\$\$(\w+)\$\$", source))
        iar_references = set(re.findall(r"extern uint32_t ([A-Z_]+)\$\$(?:Base|Limit);", source))
        self.assertTrue({"DATA", "BSS", "INIT_ARRAY", "ITCM_DATA", "DTCM_BSS"} <= arm_references)
        self.assertTrue({"ITCM_DATA_INIT", "DTCM_DATA_INIT", "DTCM_BSS"} <= iar_references)
        for core, suffix in (("CM85", ""), ("CM33", "_cpu1")):
            gcc = (ROOT / "pack_sources/ra8p1/Renesas.RA_mcu_ra8p1.5.9.0/script" /
                   ("fsp" + suffix + ".ld")).read_text()
            iar, arm = self.text(core, "icf"), self.text(core, "scat")
            for name in set(re.findall(r"\b__tz_[A-Z0-9_]+\b", gcc)):
                self.assertIn(name, iar)
                self.assertRegex(arm, r"(?m)^  " + name + r" ")
            for region in arm_references:
                self.assertRegex(arm, r"(?m)^  " + region + r" ")
            for block in iar_references:
                self.assertRegex(iar, r"define block " + block + r"\b")

    def test_every_auxiliary_gcc_region_has_bounded_commercial_counterpart(self):
        table = (("DATA_FLASH", "DF_region", "DATA_FLASH_LENGTH"),
                 ("QSPI_FLASH", "QSPI_region", "QSPI_FLASH_PRV_LENGTH"),
                 ("OSPI_DEVICE_0", "OSPI_DEVICE_0_region", "OSPI_DEVICE_0_PRV_LENGTH"),
                 ("OSPI_DEVICE_1", "OSPI_DEVICE_1_region", "OSPI_DEVICE_1_PRV_LENGTH"),
                 ("SDRAM", "SDRAM_region", "SDRAM_LENGTH"),
                 ("ID_CODE", "ID_CODE_region", "ID_CODE_LENGTH"))
        for core in ("CM85", "CM33"):
            iar, arm = self.text(core, "icf"), self.text(core, "scat")
            for region, icf_region, length in table:
                self.assertIn("define region " + icf_region + " = mem:[from " + region + "_START size " + length + "];", iar)
                self.assertIn("LOAD_REGION_" + region + " " + region + "_START " + length, arm)
            for index in (0, 1):
                self.assertIn(f"OSPI_DEVICE_{index}_NO_LOAD OSPI_DEVICE_{index}_START UNINIT NOCOMPRESS OSPI_DEVICE_{index}_PRV_LENGTH", arm)
                self.assertIn(f"section .ospi_device_{index}_no_load*", iar)
            for prefix, region in (("qspi", "QSPI_FLASH"), ("ospi_device_0", "OSPI_DEVICE_0"),
                                    ("ospi_device_1", "OSPI_DEVICE_1")):
                self.assertIn(prefix.upper() + "_NON_RETENTIVE ImageLimit(" + region + ") NOCOMPRESS", arm)
                self.assertIn("*(." + prefix + "_non_retentive*)", arm)
                self.assertIn("section ." + prefix + "_non_retentive_init", iar)
            self.assertIn("SDRAM +0 UNINIT NOCOMPRESS SDRAM_LENGTH", arm)
            self.assertIn("NOCACHE_SDRAM +0 UNINIT NOCOMPRESS ALIGN 32", arm)
            self.assertIn("define block NOCACHE_SDRAM with alignment = 32, end alignment = 32", iar)
            self.assertIn("ScatterAssert(ImageLimit(NOCACHE_SDRAM_PAD) <= SDRAM_START + SDRAM_LENGTH)", arm)

    def test_options_are_sparse_single_words_cpu0_only_without_gap_fill(self):
        expected = {s[1:].upper(): int(i["address"], 0) for s, i in self.contract["options"].items()}
        for core in ("CM85", "CM33"):
            iar, arm = self.text(core, "icf"), self.text(core, "scat")
            placed_iar = {name: int(address, 0) for address, name in re.findall(
                r"place at address mem:(0x[0-9a-f]+) \{ block (OPTION_SETTING_\w+) \};", iar)}
            placed_arm = {name: int(address, 0) for name, address in re.findall(
                r"^LOAD_REGION_(OPTION_SETTING_\w+) (0x[0-9a-f]+) 4$", arm, re.M)}
            self.assertEqual(expected if core == "CM85" else {}, placed_iar)
            self.assertEqual(placed_iar, placed_arm)
            for name in placed_iar:
                self.assertIn("define block " + name + " with maximum size = 4", iar)
                execution = re.search(r"(?m)^  " + name + r" (0x[0-9a-f]+) FIXED 4$", arm)
                self.assertIsNotNone(execution)
                self.assertEqual(placed_iar[name], int(execution[1], 0))
            option_area = arm[arm.index("LOAD_REGION_OPTION_BOUNDARIES"):arm.index("LOAD_REGION_DATA_FLASH")]
            self.assertNotIn("FILL", option_area)
            self.assertNotIn("UNUSED", option_area)
            self.assertNotIn("OPTION_SETTING_S_START+", iar)
            for script in (iar, arm):
                for legacy in (".option_setting_dualsel", ".option_setting_banksel", ".option_setting_bps", ".option_setting_data_flash"):
                    self.assertNotIn(legacy, script)
            self.assertIn("keep { section .option_setting* }", iar)
            self.assertIn("check that size(block UNSUPPORTED_OPTION_SETTINGS) == 0", iar)
            self.assertIn("ScatterAssert(ImageLength(UNSUPPORTED_OPTION_SETTINGS) == 0)", arm)
            self.assertIn("*(.option_setting*)", arm)
            if core == "CM33":
                self.assertIn("define block UNSUPPORTED_OPTION_SETTINGS { section .option_setting* };", iar)

    def test_retention_companion_covers_vectors_tcm_options_and_shared_sections(self):
        via = self.files["script/ac6/fsp_keep.via"].decode()
        for section in (".fixed_vectors*", ".application_vectors*", ".option_setting*", ".itcm_data*",
                        ".dtcm_data*", ".bss.dtcm_bss*", ".bss.nocache*", ".bss.noinit*", ".ns_buffer*",
                        ".bss.heap*", ".bss.stack*", ".data_flash*", ".id_code*", ".sdram*", ".frame*"):
            self.assertIn("--keep=*(" + section + ")", via)

    def preprocess(self, core, mode=""):
        compiler = shutil.which("clang") or shutil.which("cc")
        if compiler is None:
            self.skipTest("No host C preprocessor (not an Arm Compiler test)")
        # Deliberately stale CPU0 bundle, no OPTION_SETTING_S_LENGTH alias.
        memory = "\n".join("#define " + name + " " + value for name, value in {
            "FLASH_START": "0x02008000", "FLASH_LENGTH": "0x78000",
            "RAM_START": "0x22002000", "RAM_LENGTH": "0xce000",
            "ITCM_START": "0x0", "ITCM_LENGTH": "0x20000",
            "DTCM_START": "0x20000000", "DTCM_LENGTH": "0x20000",
            "OPTION_SETTING_START": "0x02c9f000", "OPTION_SETTING_LENGTH": "0x400",
            "DATA_FLASH_START": "0", "DATA_FLASH_LENGTH": "0", "ID_CODE_START": "0", "ID_CODE_LENGTH": "0",
            "QSPI_FLASH_START": "0", "QSPI_FLASH_LENGTH": "0", "OSPI_DEVICE_0_START": "0", "OSPI_DEVICE_0_LENGTH": "0",
            "OSPI_DEVICE_1_START": "0", "OSPI_DEVICE_1_LENGTH": "0", "SDRAM_START": "0", "SDRAM_LENGTH": "0",
        }.items()) + "\n" + mode + "\n"
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "memory_regions.scat").write_text(memory)
            source = self.text(core, "scat").split("\n", 1)[1]
            source += "\nCHECK_FLASH_START=FLASH_START; CHECK_RAM_START=RAM_START;\n"
            return subprocess.run([compiler, "-E", "-P", "-Werror", "-x", "c", "-I", directory, "-"],
                                  input=source, capture_output=True, text=True)

    def test_scatter_cpp_uses_core_allocation_even_with_stale_generated_inputs(self):
        for core in ("CM85", "CM33"):
            with self.subTest(core=core):
                result = self.preprocess(core)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("CHECK_FLASH_START=" + hex(int(self.contract["cores"][core]["MRAM"]["start"], 0)), result.stdout)
                self.assertIn("CHECK_RAM_START=" + hex(int(self.contract["cores"][core]["SRAM"]["start"], 0)), result.stdout)
                self.assertIn("LOAD_REGION_ID_CODE 0 0", result.stdout)
                if core == "CM33":
                    self.assertNotRegex(result.stdout, r"(?m)^LOAD_REGION_OPTION_SETTING_")

    def test_nonflat_inputs_rejected_not_silently_mapped_to_flat(self):
        for core in ("CM85", "CM33"):
            self.assertIn('!isdefinedsymbol(PROJECT_NONSECURE) && !isdefinedsymbol(PROJECT_SECURE)', self.text(core, "icf"))
            for mode in ("PROJECT_NONSECURE", "PROJECT_SECURE"):
                result = self.preprocess(core, "#define " + mode + " 1")
                self.assertNotEqual(0, result.returncode)
                self.assertIn("RA8P1 flat CPU0/CPU1 allocation only", result.stderr)


if __name__ == "__main__":
    unittest.main()
