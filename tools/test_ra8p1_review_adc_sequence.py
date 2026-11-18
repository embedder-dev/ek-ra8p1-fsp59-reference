"""ADC-001..006/013: independently anchored production-C behavior regressions."""
import itertools
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import test_ra8p1_review_adc_mmio as mmio
from test_ra8p1_review_adc_mmio import ROOT, SOURCE, prepare, run

FIXTURE = ROOT / "tools/ra8p1/review_adc_sequence"


class AdcSequenceReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = shutil.which("cc")
        if not cc:
            raise unittest.SkipTest("native compiler unavailable")
        cls.directory = tempfile.TemporaryDirectory(prefix="review-adc-sequence-")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.binaries = {}
        for checking in (0, 1):
            tmp = Path(cls.directory.name) / str(checking)
            tmp.mkdir()
            flags = prepare(tmp, checking)
            flags.insert(0, "-I" + str(FIXTURE))
            binary = tmp / "fixture"
            run([cc, *flags, '-DREVIEW_SOURCE="' + str(SOURCE) + '"', "-O2", "-fstrict-aliasing",
                 "-fsanitize=undefined", "-fno-sanitize-recover=all", FIXTURE / "fixture.c", "-o", binary])
            cls.binaries[checking] = binary

    def case(self, checking, *args):
        self.assertIn("ADC sequence oracle passed", run([self.binaries[checking], *map(str, args)]))

    def test_stop_delay_actual_group_and_clock_domains(self):
        for checking, source, divider, sync in itertools.product((0, 1), range(3), range(6), (0, 1)):
            with self.subTest(checking=checking, source=source, divider=divider, sync=sync):
                self.case(checking, "wait", source, divider, sync)

    def test_calibration_uses_each_converters_timing(self):
        for checking in (0, 1):
            self.case(checking, "calibration")

    def test_synchronous_scan_uses_asynchronous_calibration_then_restores_sync(self):
        for checking in (0, 1):
            self.case(checking, "ysync")

    def test_sample_hold_restores_differential_modes(self):
        for checking in (0, 1):
            self.case(checking, "sample_hold")

    def test_final_callback_can_restart_without_post_callback_wait_or_write(self):
        for checking, unit in itertools.product((0, 1), repeat=2):
            self.case(checking, "restart", unit)

    def test_error_isr_retains_failure_after_status_clear_without_callback(self):
        for checking, unit, overflow, callback in itertools.product((0, 1), repeat=4):
            with self.subTest(checking=checking, unit=unit, overflow=overflow, callback=callback):
                self.case(checking, "error", unit, overflow, callback)

    def test_actual_virtual_channel_order_not_configuration_array_order(self):
        self.case(1, "admission", 0)
        self.case(1, "admission", 1)

    def test_same_sample_hold_unit_cannot_mix_input_modes(self):
        self.case(1, "admission", 2)

    def test_minimum_phase_is_rejected_for_all_four_filters_both_converters(self):
        for unit, filter_id in itertools.product((0, 1), range(4)):
            self.case(1, "filter", unit, filter_id)

    def test_hybrid_channel_count_and_mandatory_exclusive_sinc_filters(self):
        for case in range(3, 8):
            with self.subTest(case=case):
                self.case(1, "admission", case)


class AdcSequenceLegacyArmParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mmio.AdcReviewArmInstructionsTests.setUpClass.__func__(cls)

    def test_legacy_arm_objects_are_identical_both_cores_checks_and_optimizations(self):
        with tempfile.TemporaryDirectory(prefix="review-adc-legacy-arm-") as directory:
            tmp = Path(directory)
            original = tmp / "original"
            original.mkdir()
            for relative in ("ra/fsp/src/r_adc_b/r_adc_b.c", "ra/fsp/inc/instances/r_adc_b.h"):
                data = subprocess.run(["git", "-C", str(ROOT / "baseline"), "show", "HEAD:" + relative],
                                      check=True, capture_output=True).stdout
                (original / Path(relative).name).write_bytes(data)
            for core, checking, optimization in itertools.product(
                    ("cortex-m85", "cortex-m33"), (0, 1), ("-O0", "-Og", "-O2", "-Os")):
                with self.subTest(core=core, checking=checking, optimization=optimization):
                    flags = prepare(tmp, checking, variant=0)
                    common = [self.cc, *flags, "-mthumb", "-mcpu=" + core, "-mfloat-abi=soft", optimization]
                    run([*common, "-I" + str(original), "-c", original / "r_adc_b.c", "-o", tmp / "before.o"])
                    run([*common, "-c", SOURCE, "-o", tmp / "after.o"])
                    self.assertEqual((tmp / "before.o").read_bytes(), (tmp / "after.o").read_bytes())


if __name__ == "__main__":
    unittest.main()
