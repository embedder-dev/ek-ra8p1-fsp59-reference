/* Requirements: RA8P1 HM 11.2.17-18, 14.2.17/19-22, 14.9, 9.2.23.
 * Host MMIO/control-flow evidence only; not a standby sequence or power test. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "r_lpm.h"

R_SYSTEM_Type test_system;
R_ICU_Type test_icu[2];
R_ICU_COMMON_Type test_common;
test_scb_t test_scb;
static unsigned unlocks;
static unsigned locks;
static unsigned wfi_count;
static unsigned dsb_count;
static uint8_t expected_ostdcr;

void review_assert(unsigned line) { (void) line; }
void R_BSP_RegisterProtectDisable(int protect) { (void) protect; unlocks++; }
void R_BSP_RegisterProtectEnable(int protect) { (void) protect; locks++; }
void test_dsb(void) { dsb_count++; }
void test_wfi(void)
{
    assert(dsb_count == wfi_count + 1U);
    assert((R_SYSTEM->OSTDCR & 0x80U) == 0U);
    assert((R_SYSTEM->OSTDCR & 1U) == (expected_ostdcr & 1U));
    wfi_count++;
}

static lpm_cfg_t setup(lpm_mode_t mode)
{
    memset(&test_system, 0, sizeof(test_system));
    memset(&test_icu, 0, sizeof(test_icu));
    memset(&test_common, 0, sizeof(test_common));
    memset(&test_scb, 0, sizeof(test_scb));
    unlocks = locks = wfi_count = dsb_count = 0;
    R_SYSTEM->DPSBYCR = 0x04U; /* DCSSMODE, HM 11.2.22 */
    R_SYSTEM->PDRAMSCR0 = 0x7FFFU;
    R_SYSTEM->PDRAMSCR1 = 3U;
    lpm_cfg_t cfg = {0};
    cfg.low_power_mode = mode;
    return cfg;
}

static void rejected(lpm_instance_ctrl_t *ctrl, lpm_cfg_t const *cfg, fsp_err_t error)
{
    R_SYSTEM_Type system_before;
    R_ICU_Type icu_before[2];
    R_ICU_COMMON_Type common_before;
    lpm_instance_ctrl_t ctrl_before = *ctrl;
    memcpy(&system_before, &test_system, sizeof(test_system));
    memcpy(&icu_before, &test_icu, sizeof(test_icu));
    memcpy(&common_before, &test_common, sizeof(test_common));
    unsigned before = unlocks;
    assert(R_LPM_LowPowerReconfigure(ctrl, cfg) == error);
    assert(memcmp(&ctrl_before, ctrl, sizeof(*ctrl)) == 0);
    assert(memcmp(&system_before, &test_system, sizeof(test_system)) == 0);
    assert(memcmp(&icu_before, &test_icu, sizeof(test_icu)) == 0);
    assert(memcmp(&common_before, &test_common, sizeof(test_common)) == 0);
    assert(unlocks == before);
}

static void retention(void)
{
    /* Every supported grouped SRAM choice, both initial other-core TCM states. */
    for (unsigned combination = 0; combination < 16; combination++)
    {
        for (unsigned initial = 0; initial < 4; initial++)
        {
            for (unsigned keep = 0; keep < 2; keep++)
            {
                lpm_cfg_t cfg = setup(LPM_MODE_STANDBY);
                lpm_instance_ctrl_t ctrl = {0};
                unsigned mask = ((combination & 1U) ? 0xFU : 0U) |
                                ((combination & 2U) ? 0xF0U : 0U) |
                                ((combination & 4U) ? 0xF00U : 0U) |
                                ((combination & 8U) ? 0x1000U : 0U);
                cfg.ram_retention_cfg.ram_retention = (uint16_t) mask;
                cfg.ram_retention_cfg.tcm_retention = keep != 0;
                R_SYSTEM->PDRAMSCR1 = (uint8_t) initial;
                R_SYSTEM_Type expected = test_system;
                expected.PDRAMSCR0 = (uint16_t) (0x6000U | mask);
                expected.PDRAMSCR1 = (uint8_t) ((initial & ~(1U << BSP_CFG_CPU_CORE)) |
                                              (keep << BSP_CFG_CPU_CORE));
                expected.LPSCR = LPM_CFG_STANDBY_LIMIT ? 0U : 5U;
                assert(R_LPM_Open(&ctrl, &cfg) == FSP_SUCCESS);
                assert(memcmp(&expected, &test_system, sizeof(expected)) == 0);
                assert(R_SYSTEM->PDRAMSCR0 == (0x6000U | mask));
                assert(R_SYSTEM->PDRAMSCR1 == ((initial & ~(1U << BSP_CFG_CPU_CORE)) |
                                                              (keep << BSP_CFG_CPU_CORE)));
                assert(unlocks == locks);
            }
        }
    }
    lpm_cfg_t cfg = setup(LPM_MODE_DEEP_SLEEP);
    lpm_instance_ctrl_t ctrl = {0};
    cfg.ram_retention_cfg.tcm_retention = false;
    assert(R_LPM_Open(&ctrl, &cfg) == FSP_SUCCESS);
    assert(R_SYSTEM->PDRAMSCR0 == 0x7FFFU);
    assert(R_SYSTEM->PDRAMSCR1 == (3U & ~(1U << BSP_CFG_CPU_CORE)));
    cfg.low_power_mode = LPM_MODE_STANDBY;
    /* Exhaust all 16-bit inputs: only complete nibbles and RKEEP12 are legal. */
    for (unsigned mask = 0; mask <= 0xFFFFU; mask++)
    {
        bool valid = (mask & 0xE000U) == 0U;
        for (unsigned shift = 0; shift < 12; shift += 4)
        {
            unsigned nibble = (mask >> shift) & 15U;
            valid = valid && ((nibble == 0U) || (nibble == 15U));
        }
        if (!valid)
        {
            cfg.ram_retention_cfg.ram_retention = (uint16_t) mask;
            rejected(&ctrl, &cfg, FSP_ERR_INVALID_MODE);
        }
    }
}

/* Independent HM Table 14.5 event numbers indexed by WUPEN bit. */
static unsigned event_for(unsigned source)
{
    static const unsigned short peripheral[32] = {
        [0] = 0x92, [2] = 0x70, [3] = 0x71, [4] = 0x75,
        [8] = 0x95, [9] = 0x96, [10] = 0x2C3, [11] = 0x9B,
        [12] = 0x89, [13] = 0x8A, [14] = 0x8B, [15] = 0xA0,
        [19] = 0xC6, [23] = 0x77, [24] = 0x80, [25] = 0x81,
        [26] = 0x82, [27] = 0x34A, [28] = 0x83, [29] = 0x84,
        [30] = 0x85, [31] = 0xC2
    };
    if (source < 16) { return source + 1; }
    if (source >= 48) { return source - 31; }
    return peripheral[source - 16];
}

static void wake(void)
{
    for (unsigned source = 0; source < 64; source++)
    {
        unsigned event = event_for(source);
        if (!event) { continue; }
        for (unsigned slot = 0; slot < 96; slot++)
        {
            lpm_cfg_t cfg = setup((slot & 1U) ? LPM_MODE_STANDBY : LPM_MODE_DEEP_SLEEP);
            lpm_instance_ctrl_t ctrl = {0};
            cfg.standby_wake_sources = 1ULL << source;
            /* Slot numbers deliberately have no relationship to source bits. */
            R_ICU->IELSR[slot] = event | (1U << 16); /* preserve pending IR */
            if (BSP_CFG_CPU_CORE)
            {
                R_ICU_COMMON->INTSELR[event / 32] |= 1U << (event % 32);
            }
            test_icu[1 - BSP_CFG_CPU_CORE].DSLPWUPIRQEN[0] = 0xA5A5A5A5;
            test_icu[1 - BSP_CFG_CPU_CORE].IELSR[slot] = 0xDEADBEEF;
            R_ICU_Type other = test_icu[1 - BSP_CFG_CPU_CORE];
            R_ICU_COMMON_Type common = test_common;
            R_ICU_Type expected = *R_ICU;
            expected.WUPEN = (uint32_t) cfg.standby_wake_sources;
            expected.WUPEN1 = (uint32_t) (cfg.standby_wake_sources >> 32);
            expected.DSLPWUPIRQEN[slot / 32] = 1U << (slot % 32);
            assert(R_LPM_Open(&ctrl, &cfg) == FSP_SUCCESS);
            assert(memcmp(&expected, R_ICU, sizeof(expected)) == 0);
            assert(memcmp(&other, &test_icu[1 - BSP_CFG_CPU_CORE], sizeof(other)) == 0);
            assert(memcmp(&common, &test_common, sizeof(common)) == 0);
            /* Reconfigure removes old slot enables rather than accumulating them. */
            cfg.standby_wake_sources = 0;
            assert(R_LPM_LowPowerReconfigure(&ctrl, &cfg) == FSP_SUCCESS);
            for (unsigned word = 0; word < 3; word++) { assert(R_ICU->DSLPWUPIRQEN[word] == 0); }
            cfg.standby_wake_sources = 1ULL << source;
            R_ICU->IELSR[slot] = 0;
            rejected(&ctrl, &cfg, FSP_ERR_INVALID_MODE);
            R_ICU->IELSR[slot] = event | (1U << 24); /* DTC-only is not a CPU wake slot. */
            rejected(&ctrl, &cfg, FSP_ERR_INVALID_MODE);
            R_ICU->IELSR[slot] = event;
            R_ICU_COMMON->INTSELR[event / 32] ^= 1U << (event % 32);
            rejected(&ctrl, &cfg, FSP_ERR_INVALID_MODE);
        }
    }
}

static void nmi(void)
{
    static unsigned const sources[] = {16, 18, 19, 39};
    static unsigned const enables[] = {0, 2, 3, 5};
    for (unsigned i = 0; i < 4; i++)
    {
        lpm_cfg_t cfg = setup(LPM_MODE_STANDBY);
        lpm_instance_ctrl_t ctrl = {0};
        cfg.standby_wake_sources = 1ULL << sources[i];
        /* Current-core NMI selection is an alternative, not a vector-slot number. */
        R_ICU->NMIER = 1U << enables[i];
        R_ICU_Type expected = *R_ICU;
        expected.WUPEN = (uint32_t) cfg.standby_wake_sources;
        expected.WUPEN1 = (uint32_t) (cfg.standby_wake_sources >> 32);
        assert(R_LPM_Open(&ctrl, &cfg) == FSP_SUCCESS);
        assert(memcmp(&expected, R_ICU, sizeof(expected)) == 0);
        R_ICU->NMIER = 0;
        test_icu[1 - BSP_CFG_CPU_CORE].NMIER = 1U << enables[i];
        rejected(&ctrl, &cfg, FSP_ERR_INVALID_MODE);
    }
}

static void invalid(void)
{
    lpm_cfg_t good = setup(LPM_MODE_SLEEP);
    lpm_instance_ctrl_t ctrl = {0};
    assert(R_LPM_Open(&ctrl, &good) == FSP_SUCCESS);
    rejected(&ctrl, NULL, FSP_ERR_ASSERTION);
    lpm_cfg_t bad = good;
    for (int mode = -8; mode < 16; mode++)
    {
        if ((mode == LPM_MODE_SLEEP) || (mode == LPM_MODE_DEEP_SLEEP) ||
            (mode == LPM_MODE_STANDBY) || (mode == LPM_MODE_DEEP)) { continue; }
        bad.low_power_mode = (lpm_mode_t) mode;
        rejected(&ctrl, &bad, mode == LPM_MODE_STANDBY_SNOOZE ? FSP_ERR_UNSUPPORTED : FSP_ERR_INVALID_MODE);
    }
    bad = good;
    bad.low_power_mode = LPM_MODE_DEEP;
    for (unsigned bit = 0; bit < 64; bit++)
    {
        bad.deep_standby_cancel_source = 1ULL << bit;
        bad.deep_standby_cancel_edge = 0;
        if (!(0xFFFFEF1FFFFFULL & (1ULL << bit))) { rejected(&ctrl, &bad, FSP_ERR_INVALID_MODE); }
        bad.deep_standby_cancel_source = 0xFFFFEF1FFFFFULL;
        bad.deep_standby_cancel_edge = 1ULL << bit;
        if (!(0xFFFF13FFFFULL & (1ULL << bit))) { rejected(&ctrl, &bad, FSP_ERR_INVALID_MODE); }
    }
    lpm_instance_ctrl_t unopened = {0};
    unopened.p_cfg = &good;
    bad.deep_standby_cancel_source = 1ULL << 48;
    bad.deep_standby_cancel_edge = 0;
    unsigned before = unlocks;
    assert(R_LPM_Open(&unopened, &bad) == FSP_ERR_INVALID_MODE);
    assert(unopened.lpm_open == 0 && unopened.p_cfg == &good && unlocks == before);
    bad.deep_standby_cancel_edge = 1ULL << 39;
    bad.deep_standby_cancel_source = 1ULL << 39; /* edge IRQ31 needs SOURCE bit47 */
    rejected(&ctrl, &bad, FSP_ERR_INVALID_MODE);
    bad.deep_standby_cancel_source = 1ULL << 47;
    assert(R_LPM_LowPowerReconfigure(&ctrl, &bad) == FSP_SUCCESS);
    assert(R_SYSTEM->DPSIER5 == 0x80U && R_SYSTEM->DPSIEGR4 == 0x80U);
    assert(ctrl.p_cfg == &bad);
}

static void oscillator(void)
{
    for (unsigned detect = 0; detect < 2; detect++)
    {
        for (unsigned interrupt = 0; interrupt < 2; interrupt++)
        {
            lpm_cfg_t cfg = setup(LPM_MODE_STANDBY);
            lpm_instance_ctrl_t ctrl = {0};
            expected_ostdcr = (uint8_t) ((detect << 7) | interrupt);
            R_SYSTEM->OSTDCR = expected_ostdcr;
            assert(R_LPM_Open(&ctrl, &cfg) == FSP_SUCCESS);
            assert(R_LPM_LowPowerModeEnter(&ctrl) == FSP_SUCCESS);
            assert(wfi_count == 1U && dsb_count == 1U);
            assert(R_SYSTEM->OSTDCR == expected_ostdcr);
            assert(unlocks == locks);
        }
    }
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    if (!strcmp(argv[1], "retention")) { retention(); }
    else if (!strcmp(argv[1], "wake")) { wake(); }
    else if (!strcmp(argv[1], "nmi")) { nmi(); }
    else if (!strcmp(argv[1], "invalid")) { invalid(); }
    else if (!strcmp(argv[1], "oscillator")) { oscillator(); }
    else { abort(); }
    puts("review LPM requirements passed");
    return 0;
}
