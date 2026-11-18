"""CLK-018: independent HM9.2.49/50 pp366-367 divider encoding oracle."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "baseline/ra/fsp/src/bsp/mcu/all/bsp_common.h"
MCUS = ROOT / "baseline/ra/fsp/src/bsp/mcu"


def helper(text):
    start = text.index("__STATIC_INLINE uint32_t R_FSP_ClockDividerGet (")
    brace = text.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


class ClockDividerReviewTests(unittest.TestCase):
    def test_all_legal_type6_dividers_match_manual(self):
        cc = shutil.which("cc")
        self.assertIsNotNone(cc)
        # This list is the primary register table, not the candidate inventory.
        expected = (1, 2, 4, 6, 8, 3, 5, 10, 16, 32)
        source = '#include <stdint.h>\n#include <assert.h>\n#define __STATIC_INLINE static inline\n'
        source += f'#include "{MCUS / "ra8p1/bsp_feature.h"}"\n' + helper(HEADER.read_text())
        source += '\nint main(void) {\n'
        source += ''.join(f'assert(R_FSP_ClockDividerGet({i}U) == {n}U);\n' for i, n in enumerate(expected))
        source += 'return 0; }\n'
        with tempfile.TemporaryDirectory(prefix="clock-divider-") as directory:
            src, exe = Path(directory) / "test.c", Path(directory) / "test"
            src.write_text(source)
            result = subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror", str(src), "-o", str(exe)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
            self.assertEqual(0, result.returncode, result.stderr)

    def test_every_legacy_device_retains_original_preprocessed_helper(self):
        cc = shutil.which("cc")
        self.assertIsNotNone(cc)
        original = subprocess.run(["git", "-C", str(ROOT / "baseline"), "show",
                                   "HEAD:ra/fsp/src/bsp/mcu/all/bsp_common.h"],
                                  check=True, capture_output=True, text=True).stdout
        def preprocess(device, body):
            source = f'#include "{device / "bsp_feature.h"}"\n' + body
            result = subprocess.run([cc, "-E", "-P", "-x", "c", "-"], input=source,
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(0, result.returncode, result.stderr)
            return result.stdout
        devices = sorted(p.parent for p in MCUS.glob("*/bsp_feature.h") if p.parent.name != "ra8p1")
        self.assertEqual(32, len(devices))
        for device in devices:
            with self.subTest(device=device.name):
                self.assertEqual(preprocess(device, helper(original)), preprocess(device, helper(HEADER.read_text())))


if __name__ == "__main__":
    unittest.main()
