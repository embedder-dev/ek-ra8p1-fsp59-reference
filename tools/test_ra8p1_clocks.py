"""Compile the changed production clock functions against controlled registers."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BSP = ROOT / "baseline/ra/fsp/src/bsp/mcu/all"


def function(path, name):
    text = path.read_text()
    start = text.index(name + " (")
    start = text.rfind("\n", 0, start) + 1
    brace = text.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


class ClockProductionTests(unittest.TestCase):
    def compile_run(self, source, defines=()):
        cc = shutil.which("cc")
        self.assertIsNotNone(cc, "A native C compiler is required")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "clock.c"
            binary = Path(temp) / "clock"
            path.write_text(source)
            command = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                       "-fsanitize=undefined", *defines, str(path), "-o", str(binary)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @staticmethod
    def async_configuration():
        text = (BSP / "bsp_clocks.c").read_text()
        start = text.index("#if BSP_FEATURE_BSP_HAS_BCLKA_CLOCK || BSP_FEATURE_BSP_HAS_ESW_CLOCK")
        end = text.index("/* All clocks with configurable source except PLL and CLKOUT", start)
        return text[start:end]

    @staticmethod
    def register_header():
        device = ROOT / "baseline/ra/fsp/src/bsp/cmsis/Device/RENESAS/Include/R7KA8P1KF.h"
        # Mock processor and read-only hardware flags, not the production register layout.
        return r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#define RA8P1_LAYOUT_NATIVE_CM85_H
#define RA8P1_LAYOUT_NATIVE_CM33_H
#define __IM volatile
#define __OM volatile
#define __IOM volatile
''' + f'#include "{device}"\n' + r'''
#undef R_SYSTEM
#undef R_MSTP
static R_SYSTEM_Type regs;
static R_MSTP_Type mstp;
#define R_SYSTEM (&regs)
#define R_MSTP (&mstp)
#define __STATIC_INLINE static inline
#define BSP_CFG_CLOCKS_SECURE 1
#define FSP_STYPE3_REG8_READ(x,s) (x)
#define FSP_PRV_SCKDIVCR_DIV_MASK 15U
#define BSP_CLOCKS_SOURCE_CLOCK_MOCO 1U
#define BSP_CLOCKS_SOURCE_CLOCK_PLL 5U
#define BSP_CLOCKS_CLOCK_DISABLED 255U
'''

    def startup_harness(self, startup=None):
        if startup is None:
            startup = function(BSP / "bsp_clocks.c", "bsp_clock_init")
        helpers = ("\n#if TEST_ESW && BSP_FEATURE_CGC_PLLCCR_TYPE == 6\n" +
                   function(BSP / "bsp_clocks.c", "bsp_prv_peripheral_clock_stop") + "\n#endif\n"
                   + "\n#if TEST_ESW\n" + function(BSP / "bsp_clocks.c", "bsp_peripheral_clock_set")
                   + "\n" + function(BSP / "bsp_clocks.c", "bsp_prv_esw_clock_set") + "\n#endif\n"
                   + "\n#if TEST_BCLKA\n" + function(BSP / "bsp_clocks.c", "bsp_prv_bclka_clock_set")
                   + "\n#endif\n")
        return self.register_header() + '\n#line 1 "clock_fixture.c"\n' + r'''
#define BSP_FEATURE_BSP_HAS_BCLKA_CLOCK TEST_BCLKA
#define BSP_FEATURE_BSP_HAS_ESW_CLOCK TEST_ESW
#define BSP_CFG_STARTUP_CLOCK_REG_NOT_RESET TEST_WARM
#define BSP_FEATURE_BSP_HAS_PRCR_S 1
#define BSP_FEATURE_CGC_HAS_PLL2 1
#define BSP_FEATURE_CGC_PLLCCR_TYPE 6
#define BSP_FEATURE_CGC_HAS_CPUCLK 1
#define BSP_FEATURE_CGC_STARTUP_OPCCR_MODE 2
#define BSP_CFG_USE_LOW_VOLTAGE_MODE 0
#define BSP_CLOCK_CFG_SUBCLOCK_POPULATED 0
#define BSP_PRV_PRCR_UNLOCK 0xA503U
#define BSP_PRV_PRCR_LOCK 0xA500U
#define BSP_PRV_STARTUP_OPERATING_MODE 2
#define BSP_PRV_OPERATING_MODE_HIGH_SPEED 2
#define BSP_PRV_OPERATING_MODE_MIDDLE_SPEED 1
#define BSP_PRV_OPERATING_MODE_LOW_SPEED 0
#define BSP_PRV_PLL_SUPPORTED 1
#define BSP_PRV_PLL_USED 1
#define BSP_PRV_PLL2_SUPPORTED 1
#define BSP_PRV_PLL2_USED 1
#define BSP_PRV_PLLCCR 0x12600U
#define BSP_PRV_PLLCCR2 0x246U
#define BSP_PRV_PLL2CCR 0x12B00U
#define BSP_PRV_PLL2CCR2 0x246U
#define BSP_CFG_PLL2_SOURCE 3U
#define BSP_PRV_STABILIZE_PLL 1
#define BSP_PRV_MOCO_USED 1
#define BSP_PRV_STABILIZE_MOCO 1
#define BSP_FEATURE_CGC_MOCO_STABILIZATION_MAX_US 7U
#define BSP_CFG_CLOCK_SOURCE 0U
#define BSP_CFG_CPUCLK_DIV 0U
#define BSP_PRV_STARTUP_SCKDIVCR 0x12345678U
#define BSP_PRV_STARTUP_SCKDIVCR2 0x3210U
#define BSP_CFG_BCLK_OUTPUT TEST_OUTPUT
#define BSP_CFG_SDCLK_OUTPUT 1U
#define BSP_CFG_BCLK_ASYNC TEST_ASYNC
#define BSP_CFG_CLKOUT_SOURCE 255U
#define BSP_CFG_UCK_SOURCE 255U
#define BSP_CFG_OCTA_SOURCE 255U
#define BSP_DELAY_UNITS_MICROSECONDS 1U
#define BSP_PRV_PERIPHERAL_CLK_REQ_BIT_MASK 0x40U
#define BSP_PRV_PERIPHERAL_CLK_RDY_BIT_MASK 0x80U
#define BSP_PRV_PERIPHERAL_CLK_RDY_BIT_POS 7U
''' + self.async_configuration() + r'''
static unsigned prepared, peripheral_waits, bus_waits, delays, disconnects, system_sets;
static unsigned pll1_ready, pll2_ready, module_stop_initial, voltage_waits;
static volatile uint8_t * active_control;
static volatile uint8_t * active_divider;

static unsigned setting(unsigned configured, unsigned fallback) {
    return configured == 255U ? fallback : configured;
}
static unsigned desired_source(unsigned domain) {
    if (TEST_WARM && !prepared) return 1U;
    return setting(domain == 0 ? BSP_CFG_BCLKA_SOURCE :
                   domain == 1 ? BSP_CFG_ESWCLK_SOURCE : BSP_CFG_ESWPHYCLK_SOURCE, 1U);
}
static unsigned desired_divider(unsigned domain) {
    if (TEST_WARM && !prepared) return 0U;
    return domain == 0 ? setting(BSP_CFG_BCLKA_SOURCE, 0U) == 0 ? 0U : BSP_CFG_BCLKA_DIV :
           domain == 1 ? setting(BSP_CFG_ESWCLK_SOURCE, 0U) == 0 ? 0U : BSP_CFG_ESWCLK_DIV :
                         setting(BSP_CFG_ESWPHYCLK_SOURCE, 0U) == 0 ? 0U : BSP_CFG_ESWPHYCLK_DIV;
}
void test_wait(char const * name, unsigned value) {
    if (strstr(name, "VSCR_b.VSCMTSF")) {
        assert(value == 0 && voltage_waits < 2U);
        assert(regs.PLLCR == 1 && regs.PLL2CR == 1);
        assert(regs.VSCR == (voltage_waits ? 1U : 0U));
        voltage_waits++;
        return;
    }
    if (strstr(name, "OSCSF_b.PLL2SF")) {
        assert(BSP_FEATURE_CGC_PLLCCR_TYPE != 6 || voltage_waits == 2U);
        assert(regs.PLL2CR == 0 && value == 1);
        regs.OSCSF_b.PLL2SF = 1;
        pll2_ready++;
        return;
    }
    if (strstr(name, "OSCSF_b.PLLSF")) {
        assert(BSP_FEATURE_CGC_PLLCCR_TYPE != 6 || voltage_waits == 2U);
        assert(regs.PLLCR == 0 && value == 1);
        regs.OSCSF_b.PLLSF = 1;
        pll1_ready++;
        return;
    }
    unsigned domain;
    if (strstr(name, "BCKACR")) {
        active_control = &regs.BCKACR;
        active_divider = &regs.BCKADIVCR;
        domain = 0;
        bus_waits++;
        assert(regs.EBCKOCR == 0 && regs.SDCKOCR == 0);
    } else {
        if (value) {
            if (regs.ESWCKCR & 0x40U) {
                active_control = &regs.ESWCKCR;
                active_divider = &regs.ESWCKDIVCR;
            } else {
                assert(regs.ESWPCKCR & 0x40U);
                active_control = &regs.ESWPCKCR;
                active_divider = &regs.ESWPCKDIVCR;
            }
        }
        domain = active_control == &regs.ESWCKCR ? 1U : 2U;
        peripheral_waits++;
    }
    assert(((*active_control & 0x40U) != 0) == (value != 0));
    if (value) {
        /* The old divider and source must survive until the stop acknowledgement. */
        assert(*active_divider == ((TEST_WARM && !prepared) ? 9U : 0U));
        assert((*active_control & 15U) == ((TEST_WARM && !prepared) ? 8U : 1U));
        if (domain && *active_divider) {
            assert(mstp.MSTPCRC & R_MSTP_MSTPCRC_MSTPC30_Msk);
            assert(delays >= domain);
        }
        *active_control |= 0x80U;
    } else {
        assert((*active_control & 15U) == desired_source(domain));
        assert(*active_divider == desired_divider(domain));
        if (prepared || !TEST_WARM) {
            unsigned source = desired_source(domain);
            if (source == 5 || source == 7 || source == 8) assert(pll1_ready);
            if (source == 6 || source == 9 || source == 10) assert(pll2_ready);
        }
        if (!domain) {
            unsigned bckcr = (TEST_WARM && !prepared) ? 0U :
                             (TEST_ASYNC << 7U) | (TEST_OUTPUT ? TEST_OUTPUT - 1U : 0U);
            assert(regs.BCKCR == bckcr);
        }
        *active_control &= (uint8_t) ~0x80U;
    }
}
#define FSP_HARDWARE_REGISTER_WAIT(reg, value) do { test_wait(#reg, value); assert((reg) == (value)); } while (0)
void test_read(char const * name) {
    if (strstr(name, "BCKCR")) {
        assert(!(regs.BCKCR & R_SYSTEM_BCKCR_EBCKASEL_Msk));
        assert(regs.BCKACR_b.BCKACKSRDY);
        disconnects++;
    }
}
#define FSP_REGISTER_READ(reg) do { (void)(reg); test_read(#reg); } while (0)
void R_BSP_SoftwareDelay(unsigned delay, unsigned units) {
    assert(units == BSP_DELAY_UNITS_MICROSECONDS);
    if (delay == 10) {
        assert(mstp.MSTPCRC & R_MSTP_MSTPCRC_MSTPC30_Msk);
        assert(!((regs.ESWCKCR | regs.ESWPCKCR) & 0x40U));
        delays++;
    } else {
        assert(delay == BSP_FEATURE_CGC_MOCO_STABILIZATION_MAX_US);
        assert(regs.MOCOCR == 0);
    }
}
void R_BSP_FlashCacheEnable(void) {}
void bsp_clock_freq_var_init(void) {}
void bsp_prv_sosc_init(void) {}
void bsp_prv_operating_mode_set(unsigned mode) { assert(mode == 2); }
void bsp_prv_clock_set(unsigned source, unsigned div, unsigned div2) {
    assert(source == BSP_CFG_CLOCK_SOURCE);
    assert(div == BSP_PRV_STARTUP_SCKDIVCR && div2 == BSP_PRV_STARTUP_SCKDIVCR2);
    system_sets++;
}
void bsp_prv_clock_set_hard_reset(void) { system_sets++; }
void bsp_soft_reset_prepare(void) {
#if TEST_BCLKA
    assert(regs.BCKACR == 1 && regs.BCKADIVCR == 0 && regs.BCKCR == 0);
    assert(regs.EBCKOCR == 0 && regs.SDCKOCR == 0);
#endif
#if TEST_ESW
    assert(regs.ESWCKCR == 1 && regs.ESWCKDIVCR == 0);
    assert(regs.ESWPCKCR == 1 && regs.ESWPCKDIVCR == 0);
#endif
    regs.PLLCR = 1;
    regs.PLL2CR = 1;
    prepared++;
}
''' + helpers + startup + '\n#line 1 "clock_fixture.c"\n' + r'''
int main(void) {
    regs.PLLCR = regs.PLL2CR = 1;
    regs.BCKACR = regs.ESWCKCR = regs.ESWPCKCR = TEST_WARM ? 8U : 1U;
    regs.BCKADIVCR = regs.ESWCKDIVCR = regs.ESWPCKDIVCR = TEST_WARM ? 9U : 0U;
    regs.BCKCR = 0x81U;
    regs.EBCKOCR = regs.SDCKOCR = TEST_WARM;
    regs.MOCOCR = TEST_WARM;
    mstp.MSTPCRC = (TEST_STOPPED ? R_MSTP_MSTPCRC_MSTPC30_Msk : 0U) | 0x123U;
    module_stop_initial = mstp.MSTPCRC;
    bsp_clock_init();
    assert(regs.PRCR_S == BSP_PRV_PRCR_LOCK);
    assert(regs.PLLCCR == BSP_PRV_PLLCCR && regs.PLL2CCR == BSP_PRV_PLL2CCR);
    assert(system_sets == 1);
    assert(voltage_waits == (BSP_FEATURE_CGC_PLLCCR_TYPE == 6 ? 2U : 0U));
    assert(mstp.MSTPCRC == module_stop_initial);
    assert(regs.EBCKOCR == (TEST_OUTPUT ? 1U : 0U) && regs.SDCKOCR == 1U);
#if TEST_BCLKA
    assert(bus_waits == (TEST_WARM ? 4U : 2U));
    assert(disconnects == (TEST_WARM ? 1U : 0U));
    assert(regs.BCKACR == desired_source(0) && regs.BCKADIVCR == desired_divider(0));
#endif
#if TEST_ESW
    assert(peripheral_waits == (TEST_WARM ? 8U : 4U));
    assert(delays == (TEST_WARM ? 2U : 0U));
    assert(regs.ESWCKCR == desired_source(1) && regs.ESWCKDIVCR == desired_divider(1));
    assert(regs.ESWPCKCR == desired_source(2) && regs.ESWPCKDIVCR == desired_divider(2));
#endif
    return 0;
}
'''

    def test_async_startup_handshakes_sources_and_warm_pll_detachment(self):
        common = (f"-I{ROOT / 'tools/ra8p1/layout/native'}",)
        source = self.startup_harness()
        for core in (0, 1):
            for warm in (0, 1):
                for stopped in (0, 1):
                    for sources in ((5, 9, 10), (7, 6, 8), (1, 255, 255), (255, 1, 1)):
                        with self.subTest(core=core, warm=warm, stopped=stopped, sources=sources):
                            self.compile_run(source, common + (
                                f"-DBSP_CFG_CPU_CORE={core}", "-DTEST_BCLKA=1", "-DTEST_ESW=1",
                                f"-DTEST_WARM={warm}", f"-DTEST_STOPPED={stopped}",
                                f"-DTEST_OUTPUT={2 if warm else 0}", f"-DTEST_ASYNC={sources[0] != 255:d}",
                                f"-DBSP_CFG_BCLKA_SOURCE={sources[0]}", "-DBSP_CFG_BCLKA_DIV=3",
                                f"-DBSP_CFG_ESWCLK_SOURCE={sources[1]}", "-DBSP_CFG_ESWCLK_DIV=2",
                                f"-DBSP_CFG_ESWPHYCLK_SOURCE={sources[2]}", "-DBSP_CFG_ESWPHYCLK_DIV=1"))

    def test_async_capabilities_are_independently_gated(self):
        source = self.startup_harness()
        for bus, esw in ((1, 0), (0, 1), (0, 0)):
            for warm in (0, 1):
                with self.subTest(bus=bus, esw=esw, warm=warm):
                    self.compile_run(source, (
                        "-DBSP_CFG_CPU_CORE=0", f"-I{ROOT / 'tools/ra8p1/layout/native'}",
                        f"-DTEST_BCLKA={bus}", f"-DTEST_ESW={esw}", f"-DTEST_WARM={warm}",
                        "-DTEST_STOPPED=0", "-DTEST_OUTPUT=2", "-DTEST_ASYNC=1",
                        "-DBSP_CFG_BCLKA_SOURCE=5", "-DBSP_CFG_BCLKA_DIV=3",
                        "-DBSP_CFG_ESWCLK_SOURCE=9", "-DBSP_CFG_ESWCLK_DIV=2",
                        "-DBSP_CFG_ESWPHYCLK_SOURCE=10", "-DBSP_CFG_ESWPHYCLK_DIV=1"))

    def test_hard_reset_extra_clock_step_preserves_every_divider_field(self):
        text = (BSP / "bsp_clocks.c").read_text()
        start = text.index("    R_SYSTEM->SCKDIVCR2 = BSP_CLOCKS_SYS_CLOCK_DIV_4 |")
        end = text.index("\n      #else\n    R_SYSTEM->SCKDIVCR2 = BSP_CLOCKS_SYS_CLOCK_DIV_4;", start)
        step = text[start:end]
        source = self.register_header() + r'''
#define BSP_CLOCKS_SYS_CLOCK_DIV_4 2U
#define BSP_FEATURE_CGC_HAS_MRAM_CLOCKS 1U
#define BSP_CFG_EXTRACLK1_DIV TEST_EXTRA1
#define BSP_CFG_EXTRACLK2_DIV TEST_EXTRA2
#define BSP_CFG_EXTRACLK3_DIV TEST_EXTRA3
#define BSP_INTERNAL_SCKDIVCR2_EXTRACK1_POS R_SYSTEM_SCKDIVCR2_CPUCK1_Pos
#define BSP_INTERNAL_SCKDIVCR2_EXTRACK2_POS R_SYSTEM_SCKDIVCR2_NPUCK_Pos
#define BSP_INTERNAL_SCKDIVCR2_EXTRACK3_POS R_SYSTEM_SCKDIVCR2_MRICK_Pos
#define STEP_DIVIDER(value) ((value) < 2U ? 2U : (value))
int main(void) {
    (void) mstp;
''' + step + r'''
    assert(regs.SCKDIVCR2 == (2U |
        (STEP_DIVIDER(TEST_EXTRA1) << R_SYSTEM_SCKDIVCR2_CPUCK1_Pos) |
        (STEP_DIVIDER(TEST_EXTRA2) << R_SYSTEM_SCKDIVCR2_NPUCK_Pos) |
        (STEP_DIVIDER(TEST_EXTRA3) << R_SYSTEM_SCKDIVCR2_MRICK_Pos)));
    return 0;
}
'''
        for first in (1, 2, 3):
            for second in (1, 2, 3):
                for third in (1, 2, 3):
                    with self.subTest(dividers=(first, second, third)):
                        self.compile_run(source, ("-DBSP_CFG_CPU_CORE=0",
                                                  f"-I{ROOT / 'tools/ra8p1/layout/native'}",
                                                  f"-DTEST_EXTRA1={first}", f"-DTEST_EXTRA2={second}",
                                                  f"-DTEST_EXTRA3={third}"))

    def test_legacy_startup_executable_sections_match_pristine_head(self):
        from tools.test_ra8p1_wdt import executable_sections

        result = subprocess.run(["git", "-C", str(ROOT / "baseline"), "show",
                                 "HEAD:ra/fsp/src/bsp/mcu/all/bsp_clocks.c"],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        cc = shutil.which("cc")
        self.assertIsNotNone(cc)
        with tempfile.TemporaryDirectory(prefix="clock-legacy-") as temp:
            path = Path(temp)
            pristine = path / "pristine.c"
            pristine.write_bytes(result.stdout)
            old_startup = function(pristine, "bsp_clock_init")
            for warm in (0, 1):
                objects = []
                for name, startup in (("before", old_startup), ("after", None)):
                    # Isolate this slice from the earlier, separately tested type-6 PLL port.
                    source = self.startup_harness(startup).replace(
                        "#define BSP_FEATURE_CGC_PLLCCR_TYPE 6", "#define BSP_FEATURE_CGC_PLLCCR_TYPE 1").replace(
                        "#define BSP_FEATURE_BSP_HAS_PRCR_S 1", "#define BSP_FEATURE_BSP_HAS_PRCR_S 0")
                    c_file, obj = path / f"{name}.c", path / f"{name}.o"
                    # The canonical header exposes PRCR and PRCR_S at the same offset.
                    # Production waits have no assert-line immediates; keep fixture line shifts out of parity.
                    source = source.replace("assert((reg) == (value));", "(void)(reg);")
                    c_file.write_text(source)
                    command = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", "-c", str(c_file),
                               "-o", str(obj), "-DBSP_CFG_CPU_CORE=0", f"-I{ROOT / 'tools/ra8p1/layout/native'}",
                               "-DTEST_BCLKA=0", "-DTEST_ESW=0", f"-DTEST_WARM={warm}",
                               "-DTEST_STOPPED=0", "-DTEST_OUTPUT=2", "-DTEST_ASYNC=0",
                               "-DBSP_CFG_BCLKA_SOURCE=255", "-DBSP_CFG_BCLKA_DIV=0",
                               "-DBSP_CFG_ESWCLK_SOURCE=255", "-DBSP_CFG_ESWCLK_DIV=0",
                               "-DBSP_CFG_ESWPHYCLK_SOURCE=255", "-DBSP_CFG_ESWPHYCLK_DIV=0"]
                    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    objects.append(executable_sections(obj))
                self.assertEqual(*objects, f"Legacy startup changed with warm={warm}")

    def test_async_frequency_legal_and_prohibited_register_encodings(self):
        getters = "\n".join(function(BSP / "bsp_common.h", name) for name in (
            "R_FSP_AsyncClockHzGet", "R_FSP_BclkaClockHzGet", "R_FSP_EswClockHzGet", "R_FSP_EswPhyClockHzGet"))
        self.compile_run(self.register_header() + r'''
typedef unsigned fsp_priv_source_clock_t;
static unsigned source_reads;
static uint32_t R_BSP_SourceClockHzGet(fsp_priv_source_clock_t source) {
    assert(source == 1 || (source >= 5 && source <= 10));
    source_reads++;
    return source == 1 ? 8000000U : (source + 1U) * 100000000U;
}
''' + getters + r'''
int main(void) {
    static const unsigned divisors[16] = {1,2,4,6,8,0,0,10,16,32,0,0,0,0,0,0};
    for (unsigned source = 0; source < 16; source++) {
        for (unsigned div = 0; div < 16; div++) {
            unsigned valid = (source == 1 || (source >= 5 && source <= 10)) && divisors[div];
            regs.BCKACR = regs.ESWCKCR = regs.ESWPCKCR = source;
            regs.BCKADIVCR = regs.ESWCKDIVCR = regs.ESWPCKDIVCR = div;
            unsigned hz = valid ? (source == 1 ? 8000000U : (source + 1U) * 100000000U) / divisors[div] : 0U;
            unsigned reads_before = source_reads;
            assert(R_FSP_BclkaClockHzGet() == hz);
            assert(R_FSP_EswClockHzGet() == hz);
            assert(R_FSP_EswPhyClockHzGet() == hz);
            assert(source_reads == reads_before + (valid ? 3U : 0U));
        }
    }
    for (unsigned flags = 0x40U; flags <= 0xc0U; flags += 0x40U) {
        regs.BCKACR = regs.ESWCKCR = regs.ESWPCKCR = flags | 5U;
        assert(R_FSP_BclkaClockHzGet() == 0 && R_FSP_EswClockHzGet() == 0 && R_FSP_EswPhyClockHzGet() == 0);
    }
    (void)mstp;
    return 0;
}
''', ("-DBSP_CFG_CPU_CORE=0", f"-I{ROOT / 'tools/ra8p1/layout/native'}"))

    def test_async_configuration_rejects_prohibited_options(self):
        source = r'''
#define BSP_FEATURE_BSP_HAS_BCLKA_CLOCK 1
#define BSP_FEATURE_BSP_HAS_ESW_CLOCK 1
#define BSP_CLOCKS_SOURCE_CLOCK_MOCO 1U
#define BSP_CLOCKS_CLOCK_DISABLED 255U
''' + self.async_configuration()
        base = {"BSP_PRV_PLL_SUPPORTED": 1, "BSP_PRV_PLL_USED": 1,
                "BSP_PRV_PLL2_SUPPORTED": 1, "BSP_PRV_PLL2_USED": 1,"BSP_CFG_BCLKA_SOURCE": 5, "BSP_CFG_BCLKA_DIV": 3, "BSP_CFG_BCLK_ASYNC": 1,
                "BSP_CFG_ESWCLK_SOURCE": 9, "BSP_CFG_ESWCLK_DIV": 2,
                "BSP_CFG_ESWPHYCLK_SOURCE": 10, "BSP_CFG_ESWPHYCLK_DIV": 1}
        variants = [({}, True)]
        for domain in ("BCLKA", "ESWCLK", "ESWPHYCLK"):
            for encoding in range(16):
                variants.append(({f"BSP_CFG_{domain}_DIV": encoding}, encoding in (0, 1, 2, 3, 4, 7, 8, 9)))
                variants.append(({f"BSP_CFG_{domain}_SOURCE": encoding}, encoding in (1, 5, 6, 7, 8, 9, 10)))
        variants += [({"BSP_CFG_BCLKA_SOURCE": 255}, False), ({"BSP_CFG_BCLK_ASYNC": 2}, False)]
        variants += [({name: 0}, False) for name in (
            "BSP_PRV_PLL_SUPPORTED", "BSP_PRV_PLL_USED", "BSP_PRV_PLL2_SUPPORTED", "BSP_PRV_PLL2_USED")]
        cc = shutil.which("cc")
        self.assertIsNotNone(cc)
        for changes, allowed in variants:
            with self.subTest(changes=changes):
                settings = base | changes
                result = subprocess.run([cc, "-E", "-P", "-x", "c", "-",
                                         *(f"-D{name}={value}" for name, value in settings.items())],
                                        input=source, capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, allowed, result.stderr)

    def test_mram_wait_notifications_and_prefetch_boundaries(self):
        functions = "\n".join(function(BSP / "bsp_clocks.c", name) for name in [
            "bsp_internal_prv_clear_pfb", "bsp_prv_mram_frequency_mhz",
            "bsp_internal_prv_set_wait_state_frequency", "bsp_internal_prv_set_pfb"])
        self.compile_run(r'''
#include <assert.h>
#include <stdint.h>
static struct { volatile uint8_t MRCPFB; volatile uint32_t MRCFREQ, MREFREQ; } regs;
#define R_MRAM (&regs)
#define R_MRAM_MRCFREQ_KEY_Pos 24U
#define R_MRAM_MREFREQ_KEY_Pos 24U
#define R_MRAM_MRCFREQ_MRCMHZ_Msk 0x3ffU
#define R_MRAM_MREFREQ_MREMHZ_Msk 0xffU
static unsigned reads;
#define FSP_REGISTER_READ(x) do { (void)(x); reads++; } while (0)
/* Preserve the production macro's argument precedence; bound the fixture wait. */
#define FSP_HARDWARE_REGISTER_WAIT(reg, required_value) \
    do { unsigned attempts = 4; while (reg != required_value) { assert(attempts--); } } while (0)
''' + functions + r'''
int main(void) {
    assert(bsp_prv_mram_frequency_mhz(0) == 0);
    assert(bsp_prv_mram_frequency_mhz(32768) == 0);
    assert(bsp_prv_mram_frequency_mhz(32769) == 1);
    assert(bsp_prv_mram_frequency_mhz(100000000) == 100);
    assert(bsp_prv_mram_frequency_mhz(100000001) == 101);
    assert(bsp_prv_mram_frequency_mhz(249900000) == 250);
    assert(bsp_prv_mram_frequency_mhz(250000000) == 250);
    bsp_internal_prv_set_wait_state_frequency(249900000, 124900000);
    assert(regs.MRCFREQ == 0x1e0000faU);
    assert(regs.MREFREQ == 0xe100007dU);
    bsp_internal_prv_set_wait_state_frequency(32768, 32768);
    assert(regs.MRCFREQ == 0x1e000000U);
    assert(regs.MREFREQ == 0xe1000000U);
    bsp_internal_prv_set_pfb(100000000);
    assert(regs.MRCPFB == 0);
    bsp_internal_prv_set_pfb(100000001);
    assert(regs.MRCPFB == 1);
    bsp_internal_prv_clear_pfb();
    assert(regs.MRCPFB == 0 && reads == 3);
    return 0;
}
''')

    def test_each_core_and_all_system_clock_fields(self):
        text = (BSP / "bsp_common.h").read_text()
        start = text.index("typedef enum e_fsp_priv_clock\n")
        end = text.index("} fsp_priv_clock_t;", start) + len("} fsp_priv_clock_t;")
        enum = text[start:end]
        production = function(BSP / "bsp_common.h", "R_FSP_SystemClockHzGet")
        source = r'''
#include <assert.h>
#include <stdint.h>
#define __STATIC_INLINE static inline
#define BSP_FEATURE_CGC_SCKDIVCR2_HAS_EXTRA_CLOCKS 1
#define BSP_CFG_CLOCKS_SECURE 1
#define FSP_PRV_SCKDIVCR_DIV_MASK 15U
#define FSP_STYPE3_REG8_READ(x,s) (x)
#define FSP_STYPE3_REG16_READ(x,s) (x)
#define FSP_STYPE3_REG32_READ(x,s) (x)
static struct { uint32_t SCKDIVCR; uint16_t SCKDIVCR2; uint8_t SCKSCR; } regs;
#define R_SYSTEM (&regs)
typedef unsigned fsp_priv_source_clock_t;
static uint32_t R_BSP_SourceClockHzGet(fsp_priv_source_clock_t source) {
    assert(source == 5);
    return 1000000000U;
}
''' + enum + "\n" + production + r'''
int main(void) {
    static const unsigned divisors[] = {1,2,4,8,16,32,64,0,3,6,12,24,0,0,0,0};
    regs.SCKSCR = 5;
    for (unsigned field = 0; field <= 44; field += 4) {
        for (unsigned encoding = 0; encoding < 16; encoding++) {
            unsigned actual_field = field;
            if (BSP_CFG_CPU_CORE == 1 && field == 32) actual_field = 36;
            regs.SCKDIVCR = 0;
            regs.SCKDIVCR2 = 0;
            if (actual_field < 32) regs.SCKDIVCR = encoding << actual_field;
            else regs.SCKDIVCR2 = encoding << (actual_field - 32);
            uint32_t expected = divisors[encoding] ? 1000000000U / divisors[encoding] : 0;
            assert(R_FSP_SystemClockHzGet((fsp_priv_clock_t)field) == expected);
        }
    }
    assert(R_FSP_SystemClockHzGet((fsp_priv_clock_t)1) == 0);
    assert(R_FSP_SystemClockHzGet((fsp_priv_clock_t)48) == 0);
    assert(R_FSP_SystemClockHzGet((fsp_priv_clock_t)-1) == 0);
    return 0;
}
'''
        for core in (0, 1):
            with self.subTest(core=core):
                self.compile_run(source, (f"-DBSP_CFG_CPU_CORE={core}",))


if __name__ == "__main__":
    unittest.main()
