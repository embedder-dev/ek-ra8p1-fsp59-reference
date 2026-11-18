"""Manual-derived OSPI_B layout and original FSP5.9 macro-contract checks."""

import copy
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import unittest

from ra8p1 import generate_device_header as header
from test_ra8p1_aux_header import ROOT, TOOLS, compile_source, extract_stock_cmsis
from test_ra8p1_aux_peripherals_header import stock_vocabulary
from test_ra8p1_device_header import check_source, elf_sections


INVENTORY = TOOLS / "registers_compat_ospi.json"
ANCHORS = r'''
_Static_assert(sizeof(R_XSPI0_CMCFGCS_Type) == 0x10, "command-map CS stride");
_Static_assert(offsetof(R_XSPI0_CMCFGCS_Type, CMCFG2) == 8, "write command map");
_Static_assert(sizeof(R_XSPI0_CDBUF_Type) == 0x10, "manual command stride");
_Static_assert(offsetof(R_XSPI0_CDBUF_Type, CDD1) == 0xC, "upper manual data");
_Static_assert(sizeof(R_XSPI0_CCCTLCS_Type) == 0x20, "calibration CS stride");
_Static_assert(offsetof(R_XSPI0_CCCTLCS_Type, CCCTL7) == 0x1C, "last calibration pattern");
_Static_assert(sizeof(R_XSPI0_Type) == 0x19C, "stock HAL register slice extent");
_Static_assert(_Alignof(R_XSPI0_Type) == 4, "word register alignment");
_Static_assert(offsetof(R_XSPI0_Type, WRAPCFG) == 0, "wrapper configuration");
_Static_assert(offsetof(R_XSPI0_Type, BMCFGCH[1]) == 0xC, "second bus master");
_Static_assert(offsetof(R_XSPI0_Type, CMCFGCS[1].CMCFG0) == 0x20, "second CS command map");
_Static_assert(offsetof(R_XSPI0_Type, CMCFGCS[1].CMCFG2) == 0x28, "second CS write command");
_Static_assert(offsetof(R_XSPI0_Type, LIOCFGCS[1]) == 0x54, "second CS protocol");
_Static_assert(offsetof(R_XSPI0_Type, BMCTL0) == 0x60, "bus access control");
_Static_assert(offsetof(R_XSPI0_Type, BMCTL1) == 0x64, "buffer push/clear");
_Static_assert(offsetof(R_XSPI0_Type, CMCTLCH[1]) == 0x6C, "second master XIP");
_Static_assert(offsetof(R_XSPI0_Type, CDCTL0) == 0x70, "direct-manual control");
_Static_assert(offsetof(R_XSPI0_Type, CDBUF[3].CDD1) == 0xBC, "fourth command upper data");
_Static_assert(sizeof(((R_XSPI0_Type *) 0)->CDBUF) == 0x40, "four manual commands");
_Static_assert(offsetof(R_XSPI0_Type, LPCTL0) == 0x100, "pattern control");
_Static_assert(offsetof(R_XSPI0_Type, LIOCTL) == 0x108, "link IO control");
_Static_assert(offsetof(R_XSPI0_Type, CCCTLCS[1].CCCTL0) == 0x150, "second calibration channel");
_Static_assert(offsetof(R_XSPI0_Type, CCCTLCS[1].CCCTL7) == 0x16C, "last calibration word");
_Static_assert(offsetof(R_XSPI0_Type, COMSTT) == 0x184, "common status");
_Static_assert(offsetof(R_XSPI0_Type, CASTTCS[1]) == 0x18C, "second calibration status");
_Static_assert(offsetof(R_XSPI0_Type, INTS) == 0x190, "interrupt status");
_Static_assert(offsetof(R_XSPI0_Type, INTC) == 0x194, "interrupt clear");
_Static_assert(offsetof(R_XSPI0_Type, INTE) == 0x198, "interrupt enable");
_Static_assert(R_XSPI0_WRAPCFG_DSSFTCS0_Msk == 0x1F00UL, "first target DS delay");
_Static_assert(R_XSPI0_WRAPCFG_DSSFTCS1_Msk == 0x1F000000UL, "second target DS delay");
_Static_assert(R_XSPI0_BMCTL0_CH1CS1ACC_Msk == 0xC0UL, "second master second slave access");
_Static_assert(R_XSPI0_LIOCFGCS_PRTMD_Msk == 0x3FFUL, "protocol mode");
_Static_assert(R_XSPI0_CDBUF_CDT_ADDSIZE_Msk == 0x1CUL, "manual address width");
_Static_assert(R_XSPI0_CDBUF_CDT_CMD_Msk == 0xFFFF0000UL, "manual command bytes");
_Static_assert(R_XSPI0_LPCTL1_PATREQ_Msk == 3, "reset pattern request");
_Static_assert(R_XSPI0_CCCTLCS_CCCTL0_CASFTEND_Msk == 0x1F000000UL, "calibration upper delay");
_Static_assert(R_XSPI0_CCCTLCS_CCCTL1_CADATASIZE_Msk == 0x1E0UL, "calibration data size");
_Static_assert(R_XSPI0_S_BASE == 0x40268000UL, "unit zero secure base");
_Static_assert(R_XSPI1_S_BASE == 0x40268400UL, "unit one secure base");
_Static_assert(R_XSPI1_NS_BASE == 0x50268400UL, "unit one nonsecure base");
_Static_assert(R_XSPI1_BASE - R_XSPI0_BASE == 0x400UL, "unit stride");
'''


class OspiHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fragment = json.loads(INVENTORY.read_text())
        cls.data = header.load_inventory()
        cls.rendered = header.render(copy.deepcopy(cls.data))
        cls.source, cls.expected = check_source(copy.deepcopy(cls.data))
        cls.source += ANCHORS

    def test_baseline_vocabulary_and_target_absences(self):
        self.assertEqual({"R_XSPI0_CMCFGCS_Type", "R_XSPI0_CDBUF_Type", "R_XSPI0_CCCTLCS_Type", "R_XSPI0_Type"},
                         {block["name"] for block in self.fragment["types"]})
        stock_text = (ROOT / "baseline/ra/fsp/src/bsp/cmsis/Device/RENESAS/Include/R7FA8D1BH.h").read_text()
        for block in self.fragment["types"]:
            vocabulary = stock_vocabulary(block["name"])
            for reg in block["members"]:
                if "type" in reg:
                    self.assertIn(reg["type"], {typ["name"] for typ in self.fragment["types"]})
                    continue
                self.assertIn(reg["name"], vocabulary)
                for field in reg["fields"]:
                    self.assertIn(field["name"], vocabulary[reg["name"]])
                    macro = field.get("macro_name", field["name"])
                    if macro is not None:
                        prefix = block["name"].removesuffix("_Type") + "_" + reg["name"] + "_" + macro
                        self.assertRegex(stock_text, rf"#define {prefix}_Pos\b")
        main = next(block for block in self.fragment["types"] if block["name"] == "R_XSPI0_Type")
        self.assertNotIn("ABMCFG", {reg["name"] for reg in main["members"]})
        self.assertNotIn("VERSTT", {reg["name"] for reg in main["members"]})
        for reg in main["members"]:
            names = {field["name"] for field in reg.get("fields", [])}
            if reg["name"] == "WRAPCFG":
                self.assertEqual({"DSSFTCS0", "DSSFTCS1"}, names)
            elif reg["name"] == "LIOCTL":
                self.assertEqual({"WPCS1", "RSTCS0"}, names)
            elif reg["name"] in ("INTS", "INTC", "INTE"):
                self.assertFalse(any(name.startswith(("INICMP", "BRGOF", "BRGUF", "ECSCS0", "INTCS0")) for name in names))

    def test_original_stock_hal_macro_contract(self):
        driver = (ROOT / "baseline/ra/fsp/src/r_ospi_b/r_ospi_b.c").read_text()
        required = set(re.findall(r"\bR_XSPI0_\w+_(?:Pos|Msk)\b", driver))
        missing = sorted(macro for macro in required if f"#define {macro} " not in self.rendered)
        self.assertEqual([], missing, "The owning renderer must honor per-field macro_name/null without changing bitfield names")

    def test_native_layout_both_cores_security_aliases(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("Native compiler unavailable")
        with tempfile.TemporaryDirectory(prefix="ra8p1-ospi-native-") as tmp:
            folder = Path(tmp)
            (folder / "R7KA8P1KF.h").write_text(self.rendered)
            for core in (0, 1):
                for nonsecure in (0, 1):
                    with self.subTest(core=core, nonsecure=nonsecure):
                        result, command, _ = compile_source(
                            compiler, folder, self.source, core, nonsecure, [TOOLS / "layout/native", TOOLS / "layout"])
                        self.assertEqual(0, result.returncode, " ".join(command) + "\n" + result.stderr)

    def test_arm_layout_and_bitfield_object_bytes(self):
        compiler = os.environ.get("RA8P1_ARM_CC") or shutil.which("arm-none-eabi-gcc")
        if not compiler:
            self.skipTest("Arm GCC unavailable (set RA8P1_ARM_CC)")
        with tempfile.TemporaryDirectory(prefix="ra8p1-ospi-arm-") as tmp:
            folder = Path(tmp)
            (folder / "R7KA8P1KF.h").write_text(self.rendered)
            cmsis = folder / "cmsis"
            extract_stock_cmsis(cmsis)
            for core in (0, 1):
                cpu, fpu = ("cortex-m85", "fpv5-d16") if core == 0 else ("cortex-m33", "fpv5-sp-d16")
                for nonsecure in (0, 1):
                    with self.subTest(core=core, nonsecure=nonsecure):
                        result, command, obj = compile_source(
                            compiler, folder, self.source, core, nonsecure, [cmsis, TOOLS / "layout"],
                            [f"-mcpu={cpu}", "-mthumb", f"-mfpu={fpu}", "-mfloat-abi=hard"])
                        self.assertEqual(0, result.returncode, " ".join(command) + "\n" + result.stderr)
                        actual = elf_sections(obj)
                        for section, expected in self.expected.items():
                            self.assertEqual(expected, actual[section], section)

    def test_status_registers_reject_writes(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("Native compiler unavailable")
        with tempfile.TemporaryDirectory(prefix="ra8p1-ospi-readonly-") as tmp:
            folder = Path(tmp)
            (folder / "R7KA8P1KF.h").write_text(self.rendered)
            for member in ("COMSTT", "COMSTT_b.MEMACCCH0", "CASTTCS[1]", "CASTTCS_b[1].CASUC", "INTS", "INTS_b.CASUCCS1"):
                with self.subTest(member=member):
                    result, _, _ = compile_source(
                        compiler, folder, '#include "R7KA8P1KF.h"\nvoid rejected(void) { R_XSPI0->'
                        + member + ' = 0; }\n', includes=[TOOLS / "layout/native"])
                    self.assertNotEqual(0, result.returncode)
                    self.assertRegex(result.stderr, r"read.only|const.qualified")


if __name__ == "__main__":
    unittest.main()
