"""Manual-derived peripheral layouts and disposable compatibility overlays.

The optional CLI compile report uses compatibility.py and unmodified generated
configuration. Missing dependencies and genuine stock-hardware differences remain
explicit failures/blockers in the report, not substituted register definitions.
"""

import argparse
import copy
from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tools import test_ra8p1_device_header as layout
from tools.ra8p1 import compatibility

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / "tools/ra8p1"
INVENTORY = HERE / "registers_peripheral_small.json"
GEN = layout.GEN


def peripheral_inventory():
    return GEN.validate(GEN.load_inventory())


@contextmanager
def temporary_header(data, fixture="peripheral_small.c"):
    """The integration compiler sees a disposable header, never an installed one."""
    original_include = layout.INCLUDE
    original_check_source = layout.check_source

    def checked_source(inventory):
        source, expected = original_check_source(inventory)
        return source.replace('#include "anchors.c"',
                              f'#include "anchors.c"\n#include "{fixture}"'), expected

    with tempfile.TemporaryDirectory(prefix="ra8p1-peripheral-header-") as temporary:
        include = Path(temporary)
        (include / "R7KA8P1KF.h").write_text(GEN.render(copy.deepcopy(data)))
        shutil.copyfile(original_include / "system.h", include / "system.h")
        with patch.object(layout, "INCLUDE", include), patch.object(layout, "check_source", checked_source):
            yield include


class PeripheralHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = peripheral_inventory()

    def test_integrated_inputs_are_consumed_by_generator(self):
        self.assertIn(INVENTORY, list(HERE.glob("registers*.json")))
        self.assertFalse(list(HERE.glob("registers_peripheral_*.json.pending")))
        current = GEN.load_inventory()
        self.assertIn("R_IIC0_Type", {b["name"] for b in current["types"]})
        GEN.validate(copy.deepcopy(self.data))

    def test_no_absent_agt32_or_extra_wakeup_storage(self):
        blocks = {b["name"]: b for b in self.data["types"]}
        self.assertEqual({"AGT16"}, {r["name"] for r in blocks["R_AGTX0_Type"]["members"]})
        control = blocks["R_AGTX0_AGT16_CTRL_Type"]
        self.assertNotIn("AGTIOSEL_ALT", {r["name"] for r in control["members"]})
        select = next(r for r in control["members"] if r["name"] == "AGTIOSEL")
        self.assertEqual(["TIES"], [f["name"] for f in select["fields"]])
        wake = next(r for r in blocks["R_ICU_Type"]["members"] if r["name"] == "WUPEN0")
        self.assertEqual(["WUPEN"], wake["aliases"])
        self.assertNotIn("WUPEN2", {r["name"] for r in blocks["R_ICU_Type"]["members"]})
        self.assertNotIn("LVD1WUPEN", {f["name"] for f in wake["fields"]})
        system = {r["name"] for r in blocks["R_SYSTEM_Type"]["members"]}
        self.assertNotIn("LVD3CMPCR", system)
        self.assertTrue({"LVD1CMPCR", "LVD2CMPCR", "PVD4CMPCR", "PVD5CMPCR"}.issubset(system))
        registers = {r["name"]: r for r in blocks["R_SYSTEM_Type"]["members"]}
        for channel in (1, 2):
            for suffix in ("CMPCR", "CR0", "CR1", "SR", "FCR"):
                canonical = registers[f"LVD{channel}{suffix}"]
                native = next(v for v in canonical["views"] if v["name"] == f"PVD{channel}{suffix}")
                self.assertEqual(0, native["offset"])
                self.assertEqual(canonical["width"], native["width"])
                self.assertEqual([(f["pos"], f["bits"], f["access"]) for f in canonical["fields"]],
                                 [(f["pos"], f["bits"], f["access"]) for f in native["fields"]])
        for channel in (4, 5):
            self.assertEqual({"RE", "DFDIS", "CMPE", "FSAMP"},
                             {f["name"] for f in registers[f"PVD{channel}CR0"]["fields"]})
            self.assertNotIn(f"LVD{channel}CR0", registers)

    def test_native_all_public_layouts_masks_and_bitfield_bytes(self):
        with temporary_header(self.data):
            layout.DeviceHeaderTests.test_native_layout_widths_masks_and_bitfields_both_cores(self)

    def test_cm85_cm33_stock_cmsis_all_public_layouts_and_bitfield_bytes(self):
        with temporary_header(self.data):
            layout.DeviceHeaderTests.test_arm_layout_and_actual_bitfield_bytes_with_stock_cmsis(self)


def compile_peripherals(project, report, modules, inventory=None):
    census = json.loads((HERE / "compatibility_census.json").read_text())["modules"]
    selected = [m for m in census if m["name"] in modules]
    if {m["name"] for m in selected} != set(modules):
        raise ValueError("Requested module missing from census")
    stock = compatibility.original_sources(ROOT, selected)
    candidate = compatibility.candidate_sources(ROOT, "after")
    candidate["ra/fsp/src/bsp/cmsis/Device/RENESAS/Include/R7KA8P1KF.h"] = GEN.render(inventory or peripheral_inventory()).encode()
    results = []
    for source_set in ("stock", "candidate"):
        result = compatibility.compile_project(ROOT, project, selected, source_set, "after", stock, candidate)
        result["source_set"] = source_set
        results.append(result)
    report.write_text(json.dumps({"scope": "Disposable canonical-header overlay; generated configuration unchanged",
                                  "input": str(INVENTORY.relative_to(ROOT)), "reports": results}, indent=2) + "\n")
    for item in results:
        print(item["source_set"], {name: row["status"] for name, row in item["modules"].items()})
    return int(any(row["status"] != "pass" for item in results for row in item["modules"].values()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compat-project", type=Path)
    parser.add_argument("--compat-report", type=Path)
    parser.add_argument("--module", action="append")
    args, remaining = parser.parse_known_args()
    if args.compat_project:
        if not args.compat_report:
            parser.error("--compat-report is required")
        raise SystemExit(compile_peripherals(args.compat_project, args.compat_report,
                                         args.module or ["r_iic_master", "r_iic_slave", "r_agt", "r_rtc", "r_lpm", "r_lvd"]))
    unittest.main(argv=[__file__, *remaining])
