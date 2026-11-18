"""ADC16H MDF oracles from HM54.2.3, 54.2.6, 54.3.16.6 and 54.11.16.

Exports receive option values; constraints receive option ids, as in FSP5.9.
No IDE, installation, generated project, driver or fixture changes are required.
"""
import io
import itertools
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MDF = ROOT / "baseline/module_descriptions/Renesas##HAL Drivers##all##r_adc_b####5.9.0.xml"
CAP = "interface.mcu.adc_b.adc16h"
P = "module.driver.adc."
DIAGNOSIS = (0x60, 0x61, 0x70, 0x71, 0x72, 0x74, 0x75, 0x76)
ADMISSION = "ADC16H scan assignments must satisfy channel count, filter, source and S&H restrictions."


class AdcMetadataReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if cls.node is None:
            raise unittest.SkipTest("Node is required to execute MDF JavaScript")
        cls.module = ET.parse(MDF).find("module")
        cls.bsp = ET.parse(ROOT / "baseline/module_descriptions/Renesas##BSP##ra8p1##fsp####5.9.0.xml")
        with zipfile.ZipFile(ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip") as release:
            data = release.read("internal/projectgen/ra/packs/Renesas.RA.5.9.0.pack")
        with zipfile.ZipFile(io.BytesIO(data)) as pack:
            cls.stock = ET.fromstring(pack.read(".module_descriptions/" + MDF.name)).find("module")

    def evaluate(self, cases):
        expressions = [re.sub(r"\$\{([^}]+)\}", lambda m: str(values.get(m[1], "missing")), expression)
                       for expression, values in cases]
        script = ('function testExists(x) { return x !== "missing"; }\n'
                  'console.log(JSON.stringify(JSON.parse(require("fs").readFileSync(0,"utf8"))'
                  '.map(expression => eval(expression))));')
        result = subprocess.run([self.node, "-e", script], input=json.dumps(expressions),
                                capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def export(self, vc, field, module=None):
        if module is None:
            module = self.module
        return module.find(f'property[@id="{P}virtual_channel_{vc}_{field}"]/export').text.strip()

    def defaults(self):
        return {CAP: 1, **{prop.get("id"): prop.get("default", "")
                         for prop in self.module.findall("property")}}

    def assign(self, values, vc, group, channel, differential=False, digital_filter=None):
        prefix = P + f"virtual_channel_{vc}_"
        values[prefix + "scan_group"] = prefix + f"scan_group.scan_group_{group}"
        suffix = f"an{channel:03}" if isinstance(channel, int) else channel
        values[prefix + "channel_select"] = prefix + "channel_select." + suffix
        values[prefix + "input_mode_selection"] = (f"enum.mcu.adc_b.virtual_channel_{vc}_input_mode." +
                                                    ("differential" if differential else "single_ended"))
        if digital_filter is not None:
            values[prefix + "digital_filter_id"] = prefix + f"digital_filter_id.digital_filter_table_entry_{digital_filter}"

    def admission(self):
        node = self.module.find(f'constraint[@display="{ADMISSION}"]')
        self.assertIsNotNone(node, "Missing target scan-assignment admission constraint")
        return node.text

    def test_numeric_diagnosis_exports_and_neighboring_non_diagnosis_values_all_vcs(self):
        cases, expected = [], []
        for vc, channel, differential, unsigned in itertools.product(
                range(33), (*DIAGNOSIS, 0x64, 0x65, 0x66, 0x68, 0x69, 0x62, 0x73, 0x77), (0, 1), (0, 1)):
            prefix = P + f"virtual_channel_{vc}_"
            values = {CAP: 1, prefix + "channel_select": f"(0x{channel:02X}U)",
                      prefix + "input_mode_selection": differential, prefix + "data_is_unsigned": unsigned}
            cases += [(self.export(vc, "input_mode"), values),
                      (self.export(vc, "data_sign_setting"), values)]
            expected += [str(int(channel in DIAGNOSIS or differential != 0)),
                         not (channel in DIAGNOSIS or differential != 0)]
        self.assertEqual(expected, self.evaluate(cases))

    def test_hm_group_none_zero_and_group_zero_through_eight_one_through_nine(self):
        cases, expected = [], []
        for vc in range(33):
            prefix = P + f"virtual_channel_{vc}_"
            enum = self.bsp.find(f'.//enum[@id="enum.mcu.adc_b.virtual_channel_{vc}_scan_groups"]')
            options = enum.findall("option")
            self.assertEqual([f"({i})" for i in range(10)], [option.get("value") for option in options])
            expression = self.export(vc, "data_sign_setting")
            # Inspect the actual export's decoded group/unit state, not a reimplementation.
            result = "[" + ",".join(f"group_{g}_selected" for g in range(9)) + ",selected_group_is_unit_0,selected_group_is_unit_1]"
            self.assertEqual(1, expression.count("'output')"))
            expression = expression.replace("'output')", "'" + result + "')")
            for encoded, unit in itertools.product(range(10), (0, 1)):
                values = {CAP: 1, prefix + "scan_group": options[encoded].get("value"),
                          prefix + "data_is_unsigned": 1}
                for group in range(9):
                    values[P + f"scan_group_{group}_converter_selection"] = f"({unit if group + 1 == encoded else 1 - unit})"
                cases.append((expression, values))
                expected.append([encoded == g + 1 for g in range(9)] +
                                [encoded != 0 and unit == 0, encoded != 0 and unit == 1])
        self.assertEqual(expected, self.evaluate(cases))

    def test_legacy_hidden_exports_emit_stock_values_for_all_37_virtual_channels(self):
        cases = []
        for vc, field, channel, group, differential, unsigned in itertools.product(
                range(37), ("input_mode", "data_sign_setting"),
                ("ADC_CHANNEL_0", "ADC_CHANNEL_SELF_DIAGNOSIS"), range(10), (0, 1), (0, 1)):
            prefix = P + f"virtual_channel_{vc}_"
            values = {prefix + "channel_select": channel, prefix + "scan_group": f"({group})",
                      prefix + "input_mode_selection": differential, prefix + "data_is_unsigned": unsigned,
                      P + "adc_0_method": "ADC_B_CONVERSION_METHOD_SAR",
                      P + "adc_1_method": "ADC_B_CONVERSION_METHOD_HYBRID"}
            for g in range(9):
                values[P + f"scan_group_{g}_converter_selection"] = f"({g % 2})"
            for module in (self.stock, self.module):
                cases.append((self.export(vc, field, module), values))
        results = self.evaluate(cases)
        self.assertEqual(results[::2], results[1::2])

    def test_hybrid_two_to_four_channels_mandatory_exclusive_filters_both_units_all_groups(self):
        expression = self.admission()
        cases, expected = [], []
        for group, unit, count in itertools.product(range(9), (0, 1), range(1, 6)):
            values = self.defaults()
            values[P + f"scan_group_{group}_converter_selection"] = P + f"scan_group_{group}_converter_selection.adc_{unit}"
            values[P + f"adc_{unit}_method"] = P + f"adc_{unit}_method.hybrid_mode"
            for vc in range(count):
                self.assign(values, vc, group, 16 + vc, digital_filter=vc % 4 + 1)
            cases.append((expression, values))
            expected.append(2 <= count <= 4)
        for unit, filters in itertools.product((0, 1), ((None, 2), (1, 1), (1, 2))):
            values = self.defaults()
            values[P + "scan_group_8_converter_selection"] = P + f"scan_group_8_converter_selection.adc_{unit}"
            values[P + f"adc_{unit}_method"] = P + f"adc_{unit}_method.hybrid_mode"
            for vc, digital_filter in enumerate(filters):
                self.assign(values, vc, 8, 16 + vc, digital_filter=digital_filter)
            cases.append((expression, values))
            expected.append(filters == (1, 2))
        self.assertEqual(expected, self.evaluate(cases))

    def test_minimum_phase_is_rejected_only_for_target_all_eight_filter_properties(self):
        constraints = [n for n in self.module.findall("constraint")
                       if "ADC16H digital filter" in n.get("display", "")]
        self.assertEqual(8, len(constraints))
        cases, expected = [], []
        for unit, entry, target, minimum_phase in itertools.product((0, 1), range(1, 5), (False, True), (False, True)):
            values = self.defaults()
            if not target:
                del values[CAP]
            key = P + f"digital_filter_adc{unit}_selection_{entry}"
            values[key] = key + (".minimum_phase_filter" if minimum_phase else ".sinc_filter")
            expression = next(n.text for n in constraints if key in n.text)
            cases.append((expression, values))
            expected.append(not target or not minimum_phase)
        self.assertEqual(expected, self.evaluate(cases))

    def test_sample_hold_order_circuit_reuse_modes_and_sequential_groups(self):
        expression = self.admission()
        cases, expected = [], []
        for unit, ordered, duplicate, method, mode in itertools.product(
                (0, 1), (False, True), (False, True), ("sar_mode", "oversampling_mode", "hybrid_mode"),
                ("single_scan", "continuous_scan", "background_continuous_scan")):
            values = self.defaults()
            values[P + "scan_group_8_converter_selection"] = P + f"scan_group_8_converter_selection.adc_{unit}"
            values[P + f"adc_{unit}_method"] = P + f"adc_{unit}_method.{method}"
            values[P + f"adc_{unit}_mode"] = P + f"adc_{unit}_mode.{mode}"
            values[P + "sample_and_hold_enable_mask"] = P + f"sample_and_hold_enable_mask.unit_{4 if unit else 0}"
            channels = (unit * 6, unit * 6 + 1) if duplicate else ((unit * 6, 16) if ordered else (16, unit * 6))
            for vc, channel in zip((0, 32), channels):
                self.assign(values, vc, 8, channel, digital_filter=vc % 3 + 1 if method == "hybrid_mode" else None)
            cases.append((expression, values))
            expected.append(ordered and not duplicate and
                            (method == "hybrid_mode" or (method == "sar_mode" and mode == "single_scan")))
        # Same S&H circuit reused in two separately scanned groups remains supported.
        values = self.defaults()
        values[P + "sample_and_hold_enable_mask"] = P + "sample_and_hold_enable_mask.unit_0"
        self.assign(values, 0, 0, 0)
        self.assign(values, 32, 8, 0)
        cases.append((expression, values))
        expected.append(True)
        self.assertEqual(expected, self.evaluate(cases))

    def test_hm_source_unit_and_differential_matrix_uses_real_option_ids(self):
        expression = self.admission()
        enum = self.bsp.find('.//enum[@id="enum.mcu.adc.virtual_channel_32_channel_select"]')
        cases, expected = [], []
        unit0 = {0, 1, 2, 3, 4, 5, 12, 14, 96, 112, 113, 114}
        unit1 = {6, 7, 8, 9, 10, 11, 13, 15, 97, 116, 117, 118}
        shared = {16, 17, 18, 19, 20, 21, 22, 100, 101, 102, 104, 105}
        decoded = set()
        for option in enum.findall("option"):
            value = option.get("value")
            if value.startswith("ADC_CHANNEL_"):
                channel = int(value.removeprefix("ADC_CHANNEL_"))
            else:
                channel = int(value.strip("()U"), 0)
            decoded.add(channel)
            for unit, differential in itertools.product((0, 1), (False, True)):
                values = self.defaults()
                self.assign(values, 32, 8, 16, differential)
                values[P + "virtual_channel_32_channel_select"] = option.get("id")
                values[P + "scan_group_8_converter_selection"] = P + f"scan_group_8_converter_selection.adc_{unit}"
                cases.append((expression, values))
                expected.append(channel in (shared | (unit1 if unit else unit0)) and
                                (not differential or channel in DIAGNOSIS or channel in {0, 2, 4, 6, 8, 10}))
        self.assertEqual(unit0 | unit1 | shared, decoded)
        self.assertEqual(expected, self.evaluate(cases))

    def test_all_six_sample_hold_circuits_mode_consistency_and_highest_group(self):
        expression = self.admission()
        cases, expected = [], []
        for circuit, differential, priority in itertools.product(range(6), (False, True), (False, True)):
            values = self.defaults()
            unit = int(circuit >= 3)
            values[P + "sample_and_hold_enable_mask"] = P + f"sample_and_hold_enable_mask.unit_{circuit + unit}"
            for group in (0, 8):
                values[P + f"scan_group_{group}_converter_selection"] = P + f"scan_group_{group}_converter_selection.adc_{unit}"
            self.assign(values, 0, 0, circuit * 2, False)
            self.assign(values, 32, 8, circuit * 2, differential)
            if priority:
                values[P + "group_priority_enable"] = P + f"group_priority_enable.unit_{unit}"
            cases.append((expression, values))
            expected.append(not differential and not priority)
        # Cross-unit shared-source assignments are not a static conflict: sequential scans are legal.
        values = self.defaults()
        values[P + "scan_group_8_converter_selection"] = P + "scan_group_8_converter_selection.adc_1"
        self.assign(values, 0, 0, 16)
        self.assign(values, 32, 8, 16)
        cases.append((expression, values))
        expected.append(True)
        self.assertEqual(expected, self.evaluate(cases))

    def test_unused_channels_and_non_target_do_not_receive_new_restrictions(self):
        expression = self.admission()
        values = self.defaults()
        self.assign(values, 0, 0, 16)
        self.assign(values, 1, 0, 0)
        values[P + "sample_and_hold_enable_mask"] = P + "sample_and_hold_enable_mask.unit_0"
        self.assertEqual([False, True], self.evaluate([(expression, values),
                         (expression, {k: v for k, v in values.items() if k != CAP})]))
        values[P + "virtual_channel_1_scan_group"] = P + "virtual_channel_1_scan_group.none"
        self.assertEqual([True], self.evaluate([(expression, values)]))

    def test_gpt_divisors_three_and_five_prohibited_before_adc_divider_only_on_target(self):
        # HM9.2.52 p368 Note1: /3 and /5 are prohibited when GPTCLK supplies ADC16H.
        label = "ADC16H cannot use GPTCLK divided by 3 or 5 (HM 9.2.52 Note 1)."
        constraint = self.module.find(f'constraint[@display="{label}"]')
        self.assertIsNotNone(constraint, "Missing GPTCLK consumer divider constraint")
        self.assertNotIn(P + "adc_clock_divider", constraint.text)
        for name in ("gpt_source", "gpt_divided"):
            key = "board.clock.peripheral.ra8p1." + name
            self.assertIsNotNone(self.bsp.find(f'.//peripheral[@id="{key}"]'))
        cases, expected = [], []
        for target, source, divisor, adc_divisor, source_hz in itertools.product(
                (False, True), ("gpt", "adcclk", "pclka"),
                (1, 2, 3, 4, 5, 6, 8, 10, 16, 32), range(1, 6), (100000000, 333333333)):
            values = {P + "adc_clock_source": P + "adc_clock_source." + source,
                      P + "adc_clock_divider": P + f"adc_clock_divider.div_{adc_divisor}",
                      "board.clock.peripheral.ra8p1.gpt_source": source_hz,
                      # Integer-Hz truncation deliberately exercises rounding of the clock ratio.
                      "board.clock.peripheral.ra8p1.gpt_divided": source_hz // divisor}
            if target:
                values[CAP] = 1
            cases.append((constraint.text, values))
            expected.append(not (target and source == "gpt" and divisor in (3, 5)))
        self.assertEqual(expected, self.evaluate(cases))
        # Disabled GPT remains the existing Requires-GPTCLK constraint's responsibility.
        for source in ("adcclk", "pclka"):
            values = {CAP: 1, P + "adc_clock_source": P + "adc_clock_source." + source,
                      "board.clock.peripheral.ra8p1.gpt_source": 0,
                      "board.clock.peripheral.ra8p1.gpt_divided": 0}
            self.assertEqual([True], self.evaluate([(constraint.text, values)]))

    def test_crlf_and_stock_constraints_and_nsc_contract_remain_present(self):
        data = MDF.read_bytes()
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))
        self.assertGreater(data.count(b"\r\n"), 0)
        for old in self.stock.findall("constraint"):
            self.assertTrue(any(n.attrib == old.attrib and n.text == old.text
                                for n in self.module.findall("constraint")), old.get("display"))
        self.assertEqual(ET.tostring(self.stock.find("nsc")), ET.tostring(self.module.find("nsc")))


if __name__ == "__main__":
    unittest.main()
