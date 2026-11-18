"""AGT-001..022: production-C host regression, not hardware qualification.

Oracles: RA8P1 HM25.2.1/.5/.6/.7/.9, HM25.3.1/.8 and HM25.4 pp1176-1196;
HM70.50 LOCO bounds; TN-A0158A/E (2025-11-14) countermeasure 3. Legacy
oracle is the original nested 5e8fbb10 FSP5.9, never a newer FSP driver.
"""
import itertools
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "baseline"
SOURCE = BASE / "ra/fsp/src/r_agt/r_agt.c"
HEADER = BASE / "ra/fsp/inc/instances/r_agt.h"
MDF = BASE / "module_descriptions/Renesas##HAL Drivers##all##r_agt####5.9.0.xml"
FIXTURE = ROOT / "tools/ra8p1/review_agt"
SCENARIOS = ("clock_filter", "clock_switch", "flags", "filter", "interval", "polarity_low",
             "irq_required", "ratio", "measurement_output", "endpoint", "enable", "counter",
             "duty", "close", "event", "chain", "oneshot", "capture", "callback", "arguments")


def native_source(text):
    """Observe MMIO stores, not driver decisions; widen only host pointer arithmetic.

    The test executes every production function. Wrappers implement hardware-side
    W0C/buffering/TCSTF behavior which ordinary RAM cannot provide. No branch or
    return value is replaced. The original C gets precisely the same observation.
    """
    text = re.sub(r"uint32_t (base_address|channel_base_address) =", r"uintptr_t \1 =", text)
    text = re.sub(r"\(uint32_t\) (R_AGT0|R_AGTW0|p_instance_ctrl->p_reg)\b", r"(uintptr_t) \1", text)
    text = re.sub(r"(p_reg_ctrl->AGTMR1)_b\.TCK\s*=\s*([^;]+);",
                  r"review_write_tck(&\1, \2);", text)
    text = re.sub(r"(p_reg_ctrl->(?:AGTCR|AGTMR1|AGTMR2|AGTIOC|AGTCMSR|AGTISR|AGTIOSEL))\s*=\s*([^;]+);",
                  r"review_write8(&\1, \2);", text)
    text = re.sub(r"(p_instance_ctrl->p_reg->AGT16\.(?:AGT|AGTCMA|AGTCMB))\s*=\s*([^;]+);",
                  r"review_write16(&\1, \2);", text)
    text = re.sub(r"(p_ctrl->p_(?:callback|context|callback_memory)\s*=\s*[^;]+;)",
                  r"\1\n    review_publication_point(p_ctrl);", text)
    return text


class ReviewAgtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("cc")
        if cls.cc is None:
            raise RuntimeError("A native compiler is required")
        cls.temp = tempfile.TemporaryDirectory(prefix="review-agt-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        cls.binaries = {}
        for header in ("core_cm85.h", "core_cm33.h"):
            (cls.directory / header).write_text("typedef int IRQn_Type;\n")
        (cls.directory / "system.h").write_text("")
        (cls.directory / "r_agt_cfg.h").write_text("")
        cls.original = subprocess.check_output(
            ["git", "-C", str(BASE), "show", "5e8fbb10c752e16272790bd3a2587485d0377835:ra/fsp/src/r_agt/r_agt.c"],
            timeout=10).decode()
        for name, text in (("candidate", SOURCE.read_text()), ("before", cls.original)):
            (cls.directory / (name + ".c")).write_text(native_source(text))

    def run_ok(self, command):
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, " ".join(map(str, command)) + "\n" + result.stdout + result.stderr)
        return result

    def binary(self, core, checks, inputs, outputs, secure, before=False, nsc=False):
        key = (core, checks, inputs, outputs, secure, before, nsc)
        if key not in self.binaries:
            output = self.directory / ("agt-" + "-".join(map(str, key)))
            self.run_ok([self.cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                         "-Wno-pointer-to-int-cast", "-Wno-unused-function",
                         "-fsanitize=undefined", "-fno-sanitize-recover=all",
                         "-I" + str(self.directory), "-I" + str(FIXTURE),
                         "-I" + str(BASE / "ra/fsp/src/bsp/mcu/ra8p1"),
                         "-I" + str(BASE / "ra/fsp/src/bsp/cmsis/Device/RENESAS/Include"),
                         "-I" + str(BASE / "ra/fsp/inc"),
                         "-I" + str(BASE / "ra/fsp/inc/api"),
                         "-I" + str(BASE / "ra/fsp/inc/instances"),
                         f"-DBSP_CFG_CPU_CORE={core}", f"-DBSP_TZ_SECURE_BUILD={secure}",
                         f"-DAGT_CFG_PARAM_CHECKING_ENABLE={checks}",
                         f"-DAGT_CFG_INPUT_SUPPORT_ENABLE={inputs}",
                         f"-DAGT_CFG_OUTPUT_SUPPORT_ENABLE={outputs}",
                         str(self.directory / ("before.c" if before else "candidate.c")),
                         str(FIXTURE / "fixture.c"), f"-DREVIEW_NSC={int(nsc)}",
                         *([str(self.directory / "guard.c"), str(self.directory / "nsc.c")] if nsc else []),
                         "-o", str(output)])
            self.binaries[key] = output
        return self.binaries[key]

    def test_production_c_both_cores_checks_io_and_security_matrix(self):
        for core, checks, inputs, outputs, secure in itertools.product((0, 1), repeat=5):
            binary = self.binary(core, checks, inputs, outputs, secure)
            for scenario in SCENARIOS:
                with self.subTest(core=core, checks=checks, inputs=inputs,
                                  outputs=outputs, secure=secure, scenario=scenario):
                    self.run_ok([str(binary), scenario])

    def test_original_production_c_fails_independent_hm_oracles(self):
        # The pristine driver compiles, so negative controls establish behavioral
        # detection, not the prior target's missing AGTW register compile error.
        binary = self.binary(0, 0, 1, 1, 1, before=True)
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                result = subprocess.run([str(binary), scenario], capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0, "Pristine unexpectedly passed " + scenario)
                self.assertRegex(result.stderr, r"Assertion|runtime error:")

    def test_mdf_target_constraints_and_calculator(self):
        root = ET.fromstring(MDF.read_text())
        module = root.find("module")
        targeted = [item for item in module.findall("constraint") if "Register type 1" in item.attrib["display"]]
        self.assertEqual(len(targeted), 5)
        target_fsp = ROOT / ('pack_sources/ra8p1/Renesas.RA_mcu_ra8p1.5.9.0/.module_descriptions/'
                             'Renesas##BSP##ra8p1##fsp####5.9.0.xml')
        enum_root = ET.fromstring(target_fsp.read_text())
        ids = {item.attrib["id"] for item in root.iter("option") if "id" in item.attrib} | {
            item.attrib["id"] for item in enum_root.iter("option") if "id" in item.attrib}
        for constraint in targeted:
            for option in re.findall(r'"(module\.driver\.timer\.[^"]+)"', constraint.text):
                self.assertIn(option, ids)
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required to execute the shipped MDF JavaScript")
        defaults = {p.attrib["id"]: p.attrib.get("default", "") for p in module.findall("property")}
        def evaluate(expression, values, target=True):
            expression = re.sub(r"\$\{([^}]+)\}", lambda m: str(values.get(m[1], "unavailable")), expression)
            code = "function testExists(x) { return " + str(target).lower() + "; }\nconsole.log(JSON.stringify(" + expression + "));"
            return self.run_ok([node, "-e", code]).stdout.strip()
        # Each added constraint rejects its independent bad witness and ignores legacy.
        bad = [
            {"module.driver.timer.mode": "module.driver.timer.mode.mode_one_shot", "module.driver.timer.ipl": "_disabled"},
            {"module.driver.timer.count_source": "module.driver.timer.count_source.clock_agt_underflow", "module.driver.timer.channel": 0},
            {"module.driver.timer.measurement_mode": "module.driver.timer.measurement_mode.measure_pulse_period", "module.driver.timer.agtoa_output_enable": "module.driver.timer.agtoa_output_enable.true"},
            {"module.driver.timer.mode": "module.driver.timer.mode.mode_pwm", "module.driver.timer.duty_cycle": 100},
            {"module.driver.timer.count_source": "module.driver.timer.count_source.clock_loco", "board.clock.peripheral.agt": 500},
        ]
        for constraint, bad_values in zip(targeted, bad):
            values = {**defaults, **bad_values}
            self.assertEqual(evaluate(constraint.text, values), "false", constraint.attrib["display"])
            self.assertEqual(evaluate(constraint.text, values, False), "true")
        expression = module.find("property[@id='module.driver.timer.period']/export").text.strip()
        values = {"module.driver.timer.period": 10000, "module.driver.timer.unit": "raw",
                  "module.driver.timer.count_source": "AGT_CLOCK_LOCO", "board.clock.peripheral.agt": 40000,
                  "module.driver.timer.duty_cycle": 50, "module.driver.timer.channel": 0,
                  "module.driver.timer.bits.ch0": 16}
        values["module.driver.timer.bits.ch${module.driver.timer.channel}"] = 16
        # Expand the nested channel placeholder as the configurator does.
        expression = expression.replace("${module.driver.timer.bits.ch${module.driver.timer.channel}}", "16")
        result = evaluate(expression, values)
        self.assertIn(".source_div = (timer_source_div_t)1", result)
        self.assertIn(".period_counts = (uint32_t) 0x1388", result)
        original_mdf = subprocess.check_output(
            ["git", "show", "HEAD:" + str(MDF.relative_to(ROOT))], cwd=ROOT, timeout=10)
        original_module = ET.fromstring(original_mdf).find("module")
        original_expression = original_module.find("property[@id='module.driver.timer.period']/export").text.strip()
        original_expression = original_expression.replace(
            "${module.driver.timer.bits.ch${module.driver.timer.channel}}", "16")
        before = evaluate(original_expression, values)
        self.assertIn(".source_div = (timer_source_div_t)0", before)
        self.assertNotEqual(before, result, "Unsafe original asynchronous divider was not detected")
        for source, period in itertools.product(
                ("AGT_CLOCK_PCLKB", "AGT_CLOCK_LOCO", "AGT_CLOCK_SUBCLOCK", "AGT_CLOCK_AGT_UNDERFLOW"),
                (1, 10000, 0x20000)):
            witness = {**values, "module.driver.timer.count_source": source,
                       "module.driver.timer.period": period}
            self.assertEqual(evaluate(expression, witness, False), evaluate(original_expression, witness))
        legacy = evaluate(expression, values, False)
        self.assertIn(".source_div = (timer_source_div_t)0", legacy)
        self.assertIn(".period_counts = (uint32_t) 0x2710", legacy)
        tiny = evaluate(expression, {**values, "module.driver.timer.period": 1})
        self.assertIn(".source_div = (timer_source_div_t)1", tiny)
        self.assertIn(".period_counts = (uint32_t) 0x1", tiny)
        good_updates = [
            {"module.driver.timer.ipl": 2}, {"module.driver.timer.channel": 1},
            {"module.driver.timer.measurement_mode": "module.driver.timer.measurement_mode.measure_disabled"},
            {"module.driver.timer.duty_cycle": 50}, {"board.clock.peripheral.agt": 564},
        ]
        for constraint, bad_values, update in zip(targeted, bad, good_updates):
            self.assertEqual(evaluate(constraint.text, {**defaults, **bad_values, **update}), "true")
        chained_too_long = {**defaults, **bad[1], "module.driver.timer.channel": 1,
                            "module.driver.timer.period": 65537}
        self.assertEqual(evaluate(targeted[1].text, chained_too_long), "false")

    def test_nsc_compare_dispatch_and_original_public_api(self):
        root = ET.fromstring(MDF.read_text())
        module = root.find("module")
        table = module.find("nsc/declarations").text
        self.assertIn(".compareMatchSet = ${module.driver.timer.name}_compare_match_set_guard", table)
        wrapper = module.find("guard/template").text
        self.assertIn("return R_AGT_CompareMatchSet(&${module.driver.timer.name}_ctrl, compare_match_value, match_channel);", wrapper)
        # Compile the MDF's actual NSC table and secure wrapper, then dispatch
        # through timer_api_t to the production unsupported-returning function.
        def render(text):
            return text.replace("${module.driver.timer.name}", "review_timer")
        guard = ('#include "r_agt.h"\nextern agt_instance_ctrl_t review_timer_ctrl;\n'
                 'extern const timer_cfg_t review_timer_cfg;\n' +
                 render(module.find("guard/header").text))
        (self.directory / "guard.h").write_text(guard)
        (self.directory / "guard.c").write_text(render(wrapper))
        declarations = render(table)
        (self.directory / "nsc.c").write_text(
            '#include "guard.h"\nagt_instance_ctrl_t review_timer_ctrl;\n'
            'const timer_cfg_t review_timer_cfg = {0};\n' + declarations +
            '\nint review_nsc_check(void) { return review_timer.p_api->compareMatchSet && '
            '(review_timer.p_api->compareMatchSet(NULL, 123, TIMER_COMPARE_MATCH_A) == FSP_ERR_UNSUPPORTED); }\n')
        for core, checks in itertools.product((0, 1), repeat=2):
            self.run_ok([str(self.binary(core, checks, 1, 1, 1, nsc=True)), "nsc"])
        public = BASE / "ra/fsp/inc/api/r_timer_api.h"
        original = subprocess.check_output(["git", "-C", str(BASE), "show", "HEAD:ra/fsp/inc/api/r_timer_api.h"], timeout=10)
        self.assertEqual(public.read_bytes(), original)
        original_header = subprocess.check_output(
            ["git", "-C", str(BASE), "show", "HEAD:ra/fsp/inc/instances/r_agt.h"], timeout=10).decode()
        legacy_header = re.sub(r"#if BSP_FEATURE_AGT_REGISTER_TYPE == 1\n.*?#endif\n", "",
                               HEADER.read_text(), flags=re.S)
        self.assertEqual(legacy_header, original_header.replace("\r\n", "\n"))
        for path in (SOURCE, HEADER, MDF):
            raw = path.read_bytes()
            self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"), str(path))

    def test_legacy_feature_selection_and_real_arm_objects(self):
        # Reuse the retained original-5.9 fixtures and exact executable-section
        # comparison, not an e2 operation or a generated-tree edit.
        from tools import test_ra8p1_timer_bus_compatibility as compatibility
        compatibility.TimerBusCompatibilityTests.setUpClass()
        case = compatibility.TimerBusCompatibilityTests()
        case.test_legacy_agt_objects_match_pristine_with_zero_agtw()
        case.test_original_crlf_format_preserved()
        feature_headers = list((BASE / "ra/fsp/src/bsp/mcu").glob("*/bsp_feature.h"))
        self.assertEqual(len(feature_headers), 33)
        for header in feature_headers:
            value = re.search(r"#define\s+BSP_FEATURE_AGT_REGISTER_TYPE\s+\((\d+)UL\)", header.read_text())
            self.assertIsNotNone(value)
            self.assertEqual(int(value[1]), int(header.parent.name == "ra8p1"))


if __name__ == "__main__":
    unittest.main()
