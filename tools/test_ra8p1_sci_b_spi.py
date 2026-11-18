"""SCI_B SPI CCR4 contract: production function, real device/API headers.

Native execution replaces only processor instructions and BSP side effects;
complete driver preprocessing and configuration-function objects retain stock
legacy behavior. No generated project, pack or hardware is changed.
"""
import itertools
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from tools.test_ra8p1_wdt import executable_sections

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
SOURCE = "ra/fsp/src/r_sci_b_spi/r_sci_b_spi.c"
BSP = BASELINE / "ra/fsp/src/bsp"
INCLUDE = BSP / "cmsis/Device/RENESAS/Include"
HAS_SCKSEL = {"ra6t2": "R7FA6T2BD.h", "ra8d1": "R7FA8D1BH.h",
              "ra8e1": "R7FA8E1AF.h", "ra8e2": "R7FA8E2AF.h",
              "ra8m1": "R7FA8M1AH.h", "ra8t1": "R7FA8T1AH.h"}


def config_function(source):
    source = source.replace("\r\n", "\n")
    start = source.index("static void r_sci_b_spi_hw_config (")
    end = source.index("\n}\n", start) + len("\n}")
    constant = re.search(r"^#define SCI_B_SPI_PRV_CHR_RST_VALUE\s+.*$", source, re.M)
    if constant is None:
        raise AssertionError("Production character-length constant missing")
    return constant.group() + "\n" + source[start:end]


def feature_value(source, name):
    match = re.search(r"^#define\s+" + re.escape(name) + r"\s+\((0x[0-9a-fA-F]+|[0-9]+)[UL]*\)",
                      source, re.M)
    if match is None:
        raise AssertionError("Missing numeric BSP feature: " + name)
    return int(match.group(1), 0)


BSP_FIXTURE = r'''
#ifndef BSP_API_H
#define BSP_API_H
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "fsp_common_api.h"
#include "bsp_feature.h"
#include TEST_DEVICE_HEADER
#ifndef BSP_FEATURE_SCI_SPI_HAS_SCKSEL
#error "Every MCU must define BSP_FEATURE_SCI_SPI_HAS_SCKSEL"
#endif
typedef int IRQn_Type;
#define BSP_ALIGN_VARIABLE(n) __attribute__((aligned(n)))
extern unsigned test_starts, test_waits, test_channel;
static inline void test_module_start(unsigned channel)
{
    assert(channel == test_channel);
    test_starts++;
}
static inline void test_register_wait(uint32_t actual, uint32_t expected)
{
    assert(actual == expected);
    test_waits++;
}
#define R_BSP_MODULE_START(ip,ch) test_module_start(ch)
#define FSP_HARDWARE_REGISTER_WAIT(reg,value) test_register_wait(reg,value)
#endif
'''

HARNESS = r'''
unsigned test_starts, test_waits, test_channel;
#if TEST_TARGET
/* HM39.2.9: CCR4 is a word at 0x18, with no SCKSEL field. */
_Static_assert(offsetof(R_SCI_B0_Type, CCR4) == 0x18U, "CCR4 offset");
_Static_assert(sizeof(((R_SCI_B0_Type *) 0)->CCR4) == 4U, "CCR4 width");
_Static_assert(R_SCI_B0_CCR4_CMPD_Msk == 0x1FFU, "CMPD mask");
_Static_assert(R_SCI_B0_CCR4_ASEN_Msk == 0x10000U, "ASEN mask");
_Static_assert(R_SCI_B0_CCR4_ATEN_Msk == 0x20000U, "ATEN mask");
_Static_assert(R_SCI_B0_CCR4_AST_Msk == 0x07000000U, "AST mask");
_Static_assert(R_SCI_B0_CCR4_AJD_Msk == 0x08000000U, "AJD mask");
_Static_assert(R_SCI_B0_CCR4_ATT_Msk == 0x70000000U, "ATT mask");
_Static_assert(R_SCI_B0_CCR4_AET_Msk == 0x80000000U, "AET mask");
#endif
int main(void)
{
    unsigned cases = 0;
    for (test_channel = 0; test_channel < 10; test_channel++)
    for (unsigned options = 0; options < 32; options++)
    for (unsigned divider = 0; divider < 16; divider++)
    {
        struct { uint32_t before; R_SCI_B0_Type regs; uint32_t after; } memory;
        memset(&memory, 0, sizeof(memory));
        memory.before = memory.after = 0xdeadbeefU;
        memory.regs.CCR4 = UINT32_MAX;
        sci_b_spi_extended_cfg_t ext = {
            .clk_div = {.brr = (divider & 1U) ? 255 : 0,
                        .cks = (divider >> 1U) & 3U, .bgdm = (divider >> 3U) & 1U},
            .clock_source = (options & 16U) ? SCI_B_SPI_SOURCE_CLOCK_PCLK : SCI_B_SPI_SOURCE_CLOCK_SCISPICLK
        };
        spi_cfg_t cfg = {
            .channel = test_channel, .p_extend = &ext,
            .operating_mode = (options & 1U) ? SPI_MODE_SLAVE : SPI_MODE_MASTER,
            .bit_order = (options & 2U) ? SPI_BIT_ORDER_LSB_FIRST : SPI_BIT_ORDER_MSB_FIRST,
            .clk_phase = (options & 4U) ? SPI_CLK_PHASE_EDGE_EVEN : SPI_CLK_PHASE_EDGE_ODD,
            .clk_polarity = (options & 8U) ? SPI_CLK_POLARITY_HIGH : SPI_CLK_POLARITY_LOW
        };
        sci_b_spi_instance_ctrl_t ctrl = {.p_cfg = &cfg, .p_reg = &memory.regs};
        test_starts = test_waits = 0;
        r_sci_b_spi_hw_config(&ctrl);
        assert(test_starts == 1 && test_waits == 1);
        assert(memory.before == 0xdeadbeefU && memory.after == 0xdeadbeefU);
#if TEST_TARGET
        /* HM 39.2.9: CCR4[23:18] and CCR4[15:9] are reserved, write zero. */
        assert(memory.regs.CCR4 == 0U);
        assert((memory.regs.CCR4 & 0x00fc0000U) == 0U);
        assert((memory.regs.CCR4 & (1U << 19U)) == 0U);
        assert((memory.regs.CCR4 & 0x0000fe00U) == 0U);
        assert(R_SCI0_BASE == (BSP_TZ_NONSECURE_BUILD ? 0x50358000U : 0x40358000U));
#else
        assert(memory.regs.CCR4 == (BSP_FEATURE_SCI_SPI_SCKSEL_VALUE << R_SCI_B0_CCR4_SCKSEL_Pos));
#endif
        assert(memory.regs.CCR0 == ((options & 1U) ? R_SCI_B0_CCR0_SSE_Msk : 0U));
        assert(memory.regs.CCR1 == R_SCI_B0_CCR1_SPB2DT_Msk);
        uint32_t expected_ccr2 = 0U;
        if (!(options & 1U))
        {
            expected_ccr2 = ((uint32_t)ext.clk_div.cks << R_SCI_B0_CCR2_CKS_Pos) |
                            ((uint32_t)ext.clk_div.brr << R_SCI_B0_CCR2_BRR_Pos) |
                            ((uint32_t)ext.clk_div.bgdm << R_SCI_B0_CCR2_BGDM_Pos);
        }
        assert(memory.regs.CCR2 == expected_ccr2);
        assert(memory.regs.CCR3_b.MOD == 3U);
        assert(memory.regs.CCR3_b.CKE == ((options & 1U) ? 2U : 0U));
        assert(memory.regs.CCR3_b.LSBF == !!(options & 2U));
        assert(memory.regs.CCR3_b.CPHA == !!(options & 4U));
        assert(memory.regs.CCR3_b.CPOL == !!(options & 8U));
        assert(memory.regs.CCR3_b.BPEN == !!(options & 16U));
        assert(memory.regs.FCR == (R_SCI_B0_FCR_TFRST_Msk | R_SCI_B0_FCR_RFRST_Msk));
        assert(memory.regs.FFCLR == R_SCI_B0_FFCLR_DRC_Msk);
        assert(memory.regs.CFCLR == (R_SCI_B0_CFCLR_RDRFC_Msk | R_SCI_B0_CFCLR_FERC_Msk |
               R_SCI_B0_CFCLR_PERC_Msk | R_SCI_B0_CFCLR_MFFC_Msk | R_SCI_B0_CFCLR_ORERC_Msk |
               R_SCI_B0_CFCLR_DFERC_Msk | R_SCI_B0_CFCLR_DPERC_Msk | R_SCI_B0_CFCLR_DCMFC_Msk |
               R_SCI_B0_CFCLR_ERSC_Msk));
        cases++;
    }
    assert(cases == 5120U);
    return 0;
}
'''


class SciBSpiProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("cc")
        if cls.cc is None:
            raise RuntimeError("Native C compiler required")
        result = subprocess.run(["git", "-C", str(BASELINE), "show", "HEAD:" + SOURCE],
                                capture_output=True, check=True, timeout=10)
        cls.pristine = result.stdout
        cls.current = (BASELINE / SOURCE).read_bytes()

    def run_cc(self, args, *, source=None):
        result = subprocess.run([self.cc, "-DBSP_CFG_XTAL_HZ=24000000", *args], input=source, text=True,
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def compile(self, directory, source, *, device="ra8p1", core=0, secure=0, nonsecure=0,
                checks=1, object_only=False):
        header = "R7KA8P1KF.h" if device == "ra8p1" else HAS_SCKSEL[device]
        (directory / "bsp_api.h").write_text(BSP_FIXTURE)
        unit = directory / "config.c"
        unit.write_text('#include "bsp_api.h"\n#include "r_sci_b_spi.h"\n' + config_function(source) + "\n" +
                        ("void test_config(sci_b_spi_instance_ctrl_t * p) { r_sci_b_spi_hw_config(p); }\n"
                         if object_only else HARNESS))
        output = directory / ("config.o" if object_only else "config")
        args = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-Wundef",
                "-I" + str(directory), "-I" + str(BSP / "mcu" / device),
                "-I" + str(ROOT / "tools/ra8p1/layout/native"), "-I" + str(INCLUDE),
                "-I" + str(BASELINE / "ra/fsp/inc/api"), "-I" + str(BASELINE / "ra/fsp/inc"),
                "-I" + str(BASELINE / "ra/fsp/inc/instances"),
                f'-DTEST_DEVICE_HEADER="{header}"', f"-DBSP_CFG_CPU_CORE={core}",
                f"-DBSP_TZ_SECURE_BUILD={secure}", f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}",
                f"-DSCI_B_SPI_CFG_PARAM_CHECKING_ENABLE={checks}", f"-DTEST_TARGET={int(device == 'ra8p1')}"]
        args += ["-O2", "-c"] if object_only else ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
        self.run_cc([*args, str(unit), "-o", str(output)])
        return output

    def test_reserved_ccr4_mutations_are_detected_and_crlf(self):
        self.assertEqual(self.current.count(b"\n"), self.current.count(b"\r\n"))
        source = self.current.decode().replace("\r\n", "\n")
        block = config_function(source)
        stores = re.findall(r"p_ctrl->p_reg->CCR4\s*=\s*[^;]+;", block)
        self.assertEqual(1, len(stores))
        self.assertNotIn("CCR4_b", block)
        with tempfile.TemporaryDirectory(prefix="sci-b-spi-negative-") as temp:
            for bit in (9, 15, 18, 19, 23):
                with self.subTest(bit=bit):
                    store = stores[0]
                    mutation = source.replace(store, store[:-1] + f" | (1U << {bit});", 1)
                    self.assertNotEqual(config_function(mutation), block)
                    binary = self.compile(Path(temp), mutation)
                    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
                    self.assertNotEqual(0, result.returncode, "Reserved CCR4 write escaped the behavior gate")

    def test_parent_capability_contract_and_target_register_vocabulary(self):
        header = (INCLUDE / "R7KA8P1KF.h").read_bytes()
        self.assertNotIn(b"SCKSEL", header)
        for path in sorted((BSP / "mcu").glob("*/bsp_feature.h")):
            with self.subTest(device=path.parent.name):
                text = path.read_text()
                expected = int(path.parent.name in HAS_SCKSEL)
                self.run_cc(["-E", "-P", "-Wundef", "-Werror", "-x", "c", "-",
                             "-I" + str(path.parent)], source=(
                    '#include "bsp_feature.h"\n'
                    '#ifndef BSP_FEATURE_SCI_SPI_HAS_SCKSEL\n#error "Missing presence capability"\n#endif\n'
                    f'#if BSP_FEATURE_SCI_SPI_HAS_SCKSEL != {expected}\n#error "Wrong field presence"\n#endif\n'))
                value = feature_value(text, "BSP_FEATURE_SCI_SPI_SCKSEL_VALUE")
                self.assertEqual(value, int(path.parent.name in HAS_SCKSEL and path.parent.name != "ra6t2"))
                if expected:
                    self.assertIn("R_SCI_B0_CCR4_SCKSEL_Pos", (INCLUDE / HAS_SCKSEL[path.parent.name]).read_text())

    def test_target_production_config_both_cores_security_and_checks(self):
        with tempfile.TemporaryDirectory(prefix="sci-b-spi-target-") as temp:
            for core, (secure, nonsecure), checks in itertools.product(
                    (0, 1), ((0, 0), (1, 0), (0, 1)), (0, 1)):
                with self.subTest(core=core, secure=secure, nonsecure=nonsecure, checks=checks):
                    binary = self.compile(Path(temp), self.current.decode(), core=core,
                                          secure=secure, nonsecure=nonsecure, checks=checks)
                    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_complete_legacy_preprocessed_tokens_match(self):
        with tempfile.TemporaryDirectory(prefix="sci-b-spi-tokens-") as temp:
            directory = Path(temp)
            for header in ("r_sci_b_spi.h", "r_sci_b_spi_cfg.h"):
                (directory / header).write_text("")
            for checks, dtc, secure, value in itertools.product((0, 1), repeat=4):
                with self.subTest(checks=checks, dtc=dtc, secure=secure, value=value):
                    args = ["-E", "-P", "-x", "c", "-", "-I" + str(directory),
                            "-DBSP_FEATURE_SCI_SPI_HAS_SCKSEL=1", f"-DBSP_FEATURE_SCI_SPI_SCKSEL_VALUE={value}",
                            f"-DSCI_B_SPI_CFG_PARAM_CHECKING_ENABLE={checks}",
                            f"-DSCI_B_SPI_DTC_SUPPORT_ENABLE={dtc}", f"-DBSP_TZ_SECURE_BUILD={secure}"]
                    before = self.run_cc(args, source=self.pristine.decode())
                    after = self.run_cc(args, source=self.current.decode())
                    self.assertEqual(before.split(), after.split())

    def test_all_legacy_config_objects_match_and_execute(self):
        with tempfile.TemporaryDirectory(prefix="sci-b-spi-legacy-") as temp:
            directory = Path(temp)
            for device, checks in itertools.product(HAS_SCKSEL, (0, 1)):
                with self.subTest(device=device, checks=checks):
                    before = self.compile(directory, self.pristine.decode(), device=device,
                                          checks=checks, object_only=True)
                    original = executable_sections(before)
                    after = self.compile(directory, self.current.decode(), device=device,
                                         checks=checks, object_only=True)
                    self.assertEqual(original, executable_sections(after))
                    binary = self.compile(directory, self.current.decode(), device=device, checks=checks)
                    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
