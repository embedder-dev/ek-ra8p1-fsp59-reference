"""RA8P1 target MDF contracts, derived from HM Rev.1.30 sections 2/8/17/18/54."""
import io
import json
from fractions import Fraction
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MDFS = ROOT / "baseline/module_descriptions"
TARGET = MDFS / "Renesas##BSP##ra8p1##fsp####5.9.0.xml"
DRIVER = MDFS / "Renesas##HAL Drivers##all##r_adc_b####5.9.0.xml"
SECURITY = ("PVDSAR", "DMACSAR", "DTCSAR", "TCMSAR", "TCMSABARC", "TCMSABARS")


class Metadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ET.parse(TARGET).getroot()
        cls.enums = {x.attrib["id"]: x for x in cls.root.iter("enum")}
        cls.properties = {x.attrib["id"]: x for x in cls.root.findall("./config/property")}
        cls.content = cls.root.find("./config/content").text

    def options(self, key):
        return {x.attrib["id"]: x.attrib["value"] for x in self.enums[key].findall("option")}

    def test_all_adc_enums_resolve_in_target_without_other_devices(self):
        refs = {x.attrib["enum"] for x in ET.parse(DRIVER).getroot().iter("select")
                if x.attrib.get("enum", "").startswith(("enum.mcu.adc", "enum.driver.adc"))}
        self.assertEqual(refs - self.enums.keys(), set())
        self.assertEqual(len(refs), 418)
        for key in refs:
            enum = self.enums[key]
            ids = [x.attrib["id"] for x in enum.findall("option")]
            self.assertEqual(len(ids), len(set(ids)), key)
            if enum.attrib.get("default"):
                self.assertIn(enum.attrib["default"], ids, key)

    def test_adc_clock_source_and_divider_encodings(self):
        source = self.options("enum.driver.adc.adc_clock_source")
        self.assertEqual(source, {
            "module.driver.adc.adc_clock_source.adcclk": "(0U)",
            "module.driver.adc.adc_clock_source.gpt": "(1U)",
            "module.driver.adc.adc_clock_source.pclka": "(2U)",
        })
        divider = self.options("enum.driver.adc.adc_clock_divider")
        self.assertEqual(set(divider), {f"module.driver.adc.adc_clock_divider.div_{n}" for n in range(1, 6)})
        for n in range(1, 6):
            self.assertEqual(divider[f"module.driver.adc.adc_clock_divider.div_{n}"], f"ADC_B_CLOCK_DIV_{n}")

    def test_adc_clock_default_is_target_local_and_names_clock_prerequisite(self):
        key = "enum.driver.adc.adc_clock_source"
        enum = self.enums[key]
        self.assertEqual(enum.attrib["default"], "module.driver.adc.adc_clock_source.adcclk")
        option = enum.find("option[@id='" + enum.attrib["default"] + "']")
        self.assertIn("enable on Clocks tab", option.attrib["display"])
        self.assertIn("25-60 MHz", option.attrib["display"])
        self.assertIn("must not exceed PCLKA", option.attrib["display"])
        # RA6T2 is the original 5.9 ADC_B provider; preserve its complete enum, not just its default.
        name = "Renesas##BSP##ra6t2##fsp####5.9.0.xml"
        with zipfile.ZipFile(ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip") as release:
            data = release.read("internal/projectgen/ra/packs/Renesas.RA_mcu_ra6t2.5.9.0.pack")
        with zipfile.ZipFile(io.BytesIO(data)) as pack:
            stock = ET.fromstring(pack.read(".module_descriptions/" + name))
        original = stock.find(".//enum[@id='" + key + "']")
        current = ET.parse(MDFS / name).find(".//enum[@id='" + key + "']")
        self.assertEqual(ET.tostring(current), ET.tostring(original))
        self.assertEqual(current.attrib["default"], "module.driver.adc.adc_clock_source.pclkc")

    def test_physical_and_internal_channel_selections(self):
        internal = {"self_diagnosis": 0x60, "self_diagnosis_unit1": 0x61,
                    "temperature_sensor": 0x64, "internal_reference_voltage": 0x65,
                    "vbatt": 0x66, "da_converter_channel_0": 0x68, "da_converter_channel_1": 0x69}
        internal.update({f"self_diagnosis_sh{n}": 0x70 + n for n in (0, 1, 2, 4, 5, 6)})
        for n in range(37):
            prefix = f"module.driver.adc.virtual_channel_{n}_channel_select."
            options = self.options(f"enum.mcu.adc.virtual_channel_{n}_channel_select")
            expected = {prefix + f"an{ch:03}": f"ADC_CHANNEL_{ch}" for ch in range(23)}
            expected.update({prefix + key: f"(0x{value:02X}U)" for key, value in internal.items()})
            self.assertEqual(options, expected)

    def test_only_33_virtual_channels_can_join_scan_groups(self):
        for n in range(37):
            options = self.options(f"enum.mcu.adc_b.virtual_channel_{n}_scan_groups")
            expected = {"(0)"} if n >= 33 else {f"({g})" for g in range(10)}
            self.assertEqual(set(options.values()), expected)

    def test_gpt_trigger_and_table_completeness(self):
        for n in range(9):
            options = self.options(f"enum.mcu.adc.scan_group_{n}_gpt_trigger_enable_mask")
            self.assertEqual(set(options.values()), {f"ADC_B_GPT_TRIGGER_{side}{ch}" for side in ("A", "B") for ch in range(14)})
        for n in range(33):
            sample = self.options(f"enum.mcu.adc_b.virtual_channel_{n}_sampling_table_id")
            self.assertEqual(set(sample.values()), {f"ADC_B_SAMPLING_STATE_TABLE_{i}" for i in range(16)})
            self.assertEqual(len(self.options(f"enum.mcu.adc_b.virtual_channel_{n}_gain_table")), 9)
            self.assertEqual(len(self.options(f"enum.mcu.adc_b.virtual_channel_{n}_offset_table")), 9)

    def security_source(self, choices=None):
        choices = choices or {}
        def substitute(match):
            prop = self.properties[match[1]]
            option = choices.get(match[1], prop.attrib["default"])
            return next(x.attrib["value"] for x in prop.findall("option") if x.attrib["id"] == option)
        blocks = []
        for suffix in SECURITY:
            macro = "BSP_TZ_CFG_" + suffix
            pattern = r"^#define " + macro + r" [^\n]*(?:\\\n[^\n]*)*"
            # Join continuation lines first so the definition is captured as one logical line.
            logical = self.content.replace("\\\n", " ")
            block = re.search(pattern, logical, re.M)
            self.assertIsNotNone(block, macro)
            blocks.append(re.sub(r"\$\{([^}]+)\}", substitute, block[0]))
        guard = re.search(r"#if \(BSP_TZ_CFG_TCMSAR != 0U\).*?#endif", self.content, re.S)
        self.assertIsNotNone(guard)
        return "\n".join(blocks) + "\n" + guard[0] + "\n"

    def compile_security(self, choices=None, local_secure=False, valid=True, expected=None):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler not installed")
        preamble = (f"#define BSP_TZ_CFG_LVDSAR {0 if local_secure else 3}U\n"
                    f"#define BSP_TZ_CFG_DMACCHSAR {0xFE if local_secure else 0xFF}U\n"
                    f"#define BSP_TZ_CFG_DTC_USED {1 if local_secure else 0}U\n")
        source = preamble + self.security_source(choices)
        for suffix, value in (expected or {}).items():
            source += f'_Static_assert(BSP_TZ_CFG_{suffix} == {value}U, "{suffix}");\n'
        source += "int main(void) { return 0; }\n"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "security.c"
            path.write_text(source)
            result = subprocess.run([compiler, "-std=c11", "-Wall", "-Werror", "-fsyntax-only", str(path)], capture_output=True, text=True)
        if valid:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("TCM", result.stderr)

    def test_security_defaults_and_local_secure_ownership(self):
        self.compile_security(expected={"PVDSAR": 3, "DMACSAR": 1, "DTCSAR": 1,
                                        "TCMSAR": 0, "TCMSABARC": 65536, "TCMSABARS": 65536})
        self.compile_security(local_secure=True, expected={"PVDSAR": 0, "DMACSAR": 0, "DTCSAR": 0})

    def test_explicit_secondary_controller_ownership(self):
        choices = {f"config.bsp.fsp.tz.{kind}.cpu1": f"config.bsp.fsp.tz.{kind}.cpu1.nonsecure" for kind in ("dmacsar", "dtcsar")}
        self.compile_security(choices, expected={"DMACSAR": 0x10001, "DTCSAR": 0x10001})

    def test_tcm_boundary_values_and_invalid_nonsecure_control(self):
        for kind in ("tcmsabarc", "tcmsabars"):
            prop = self.properties["config.bsp.fsp.tz." + kind]
            values = {int(x.attrib["value"].rstrip("U"), 0) for x in prop.findall("option")}
            self.assertEqual(values, set(range(0, 0x10001, 0x2000)))
        choice = {"config.bsp.fsp.tz.tcmsar": "config.bsp.fsp.tz.tcmsar.nonsecure"}
        self.compile_security(choice, valid=False)
        choice.update({f"config.bsp.fsp.tz.{kind}": f"config.bsp.fsp.tz.{kind}.0" for kind in ("tcmsabarc", "tcmsabars")})
        self.compile_security(choice, expected={"TCMSAR": 1, "TCMSABARC": 0, "TCMSABARS": 0})


class ClockMetadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ET.parse(TARGET).getroot()
        cls.clock = cls.root.find("./bsp/clock")
        cls.nodes = {x.attrib["id"]: x for x in cls.clock.findall("node")}

    def selected(self, key, changes=None):
        node = self.nodes[key]
        choice = (changes or {}).get(key, node.attrib.get("default"))
        options = node.findall("option")
        if choice is None:
            choice = options[0].attrib["id"]
        return choice, next((x for x in options if x.attrib["id"] == choice), options[0])

    def frequency(self, key, changes=None):
        choice, option = self.selected(key, changes)
        if str(choice).isdigit():
            return Fraction(int(choice))
        source = option.attrib.get("input")
        base = self.frequency(source, changes) if source and source != "0" else Fraction(0 if source == "0" else 1)
        return base * Fraction(option.attrib.get("mul", "1")) / Fraction(option.attrib.get("div", "1"))

    def evaluate(self, cases):
        node = shutil.which("node")
        if not node:
            self.skipTest("JavaScript runtime not installed")
        script = "const expressions = JSON.parse(require('fs').readFileSync(0, 'utf8')); process.stdout.write(JSON.stringify(expressions.map(x => Boolean(eval(x)))));"
        result = subprocess.run([node, "-e", script], input=json.dumps(cases), capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def expression(self, constraint, changes=None, values=None):
        values = values or {}
        def substitute(match):
            key = match[1]
            if key.startswith("value:"):
                key = key[6:]
                return str(float(values[key] if key in values else self.frequency(key, changes)))
            return str(self.selected(key, changes)[0])
        return re.sub(r"\$\{([^}]+)\}", substitute, constraint.text)

    def test_independent_mcu_defaults_match_board_and_all_clock_constraints(self):
        board = ET.parse(MDFS / "Renesas##BSP##Board##ra8p1_ek####5.9.0##configuration.xml").getroot()
        for entry in board.findall("./raClockConfiguration/node"):
            expected = entry.attrib.get("mul") if entry.attrib["option"] == "_edit" else entry.attrib["option"]
            self.assertEqual(self.nodes[entry.attrib["id"]].attrib["default"], expected)
        constraints = self.clock.findall("constraint")
        results = self.evaluate([self.expression(c) for c in constraints])
        self.assertEqual([c.attrib["display"] for c, valid in zip(constraints, results) if not valid], [])
        for clock in ("cpuclk", "cpuclk1", "mriclk", "iclk"):
            self.assertEqual(self.frequency(f"board.clock.{clock}.display"), 24000000)
        self.assertEqual(self.frequency("board.clock.pll.display"), 960000000)

    def adc_clock_constraint(self, source, divider=1, changes=None, values=None):
        constraint = next(c for c in ET.parse(DRIVER).findall("./module/constraint")
                          if c.attrib["display"] == "The ADC clock frequency must be between 25 MHz to 60 MHz.")
        values = values or {}
        def substitute(match):
            key = match[1]
            if key == "module.driver.adc.adc_clock_source":
                return "module.driver.adc.adc_clock_source." + source
            if key == "module.driver.adc.adc_clock_divider":
                return "module.driver.adc.adc_clock_divider.div_" + str(divider)
            if key in values:
                return str(values[key])
            clock = next(node.attrib["id"] for node in self.nodes.values()
                         if node.find("peripheral[@id='" + key + "']") is not None)
            return str(float(self.frequency(clock, changes)))
        return re.sub(r"\$\{([^}]+)\}", substitute, constraint.text)

    def test_adc_default_rejects_disabled_clock_and_hoco_recipe_clears_requirement(self):
        source = self.nodes["board.clock.adcclk.source"]
        self.assertEqual(source.attrib["default"], "board.clock.adcclk.source.disabled")
        self.assertIn("ADC_B defaults to ADCCLK", source.attrib["tooltip"])
        self.assertEqual(self.frequency("board.clock.adcclk.display"), 0)
        self.assertLess(self.frequency("board.clock.pclka.display"), 25000000)
        recipe = {"board.clock.hoco.freq": "board.clock.hoco.freq.48m",
                  "board.clock.pll1p.div": "board.clock.pll1p.div.8",
                  "board.clock.clock.source": "board.clock.clock.source.pll1p",
                  "board.clock.pclka.div": "board.clock.pclka.div.2",
                  "board.clock.adcclk.source": "board.clock.adcclk.source.hoco"}
        self.assertEqual(self.frequency("board.clock.pclka.display", recipe), 60000000)
        self.assertEqual(self.frequency("board.clock.adcclk.display", recipe), 48000000)
        self.assertGreaterEqual(self.frequency("board.clock.pclka.display", recipe),
                                self.frequency("board.clock.adcclk.display", recipe))
        self.assertEqual(self.frequency("board.clock.adcclk.div", recipe), 48000000)
        self.assertEqual(self.evaluate([self.adc_clock_constraint("adcclk"),
                                        self.adc_clock_constraint("pclka"),
                                        self.adc_clock_constraint("adcclk", changes=recipe),
                                        self.adc_clock_constraint("adcclk", divider=2, changes=recipe)]),
                         [False, False, True, False])
        for divider in range(1, 6):
            expressions, expected = [], []
            for clock, valid in ((0, False), (24999999, False), (25000000, True),
                                 (48000000, True), (60000000, True), (60000001, False)):
                expressions.append(self.adc_clock_constraint("adcclk", divider=divider,
                                   values={"board.clock.peripheral.adcclk": clock * divider}))
                expected.append(valid)
            self.assertEqual(self.evaluate(expressions), expected)
        self.assertTrue(all(self.evaluate([self.expression(c, recipe)
                                          for c in self.clock.findall("constraint")])))

    def test_async_clock_contract_and_documented_register_encodings(self):
        expected = {1: 0, 2: 1, 4: 2, 6: 3, 8: 4, 10: 7, 16: 8, 32: 9}
        for domain, source_max, output_max in (("bclka", 800000000, 133000000), ("eswclk", 1000000000, 250000000), ("eswphyclk", 1000000000, 500000000)):
            source = self.nodes[f"board.clock.{domain}.source"]
            self.assertEqual(source.attrib["default"], f"board.clock.{domain}.source.moco")
            self.assertEqual({x.attrib["id"].rsplit(".", 1)[1] for x in source}, {"moco", "pll1p", "pll1q", "pll1r", "pll2p", "pll2q", "pll2r"})
            for option in source:
                self.assertEqual(option.attrib["macroName"], f"BSP_CFG_{domain.upper()}_SOURCE")
                self.assertEqual(int(option.attrib["maxValue"]), source_max)
            divider = self.nodes[f"board.clock.{domain}.div"]
            actual = {int(x.attrib["div"]): int(x.attrib["macroValue"].strip("()U")) for x in divider}
            self.assertEqual(actual, expected)
            display = self.nodes[f"board.clock.{domain}.display"].find("option")
            self.assertEqual(display.attrib["macroName"], f"BSP_CFG_{domain.upper()}_FREQUENCY_HZ")
            self.assertEqual(int(display.attrib["maxValue"]), output_max)
            self.assertEqual(self.frequency(f"board.clock.{domain}.display"), 8000000)
        self.assertFalse(any("ethphyclk" in key for key in self.nodes))

    def test_bus_outputs_follow_synchronous_or_asynchronous_selection(self):
        for async_enabled, expected in ((False, 24000000), (True, 8000000)):
            changes = {"board.clock.bclk.async": "board.clock.bclk.async." + ("asynchronous" if async_enabled else "synchronous"),
                       "board.clock.sdclkout.enable": "board.clock.sdclkout.enable.enabled",
                       "board.clock.bclkout.div": "board.clock.bclkout.div.2"}
            self.assertEqual(self.frequency("board.clock.sdclkout.display", changes), expected)
            self.assertEqual(self.frequency("board.clock.bclkout.display", changes), expected / 2)
            _, selection = self.selected("board.clock.bclk.async", changes)
            self.assertEqual(selection.attrib["macroName"], "BSP_CFG_BCLK_ASYNC")
            self.assertEqual(selection.attrib["macroValue"], "(1U)" if async_enabled else "(0U)")

    def test_every_system_field_participates_in_24_family_exclusion(self):
        constraint = next(x for x in self.clock.findall("constraint") if "If using /3" in x.attrib["display"])
        fields = ("cpuclk", "cpuclk1", "npuclk", "mriclk", "iclk", "fclk", "bclk", "pclka", "pclkb", "pclkc", "pclkd", "pclke")
        cases, expected = [], []
        base = {f"board.clock.{field}.div": f"board.clock.{field}.div.1" for field in fields}
        for first in fields:
            for second in fields:
                if first == second:
                    continue
                for three, two in ((3, 2), (6, 4), (12, 8), (24, 16), (24, 32), (24, 64)):
                    changes = dict(base, **{f"board.clock.{first}.div": f"board.clock.{first}.div.{three}",
                                          f"board.clock.{second}.div": f"board.clock.{second}.div.{two}"})
                    cases.append(self.expression(constraint, changes))
                    expected.append(False)
        for divisor in (1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 64):
            changes = {f"board.clock.{field}.div": f"board.clock.{field}.div.{divisor}" for field in fields}
            cases.append(self.expression(constraint, changes))
            expected.append(True)
        self.assertEqual(self.evaluate(cases), expected)

    def test_each_system_ratio_accepts_boundaries_and_rejects_invalid_values(self):
        constraints = [c for c in self.clock.findall("constraint") if "integer N from 1 to 64" in c.attrib["display"]]
        self.assertEqual(len(constraints), 14)
        cases, expected = [], []
        for constraint in constraints:
            comparison = re.search(r"\(\$\{value:([^}]+)\}\s*>=\s*\$\{value:([^}]+)\}\)", constraint.text)
            self.assertIsNotNone(comparison)
            a, b = comparison.groups()
            bidirectional = "or 1:N" in constraint.attrib["display"]
            for av, bv, valid in ((100, 100, True), (640, 10, True), (100, 30, False), (650, 10, False), (10, 20, bidirectional)):
                cases.append(self.expression(constraint, values={a: av, b: bv}))
                expected.append(valid)
        self.assertEqual(self.evaluate(cases), expected)


if __name__ == "__main__":
    unittest.main()
