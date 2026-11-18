"""Independent ADC-007/009/016/017/019/020 manual admission oracles.

No IDE, packs or target operations. The production C executes with the actual
candidate register layout; MDF exports execute in Node after value substitution.
"""
import io
import itertools
import json
import zipfile
from pathlib import Path
import re
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET

from test_ra8p1_review_adc_mmio import ROOT, SOURCE, FSP, prepare, run

FIXTURE = ROOT / "tools/ra8p1/review_adc_admission"
MDF = ROOT / "baseline/module_descriptions/Renesas##HAL Drivers##all##r_adc_b####5.9.0.xml"


def flags(tmp, checking, core):
    result = prepare(tmp, checking)
    (tmp / "bsp_api.h").write_text('#include "' + str(FIXTURE / "fixture_bsp.h") + '"\n')
    result += ['-DREVIEW_SOURCE="' + str(SOURCE) + '"', '-DBSP_CFG_CPU_CORE=' + str(core)]
    if "low_voltage" in (FSP / "inc/instances/r_adc_b.h").read_text():
        result += ["-DREVIEW_LOW_VOLTAGE"]
    return result


class AdcAdmissionC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="review-adc-admission-")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.binaries = []
        for core, checking in itertools.product((0, 1), repeat=2):
            tmp = Path(cls.directory.name) / f"{core}-{checking}"
            tmp.mkdir()
            binary = tmp / "fixture"
            run([shutil.which("cc"), *flags(tmp, checking, core), "-O2", "-fsanitize=undefined",
                 "-fno-sanitize-recover=all", FIXTURE / "fixture.c", "-o", binary])
            cls.binaries.append(binary)

    def case(self, *args):
        for binary in self.binaries:
            with self.subTest(build=binary.parent.name, args=args):
                self.assertIn("ADC admission oracle passed", run([binary, *map(str, args)]))

    def test_overflow_never_resets_fifo_even_if_callback_restarts(self):
        for args in itertools.product((0, 1, 2, 3, 0x10000), (0, 1), (0, 1)):
            self.case("fifo", *args)

    def test_successive_approximation_real_clock_boundaries(self):
        for hz, cycles, low in itertools.product((25000000, 50000000, 60000000), range(3, 14), (0, 1)):
            self.case("timing", hz, cycles, cycles, low)
        self.case("timing", 60000000, 6, 7, 0)
        self.case("timing", 24000000, 4, 4, 0)
        self.case("timing", 61000000, 7, 7, 0)
        for source, divider, hz, cycles, low in itertools.product(
                range(3), range(5), (60000000, 120000000), (5, 6, 8, 10, 12), (0, 1)):
            self.case("timing", hz, cycles, cycles, low, source, divider)
        self.case("timing", 60000000, 6, 6, 0, 3, 0)
        self.case("timing", 300000000, 6, 6, 0, 0, 5)

    def test_scoped_production_files_keep_crlf(self):
        for path in (SOURCE, FSP / "inc/instances/r_adc_b.h", MDF):
            data = path.read_bytes()
            self.assertGreater(data.count(b"\r\n"), 0)
            self.assertEqual(data.count(b"\r\n"), data.count(b"\n"), str(path))

    def test_source_mode_and_sign_matrix_precedes_any_configuration_write(self):
        for channel, unit, diff, unsigned in itertools.product(
                (*range(23), 96, 97, 98, 100, 101, 102, 104, 105, 112, 113, 114, 115, 116, 117, 118),
                (0, 1), (0, 1), (0, 1)):
            self.case("source", channel, unit, diff, unsigned)

    def test_shared_sources_reject_concurrent_but_allow_sequential_reuse(self):
        for args in itertools.product((*range(16, 23), 100, 101, 102, 104, 105), (0, 1), (0, 1), (0, 1), (0, 1)):
            self.case("overlap", *args)


class AdcAdmissionMdf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if not cls.node:
            raise unittest.SkipTest("Node unavailable")
        cls.root = ET.fromstring(MDF.read_text())

    def evaluate_many(self, cases):
        expressions = [re.sub(r"\$\{([^}]+)\}", lambda m: str(values.get(m[1], "missing")), expression)
                       for expression, values in cases]
        program = ('function testExists(x) { return x !== "missing"; }\n'
                   'const expressions = JSON.parse(require("fs").readFileSync(0,"utf8"));\n'
                   'console.log(JSON.stringify(expressions.map(expression => eval(expression))));')
        return json.loads(run([self.node, "-e", program], input=json.dumps(expressions)))

    def evaluate(self, expression, values):
        return self.evaluate_many([(expression, values)])[0]

    def exports(self, vc, field, values):
        prop = self.root.find(f'.//property[@id="module.driver.adc.virtual_channel_{vc}_{field}"]/export')
        return self.evaluate(prop.text.strip(), values)

    def test_all_diagnosis_values_force_differential_and_signed_for_every_vc(self):
        for vc in range(33):
            prefix = f"module.driver.adc.virtual_channel_{vc}_"
            for channel in (96, 97, 112, 113, 114, 116, 117, 118):
                values = {"interface.mcu.adc_b.adc16h": 1, prefix + "channel_select": f"(0x{channel:X}U)",
                          prefix + "input_mode_selection": 0, prefix + "data_is_unsigned": 1,
                          prefix + "scan_group": 9,
                          "module.driver.adc.adc_0_method": "ADC_B_CONVERSION_METHOD_SAR",
                          "module.driver.adc.adc_1_method": "ADC_B_CONVERSION_METHOD_SAR"}
                self.assertEqual("1", self.exports(vc, "input_mode", values))
                self.assertFalse(self.exports(vc, "data_sign_setting", values))

    def test_group_none_and_all_nine_groups_and_input_mode_sign(self):
        for vc in (0, 16, 32):
            prefix = f"module.driver.adc.virtual_channel_{vc}_"
            for group, unit, diff in itertools.product(range(10), (0, 1), (0, 1)):
                values = {"interface.mcu.adc_b.adc16h": 1, prefix + "channel_select": 0,
                          prefix + "scan_group": f"({group})", prefix + "input_mode_selection": diff,
                          prefix + "data_is_unsigned": diff,
                          "module.driver.adc.adc_0_method": "ADC_B_CONVERSION_METHOD_SAR",
                          "module.driver.adc.adc_1_method": "ADC_B_CONVERSION_METHOD_OVERSAMPLE"}
                for i in range(9):
                    values[f"module.driver.adc.scan_group_{i}_converter_selection"] = unit if i + 1 == group else 1 - unit
                self.assertEqual(not diff, self.exports(vc, "data_sign_setting", values))

    def test_actual_target_enum_values_and_group_offset_exports(self):
        bsp = ET.parse(ROOT / "baseline/module_descriptions/Renesas##BSP##ra8p1##fsp####5.9.0.xml")
        cases, expected = [], []
        for vc in range(33):
            prefix = f"module.driver.adc.virtual_channel_{vc}_"
            enum = bsp.find(f'.//enum[@id="enum.mcu.adc_b.virtual_channel_{vc}_scan_groups"]')
            expression = self.root.find(f'.//property[@id="{prefix}data_sign_setting"]/export').text.strip()
            group_flags = "[" + ",".join(f"group_{group}_selected" for group in range(9)) + "]"
            self.assertIn("'output')", expression)
            expression = expression.replace("'output')", "'" + group_flags + "')")
            for encoded, option in enumerate(enum.findall("option")):
                cases.append((expression, {"interface.mcu.adc_b.adc16h": 1,
                                          prefix + "scan_group": option.get("value"),
                                          prefix + "data_is_unsigned": 1}))
                expected.append([encoded == group + 1 for group in range(9)])
        self.assertEqual(expected, self.evaluate_many(cases))

    def test_legacy_exports_preserve_stock_59_value_semantics(self):
        with zipfile.ZipFile(ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip") as release:
            data = release.read("internal/projectgen/ra/packs/Renesas.RA.5.9.0.pack")
        with zipfile.ZipFile(io.BytesIO(data)) as pack:
            stock = ET.fromstring(pack.read(".module_descriptions/" + MDF.name))
        cases = []
        for vc, field, channel, group, diff, unsigned in itertools.product(
                range(37), ("input_mode", "data_sign_setting"),
                ("ADC_CHANNEL_0", "ADC_CHANNEL_SELF_DIAGNOSIS"), ("(0)", "(1)", "(8)", "(9)"), (0, 1), (0, 1)):
            prefix = f"module.driver.adc.virtual_channel_{vc}_"
            values = {prefix + "channel_select": channel, prefix + "scan_group": group,
                      prefix + "input_mode_selection": diff, prefix + "data_is_unsigned": unsigned,
                      "module.driver.adc.adc_0_method": "ADC_B_CONVERSION_METHOD_SAR",
                      "module.driver.adc.adc_1_method": "ADC_B_CONVERSION_METHOD_OVERSAMPLE"}
            for i in range(9):
                values[f"module.driver.adc.scan_group_{i}_converter_selection"] = i % 2
            for root in (stock, self.root):
                expression = root.find(f'.//property[@id="{prefix}{field}"]/export').text.strip()
                cases.append((expression, values))
        actual = self.evaluate_many(cases)
        self.assertEqual(actual[::2], actual[1::2])

    def test_clock_voltage_and_equal_unit_constraints(self):
        constraints = [node for node in self.root.findall("module/constraint")
                       if "successive approximation" in node.get("display", "").lower() and "ADC16H" in node.get("display", "")]
        self.assertTrue(constraints)
        for hz, cycles, low in itertools.product((25000000, 50000000, 60000000), range(3, 14), (0, 1)):
            values = {"interface.mcu.adc_b.adc16h": 1, "board.clock.peripheral.adcclk": hz,
                      "module.driver.adc.adc_clock_source": "module.driver.adc.adc_clock_source.adcclk",
                      "module.driver.adc.adc_clock_divider": "module.driver.adc.adc_clock_divider.div_1",
                      "module.driver.adc.adc_0_conversion_state": cycles, "module.driver.adc.adc_1_conversion_state": cycles,
                      "module.driver.adc.low_voltage": "module.driver.adc.low_voltage." + ("enabled" if low else "disabled")}
            expected = cycles * 1000000000 >= hz * (200 if low else 100) and cycles * 1000000000 <= hz * 200
            actual = all(self.evaluate(c.text, values) for c in constraints)
            self.assertEqual(expected, actual, values)
            values["module.driver.adc.adc_1_conversion_state"] = cycles + 1
            self.assertFalse(all(self.evaluate(c.text, values) for c in constraints))


if __name__ == "__main__":
    unittest.main()
