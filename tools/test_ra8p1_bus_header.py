"""Manual-derived I3C and USB canonical interfaces and layout checks."""

import copy
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import test_ra8p1_device_header as layout
from tools import test_ra8p1_peripheral_header as small

HERE = small.HERE
GEN = small.GEN


class BusHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = small.peripheral_inventory()

    def test_inventory_is_valid_and_manually_cited(self):
        GEN.validate(copy.deepcopy(self.data))
        for block in self.data["types"]:
            for register in block["members"]:
                self.assertIn("RA8P1 HM", register["source"])

    def test_i3c_reserved_fields_are_not_fabricated(self):
        block = next(b for b in self.data["types"] if b["name"] == "R_I3C0_Type")
        registers = {r["name"]: r for r in block["members"]}
        # HM41.2.2,11,26,70 describe these implemented fields exhaustively.
        expected = {
            "BCTL": {"INCBA", "BMDS", "ABT", "RSM", "BUSE"},
            "IBINCTL": {"NRMRCTL", "NRSIRCTL"},
            "SCSTLCTL": {"STLCYC", "AAPE", "PARPE", "ACKPE"},
            "CSECMD": {"SVIRQE", "MSRQE"},
        }
        for register, fields in expected.items():
            with self.subTest(register=register):
                self.assertEqual(fields, {f["name"] for f in registers[register]["fields"]})
        rendered = GEN.render(copy.deepcopy(self.data))
        for forbidden in ("BCTL_HJACKCTL", "IBINCTL_NRHJCTL", "SCSTLCTL_TRAPE", "CSECMD_HJEVE"):
            self.assertNotIn("#define R_I3C0_" + forbidden + "_", rendered)

    def test_usb_port_widths_pipe_variants_and_device_counts(self):
        blocks = {b["name"]: b for b in self.data["types"]}
        fs = {r["name"]: r for r in blocks["R_USB_FS0_Type"]["members"]}
        hs = {r["name"]: r for r in blocks["R_USB_HS0_Type"]["members"]}
        # HM37.2.4–5,35–39 and HM38.2.7,38–41.
        self.assertEqual(16, fs["CFIFO"]["width"])
        self.assertEqual(32, hs["CFIFO"]["width"])
        self.assertEqual(6, fs["DEVADD"]["count"])
        self.assertEqual(10, hs["DEVADD"]["count"])
        self.assertEqual(0xE4, GEN.number(hs["DEVADDA"]["offset"]))
        self.assertNotIn("PIPEBUF", fs)
        self.assertNotIn("DPUSR0R", fs)
        self.assertNotIn("DPUSR0R_FS", hs)
        fs_views = {v["name"]: {f["name"] for f in v["fields"]} for v in fs["PIPE_CTR"]["views"]}
        self.assertIn("ATREPM", fs_views["PIPE5CTR"])
        self.assertNotIn("ATREPM", fs_views["PIPE6CTR"])
        self.assertIn("INBUFM", fs_views["PIPE5CTR"])
        self.assertNotIn("INBUFM", fs_views["PIPE9CTR"])

    def test_usb_fs_fifo_views_match_manual_access_widths(self):
        block = next(b for b in self.data["types"] if b["name"] == "R_USB_FS0_Type")
        registers = {r["name"]: r for r in block["members"]}
        # HM37.2.4–5 pp.1982–1984, Tables37.5–8: byte access uses bits7:0
        # for either BIGEND value. Neither upper-byte nor word access is valid.
        for port, offset in (("CFIFO", 0x14), ("D0FIFO", 0x18), ("D1FIFO", 0x1C)):
            with self.subTest(port=port):
                reg = registers[port]
                self.assertEqual((offset, 16, "R/W"), (GEN.number(reg["offset"]), reg["width"], reg["access"]))
                self.assertEqual({port + "L": (0, 16, "R/W"), port + "LL": (0, 8, "R/W")},
                                 {v["name"]: (v["offset"], v["width"], v["access"]) for v in reg["views"]})
                self.assertIn("Original FSP5.9", reg["note"])

    def test_original_usb_fs_fifo_macro_widths_native_and_both_arm_cores(self):
        stock = small.compatibility.original_sources(small.ROOT)
        path = "ra/fsp/src/r_usb_basic/src/hw/inc/r_usb_reg_access.h"
        macros = re.findall(r"^\s*#define\s+(USB0_(?:C|D0|D1)FIFO(?:8|16))\s+([^\r\n]+)",
                            stock[path].decode(), re.M)
        self.assertEqual(6, len(macros))
        extra = "\n#define USB_M0 registers\n"
        extra += "\n".join(f"#define {name} {value}" for name, value in macros) + "\n"
        for name, value in macros:
            bits = 16 if name.endswith("16") else 8
            extra += (f'_Static_assert(sizeof({value.replace("USB_M0", "((R_USB_FS0_Type *) 0)")}) == '
                      f'{bits // 8}, "{name} stock access width");\n')
            extra += (f"void {name.lower()}_store(R_USB_FS0_Type * registers, uint{bits}_t value) "
                      f"{{ {name} = value; }}\n"
                      f"uint{bits}_t {name.lower()}_load(R_USB_FS0_Type * registers) "
                      f"{{ return {name}; }}\n")
        with small.temporary_header(self.data, fixture="peripheral_bus.c"):
            original_check = layout.check_source

            def checked_source(data):
                source, expected = original_check(data)
                return source + extra, expected

            with patch.object(layout, "check_source", checked_source):
                layout.DeviceHeaderTests.test_native_layout_widths_masks_and_bitfields_both_cores(self)
                layout.DeviceHeaderTests.test_arm_layout_and_actual_bitfield_bytes_with_stock_cmsis(self)

    def test_native_all_layouts_masks_bitfield_bytes(self):
        with small.temporary_header(self.data, fixture="peripheral_bus.c"):
            layout.DeviceHeaderTests.test_native_layout_widths_masks_and_bitfields_both_cores(self)

    def test_native_writes_preserve_adjacent_bytes(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("Native compiler unavailable")
        with small.temporary_header(self.data) as include, tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "peripheral-writes"
            for core in (0, 1):
                for nonsecure in (0, 1):
                    with self.subTest(core=core, nonsecure=nonsecure):
                        layout.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined",
                                    f"-DBSP_CFG_CPU_CORE={core}", f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}",
                                    "-I", HERE / "layout/native", "-I", include, "-I", layout.BSP,
                                    HERE / "layout/peripheral_writes.c", "-o", executable])
                        layout.run([executable])

    def test_read_only_status_and_fifo_views_reject_writes(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("Native compiler unavailable")
        members = ("R_IIC0->ICDRR", "R_SSI0->SSIFRDR", "R_SSI0->SSIFRDR16",
                   "R_RTC->CP[2].RSEC_b.SEC1", "R_I3C0->MRCCPT",
                   "R_USB_HS0->PL1CTRL2_b.HIRDMON", "R_USB_FS0->SYSSTS0_b.LNST")
        with small.temporary_header(self.data) as include:
            for member in members:
                source = '#include "bsp_exceptions.h"\n#include "R7KA8P1KF.h"\nvoid rejected(void) { ' + member + ' = 0; }\n'
                with self.subTest(member=member):
                    result = subprocess.run([compiler, "-x", "c", "-std=c11", "-fsyntax-only",
                                             "-DBSP_CFG_CPU_CORE=0", "-I", str(HERE / "layout/native"),
                                             "-I", str(include), "-I", str(layout.BSP), "-"],
                                            input=source, text=True, capture_output=True, timeout=60)
                    self.assertNotEqual(0, result.returncode)
                    self.assertRegex(result.stderr, r"read.only|const.qualified")

    def test_cm85_cm33_all_layouts_masks_bitfield_bytes(self):
        with small.temporary_header(self.data, fixture="peripheral_bus.c"):
            layout.DeviceHeaderTests.test_arm_layout_and_actual_bitfield_bytes_with_stock_cmsis(self)


if __name__ == "__main__":
    unittest.main()
