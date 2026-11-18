"""Compile-only auxiliary graphics/comparator layout and FSP5.9 vocabulary checks."""

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
from test_ra8p1_device_header import check_source, elf_sections


INVENTORY = TOOLS / "registers_compat_graphics.json"
STOCK = ROOT / "baseline/ra/fsp/src/bsp/cmsis/Device/RENESAS/Include/R7FA8D1BH.h"

# Independent numeric anchors from HM §§22.2.1, 57.2, 61.2 and 63.2.
ANCHORS = r'''
_Static_assert(sizeof(R_GPT_POEG0_Type) == 4, "POEG implemented extent");
_Static_assert(offsetof(R_GPT_POEG0_Type, POEGG) == 0, "POEGG offset");
_Static_assert(R_GPT_POEG0_POEGG_CDRE3_Msk == 0x800UL, "last target comparator");
_Static_assert(R_GPT_POEG0_POEGG_ST_Msk == 0x10000UL, "POEG input status");
_Static_assert(R_GPT_POEG0_POEGG_NFCS_Msk == 0xC0000000UL, "POEG noise divider");
_Static_assert(R_GPT_POEG0_S_BASE == 0x40212000UL, "POEG secure base");
_Static_assert(R_GPT_POEG3_NS_BASE == 0x50212300UL, "POEG last nonsecure base");
_Static_assert(R_GPT_POEG1_BASE - R_GPT_POEG0_BASE == 0x100UL, "POEG stride");
_Static_assert(sizeof(R_ACMPHS0_Type) == 0x45, "ACMPHS implemented extent");
_Static_assert(_Alignof(R_ACMPHS0_Type) == 1, "ACMPHS byte registers");
_Static_assert(offsetof(R_ACMPHS0_Type, CMPCTL) == 0, "comparator control");
_Static_assert(offsetof(R_ACMPHS0_Type, CMPSEL0) == 4, "input select");
_Static_assert(offsetof(R_ACMPHS0_Type, CMPSEL1) == 8, "reference select");
_Static_assert(offsetof(R_ACMPHS0_Type, CMPMON) == 0xC, "read-only comparator monitor");
_Static_assert(offsetof(R_ACMPHS0_Type, CPIOC) == 0x10, "output enable");
_Static_assert(offsetof(R_ACMPHS0_Type, CPINTCTL) == 0x40, "interrupt enable");
_Static_assert(offsetof(R_ACMPHS0_Type, CPMSKCTL) == 0x44, "interrupt mask source");
_Static_assert(R_ACMPHS0_CMPSEL1_CRVS_Msk == 0xFUL, "target has four reference inputs");
_Static_assert(R_ACMPHS0_CMPCTL_CDFS_Msk == 0x60UL, "comparator noise filter");
_Static_assert(R_ACMPHS0_CPIOC_VREFEN_Msk == 0x80UL, "channel-zero reference enable");
_Static_assert(R_ACMPHS0_S_BASE == 0x40236000UL, "comparator secure base");
_Static_assert(R_ACMPHS3_NS_BASE == 0x50236300UL, "last comparator nonsecure base");
_Static_assert(R_ACMPHS1_BASE - R_ACMPHS0_BASE == 0x100UL, "comparator stride");
_Static_assert(sizeof(R_CEU_Type) == 0x20A0, "CEU mirror-plane extent");
_Static_assert(offsetof(R_CEU_Type, CAPSR) == 0, "capture start");
_Static_assert(offsetof(R_CEU_Type, CEIER) == 0x70, "capture interrupt enable");
_Static_assert(offsetof(R_CEU_Type, CETCR) == 0x74, "capture interrupt flags");
_Static_assert(offsetof(R_CEU_Type, CSTSR) == 0x7C, "capture status");
_Static_assert(offsetof(R_CEU_Type, CDSSR) == 0x84, "capture data size");
_Static_assert(offsetof(R_CEU_Type, CBWER) == 0xA0, "HM61.2.29 target bufferable write register");
_Static_assert(sizeof(((R_CEU_Type *) 0)->CBWER) == 4, "CBWER word access");
_Static_assert(R_CEU_CBWER_BWE_Pos == 0, "CBWER BWE position");
_Static_assert(R_CEU_CBWER_BWE_Msk == 1UL, "CBWER BWE mask");
_Static_assert(offsetof(R_CEU_Type, CAMOR_B) == 0x1010, "plane B offset");
_Static_assert(offsetof(R_CEU_Type, CAMOR_M) == 0x2010, "unused-plane mirror");
_Static_assert(offsetof(R_CEU_Type, CDBCR2_M) == 0x209C, "last mirror register");
_Static_assert(R_CEU_CAMCR_DTIF_Msk == 0x1000UL, "capture bus width");
_Static_assert(R_CEU_CMCYR_HCYL_Msk == 0x3FFFUL, "horizontal cycle count");
_Static_assert(R_CEU_CFWCR_FWV_Msk == 0xFFFFFFE0UL, "firewall address upper bits");
_Static_assert(R_CEU_CDOCR_CBE_Msk == 0x10000UL, "bundle write enable");
_Static_assert(R_CEU_CETCR_FWF_Msk == 0x800000UL, "firewall interrupt");
_Static_assert(R_CEU_S_BASE == 0x40348000UL, "CEU secure base");
_Static_assert(R_CEU_NS_BASE == 0x50348000UL, "CEU nonsecure base");
_Static_assert(sizeof(R_DRW_Type) == 0x104, "DRW implemented extent");
_Static_assert(offsetof(R_DRW_Type, CONTROL) == 0, "geometry write port");
_Static_assert(offsetof(R_DRW_Type, STATUS) == 0, "status read port");
_Static_assert(offsetof(R_DRW_Type, CONTROL2) == 4, "surface write port");
_Static_assert(offsetof(R_DRW_Type, HWREVISION) == 4, "feature read port");
_Static_assert(offsetof(R_DRW_Type, L1START) == 0x10, "first limiter start");
_Static_assert(offsetof(R_DRW_Type, L6START) == 0x24, "last limiter start");
_Static_assert(offsetof(R_DRW_Type, L6XADD) == 0x3C, "last limiter X increment");
_Static_assert(offsetof(R_DRW_Type, L6YADD) == 0x54, "last limiter Y increment");
_Static_assert(offsetof(R_DRW_Type, LVSTARTI) == 0x9C, "V limiter integer start");
_Static_assert(sizeof(((R_DRW_Type *) 0)->LVSTARTI) == 4, "V integer start access");
_Static_assert(offsetof(R_DRW_Type, IRQCTL) == 0xC0, "drawing interrupts");
_Static_assert(offsetof(R_DRW_Type, DLISTSTART) == 0xC8, "display-list launch");
_Static_assert(offsetof(R_DRW_Type, PERFCOUNT2) == 0xD0, "second performance counter");
_Static_assert(offsetof(R_DRW_Type, DBWER) == 0x100, "bufferable write enable");
_Static_assert(R_DRW_CONTROL2_READFORMAT32_Msk == 0x30UL, "upper texture format bits");
_Static_assert(R_DRW_CONTROL2_READFORMAT10_Msk == 0xC0000UL, "lower texture format bits");
_Static_assert(R_DRW_CONTROL2_WRITEFORMAT10_Msk == 0x300000UL, "framebuffer format");
_Static_assert(R_DRW_STATUS_BUSERRMDL_Msk == 0x400UL, "display-list bus error");
_Static_assert(R_DRW_HWREVISION_TEXCLU_Msk == 0x200000UL, "texture CLUT feature");
_Static_assert(R_DRW_DBWER_BWE_Msk == 4, "DRW write buffering");
_Static_assert(R_DRW_S_BASE == 0x40444000UL, "DRW secure base");
_Static_assert(R_DRW_NS_BASE == 0x50444000UL, "DRW nonsecure base");
'''


def stock_vocabulary(name):
    text = STOCK.read_text()
    end = text.index("} " + name + ";")
    text = text[text.rfind("typedef struct", 0, end):end]
    return {
        match.group(1): set(re.findall(r"uint\d+_t\s+(\w+)\s*:", match.group(2)))
        for match in re.finditer(
            r"uint(?:8|16|32)_t\s+(\w+)(?:\[[^\]]+\])?\s*;.*?struct\s*\{(.*?)\}\s*\1_b", text, re.S)
        if not match.group(1).startswith("RESERVED")
    }


class AuxPeripheralHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fragment = json.loads(INVENTORY.read_text())
        cls.data = header.load_inventory()
        cls.rendered = header.render(copy.deepcopy(cls.data))
        source, cls.expected = check_source(copy.deepcopy(cls.data))
        cls.source = source + ANCHORS

    def test_unique_types_and_only_original_register_vocabulary(self):
        self.assertEqual({"R_GPT_POEG0_Type", "R_ACMPHS0_Type", "R_DRW_Type", "R_CEU_Type"},
                         {block["name"] for block in self.fragment["types"]})
        for block in self.fragment["types"]:
            stock = stock_vocabulary(block["name"])
            # HM61.2.29 defines CBWER.BWE, not the stock AXIBUSCTL2.AWCACHE register.
            additions = {"CBWER": {"BWE"}} if block["name"] == "R_CEU_Type" else {}
            actual = {}
            for reg in block["members"]:
                actual[reg["name"]] = {field["name"] for field in reg.get("fields", [])}
                for view in reg.get("views", []):
                    actual[view["name"]] = {field["name"] for field in view.get("fields", [])}
            with self.subTest(block=block["name"]):
                self.assertEqual(actual.keys() - stock.keys(), additions.keys())
                for reg, fields in actual.items():
                    if reg in additions:
                        self.assertEqual(fields, additions[reg], reg)
                    else:
                        self.assertLessEqual(fields, stock[reg], reg)
        ceu = next(block for block in self.fragment["types"] if block["name"] == "R_CEU_Type")
        self.assertIn("not aliased to legacy AXIBUSCTL2", ceu["note"])
        self.assertNotIn("AXIBUSCTL2", {reg["name"] for reg in ceu["members"]})
        for forbidden in ("R_GPT_POEG0_POEGG_DERR0ST", "R_GPT_POEG0_POEGG_CDRE4",
                          "R_GPT_POEG0_GTONCWP", "R_GPT_POEG0_GTONCCR"):
            self.assertNotIn(forbidden, self.rendered)

    def test_native_layout_and_stock_hal_vocabulary(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("Native compiler unavailable")
        text = self.source
        for driver, instance, expression in (
            ("r_poeg", "R_GPT_POEG0", r"->(POEGG(?:_b\.\w+)?)"),
            ("r_acmphs", "R_ACMPHS0", r"->(CMP\w+(?:\.\w+)?|CPIOC(?:_b\.\w+)?)"),
            ("r_ceu", "R_CEU", r"R_CEU->(\w+(?:\.\w+)?)"),
        ):
            source = (ROOT / f"baseline/ra/fsp/src/{driver}/{driver}.c").read_text()
            text += f"\nvoid {driver}_vocabulary(void) {{\n"
            for member in sorted(set(re.findall(expression, source))):
                text += f"    (void) ({instance}->{member});\n"
            text += "}\n"
            for macro in re.findall(r"\bR_(?:GPT_POEG0|ACMPHS0|CEU)_\w+_(?:Pos|Msk)\b", source):
                if "DERR" not in macro:
                    self.assertIn(f"#define {macro} ", self.rendered)
        for path in sorted((ROOT / "baseline/ra/fsp/src/r_drw").glob("*.c")):
            for member in re.findall(r"R_DRW->(\w+(?:\.\w+)?)", path.read_text()):
                text += f"\nvoid drw_{member.lower()}_vocabulary_{len(text)}(void) {{ (void) R_DRW->{member}; }}\n"
        with tempfile.TemporaryDirectory(prefix="ra8p1-aux-peripheral-native-") as tmp:
            folder = Path(tmp)
            (folder / "R7KA8P1KF.h").write_text(self.rendered)
            for core in (0, 1):
                for nonsecure in (0, 1):
                    with self.subTest(core=core, nonsecure=nonsecure):
                        result, command, _ = compile_source(
                            compiler, folder, text, core, nonsecure, [TOOLS / "layout/native", TOOLS / "layout"])
                        self.assertEqual(0, result.returncode, " ".join(command) + "\n" + result.stderr)

    def test_arm_layout_and_bitfield_bytes_both_cores_security_aliases(self):
        compiler = os.environ.get("RA8P1_ARM_CC") or shutil.which("arm-none-eabi-gcc")
        if not compiler:
            self.skipTest("Arm GCC unavailable (set RA8P1_ARM_CC)")
        with tempfile.TemporaryDirectory(prefix="ra8p1-aux-peripheral-arm-") as tmp:
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

    def test_read_only_status_registers_and_bitfields_reject_writes(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("Native compiler unavailable")
        with tempfile.TemporaryDirectory(prefix="ra8p1-aux-peripheral-readonly-") as tmp:
            folder = Path(tmp)
            (folder / "R7KA8P1KF.h").write_text(self.rendered)
            for member in ("R_GPT_POEG0->POEGG_b.ST", "R_ACMPHS0->CMPMON",
                           "R_ACMPHS0->CMPMON_b.CMPMON", "R_CEU->CSTSR", "R_CEU->CDSSR",
                           "R_DRW->STATUS", "R_DRW->STATUS_b.BUSIRQ", "R_DRW->HWREVISION"):
                with self.subTest(member=member):
                    result, _, _ = compile_source(
                        compiler, folder, '#include "R7KA8P1KF.h"\nvoid rejected(void) { '
                        + member + ' = 0; }\n', includes=[TOOLS / "layout/native"])
                    self.assertNotEqual(0, result.returncode)
                    self.assertRegex(result.stderr, r"read.only|const.qualified")


if __name__ == "__main__":
    unittest.main()
