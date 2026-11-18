"""Full production CGC translation-unit tests with real device and API headers."""
from pathlib import Path
import itertools
import shutil
import subprocess
import tempfile
import unittest

from tools.test_ra8p1_wdt import executable_sections

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
PRODUCTION = BASELINE / "ra/fsp/src/r_cgc/r_cgc.c"
FIXTURES = ROOT / "tools/ra8p1/cgc_test"
MCU = BASELINE / "ra/fsp/src/bsp/mcu"


class CgcProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("cc")
        if cls.cc is None:
            raise RuntimeError("A native C compiler is required for production CGC tests")

    def compile(self, destination, source, *, target=1, core=0, checks=1, xtal=24000000,
                fll=0, object_only=False, capabilities=None):
        command = [self.cc, "-std=c11", "-Wall", "-Wextra", "-Werror"]
        device = {0: "ra8m1", 1: "ra8p1", 2: "ra4m3"}[target]
        includes = (FIXTURES, MCU / device, MCU / "all",
                    ROOT / "tools/ra8p1/layout/native", BASELINE / "ra/fsp/inc/instances",
                    BASELINE / "ra/fsp/inc/api",
                    BASELINE / "ra/fsp/src/bsp/cmsis/Device/RENESAS/Include")
        command += [f"-I{path}" for path in includes]
        command += [f"-DTEST_TARGET={target}", f"-DTEST_CORE={core}", f"-DTEST_CHECKS={checks}",
                    f"-DTEST_XTAL_HZ={xtal}", f"-DTEST_FLL={fll}"]
        if capabilities is not None:
            command += [f"-DTEST_BCLKA={capabilities[0]}", f"-DTEST_ESW={capabilities[1]}"]
        if object_only:
            command += ["-O2", "-c", str(source)]
        else:
            command += ["-fsanitize=undefined", "-fno-sanitize-recover=all", str(source),
                        str(FIXTURES / "harness.c")]
        command += ["-o", str(destination)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, "Production CGC harness cannot compile:\n"
                         + " ".join(command) + "\n" + result.stdout + result.stderr)

    def test_production_cgc_behavior(self):
        with tempfile.TemporaryDirectory(prefix="cgc-test-") as temp:
            for core, checks, fll in itertools.product((0, 1), (0, 1), (0, 1)):
                with self.subTest(core=core, checks=checks, fll=fll):
                    binary = Path(temp) / "cgc"
                    self.compile(binary, PRODUCTION, core=core, checks=checks, fll=fll)
                    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("production CGC behavior passed", result.stdout)
                    self.assertIn("runtime peripheral-consumer protection passed: 144 cases", result.stdout)

    def test_peripheral_capabilities_independently_gated(self):
        with tempfile.TemporaryDirectory(prefix="cgc-gates-") as temp:
            for capabilities, core, checks in itertools.product(((0, 0), (1, 0), (0, 1)), (0, 1), (0, 1)):
                with self.subTest(capabilities=capabilities, core=core, checks=checks):
                    binary = Path(temp) / "cgc"
                    self.compile(binary, PRODUCTION, core=core, checks=checks, capabilities=capabilities)
                    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("runtime peripheral-consumer protection passed: 144 cases", result.stdout)

    def test_legacy_executable_sections_match_pristine_head(self):
        pristine = subprocess.run(
            ["git", "-C", str(BASELINE), "show", "HEAD:ra/fsp/src/r_cgc/r_cgc.c"],
            capture_output=True, timeout=10)
        self.assertEqual(pristine.returncode, 0, pristine.stderr.decode())
        with tempfile.TemporaryDirectory(prefix="cgc-legacy-") as temp:
            directory = Path(temp)
            original = directory / "pristine.c"
            original.write_bytes(pristine.stdout)
            for target, checks, fll in itertools.product((0, 2), (0, 1), (0, 1)):
                with self.subTest(target=target, checks=checks, fll=fll):
                    before, after = directory / "before.o", directory / "after.o"
                    self.compile(before, original, target=target, checks=checks, fll=fll, object_only=True)
                    self.compile(after, PRODUCTION, target=target, checks=checks, fll=fll, object_only=True)
                    self.assertEqual(executable_sections(before), executable_sections(after))


if __name__ == "__main__":
    unittest.main()
