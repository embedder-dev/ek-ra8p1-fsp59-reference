"""TEST-010/011: independent software timing/order gates and executable mutants.

DAC: HM55.3.2 p3504, Table70.114 p4258 (4ns setup, 6us worst-case stages).
FLL: HM9.11.5.2 p416, Table70.50 p4117 (1920us standard, 2150us SiP).
Runs production C on host RAM, not a physical timing qualification or IDE build.
"""
from pathlib import Path
import itertools
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FSP = ROOT / "baseline/ra/fsp"
FIXTURES = ROOT / "tools/ra8p1"
DAC = FSP / "src/r_dac_b/r_dac_b.c"
CGC = FSP / "src/r_cgc/r_cgc.c"


class PrimaryTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("cc")
        if cls.cc is None:
            raise RuntimeError("Native compiler required for independent temporal gates")

    def execute(self, command, binary):
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, " ".join(map(str, command)) + "\n" + result.stdout + result.stderr)
        return subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)

    def dac_run(self, source, checking=1, nonsecure=0):
        with tempfile.TemporaryDirectory(prefix="dac-temporal-") as temp:
            folder = Path(temp)
            (folder / "bsp_api.h").write_bytes((FIXTURES / "memory_analog_bsp.h").read_bytes())
            for driver in ("mram", "dac_b"):
                (folder / f"r_{driver}_cfg.h").write_text(
                    f"#define {driver.upper()}_CFG_PARAM_CHECKING_ENABLE {checking}\n")
            production, harness, binary = folder / "dac.c", folder / "timing.c", folder / "dac"
            production.write_text(source)
            # Reuse the owned timing assertions without executing unrelated MRAM operations.
            harness.write_text('#define main unused_memory_analog_main\n#include "memory_analog_fixture.c"\n'
                               '#undef main\nint main(void) { test_dac_b(); puts("DAC temporal gate passed"); return 0; }\n')
            includes = (folder, FIXTURES, FSP / "inc", FSP / "inc/api", FSP / "inc/instances",
                        FSP / "src/bsp/cmsis/Device/RENESAS/Include", FIXTURES / "layout/native")
            command = [self.cc, "-std=c11", "-Wall", "-Wextra", "-Wconversion", "-Wshadow", "-Werror",
                       "-fsanitize=undefined", "-fno-sanitize-recover=all", "-DTEST_DAC_B",
                       "-DMEMORY_ANALOG_REAL_HEADER=1", "-DBSP_CFG_CPU_CORE=0",
                       f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}", "-DBSP_TZ_SECURE_BUILD=0",
                       *[f"-I{path}" for path in includes], str(production), str(harness),
                       str(FSP / "src/r_mram/r_mram.c"), "-o", str(binary)]
            return self.execute(command, binary)

    def test_dac_software_stages_single_pair_and_elc_scope(self):
        for checking, nonsecure in itertools.product((0, 1), repeat=2):
            with self.subTest(checking=checking, nonsecure=nonsecure):
                result = self.dac_run(DAC.read_text(), checking, nonsecure)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("DAC temporal gate passed", result.stdout)

    def test_dac_short_setup_preparation_switch_conversion_and_pair_mutants_fail(self):
        source = DAC.read_text()
        for stage in ("setup", "preparation", "pair_preparation", "switch", "conversion", "sample_order"):
            if stage == "setup":
                mutant, count = re.subn(r"R_BSP_SoftwareDelay\(1U,", "R_BSP_SoftwareDelay(0U,", source)
                diagnostic = "1000U >= 4U"
            elif stage in ("preparation", "pair_preparation", "sample_order"):
                begin, end = source.index("fsp_err_t R_DAC_B_Start ("), source.index("fsp_err_t R_DAC_B_Stop (")
                replacement = {"preparation": "R_BSP_SoftwareDelay(1U,",
                               "pair_preparation": "R_BSP_SoftwareDelay((p_pair == NULL) ? 6U : 1U,",
                               "sample_order": "p_ctrl->p_reg->DADR = p_ctrl->sample; R_BSP_SoftwareDelay(6U,"}[stage]
                body, count = re.subn(r"R_BSP_SoftwareDelay\(6U,", replacement, source[begin:end])
                mutant = source[:begin] + body + source[end:]
                diagnostic = "dac_initial" if stage == "sample_order" else "delays[tick] >= 6U"
            else:
                # The output helper has exactly two 6us stages: destination switch, then conversion.
                begin = source.index("static void r_dac_b_output (dac_b_instance_ctrl_t * p_ctrl)\n{")
                body = source[begin:]
                matches = list(re.finditer(r"R_BSP_SoftwareDelay\(6U,", body))
                self.assertEqual(len(matches), 2)
                match = matches[0 if stage == "switch" else 1]
                mutant = source[:begin] + body[:match.start()] + "R_BSP_SoftwareDelay(1U," + body[match.end():]
                count, diagnostic = 1, "delays[tick] >= 6U"
            self.assertEqual(count, 1, stage)
            with self.subTest(stage=stage):
                result = self.dac_run(mutant)
                self.assertNotEqual(result.returncode, 0, "Timing/order mutant escaped: " + stage)
                self.assertIn(diagnostic, result.stderr)

    def cgc_run(self, source, minimum, core=0, checking=1):
        with tempfile.TemporaryDirectory(prefix="fll-temporal-") as temp:
            folder = Path(temp)
            production, binary = folder / "cgc.c", folder / "cgc"
            production.write_text(source)
            harness = folder / "fll.c"
            harness.write_text('#define main unused_cgc_matrix_main\n#include "harness.c"\n#undef main\n'
                               'int main(void) { reset_fixture(); cgc_instance_ctrl_t ctrl; open_control(&ctrl);\n'
                               'assert(!R_SYSTEM->OSCSF_b.HOCOSF && fll_elapsed_us == 0U);\n'
                               'assert(R_CGC_ClockStart(&ctrl, CGC_CLOCK_HOCO, NULL) == FSP_SUCCESS);\n'
                               'assert(R_CGC_ClockCheck(&ctrl, CGC_CLOCK_HOCO) == FSP_SUCCESS);\n'
                               'assert(fll_started && fll_hoco_ready && R_SYSTEM->OSCSF_b.HOCOSF);\n'
                               'fll_settled(); assert(fll_elapsed_us >= TEST_FLL_MIN_US);\n'
                               'puts("FLL temporal gate passed"); return 0; }\n')
            mcu = FSP / "src/bsp/mcu"
            includes = (FIXTURES / "cgc_test", mcu / "ra8p1", mcu / "all", FIXTURES / "layout/native",
                        FSP / "inc/instances", FSP / "inc/api", FSP / "src/bsp/cmsis/Device/RENESAS/Include")
            command = [self.cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined",
                       "-fno-sanitize-recover=all", "-DTEST_TARGET=1", f"-DTEST_CORE={core}",
                       f"-DTEST_CHECKS={checking}", "-DTEST_XTAL_HZ=24000000", "-DTEST_FLL=1",
                       f"-DTEST_FLL_MIN_US={minimum}", f"-DBSP_PRV_FLL_STABILIZATION_TIME_US={minimum}",
                       *[f"-I{path}" for path in includes], str(production),
                       str(harness), "-o", str(binary)]
            return self.execute(command, binary)

    def test_fll_flag_and_elapsed_standard_and_sip(self):
        for minimum, core, checking in itertools.product((1920, 2150), (0, 1), (0, 1)):
            with self.subTest(minimum=minimum, core=core, checking=checking):
                result = self.cgc_run(CGC.read_text(), minimum, core, checking)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("FLL temporal gate passed", result.stdout)

    def test_fll_one_microsecond_is_not_stability_flag_completion(self):
        source, count = re.subn(r"R_BSP_SoftwareDelay\(\(BSP_PRV_FLL_STABILIZATION_TIME_US > 1920U\)\s*\?\s*"
                                r"BSP_PRV_FLL_STABILIZATION_TIME_US : 1920U, BSP_DELAY_UNITS_MICROSECONDS\);",
                                "R_BSP_SoftwareDelay(1U, BSP_DELAY_UNITS_MICROSECONDS);", CGC.read_text())
        self.assertEqual(count, 1, "Locate the real production FLL settling call")
        for minimum in (1920, 2150):
            with self.subTest(minimum=minimum):
                result = self.cgc_run(source, minimum)
                self.assertNotEqual(result.returncode, 0, "1us FLL delay escaped the elapsed-time oracle")
                self.assertIn("fll_elapsed_us >= TEST_FLL_MIN_US", result.stderr)


if __name__ == "__main__":
    unittest.main()
