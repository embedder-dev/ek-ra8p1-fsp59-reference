"""Target-only graphics availability and CANFD topology contracts for R7KA8P1KFLCAC."""
import itertools
import json
import re
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MDFS = ROOT / "baseline/module_descriptions"
PART = MDFS / "Renesas##BSP##ra8p1##device##R7KA8P1KFLCAC##5.9.0.xml"
FAMILY = MDFS / "Renesas##BSP##ra8p1##device####5.9.0.xml"
FSP = MDFS / "Renesas##BSP##ra8p1##fsp####5.9.0.xml"
EVENTS = MDFS / "Renesas##BSP##ra8p1##events####5.9.0.xml"
PINS = ROOT / ".embedder/pin-model/pinmapping/PinCfgR7KA8P1KxxCAC.xml"


def driver(name):
    return ET.parse(MDFS / f"Renesas##HAL Drivers##all##{name}####5.9.0.xml").getroot()


def provides(root):
    return {p.attrib["interface"] for p in root.iter("provides")}


class GraphicsMetadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.part = ET.parse(PART).getroot()
        cls.family = ET.parse(FAMILY).getroot()
        cls.fsp = ET.parse(FSP).getroot()
        cls.pins = ET.parse(PINS).getroot()
        cls.available = provides(cls.part) | provides(cls.family) | provides(cls.fsp)

    def test_physical_glcdc_requirement_and_negative_control(self):
        required = {x.attrib["interface"] for x in driver("r_glcdc").findall("./module/requires")
                    if x.attrib.get("visible") == "false"}
        self.assertEqual(required, {"interface.mcu.glcdc.external"})
        self.assertFalse(required - self.available)
        self.assertEqual(required - (self.available - {"interface.mcu.glcdc.external"}), required)
        self.assertIn("interface.mcu.glcdc.external", provides(self.part))

    def test_physical_dsi_requirement_without_false_feature_set(self):
        external = "interface.mcu.mipi_dsi.external"
        self.assertIn(external, provides(self.part))
        for name in ("r_mipi_phy", "r_mipi_dsi"):
            required = {x.attrib["interface"] for x in driver(name).findall("./module/requires")}
            self.assertIn(external, required, name)
        features = {x for x in provides(self.part) if x.startswith("interface.mcu.feature_set.")}
        self.assertEqual(features, {"interface.mcu.feature_set.k"})
        self.assertIn("#define BSP_MCU_FEATURE_SET ('K')", self.part.find("./config/content").text)
        self.assertEqual(self.part.find("./device").attrib["id"], "R7KA8P1KFLCAC")

    def test_k_package_has_complete_parallel_display_signals(self):
        block = self.pins.find(".//component[@id='glcdc'][@type='peripheral']")
        self.assertIsNotNone(block)
        bonded = {p.attrib["id"] for p in block.findall("./pins/pin")
                  if any(a.attrib.get("type") != "none"
                         for a in p.findall("./configurations/configuration/alt"))}
        expected = {f"glcdc.lcd_data{n}" for n in range(24)}
        expected |= {f"glcdc.lcd_tcon{n}" for n in range(4)}
        expected |= {"glcdc.lcd_clk", "glcdc.lcd_extclk"}
        self.assertEqual(bonded, expected)
        self.assertIsNotNone(block.find(".//alt[@id='glcdc.lcd_clk.p515']"))

    def test_k_package_has_dsi_te_and_dedicated_lanes(self):
        block = self.pins.find(".//component[@id='mipi'][@type='peripheral']")
        self.assertIsNotNone(block)
        te = block.find("./pins/pin[@id='mipi.dsi_te']")
        alts = {a.attrib["id"] for a in te.findall("./configurations/configuration/alt")
                if a.attrib.get("type") != "none"}
        self.assertEqual(alts, {f"mipi.dsi_te.{pin}" for pin in ("p411", "p714", "p804")})
        for pin in ("mipi_cln", "mipi_clp", "mipi_dl0n", "mipi_dl0p", "mipi_dl1n", "mipi_dl1p"):
            self.assertIsNotNone(self.pins.find(f".//component[@id='{pin}'][@type='port']"), pin)

    def test_stock_graphics_enum_and_event_references_are_target_local(self):
        enums = {x.attrib["id"] for root in (self.part, self.family, self.fsp) for x in root.iter("enum")}
        events = {x.attrib["id"] for x in ET.parse(EVENTS).getroot().iter("event")}
        for name in ("r_glcdc", "r_mipi_phy", "r_mipi_dsi"):
            root = driver(name)
            required_enums = {x.attrib["enum"] for x in root.iter("select") if "enum" in x.attrib}
            required_events = {x.attrib["event"] for x in root.iter("interrupt")}
            self.assertFalse(required_enums - enums, name)
            self.assertFalse(required_events - events, name)

    def test_existing_graphics_clock_exports_cover_driver_references(self):
        clocks = self.fsp.find("./bsp/clock")
        expected = {"board.clock.xtal.freq": "board.clock.peripheral.mipimclk",
                    "board.clock.pclka.display": "board.clock.peripheral.mipi_phy",
                    "board.clock.lcdclk.display": "board.clock.peripheral.lcdclk"}
        for node, export in expected.items():
            self.assertIsNotNone(clocks.find(f"./node[@id='{node}']/peripheral[@id='{export}']"))
        supplied = {x.attrib["id"] for x in clocks.iter("peripheral")}
        refs = set()
        for name in ("r_glcdc", "r_mipi_phy", "r_mipi_dsi"):
            refs.update(re.findall(r"\$\{(board\.clock\.peripheral\.[^}]+)\}",
                                  ET.tostring(driver(name), encoding="unicode")))
        self.assertFalse(refs - supplied)
        self.assertEqual(clocks.find("./node[@id='board.clock.lcdclk.source']").attrib["default"],
                         "board.clock.lcdclk.source.disabled")

    def test_canfd_logical_channels_match_two_one_channel_instances(self):
        props = {p.attrib["id"]: p for p in self.fsp.findall("./config/property")}
        prefix = "config.bsp.fsp.mcu.canfd."
        topology = {key: int(props[prefix + key].attrib["default"])
                    for key in ("num_channels", "num_instances", "channels_per_instance")}
        self.assertEqual(topology, {"num_channels": 2, "num_instances": 2, "channels_per_instance": 1})
        self.assertEqual(topology["num_channels"], topology["num_instances"] * topology["channels_per_instance"])
        feature = (ROOT / "baseline/ra/fsp/src/bsp/mcu/ra8p1/bsp_feature.h").read_text()
        for macro, value in (("NUM_CHANNELS", 1), ("NUM_INSTANCES", 2)):
            self.assertRegex(feature, rf"#define BSP_FEATURE_CANFD_{macro}\s+\({value}UL\)")
        self.assertIn("interface.mcu.canfdlite.driver", self.available)
        for channel in (0, 1):
            self.assertIn(f"interface.mcu.canfd.external.{channel}", provides(self.part))

    def test_canfd_limits_preserve_stock_logical_channel_contract(self):
        props = {p.attrib["id"]: p.attrib["default"] for p in self.fsp.findall("./config/property")}
        prefix = "config.bsp.fsp.mcu.canfd."
        expected = {"num_channels": 2, "rx_fifos": 2, "buffer_ram": 1216,
                    "afl_rules": 32, "afl_rules_each_chnl": 16, "max_data_rate_hz": 8}
        self.assertEqual({key: int(props[prefix + key]) for key in expected}, expected)
        limits = driver("r_canfdlite").findall("./module/constraint")
        channel_gate = next(x.text for x in limits if x.attrib.get("display") == "Only Channel 0 is available on this MCU.")
        self.assertIn('${config.bsp.fsp.mcu.canfd.num_channels}" === "2"', channel_gate)
        channel_enum = self.part.find(".//enum[@id='enum.mcu.canfd.external.channels']")
        self.assertEqual({x.attrib["value"] for x in channel_enum.findall("option")}, {"0", "1"})


class SharedGraphicsMetadata(unittest.TestCase):
    def test_glcdc_retains_legacy_and_supplied_model_bindings(self):
        bindings = driver("r_glcdc").findall("./module/peripheral")
        self.assertEqual({x.attrib["component"] for x in bindings}, {"glcdc0", "glcdc"})
        pins = ET.parse(PINS).getroot()
        self.assertIsNotNone(pins.find(".//component[@id='glcdc'][@type='peripheral']"))

    def test_external_hardware_requires_remain_without_feature_set_alias(self):
        for name in ("r_mipi_phy", "r_mipi_dsi"):
            required = {x.attrib["interface"] for x in driver(name).findall("./module/requires")}
            self.assertIn("interface.mcu.mipi_dsi.external", required)
            self.assertNotIn("interface.mcu.feature_set.b", required)
        part = ET.parse(PART).getroot()
        self.assertNotIn("interface.mcu.feature_set.b", provides(part))

    def test_mipi_eligibility_javascript_positive_and_negative_controls(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required to execute MDF JavaScript")
        keys = ("interface.mcu.mipi_dsi.external", "interface.mcu.feature_set.b",
                "interface.mcu.mipi_dsi", "interface.mcu.dphycnt")
        cases = []
        for values in itertools.product((None, "0", "1"), repeat=4):
            supplied = {key: value for key, value in zip(keys, values) if value is not None}
            expected = values[0] == "1" and (values[1] == "1" or values[2:] == ("1", "1"))
            for name in ("r_mipi_phy", "r_mipi_dsi"):
                gate = driver(name).find("./module/constraint[@display='Requires MIPI DSI peripheral']").text
                expr = re.sub(r"\$\{([^}]+)\}", lambda match: supplied.get(match[1], match[0]), gate)
                cases.append({"expression": expr, "expected": expected, "case": [name, values]})
        target = provides(ET.parse(PART).getroot()) | provides(ET.parse(FAMILY).getroot())
        self.assertTrue(all(key in target for key in (keys[0], keys[2], keys[3])))
        script = (
            "const fs = require('fs'); const cases = JSON.parse(fs.readFileSync(0, 'utf8'));"
            "function testExists(value) { return !value.startsWith('${'); }"
            "for (const c of cases) { if (eval(c.expression) !== c.expected) {"
            "throw new Error(JSON.stringify(c)); }}"
        )
        result = subprocess.run([node, "-e", script], input=json.dumps(cases), text=True,
                                capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_legacy_graphics_contracts_against_original_release(self):
        from tools.ra8p1 import regression, stock_regression

        manifests = sorted((ROOT / "validation/ra8p1/packs").glob("r[0-9][0-9][0-9]/manifest.json"))
        self.assertTrue(manifests, "A frozen candidate is required for owning-MDF contract checks")
        historical = json.loads((ROOT / regression.MANIFEST).read_text())
        result = stock_regression.review_metadata(ROOT, historical, manifests[-1])
        proof = result["legacy_selector_proof"]
        self.assertEqual(32, len(proof["devices"]))
        self.assertTrue(proof["dsi_admission_legacy_equivalent"])
        for name in ("r_glcdc", "r_mipi_phy", "r_mipi_dsi"):
            key = f".module_descriptions/Renesas##HAL Drivers##all##{name}####5.9.0.xml"
            self.assertIn(key, result["shared_defaults"])
        # Target behavior has separate numerical/timing and legacy-negative controls.
        from tools.test_ra8p1_review_glcdc_metadata import GlcdcDitherMetadataTests
        GlcdcDitherMetadataTests().test_actual_export_selects_header_enum_for_target_without_changing_legacy()


if __name__ == "__main__":
    unittest.main()
