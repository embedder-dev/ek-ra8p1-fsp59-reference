"""ADC-010/018: ordinal calibration callbacks and single-word volatile FIFO pops.

Oracles: unchanged FSP5.9 r_adc_api.h; RA8P1 HM 54.5.10.2/.5 pp3471-3472.
Execute production C, and inspect ARM instructions emitted from its FIFO function.
No IDE, generated project, pack or hardware is changed by these checks.
"""
import itertools
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FSP = ROOT / "baseline/ra/fsp"
FIXTURE = ROOT / "tools/ra8p1/review_adc_mmio"
SOURCE = FSP / "src/r_adc_b/r_adc_b.c"


def run(command, **kwargs):
    result = subprocess.run([str(arg) for arg in command], capture_output=True, text=True,
                            timeout=60, **kwargs)
    if result.returncode:
        raise AssertionError(" ".join(map(str, command)) + "\n" + result.stdout + result.stderr)
    return result.stdout


def prepare(tmp, checking, variant=1):
    name = "R7KA8P1KF.h" if variant else "R7FA6T2BD.h"
    device = (FSP / "src/bsp/cmsis/Device/RENESAS/Include" / name).read_text()
    end = device.index("} R_ADC_B0_Type;") + len("} R_ADC_B0_Type;")
    start = device.rfind("typedef struct", 0, end)
    registers = device[start:end] + "\n"
    registers += "\n".join(line for line in device.splitlines()
                            if re.match(r"\s*#define R_ADC_B0_", line))
    family = "ra8p1" if variant else "ra6t2"
    features = (FSP / "src/bsp/mcu" / family / "bsp_feature.h").read_text()
    registers += "\n" + "\n".join(line for line in features.splitlines()
                                  if re.match(r"\s*#define BSP_FEATURE_ADC_B_UNIT_[01]_CHANNELS\s", line))
    (tmp / "acquisition_adc_registers.h").write_text(registers)
    if variant:
        override = (FSP / "src/bsp/mcu/ra8p1/bsp_override.h").read_text()
        types = override[override.index("/** ADC16H clock selectors"):override.rindex("#endif")]
        types = "#define BSP_OVERRIDE_ADC_CHANNEL_T\n#define ADC_B_CHANNEL_MASK_EXT_OFFSET (32U)\n" + types
    else:
        types = (FSP / "src/bsp/mcu/ra6t2/r_adc_device_types.h").read_text()
    (tmp / "r_adc_device_types.h").write_text(types)
    (tmp / "bsp_api.h").write_text('#include "fixture_bsp.h"\n')
    (tmp / "r_adc_b_cfg.h").write_text(f"#define ADC_B_CFG_PARAM_CHECKING_ENABLE {checking}\n")
    return ["-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-pointer-to-int-cast", "-Wno-sign-compare",
            f"-DBSP_FEATURE_ADC_B_REGISTER_TYPE={variant}",
            "-I" + str(tmp), "-I" + str(FIXTURE), "-I" + str(FSP / "inc"),
            "-I" + str(FSP / "inc/api"), "-I" + str(FSP / "inc/instances")]


class AdcReviewBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = shutil.which("cc")
        if not cc:
            raise unittest.SkipTest("native C compiler unavailable")
        cls.directory = tempfile.TemporaryDirectory(prefix="review-adc-mmio-")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.binaries = {}
        for checking in (0, 1):
            tmp = Path(cls.directory.name) / str(checking)
            tmp.mkdir()
            binary = tmp / "fixture"
            run([cc, *prepare(tmp, checking), "-O2", "-fstrict-aliasing", "-fsanitize=undefined",
                 "-fno-sanitize-recover=all", SOURCE, FIXTURE / "fixture.c", "-o", binary])
            cls.binaries[checking] = binary

    def case(self, checking, *args):
        output = run([self.binaries[checking], *map(str, args)],
                     env={**os.environ, "UBSAN_OPTIONS": "halt_on_error=1"})
        self.assertIn("production ADC_B focused case passed", output)

    def calibration(self, flags):
        for checking, unit, phase, enabled, memory in itertools.product((0, 1), repeat=5):
            with self.subTest(checking=checking, unit=unit, flags=flags, phase=phase,
                              callback=enabled, callback_memory=memory):
                self.case(checking, "calibration", unit, flags, phase, enabled, memory)

    def test_conversion_error_is_not_misreported_as_overflow(self):
        self.calibration(1)

    def test_overflow_is_reported_as_an_ordinal_event(self):
        self.calibration(2)

    def test_simultaneous_failures_are_two_real_error_events(self):
        self.calibration(3)

    def test_success_continues_or_completes_calibration(self):
        self.calibration(0)

    def test_other_units_error_flags_do_not_fail_this_calibration(self):
        self.calibration(12)

    def test_fifo_all_groups_empty_partial_full_preserve_all_bytes(self):
        for checking, group, vacant in itertools.product((0, 1), range(9), (0, 1, 4, 7, 8, 15)):
            with self.subTest(checking=checking, group=group, vacant=vacant):
                self.case(checking, "fifo", group, vacant)

    def test_source_keeps_crlf_line_endings(self):
        data = SOURCE.read_bytes()
        self.assertGreater(data.count(b"\r\n"), 0)
        self.assertEqual(data.count(b"\r\n"), data.count(b"\n"))

    def test_api_contract_is_byte_identical_to_fsp59(self):
        api = "ra/fsp/inc/api/r_adc_api.h"
        original = subprocess.run(["git", "-C", str(ROOT / "baseline"), "show", "HEAD:" + api],
                                  check=True, capture_output=True).stdout
        self.assertEqual(original, (ROOT / "baseline" / api).read_bytes())

    def test_legacy_preprocessed_tokens_and_objects_remain_identical(self):
        cc = shutil.which("cc")
        for checking in (0, 1):
            with self.subTest(checking=checking), tempfile.TemporaryDirectory(prefix="review-adc-legacy-") as directory:
                tmp = Path(directory)
                command = [cc, *prepare(tmp, checking, variant=0), "-O2"]
                original = tmp / "original"
                original.mkdir()
                for relative in ("ra/fsp/src/r_adc_b/r_adc_b.c", "ra/fsp/inc/instances/r_adc_b.h"):
                    data = subprocess.run(["git", "-C", str(ROOT / "baseline"), "show", "HEAD:" + relative],
                                          check=True, capture_output=True).stdout
                    (original / Path(relative).name).write_bytes(data)
                before = run(command + ["-I" + str(original), "-E", "-P", original / "r_adc_b.c"])
                after = run(command + ["-E", "-P", SOURCE])
                self.assertEqual(re.findall(r"\S+", before), re.findall(r"\S+", after))
                run(command + ["-I" + str(original), "-c", original / "r_adc_b.c", "-o", tmp / "before.o"])
                run(command + ["-c", SOURCE, "-o", tmp / "after.o"])
                self.assertEqual((tmp / "before.o").read_bytes(), (tmp / "after.o").read_bytes())


class AdcReviewArmInstructionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = os.environ.get("RA8P1_ARM_GCC")
        if not cls.cc:
            database = ROOT / "validation/ra8p1/projects/adc_b/Debug/compile_commands.json"
            if database.is_file():
                entry = next(item for item in json.loads(database.read_text())
                             if item["file"].endswith("/r_adc_b.c"))
                cls.cc = shlex.split(entry["command"])[0]
        cls.cc = cls.cc or shutil.which("arm-none-eabi-gcc")
        if not cls.cc or not shutil.which(cls.cc):
            raise unittest.SkipTest("ARM GCC unavailable; set RA8P1_ARM_GCC")

    def test_fifo_volatile_word_load_instructions_both_cores_all_optimizations(self):
        with tempfile.TemporaryDirectory(prefix="review-adc-arm-") as directory:
            tmp = Path(directory)
            for core, optimization, checking in itertools.product(
                    ("cortex-m85", "cortex-m33"), ("-O0", "-Og", "-O1", "-O2", "-O3", "-Os", "-Oz"), (0, 1)):
                with self.subTest(core=core, optimization=optimization, checking=checking):
                    flags = prepare(tmp, checking=checking)
                    assembly = tmp / "adc.s"
                    run([self.cc, *flags, "-DREVIEW_ADC_ARM", "-mthumb", "-mcpu=" + core,
                         "-mfloat-abi=soft", optimization, "-fstrict-aliasing", "-fverbose-asm",
                         "-S", SOURCE, "-o", assembly])
                    text = assembly.read_text()
                    body = text.split("R_ADC_B_FifoRead:", 1)[1].split(".size\tR_ADC_B_FifoRead", 1)[0]
                    # Follow source annotations: optimization may rename p_fifo_data to prephitmp.
                    # A stack reload of the pointer is not the pointed-to MMIO load (marked '*').
                    source_line = "uint32_t fifo_data = *p_fifo_data;"
                    lines = body.splitlines()
                    active = False
                    pops = []
                    for index, line in enumerate(lines):
                        if re.match(r"@ .*:\d+: ", line):
                            active = source_line in line
                        elif active and re.search(r"^\s+ldr\w*(?:\.w)?\s+.*@.*\*", line):
                            pops.append((index, line))
                    self.assertEqual(1, len(pops), body)
                    pop_index, pop = pops[0]
                    self.assertRegex(pop, r"^\s+ldr(?:\.w)?\s+")
                    # The word load must be in the entry loop, never hoisted out of it.
                    labels = {line[:-1]: index for index, line in enumerate(lines)
                              if re.match(r"\.L\w+:$", line)}
                    enclosed = False
                    for index, line in enumerate(lines):
                        branch = re.match(r"\s+(?:b[a-z]*(?:\.w)?|le)\s+(?:lr,\s*)?(\.L\w+)\b", line)
                        if branch and branch[1] in labels:
                            enclosed |= labels[branch[1]] <= pop_index < index
                    self.assertTrue(enclosed, body)
                    # Also assemble and inspect the encoded instruction, not just compiler text.
                    obj = tmp / "adc.o"
                    run([self.cc, "-mthumb", "-mcpu=" + core, "-c", assembly, "-o", obj])
                    objdump = str(Path(self.cc).with_name("arm-none-eabi-objdump"))
                    decoded = run([objdump, "-d", "--disassemble=R_ADC_B_FifoRead", obj])
                    normalize = lambda value: re.sub(r"\.w|,#0(?=\])", "", re.sub(r"\s+", "", value))
                    instruction = normalize(pop.split("@", 1)[0])
                    self.assertTrue(any(instruction in normalize(line) for line in decoded.splitlines()), decoded)
                    # Representation transfer must start with a volatile scalar source.
                    function = SOURCE.read_text().split("fsp_err_t R_ADC_B_FifoRead (", 1)[1].split("return err;", 1)[0]
                    self.assertRegex(function, r"(?:const\s+volatile|volatile\s+const)\s+uint32_t\s*\*\s*p_fifo_data")


if __name__ == "__main__":
    unittest.main()
