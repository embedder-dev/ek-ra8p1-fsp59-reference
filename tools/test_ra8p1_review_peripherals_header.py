"""Independent HM/SVD review checks; render temporary headers, never publish one.

The frozen HM tables and handwritten C anchors are separate from the production
inventory. Native/Arm compilation uses the established CMSIS fixtures/original
5.9 pack. No IDE, installed pack, target, or newer FSP source is consulted.
"""

import copy
import hashlib
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


INVENTORY = TOOLS / "registers_review_peripherals.json"
FIXTURES = TOOLS / "review_peripherals"
TYPES = {
    "R_GPTP_Type", "R_MIPI_CSI0_Type", "R_VIN0_Type", "R_ECCMB0_Type",
    "R_MFWD_Type", "R_ESWM_Type", "R_COMA_Type", "R_ETHA0_Type", "R_RMAC0_Type",
    "R_GWCA0_Type", "R_DOTF_Type", "R_PDG_Type",
}


def flat_members(block):
    """Numbered public views, with physical offsets independent of C rendering."""
    result = {}
    for reg in block["members"]:
        if "count" in reg:
            names = reg["individual_names"]
            assert len(names) == reg["count"]
            for i, name in enumerate(names):
                result[name] = {**reg, "name": name,
                                "offset": header.number(reg["offset"]) + i * reg["width"] // 8}
        else:
            result[reg["name"]] = {**reg, "offset": header.number(reg["offset"])}
    return result


def mask(field):
    return ((1 << field["bits"]) - 1) << field["pos"]


class ReviewPeripheralHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fragment = json.loads(INVENTORY.read_text())
        cls.hm = json.loads((FIXTURES / "hm_layout.json").read_text())
        cls.merged = header.load_inventory()
        cls.data = {**cls.merged, "types": copy.deepcopy(cls.fragment["types"]),
                    "instances": copy.deepcopy(cls.fragment["instances"]), "selections": []}
        cls.rendered = header.render(cls.data)
        cls.source, cls.expected_sections = check_source(cls.data)
        cls.blocks = {b["name"]: b for b in cls.fragment["types"]}

    def assert_manual_layout(self, fragment):
        self.assertEqual(TYPES, {b["name"] for b in fragment["types"]})
        for block in fragment["types"]:
            typ = block["name"]
            hm = self.hm[typ]
            actual = flat_members(block)
            self.assertEqual(hm["size"], header.number(block["size"]), typ)
            self.assertEqual({v["name"] for v in hm["views"]}, set(actual), typ)
            for view in hm["views"]:
                reg = actual[view["name"]]
                label = typ + "." + view["name"]
                self.assertEqual(view["offset"], reg["offset"], label)
                self.assertEqual(view["width"], reg["width"], label)
                self.assertEqual(view["access"], reg["access"], label)
                fields = reg.get("fields", [])
                manual_fields = hm["field_tables"][view["table"]]
                expected_mask = 0
                for field in manual_fields:
                    # PLSOTIM raw time/count registers have no HM subfield name.
                    if field["symbol"] != "n/a":
                        expected_mask |= mask(field)
                    enclosed = [f for f in fields if field["pos"] <= f["pos"]
                                and f["pos"] + f["bits"] <= field["pos"] + field["bits"]]
                    for f in enclosed:
                        self.assertEqual(field["access"], f["access"], label + "." + f["name"])
                    symbol = re.sub(r"\[.*?\]|\*\d+", "", field["symbol"]).strip()
                    if typ == "R_DOTF_Type" and symbol == "CONVAREAED":
                        symbol = "CONVAREAD"  # Original FSP5.9 vocabulary.
                    if re.fullmatch(r"[A-Za-z_]\w*", symbol):
                        self.assertEqual([symbol], [f["name"] for f in enclosed], label)
                    numbered = re.fullmatch(r"(\w+?)(\d+) to \1(\d+)", symbol)
                    if numbered:
                        first, last = sorted((int(numbered[2]), int(numbered[3])))
                        digits = min(len(numbered[2]), len(numbered[3]))
                        if label == "R_MFWD_Type.FWSEQNRC":
                            digits = 2  # Supplied SVD uses SEQNR00..31; HM omits zero padding.
                        self.assertEqual([numbered[1] + str(i).zfill(digits) for i in range(first, last + 1)],
                                         [f["name"] for f in enclosed], label)
                        for i, f in enumerate(enclosed):
                            self.assertEqual((field["pos"] + i, 1), (f["pos"], f["bits"]), label)
                actual_mask = 0
                for field in fields:
                    self.assertFalse(actual_mask & mask(field), label)
                    actual_mask |= mask(field)
                self.assertEqual(expected_mask, actual_mask, label)

    def test_every_layout_width_field_mask_and_vocabulary_against_frozen_hm(self):
        self.assert_manual_layout(self.fragment)

    def test_automatic_inventory_loading_and_kf_security_aliases(self):
        header.validate(copy.deepcopy(self.merged))
        self.assertTrue(TYPES <= {b["name"] for b in self.merged["types"]})
        self.assertEqual("R7KA8P1KFLCAC", self.fragment["applicability"]["device"])
        self.assertEqual(17, len(self.fragment["instances"]))
        self.assertNotRegex(self.rendered, r"\bR_NPU(?:_|\b)")
        # The independent C fixture checks each numeric base and selected alias.
        self.assertIn("R_DOTF0_Type", self.rendered)
        self.assertNotIn("CONVAREAED_Msk", self.rendered)

    def test_documented_dimensions_not_compact_range_spelling(self):
        dims = {typ: {d["symbol"]: d for d in block["dimensions"]}
                for typ, block in self.hm.items()}
        self.assertEqual({"t": [0, 1]}, dims["R_ESWM_Type"]["TPEMIMC6t"]["dimensions"])
        self.assertEqual(list(range(64)), dims["R_ESWM_Type"]["TPEMIMC7t"]["dimensions"]["t"])
        self.assertEqual({"i": list(range(16)), "j": list(range(7))},
                         dims["R_MFWD_Type"]["FWCFMCij"]["dimensions"])
        self.assertEqual({"i": [0, 1, 2], "j": [0, 1]},
                         dims["R_COMA_Type"]["CABPPPFLCij"]["dimensions"])
        self.assertEqual({"i": [0, 1, 2, 3]}, dims["R_GWCA0_Type"]["GWIDASAMi0"]["dimensions"])
        for typ, spec in self.hm.items():
            actual = flat_members(self.blocks[typ])
            for dim in spec["dimensions"]:
                for name, offset in dim["members"]:
                    self.assertEqual(offset, actual[name]["offset"], typ + "." + name)
                if "array" in dim:
                    reg = next(r for r in self.blocks[typ]["members"] if r["name"] == dim["array"])
                    self.assertEqual(len(dim["members"]), reg["count"])
        gwca = flat_members(self.blocks["R_GWCA0_Type"])
        for register, stem in (("GWTRC1", "TSR"), ("GWDIS1", "DIS"), ("GWEIS21", "DFES")):
            self.assertEqual([stem + str(n) for n in range(32, 64)],
                             [f["name"] for f in gwca[register]["fields"]])

    def test_disputed_sources_are_explicit_and_unsafe_views_withheld(self):
        notes = {n["register"]: n for n in self.fragment["source_discrepancies"]}
        reset = notes["DOTF0/1.CONVAREAD"]
        self.assertEqual((0, 0xFFF), (reset["svd"], reset["hm"]))
        self.assertIn("Unresolved", reset["decision"])
        self.assertIn("0x0C00", notes["GWCA0.GWIDCi"]["hm_list"])
        self.assertIn("0x0C000", notes["GWCA0.GWIDCi"]["hm_description"])
        for typ, names in {
            "R_GWCA0_Type": ["GWIDC", "GWIDC0", "GWIDC63"],
            "R_GPTP_Type": ["PTPSCR0", "PTPSCR1", "PTPSCR2"],
            "R_ESWM_Type": ["TPEMIMC0", "TPEMIMC62"],
            "R_MFWD_Type": ["FWRFC2", "FWRFVC15"],
        }.items():
            actual = flat_members(self.blocks[typ])
            for name in names:
                self.assertNotIn(name, actual)
        for name in ("GSIM0", "RSIM0", "RSIM1"):
            self.assertNotRegex(self.rendered, r"\b" + name + r"\s*:")
        dotf = self.blocks["R_DOTF_Type"]
        self.assertTrue(all("reset" not in key.lower() for r in dotf["members"] for key in r))

    def test_primary_supplied_svd_identity(self):
        path = ROOT / ".embedder/svd-cache/R7KA8P1AD.json"
        if not path.exists():
            self.skipTest("Primary supplied SVD unavailable; frozen HM checks remain independent")
        self.assertEqual(self.fragment["primary_svd"]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        svd = json.loads(path.read_text())
        self.assertEqual(("R7KA8P1AD", "1.10.02"), (svd["name"], svd["version"]))
        # This generic SVD is not the KF applicability oracle: its secure ETHA
        # instances are absent, although the HM documents both aliases.
        names = {p["name"] for p in svd["peripherals"]}
        self.assertIn("ETHA0_NS", names)
        self.assertNotIn("ETHA0", names)
        peripherals = {p["name"]: p for p in svd["peripherals"]}
        groups = (
            ("GPTP", "GPTP_NS"), ("MIPI_CSI0", "MIPI_CSI0_NS"), ("VIN0", "VIN0_NS"),
            ("ECCMB0", "ECCMB1", "ECCMB0_NS", "ECCMB1_NS"), ("MFWD", "MFWD_NS"),
            ("ESWM", "ESWM_NS"), ("COMA", "COMA_NS"), ("ETHA0_NS", "ETHA1_NS"),
            ("RMAC0", "RMAC1", "RMAC0_NS", "RMAC1_NS"), ("GWCA0", "GWCA0_NS"),
            ("DOTF0", "DOTF1", "DOTF0_NS", "DOTF1_NS"), ("PDG", "PDG_NS"),
        )
        for group in groups:
            for name in group[1:]:
                self.assertEqual(peripherals[group[0]]["registers"], peripherals[name]["registers"], name)

    def test_independent_oracle_rejects_offset_width_mask_and_dimension_mutations(self):
        for mutation in ("offset", "width", "field", "count"):
            data = copy.deepcopy(self.fragment)
            reg = data["types"][0]["members"][0]
            if mutation == "offset":
                reg["offset"] = "0x4"
            elif mutation == "width":
                reg["width"] = 16
            elif mutation == "field":
                reg["fields"][0]["bits"] = 31
            else:
                reg = next(r for b in data["types"] for r in b["members"] if "count" in r)
                reg["count"] += 1
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                self.assert_manual_layout(data)

    def test_native_compilation_both_cores_and_security_aliases(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("Native C compiler unavailable")
        with tempfile.TemporaryDirectory(prefix="ra8p1-review-peripherals-native-") as tmp:
            folder = Path(tmp)
            (folder / "R7KA8P1KF.h").write_text(self.rendered)
            for core in (0, 1):
                for nonsecure in (0, 1):
                    result, command, _ = compile_source(
                        compiler, folder, self.source + self.manual_assertions(), core, nonsecure,
                        [FIXTURES, TOOLS / "layout/native", TOOLS / "layout"])
                    self.assertEqual(0, result.returncode, " ".join(command) + "\n" + result.stderr)

    def manual_assertions(self):
        lines = []
        for typ, hm in self.hm.items():
            lines += [f'_Static_assert(sizeof({typ}) == {hm["size"]}, "HM type size");',
                      f'_Static_assert(_Alignof({typ}) == {hm["alignment"]}, "HM type alignment");']
            for view in hm["views"]:
                lines += [f'_Static_assert(offsetof({typ}, {view["name"]}) == {view["offset"]}, "HM offset");',
                          f'_Static_assert(sizeof((({typ} *)0)->{view["name"]}) == {view["width"] // 8}, "HM access width");']
        return "\n".join(lines)

    def test_cm85_cm33_compilation_and_all_bitfield_object_bytes(self):
        compiler = os.environ.get("RA8P1_ARM_CC") or shutil.which("arm-none-eabi-gcc")
        if not compiler:
            self.skipTest("Arm GCC unavailable (set RA8P1_ARM_CC)")
        with tempfile.TemporaryDirectory(prefix="ra8p1-review-peripherals-arm-") as tmp:
            folder = Path(tmp)
            (folder / "R7KA8P1KF.h").write_text(self.rendered)
            cmsis = folder / "cmsis"
            extract_stock_cmsis(cmsis)
            for core in (0, 1):
                cpu, fpu = ("cortex-m85", "fpv5-d16") if core == 0 else ("cortex-m33", "fpv5-sp-d16")
                for nonsecure in (0, 1):
                    result, command, obj = compile_source(
                        compiler, folder, self.source + self.manual_assertions(), core, nonsecure,
                        [FIXTURES, cmsis, TOOLS / "layout"],
                        [f"-mcpu={cpu}", "-mthumb", f"-mfpu={fpu}", "-mfloat-abi=hard"])
                    self.assertEqual(0, result.returncode, " ".join(command) + "\n" + result.stderr)
                    sections = elf_sections(obj)
                    for name, expected in self.expected_sections.items():
                        self.assertEqual(expected, sections[name], (core, nonsecure, name))

    def test_read_only_registers_and_mixed_status_fields_reject_writes(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("Native C compiler unavailable")
        expressions = (
            "R_GPTP->PTPIPV", "R_GPTP->POTCPR3L", "R_MIPI_CSI0->VCST15",
            "R_VIN0->MS", "R_ECCMB1->EC710EAD0", "R_ECCMB0->EC710CTL_b.ECSEDF0",
            "R_MFWD->FWFRPPCN127", "R_MFWD->FWFRPPCN127_E", "R_ESWM->TSIM",
            "R_COMA->CABPPCM", "R_ETHA1->EAMS", "R_ETHA0->EATASC_b.TASCI",
            "R_RMAC1->MPIM", "R_GWCA0->GWMS", "R_GWCA0->GWRDCN_E",
        )
        with tempfile.TemporaryDirectory(prefix="ra8p1-review-peripherals-readonly-") as tmp:
            folder = Path(tmp)
            (folder / "R7KA8P1KF.h").write_text(self.rendered)
            for expr in expressions:
                result, _, _ = compile_source(
                    compiler, folder, '#include "R7KA8P1KF.h"\nvoid rejected(void) { ' + expr + ' = 0; }\n',
                    includes=[TOOLS / "layout/native"])
                self.assertNotEqual(0, result.returncode, expr)
                self.assertRegex(result.stderr, r"read.only|const.qualified", expr)


if __name__ == "__main__":
    unittest.main()
