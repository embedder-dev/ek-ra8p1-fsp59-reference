"""PDM-001..004: execute unmodified production C with asynchronous MMIO controls.

Acceptance anchors are HM50.2.19 (INPSEL, p3219), table50.18 (pp3252-53),
50.3.7/50.3.10 (pp3254/3256), 50.5.1 (p3265), and tables50.16/70.50
(pp3251/4117). No target execution or e2 operations are performed.
"""
from pathlib import Path
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
FSP = ROOT / "baseline/ra/fsp"
FIXTURE = ROOT / "tools/ra8p1"
MDF = ROOT / "baseline/module_descriptions/Renesas##HAL Drivers##all##r_pdm####5.9.0.xml"


class PdmReviewProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("clang")
        if not cls.cc:
            raise unittest.SkipTest("Clang coverage instrumentation required for native-C MMIO injection")
        cls.temp = tempfile.TemporaryDirectory(prefix="pdm-review-")
        cls.addClassCleanup(cls.temp.cleanup)
        tmp = Path(cls.temp.name)
        (tmp / "bsp_api.h").write_text('#include "acquisition_fixture_bsp.h"\n')
        cls.binaries = []
        for checking in (0, 1):
            (tmp / "r_pdm_cfg.h").write_text(f"#define PDM_CFG_PARAM_CHECKING_ENABLE {checking}\n")
            for core in (0, 1):
                binary = tmp / f"pdm-{checking}-{core}"
                cmd = [cls.cc, "-std=c11", "-O0", "-g", "-Wall", "-Wextra", "-Wconversion", "-Werror",
                       "-fsanitize=undefined", "-fno-sanitize-recover=all", f"-DBSP_CFG_CPU_CORE={core}",
                       "-DBSP_TZ_SECURE_BUILD=0", "-I" + str(tmp), "-I" + str(FIXTURE),
                       "-I" + str(FSP / "inc"), "-I" + str(FSP / "inc/api"), "-I" + str(FSP / "inc/instances")]
                driver = tmp / "pdm.o"
                for args in (cmd + ["-fsanitize-coverage=trace-pc-guard", "-c", str(FSP / "src/r_pdm/r_pdm.c"),
                                    "-o", str(driver)],
                             cmd + [str(FIXTURE / "review_pdm_fixture.c"), str(driver), "-o", str(binary)]):
                    built = subprocess.run(args, capture_output=True, text=True)
                    if built.returncode:
                        raise AssertionError(built.stdout + built.stderr)
                cls.binaries.append((checking, core, binary))

    def scenario(self, number):
        for checking, core, binary in self.binaries:
            with self.subTest(checking=checking, core=core):
                run = subprocess.run([str(binary), str(number)], capture_output=True, text=True, timeout=10)
                self.assertEqual(0, run.returncode, run.stdout + run.stderr)
                self.assertIn("PDM review regression passed", run.stdout)

    def test_pdm001_overwrite_injected_during_fifo_drain(self):
        self.scenario(0)
        self.scenario(5)  # Last FIFO read also must not escape as COMPLETE.
        self.scenario(6)  # Error appearing exactly at the final IRQ clear.

    def test_pdm002_threshold_crossing_at_icu_clear_is_repended(self):
        self.scenario(1)

    def test_pdm002_error_at_icu_clear_is_repended(self):
        self.scenario(2)

    def test_pdm003_all_settling_modes_cover_guaranteed_moco_minimum(self):
        self.scenario(3)

    def test_positive_clean_completion(self):
        self.scenario(4)

    def test_pdm004_source_mandatory_and_matched(self):
        for scenario in range(8):
            with self.subTest(scenario=scenario):
                self.scenario(10 + scenario)

    def test_pdm004_source_cannot_stop_before_consumer(self):
        self.scenario(18)

    def test_pdm004_start_rechecks_source(self):
        self.scenario(19)

    def test_pdm004_unused_consumer_divider_can_differ_with_equal_decimation(self):
        self.scenario(7)


class PdmReviewMetadataTests(unittest.TestCase):
    def test_hm_inpsel_mapping_uses_supplied_physical_pin_groups(self):
        pinfile = ROOT / ".embedder/pin-model/pinmapping/PinCfgR7KA8P1KxxCAC.xml"
        pinroot = ET.parse(pinfile)
        mod = ET.parse(MDF).find("module")
        self.assertEqual("pdm${module.driver.pdm.physical_input}", mod.find("peripheral").get("component"))
        # HM50.2.19 explicitly overrides the two-channel example in table50.17:
        # falling consumers CH0/CH1/CH2 use physical inputs 2/0/1 respectively.
        for consumer, source in ((0, 2), (1, 0), (2, 1)):
            self.assertEqual(source, (consumer + 2) % 3)
            component = pinroot.find(f".//component[@id='pdm{source}']")
            self.assertIsNotNone(component)
            for signal in (f"pdm{source}.pdmdat{source}", f"pdm{source}.pdmclk{source}"):
                self.assertIsNotNone(component.find(f"pins/pin[@id='{signal}']"))

    def test_stereo_constraint_rejects_missing_and_mismatched_source(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node required to execute MDF JavaScript constraints")
        mod = ET.parse(MDF).find("module")
        constraints = [e.text for e in mod.findall("constraint") if "stereo" in e.get("display", "").lower()]
        self.assertTrue(constraints, "falling stereo requires an independently validated peer constraint")
        providers = [e.get("interface") for e in mod.findall("provides")]
        expressions, wants = [], []
        for channel, physical in ((0, 2), (1, 0), (2, 1)):
            values = {"module.driver.pdm.channel": str(channel), "module.driver.pdm.physical_input": str(physical),
                      "module.driver.pdm.input": "module.driver.pdm.input.falling",
                      "module.driver.pdm.sinc_order": "module.driver.pdm.sinc_order.4",
                      "module.driver.pdm.clock_div": "module.driver.pdm.clock_div.0",
                      "module.driver.pdm.fifo_threshold": "module.driver.pdm.fifo_threshold.4"}
            for missing in (False, True):
                for mismatch in (None, "sinc_order", "clock_div", "fifo_threshold", "input", "channel"):
                    source_values = {**values, "module.driver.pdm.channel": str(physical),
                                     "module.driver.pdm.input": "module.driver.pdm.input.rising"}
                    if mismatch == "channel":
                        source_values["module.driver.pdm.channel"] = str((physical + 1) % 3)
                    elif mismatch == "input":
                        source_values["module.driver.pdm.input"] = "module.driver.pdm.input.falling"
                    elif mismatch:
                        source_values["module.driver.pdm." + mismatch] = "module.driver.pdm." + mismatch + ".3"
                    available = set() if missing else {
                        re.sub(r"\$\{([^{}]+)\}", lambda m: source_values.get(m[1], "unused"), p) for p in providers}
                    for expression in constraints:
                        text = re.sub(r"\$\{([^{}]+)\}", lambda m: values.get(m[1], m[0]), expression)
                        text = re.sub(r"\$\{(interface\.[^{}]+)\}", lambda m: "1" if m[1] in available else "absent", text)
                        self.assertNotIn("${", text)
                        expressions.append(text)
                        wants.append(not missing and mismatch is None)
        # Independently transcribed M values from table50.7. Unique-channel
        # shifts/format/coefficients are deliberately absent from the signature.
        decimation = (125, 62, 42, 31, 25, 21, 18, 16, 14, 12, 11, 10, 9, 9, 8, 8)
        for source_div in range(16):
            for consumer_div in range(16):
                for order in range(1, 5):
                    values = {"module.driver.pdm.channel": "0", "module.driver.pdm.physical_input": "2",
                              "module.driver.pdm.input": "module.driver.pdm.input.falling",
                              "module.driver.pdm.sinc_order": f"module.driver.pdm.sinc_order.{order}",
                              "module.driver.pdm.clock_div": f"module.driver.pdm.clock_div.{consumer_div}",
                              "module.driver.pdm.fifo_threshold": "module.driver.pdm.fifo_threshold.4"}
                    source_values = {**values, "module.driver.pdm.channel": "2",
                                     "module.driver.pdm.input": "module.driver.pdm.input.rising",
                                     "module.driver.pdm.clock_div": f"module.driver.pdm.clock_div.{source_div}"}
                    available = {re.sub(r"\$\{([^{}]+)\}", lambda m: source_values.get(m[1], "unused"), p)
                                 for p in providers}
                    for expression in constraints:
                        text = re.sub(r"\$\{([^{}]+)\}", lambda m: values.get(m[1], m[0]), expression)
                        text = re.sub(r"\$\{(interface\.[^{}]+)\}", lambda m: "1" if m[1] in available else "absent", text)
                        expressions.append(text)
                        wants.append(decimation[source_div] == decimation[consumer_div])
        script = ('const testExists = x => x === "1"; '
                  'console.log(JSON.stringify(JSON.parse(require("fs").readFileSync(0,"utf8")).map(x=>eval(x))));')
        run = subprocess.run([node, "-e", script], input=json.dumps(expressions), capture_output=True, text=True, check=True)
        self.assertEqual(wants, json.loads(run.stdout))


if __name__ == "__main__":
    unittest.main()
