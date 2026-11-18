"""Compile the unchanged production gamma routine as C against real FSP headers.

Only CMSIS declarations and the BSP include boundary are host fixtures. The
register layout and display configuration types come from production headers.
The rest of the GLCDC translation unit is deliberately outside this focused gate.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from test_ra8p1_wdt import executable_sections

ROOT = Path(__file__).resolve().parents[1]
FSP = ROOT / "baseline/ra/fsp"
SOURCE = FSP / "src/r_glcdc/r_glcdc.c"
DEVICE = FSP / "src/bsp/cmsis/Device/RENESAS/Include"
CAPABILITY = "BSP_FEATURE_GLCDC_HAS_GLOBAL_GAMMA_SWITCH"

CORE = """
#ifndef TEST_CORE_H
#define TEST_CORE_H
#define __IM volatile const
#define __OM volatile
#define __IOM volatile
#define __I volatile const
#define __O volatile
#define __IO volatile
#endif
"""

BSP = """
#ifndef BSP_API_H
#define BSP_API_H
#include <stdbool.h>
#include <stddef.h>
#include "fsp_common_api.h"
#include "bsp_exceptions.h"
#endif
"""

PREAMBLE = """
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "bsp_api.h"
#include "r_display_api.h"
#if TEST_TARGET
#include "R7KA8P1KF.h"
#elif TEST_RA6M3
#include "R7FA6M3AH.h"
#else
#include "R7FA8D1BH.h"
#endif
static R_GLCDC_Type registers;
static R_GLCDC_Type * test_access(void);
#undef R_GLCDC
#define R_GLCDC test_access()
"""

HARNESS = r"""
static unsigned char previous[sizeof(registers)];
static size_t writes[64];
static uint32_t values[64];
static size_t write_count;

/* Every tested initial store differs from its poison value. Flushing before
 * each production register access records actual changes without rewriting C. */
static R_GLCDC_Type * test_access(void)
{
    unsigned char const * bytes = (unsigned char const *) &registers;
    size_t changed_word = sizeof(registers);
    for (size_t i = 0; i < sizeof(registers); ++i)
    {
        if (bytes[i] != previous[i])
        {
            size_t word = i & ~(size_t) 3U;
            assert(changed_word == sizeof(registers) || changed_word == word);
            changed_word = word;
        }
    }
    if (changed_word != sizeof(registers))
    {
        assert(write_count < sizeof(writes) / sizeof(writes[0]));
        writes[write_count] = changed_word;
        memcpy(&values[write_count], bytes + changed_word, sizeof(uint32_t));
        ++write_count;
    }
    memcpy(previous, &registers, sizeof(registers));
    return &registers;
}

static void apply(display_cfg_t const * cfg)
{
    r_glcdc_gamma_correction(cfg);
    (void) test_access();
}

static uint32_t load_word(void const * image, size_t offset)
{
    uint32_t value;
    memcpy(&value, (unsigned char const *) image + offset, sizeof(value));
    return value;
}

static void store_word(void * image, size_t offset, uint32_t value)
{
    memcpy((unsigned char *) image + offset, &value, sizeof(value));
}

static void check_mask(unsigned mask, bool poisoned, bool wide)
{
    uint16_t gain[3][16];
    uint16_t threshold[3][16];
    display_gamma_correction_t gamma = {0};
    gamma_correction_t * channels[3] = {&gamma.g, &gamma.b, &gamma.r};
    display_cfg_t cfg = {0};
    cfg.output.p_gamma_correction = &gamma;
    for (unsigned color = 0; color < 3; ++color)
    {
        channels[color]->enable = (mask & (1U << color)) != 0;
        for (unsigned i = 0; i < 16; ++i)
        {
            /* Also exercise register-field masking independently of API checks. */
            gain[color][i] = (uint16_t) ((wide ? 0xF800U : 0U) | (17U + 71U * i + color));
            threshold[color][i] = (uint16_t) ((wide ? 0xFC00U : 0U) | (60U * i));
        }
        channels[color]->gain = channels[color]->enable ? gain[color] : NULL;
        channels[color]->threshold = channels[color]->enable ? threshold[color] : NULL;
    }
    if (poisoned)
    {
        memset(&registers, 0xA5, sizeof(registers));
    }
    unsigned char expected[sizeof(registers)];
    memcpy(expected, &registers, sizeof(registers));
    memcpy(previous, &registers, sizeof(registers));
    write_count = 0;

    for (unsigned color = 0; color < 3; ++color)
    {
        bool enabled = channels[color]->enable;
        size_t base = 0x1300U + color * 0x40U;
        if (enabled || (TEST_TARGET && mask))
        {
            for (unsigned i = 0; i < 8; ++i)
            {
                uint32_t first = enabled ? gain[color][2 * i] & 0x7FFU : 1024U;
                uint32_t second = enabled ? gain[color][2 * i + 1] & 0x7FFU : 1024U;
                store_word(expected, base + 8U + 4U * i, (first << 16) | second);
            }
            for (unsigned i = 0; i < 5; ++i)
            {
                uint32_t packed = 0;
                for (unsigned k = 1; k <= 3; ++k)
                {
                    uint32_t t = enabled ? threshold[color][3 * i + k] & 0x3FFU :
                                          64U * (3U * i + k);
                    packed |= t << (10U * (3U - k));
                }
                store_word(expected, base + 0x28U + 4U * i, packed);
            }
        }
        if (!TEST_TARGET || color == 0)
        {
            store_word(expected, base + 4U, TEST_TARGET ? mask != 0 : enabled);
        }
        if (!TEST_TARGET)
        {
            store_word(expected, base, 1U);
        }
    }
    apply(&cfg);
    assert(memcmp(&registers, expected, sizeof(registers)) == 0);
    if (poisoned)
    {
        size_t enabled_count = ((mask & 1U) != 0) + ((mask & 2U) != 0) + ((mask & 4U) != 0);
        size_t expected_count = TEST_TARGET ? 1U + (mask ? 39U : 0U) : 6U + 13U * enabled_count;
        assert(write_count == expected_count);
        for (size_t w = 0; w < write_count; ++w)
        {
            assert(values[w] == load_word(expected, writes[w]));
            if (TEST_TARGET)
            {
                assert(writes[w] != 0x1344U && writes[w] != 0x1384U);
                /* HM64.2.28: no individual VEN request before startup global reflection. */
                assert(writes[w] != 0x1300U && writes[w] != 0x1340U && writes[w] != 0x1380U);
                if (w < write_count - 1U)
                {
                    /* All table writes precede the shared switch. */
                    assert(writes[w] >= 0x1308U && writes[w] <= 0x13B8U);
                }
            }
        }
        if (TEST_TARGET)
        {
            assert(writes[write_count - 1U] == 0x1304U);
        }
    }
}

static void check_unity_output(void)
{
    /* Disabled G/B channels in mixed mode must remain exact pass-through. */
    check_mask(4U, true, false);
    for (unsigned color = 0; color < 2; ++color)
    {
        unsigned thresholds[17] = {0};
        unsigned gains[16];
        size_t base = 0x1300U + color * 0x40U;
        thresholds[16] = 1023;
        for (unsigned i = 0; i < 16; ++i)
        {
            uint32_t packed = load_word(&registers, base + 8U + 4U * (i / 2U));
            gains[i] = (packed >> (i % 2U ? 0U : 16U)) & 0x7FFU;
            if (i)
            {
                unsigned index = i - 1U;
                packed = load_word(&registers, base + 0x28U + 4U * (index / 3U));
                thresholds[i] = (packed >> (10U * (2U - index % 3U))) & 0x3FFU;
                assert(thresholds[i - 1] < thresholds[i]);
            }
        }
        for (unsigned input = 0; input < 1024; ++input)
        {
            unsigned area = 0;
            unsigned offset = 0;
            while (area < 15 && input >= thresholds[area + 1])
            {
                offset += (thresholds[area + 1] - thresholds[area]) * gains[area] / 1024U;
                ++area;
            }
            unsigned output = offset + (input - thresholds[area]) * gains[area] / 1024U;
            assert(output == input);
        }
    }
}

int main(void)
{
    for (unsigned wide = 0; wide < 2; ++wide)
    {
        for (unsigned mask = 0; mask < 8; ++mask)
        {
            check_mask(mask, true, wide);
            for (unsigned next = 0; next < 8; ++next)
            {
                check_mask(mask, true, wide);
                check_mask(next, false, wide);
            }
        }
    }
    if (TEST_TARGET)
    {
        check_unity_output();
    }
    puts("production GLCDC gamma matrix passed");
    return 0;
}
"""


def gamma_slice(source):
    """Extract the complete definition, not the same-named forward declaration."""
    start = source.index("static void r_glcdc_gamma_correction (")
    end = source.index("\n}\n", start) + len("\n}\n")
    macros = []
    for name in ("GLCDC_PRV_GAMX_LUTX_GAIN_MASK", "GLCDC_PRV_GAMX_AREAX_MASK"):
        macros.append(re.search(r"^#define " + name + r"\s+[^\n]+", source, re.M).group())
    return "\n".join(macros) + "\n" + source[start:end]


class GlcdcGammaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("cc")
        if cls.cc is None:
            raise RuntimeError("A native C compiler is required for GLCDC production-C tests")

    def compile(self, directory, source, target, *, core=0, ra6m3=0, object_only=False):
        for name in ("core_cm85.h", "core_cm33.h", "core_cm4.h"):
            (directory / name).write_text(CORE)
        (directory / "bsp_api.h").write_text(BSP)
        text = PREAMBLE + gamma_slice(source)
        text += ("\nstatic R_GLCDC_Type * test_access(void) { return &registers; }\n"
                 "void gamma_entry(display_cfg_t const * cfg) { r_glcdc_gamma_correction(cfg); }\n"
                 if object_only else HARNESS)
        path = directory / "gamma.c"
        path.write_text(text)
        output = directory / ("gamma.o" if object_only else "gamma")
        command = [self.cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
                   f"-DTEST_TARGET={target}", f"-DTEST_RA6M3={ra6m3}",
                   f"-DBSP_CFG_CPU_CORE={core}", f"-D{CAPABILITY}={target}",
                   f"-I{directory}", f"-I{DEVICE}", f"-I{FSP / 'inc/api'}",
                   f"-I{FSP / 'inc'}", f"-I{FSP / 'src/bsp/mcu/all'}"]
        command += (["-c"] if object_only else
                    ["-fsanitize=undefined", "-fno-sanitize-recover=all"])
        command += [str(path), "-o", str(output)]
        result = subprocess.run(command, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return output

    def test_production_gamma_all_enables_and_transitions(self):
        with tempfile.TemporaryDirectory(prefix="glcdc-gamma-") as temp:
            for target, core, ra6m3 in ((1, 0, 0), (1, 1, 0), (0, 0, 0), (0, 0, 1)):
                with self.subTest(target=target, core=core, ra6m3=ra6m3):
                    output = self.compile(Path(temp), SOURCE.read_text(), target,
                                          core=core, ra6m3=ra6m3)
                    result = subprocess.run([str(output)], text=True, capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("production GLCDC gamma matrix passed", result.stdout)

    def test_legacy_gamma_executable_bytes_match_pristine_head(self):
        original = subprocess.run(
            ["git", "-C", str(ROOT / "baseline"), "show", "HEAD:ra/fsp/src/r_glcdc/r_glcdc.c"],
            text=True, capture_output=True, timeout=10, check=True).stdout
        with tempfile.TemporaryDirectory(prefix="glcdc-legacy-") as temp:
            for ra6m3 in (0, 1):
                with self.subTest(ra6m3=ra6m3):
                    before = self.compile(Path(temp), original, 0, ra6m3=ra6m3, object_only=True)
                    pristine = executable_sections(before)
                    after = self.compile(Path(temp), SOURCE.read_text(), 0,
                                         ra6m3=ra6m3, object_only=True)
                    self.assertEqual(pristine, executable_sections(after))

    def test_each_premature_gamma_latch_write_is_detected(self):
        original = SOURCE.read_text()
        anchor = "R_GLCDC->GAM[0].GAM_SW = gamma_enable;"
        self.assertEqual(1, original.count(anchor))
        with tempfile.TemporaryDirectory(prefix="glcdc-latch-negative-") as temp:
            for color in range(3):
                with self.subTest(color=color):
                    source = original.replace(anchor, anchor + f"\n    R_GLCDC->GAM[{color}].LATCH = 1U;", 1)
                    output = self.compile(Path(temp), source, 1)
                    result = subprocess.run([str(output)], text=True, capture_output=True, timeout=10)
                    self.assertNotEqual(0, result.returncode, "Premature VEN request escaped the behavior gate")

    def test_shared_switch_negative_control_detects_reserved_writes(self):
        source = SOURCE.read_text().replace(
            "R_GLCDC->GAM[0].GAM_SW = gamma_enable;",
            "R_GLCDC->GAM[1].GAM_SW = gamma_enable;", 1)
        self.assertNotEqual(source, SOURCE.read_text())
        with tempfile.TemporaryDirectory(prefix="glcdc-negative-") as temp:
            output = self.compile(Path(temp), source, 1)
            result = subprocess.run([str(output)], text=True, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0, "Reserved switch write escaped the behavior gate")


if __name__ == "__main__":
    unittest.main()
