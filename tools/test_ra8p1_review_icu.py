"""ICU-001..004: execute complete production C with unchanged FSP public headers.

Independent oracles: RA8P1 HM14.2.12 pp539-540 (channels0-31, trigger0-3,
reserved bit2 zero) and HM14.2.17 pp551-552 (IELSR0-95, IR=1 prohibited).
Register fixtures model inactive input factors, not physical IRQ timing or
cross-core channel arbitration. No generated projects or hardware are used.
"""
import itertools
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from test_ra8p1_wdt import executable_sections

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
PRODUCTION = BASELINE / "ra/fsp/src/r_icu/r_icu.c"
BSP = BASELINE / "ra/fsp/src/bsp/mcu"
FIXTURE = ROOT / "tools/ra8p1/review_icu"


class ReviewIcuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("cc")
        if cls.cc is None:
            raise RuntimeError("A native C compiler is required")
        cls.temp = tempfile.TemporaryDirectory(prefix="review-icu-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        cls.binaries = {}
        cls.original = cls.directory / "pristine.c"
        cls.original.write_bytes(subprocess.run(
            ["git", "-C", str(BASELINE), "show", "HEAD:ra/fsp/src/r_icu/r_icu.c"],
            capture_output=True, check=True, timeout=10,
        ).stdout)

    def command(self, device, core, checking):
        return [
            self.cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
            f"-DBSP_CFG_CPU_CORE={core}",
            f"-DICU_CFG_PARAM_CHECKING_ENABLE={checking}",
            "-I", str(FIXTURE), "-I", str(BSP / device),
            "-I", str(BASELINE / "ra/fsp/inc/instances"),
            "-I", str(BASELINE / "ra/fsp/inc/api"),
        ]

    def run_command(self, command):
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode,
                         " ".join(map(str, command)) + "\n" + result.stdout + result.stderr)
        return result

    def binary(self, core, checking):
        key = (core, checking)
        if key not in self.binaries:
            binary = self.directory / f"icu-{core}-{checking}"
            self.run_command(self.command("ra8p1", core, checking) + [
                "-fsanitize=undefined", "-fno-sanitize-recover=all",
                str(PRODUCTION), str(FIXTURE / "fixture.c"), "-o", str(binary),
            ])
            self.binaries[key] = binary
        return self.binaries[key]

    def run_case(self, case, *arguments, modes=(0, 1)):
        for core, checking in itertools.product((0, 1), modes):
            with self.subTest(core=core, checking=checking, case=case, arguments=arguments):
                result = self.run_command([str(self.binary(core, checking)), case,
                                           *map(str, arguments)])
                self.assertIn(f"production ICU: {case} passed", result.stdout)

    def test_all_supported_channels_triggers_filters_dividers_both_cores_and_checking_modes(self):
        self.run_case("supported")

    def test_pending_ir_is_never_restored_but_event_and_dtce_survive(self):
        self.run_case("pending")

    def test_vectorless_elc_open_never_indexes_ielsr_or_configures_nvic(self):
        self.run_case("vectorless")

    def test_unsupported_trigger_rejected_without_any_side_effects(self):
        for trigger in (4, 5, 7, 255, 0xFFFFFFFF):
            self.run_case("trigger", trigger, modes=(1,))

    def test_invalid_channels_rejected_before_undefined_shift_or_side_effects(self):
        for channel in (32, 33, 63, 64, 65, 127, 128, 255):
            self.run_case("channel", channel, modes=(1,))

    def test_parameter_admission_is_not_enabled_when_checking_is_disabled(self):
        self.run_case("unchecked", modes=(0,))

    def test_legacy_tokens_and_executable_objects_match_stock_for_representative_devices(self):
        # Filter/no filter, IELSR/no IELSR, and the LOCO-filter variant.
        for device, checking in itertools.product(
                ("ra8m1", "ra6t2", "ra2l1", "ra0e1", "ra4l1"), (0, 1)):
            with self.subTest(device=device, checking=checking):
                command = self.command(device, 0, checking)
                before, after = [self.run_command(command + ["-E", "-P", str(source)]).stdout
                                 for source in (self.original, PRODUCTION)]
                tokens = lambda value: re.findall(r"\w+|[^\w\s]", value)
                self.assertEqual(tokens(before), tokens(after), "Legacy production tokens changed")
                objects = [self.directory / "before.o", self.directory / "after.o"]
                for source, obj in zip((self.original, PRODUCTION), objects):
                    self.run_command(command + ["-O2", "-c", str(source), "-o", str(obj)])
                self.assertEqual(*(executable_sections(obj) for obj in objects),
                                 "Legacy executable object sections changed")

    def test_arm_objects_compile_for_both_target_cores_and_checking_modes(self):
        compiler = shutil.which("arm-none-eabi-gcc")
        if compiler is None:
            self.skipTest("Arm GNU compiler unavailable; native production-C tests still run")
        for (core, cpu), checking in itertools.product(
                ((0, "cortex-m85"), (1, "cortex-m33")), (0, 1)):
            with self.subTest(core=core, cpu=cpu, checking=checking):
                command = self.command("ra8p1", core, checking)
                command[0] = compiler
                self.run_command(command + [f"-mcpu={cpu}", "-mthumb", "-ffreestanding", "-O2", "-c",
                                            str(PRODUCTION), "-o",
                                            str(self.directory / f"arm-{core}-{checking}.o")])

    def test_all_older_devices_select_unchanged_paths_and_source_stays_crlf(self):
        headers = sorted(BSP.glob("*/bsp_feature.h"))
        self.assertEqual(33, len(headers))
        for header in headers:
            with self.subTest(device=header.parent.name):
                match = re.search(r"#define\s+BSP_FEATURE_ICU_HAS_COMMON_REGS\s+\((\d+)UL\)",
                                  header.read_text())
                self.assertIsNotNone(match)
                self.assertEqual(int(header.parent.name == "ra8p1"), int(match[1]))
        raw = PRODUCTION.read_bytes()
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"))


if __name__ == "__main__":
    unittest.main()
