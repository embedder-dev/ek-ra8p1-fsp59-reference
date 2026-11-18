"""RXIER device-enum controls; live e2 model coverage is recorded separately."""
import io
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "baseline/module_descriptions"
NAME = "Renesas##HAL Drivers##all##r_mipi_dsi####5.9.0.xml"
MDF = DIRECTORY / NAME
HEADERS = ROOT / "baseline/ra/fsp/src/bsp/cmsis/Device/RENESAS/Include"
RXIE = "module.driver.mipi_dsi.rxie"
ENUM = "enum.driver.mipi_dsi.rxie"
RXTE = "R_DSILINK_RXIER_RXTE_Msk"
# HM Rev.1.30 section 66.2.16, pp.3868-3871: implemented RXIER bits.
RXIER_BITS = (0, 1, 2, 8, 10, 14, 15, 16, 17, 18, 20, 21, 22, 23, 24, 25, 26, 28, 30)


def bitmap(options, selected):
    selected = set(selected)
    return "".join(option["value"] + " | " for option in options if option["id"] in selected)


class MipiDsiMetadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current = ET.parse(MDF).getroot()
        with zipfile.ZipFile(ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip") as outer:
            def original(pack_name, name):
                entry = next(x for x in outer.namelist() if x.endswith("/" + pack_name))
                with zipfile.ZipFile(io.BytesIO(outer.read(entry))) as pack:
                    return pack.read(".module_descriptions/" + name)
            cls.stock = ET.fromstring(original("Renesas.RA.5.9.0.pack", NAME))
            cls.stock_family = original("Renesas.RA_mcu_ra8d1.5.9.0.pack",
                                        "Renesas##BSP##ra8d1##fsp####5.9.0.xml")
        cls.prop = cls.current.find(f"./module/property[@id='{RXIE}']")
        cls.stock_prop = cls.stock.find(f"./module/property[@id='{RXIE}']")
        cls.stock_options = [dict(x.attrib) for x in cls.stock_prop.findall("option")]
        cls.enums = {}
        for family in ("ra8p1", "ra8d1"):
            path = DIRECTORY / f"Renesas##BSP##{family}##fsp####5.9.0.xml"
            enumeration = ET.parse(path).find(f"./bsp/enum[@id='{ENUM}']")
            cls.enums[family] = [dict(x.attrib) for x in enumeration.findall("option")]

    def selections(self):
        ids = [x["id"] for x in self.stock_options]
        return ([[], self.stock_prop.attrib["default"].split(",")]
                + [[x] for x in ids]
                + [[y for y in ids if y != x] for x in ids]
                + [ids[::2], ids[1::2], ids[:8], ids[8:], list(reversed(ids)),
                   [RXIE + ".rxte", RXIE + ".extedet"],
                   [RXIE + ".extedet", RXIE + ".btarend", RXIE + ".rxack"]])

    def test_property_default_and_every_legacy_selection_id_are_unchanged(self):
        expected = dict(self.stock_prop.attrib)
        expected["description"] = (
            "Enable receive interrupts. Tearing Effect Trigger Receive (RXTE) has no effect on "
            "hardware where RXIER reserves that bit; External Tearing Effect Detect remains supported.")
        self.assertEqual(self.prop.attrib, expected)
        self.assertEqual([x.tag for x in self.prop], ["select"])
        self.assertEqual(self.prop.find("select").attrib, {"enum": ENUM})
        self.assertEqual(self.enums["ra8d1"], self.stock_options)
        target = [dict(x) for x in self.stock_options]
        next(x for x in target if x["id"] == RXIE + ".rxte")["value"] = "0U"
        self.assertEqual(self.enums["ra8p1"], target)
        self.assertEqual(len(target), 20)

    def test_ra8d1_selected_and_exported_output_matches_stock_for_custom_subsets(self):
        for selected in self.selections():
            with self.subTest(selected=selected):
                self.assertEqual(bitmap(self.enums["ra8d1"], selected),
                                 bitmap(self.stock_options, selected))
                available = {x["id"] for x in self.enums["ra8d1"]}
                self.assertTrue(set(selected) <= available)
        self.assertIn(RXTE, bitmap(self.enums["ra8d1"], self.prop.attrib["default"].split(",")))

    def test_target_changes_only_rxte_and_keeps_external_te(self):
        for selected in self.selections():
            with self.subTest(selected=selected):
                self.assertEqual(bitmap(self.enums["ra8p1"], selected),
                                 bitmap(self.stock_options, selected).replace(RXTE, "0U"))
        self.assertEqual(bitmap(self.enums["ra8p1"], [RXIE + ".rxte"]), "0U | ")
        self.assertEqual(bitmap(self.enums["ra8p1"], [RXIE + ".extedet"]),
                         "R_DSILINK_RXIER_EXTEDET_Msk | ")

    def test_unused_capability_and_ineffective_export_are_absent(self):
        self.assertIsNone(self.prop.find("export"))
        for path in DIRECTORY.glob("*.xml"):
            self.assertNotIn("interface.mcu.mipi_dsi.rxier_no_rxte", path.read_text(), str(path))

    def test_ra8d1_bsp_is_byte_identical_to_release_except_added_enum(self):
        path = DIRECTORY / "Renesas##BSP##ra8d1##fsp####5.9.0.xml"
        current = path.read_bytes()
        pattern = rb'        <enum id="enum.driver.mipi_dsi.rxie" default="">\r\n.*?        </enum>\r\n'
        restored, count = re.subn(pattern, b"", current, flags=re.S)
        self.assertEqual(count, 1)
        self.assertEqual(restored, self.stock_family)

    def test_shared_mdfs_preserve_crlf(self):
        names = [f"Renesas##HAL Drivers##all##{driver}####5.9.0.xml"
                 for driver in ("r_glcdc", "r_mipi_dsi", "r_mipi_phy")]
        names.append("Renesas##BSP##ra8d1##fsp####5.9.0.xml")
        for name in names:
            data = (DIRECTORY / name).read_bytes()
            self.assertGreater(data.count(b"\r\n"), 0, name)
            self.assertNotIn(b"\n", data.replace(b"\r\n", b""), name)

    def test_canonical_target_rxier_masks_match_every_documented_bit(self):
        header = (HEADERS / "R7KA8P1KF.h").read_text()
        masks = dict(re.findall(r"^\s*#define\s+(R_DSILINK_RXIER_\w+_Msk)\s+\((0x[0-9a-fA-F]+)UL\)",
                                header, re.M))
        self.assertNotIn(RXTE, masks)
        self.assertEqual({int(x, 16) for x in masks.values()}, {1 << x for x in RXIER_BITS})
        self.assertEqual(set(masks), {x["value"] for x in self.enums["ra8p1"]} - {"0U"})

    def default_interrupts(self, family):
        result = {}
        for prop in self.current.findall("./module/property"):
            if "bitmapPrefix" not in prop.attrib or not prop.attrib["id"].endswith("ie"):
                continue
            options = self.enums[family] if prop.attrib["id"] == RXIE else [x.attrib for x in prop.findall("option")]
            result[prop.attrib["id"]] = bitmap(options, prop.attrib.get("default", "").split(","))
        return result

    def test_every_default_interrupt_selection_compiles_for_target_and_stock(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("Host C compiler not installed")
        for family, part in (("ra8p1", "R7KA8P1KF.h"), ("ra8d1", "R7FA8D1BH.h")):
            header = (HEADERS / part).read_text()
            definitions = "\n".join(re.findall(r"^\s*#define\s+R_DSILINK_\w+_Msk\s+[^\n]+", header, re.M))
            emitted = self.default_interrupts(family)
            source = definitions + "\n"
            for index, expression in enumerate(emitted.values()):
                source += f"static const unsigned int mask{index} = {expression} 0x0;\n"
            expected = sum(1 << bit for bit in RXIER_BITS)
            if family == "ra8d1":
                expected |= 1 << 13
            source += f'_Static_assert(({emitted[RXIE]} 0x0) == {expected}U, "RXIER mask");\n'
            source += "int main(void) { return " + " + ".join(
                f"(mask{index} == 0U)" for index in range(len(emitted))) + "; }\n"
            with self.subTest(part=part), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "default_masks.c"
                path.write_text(source)
                command = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsyntax-only", str(path)]
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                if family == "ra8p1":
                    original = bitmap(self.stock_options, self.stock_prop.attrib["default"].split(","))
                    path.write_text(definitions + f"\nconst unsigned int invalid = {original} 0x0;\n")
                    negative = subprocess.run(command, capture_output=True, text=True)
                    self.assertNotEqual(negative.returncode, 0)
                    self.assertIn(RXTE, negative.stderr)

    def test_all_other_default_interrupt_macros_exist_in_canonical_target(self):
        header = (HEADERS / "R7KA8P1KF.h").read_text()
        macros = set(re.findall(r"^\s*#define\s+(\w+)", header, re.M))
        referenced = set(re.findall(r"\bR_\w+_Msk\b", " ".join(self.default_interrupts("ra8p1").values())))
        self.assertFalse(referenced - macros)


if __name__ == "__main__":
    unittest.main()
