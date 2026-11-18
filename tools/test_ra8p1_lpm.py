"""Execute production LPM C with real device/API headers and host-backed MMIO.

Only CMSIS instructions and BSP services are mocked. No register members or
hardware aliases are supplied by this harness. The target WUPEN view must come
from the canonical generated device header.
"""
from pathlib import Path
import itertools
import shutil
import subprocess
import tempfile
import unittest

from test_ra8p1_wdt import executable_sections

ROOT = Path(__file__).resolve().parents[1]
FSP = ROOT / "baseline/ra/fsp"
SOURCE = FSP / "src/r_lpm/r_lpm.c"
DEVICE = FSP / "src/bsp/cmsis/Device/RENESAS/Include"

CORE = r"""
#ifndef TEST_CORE_H
#define TEST_CORE_H
#include <stdint.h>
#define __IM volatile const
#define __OM volatile
#define __IOM volatile
#define __I volatile const
#define __O volatile
#define __IO volatile
#define SCB_SCR_SLEEPDEEP_Msk (1UL << 2)
typedef struct { volatile uint32_t SCR; } test_scb_t;
extern test_scb_t test_scb;
#define SCB (&test_scb)
void test_dsb(void);
void test_wfi(void);
#define __DSB() test_dsb()
#define __WFI() test_wfi()
#endif
"""

BSP = r"""
#ifndef BSP_API_H
#define BSP_API_H
#include <stdbool.h>
#include <stddef.h>
#include "fsp_common_api.h"
#include "bsp_feature.h"
#include "bsp_elc.h"
#include "bsp_override.h"
#if TEST_TARGET
#include "R7KA8P1KF.h"
#else
#include "R7FA8M1AH.h"
#endif
/* Relocate register blocks to host storage, retaining production types/members. */
extern R_SYSTEM_Type test_system;
#undef R_SYSTEM
#undef R_ICU
#define R_SYSTEM (&test_system)
#if TEST_TARGET
extern R_ICU_Type test_icu[2];
extern R_ICU_COMMON_Type test_icu_common;
#undef R_ICU_COMMON
#define R_ICU (&test_icu[BSP_CFG_CPU_CORE])
#define R_ICU_COMMON (&test_icu_common)
#else
extern R_ICU_Type test_icu;
#define R_ICU (&test_icu)
#endif
#define FSP_ERROR_RETURN(condition, error) { if (!(condition)) { return (error); } }
#define FSP_ASSERT(condition) FSP_ERROR_RETURN(condition, FSP_ERR_ASSERTION)
#define FSP_HARDWARE_REGISTER_WAIT(value, expected) do { assert((value) == (expected)); } while (0)
#define FSP_STYPE3_REG8_READ(value, secure) (value)
#define BSP_REG_PROTECT_OM_LPC_BATT 1
#define BSP_REG_PROTECT_CGC 2
void R_BSP_RegisterProtectDisable(int protect);
void R_BSP_RegisterProtectEnable(int protect);
#endif
"""

HARNESS = r"""
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "r_lpm.h"

R_SYSTEM_Type test_system;
#if TEST_TARGET
R_ICU_Type test_icu[2];
R_ICU_COMMON_Type test_icu_common;
#else
R_ICU_Type test_icu;
#endif
test_scb_t test_scb;
static lpm_cfg_t cfg;
static unsigned dsb_count;
static unsigned wfi_count;
static unsigned unlocked;

void R_BSP_RegisterProtectDisable(int protect)
{
    unlocked |= (unsigned) protect;
}

void R_BSP_RegisterProtectEnable(int protect)
{
    unlocked &= ~(unsigned) protect;
}

void test_dsb(void)
{
    dsb_count++;
}

void test_wfi(void)
{
    assert(dsb_count == wfi_count + 1U);
    wfi_count++;
    assert((SCB->SCR & SCB_SCR_SLEEPDEEP_Msk) ==
           (cfg.low_power_mode == LPM_MODE_SLEEP ? 0U : SCB_SCR_SLEEPDEEP_Msk));
    assert(R_SYSTEM->LPSCR == (cfg.low_power_mode == LPM_MODE_STANDBY ?
           (TEST_TARGET || BSP_MCU_GROUP_NEPTUNE ? 5U : 4U) :
           (cfg.low_power_mode == LPM_MODE_DEEP ? 8U | cfg.power_supply_state : 0U)));
    assert(unlocked & BSP_REG_PROTECT_OM_LPC_BATT);
    if (cfg.low_power_mode >= LPM_MODE_STANDBY)
    {
        assert((R_SYSTEM->OSTDCR & R_SYSTEM_OSTDCR_OSTDE_Msk) == 0);
    }
    if (cfg.low_power_mode == LPM_MODE_DEEP)
    {
        assert(R_SYSTEM->DPSIFR0 == 0 && R_SYSTEM->DPSIFR1 == 0);
        assert(R_SYSTEM->DPSIFR2 == 0 && R_SYSTEM->DPSIFR3 == 0);
#if TEST_TARGET
        assert(R_SYSTEM->DPSIFR4 == 0 && R_SYSTEM->DPSIFR5 == 0);
        assert(R_SYSTEM->SYOCDCR == 0x80U);
#else
        assert(R_SYSTEM->SYOCDCR_b.DOCDF == 0);
#endif
    }
}

static void run_mode(lpm_mode_t mode, lpm_power_supply_t supply)
{
    lpm_instance_ctrl_t ctrl = {0};
    memset(&test_system, 0, sizeof(test_system));
    memset(&test_icu, 0, sizeof(test_icu));
#if TEST_TARGET
    memset(&test_icu_common, 0, sizeof(test_icu_common));
#endif
    memset(&cfg, 0, sizeof(cfg));
    dsb_count = 0;
    wfi_count = 0;
    unlocked = 0;
    SCB->SCR = 0x10U;
    cfg.low_power_mode = mode;
    cfg.power_supply_state = supply;
    cfg.standby_wake_sources = (1ULL << 24) | 1ULL;
    cfg.output_port_enable = LPM_OUTPUT_PORT_ENABLE_RETAIN;
    cfg.io_port_state = LPM_IO_PORT_NO_CHANGE;
    cfg.deep_standby_cancel_source = LPM_DEEP_STANDBY_CANCEL_SOURCE_IRQ0;
    cfg.deep_standby_cancel_edge = LPM_DEEP_STANDBY_CANCEL_SOURCE_IRQ0_RISING;
    cfg.ram_retention_cfg.ram_retention = 1U;
    cfg.ram_retention_cfg.tcm_retention = true;
    R_SYSTEM->SYOCDCR = 0x80U;
#if TEST_TARGET
    R_SYSTEM->DPSBYCR = 1U << R_SYSTEM_DPSBYCR_DCSSMODE_Pos;
#endif
#if !TEST_TARGET
    R_SYSTEM->SYOCDCR_b.DOCDF = 1;
#endif
    R_SYSTEM->OPCCR = 0;
    /* Start with oscillator-stop detection disabled and its interrupt-enable bit retained. */
    R_SYSTEM->OSTDCR = R_SYSTEM_OSTDCR_OSTDIE_Msk;
    R_SYSTEM->DPSIFR0 = 0xFF;
    R_SYSTEM->DPSIFR1 = 0xFF;
    R_SYSTEM->DPSIFR2 = 0xFF;
    R_SYSTEM->DPSIFR3 = 0xFF;
#if TEST_TARGET
    /* HM 11.2.17-18: SRAM0 is one group; preserve the other core's TCM bit. */
    cfg.ram_retention_cfg.ram_retention = 0xFU;
    R_SYSTEM->PDRAMSCR0 = 0x7FFFU;
    R_SYSTEM->PDRAMSCR1 = 1U << (1U - BSP_CFG_CPU_CORE);
    cfg.standby_wake_sources |= LPM_STANDBY_WAKE_SOURCE_IRQ16;
    cfg.deep_standby_cancel_source |= LPM_DEEP_STANDBY_CANCEL_SOURCE_IRQ16 |
                                       LPM_DEEP_STANDBY_CANCEL_SOURCE_IRQ31;
    cfg.deep_standby_cancel_edge |= LPM_DEEP_STANDBY_CANCEL_SOURCE_IRQ16_RISING |
                                     LPM_DEEP_STANDBY_CANCEL_SOURCE_IRQ31_RISING;
    R_SYSTEM->DPSIFR4 = 0xFF;
    R_SYSTEM->DPSIFR5 = 0xFF;
    /* HM Table 14.5: IRQ0/RTC_ALM/IRQ16 events in unrelated NVIC slots.
     * HM 14.9: DSLPWUPIRQEN selects slots, while INTSELR selects the CPU. */
    R_ICU->IELSR[7] = 0x001U | (1U << 16); /* Pending IR must survive. */
    R_ICU->IELSR[46] = 0x095U;
    R_ICU->IELSR[95] = 0x011U;
    R_ICU->IELSR[9] = 0x001U | (1U << 24); /* DTC-only, not a CPU wake slot. */
    R_ICU_COMMON->INTSELR[0] = BSP_CFG_CPU_CORE ? (1U << 1) | (1U << 17) : 0U;
    R_ICU_COMMON->INTSELR[4] = BSP_CFG_CPU_CORE ? 1U << 21 : 0U;
    R_ICU->DSLPWUPIRQEN[0] = 0x12345678U;
    R_ICU->DSLPWUPIRQEN[1] = 0x87654321U;
    R_ICU->DSLPWUPIRQEN[2] = 0x11223344U;
    test_icu[1U - BSP_CFG_CPU_CORE].IELSR[7] = 0x095U;
    test_icu[1U - BSP_CFG_CPU_CORE].DSLPWUPIRQEN[0] = 0xA5A5A5A5U;
    test_icu[1U - BSP_CFG_CPU_CORE].DSLPWUPIRQEN[1] = 0x5A5A5A5AU;
    test_icu[1U - BSP_CFG_CPU_CORE].DSLPWUPIRQEN[2] = 0xF0F0F0F0U;
    R_ICU_Type other_icu_before = test_icu[1U - BSP_CFG_CPU_CORE];
    R_ICU_COMMON_Type common_before = test_icu_common;
    R_ICU_Type expected_icu = *R_ICU;
    if (mode != LPM_MODE_SLEEP)
    {
        expected_icu.WUPEN0 = (uint32_t) cfg.standby_wake_sources;
        expected_icu.WUPEN1 = (uint32_t) (cfg.standby_wake_sources >> 32);
    }
    if ((mode == LPM_MODE_DEEP_SLEEP) || (mode == LPM_MODE_STANDBY))
    {
        expected_icu.DSLPWUPIRQEN[0] = 1U << 7;
        expected_icu.DSLPWUPIRQEN[1] = 1U << 14;
        expected_icu.DSLPWUPIRQEN[2] = 1U << 31;
    }
#endif
    assert(g_lpm_on_lpm.open(&ctrl, &cfg) == FSP_SUCCESS);
    assert(ctrl.p_cfg == &cfg && ctrl.lpm_open != 0);
    assert(R_SYSTEM->LPSCR == (LPM_CFG_STANDBY_LIMIT ? 0U :
           (mode == LPM_MODE_STANDBY ? (TEST_TARGET || BSP_MCU_GROUP_NEPTUNE ? 5U : 4U) :
           (mode == LPM_MODE_DEEP ? 8U | supply : 0U))));
    assert(unlocked == 0);
#if TEST_TARGET
    assert((R_SYSTEM->DPSBYCR & R_SYSTEM_DPSBYCR_DCSSMODE_Msk) ==
           (1U << R_SYSTEM_DPSBYCR_DCSSMODE_Pos));
    if (mode == LPM_MODE_DEEP)
    {
        assert(R_SYSTEM->DPSIER4 == 1U && R_SYSTEM->DPSIER5 == 0x80U);
        assert(R_SYSTEM->DPSIEGR3 == 1U && R_SYSTEM->DPSIEGR4 == 0x80U);
    }
#endif
    if (mode != LPM_MODE_SLEEP)
    {
        assert(R_ICU->WUPEN == (uint32_t) cfg.standby_wake_sources);
#if TEST_TARGET
        assert(R_ICU->WUPEN0 == R_ICU->WUPEN);
        assert(R_ICU->WUPEN1 == 0x10000U);
#endif
#if !TEST_TARGET
        assert(R_SYSTEM->PDRAMSCR1 == (mode == LPM_MODE_DEEP ? 0U : 1U));
#endif
    }
#if TEST_TARGET
    assert(R_SYSTEM->PDRAMSCR0 == (mode == LPM_MODE_STANDBY ? 0x600FU : 0x7FFFU));
    assert(R_SYSTEM->PDRAMSCR1 ==
           (((mode == LPM_MODE_DEEP_SLEEP) || (mode == LPM_MODE_STANDBY)) ?
            3U : 1U << (1U - BSP_CFG_CPU_CORE)));
    assert(memcmp(&expected_icu, R_ICU, sizeof(expected_icu)) == 0);
    assert(memcmp(&other_icu_before, &test_icu[1U - BSP_CFG_CPU_CORE], sizeof(other_icu_before)) == 0);
    assert(memcmp(&common_before, &test_icu_common, sizeof(common_before)) == 0);
#endif
    assert(g_lpm_on_lpm.lowPowerModeEnter(&ctrl) == FSP_SUCCESS);
    assert(wfi_count == 1 && dsb_count == 1);
    assert(SCB->SCR == 0x10U);
    assert(R_SYSTEM->OSTDCR == R_SYSTEM_OSTDCR_OSTDIE_Msk);
    assert(unlocked == 0);
#if TEST_TARGET
    assert(R_SYSTEM->SYOCDCR == 0x80U);
    assert(memcmp(&expected_icu, R_ICU, sizeof(expected_icu)) == 0);
    assert(memcmp(&other_icu_before, &test_icu[1U - BSP_CFG_CPU_CORE], sizeof(other_icu_before)) == 0);
    assert(memcmp(&common_before, &test_icu_common, sizeof(common_before)) == 0);
#endif
    assert(g_lpm_on_lpm.ioKeepClear(&ctrl) == FSP_SUCCESS);
    assert(R_SYSTEM->DPSBYCR_b.IOKEEP == 0);
    cfg.low_power_mode = LPM_MODE_SLEEP;
    assert(g_lpm_on_lpm.lowPowerReconfigure(&ctrl, &cfg) == FSP_SUCCESS);
    assert(R_SYSTEM->LPSCR == 0);
    assert(g_lpm_on_lpm.close(&ctrl) == FSP_SUCCESS);
    assert(ctrl.lpm_open == 0);
#if LPM_CFG_PARAM_CHECKING_ENABLE
    assert(R_LPM_Close(&ctrl) == FSP_ERR_NOT_OPEN);
    assert(R_LPM_LowPowerModeEnter(&ctrl) == FSP_ERR_NOT_OPEN);
#endif
}

int main(void)
{
    run_mode(LPM_MODE_SLEEP, LPM_POWER_SUPPLY_DEEP_STANDBY_MODE1);
    run_mode(LPM_MODE_DEEP_SLEEP, LPM_POWER_SUPPLY_DEEP_STANDBY_MODE1);
    run_mode(LPM_MODE_STANDBY, LPM_POWER_SUPPLY_DEEP_STANDBY_MODE1);
    run_mode(LPM_MODE_DEEP, LPM_POWER_SUPPLY_DEEP_STANDBY_MODE1);
    run_mode(LPM_MODE_DEEP, LPM_POWER_SUPPLY_DEEP_STANDBY_MODE2);
    run_mode(LPM_MODE_DEEP, LPM_POWER_SUPPLY_DEEP_STANDBY_MODE3);
#if LPM_CFG_PARAM_CHECKING_ENABLE
    lpm_instance_ctrl_t ctrl = {0};
    assert(R_LPM_Open(NULL, &cfg) == FSP_ERR_ASSERTION);
    assert(R_LPM_Open(&ctrl, NULL) == FSP_ERR_ASSERTION);
    cfg.low_power_mode = LPM_MODE_STANDBY_SNOOZE;
    assert(R_LPM_Open(&ctrl, &cfg) == FSP_ERR_UNSUPPORTED);
#if TEST_TARGET
    cfg.low_power_mode = LPM_MODE_DEEP;
    cfg.power_supply_state = (lpm_power_supply_t) 3;
    assert(R_LPM_Open(&ctrl, &cfg) == FSP_ERR_INVALID_MODE);
    cfg.power_supply_state = (lpm_power_supply_t) -1;
    assert(R_LPM_Open(&ctrl, &cfg) == FSP_ERR_INVALID_MODE);
    cfg.power_supply_state = LPM_POWER_SUPPLY_DEEP_STANDBY_MODE1;
#endif
    cfg.low_power_mode = LPM_MODE_STANDBY;
    cfg.standby_wake_sources = 1ULL << 17;
    assert(R_LPM_Open(&ctrl, &cfg) == FSP_ERR_INVALID_MODE);
    cfg.standby_wake_sources = 1ULL;
    assert(R_LPM_Open(&ctrl, &cfg) == FSP_SUCCESS);
    assert(R_LPM_Open(&ctrl, &cfg) == FSP_ERR_ALREADY_OPEN);
    R_SYSTEM->MOCOCR = 1;
    assert(R_LPM_LowPowerModeEnter(&ctrl) == FSP_ERR_INVALID_MODE);
    assert(unlocked == 0);
#endif
#if TEST_TARGET
    lpm_instance_ctrl_t invalid_ctrl = {0};
    cfg.low_power_mode = LPM_MODE_SLEEP;
    R_SYSTEM->DPSBYCR = 0;
    assert(R_LPM_Open(&invalid_ctrl, &cfg) == FSP_ERR_INVALID_MODE);
    assert(invalid_ctrl.lpm_open == 0 && unlocked == 0);
    _Static_assert(LPM_STANDBY_WAKE_SOURCE_IRQ31 == (1ULL << 63), "IRQ31 wake encoding");
    _Static_assert(LPM_STANDBY_WAKE_SOURCE_SOSTD == (1ULL << 39), "SOSC wake encoding");
    _Static_assert(LPM_STANDBY_WAKE_SOURCE_PDM == (1ULL << 47), "PDM wake encoding");
    _Static_assert(LPM_SNOOZE_CANCEL_SOURCE_NONE == 0, "Neutral snooze encoding");
#endif
    puts("production LPM behavior passed");
    return 0;
}
"""


class LpmProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("cc")
        if cls.cc is None:
            raise RuntimeError("Native C compiler required for production LPM tests")

    def fixture(self, directory, target, core, checks, limit, neptune=0):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "bsp_api.h").write_text(BSP)
        (directory / "core_cm85.h").write_text(CORE)
        (directory / "core_cm33.h").write_text(CORE)
        (directory / "r_lpm_cfg.h").write_text(
            f"#define LPM_CFG_PARAM_CHECKING_ENABLE {checks}\n"
            f"#define LPM_CFG_STANDBY_LIMIT {limit}\n")
        (directory / "harness.c").write_text(HARNESS)
        return [self.cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                f"-DTEST_TARGET={target}", f"-DBSP_CFG_CPU_CORE={core}",
                f"-DBSP_MCU_GROUP_NEPTUNE={neptune}",
                "-I" + str(directory), "-I" + str(DEVICE),
                "-I" + str(FSP / ("src/bsp/mcu/ra8p1" if target else "src/bsp/mcu/ra8m1")),
                "-I" + str(FSP / "inc/api"), "-I" + str(FSP / "inc/instances"),
                "-I" + str(FSP / "inc")]

    def checked(self, command):
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, " ".join(command) + "\n" + result.stdout + result.stderr)
        return result

    def test_production_behavior_both_cores_checks_and_standby_limit(self):
        with tempfile.TemporaryDirectory(prefix="lpm-behavior-") as temporary:
            directory = Path(temporary)
            for target, core, checks, limit in itertools.product((0, 1), (0, 1), (0, 1), (0, 1)):
                if not target and core:
                    continue
                with self.subTest(target=target, core=core, checks=checks, limit=limit):
                    command = self.fixture(directory, target, core, checks, limit)
                    binary = directory / "lpm"
                    self.checked(command + ["-fsanitize=undefined", "-fno-sanitize-recover=all",
                                            str(SOURCE), str(directory / "harness.c"), "-o", str(binary)])
                    self.assertIn("production LPM behavior passed", self.checked([str(binary)]).stdout)

    def test_legacy_macro_off_executable_sections_match_original_fsp59(self):
        original = self.checked(["git", "-C", str(ROOT / "baseline"), "show",
                                 "HEAD:ra/fsp/src/r_lpm/r_lpm.c"]).stdout
        with tempfile.TemporaryDirectory(prefix="lpm-parity-") as temporary:
            directory = Path(temporary)
            pristine = directory / "original.c"
            pristine.write_text(original)
            for checks, limit, neptune in itertools.product((0, 1), repeat=3):
                with self.subTest(checks=checks, limit=limit, neptune=neptune):
                    command = self.fixture(directory, 0, 0, checks, limit, neptune)
                    before, after = directory / "before.o", directory / "after.o"
                    for source, output in ((pristine, before), (SOURCE, after)):
                        self.checked(command + ["-O2", "-c", str(source), "-o", str(output)])
                    self.assertEqual(executable_sections(before), executable_sections(after))


if __name__ == "__main__":
    unittest.main()
