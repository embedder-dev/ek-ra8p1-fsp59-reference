"""Offline target MDF controls; numerical anchors are from HM/Datasheet Rev.1.30.

These execute substituted constraints in JavaScript, not e2's model resolver.
Per-unit attribution tests exercise the provider contract, not pack integration.
"""
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MDF = ROOT / "baseline/module_descriptions"
FSP = MDF / "Renesas##BSP##ra8p1##fsp####5.9.0.xml"
DEVICE = MDF / "Renesas##BSP##ra8p1##device####5.9.0.xml"
IOPORT = MDF / "Renesas##HAL Drivers##all##r_ioport####5.9.0.xml"
CANFD = MDF / "Renesas##HAL Drivers##all##r_canfd####5.9.0.xml"
GATE = "interface.mcu.ra8p1.clock_limits"
PART_A = "interface.mcu.r7ka8p1kflcac"
TOKEN = re.compile(r"\$\{([^{}]+)\}")


def substitute(text, values, unknown=None):
    return TOKEN.sub(lambda m: str(values.get(m[1], m[0] if unknown is None else unknown)), text)


def defaults(rendered=False):
    values = {}
    for prop in ET.parse(FSP).findall(".//config/property"):
        value = prop.get("default", "")
        if rendered:
            option = prop.find(f"option[@id='{value}']")
            if option is not None:
                value = option.get("value")
        values[prop.get("id")] = value
    return values


def js_results(expressions):
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node.js is required to execute the MDF JavaScript controls")
    program = r'''
const fs = require('fs');
const testExists = s => !String(s).includes('${') && s !== 'RA_NOT_DEFINED';
const testInteger = s => /^(?:0[xX][0-9a-fA-F]+|[+-]?[0-9]+)$/.test(s) && Number.isInteger(Number(s));
const rows = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(rows.map(expression => Boolean(eval(expression)))));
'''
    result = subprocess.run([node, "-e", program], input=json.dumps(expressions),
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def macro(name):
    content = ET.parse(FSP).find(".//config/content").text.replace("\\\n", "")
    found = re.search(r"^[ \t]*#define " + name + r"[ \t]+([^\n]*)", content, re.M)
    if found is None:
        raise AssertionError("Missing generated macro " + name)
    return found[1]


class ConfigMetadataReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fsp = ET.parse(FSP).getroot()
        cls.nodes = {x.get("id"): x for x in cls.fsp.findall(".//clock/node")}
        cls.io = [x for x in ET.parse(IOPORT).findall(".//module/constraint")
                  if GATE in x.text]
        cls.can = [x for x in ET.parse(CANFD).findall(".//module/constraint")
                   if GATE in x.text]

    def evaluate(self, constraints, changes=None, target=True):
        values = defaults()
        if target:
            values.update({GATE: "1", PART_A: "1"})
        values.update(changes or {})
        return js_results([substitute(x.text, values) for x in constraints])

    def one_constraint(self, text, constraints=None):
        matches = [x for x in (self.io if constraints is None else constraints)
                   if re.search(r"(?<![A-Za-z0-9_])" + re.escape(text), x.get("display", ""))]
        self.assertEqual(1, len(matches), text)
        return matches

    def compile_assertions(self, assertions):
        compiler = shutil.which("cc")
        self.assertIsNotNone(compiler, "A native C compiler is required")
        source = "#include <stdint.h>\n" + "\n".join(
            f'_Static_assert((uint32_t)({expression}) == {expected}U, "case {i}");'
            for i, (expression, expected) in enumerate(assertions))
        result = subprocess.run([compiler, "-std=c11", "-Wall", "-Werror", "-x", "c",
                                 "-fsyntax-only", "-"], input=source, capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)

    def frequency(self, name, choices):
        if name == "0":
            return Fraction(0)
        node = self.nodes[name]
        selected = choices.get(name, node.get("default"))
        options = node.findall("option")
        option = next((x for x in options if x.get("id") == selected), options[0])
        if option.get("id") == "_edit":
            return Fraction(choices.get(name, node.get("default")))
        source = self.frequency(option.get("input"), choices) if option.get("input") else Fraction(1)
        return source * Fraction(option.get("mul", "1")) / Fraction(option.get("div", "1"))

    def test_both_plls_keep_ids_but_compute_all_fractional_options_exactly(self):
        # HM 9.2.6/9.2.9: .33/.66 are serialized thirds, not decimal hundredths.
        for pll in ("pll", "pll2"):
            options = self.nodes[f"board.clock.{pll}.mul"].findall("option")
            self.assertEqual(1041, len(options))
            for option in options:
                whole, fraction = option.get("id").rsplit(".", 1)[1].split("_")
                expected = int(whole) + {"00": Fraction(0), "33": Fraction(1, 3),
                                         "50": Fraction(1, 2), "66": Fraction(2, 3)}[fraction]
                self.assertEqual(expected, Fraction(int(option.get("mul")), int(option.get("div"))))
                self.assertIn(f"BSP_CLOCKS_PLL_MUL({int(whole)},{int(fraction)})", option.get("macroValue"))

    def test_fractional_frequency_reaches_every_output_and_macro(self):
        for pll, output_prefix in (("pll", "pll1"), ("pll2", "pll2")):
            choices = {f"board.clock.{pll}.source": f"board.clock.{pll}.source.xtal",
                       f"board.clock.{pll}.div": f"board.clock.{pll}.div.1",
                       f"board.clock.{pll}.mul": f"board.clock.{pll}.mul.41_66"}
            for output in "pqr":
                name = f"board.clock.{output_prefix}{output}"
                choices[name + ".div"] = name + ".div.2"
                self.assertEqual(500_000_000, self.frequency(name + ".display", choices))
                option = self.nodes[name + ".display"].find("option")
                self.assertEqual("(${value})", option.get("macroValue"))

    def test_dedicated_clock_source_ceilings_are_before_division(self):
        # HM table 9.2: source ceilings are independent of divided-output caps.
        ceilings = {"sciclk": 480_000_000, "spiclk": 333_000_000,
                    "canfdclk": 480_000_000, "lcdclk": 480_000_000,
                    "i3cclk": 800_000_000, "uck": 480_000_000,
                    "u60ck": 480_000_000, "octaspiclk": 333_000_000,
                    "adcclk": 480_000_000, "gptclk": 600_000_000}
        for name, ceiling in ceilings.items():
            options = self.nodes[f"board.clock.{name}.source"].findall("option")
            for option in options:
                if option.get("input", "").startswith("board.clock.pll"):
                    with self.subTest(clock=name, option=option.get("id")):
                        self.assertEqual(ceiling, int(option.get("maxValue")))
                        self.assertLessEqual(ceiling, int(option.get("maxValue")))
                        self.assertGreater(ceiling + 1, int(option.get("maxValue")))
        self.assertEqual("1000000000", self.nodes["board.clock.pll1p.display"].find("option").get("maxValue"))
        self.assertEqual("1200000000", self.nodes["board.clock.pll2p.display"].find("option").get("maxValue"))

    def test_eight_dedicated_domains_include_high_dividers_with_real_macro_names(self):
        header = (ROOT / "baseline/ra/fsp/src/bsp/mcu/all/bsp_clocks.h").read_text()
        for name in ("sciclk", "spiclk", "canfdclk", "lcdclk", "i3cclk", "uck", "u60ck", "octaspiclk"):
            node = self.nodes[f"board.clock.{name}.div"]
            for divisor in (10, 16, 32):
                option = node.find(f"option[@id='board.clock.{name}.div.{divisor}']")
                self.assertIsNotNone(option, (name, divisor))
                self.assertEqual(str(divisor), option.get("div"))
                symbol = option.get("macroValue").strip("()")
                self.assertRegex(header, r"\b" + re.escape(symbol) + r"\b")

    def test_range_two_limits_and_default_range_one(self):
        # Datasheet table 2.49 pp.108-113; exercise every added range-2 constraint.
        limits = {"pll1p": 600_000_000, "cpuclk": 600_000_000, "cpuclk1": 150_000_000,
                  "npuclk": 300_000_000, "iclk": 150_000_000, "mriclk": 150_000_000,
                  "fclk": 75_000_000, "pclka": 75_000_000, "pclkb": 37_500_000,
                  "pclkd": 150_000_000, "pclke": 150_000_000, "bclk": 75_000_000}
        for name, limit in limits.items():
            rows = self.one_constraint(f"{name.upper()} exceeds the range-2")
            values = {"config.bsp.fsp.clock_voltage_range": "config.bsp.fsp.clock_voltage_range.2",
                      f"board.clock.peripheral.ra8p1.{name}": limit}
            self.assertEqual([True], self.evaluate(rows, values))
            values[f"board.clock.peripheral.ra8p1.{name}"] += 1
            self.assertEqual([False], self.evaluate(rows, values))
            del values["config.bsp.fsp.clock_voltage_range"]
            self.assertEqual([True], self.evaluate(rows, values))

    def test_part_specific_pll1p_limit_and_low_vcc_bus_boundaries(self):
        rows = self.one_constraint("PLL1P above 800")
        self.assertEqual([True], self.evaluate(rows, {"board.clock.peripheral.ra8p1.pll1p": 1_000_000_000}))
        for frequency, valid in ((800_000_000, True), (800_000_001, False)):
            self.assertEqual([valid], self.evaluate(rows, {PART_A: "${missing}",
                             "board.clock.peripheral.ra8p1.pll1p": frequency}))
        for name, limit in (("bclk", 60_000_000), ("ebclk", 30_000_000)):
            rows = self.one_constraint(f"{name.upper()} exceeds the VCC")
            values = {"config.bsp.fsp.clock_vcc_range": "config.bsp.fsp.clock_vcc_range.low",
                      f"board.clock.peripheral.ra8p1.{name}": limit}
            self.assertEqual([True], self.evaluate(rows, values))
            values[f"board.clock.peripheral.ra8p1.{name}"] += 1
            self.assertEqual([False], self.evaluate(rows, values))
            del values["config.bsp.fsp.clock_vcc_range"]
            self.assertEqual([True], self.evaluate(rows, values))

    def test_canfd_ratio_is_consumer_only(self):
        self.assertEqual(1, len(self.can))
        for a, e, valid in ((125_000_000, 250_000_000, True), (125_000_000, 125_000_000, False), (0, 0, False)):
            values = {"board.clock.peripheral.ra8p1.pclka": a,
                      "board.clock.peripheral.ra8p1.pclke": e}
            self.assertEqual([valid], self.evaluate(self.can, values))
        self.assertFalse(any("PCLKE:PCLKA" in x.get("display", "")
                             for x in self.fsp.findall(".//clock/constraint")))

    def test_clock_only_constraints_have_no_unresolvable_model_references(self):
        for constraint in self.fsp.findall(".//clock/constraint"):
            self.assertNotRegex(constraint.text, r"\$\{(?:interface|config)\.")
        for constraint in self.io + self.can:
            for exported in re.findall(r"\$\{(board.clock.peripheral.[^}]+)\}", constraint.text):
                self.assertIsNotNone(self.fsp.find(f".//clock/node/peripheral[@id='{exported}']"), exported)

    def test_mram_ratio_five_and_enabled_gpt_strict_comparison(self):
        for text, cases in (("five times", [(250_000_000, 50_000_000, True), (250_000_000, 49_999_999, False)]),
                            ("Enabled GPTCLK", [(0, 125_000_000, True), (125_000_000, 125_000_000, False), (125_000_001, 125_000_000, True)])):
            constraints = self.one_constraint(text, self.fsp.findall(".//clock/constraint"))
            for first, second, valid in cases:
                keys = ("mriclk", "fclk") if text == "five times" else ("gptclk", "pclka")
                values = {f"value:board.clock.{key}.display": value for key, value in zip(keys, (first, second))}
                self.assertEqual([valid], self.evaluate(constraints, values))

    def test_reject_every_nondefault_fsbl_option_and_all_address_provisioning(self):
        self.assertEqual([True] * len(self.io), self.evaluate(self.io, {
            "board.clock.peripheral.ra8p1." + name: 0 for name in
            ("pll1p", "cpuclk", "cpuclk1", "npuclk", "iclk", "mriclk", "fclk", "pclka", "pclkb", "pclkd", "pclke", "bclk", "ebclk")}))
        for reg in ("FSBLCTRL0", "FSBLCTRL1", "FSBLCTRL2"):
            rows = self.one_constraint(reg + " nondefault")
            for prop in self.fsp.findall(".//config/property"):
                if prop.get("id", "").startswith("config.bsp.fsp." + reg + "."):
                    for option in prop.findall("option"):
                        self.assertEqual([option.get("id") == prop.get("default")], self.evaluate(rows, {prop.get("id"): option.get("id")}))
        for address in ("SACC0", "SACC1", "SAMR"):
            rows = self.one_constraint(address + " provisioning")
            for value in ("0", "0x02000000", "0x22007BFC", "0xFFFFFFFF", "4294967295", "-1", "4294967296", "garbage"):
                self.assertEqual([value in ("0xFFFFFFFF", "4294967295")], self.evaluate(rows, {"config.bsp.fsp." + address: value}))

    def test_unsupported_provisioning_also_fails_generated_compile(self):
        text = self.fsp.find(".//config/content").text
        start = text.index("/* FSBL Control Register 0 */")
        end = text.index("#endif", text.index('#error "RA8P1 FSBL/SACC/SAMR', start)) + len("#endif")
        fragment = text[start:end]
        cases = [{}, {"config.bsp.fsp.FSBLCTRL0.FSBLEN": "0"}, {"config.bsp.fsp.SACC0": "0x02000000"},
                 {"config.bsp.fsp.SACC1": "0x02000400"}, {"config.bsp.fsp.SAMR": "0x22000000"}]
        for changes in cases:
            values = defaults(rendered=True)
            values.update(changes)
            result = subprocess.run([shutil.which("cc"), "-E", "-x", "c", "-"],
                                    input=substitute(fragment, values), text=True,
                                    capture_output=True, timeout=30)
            self.assertEqual(not changes, result.returncode == 0)
            if changes:
                self.assertIn("provisioning is unsupported", result.stderr)

    def test_per_unit_dac_and_ospi_dotf_secure_attribution_formulas(self):
        # HM 52.8.1/52.8.3: Secure = zero. DAC121 bit19, DAC120 bit20.
        assertions = []
        for channel, bit in ((0, 20), (1, 19)):
            values = defaults(rendered=True)
            values[f"interface.peripheral.dac_b{channel}"] = 1
            expression = substitute(macro("BSP_TZ_CFG_PSARD"), values, "0")
            assertions.append((f"({expression}) & ((1U << 19) | (1U << 20))", 1 << (19 if bit == 20 else 20)))
        for unit in (0, 1):
            for block in ("ospi_b", "dotf"):
                expression = substitute(macro("BSP_TZ_CFG_PSARB"), {f"interface.peripheral.{block}{unit}": 1}, "0")
                assertions.append((f"({expression}) & (3U << 16)", 1 << (17 - unit)))
        self.compile_assertions(assertions)

    def test_cpu1_dma_and_mmpu_composite_policy(self):
        # HM 16.3.1.1 and 17.2.2: bank 1 is bits23:16; other bits stay zero.
        assertions = []
        for channel in range(8):
            values = defaults(rendered=True)
            values.update({f"interface.peripheral.dmac{channel}": 1,
                           "config.bsp.fsp.tz.dmacchsar.cpu1": str(1 << channel)})
            local = substitute(macro("BSP_TZ_CFG_DMACCHSAR_LOCAL"), values, "0")
            combined = macro("BSP_TZ_CFG_DMACCHSAR").replace("BSP_TZ_CFG_DMACCHSAR_LOCAL", f"({local})").replace("BSP_TZ_CFG_DMACCHSAR_CPU1", str(1 << channel))
            assertions.append((combined, (255 ^ (1 << channel)) | ((1 << channel) << 16)))
        self.assertEqual("(BSP_TZ_CFG_DMACCHSAR)", macro("BSP_TZ_CFG_MMPUSARA").strip())
        self.compile_assertions(assertions)
        rows = self.one_constraint("RA8P1 CPU1 Non-secure DMA channel mask")
        for value, valid in (("0", True), ("0xFF", True), ("256", False), ("-1", False), ("1.5", False)):
            self.assertEqual([valid], self.evaluate(rows, {"config.bsp.fsp.tz.dmacchsar.cpu1": value}))

    def test_nmi_common_and_per_core_policy_bits_are_independent(self):
        # HM 14.2.2 pp531-532: SANMI common0, SANMI0 bit1, SANMI1 bit2.
        assertions = []
        for common in (0, 1):
            for cpu0 in (0, 1):
                for cpu1 in (0, 1):
                    expression = substitute(macro("BSP_TZ_CFG_ICUSARB"), {
                        "config.bsp.fsp.tz.icusarb.common": common,
                        "config.bsp.fsp.tz.cmsis.bfhfnmins": cpu0,
                        "config.bsp.fsp.tz.icusarb.cpu1": cpu1})
                    assertions.append((expression, common | cpu0 << 1 | cpu1 << 2))
        self.compile_assertions(assertions)
        self.assertEqual("0U", defaults(rendered=True)["config.bsp.fsp.tz.icusarb.common"])
        self.assertEqual("0U", defaults(rendered=True)["config.bsp.fsp.tz.icusarb.cpu1"])

    def test_target_capabilities_and_corrected_channel_options(self):
        provides = {x.get("interface") for x in ET.parse(DEVICE).findall(".//bsp/provides")}
        self.assertTrue({GATE, "interface.mcu.sci_b.no_scksel", "interface.mcu.agt.register_type.1",
                         "interface.mcu.icu.common_regs", "interface.mcu.glcdc.global_gamma_switch"} <= provides)
        for role in ("master", "slave"):
            prop = self.fsp.find(f".//property[@id='config.bsp.fsp.mcu.iic_{role}.fastplus_channels']")
            self.assertEqual(7, int(prop.get("default"), 0))
        units = self.fsp.find(".//enum[@id='enum.mcu.ospi_b.units']")
        self.assertEqual({"0", "1"}, {x.get("value") for x in units})
        ivcmp = self.fsp.find(".//enum[@id='enum.driver.acmphs.ivcmp']")
        ivref = self.fsp.find(".//enum[@id='enum.driver.acmphs.ivref']")
        for enum, expected in ((ivcmp, {"ACMPHS_INPUT_IVCMP0": "AN017", "ACMPHS_INPUT_IVCMP3": "AN001"}),
                               (ivref, {"ACMPHS_REFERENCE_IVREF0": "AN008", "ACMPHS_REFERENCE_IVREF1": "AN009"})):
            for value, label in expected.items():
                self.assertTrue(any(x.get("value") == value and label in x.get("display", "") for x in enum), (value, label))

    def test_all_new_shared_constraints_bypass_legacy_without_target_values(self):
        self.assertEqual([True] * len(self.io + self.can), self.evaluate(self.io + self.can, target=False))
        # Preserve owner-qualified original metadata, templates, options, guards and defaults.
        archive = ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip"
        self.assertEqual("99c4abae6239a68171fcbff86070971f591f0a8945e90a50eb07d87843bee363",
                         hashlib.sha256(archive.read_bytes()).hexdigest())
        with zipfile.ZipFile(archive) as release:
            name = next(x for x in release.namelist() if x.endswith("/Renesas.RA.5.9.0.pack"))
            with zipfile.ZipFile(io.BytesIO(release.read(name))) as pack:
                for path in (IOPORT, CANFD):
                    current = ET.parse(path).getroot()
                    for module in current.findall("module"):
                        for constraint in list(module.findall("constraint")):
                            if GATE in constraint.text:
                                module.remove(constraint)
                    original = ET.fromstring(pack.read(".module_descriptions/" + path.name))
                    self.assertEqual(ET.canonicalize(ET.tostring(original, encoding="unicode"), strip_text=True),
                                     ET.canonicalize(ET.tostring(current, encoding="unicode"), strip_text=True))


if __name__ == "__main__":
    unittest.main()
