"""ADC-008: execute the MDF's emitted guard against independent CMSE range grants."""
from pathlib import Path
import re
import shutil
import io
import zipfile
import tempfile
import unittest
import xml.etree.ElementTree as ET

import test_ra8p1_review_adc_mmio as mmio
from test_ra8p1_review_adc_mmio import ROOT, prepare, run

MDF = ROOT / "baseline/module_descriptions/Renesas##HAL Drivers##all##r_adc_b####5.9.0.xml"
FIXTURE = ROOT / "tools/ra8p1/review_adc_guard"


def scan_guard(xml):
    root = ET.fromstring(xml)
    text = root.find("module/guard/template").text
    begin = text.index("BSP_CMSE_NONSECURE_ENTRY fsp_err_t ${module.driver.adc.name}_scan_cfg_guard")
    end = text.index("BSP_CMSE_NONSECURE_ENTRY fsp_err_t", begin + 1)
    return text[begin:end].replace("${module.driver.adc.name}", "g_adc")


class AdcNestedGuardReviewTests(unittest.TestCase):
    def test_every_nested_range_and_count_before_secure_dereference(self):
        cc = shutil.which("cc")
        if not cc:
            self.skipTest("native compiler unavailable")
        with tempfile.TemporaryDirectory(prefix="review-adc-guard-") as directory:
            tmp = Path(directory)
            for checking in (0, 1):
                flags = prepare(tmp, checking)
                (tmp / "guard_function.h").write_text(scan_guard(MDF.read_text()))
                binary = tmp / "guard"
                run([cc, *flags, "-O2", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                     FIXTURE / "fixture.c", "-o", binary])
                for deny in range(-1, 15):
                    with self.subTest(checking=checking, deny=deny):
                        self.assertIn("nested CMSE guard oracle passed", run([binary, str(deny), "0"]))
                with self.subTest(checking=checking, mutation=True):
                    self.assertIn("nested CMSE guard oracle passed", run([binary, "-1", "1"]))

    def test_legacy_guard_tokens_are_byte_equivalent_after_preprocessing(self):
        with zipfile.ZipFile(ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip") as release:
            data = release.read("internal/projectgen/ra/packs/Renesas.RA.5.9.0.pack")
        with zipfile.ZipFile(io.BytesIO(data)) as pack:
            original = pack.read(".module_descriptions/" + MDF.name).decode()
        cc = shutil.which("cc")
        with tempfile.TemporaryDirectory(prefix="review-adc-guard-legacy-") as directory:
            tmp = Path(directory)
            for label, text in (("before", scan_guard(original)), ("after", scan_guard(MDF.read_text()))):
                (tmp / (label + ".c")).write_text(text)
            outputs = [run([cc, "-E", "-P", "-DBSP_FEATURE_ADC_B_REGISTER_TYPE=0", tmp / (label + ".c")])
                       for label in ("before", "after")]
            self.assertEqual(*[re.findall(r"\S+", text) for text in outputs])


class AdcGuardArmCompileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mmio.AdcReviewArmInstructionsTests.setUpClass.__func__(cls)

    def test_real_arm_cmse_intrinsics_compile_for_both_cores(self):
        with tempfile.TemporaryDirectory(prefix="review-adc-guard-arm-") as directory:
            tmp = Path(directory)
            flags = prepare(tmp, checking=1)
            source = tmp / "guard.c"
            source.write_text('#include <arm_cmse.h>\n#include "r_adc_b.h"\n'
                              '#define BSP_CMSE_NONSECURE_ENTRY __attribute__((cmse_nonsecure_entry))\n'
                              'extern adc_b_instance_ctrl_t g_adc_ctrl;\n' + scan_guard(MDF.read_text()))
            for core in ("cortex-m85", "cortex-m33"):
                with self.subTest(core=core):
                    run([self.cc, *flags, "-mthumb", "-mcpu=" + core, "-mcmse", "-mfloat-abi=soft", "-Os",
                         "-fstack-usage", "-c", source, "-o", tmp / (core + ".o")])


if __name__ == "__main__":
    unittest.main()
