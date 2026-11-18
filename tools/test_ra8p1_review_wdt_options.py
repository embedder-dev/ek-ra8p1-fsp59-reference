"""WDT-002 admission against actual RO option addresses (HM7.2.6-7.2.7).

The entire unmodified production translation unit runs against host-mapped,
read-only option pages. CPU0/legacy and NS rejection run without those pages.
These are host tests and real-core compiler checks, not target qualification.
"""

import itertools
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_ra8p1_wdt import configuration, executable_sections

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
PRODUCTION = BASELINE / "ra/fsp/src/r_wdt/r_wdt.c"
FIXTURE = ROOT / "tools/ra8p1/review_wdt_options"
BSP = BASELINE / "ra/fsp/src/bsp/mcu"
MODES = (
    (False, True, True), (False, False, True), (False, False, False),
    (True, True, True), (True, False, True),
)


def open_function(source):
    start = source.index("fsp_err_t R_WDT_Open (")
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return start, end


class ReviewWdtOptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("cc")
        cls.arm_cc = os.environ.get("ARM_GCC")
        database = ROOT / "validation/ra8p1/compatibility/extra85/Debug/compile_commands.json"
        if not cls.arm_cc and database.is_file():
            row = json.loads(database.read_text())[0]
            cls.arm_cc = (row.get("arguments") or shlex.split(row["command"]))[0]
        cls.arm_cc = cls.arm_cc or shutil.which("arm-none-eabi-gcc")
        cls.arm_objcopy = str(Path(cls.arm_cc).with_name("arm-none-eabi-objcopy")) if cls.arm_cc else None
        if not cls.cc or not cls.arm_cc or not Path(cls.arm_objcopy).is_file():
            raise RuntimeError("Native cc and complete arm-none-eabi GCC/binutils are required (ARM_GCC)")
        subprocess.run([cls.arm_cc, "-E", "-x", "c", "-"],
                       input=b"#include <stdint.h>\n", capture_output=True, check=True, timeout=10)
        cls.temp = tempfile.TemporaryDirectory(prefix="review-wdt-options-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        cls.binaries = {}
        pristine = subprocess.run(
            ["git", "-C", str(BASELINE), "show", "HEAD:ra/fsp/src/r_wdt/r_wdt.c"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout
        cls.pristine = cls.directory / "pristine.c"
        cls.pristine.write_text(pristine)
        current = PRODUCTION.read_text()
        a, b = open_function(pristine)
        old_open = pristine[a:b].replace("R_WDT->", "WDT_PRV_REG->")
        a, b = open_function(current)
        # Only the existing per-core register alias is applied to the stock Open.
        # All previously repaired helpers are identical on either side of CPU0 parity.
        cls.cpu0_reference = cls.directory / "cpu0_before_options.c"
        cls.cpu0_reference.write_text(current[:a] + old_open + current[b:])

    def run_command(self, command):
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0,
                         " ".join(map(str, command)) + "\n" + result.stdout + result.stderr)
        return result

    def flags(self, device, core, checks, mode, nonsecure=0):
        defines = configuration(int(device == "ra8p1"), core, checks, *mode)
        defines["TEST_NONSECURE"] = nonsecure
        return [
            "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-I", str(FIXTURE), "-I", str(BSP / device),
            "-I", str(ROOT / "tools/ra8p1/review_wdt"),
            "-I", str(ROOT / "tools/ra8p1/wdt_test"),
            "-I", str(BASELINE / "ra/fsp/inc/instances"),
            "-I", str(BASELINE / "ra/fsp/inc/api"),
        ] + [f"-D{key}={value}" for key, value in defines.items()]

    def binary(self, device, core, checks, mode, nonsecure=0):
        key = (device, core, checks, mode, nonsecure)
        if key not in self.binaries:
            binary = self.directory / f"options-{len(self.binaries)}"
            command = [self.cc] + self.flags(*key) + [
                "-fsanitize=undefined", "-fno-sanitize-recover=all",
                f'-DREVIEW_WDT_SOURCE="{PRODUCTION}"',
                str(FIXTURE / "harness.c"), "-o", str(binary),
            ]
            if sys.platform == "darwin":
                # Darwin arm64 requires 4GB PAGEZERO. x86_64 permits the actual low option addresses.
                command += ["-arch", "x86_64", "-Wl,-pagezero_size,0x4000", "-Wl,-no_pie"]
            self.run_command(command)
            self.binaries[key] = binary
        return self.binaries[key]

    def test_cpu1_secure_nonsecure_and_mixed_selected_words_match(self):
        for checks, mode in itertools.product((0, 1), MODES):
            with self.subTest(checks=checks, mode=mode):
                binary = self.binary("ra8p1", 1, checks, mode)
                for case in ("match", "reserved"):
                    self.run_command([str(binary), case])

    def test_cpu1_every_wdt_bit_mismatch_rejects_without_side_effects(self):
        for checks, mode in itertools.product((0, 1), MODES):
            with self.subTest(checks=checks, mode=mode):
                self.run_command([str(self.binary("ra8p1", 1, checks, mode)), "mismatch"])

    def test_cpu1_nonsecure_rejects_without_accessing_unmapped_secure_options(self):
        for checks, mode in itertools.product((0, 1), MODES):
            with self.subTest(checks=checks, mode=mode):
                binary = self.binary("ra8p1", 1, checks, mode, nonsecure=1)
                self.run_command([str(binary), "nonsecure"])

    def test_cpu0_and_legacy_paths_preprocessing_and_objects_are_unchanged(self):
        for device, checks, mode in itertools.product(
                ("ra8p1", "ra8m1", "ra6t2", "ra2l1"), (0, 1), MODES):
            with self.subTest(device=device, checks=checks, mode=mode):
                self.run_command([str(self.binary(device, 0, checks, mode)), "unaffected"])
                reference = self.cpu0_reference if device == "ra8p1" else self.pristine
                flags = self.flags(device, 0, checks, mode)
                pp = [self.run_command([self.cc] + flags + ["-E", "-P", str(source)]).stdout
                      for source in (reference, PRODUCTION)]
                self.assertEqual(*pp)
                objects = [self.directory / "before.o", self.directory / "after.o"]
                for source, obj in zip((reference, PRODUCTION), objects):
                    self.run_command([self.cc] + flags + ["-O2", "-c", str(source), "-o", str(obj)])
                self.assertEqual(*(executable_sections(obj) for obj in objects))

    def test_full_production_compiles_for_cortex_m85_and_cortex_m33(self):
        for core, checks, mode, nonsecure in itertools.product((0, 1), (0, 1), MODES, (0, 1)):
            with self.subTest(core=core, checks=checks, mode=mode, nonsecure=nonsecure):
                obj = self.directory / "target.o"
                arch = "cortex-m85" if core == 0 else "cortex-m33"
                flags = self.flags("ra8p1", core, checks, mode, nonsecure)
                self.run_command([self.arm_cc] + flags + [
                    f"-mcpu={arch}", "-mthumb", "-mfloat-abi=soft", "-O2",
                    "-c", str(PRODUCTION), "-o", str(obj),
                ])
                if core == 0 and nonsecure == 0:
                    before = self.directory / "target_before.o"
                    self.run_command([self.arm_cc] + flags + [
                        f"-mcpu={arch}", "-mthumb", "-mfloat-abi=soft", "-O2",
                        "-c", str(self.cpu0_reference), "-o", str(before),
                    ])
                    sections = []
                    for path in (before, obj):
                        text = self.directory / "target_text.bin"
                        self.run_command([self.arm_objcopy, "--dump-section", f".text={text}", str(path)])
                        sections.append(text.read_bytes())
                    self.assertTrue(sections[0])
                    self.assertEqual(*sections)

    def test_source_retains_crlf_and_const_volatile_option_reads(self):
        raw = PRODUCTION.read_bytes()
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"))
        source = raw.decode()
        for address in ("02C9F0C4", "12C9F4C4", "02C9F124"):
            self.assertIn(f"*((volatile uint32_t const *) 0x{address}UL)", source)


if __name__ == "__main__":
    unittest.main()
