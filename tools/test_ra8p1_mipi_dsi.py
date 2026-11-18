"""Production DSI clear writes against real device headers; no live MMIO.

The native fixture substitutes only CMSIS processor declarations and redirects
R_DSILINK to ordinary memory. The four initialization assignments are extracted
unchanged from production C. Whole-driver preprocessing additionally proves the
legacy tokens match the hash-verified original FSP 5.9 release, including both
parameter-checking and TrustZone paths. Generated-project builds are separate.
"""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from ra8p1.compatibility import original_sources
from test_ra8p1_wdt import executable_sections


ROOT = Path(__file__).resolve().parents[1]
FSP = ROOT / "baseline/ra/fsp"
RELATIVE_SOURCE = "ra/fsp/src/r_mipi_dsi/r_mipi_dsi.c"
SOURCE = ROOT / "baseline" / RELATIVE_SOURCE
DEVICE = FSP / "src/bsp/cmsis/Device/RENESAS/Include"
CAPABILITY = "BSP_FEATURE_MIPI_DSI_STATUS_CLEAR_TYPE"
RESERVED = (("SQCH0SCR", 16), ("SQCH0SCR", 19), ("SQCH1SCR", 16), ("RXSCR", 13))
FORBIDDEN = ("R_DSILINK_RXSCR_RXTE_Msk", "R_DSILINK_SQCH0SCR_DABORT_Msk",
             "R_DSILINK_SQCH0SCR_SIZEERR_Msk", "R_DSILINK_SQCH1SCR_DABORT_Msk")

CORE = """
/* Native-only CMSIS declaration fixture: no processor implementation. */
#define __IM volatile const
#define __OM volatile
#define __IOM volatile
#define __I volatile const
#define __O volatile
#define __IO volatile
"""
BSP = """
#ifndef BSP_API_H
#define BSP_API_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "bsp_exceptions.h"
#include "R7FA8D1BH.h"
#endif
"""
PREAMBLE = """
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "bsp_exceptions.h"
#if TEST_TARGET
#include "R7KA8P1KF.h"
#else
#include "R7FA8D1BH.h"
#endif
static R_DSILINK_Type registers;
static R_DSILINK_Type * test_access(void);
#undef R_DSILINK
#define R_DSILINK test_access()
"""
HARNESS = r"""
/* Independent HM 66.2.15/46/55/59 anchors, not inventory-derived masks. */
static size_t const offsets[] = {0x5D4U, 0x614U, 0x414U, 0x204U};
static uint32_t const values[] = {
    TEST_TARGET ? 0x7D000110U : 0x7D090110U,
    TEST_TARGET ? 0x7D080110U : 0x7D090110U,
    0x00D0000BU,
    TEST_TARGET ? 0x57F7C507U : 0x57F7E507U
};
static unsigned char expected[sizeof(registers)];
static size_t accesses;

/* Check the entire image before each access, then predict exactly the next
 * store. A final flush checks the last write; extra accesses fail as well. */
static R_DSILINK_Type * test_access(void)
{
    assert(accesses <= 4U);
    assert(memcmp(&registers, expected, sizeof(registers)) == 0);
    if (accesses < 4U)
    {
        memcpy(expected + offsets[accesses], &values[accesses], sizeof(uint32_t));
    }
    ++accesses;
    return &registers;
}

int main(void)
{
    unsigned char const poison[] = {0U, 0xA5U, 0xFFU};
    for (size_t i = 0; i < sizeof(poison); ++i)
    {
        memset(&registers, poison[i], sizeof(registers));
        memcpy(expected, &registers, sizeof(registers));
        accesses = 0;
        production_clear();
        (void) test_access();
        assert(accesses == 5U);
    }
    puts("production DSI clear writes passed");
    return 0;
}
"""


def initialization_slice(source):
    start = source.index("    /* Clear any active status bits */")
    end = source.index("    p_ctrl->p_callback_memory = NULL;", start)
    return source[start:end]


class MipiDsiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("cc")
        if not cls.cc:
            raise RuntimeError("A native C compiler is required for production DSI tests")
        cls.original = original_sources(ROOT)[RELATIVE_SOURCE]

    def includes(self, folder):
        for name in ("core_cm85.h", "core_cm33.h"):
            (folder / name).write_text(CORE)
        return [f"-I{folder}", f"-I{DEVICE}", f"-I{FSP / 'src/bsp/mcu/all'}",
                f"-I{FSP / 'inc/instances'}", f"-I{FSP / 'inc/api'}"]

    def compile(self, folder, source, target, core=0, nonsecure=0, object_only=False):
        path = folder / "clear.c"
        output = folder / ("clear.o" if object_only else "clear")
        absent = "\n".join(f"#ifdef {name}\n#error Reserved clear bit must not exist\n#endif"
                           for name in FORBIDDEN) if target else ""
        definition = "void" if object_only else "static void"
        suffix = ("\nstatic R_DSILINK_Type * test_access(void) { return &registers; }\n"
                  if object_only else HARNESS)
        path.write_text(PREAMBLE + absent + f"\n{definition} production_clear(void)\n{{\n" +
                        initialization_slice(source) + "}\n" + suffix)
        command = [self.cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
                   f"-D{CAPABILITY}={target}", f"-DTEST_TARGET={target}",
                   f"-DBSP_CFG_CPU_CORE={core}", f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}",
                   *self.includes(folder)]
        command += (["-c"] if object_only else
                    ["-fsanitize=undefined", "-fno-sanitize-recover=all"])
        command += [str(path), "-o", str(output)]
        return subprocess.run(command, capture_output=True, text=True, timeout=30), output

    def test_crlf_and_legacy_clear_executable_bytes_identical(self):
        current = SOURCE.read_bytes()
        self.assertNotIn(b"\n", current.replace(b"\r\n", b""))
        with tempfile.TemporaryDirectory(prefix="dsi-legacy-object-") as temp:
            for core in (0, 1):
                for ns in (0, 1):
                    with self.subTest(core=core, nonsecure=ns):
                        images = []
                        for source in (self.original.decode(), current.decode()):
                            result, output = self.compile(Path(temp), source, 0, core, ns,
                                                          object_only=True)
                            self.assertEqual(0, result.returncode, result.stderr)
                            images.append(executable_sections(output))
                        self.assertTrue(images[0])
                        self.assertEqual(*images)

    def test_legacy_whole_driver_preprocessed_tokens_identical(self):
        with tempfile.TemporaryDirectory(prefix="dsi-legacy-tokens-") as temp:
            folder = Path(temp)
            (folder / "bsp_api.h").write_text(BSP)
            (folder / "r_mipi_dsi_cfg.h").write_text("")
            includes = self.includes(folder)
            for checking in (0, 1):
                for secure in (0, 1):
                    with self.subTest(checking=checking, secure=secure):
                        tokens = []
                        for source in (self.original.decode(), SOURCE.read_text()):
                            (folder / "driver.c").write_text(source)
                            result = subprocess.run(
                                [self.cc, "-E", "-P", f"-D{CAPABILITY}=0",
                                 f"-DMIPI_DSI_CFG_PARAM_CHECKING_ENABLE={checking}",
                                 f"-DBSP_TZ_SECURE_BUILD={secure}", *includes,
                                 str(folder / "driver.c")],
                                capture_output=True, text=True, timeout=30)
                            self.assertEqual(0, result.returncode, result.stderr)
                            tokens.append(result.stdout.split())
                        self.assertEqual(*tokens)

    def test_production_initialization_target_and_legacy_writes(self):
        with tempfile.TemporaryDirectory(prefix="dsi-clear-") as temp:
            for target, core, ns in ((0, 0, 0), (1, 0, 0), (1, 0, 1), (1, 1, 0), (1, 1, 1)):
                with self.subTest(target=target, core=core, nonsecure=ns):
                    result, output = self.compile(Path(temp), SOURCE.read_text(), target, core, ns)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([str(output)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn("production DSI clear writes passed", result.stdout)

    def test_original_target_compile_rejects_four_nonexistent_masks(self):
        with tempfile.TemporaryDirectory(prefix="dsi-original-rejected-") as temp:
            result, _ = self.compile(Path(temp), self.original.decode(), 1)
            self.assertNotEqual(0, result.returncode)
            for name in FORBIDDEN:
                self.assertIn(name, result.stderr)

    def test_each_reserved_bit_write_is_detected(self):
        original = SOURCE.read_text()
        initialization = initialization_slice(original)
        with tempfile.TemporaryDirectory(prefix="dsi-negative-") as temp:
            for register, bit in RESERVED:
                with self.subTest(register=register, bit=bit):
                    field = "BTAREND" if register == "RXSCR" else "AACTFIN"
                    mask = f"R_DSILINK_{register}_{field}_Msk"
                    self.assertEqual(1, initialization.count(mask))
                    mutated = initialization.replace(mask, f"({mask} | (1UL << {bit}))", 1)
                    mutation = original.replace(initialization, mutated, 1)
                    self.assertEqual(mutated, initialization_slice(mutation))
                    result, output = self.compile(Path(temp), mutation, 1)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([str(output)], capture_output=True, text=True, timeout=10)
                    self.assertNotEqual(0, result.returncode, "Reserved write escaped the trace gate")


if __name__ == "__main__":
    unittest.main()
