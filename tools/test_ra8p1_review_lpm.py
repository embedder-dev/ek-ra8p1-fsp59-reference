"""Requirement-based complete production LPM tests (no physical power claim)."""
from pathlib import Path
import itertools
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

from test_ra8p1_lpm import CORE
from test_ra8p1_wdt import executable_sections

ROOT = Path(__file__).resolve().parents[1]
FSP = ROOT / "baseline/ra/fsp"
SOURCE = FSP / "src/r_lpm/r_lpm.c"
FIXTURES = ROOT / "tools/ra8p1/review_lpm"
MDF = ROOT / "baseline/module_descriptions/Renesas##BSP##ra8p1##fsp####5.9.0.xml"


class ReviewLpmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("cc")
        if not cls.cc:
            raise RuntimeError("Native C compiler required")

    def checked(self, command):
        run = subprocess.run(command, capture_output=True, text=True, timeout=90)
        self.assertEqual(run.returncode, 0, " ".join(map(str, command)) + "\n" + run.stdout + run.stderr)
        return run.stdout

    def command(self, directory, core=0, checks=1, limit=0, target=1, legacy="ra8m1", neptune=0):
        (directory / "core_cm85.h").write_text(CORE)
        (directory / "core_cm33.h").write_text(CORE)
        (directory / "r_lpm_cfg.h").write_text(
            f"#define LPM_CFG_PARAM_CHECKING_ENABLE {checks}\n#define LPM_CFG_STANDBY_LIMIT {limit}\n")
        return [self.cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                f"-DTEST_TARGET={target}", f"-DBSP_CFG_CPU_CORE={core}",
                f"-DBSP_MCU_GROUP_NEPTUNE={neptune}", f"-DTEST_LEGACY_RA6T2={int(legacy == 'ra6t2')}",
                "-I" + str(FIXTURES), "-I" + str(directory),
                "-I" + str(FSP / "src/bsp/cmsis/Device/RENESAS/Include"),
                "-I" + str(FSP / "src/bsp/mcu" / ("ra8p1" if target else legacy)),
                "-I" + str(FSP / "inc/api"), "-I" + str(FSP / "inc/instances"), "-I" + str(FSP / "inc")]

    def test_production_requirements_both_cores_checks_limits(self):
        with tempfile.TemporaryDirectory(prefix="review-lpm-") as temporary:
            directory = Path(temporary)
            for core, checks, limit in itertools.product((0, 1), repeat=3):
                binary = directory / "review-lpm"
                self.checked(self.command(directory, core, checks, limit) +
                             ["-fsanitize=undefined", "-fno-sanitize-recover=all", str(SOURCE),
                              str(FIXTURES / "fixture.c"), "-o", str(binary)])
                for requirement in ("retention", "wake", "nmi", "invalid", "oscillator"):
                    with self.subTest(core=core, checks=checks, limit=limit, requirement=requirement):
                        self.checked([str(binary), requirement])

    def test_target_metadata_complete_grouped_retention_and_wakes(self):
        tree = ET.parse(MDF)
        enums = {node.attrib["id"]: node for node in tree.findall(".//enum")}
        for suffix, rising in (("standby_wake_sources", False),
                               ("deep_standby_cancel_sources", False),
                               ("deep_standby_cancel_edges", True)):
            options = {node.attrib["value"] for node in enums["enum.mcu.lpm." + suffix]}
            self.assertTrue({f"IRQ{i}" + ("_RISING" if rising else "") for i in range(32)} <= options)
        wake = {node.attrib["value"] for node in enums["enum.mcu.lpm.standby_wake_sources"]}
        self.assertTrue({"SOSTD", "PDM"} <= wake)
        regions = enums["enum.mcu.lpm.ram_power_enable"]
        self.assertEqual({int(node.attrib["value"].rstrip("UuLl"), 0) for node in regions},
                         {0xF, 0xF0, 0xF00, 0x1000})
        self.assertEqual(len(regions), 4)
        tcm = enums["enum.mcu.lpm.tcm_power_enable"]
        self.assertTrue(all("current" in node.attrib["display"].lower() for node in tcm))

    def test_legacy_preprocessing_and_objects_include_assertion_lines(self):
        pristine = self.checked(["git", "-C", str(ROOT / "baseline"), "show", "HEAD:ra/fsp/src/r_lpm/r_lpm.c"])
        with tempfile.TemporaryDirectory(prefix="review-lpm-legacy-") as temporary:
            directory = Path(temporary)
            before = directory / "pristine.c"
            before.write_text(pristine)
            for legacy, checks, limit, neptune in itertools.product(("ra8m1", "ra6t2"), (0, 1), (0, 1), (0, 1)):
                with self.subTest(legacy=legacy, checks=checks, limit=limit, neptune=neptune):
                    command = self.command(directory, checks=checks, limit=limit, target=0,
                                           legacy=legacy, neptune=neptune)
                    preprocessed = []
                    objects = []
                    for index, source in enumerate((before, SOURCE)):
                        # -P removes location markers, not __LINE__ assertion values.
                        preprocessed.append(self.checked(command + ["-E", "-P", str(source)]))
                        obj = directory / f"{index}.o"
                        self.checked(command + ["-O2", "-c", str(source), "-o", str(obj)])
                        objects.append(executable_sections(obj))
                    self.assertEqual(preprocessed[0].split(), preprocessed[1].split())
                    self.assertEqual(objects[0], objects[1])

    def test_driver_crlf_preserved(self):
        data = SOURCE.read_bytes()
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))


if __name__ == "__main__":
    unittest.main()
