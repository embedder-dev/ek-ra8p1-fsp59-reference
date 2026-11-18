"""Focused CLK-001/003/004/007/008/009 production execution and legacy parity.

Independent primary anchors and deliberate failure cases live in the fixtures.
No e2, pack publication, or target operations are performed.
"""
from pathlib import Path
import itertools
import json
import shlex
import re
import shutil
import subprocess
import tempfile
import unittest

from tools.test_ra8p1_review_clock_registers import function, definitions
from tools.test_ra8p1_clocks import function as any_function
from tools.test_ra8p1_wdt import executable_sections

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
BSP = BASELINE / "ra/fsp/src/bsp/mcu/all"
FIXTURE = ROOT / "tools/ra8p1/review_clock_transitions"
SOURCE = BSP / "bsp_clocks.c"


class ReviewClockTransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc, cls.cxx = shutil.which("cc"), shutil.which("c++")
        if not cls.cc or not cls.cxx:
            raise RuntimeError("Native C and C++ compilers are required")

    def command(self, args):
        result = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, " ".join(map(str, args)) + "\n" + result.stdout + result.stderr)
        return result.stdout

    def prepare(self, directory):
        text = SOURCE.read_text()
        helpers = "\n".join(any_function(SOURCE, name) for name in (
            "bsp_internal_prv_clear_pfb", "bsp_prv_mram_frequency_mhz",
            "bsp_internal_prv_set_wait_state_frequency", "bsp_internal_prv_set_pfb"))
        (directory / "production_mram.inc").write_text(helpers)
        start = text.index("#if (6U == BSP_FEATURE_CGC_PLLCCR_TYPE)\n/* Use a common")
        end = text.index("/*******************************************************************************************************************//**\n * Write SCKDIVCR", start)
        (directory / "production_transition.inc").write_text(text[start:end])
        (directory / "production_runtime.inc").write_text(function(text, "bsp_prv_clock_set"))
        (directory / "production_cold.inc").write_text(any_function(SOURCE, "bsp_prv_clock_set_hard_reset"))
        (directory / "production_stop.inc").write_text(any_function(SOURCE, "bsp_prv_peripheral_clock_stop"))
        (directory / "production_peripheral.inc").write_text(any_function(SOURCE, "bsp_peripheral_clock_set"))
        (directory / "production_init.inc").write_text(function(text, "bsp_clock_init"))
        (directory / "production_octa.inc").write_text(function(text, "R_BSP_OctaclkUpdate"))
        keys = "\n".join(re.findall(r"(?m)^#define BSP_PRV_PRCR_\w+[^\n]*", text))
        (directory / "production_keys.inc").write_text(keys)
        header = (BSP / "bsp_clocks.h").read_text()
        a = header.index("/* FLL is only used")
        b = header.index("#if BSP_FEATURE_RTC_IS_AVAILABLE", a)
        (directory / "production_fll.inc").write_text(header[a:b])

    def compile_fixture(self, name, variants):
        with tempfile.TemporaryDirectory(prefix="clock-transitions-") as temp:
            directory = Path(temp)
            self.prepare(directory)
            for values in variants:
                with self.subTest(**values):
                    (directory / "configuration.h").write_text(definitions({
                        "BSP_FEATURE_CGC_PLLCCR_TYPE": 6, **values,
                    }) + "#define BSP_PRV_SCKDIVCR_DIV_VALUE(div) (((div)&8U)?(3U<<((div)&7U)):(1U<<(div)))\n")
                    binary = directory / "fixture"
                    self.command([self.cxx, "-std=c++11", "-Wall", "-Wextra", "-Werror",
                                  "-fsanitize=undefined", "-fno-sanitize-recover=all", f"-I{directory}",
                                  f"-I{ROOT / 'tools/ra8p1/layout/native'}",
                                  f"-I{BASELINE / 'ra/fsp/src/bsp/cmsis/Device/RENESAS/Include'}",
                                  str(FIXTURE / name), "-o", binary])
                    self.assertIn("anchors passed", self.command([binary]))

    def test_runtime_and_cold_start_every_write_ratios_and_mram_wait_order(self):
        variants = [dict(zip(("BSP_CFG_CPU_CORE", "BSP_CFG_PARAM_CHECKING_ENABLE",
                              "BSP_CFG_CLOCK_SETTLING_DELAY_ENABLE"), row))
                    for row in itertools.product((0, 1), repeat=3)]
        self.compile_fixture("transition.cpp", variants)

    def generated_command(self, project, checks, directory):
        database = project / "Debug/compile_commands.json"
        self.assertTrue(database.is_file(), f"Required existing generated fixture missing: {database}")
        entry = next(e for e in json.loads(database.read_text()) if e["file"].endswith("/bsp_clocks.c"))
        args = shlex.split(entry["command"])
        self.assertTrue(Path(args[0]).is_file(), "Recorded ARM toolchain is required")
        args = [a.replace(str(project / "ra/fsp"), str(BASELINE / "ra/fsp")) for a in args]
        cfg = (project / "ra_cfg/fsp_cfg/bsp/bsp_cfg.h").read_text()
        cfg, count = re.subn(r"(#define\s+BSP_CFG_PARAM_CHECKING_ENABLE\s+)\([^\n]*\)",
                             rf"\g<1>({checks})", cfg)
        self.assertEqual(count, 1)
        (directory / "bsp_cfg.h").write_text(cfg)
        args.insert(1, f"-I{directory}")
        return args, entry["directory"]

    def test_complete_arm_translation_unit_both_cores_checks_on_off(self):
        for core, checks in itertools.product((0, 1), repeat=2):
            with self.subTest(core=core, checks=checks), tempfile.TemporaryDirectory(prefix="clock-arm-") as temp:
                directory = Path(temp)
                args, cwd = self.generated_command(ROOT / f"validation/ra8p1/projects/cpu{core}", checks, directory)
                args[args.index("-o") + 1] = str(directory / "clocks.o")
                args[-1] = str(SOURCE)
                result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=90)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn("warning:", result.stderr)

    def test_legacy_complete_tu_preprocessing_and_arm_object_parity(self):
        from tools.ra8p1.regression import readonly_sections
        pristine = self.command(["git", "-C", BASELINE, "show", "HEAD:ra/fsp/src/bsp/mcu/all/bsp_clocks.c"])
        projects = ("validation/stock", "validation/controls/stock_ra6t2_adc",
                    "validation/ra8p1/regression/controls/regression_ra4m1_r006",
                    "validation/ra8p1/regression/controls/regression_ra0e1_r006")
        for project, checks in itertools.product(projects, (0, 1)):
            with self.subTest(project=project, checks=checks), tempfile.TemporaryDirectory(prefix="clock-legacy-") as temp:
                directory = Path(temp)
                before = directory / "bsp_clocks.c"
                before.write_text(pristine)
                args, cwd = self.generated_command(ROOT / project, checks, directory)
                args.insert(1, f"-I{BSP}")
                args[1:1] = [f"-fmacro-prefix-map={before}=bsp_clocks.c",
                             f"-fmacro-prefix-map={SOURCE}=bsp_clocks.c"]
                tokens, objects = [], []
                for index, source in enumerate((before, SOURCE)):
                    obj = directory / f"clock-{index}.o"
                    args[args.index("-o") + 1] = str(obj)
                    args[-1] = str(source)
                    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=90)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    objects.append(readonly_sections(obj.read_bytes()))
                    pre = [a for a in args if a != "-c"]
                    index = pre.index("-o")
                    del pre[index:index + 2]
                    result = subprocess.run(pre + ["-E", "-P"], cwd=cwd,
                                            capture_output=True, text=True, timeout=90)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    tokens.append(result.stdout.split())
                self.assertEqual(tokens[0], tokens[1], "Legacy whole-TU preprocessed tokens changed")
                self.assertEqual(objects[0], objects[1], "Legacy ARM code/constants/relocations changed")

    def test_all32_legacy_changed_regions_preprocessed_and_object_parity(self):
        from tools.test_ra8p1_review_clock_registers import ReviewClockRegisterTests
        test = ReviewClockRegisterTests("test_all_older_devices_preprocessed_and_executable_parity")
        test.setUpClass()
        test.test_all_older_devices_preprocessed_and_executable_parity()
        original = self.command(["git", "-C", BASELINE, "show", "HEAD:ra/fsp/src/bsp/mcu/all/bsp_clocks.h"])
        current = (BSP / "bsp_clocks.h").read_text()
        def fll_block(text):
            return text[text.index("/* FLL is only used"):text.index("#if BSP_FEATURE_RTC_IS_AVAILABLE")]
        for device in sorted((BSP.parent).glob("*/bsp_feature.h")):
            if device.parent.name == "ra8p1":
                continue
            for enabled in (0, 1):
                outputs = []
                for header in (original, current):
                    source = f'#include "{device}"\n' + definitions({
                        "BSP_CFG_FLL_ENABLE": enabled, "BSP_CLOCK_CFG_SUBCLOCK_POPULATED": 1,
                    }) + fll_block(header) + "\nBSP_PRV_HOCO_USE_FLL BSP_PRV_FLL_STABILIZATION_TIME_US\n"
                    result = subprocess.run([self.cc, "-E", "-P", "-x", "c", "-"], input=source,
                                            capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    outputs.append(result.stdout.split())
                self.assertEqual(outputs[0], outputs[1])
        for path in (SOURCE, BSP / "bsp_clocks.h"):
            self.assertNotIn(b"\n", path.read_bytes().replace(b"\r\n", b""))

    def test_legacy_irtc_logged_line_numbers_and_object_parity(self):
        original = self.command(["git", "-C", BASELINE, "show", "HEAD:ra/fsp/src/bsp/mcu/all/bsp_clocks.c"])
        prefix = f'#include "{BSP.parent / "ra2a2/bsp_feature.h"}"\n' + """
#include <stdint.h>
#define BSP_CLOCK_CFG_SUBCLOCK_POPULATED 1
#define BSP_CLOCK_CFG_SUBCLOCK_DRIVE 0
#define BSP_REG_PROTECT_CGC 0
#define FSP_SUCCESS 0
#define FSP_ERR_INVALID_HW_CONDITION 1
#define FSP_ERR_NOT_INITIALIZED 2
typedef int fsp_err_t;
extern struct { struct { uint8_t VRTVLD; } VRTSR_b; uint8_t SOSCCR;
                struct { uint8_t SODRV; } SOMCR_b; } registers;
#define R_SYSTEM (&registers)
extern void fsp_error_log(int, const char *, unsigned);
extern void R_BSP_RegisterProtectDisable(unsigned);
extern void R_BSP_RegisterProtectEnable(unsigned);
extern void bsp_prv_sosc_init(void);
#define FSP_ERROR_RETURN(a, e) do { if (!(a)) { fsp_error_log(e, __FILE__, __LINE__); return e; } } while (0)
"""
        with tempfile.TemporaryDirectory(prefix="clock-irtc-") as temp:
            tokens, objects = [], []
            for i, text in enumerate((original, SOURCE.read_text())):
                start = text.rindex("\n#if BSP_FEATURE_RTC_IS_IRTC") + 1
                if "#line 3465\n" in text[:start]:
                    start = text.rindex("#line 3465\n", 0, start)
                line = text[:start].count("\n") + 1
                source, obj = Path(temp) / f"{i}.c", Path(temp) / f"{i}.o"
                source.write_text(prefix + f'#line {line} "bsp_clocks.c"\n' + text[start:])
                result = self.command([self.cc, "-E", "-P", source])
                for expected in (3479, 3502):
                    self.assertRegex(result, rf'fsp_error_log\([^;]*"bsp_clocks.c",\s*{expected}\)')
                tokens.append(result.split())
                self.command([self.cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", "-c", source, "-o", obj])
                objects.append(executable_sections(obj))
            self.assertEqual(tokens[0], tokens[1])
            self.assertEqual(objects[0], objects[1])

    def test_frozen_keyed_octa_protection_all_legal_saved_masks(self):
        with tempfile.TemporaryDirectory(prefix="clock-protection-") as temp:
            directory = Path(temp)
            self.prepare(directory)
            # Module-stop ordering is exercised separately against the real helper.
            helper = """static uint32_t bsp_prv_peripheral_clock_stop(volatile uint8_t *, uint8_t,
                volatile uint32_t **stop) { *stop = nullptr; return 0; }
"""
            (directory / "production_octaclk.inc").write_text(
                helper + function(SOURCE.read_text(), "R_BSP_OctaclkUpdate"))
            for core, checks, nonsecure in itertools.product((0, 1), repeat=3):
                with self.subTest(core=core, checks=checks, nonsecure=nonsecure):
                    (directory / "configuration.h").write_text(
                        f'#include "{BSP.parent / "ra8p1/bsp_feature.h"}"\n' + definitions({
                            "BSP_CFG_CPU_CORE": core, "BSP_CFG_PARAM_CHECKING_ENABLE": checks,
                            "BSP_TZ_NONSECURE_BUILD": nonsecure,
                        }))
                    binary = directory / "protection"
                    self.command([self.cxx, "-std=c++11", "-Wall", "-Wextra", "-Werror",
                                  "-fsanitize=undefined", "-fno-sanitize-recover=all", f"-I{directory}",
                                  ROOT / "tools/ra8p1/review_clock_registers/protection.cpp",
                                  "-o", binary])
                    self.assertIn("keyed protection and OCTA settings passed", self.command([binary]))

    def test_domain_masks_voltage_fll_and_mosc_startup_order(self):
        names = ("BSP_CFG_CPU_CORE", "BSP_CFG_PARAM_CHECKING_ENABLE", "BSP_TZ_NONSECURE_BUILD",
                 "TEST_FLL", "TEST_PLL_HOCO", "BSP_CFG_STARTUP_CLOCK_REG_NOT_RESET")
        self.compile_fixture("peripheral_startup.cpp", [dict(zip(names, row))
                             for row in itertools.product((0, 1), repeat=6)])


if __name__ == "__main__":
    unittest.main()
