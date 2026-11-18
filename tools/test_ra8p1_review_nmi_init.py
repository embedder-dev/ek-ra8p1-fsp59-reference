"""BSP-004: execute the production early-init function, without IDE or target.

The RA8P1 oracle is HM 14.2.14, pp. 545-547: NMI sources extend through
IPCEN at bit 20. Older-device parity uses the preserved FSP 5.9.0 function,
including its 16-slot behavior when the device's maximum index is smaller.
"""

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
BSP = BASELINE / "ra/fsp/src/bsp"
SYSTEM = BSP / "cmsis/Device/RENESAS/Source/system.c"
FIXTURE = ROOT / "tools/ra8p1/review_nmi_init.c"


def extract_function(source):
    signature = "static void bsp_init_uninitialized_vars (void)"
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


class NmiInitializationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which("cc")
        if cls.compiler is None:
            raise RuntimeError("A native C compiler is required")
        cls.production = extract_function(SYSTEM.read_text())
        original = cls.run_command([
            "git", "-C", str(BASELINE), "show",
            "HEAD:" + SYSTEM.relative_to(BASELINE).as_posix(),
        ]).stdout
        cls.original = extract_function(original)
        cls.fixture = FIXTURE.read_text()
        cls.legacy_devices = sorted(
            path.parent.name for path in (BSP / "mcu").glob("*/bsp_feature.h")
            if path.parent.name != "ra8p1"
        )

    @staticmethod
    def run_command(command):
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(
                f"Command failed ({result.returncode}): {' '.join(map(str, command))}\n"
                f"{result.stdout}{result.stderr}"
            )
        return result

    def command(self, device, core, target):
        return [
            self.compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-DBSP_CFG_EARLY_INIT=1", f"-DBSP_CFG_CPU_CORE={core}",
            "-DBSP_CFG_XTAL_HZ=24000000", f"-DTEST_TARGET={int(target)}",
            "-I", str(BSP / "mcu" / device),
        ]

    def execute(self, device, core=0, target=False):
        with tempfile.TemporaryDirectory(prefix="review-nmi-init-") as temp:
            source = Path(temp) / "nmi_init.c"
            binary = Path(temp) / "nmi_init"
            source.write_text(self.fixture.replace("/* PRODUCTION */", self.production))
            self.run_command(self.command(device, core, target) + [
                "-fsanitize=undefined", str(source), "-o", str(binary),
            ])
            self.run_command([str(binary)])

    def test_ra8p1_cpu0_clears_through_ipc_and_preserves_canary(self):
        self.execute("ra8p1", core=0, target=True)

    def test_ra8p1_cpu1_clears_through_ipc_and_preserves_canary(self):
        self.execute("ra8p1", core=1, target=True)

    def test_all_legacy_devices_retain_16_slot_behavior(self):
        self.assertEqual(len(self.legacy_devices), 32)
        maxima = set()
        for device in self.legacy_devices:
            with self.subTest(device=device):
                header = (BSP / "mcu" / device / "bsp_feature.h").read_text()
                value = re.search(
                    r"#define\s+BSP_FEATURE_ICU_NMIER_MAX_INDEX\s+\((\d+)UL\)", header
                )
                self.assertIsNotNone(value)
                maxima.add(int(value[1]))
                self.execute(device)
        self.assertEqual(maxima, {8, 12, 13, 15})

    def test_all_legacy_preprocessed_functions_match_original_exactly(self):
        with tempfile.TemporaryDirectory(prefix="review-nmi-parity-") as temp:
            source = Path(temp) / "nmi_init.c"
            for device in self.legacy_devices:
                with self.subTest(device=device):
                    results = []
                    for function in (self.original, self.production):
                        source.write_text(self.fixture.replace("/* PRODUCTION */", function))
                        results.append(self.run_command(
                            self.command(device, 0, False) + ["-E", "-P", str(source)]
                        ).stdout)
                    self.assertEqual(*results)


if __name__ == "__main__":
    unittest.main()
