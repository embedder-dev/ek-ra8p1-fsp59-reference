"""Run the production type-6 startup voltage switch against native register mocks."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SOURCE = (Path(__file__).resolve().parents[2]
          / "baseline/ra/fsp/src/bsp/mcu/all/bsp_clocks.c")

MOCK = r"""
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define BSP_FEATURE_CGC_PLLCCR_TYPE 6U
static enum { PRIOR_TRANSITION, READY, REQUESTED, COMPLETE } phase;
static struct system_registers { volatile uint8_t VSCR; } system_regs;

#if __CORTEX_M == 85U
#define SCB_CCR_IC_Msk (1U << 17)
#define SCB_CCR_DC_Msk (1U << 16)
#define MEMSYSCTL_MSCR_ICACTIVE_Msk (1U << 13)
#define MEMSYSCTL_MSCR_DCACTIVE_Msk (1U << 12)
#define ENABLE_MASK (SCB_CCR_IC_Msk | SCB_CCR_DC_Msk)
#define ACTIVE_MASK (MEMSYSCTL_MSCR_ICACTIVE_Msk | MEMSYSCTL_MSCR_DCACTIVE_Msk)
static struct { volatile uint32_t CCR; } scb;
static struct { volatile uint32_t MSCR; } memsysctl;
#define SCB (&scb)
#define MEMSYSCTL (&memsysctl)
static uint32_t initial_ccr, initial_mscr, cache_calls;
static unsigned barriers;

static void disable_cache(uint32_t mask)
{
    assert(phase == READY && system_regs.VSCR == 0U);
    assert(memsysctl.MSCR == initial_mscr);
    assert((scb.CCR & mask) == mask);
    scb.CCR &= ~mask;
    cache_calls |= mask;
}

static void enable_cache(uint32_t mask)
{
    assert(phase == COMPLETE && barriers == 2U);
    assert(memsysctl.MSCR == initial_mscr);
    assert((initial_ccr & mask) == mask && (scb.CCR & mask) == 0U);
    scb.CCR |= mask;
    cache_calls |= mask;
}

#define SCB_DisableICache() disable_cache(SCB_CCR_IC_Msk)
#define SCB_DisableDCache() disable_cache(SCB_CCR_DC_Msk)
#define SCB_EnableICache() enable_cache(SCB_CCR_IC_Msk)
#define SCB_EnableDCache() enable_cache(SCB_CCR_DC_Msk)

static void __DSB(void)
{
    assert(phase == READY || phase == COMPLETE);
    assert(scb.CCR == (initial_ccr & ~ENABLE_MASK));
    assert(memsysctl.MSCR == (phase == READY ? initial_mscr & ~ACTIVE_MASK : initial_mscr));
    barriers = 1U;
}

static void __ISB(void)
{
    assert(barriers == 1U);
    barriers = 2U;
}

static void check_quiesced(void)
{
    assert(cache_calls == (initial_ccr & ENABLE_MASK) && barriers == 2U);
    assert(scb.CCR == (initial_ccr & ~ENABLE_MASK));
    assert(memsysctl.MSCR == (initial_mscr & ~ACTIVE_MASK));
}
#endif

/* Waits intercept the register token, so the lvalue accessor sees the VSCR store itself. */
static struct system_registers *voltage_request(void)
{
    assert(phase == READY && system_regs.VSCR == 0U);
#if __CORTEX_M == 85U
    check_quiesced();
#endif
    phase = REQUESTED;
    return &system_regs;
}

static void wait_for_transition(const char *reg, unsigned expected)
{
    assert(strcmp(reg, "R_SYSTEM->VSCR_b.VSCMTSF") == 0 && expected == 0U);
    if (phase == PRIOR_TRANSITION)
    {
        assert(system_regs.VSCR == 0U);
#if __CORTEX_M == 85U
        assert(scb.CCR == initial_ccr && memsysctl.MSCR == initial_mscr);
#endif
        phase = READY;
        return;
    }

    assert(phase == REQUESTED && system_regs.VSCR == 1U);
#if __CORTEX_M == 85U
    check_quiesced();
    cache_calls = 0U;
    barriers = 0U;
#endif
    phase = COMPLETE;
}

#define R_SYSTEM (voltage_request())
#define FSP_HARDWARE_REGISTER_WAIT(reg, value) wait_for_transition(#reg, (value))

static void startup_dvfs(void)
{
#include "production.inc"
}

int main(int argc, char **argv)
{
#if __CORTEX_M == 85U
    assert(argc == 3);
    scb.CCR = initial_ccr = (uint32_t)strtoul(argv[1], NULL, 16);
    memsysctl.MSCR = initial_mscr = (uint32_t)strtoul(argv[2], NULL, 16);
#else
    (void)argc;
    (void)argv;
#endif
    startup_dvfs();
    assert(phase == COMPLETE && system_regs.VSCR == 1U);
#if __CORTEX_M == 85U
    assert(cache_calls == (initial_ccr & ENABLE_MASK) && barriers == 2U);
    assert(scb.CCR == initial_ccr && memsysctl.MSCR == initial_mscr);
#endif
    return 0;
}
"""


class StartupDvfsTests(unittest.TestCase):
    def command(self, args):
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_type6_startup_voltage_transitions(self):
        cc = shutil.which("cc")
        self.assertIsNotNone(cc, "A native C compiler is required")
        source = SOURCE.read_text()
        init = source.index("void bsp_clock_init (void)")
        stop = source.index("    /* Start clocks that require other clocks.", init)
        start = source.rindex("#if (6U == BSP_FEATURE_CGC_PLLCCR_TYPE)\n", init, stop)
        line = source.count("\n", 0, start) + 1
        with tempfile.TemporaryDirectory(prefix="startup-dvfs-") as tmp:
            directory = Path(tmp)
            (directory / "production.inc").write_text(f'#line {line} "bsp_clocks.c"\n' + source[start:stop])
            fixture = directory / "fixture.c"
            fixture.write_text(MOCK)
            for core, cases in (
                (85, (
                    ("Rev A reset", "000e0201", "00013004"),
                    ("both caches enabled", "000f0201", "00013004"),
                    ("neither enabled, only D active", "000c0201", "00011004"),
                )),
                (33, (("no cache support",),)),
            ):
                with self.subTest(core=core):
                    binary = directory / f"dvfs-m{core}"
                    self.command([cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
                                  f"-D__CORTEX_M={core}", str(fixture), "-o", str(binary)])
                    for case, *registers in cases:
                        with self.subTest(case=case):
                            self.command([str(binary), *registers])


if __name__ == "__main__":
    unittest.main()
