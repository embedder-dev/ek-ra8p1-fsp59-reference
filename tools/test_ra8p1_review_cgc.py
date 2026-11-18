"""Independent production-C regressions for confirmed CGC-001 through CGC-010.

Primary anchors are recorded in review_cgc/fixture.c. No extracted/reimplemented
transition code is tested: the entire owning r_cgc.c and real API/header compile.
"""
from pathlib import Path
import itertools
import re
import shutil
import subprocess
import tempfile
import unittest

from tools import test_ra8p1_cgc as legacy
from tools.test_ra8p1_cgc import BASELINE, MCU, PRODUCTION, FIXTURES

REVIEW = Path(__file__).resolve().parent / "ra8p1/review_cgc"


class ReviewCgcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("cc")
        if not cls.cc:
            raise RuntimeError("A native C compiler is required")
        cls.temp = tempfile.TemporaryDirectory(prefix="review-cgc-")
        cls.directory = Path(cls.temp.name)
        cls.binaries = {}
        for core, checks, fll in itertools.product((0, 1), repeat=3):
            binary = cls.directory / f"cgc-{core}-{checks}-{fll}"
            command = cls.command(core=core, checks=checks, fll=fll) + [
                "-fsanitize=undefined", "-fno-sanitize-recover=all", str(PRODUCTION),
                str(REVIEW / "fixture.c"), "-o", str(binary)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            if result.returncode:
                cls.temp.cleanup()
                raise AssertionError(" ".join(command) + "\n" + result.stdout + result.stderr)
            cls.binaries[core, checks, fll] = binary

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def command(cls, *, core=0, checks=1, fll=0, target=1):
        device = {0: "ra8m1", 1: "ra8p1", 2: "ra4m3"}[target]
        includes = (REVIEW, FIXTURES, MCU / device, MCU / "all",
                    FIXTURES.parent / "layout/native", BASELINE / "ra/fsp/inc/instances",
                    BASELINE / "ra/fsp/inc/api",
                    BASELINE / "ra/fsp/src/bsp/cmsis/Device/RENESAS/Include")
        return [cls.cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                *[f"-I{path}" for path in includes], f"-DTEST_CORE={core}",
                f"-DTEST_TARGET={target}", f"-DTEST_CHECKS={checks}",
                f"-DTEST_FLL={fll}", "-DTEST_XTAL_HZ=24000000"]

    def case(self, number, *, flls=(0, 1)):
        for core, checks, fll in itertools.product((0, 1), (0, 1), flls):
            with self.subTest(core=core, checks=checks, fll=fll):
                result = subprocess.run([str(self.binaries[core, checks, fll]), str(number)],
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f"CGC-{number:03d} passed", result.stdout)

    def test_001_output_specific_limit(self): self.case(1)
    def test_002_prospective_hoco_cpu0_limit(self): self.case(2)
    def test_003_all_async_selectors_and_pll_inputs(self): self.case(3)
    def test_004_direct_hoco_fll_settling(self): self.case(4)
    def test_005_stop_hoco_before_disabling_fll(self): self.case(5, flls=(1,))
    def test_006_sosc_required_while_fll_enabled(self): self.case(6)
    def test_007_stabilization_reference_order(self): self.case(7)
    def test_008_none_uses_running_pll_source(self): self.case(8)
    def test_009_busy_precedes_loco_access(self): self.case(9)
    def test_010_primary_nmi_ownership_and_rmw(self): self.case(10)

    def test_legacy_complete_tu_executable_parity(self):
        # Existing full-TU object gate: RA8M1(type3) and RA4M3(type1), checks/FLL on/off.
        test = legacy.CgcProductionTests("test_legacy_executable_sections_match_pristine_head")
        test.cc = self.cc
        test.test_legacy_executable_sections_match_pristine_head()

    def test_all_legacy_preprocessed_parity_and_crlf(self):
        before = subprocess.run(["git", "-C", str(BASELINE), "show",
                                 "HEAD:ra/fsp/src/r_cgc/r_cgc.c"], capture_output=True, timeout=10)
        self.assertEqual(before.returncode, 0, before.stderr.decode())
        original = self.directory / "original.c"
        original.write_bytes(before.stdout)
        devices = sorted(p for p in MCU.glob("*/bsp_feature.h") if p.parent.name != "ra8p1")
        self.assertEqual(len(devices), 32)
        for device, checks, fll in itertools.product(devices, (0, 1), (0, 1)):
            with self.subTest(device=device.parent.name, checks=checks, fll=fll):
                # Preprocessing does not require a fabricated device layout. The actual
                # per-device feature data selects all32 legacy conditional paths.
                cmd = self.command(target=0, checks=checks, fll=fll) + ["-include", str(device), "-E", "-P"]
                tokens = []
                for path in (original, PRODUCTION):
                    result = subprocess.run(cmd + [str(path)], capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    tokens.append(re.findall(r'\w+|[^\s\w]', result.stdout))
                self.assertEqual(tokens[0], tokens[1], "Legacy preprocessed output changed")
        data = PRODUCTION.read_bytes()
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""), "Production CRLF must be preserved")


if __name__ == "__main__":
    unittest.main()
