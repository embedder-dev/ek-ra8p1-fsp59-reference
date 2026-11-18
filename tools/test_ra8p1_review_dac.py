"""DAC-001: execute production DAC_B C at the calibration polling boundary.

Oracle: RA8P1 HM 60.5.24 p3578 and 60.10 p3629; terminal TRBUSY, not
remaining polling iterations, determines completion. No target hardware used.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FSP = ROOT / "baseline/ra/fsp"
FIXTURE = ROOT / "tools/ra8p1/review_dac"


class DacCalibrationBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("cc")
        if not compiler:
            raise unittest.SkipTest("native C compiler unavailable")
        cls.directory = tempfile.TemporaryDirectory(prefix="review-dac-")
        cls.addClassCleanup(cls.directory.cleanup)
        tmp = Path(cls.directory.name)
        device = (FSP / "src/bsp/cmsis/Device/RENESAS/Include/R7KA8P1KF.h").read_text()
        registers = []
        for name in ("R_DAC_B0_Type", "R_MRAM_Type"):
            end = device.index("} " + name + ";") + len("} " + name + ";")
            start = device.rfind("typedef struct", 0, end)
            registers.append(device[start:end])
        (tmp / "dac_registers.h").write_text("\n".join(registers))
        features = (FSP / "src/bsp/mcu/ra8p1/bsp_feature.h").read_text()
        mask = next(line for line in features.splitlines()
                    if line.startswith("#define BSP_FEATURE_DAC_B_CHANNEL_MASK "))
        (tmp / "bsp_api.h").write_text('#include "fixture_bsp.h"\n' + mask + "\n")
        cls.binaries = {}
        for checking in (0, 1):
            for nonsecure in (0, 1):
                binary = tmp / f"dac-{checking}-{nonsecure}"
                command = [compiler, "-std=c11", "-Wall", "-Wextra", "-Wconversion", "-Wshadow", "-Werror",
                           "-fsanitize=undefined", "-fno-sanitize-recover=all",
                           f"-DDAC_B_CFG_PARAM_CHECKING_ENABLE={checking}",
                           f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}",
                           f"-DBSP_TZ_SECURE_BUILD={1 - nonsecure}",
                           "-I" + str(tmp), "-I" + str(FIXTURE), "-I" + str(FSP / "inc"),
                           "-I" + str(FSP / "inc/api"), "-I" + str(FSP / "inc/instances"),
                           str(FSP / "src/r_dac_b/r_dac_b.c"), str(FIXTURE / "fixture.c"), "-o", str(binary)]
                # This is the sole generated configuration header needed by the production driver.
                (tmp / "r_dac_b_cfg.h").write_text("/* Checking selected on compiler command line. */\n")
                build = subprocess.run(command, capture_output=True, text=True, timeout=60)
                if build.returncode:
                    raise AssertionError(" ".join(command) + "\n" + build.stdout + build.stderr)
                cls.binaries[checking, nonsecure] = binary

    def run_case(self, case, nonsecure=0):
        for checking in (0, 1):
            with self.subTest(checking=checking, nonsecure=nonsecure):
                result = subprocess.run([str(self.binaries[checking, nonsecure]), case],
                                        capture_output=True, text=True, timeout=10,
                                        env={**os.environ, "UBSAN_OPTIONS": "halt_on_error=1"})
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertIn("production DAC_B: " + case + " passed", result.stdout)

    def test_immediate_completion_restores_saved_selection(self):
        self.run_case("immediate")

    def test_completion_before_budget_exhaustion(self):
        self.run_case("before_deadline")

    def test_completion_on_last_poll(self):
        self.run_case("last_poll")

    def test_completion_on_single_poll_budget(self):
        self.run_case("single_poll")

    def test_zeroization_on_last_poll_restores_selection_and_reports_error(self):
        self.run_case("zeroization")

    def test_still_busy_does_not_restore_selection(self):
        self.run_case("still_busy")

    def test_still_busy_with_zeroization_does_not_restore_selection(self):
        self.run_case("busy_zeroization")

    def test_existing_transfer_is_not_rewritten(self):
        self.run_case("already_busy")

    def test_nonsecure_requires_preloaded_calibration(self):
        self.run_case("nonsecure", nonsecure=1)


if __name__ == "__main__":
    unittest.main()
