"""WDT-001/003: execute the complete production C with the stock public headers.

Primary oracles: RA8P1 HM14.2.14 pp545-547 (mixed R/W NMIER enables) and
HM28.3.1 pp1273-1275 (option-memory, not stack fields, configures autostart).
Host register fixtures do not establish NMI routing or hardware timing.
"""

import itertools
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_ra8p1_wdt import configuration, executable_sections

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
PRODUCTION = BASELINE / "ra/fsp/src/r_wdt/r_wdt.c"
BSP = BASELINE / "ra/fsp/src/bsp/mcu"
FIXTURE = ROOT / "tools/ra8p1/review_wdt"
MODES = (
    (False, True, True),
    (False, False, True),
    (False, False, False),
    (True, True, True),
    (True, False, True),
)


class ReviewWdtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("cc")
        if cls.cc is None:
            raise RuntimeError("A native C compiler is required")
        cls.temp = tempfile.TemporaryDirectory(prefix="review-wdt-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        cls.binaries = {}
        original = subprocess.run(
            ["git", "-C", str(BASELINE), "show", "HEAD:ra/fsp/src/r_wdt/r_wdt.c"],
            capture_output=True, timeout=10, check=True,
        ).stdout
        cls.original = cls.directory / "pristine.c"
        cls.original.write_bytes(original)

    def command(self, device, core, checks, mode):
        defines = configuration(int(device == "ra8p1"), core, checks, *mode)
        return [
            self.cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-I", str(FIXTURE), "-I", str(BSP / device),
            "-I", str(ROOT / "tools/ra8p1/wdt_test"),
            "-I", str(BASELINE / "ra/fsp/inc/instances"),
            "-I", str(BASELINE / "ra/fsp/inc/api"),
        ] + [f"-D{key}={value}" for key, value in defines.items()]

    def run_command(self, command):
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0,
                         " ".join(map(str, command)) + "\n" + result.stdout + result.stderr)
        return result

    def binary(self, device, core, checks, mode):
        key = (device, core, checks, mode)
        if key not in self.binaries:
            binary = self.directory / f"wdt-{len(self.binaries)}"
            command = self.command(*key) + [
                "-fsanitize=undefined", "-fno-sanitize-recover=all",
                str(PRODUCTION), str(FIXTURE / "harness.c"), "-o", str(binary),
            ]
            if sys.platform == "darwin" and device == "ra8p1" and core == 1:
                # Darwin arm64 PAGEZERO excludes the actual low option addresses; x86_64 permits them.
                command += ["-arch", "x86_64", "-Wl,-pagezero_size,0x4000", "-Wl,-no_pie"]
            self.run_command(command)
            self.binaries[key] = binary
        return self.binaries[key]

    def test_target_preserves_mixed_nmier_enables_both_cores_checks_and_modes(self):
        for core, checks, mode in itertools.product((0, 1), (0, 1), MODES):
            with self.subTest(core=core, checks=checks, mode=mode):
                binary = self.binary("ra8p1", core, checks, mode)
                self.run_command([str(binary), "preservation"])

    def test_target_autostart_ignores_zero_and_invalid_unused_fields(self):
        for core, checks, mode in itertools.product((0, 1), (0, 1), MODES[3:]):
            with self.subTest(core=core, checks=checks, mode=mode):
                binary = self.binary("ra8p1", core, checks, mode)
                self.run_command([str(binary), "autostart"])

    def test_target_register_start_still_checks_consumed_fields(self):
        for core, checks, mode in itertools.product((0, 1), (0, 1), MODES[:3]):
            with self.subTest(core=core, checks=checks, mode=mode):
                binary = self.binary("ra8p1", core, checks, mode)
                self.run_command([str(binary), "register"])

    def test_legacy_behavior_preprocessing_and_executable_sections_match_pristine(self):
        # Three pre-existing series, including the nearest sibling and motor-control MCU.
        for device, checks, mode in itertools.product(
                ("ra8m1", "ra6t2", "ra2l1"), (0, 1), MODES):
            with self.subTest(device=device, checks=checks, mode=mode):
                command = self.command(device, 0, checks, mode)
                preprocessed = [self.run_command(command + ["-E", "-P", str(source)]).stdout
                                for source in (self.original, PRODUCTION)]
                self.assertEqual(*preprocessed, "Legacy preprocessed production C changed")
                objects = [self.directory / "before.o", self.directory / "after.o"]
                for source, obj in zip((self.original, PRODUCTION), objects):
                    self.run_command(command + ["-O2", "-c", str(source), "-o", str(obj)])
                self.assertEqual(*(executable_sections(obj) for obj in objects),
                                 "Legacy executable object sections changed")
                binary = self.binary(device, 0, checks, mode)
                self.run_command([str(binary), "preservation"])
                if mode[0]:
                    self.run_command([str(binary), "autostart"])

    def test_existing_capabilities_select_legacy_paths_for_all_32_older_devices(self):
        headers = sorted(path for path in BSP.glob("*/bsp_feature.h")
                         if path.parent.name != "ra8p1")
        self.assertEqual(len(headers), 32)
        for header in headers:
            with self.subTest(device=header.parent.name):
                text = header.read_text()
                maximum = re.search(r"#define\s+BSP_FEATURE_ICU_NMIER_MAX_INDEX\s+\((\d+)UL\)", text)
                per_core = re.search(r"#define\s+BSP_FEATURE_WDT_PER_CORE\s+\((\d+)UL\)", text)
                self.assertIsNotNone(maximum)
                self.assertIsNotNone(per_core)
                self.assertLessEqual(int(maximum[1]), 15)
                self.assertEqual(int(per_core[1]), 0)

    def test_source_preserves_crlf_and_stock_nmier_statement(self):
        raw = PRODUCTION.read_bytes()
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"))
        original = self.original.read_text()
        legacy = ("    /* Enable the WDT underflow/refresh error interrupt (will generate an NMI). "
                  "NMIER bits cannot be cleared after reset,\n"
                  "     * so no need to read-modify-write. */\n"
                  "    R_ICU->NMIER = R_ICU_NMIER_WDTEN_Msk;")
        self.assertIn(legacy, original)
        self.assertIn(legacy, PRODUCTION.read_text())


if __name__ == "__main__":
    unittest.main()
