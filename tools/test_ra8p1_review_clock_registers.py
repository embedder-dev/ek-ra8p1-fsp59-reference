"""Compile production clock fragments against independent HM register expectations.

RA8P1 HM Rev.1.30: PLLCCR/PLL2CCR pp.333/336, FLLCR2 pp.344-345,
PRCR_S/PRCR_NS pp.525-526. No clock algorithm is reimplemented here.
"""
from pathlib import Path
import itertools
import re
import shutil
import subprocess
import tempfile
import unittest

from tools.test_ra8p1_wdt import executable_sections

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
MCU = BASELINE / "ra/fsp/src/bsp/mcu"
SOURCE = MCU / "all/bsp_clocks.c"
FIXTURES = ROOT / "tools/ra8p1/review_clock_registers"


def conditional(text, marker):
    """Extract a whole production conditional, including its nested branches."""
    start = text.index("#if", text.index(marker))
    depth = 0
    for match in re.finditer(r"(?m)^\s*#\s*(if|ifdef|ifndef|endif)\b[^\n]*", text[start:]):
        depth += -1 if match[1] == "endif" else 1
        if depth == 0:
            return text[start:start + match.end()] + "\n"
    raise AssertionError("Unbalanced production conditional: " + marker)


def function(text, name):
    start = re.search(r"(?m)^void " + name + r" \(", text).start()
    brace = text.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end] + "\n"


def fragments(text):
    return (conditional(text, "/* Choose the value to write to FLLCR2"),
            conditional(text, "/* Calculate PLLCCR value. */")
            + conditional(text, "#if BSP_FEATURE_CGC_HAS_PLL2"))


def reset_macros(text):
    return "".join("#undef " + name + "\n" for name in sorted(set(
        re.findall(r"(?m)^\s*#\s*define\s+(\w+)", text))))


def definitions(values):
    return "".join(f"#define {name} {value}\n" for name, value in values.items())


CLOCK_CONSTANTS = """
#include <stdint.h>
#include <stdio.h>
#define BSP_CLOCKS_SOURCE_CLOCK_HOCO 0U
#define BSP_CLOCKS_SOURCE_CLOCK_MAIN_OSC 3U
#define BSP_CLOCKS_SOURCE_CLOCK_SUBCLOCK 4U
#define BSP_CLOCKS_PLL_DIV_1 0U
#define BSP_CLOCKS_PLL_DIV_4 3U
#define BSP_CLOCKS_PLL_DIV_6 5U
#define BSP_PRV_PLL_SUPPORTED 1
"""


class ReviewClockRegisterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("cc")
        cls.cxx = shutil.which("c++")
        if not cls.cc or not cls.cxx:
            raise RuntimeError("Native C and C++ compilers are required")

    def run_command(self, command):
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, " ".join(map(str, command)) + "\n"
                         + result.stdout + result.stderr)
        return result.stdout

    def compile_run(self, text, *, core=0, checks=1):
        with tempfile.TemporaryDirectory(prefix="review-clocks-") as temp:
            source, binary = Path(temp) / "test.c", Path(temp) / "test"
            source.write_text(text)
            self.run_command([self.cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                              "-fsanitize=undefined", "-fno-sanitize-recover=all",
                              f"-DBSP_CFG_CPU_CORE={core}",
                              f"-DBSP_CFG_PARAM_CHECKING_ENABLE={checks}",
                              str(source), "-o", str(binary)])
            return self.run_command([str(binary)])

    def target_header(self):
        return f'#include "{MCU / "ra8p1/bsp_feature.h"}"\n'

    def test_target_fll_all_hoco_choices_and_disabled(self):
        text = SOURCE.read_text()
        fll, _ = fragments(text)
        begin = text.index("/* The FLL function can only be used when the subclock is running. */")
        end = text.index("/* Start all clocks used by other clocks first. */", begin)
        apply = text[begin:end]
        # Literal requirements from HM 9.2.20, not the source's branch arithmetic.
        required = {0: 0x1E8, 1: 0x225, 2: 0x262, 4: 0x1E8, 7: 0x1E8}
        source = self.target_header() + CLOCK_CONSTANTS + """
static struct { uint16_t FLLCR1, FLLCR2; } registers;
#define R_SYSTEM (&registers)
"""
        calls, expected = [], []
        for index, (enabled, (choice, value)) in enumerate(itertools.product((0, 1), required.items())):
            config = definitions({"BSP_PRV_HOCO_USE_FLL": enabled, "BSP_CFG_HOCO_FREQUENCY": choice})
            source += config + fll + f"static void apply_{index}(void) {{\n" + apply + "}\n"
            source += reset_macros(config + fll)
            calls.append(f"registers.FLLCR1 = 0x55; registers.FLLCR2 = 0x555; apply_{index}(); "
                         'printf("%u %u\\n", registers.FLLCR1, registers.FLLCR2);')
            expected.append((1, value) if enabled else (0x55, 0x555))
        source += "int main(void) {\n" + "\n".join(calls) + "\nreturn 0; }\n"
        for core, checks in itertools.product((0, 1), repeat=2):
            with self.subTest(core=core, checks=checks):
                output = self.compile_run(source, core=core, checks=checks)
                self.assertEqual([tuple(map(int, line.split())) for line in output.splitlines()], expected)

    def test_target_both_plls_multiplier_boundaries_and_fractions(self):
        _, pll = fragments(SOURCE.read_text())
        header = (MCU / "all/bsp_clocks.h").read_text()
        mul = header[header.index("/* PLL multiplier options. */"):
                     header.index("/* Configuration option used to disable clock output. */")]
        # Independent register fields: nine integer bits at 16:8, fraction at 7:6.
        integer_bits = {40: 0x2700, 255: 0xFE00, 256: 0xFF00, 257: 0x10000, 300: 0x12B00}
        fractional_bits = {0: 0, 33: 0x40, 50: 0xC0, 66: 0x80}
        source = self.target_header() + CLOCK_CONSTANTS + mul
        expected, names = [], []
        for index, ((integer, bits), (fraction, frac_bits), hoco, divider) in enumerate(
                itertools.product(integer_bits.items(), fractional_bits.items(), (0, 1), (0, 1, 2))):
            config = definitions({
                "BSP_CFG_PLL_SOURCE": 0 if hoco else 3,
                "BSP_CFG_PLL2_SOURCE": 3 if hoco else 0,
                "BSP_CFG_PLL_MUL": f"BSP_CLOCKS_PLL_MUL({integer}U, {fraction}U)",
                "BSP_CFG_PLL2_MUL": f"BSP_CLOCKS_PLL_MUL({integer}U, {fraction}U)",
                "BSP_CFG_PLL_DIV": divider, "BSP_CFG_PLL2_DIV": 2 - divider,
                "BSP_CFG_PLODIVP": 2, "BSP_CFG_PLODIVQ": 4, "BSP_CFG_PLODIVR": 7,
                "BSP_CFG_PL2ODIVP": 1, "BSP_CFG_PL2ODIVQ": 3, "BSP_CFG_PL2ODIVR": 5,
            })
            source += config + pll
            name = f"row_{index}"
            names.append(name)
            source += f"static const uint32_t {name}[] = {{BSP_PRV_PLLCCR, BSP_PRV_PLL2CCR, " \
                      "BSP_PRV_PLLCCR2, BSP_PRV_PLL2CCR2};\n"
            source += reset_macros(config + pll)
            expected.append((bits | frac_bits | (0x10 if hoco else 0) | divider,
                             bits | frac_bits | (0 if hoco else 0x10) | (2 - divider), 0x742, 0x531))
        source += "int main(void) {\n" + "\n".join(
            f'printf("%u %u %u %u\\n", {name}[0], {name}[1], {name}[2], {name}[3]);' for name in names)
        source += "\nreturn 0; }\n"
        for core, checks in itertools.product((0, 1), repeat=2):
            with self.subTest(core=core, checks=checks):
                output = self.compile_run(source, core=core, checks=checks)
                self.assertEqual([tuple(map(int, row.split())) for row in output.splitlines()], expected)

    def test_target_keyed_protection_and_octa_settings(self):
        text = SOURCE.read_text()
        keys = "\n".join(re.findall(r"(?m)^#define BSP_PRV_PRCR_\w+[^\n]*", text))
        with tempfile.TemporaryDirectory(prefix="review-prcr-") as temp:
            directory = Path(temp)
            from tools.test_ra8p1_clocks import function as clock_function
            (directory / "production_octaclk.inc").write_text(
                clock_function(SOURCE, "bsp_prv_peripheral_clock_stop") + "\n" +
                function(text, "R_BSP_OctaclkUpdate"))
            (directory / "production_keys.inc").write_text(keys)
            for core, checks, nonsecure in itertools.product((0, 1), repeat=3):
                with self.subTest(core=core, checks=checks, nonsecure=nonsecure):
                    (directory / "configuration.h").write_text(self.target_header() + definitions({
                        "BSP_CFG_CPU_CORE": core, "BSP_CFG_PARAM_CHECKING_ENABLE": checks,
                        "BSP_TZ_NONSECURE_BUILD": nonsecure, "TEST_OCTA_REAL_STOP": 1,
                    }))
                    binary = directory / "protection"
                    self.run_command([self.cxx, "-std=c++11", "-Wall", "-Wextra", "-Werror",
                                      "-fsanitize=undefined", "-fno-sanitize-recover=all", f"-I{directory}",
                                      str(FIXTURES / "protection.cpp"), "-o", str(binary)])
                    self.assertIn("keyed protection and OCTA settings passed", self.run_command([str(binary)]))

    def legacy_source(self, text, device, nonsecure):
        fll, pll = fragments(text)
        keys = "\n".join(re.findall(r"(?m)^#define BSP_PRV_PRCR_\w+[^\n]*", text))
        legacy_header = (BASELINE / "ra/fsp/src/bsp/cmsis/Device/RENESAS/Include/R7FA6M5BH.h").read_text()
        positions = "\n".join(re.findall(
            r"(?m)^\s*#define\s+R_SYSTEM_PLL2CCR_(?:PLL2MUL|PL2IDIV|PL2SRCSEL)_Pos[^\n]*",
            legacy_header))
        result = f'#include "{device}"\n' + CLOCK_CONSTANTS + keys + "\n" + positions + "\n"
        result += definitions({"BSP_TZ_NONSECURE_BUILD": nonsecure,
                               "BSP_CFG_PARAM_CHECKING_ENABLE": 1})
        for index, (enabled, hoco) in enumerate(itertools.product((0, 1), (0, 1, 2, 4, 7))):
            config = definitions({
                "BSP_PRV_HOCO_USE_FLL": enabled, "BSP_CFG_HOCO_FREQUENCY": hoco,
                "BSP_CFG_PLL_SOURCE": f"(BSP_FEATURE_CGC_PLLCCR_TYPE == 4U ? 4U : {0 if hoco else 3}U)",
                "BSP_CFG_PLL2_SOURCE": 0 if hoco else 3,
                "BSP_CFG_PLL_MUL": 0x4AC, "BSP_CFG_PLL2_MUL": 0x4AF,
                "BSP_CFG_PLL_DIV": 0, "BSP_CFG_PLL2_DIV": 1,
                "BSP_CFG_PLODIVP": 2, "BSP_CFG_PLODIVQ": 4, "BSP_CFG_PLODIVR": 7,
                "BSP_CFG_PL2ODIVP": 1, "BSP_CFG_PL2ODIVQ": 3, "BSP_CFG_PL2ODIVR": 5,
            })
            result += config + fll + pll + f"uint32_t values_{index}(void) {{ return 0U\n"
            for name in ("BSP_PRV_FLL_FLLCR2", "BSP_PRV_PLLCCR", "BSP_PRV_PLL2CCR",
                         "BSP_PRV_PLLCCR2", "BSP_PRV_PLL2CCR2"):
                result += f"#ifdef {name}\n + {name}\n#endif\n"
            result += "; }\n" + reset_macros(config + fll + pll)
        result += """
typedef struct { uint8_t divider, source_clock; } bsp_octaclk_settings_t;
typedef struct {
    uint16_t PRCR, PRCR_S, PRCR_NS;
    uint8_t OCTACKDIVCR, OCTACKCR;
    struct { unsigned OCTACKSREQ, OCTACKSRDY; } OCTACKCR_b;
} review_registers_t;
extern volatile review_registers_t * review_registers;
#define R_SYSTEM review_registers
#define R_SYSTEM_OCTACKCR_OCTACKSREQ_Msk 0x40U
#define FSP_HARDWARE_REGISTER_WAIT(reg, value) do { (void)(reg); (void)(value); } while (0)
#define FSP_REGISTER_READ(reg) ((void)(reg))
#define FSP_PARAMETER_NOT_USED(value) ((void)(value))
"""
        return result + function(text, "R_BSP_OctaclkUpdate")

    def test_all_older_devices_preprocessed_and_executable_parity(self):
        pristine = self.run_command(["git", "-C", str(BASELINE), "show",
                                     "HEAD:ra/fsp/src/bsp/mcu/all/bsp_clocks.c"])
        current = SOURCE.read_text()
        devices = sorted(path for path in MCU.glob("*/bsp_feature.h") if path.parent.name != "ra8p1")
        self.assertGreaterEqual(len(devices), 32)
        with tempfile.TemporaryDirectory(prefix="review-clock-legacy-") as temp:
            directory = Path(temp)
            for device, nonsecure in itertools.product(devices, (0, 1)):
                with self.subTest(device=device.parent.name, nonsecure=nonsecure):
                    tokens, objects = [], []
                    for label, text in (("before", pristine), ("after", current)):
                        source, obj = directory / f"{label}.c", directory / f"{label}.o"
                        source.write_text(self.legacy_source(text, device, nonsecure))
                        command = [self.cc, "-std=c11", "-Wall", "-Wextra", "-Werror"]
                        tokens.append(self.run_command(command + ["-E", "-P", str(source)]).split())
                        self.run_command(command + ["-O2", "-c", str(source), "-o", str(obj)])
                        objects.append(executable_sections(obj))
                    self.assertEqual(tokens[0], tokens[1], "Legacy preprocessed tokens changed")
                    self.assertEqual(objects[0], objects[1], "Legacy executable sections changed")


if __name__ == "__main__":
    unittest.main()
