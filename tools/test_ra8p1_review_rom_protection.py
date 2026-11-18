"""BSP-001: admission tests compile the complete production ROM translation unit.

HM 7.2.8-9 and 60.9.1.2 define zero protection bits and irreversible PBPS.
Minimal target inputs use the current generated ~(0U) macro contract and real
MCU capabilities. Frozen generated older-device inputs prove byte preservation;
these are compile/object tests, not e2 builds or hardware qualification.
"""

import itertools
import json
import os
from pathlib import Path
import shlex
import shutil
import struct
import subprocess
import tempfile
import unittest

from ra8p1 import regression

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
RELATIVE = "ra/fsp/src/bsp/mcu/all/bsp_rom_registers.c"
PRODUCTION = BASELINE / RELATIVE
FIXTURE = ROOT / "tools/ra8p1/review_rom_protection"
WORDS = tuple(f"BSP_CFG_ROM_REG_BPS{i}" for i in range(16)) + tuple(
    f"BSP_CFG_ROM_REG_PBPS{i}" for i in range(4))
MODES = ((0, 0), (1, 0), (0, 1))  # Flat, Secure, Nonsecure.


class ReviewRomProtectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = os.environ.get("RA8P1_ARM_CC") or shutil.which("arm-none-eabi-gcc")
        if not cls.cc:
            database = ROOT / "validation/stock/Debug/compile_commands.json"
            if database.is_file():
                cls.cc = shlex.split(json.loads(database.read_text())[0]["command"])[0]
        if not cls.cc or not Path(cls.cc).is_file():
            raise RuntimeError("Arm GCC is required (or set RA8P1_ARM_CC)")
        cls.temp = tempfile.TemporaryDirectory(prefix="review-rom-protection-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        cls.pristine = cls.run_command([
            "git", "-C", str(BASELINE), "show", "HEAD:" + RELATIVE,
        ]).stdout

    @staticmethod
    def run_command(command, **kwargs):
        result = subprocess.run(command, capture_output=True, timeout=60, **kwargs)
        if result.returncode:
            raise AssertionError(shlex.join(map(str, command)) + "\n" +
                                 (result.stdout + result.stderr).decode(errors="replace"))
        return result

    def command(self, core, mode, *, boot=0, reduced=False, overrides=None):
        secure, nonsecure = mode
        return [
            self.cc, "-std=c99", "-Wall", "-Wextra", "-Werror", "-ffreestanding", "-O2", "-g0",
            f"-mcpu=cortex-m{85 if core == 0 else 33}", "-mthumb",
            f"-D__CORTEX_M={85 if core == 0 else 33}", f"-DBSP_CFG_CPU_CORE={core}",
            f"-DBSP_TZ_SECURE_BUILD={secure}", f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}",
            f"-DBSP_CFG_BOOT_IMAGE={boot}",
            *(["-DREVIEW_REDUCED_POLICY"] if reduced else []),
            *(f"-D{key}={value}" for key, value in (overrides or {}).items()),
            "-I", str(FIXTURE), "-I", str(BASELINE / "ra/fsp/src/bsp/mcu/ra8p1"),
        ]

    def compile(self, command):
        output = self.directory / "rom.o"
        self.run_command(command + ["-c", str(PRODUCTION), "-o", str(output)])
        return output.read_bytes()

    def assert_rejected(self, command, word):
        output = self.directory / "rejected.o"
        output.unlink(missing_ok=True)
        result = subprocess.run(command + ["-c", str(PRODUCTION), "-o", str(output)],
                                capture_output=True, timeout=60)
        self.assertNotEqual(result.returncode, 0, word + " was silently ignored")
        family = "PBPS" if "PBPS" in word else "BPS"
        self.assertIn(f"MRAM {family} protection is unsupported".encode(), result.stderr)
        self.assertFalse(output.exists(), "Rejected protection policy emitted an object")

    def test_each_word_rejected_independently_for_both_cores_and_all_security_modes(self):
        for core, mode, word, bit in itertools.product((0, 1), MODES, WORDS, (0, 31)):
            with self.subTest(core=core, mode=mode, word=word, bit=bit):
                # This is the expression emitted for a selected MDF bitmap option.
                self.assert_rejected(self.command(core, mode, overrides={word: f"(~(1U << {bit}))"}), word)

    def test_each_word_rejected_when_it_is_the_only_defined_protection_macro(self):
        # Reduced existing host harnesses omit these macros; don't invent defaults,
        # and don't let a missing BPS0 or word-count macro hide a later word.
        for core, mode, word in itertools.product((0, 1), MODES, WORDS):
            with self.subTest(core=core, mode=mode, word=word):
                self.assert_rejected(self.command(core, mode, reduced=True,
                                                 overrides={word: "0xFFFFFFFEU"}), word)

    def test_boot_image_cannot_silently_drop_selected_protection(self):
        for core, mode, word in itertools.product((0, 1), MODES, WORDS):
            with self.subTest(core=core, mode=mode, word=word):
                self.assert_rejected(self.command(core, mode, boot=1, overrides={word: "0U"}), word)

    def test_all_default_words_accepted_without_new_image_sections_or_bytes(self):
        for core, mode, boot in itertools.product((0, 1), MODES, (0, 1)):
            with self.subTest(core=core, mode=mode, boot=boot):
                command = self.command(core, mode, boot=boot)
                default = self.compile(command)
                reduced = self.compile(self.command(core, mode, boot=boot, reduced=True))
                literal = self.compile(self.command(core, mode, boot=boot,
                    overrides={word: "0xFFFFFFFFU" for word in WORDS}))
                self.assertEqual(default, reduced)
                self.assertEqual(default, literal)
                expected = {}
                if core == 0 and not boot:
                    expected = {".option_setting_ofs1": 0xFCFFF0D0,
                                ".option_setting_ofs3": 0xFFFFFFFF}
                    if not mode[1]:
                        expected = {".option_setting_ofs0": 0xFFFFFFFF,
                                    ".option_setting_ofs2": 0xFFFFFFFF,
                                    ".option_setting_ofs1_sec": 0xFCFFF0D0,
                                    ".option_setting_ofs3_sec": 0xFFFFFFFF,
                                    ".option_setting_ofs1_sel": 0,
                                    ".option_setting_ofs3_sel": 0}
                actual = regression.readonly_sections(default)
                self.assertEqual(set(actual), set(expected))
                for section, value in expected.items():
                    self.assertEqual(actual[section]["size"], 4)
                    self.assertEqual(actual[section]["sha256"], regression.sha256(struct.pack("<I", value)))
                    self.assertEqual(actual[section]["relocations"], [])
                preprocess = self.run_command(command + ["-E", "-P", str(PRODUCTION)]).stdout
                no_policy = self.run_command(self.command(core, mode, boot=boot, reduced=True) +
                                             ["-E", "-P", str(PRODUCTION)]).stdout
                self.assertEqual(preprocess, no_policy)

    def test_frozen_generated_stock_controls_keep_exact_preprocessed_and_object_bytes(self):
        manifest = json.loads((ROOT / regression.MANIFEST).read_text())
        controls = dict(manifest["fixtures"])
        controls.update({device: manifest["generated_fixtures"][device + "_checks_on"]
                         for device in ("ra8d1", "ra4m2", "ra4m1", "ra0e1")})
        for device, spec in controls.items():
            with self.subTest(device=device):
                tree = self.directory / device
                regression.unpack_fixture(ROOT, spec, tree)
                rows = json.loads((tree / "Debug/compile_commands.json").read_text())
                row = next(row for row in rows if row["file"].endswith("/" + RELATIVE))
                output = tree / "review-rom.o"
                command, cwd, relative = regression.compile_command(row, tree, output)
                # Remove debug line tables only. Use the same source/output paths
                # on both passes so even ELF symbol-table bytes must match exactly.
                command += ["-g0", "-Werror"]
                preprocess = command.copy()
                preprocess.remove("-c")
                index = preprocess.index("-o")
                del preprocess[index:index + 2]
                preprocess += ["-E", "-P"]
                source = tree / relative
                original_preprocessed = original_object = None
                for data in (self.pristine, PRODUCTION.read_bytes()):
                    source.write_bytes(data)
                    current_preprocessed = self.run_command(preprocess, cwd=cwd).stdout
                    self.run_command(command, cwd=cwd)
                    current_object = output.read_bytes()
                    self.assertTrue(regression.readonly_sections(current_object),
                                    "Stock ROM control unexpectedly empty")
                    if original_object is not None:
                        self.assertEqual(original_preprocessed, current_preprocessed)
                        self.assertEqual(original_object, current_object)
                    original_preprocessed, original_object = current_preprocessed, current_object

    def test_source_keeps_legacy_source_and_crlf(self):
        raw = PRODUCTION.read_bytes()
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"))
        self.assertNotIn(b"BSP_MCU_GROUP_RA8P1", raw)
        # The existing target option emitter is not expanded by this fix.
        original = self.pristine.decode().replace("\r\n", "\n")
        current = raw.decode().replace("\r\n", "\n")
        legacy_start = " #elif BSP_FEATURE_CGC_SCKDIVCR2_HAS_EXTRA_CLOCKS"
        self.assertEqual(original[original.index(legacy_start):], current[current.index(legacy_start):])


if __name__ == "__main__":
    unittest.main()
