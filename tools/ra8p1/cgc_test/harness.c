#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "r_cgc.h"

R_SYSTEM_Type cgc_test_system;
R_ICU_Type cgc_test_icu;
uint32_t SystemCoreClock = 8000000U;
static unsigned protection_disable_calls;
static unsigned protection_enable_calls;
static unsigned clock_set_calls;
static unsigned group_registrations;
static void (* nmi_callback)(bsp_grp_irq_t);
static uint32_t pll_frequencies[2][3];
static unsigned callback_calls;
static unsigned context;
static cgc_callback_args_t * expected_callback_memory;

/* HM9.11.5.2 p416 Table9.16 steps7–9 separates HOCOSF from elapsed tFLLWT.
 * This models oscillator readiness only, never completion of FLL settling.
 */
#ifndef TEST_FLL_MIN_US
 #define TEST_FLL_MIN_US 1920U /* HM70.3.2 Table70.50 p4117, standard product. */
#endif
static bool fll_started;
static bool fll_hoco_ready;
static uint64_t fll_elapsed_us;
static void sync_stability_flags(void)
{
    uint8_t flags = (uint8_t) ((!R_SYSTEM->HOCOCR << CGC_CLOCK_HOCO) |
                              (!R_SYSTEM->MOSCCR << CGC_CLOCK_MAIN_OSC) |
                              (!R_SYSTEM->PLLCR << CGC_CLOCK_PLL) |
                              (!R_SYSTEM->PLL2CR << CGC_CLOCK_PLL2));
    *(volatile uint8_t *) (void *) &R_SYSTEM->OSCSF = flags;
    if (R_SYSTEM->HOCOCR != 0U)
    {
        fll_started = false;
        fll_hoco_ready = false;
        fll_elapsed_us = 0U;
    }
    else if ((R_SYSTEM->FLLCR1 != 0U) && !fll_started)
    {
        fll_started = true;
        fll_hoco_ready = (flags & 1U) != 0U;
        fll_elapsed_us = 0U;
    }
}

void cgc_test_wait(uint32_t actual, uint32_t expected, char const * reg)
{
    if (actual != expected)
    {
        fprintf(stderr, "unexpected wait: %s actual=%u expected=%u\n", reg, actual, expected);
        abort();
    }
    sync_stability_flags();
}
void R_BSP_RegisterProtectDisable(uint32_t mask) { (void) mask; ++protection_disable_calls; }
void R_BSP_RegisterProtectEnable(uint32_t mask) { (void) mask; ++protection_enable_calls; }
void R_BSP_FlashCacheDisable(void) { }
void R_BSP_FlashCacheEnable(void) { }
void R_BSP_SoftwareDelay(uint32_t delay, uint32_t units)
{
    assert(delay > 0U);
    assert(units == BSP_DELAY_UNITS_MICROSECONDS);
    if (fll_started)
    {
        assert(fll_hoco_ready && R_SYSTEM->OSCSF_b.HOCOSF);
        assert(R_SYSTEM->FLLCR1 && !R_SYSTEM->HOCOCR);
        fll_elapsed_us += delay;
    }
}
static void fll_settled(void)
{
    if (fll_started)
    {
        assert(fll_hoco_ready); /* Flag readiness alone does not satisfy the next assertion. */
        assert(fll_elapsed_us >= TEST_FLL_MIN_US);
    }
}
void bsp_prv_operating_mode_set(uint8_t mode) { R_SYSTEM->OPCCR_b.OPCM = mode; }
void bsp_prv_prepare_pll(uint32_t clock, uint32_t const * const hz)
{
    assert(clock == CGC_CLOCK_PLL || clock == CGC_CLOCK_PLL2);
    fll_settled();
    memcpy(pll_frequencies[clock - CGC_CLOCK_PLL], hz, sizeof(pll_frequencies[0]));
}
void bsp_prv_clock_set(uint32_t clock, uint32_t sckdivcr, uint16_t sckdivcr2)
{
    fll_settled();
    ++clock_set_calls;
    R_SYSTEM->SCKSCR = (uint8_t) clock;
    R_SYSTEM->SCKDIVCR = sckdivcr;
    R_SYSTEM->SCKDIVCR2 = sckdivcr2;
}
void R_BSP_GroupIrqWrite(bsp_grp_irq_t irq, void (* callback)(bsp_grp_irq_t))
{
    assert(irq == BSP_GRP_IRQ_OSC_STOP_DETECT);
    assert(callback != NULL);
    nmi_callback = callback;
    ++group_registrations;
}
uint32_t R_BSP_SourceClockHzGet(uint32_t clock)
{
    assert(clock == FSP_PRIV_CLOCK_PLL1P);
    return pll_frequencies[0][0];
}
static void callback(cgc_callback_args_t * args)
{
    assert(args->event == CGC_EVENT_OSC_STOP_DETECT_NMI);
    assert(args->p_context == &context);
    if (expected_callback_memory != NULL)
    {
        assert(args == expected_callback_memory);
    }
    ++callback_calls;
}

static void reset_fixture(void)
{
    memset(&cgc_test_system, 0, sizeof(cgc_test_system));
    memset(&cgc_test_icu, 0, sizeof(cgc_test_icu));
    R_SYSTEM->HOCOCR = 1;
    R_SYSTEM->MOSCCR = 1;
    R_SYSTEM->PLLCR = 1;
    R_SYSTEM->PLL2CR = 1;
    R_SYSTEM->SCKSCR = CGC_CLOCK_MOCO;
    /* HM9.2.44–58/64–67: these selectors reset to MOCO=1, not memset's HOCO=0. */
    R_SYSTEM->BCKACR = R_SYSTEM->ESWCKCR = R_SYSTEM->ESWPCKCR = 1U;
#if TEST_TARGET == 1
    R_SYSTEM->USBCKCR = R_SYSTEM->OCTACKCR = R_SYSTEM->CANFDCKCR = 1U;
    R_SYSTEM->USB60CKCR = R_SYSTEM->I3CCKCR = R_SYSTEM->SCICKCR = 1U;
    R_SYSTEM->SPICKCR = R_SYSTEM->ADCCKCR = R_SYSTEM->GPTCKCR = 1U;
    R_SYSTEM->LCDCKCR = R_SYSTEM->ETHPCKCR = 1U;
#endif
    protection_disable_calls = 0;
    protection_enable_calls = 0;
    clock_set_calls = 0;
    group_registrations = 0;
    callback_calls = 0;
    nmi_callback = NULL;
    expected_callback_memory = NULL;
    memset(pll_frequencies, 0, sizeof(pll_frequencies));
    SystemCoreClock = 8000000U;
    sync_stability_flags();
}

static void open_control(cgc_instance_ctrl_t * ctrl)
{
    memset(ctrl, 0, sizeof(*ctrl));
    cgc_cfg_t cfg = {.p_callback = callback, .p_context = &context};
    assert(R_CGC_Open(ctrl, &cfg) == FSP_SUCCESS);
}

static cgc_pll_cfg_t pll_config(void)
{
    cgc_pll_cfg_t cfg = {
        .source_clock = CGC_CLOCK_MAIN_OSC, .divider = CGC_PLL_DIV_2,
        .multiplier = BSP_CLOCKS_PLL_MUL(100, 0),
        .out_div_p = CGC_PLL_OUT_DIV_6, .out_div_q = CGC_PLL_OUT_DIV_8,
        .out_div_r = CGC_PLL_OUT_DIV_9,
    };
    return cfg;
}

static void source_ready(cgc_clock_t source)
{
    if (source == CGC_CLOCK_MAIN_OSC) R_SYSTEM->MOSCCR = 0;
    if (source == CGC_CLOCK_HOCO) R_SYSTEM->HOCOCR = 0;
    sync_stability_flags();
}

static void check_api_and_open_close(void)
{
    assert(g_cgc_on_cgc.open == R_CGC_Open);
    assert(g_cgc_on_cgc.clocksCfg == R_CGC_ClocksCfg);
    assert(g_cgc_on_cgc.clockStart == R_CGC_ClockStart);
    assert(g_cgc_on_cgc.clockStop == R_CGC_ClockStop);
    assert(g_cgc_on_cgc.clockCheck == R_CGC_ClockCheck);
    assert(g_cgc_on_cgc.systemClockSet == R_CGC_SystemClockSet);
    assert(g_cgc_on_cgc.systemClockGet == R_CGC_SystemClockGet);
    assert(g_cgc_on_cgc.oscStopDetectEnable == R_CGC_OscStopDetectEnable);
    assert(g_cgc_on_cgc.oscStopDetectDisable == R_CGC_OscStopDetectDisable);
    assert(g_cgc_on_cgc.oscStopStatusClear == R_CGC_OscStopStatusClear);
    assert(g_cgc_on_cgc.callbackSet == R_CGC_CallbackSet);
    assert(g_cgc_on_cgc.close == R_CGC_Close);
    reset_fixture();
    cgc_instance_ctrl_t ctrl = {0};
    cgc_cfg_t cfg = {.p_callback = callback, .p_context = &context};
#if TEST_CHECKS
    assert(R_CGC_Open(NULL, &cfg) == FSP_ERR_ASSERTION);
    assert(R_CGC_Open(&ctrl, NULL) == FSP_ERR_ASSERTION);
    assert(R_CGC_Close(&ctrl) == FSP_ERR_NOT_OPEN);
#endif
    assert(R_CGC_Open(&ctrl, &cfg) == FSP_SUCCESS);
    assert(ctrl.p_callback == callback);
    assert(ctrl.p_context == &context);
#if TEST_CHECKS
    assert(R_CGC_Open(&ctrl, &cfg) == FSP_ERR_ALREADY_OPEN);
#endif
    assert(R_CGC_Close(&ctrl) == FSP_SUCCESS);
    assert(ctrl.open == 0);
    assert(R_CGC_Open(&ctrl, &cfg) == FSP_SUCCESS);
    assert(R_CGC_Close(&ctrl) == FSP_SUCCESS);
}

static cgc_divider_cfg_t uniform_dividers(unsigned encoding)
{
    cgc_divider_cfg_t cfg = {0};
    cfg.sckdivcr_w = encoding * 0x11111111U;
    cfg.sckdivcr2 = (uint16_t) (encoding * 0x1111U);
    return cfg;
}

static cgc_divider_cfg_t independent_dividers(void)
{
    cgc_divider_cfg_t cfg = {0};
    cfg.sckdivcr_b.pclkd_div = CGC_SYS_CLOCK_DIV_4;
    cfg.sckdivcr_b.pclkc_div = CGC_SYS_CLOCK_DIV_4;
    cfg.sckdivcr_b.pclkb_div = CGC_SYS_CLOCK_DIV_16;
    cfg.sckdivcr_b.pclka_div = CGC_SYS_CLOCK_DIV_8;
    cfg.sckdivcr_b.bclk_div = CGC_SYS_CLOCK_DIV_8;
    cfg.sckdivcr_b.pclke_div = CGC_SYS_CLOCK_DIV_4;
    cfg.sckdivcr_b.iclk_div = CGC_SYS_CLOCK_DIV_4;
    cfg.sckdivcr_b.mrpclk_div = CGC_SYS_CLOCK_DIV_8;
    cfg.sckdivcr2_b.cpuclk_div = CGC_SYS_CLOCK_DIV_1;
    cfg.sckdivcr2_b.cpuclk1_div = CGC_SYS_CLOCK_DIV_4;
    cfg.sckdivcr2_b.npuclk_div = CGC_SYS_CLOCK_DIV_2;
    cfg.sckdivcr2_b.mriclk_div = CGC_SYS_CLOCK_DIV_4;
    return cfg;
}

static void check_system_dividers(void)
{
    static const unsigned legal[] = {0,1,2,3,4,5,6,8,9,10,11};
    for (unsigned i = 0; i < sizeof(legal) / sizeof(legal[0]); ++i)
    {
        reset_fixture();
        cgc_instance_ctrl_t ctrl;
        open_control(&ctrl);
        cgc_divider_cfg_t cfg = uniform_dividers(legal[i]);
        assert(R_CGC_SystemClockSet(&ctrl, CGC_CLOCK_MOCO, &cfg) == FSP_SUCCESS);
        assert(R_SYSTEM->SCKDIVCR == cfg.sckdivcr_w);
        assert(R_SYSTEM->SCKDIVCR2 == cfg.sckdivcr2);
        cgc_clock_t source;
        cgc_divider_cfg_t actual = {0};
        assert(R_CGC_SystemClockGet(&ctrl, &source, &actual) == FSP_SUCCESS);
        assert(source == CGC_CLOCK_MOCO);
        assert(actual.sckdivcr_w == cfg.sckdivcr_w);
        assert(actual.sckdivcr2 == cfg.sckdivcr2);
        assert(clock_set_calls == 1);
        assert(protection_disable_calls == protection_enable_calls);
    }
    reset_fixture();
    cgc_instance_ctrl_t ctrl;
    open_control(&ctrl);
    cgc_divider_cfg_t cfg = independent_dividers();
    assert(R_CGC_SystemClockSet(&ctrl, CGC_CLOCK_MOCO, &cfg) == FSP_SUCCESS);
    assert(R_SYSTEM->SCKDIVCR2_b.CPUCK0 == 0);
    assert(R_SYSTEM->SCKDIVCR2_b.CPUCK1 == 2);
    assert(R_SYSTEM->SCKDIVCR2_b.NPUCK == 1);
    assert(R_SYSTEM->SCKDIVCR2_b.MRICK == 2);
    assert(R_CGC_SystemClockGet(&ctrl, NULL, NULL) == FSP_SUCCESS);
#if TEST_CHECKS
    static const unsigned prohibited[] = {7,12,13,14,15};
    for (unsigned field = 0; field < 12; ++field)
    {
        for (unsigned i = 0; i < sizeof(prohibited) / sizeof(prohibited[0]); ++i)
        {
            cfg = uniform_dividers(0);
            if (field < 8) cfg.sckdivcr_w = prohibited[i] << (field * 4);
            else cfg.sckdivcr2 = (uint16_t) (prohibited[i] << ((field - 8) * 4));
            assert(R_CGC_SystemClockSet(&ctrl, CGC_CLOCK_MOCO, &cfg) == FSP_ERR_ASSERTION);
        }
        cfg = uniform_dividers(1);
        if (field < 8) cfg.sckdivcr_w = (cfg.sckdivcr_w & ~(15U << (field * 4))) | (8U << (field * 4));
        else cfg.sckdivcr2 = (uint16_t) ((cfg.sckdivcr2 & ~(15U << ((field - 8) * 4))) | (8U << ((field - 8) * 4)));
        assert(R_CGC_SystemClockSet(&ctrl, CGC_CLOCK_MOCO, &cfg) == FSP_ERR_ASSERTION);
    }
    /* Independently violate each domain relationship without mixing families. */
    for (unsigned field = 8; field < 12; ++field)
    {
        cfg = independent_dividers();
        cfg.sckdivcr2 = (uint16_t) ((cfg.sckdivcr2 & ~(15U << ((field - 8) * 4))) | (3U << ((field - 8) * 4)));
        assert(R_CGC_SystemClockSet(&ctrl, CGC_CLOCK_MOCO, &cfg) == FSP_ERR_ASSERTION);
    }
    cfg = uniform_dividers(8);
    cfg.sckdivcr_b.iclk_div = CGC_SYS_CLOCK_DIV_1;
    cfg.sckdivcr2 = 0;
    assert(R_CGC_SystemClockSet(&ctrl, CGC_CLOCK_MOCO, &cfg) == FSP_SUCCESS);
    cfg.sckdivcr2_b.cpuclk1_div = CGC_SYS_CLOCK_DIV_3;
    assert(R_CGC_SystemClockSet(&ctrl, CGC_CLOCK_MOCO, &cfg) == FSP_ERR_ASSERTION);
    assert(R_CGC_SystemClockSet(&ctrl, CGC_CLOCK_PLL2, &cfg) == FSP_ERR_ASSERTION);
    assert(R_CGC_SystemClockSet(&ctrl, (cgc_clock_t) -1, &cfg) == FSP_ERR_ASSERTION);
#endif
}

static uint32_t divided_vco(uint64_t vco, cgc_pll_out_div_t division)
{
    return (uint32_t) (division == CGC_PLL_OUT_DIV_1_5 ? vco * 2 / 3 : vco / division);
}

static void check_pll_options(void)
{
    static const cgc_pll_out_div_t p_options[] = {2,3,4,6,8,16};
    static const cgc_pll_out_div_t qr_options[] = {2,3,4,5,6,8,9,10};
    for (unsigned unit = 0; unit < 2; ++unit)
    {
        cgc_clock_t clock = (cgc_clock_t) (CGC_CLOCK_PLL + unit);
        for (unsigned p = 0; p < sizeof(p_options) / sizeof(p_options[0]); ++p)
        {
            for (unsigned q = 0; q < sizeof(qr_options) / sizeof(qr_options[0]); ++q)
            {
                for (unsigned r = 0; r < sizeof(qr_options) / sizeof(qr_options[0]); ++r)
                {
                    reset_fixture();
                    cgc_instance_ctrl_t ctrl;
                    open_control(&ctrl);
                    source_ready(CGC_CLOCK_MAIN_OSC);
                    cgc_pll_cfg_t cfg = pll_config();
                    cfg.out_div_p = p_options[p];
                    cfg.out_div_q = qr_options[q];
                    cfg.out_div_r = qr_options[r];
                    assert(R_CGC_ClockStart(&ctrl, clock, &cfg) == FSP_SUCCESS);
                    uint32_t control = unit ? R_SYSTEM->PLL2CCR : R_SYSTEM->PLLCCR;
                    uint16_t outputs = unit ? R_SYSTEM->PLL2CCR2 : R_SYSTEM->PLLCCR2;
                    assert(control == ((99U << 8) | 1U));
                    assert(outputs == (uint16_t) ((cfg.out_div_p - 1) | ((cfg.out_div_q - 1) << 4) | ((cfg.out_div_r - 1) << 8)));
                    assert(pll_frequencies[unit][0] == divided_vco(1200000000ULL, cfg.out_div_p));
                    assert(pll_frequencies[unit][1] == divided_vco(1200000000ULL, cfg.out_div_q));
                    assert(pll_frequencies[unit][2] == divided_vco(1200000000ULL, cfg.out_div_r));
                    assert(protection_disable_calls == protection_enable_calls);
                }
            }
        }
        static const unsigned fractions[] = {0,33,50,66};
        for (unsigned f = 0; f < 4; ++f)
        {
            reset_fixture();
            cgc_instance_ctrl_t ctrl;
            open_control(&ctrl);
            source_ready(CGC_CLOCK_MAIN_OSC);
            cgc_pll_cfg_t cfg = pll_config();
            cfg.multiplier = BSP_CLOCKS_PLL_MUL(80, fractions[f]);
            assert(R_CGC_ClockStart(&ctrl, clock, &cfg) == FSP_SUCCESS);
            uint64_t vco = 960000000ULL + (f == 0 ? 0 : f == 1 ? 4000000 : f == 2 ? 6000000 : 8000000);
            assert(pll_frequencies[unit][0] == vco / 6);
            assert(pll_frequencies[unit][1] == vco / 8);
            assert(pll_frequencies[unit][2] == vco / 9);
        }
        reset_fixture();
        cgc_instance_ctrl_t ctrl;
        open_control(&ctrl);
        source_ready(CGC_CLOCK_MAIN_OSC);
        cgc_pll_cfg_t cfg = pll_config();
        cfg.divider = CGC_PLL_DIV_3;
        cfg.multiplier = CGC_PLL_MUL_300_0;
        /* PLL1P is limited to 1 GHz; PLL2P permits 1.2 GHz (HM70.3 clock limits). */
        cfg.out_div_p = unit ? CGC_PLL_OUT_DIV_2 : CGC_PLL_OUT_DIV_3;
        cfg.out_div_q = CGC_PLL_OUT_DIV_2;
        cfg.out_div_r = CGC_PLL_OUT_DIV_2;
        assert(R_CGC_ClockStart(&ctrl, clock, &cfg) == FSP_SUCCESS);
        assert((unit ? R_SYSTEM->PLL2CCR : R_SYSTEM->PLLCCR) == 0x12B02U);
        assert(pll_frequencies[unit][0] == (unit ? 1200000000U : 800000000U));
        assert(R_CGC_ClockStart(&ctrl, clock, &cfg) == FSP_SUCCESS);
        cfg.out_div_q = CGC_PLL_OUT_DIV_3;
        assert(R_CGC_ClockStart(&ctrl, clock, &cfg) == FSP_ERR_CLOCK_ACTIVE);
        cfg = pll_config();
        assert(R_CGC_ClockStart(&ctrl, clock, &cfg) == FSP_ERR_CLOCK_ACTIVE);
    }
}

static cgc_clocks_cfg_t clocks_config(void)
{
    cgc_clocks_cfg_t cfg = {
        .system_clock = CGC_CLOCK_MOCO,
        .pll_cfg = pll_config(), .pll2_cfg = pll_config(),
        .divider_cfg = independent_dividers(),
        .loco_state = CGC_CLOCK_CHANGE_NONE, .moco_state = CGC_CLOCK_CHANGE_NONE,
        .hoco_state = CGC_CLOCK_CHANGE_NONE, .mainosc_state = CGC_CLOCK_CHANGE_NONE,
        .pll_state = CGC_CLOCK_CHANGE_NONE, .pll2_state = CGC_CLOCK_CHANGE_NONE,
        .subosc_state = CGC_CLOCK_CHANGE_NONE,
    };
    return cfg;
}

static void check_clocks_configuration(void)
{
    reset_fixture();
    cgc_instance_ctrl_t ctrl;
    open_control(&ctrl);
    cgc_clocks_cfg_t cfg = clocks_config();
    cfg.mainosc_state = CGC_CLOCK_CHANGE_START;
    cfg.pll_state = CGC_CLOCK_CHANGE_START;
    cfg.pll2_state = CGC_CLOCK_CHANGE_START;
    cfg.system_clock = CGC_CLOCK_PLL;
    assert(R_CGC_ClocksCfg(&ctrl, &cfg) == FSP_SUCCESS);
    assert(R_SYSTEM->SCKSCR == CGC_CLOCK_PLL);
    assert(R_SYSTEM->SCKDIVCR2 == cfg.divider_cfg.sckdivcr2);
    assert(R_SYSTEM->PLLCR == 0 && R_SYSTEM->PLL2CR == 0);
    assert(pll_frequencies[0][0] == 200000000U);
    assert(pll_frequencies[1][0] == 200000000U);
    assert(R_CGC_ClockCheck(&ctrl, CGC_CLOCK_PLL) == FSP_SUCCESS);
#if TEST_CHECKS
    assert(R_CGC_ClockStop(&ctrl, CGC_CLOCK_PLL) == FSP_ERR_IN_USE);
    assert(R_CGC_ClockStop(&ctrl, CGC_CLOCK_MAIN_OSC) == FSP_ERR_IN_USE);
#endif
    cfg = clocks_config();
    cfg.mainosc_state = CGC_CLOCK_CHANGE_STOP;
    cfg.pll_state = CGC_CLOCK_CHANGE_STOP;
    cfg.pll2_state = CGC_CLOCK_CHANGE_STOP;
    assert(R_CGC_ClocksCfg(&ctrl, &cfg) == FSP_SUCCESS);
    assert(R_SYSTEM->PLLCR == 1 && R_SYSTEM->PLL2CR == 1 && R_SYSTEM->MOSCCR == 1);
    assert(R_SYSTEM->SCKSCR == CGC_CLOCK_MOCO);
    assert(R_CGC_ClockCheck(&ctrl, CGC_CLOCK_PLL) == FSP_ERR_CLOCK_INACTIVE);
    assert(protection_disable_calls == protection_enable_calls);
#if TEST_CHECKS
    cfg = clocks_config();
    cfg.system_clock = CGC_CLOCK_PLL2;
    assert(R_CGC_ClocksCfg(&ctrl, &cfg) == FSP_ERR_ASSERTION);
    cfg = clocks_config();
    cfg.hoco_state = (cgc_clock_change_t) 3;
    assert(R_CGC_ClocksCfg(&ctrl, &cfg) == FSP_ERR_ASSERTION);
    cfg = clocks_config();
    cfg.pll_state = CGC_CLOCK_CHANGE_START;
    cfg.mainosc_state = CGC_CLOCK_CHANGE_START;
    cfg.pll_cfg.out_div_p = 0;
    assert(R_CGC_ClocksCfg(&ctrl, &cfg) == FSP_ERR_ASSERTION);
#endif
}

typedef struct st_consumer_snapshot
{
    unsigned char system[sizeof(cgc_test_system)];
    unsigned char icu[sizeof(cgc_test_icu)];
    uint32_t frequencies[2][3];
    unsigned protection_disable;
    unsigned protection_enable;
    unsigned clock_sets;
} consumer_snapshot_t;

static consumer_snapshot_t consumer_snapshot(void)
{
    consumer_snapshot_t snapshot;
    memcpy(snapshot.system, &cgc_test_system, sizeof(snapshot.system));
    memcpy(snapshot.icu, &cgc_test_icu, sizeof(snapshot.icu));
    memcpy(snapshot.frequencies, pll_frequencies, sizeof(pll_frequencies));
    snapshot.protection_disable = protection_disable_calls;
    snapshot.protection_enable = protection_enable_calls;
    snapshot.clock_sets = clock_set_calls;
    return snapshot;
}

static void consumer_unchanged(consumer_snapshot_t const * snapshot)
{
    assert(memcmp(snapshot->system, &cgc_test_system, sizeof(snapshot->system)) == 0);
    assert(memcmp(snapshot->icu, &cgc_test_icu, sizeof(snapshot->icu)) == 0);
    assert(memcmp(snapshot->frequencies, pll_frequencies, sizeof(pll_frequencies)) == 0);
    assert(protection_disable_calls == snapshot->protection_disable);
    assert(protection_enable_calls == snapshot->protection_enable);
    assert(clock_set_calls == snapshot->clock_sets);
}

static void check_peripheral_consumers(void)
{
    static const unsigned sources[] = {5, 6, 7, 8, 9, 10};
    unsigned cases = 0;
    for (unsigned domain = 0; domain < 3; domain++)
    {
        bool enabled = domain == 0 ? BSP_FEATURE_BSP_HAS_BCLKA_CLOCK : BSP_FEATURE_BSP_HAS_ESW_CLOCK;
        for (unsigned output = 0; output < sizeof(sources) / sizeof(sources[0]); output++)
        {
            unsigned source = sources[output];
            cgc_clock_t clock = (source == 5 || source == 7 || source == 8) ? CGC_CLOCK_PLL : CGC_CLOCK_PLL2;
            for (unsigned flags = 0; flags <= 0xC0U; flags += 0x40U)
            {
                for (unsigned stopped = 0; stopped < 2; stopped++)
                {
                    reset_fixture();
                    cgc_instance_ctrl_t ctrl;
                    open_control(&ctrl);
                    source_ready(CGC_CLOCK_MAIN_OSC);
                    source_ready(CGC_CLOCK_HOCO);
                    cgc_pll_cfg_t cfg = pll_config();
                    assert(R_CGC_ClockStart(&ctrl, clock, &cfg) == FSP_SUCCESS);
                    R_SYSTEM->BCKACR = R_SYSTEM->ESWCKCR = R_SYSTEM->ESWPCKCR = 1U;
                    volatile uint8_t * selection = domain == 0 ? &R_SYSTEM->BCKACR :
                                                   domain == 1 ? &R_SYSTEM->ESWCKCR : &R_SYSTEM->ESWPCKCR;
                    *selection = (uint8_t) (source | flags);
                    if (stopped)
                    {
                        if (clock == CGC_CLOCK_PLL) R_SYSTEM->PLLCR = 1;
                        else R_SYSTEM->PLL2CR = 1;
                        sync_stability_flags();
                    }
                    if (!enabled)
                    {
                        /* A capability-off domain must not acquire ownership by its selector's value. */
                        assert(R_CGC_ClockStop(&ctrl, clock) == FSP_SUCCESS);
                        cfg.out_div_p = CGC_PLL_OUT_DIV_3;
                        assert(R_CGC_ClockStart(&ctrl, clock, &cfg) == FSP_SUCCESS);
                        cases++;
                        continue;
                    }
                    consumer_snapshot_t before = consumer_snapshot();
                    assert(R_CGC_ClockStop(&ctrl, clock) == FSP_ERR_IN_USE);
                    consumer_unchanged(&before);

                    /* A late prohibited stop must prevent an earlier, otherwise valid PLL start as well. */
                    cgc_clocks_cfg_t all = clocks_config();
                    all.mainosc_state = CGC_CLOCK_CHANGE_START;
                    all.pll_state = clock == CGC_CLOCK_PLL ? CGC_CLOCK_CHANGE_STOP : CGC_CLOCK_CHANGE_START;
                    all.pll2_state = clock == CGC_CLOCK_PLL2 ? CGC_CLOCK_CHANGE_STOP : CGC_CLOCK_CHANGE_START;
                    assert(R_CGC_ClocksCfg(&ctrl, &all) == FSP_ERR_IN_USE);
                    consumer_unchanged(&before);

                    for (unsigned setting = 0; setting < 6; setting++)
                    {
                        cgc_pll_cfg_t change = cfg;
                        switch (setting)
                        {
                            case 0: change.divider = CGC_PLL_DIV_3; break;
                            case 1: change.multiplier = BSP_CLOCKS_PLL_MUL(80, 0); break;
                            case 2: change.source_clock = CGC_CLOCK_HOCO; break;
                            case 3: change.out_div_p = CGC_PLL_OUT_DIV_3; break;
                            case 4: change.out_div_q = CGC_PLL_OUT_DIV_6; break;
                            case 5: change.out_div_r = CGC_PLL_OUT_DIV_8; break;
                        }
                        assert(R_CGC_ClockStart(&ctrl, clock, &change) == FSP_ERR_IN_USE);
                        consumer_unchanged(&before);
                        all = clocks_config();
                        if (clock == CGC_CLOCK_PLL)
                        {
                            all.pll_state = CGC_CLOCK_CHANGE_START;
                            all.pll_cfg = change;
                        }
                        else
                        {
                            all.pll_state = CGC_CLOCK_CHANGE_START;
                            all.pll2_state = CGC_CLOCK_CHANGE_START;
                            all.pll2_cfg = change;
                        }
                        assert(R_CGC_ClocksCfg(&ctrl, &all) == FSP_ERR_IN_USE);
                        consumer_unchanged(&before);
                    }
                    if (stopped)
                    {
                        assert(R_CGC_ClockStart(&ctrl, clock, &cfg) == FSP_ERR_IN_USE);
                        consumer_unchanged(&before);
                    }
                    else
                    {
                        /* The upstream oscillator is also globally owned, even with parameter checking off. */
                        assert(R_CGC_ClockStop(&ctrl, CGC_CLOCK_MAIN_OSC) == FSP_ERR_IN_USE);
                        consumer_unchanged(&before);
                        all = clocks_config();
                        all.mainosc_state = CGC_CLOCK_CHANGE_STOP;
                        assert(R_CGC_ClocksCfg(&ctrl, &all) == FSP_ERR_IN_USE);
                        consumer_unchanged(&before);
                        assert(R_CGC_ClockStart(&ctrl, clock, &cfg) == FSP_SUCCESS);
                        assert((clock == CGC_CLOCK_PLL ? R_SYSTEM->PLLCCR : R_SYSTEM->PLL2CCR) ==
                               ((99U << 8) | 1U));
                        assert(*selection == (uint8_t) (source | flags));
                    }
                    /* Detach only this consumer; neither a module stop nor BCKCR selection is a release. */
                    *selection = 1U;
                    assert(R_CGC_ClockStop(&ctrl, clock) == FSP_SUCCESS);
                    cfg.out_div_p = CGC_PLL_OUT_DIV_3;
                    assert(R_CGC_ClockStart(&ctrl, clock, &cfg) == FSP_SUCCESS);
                    cases++;
                }
            }
        }
    }
    assert(cases == 144);

#if BSP_FEATURE_BSP_HAS_BCLKA_CLOCK && BSP_FEATURE_BSP_HAS_ESW_CLOCK
    reset_fixture();
    cgc_instance_ctrl_t ctrl;
    open_control(&ctrl);
    source_ready(CGC_CLOCK_MAIN_OSC);
    source_ready(CGC_CLOCK_HOCO);
    cgc_pll_cfg_t cfg = pll_config();
    cfg.source_clock = CGC_CLOCK_HOCO;
    cfg.multiplier = BSP_CLOCKS_PLL_MUL(50, 0);
    assert(R_CGC_ClockStart(&ctrl, CGC_CLOCK_PLL, &cfg) == FSP_SUCCESS);
    assert(R_CGC_ClockStart(&ctrl, CGC_CLOCK_PLL2, &cfg) == FSP_SUCCESS);
    R_SYSTEM->BCKACR = 7;
    R_SYSTEM->ESWCKCR = 10;
    R_SYSTEM->ESWPCKCR = 8;
    consumer_snapshot_t before = consumer_snapshot();
    assert(R_CGC_ClockStop(&ctrl, CGC_CLOCK_PLL) == FSP_ERR_IN_USE);
    assert(R_CGC_ClockStop(&ctrl, CGC_CLOCK_PLL2) == FSP_ERR_IN_USE);
    assert(R_CGC_ClockStop(&ctrl, CGC_CLOCK_HOCO) == FSP_ERR_IN_USE);
    consumer_unchanged(&before);
    /* Releasing one of two consumers is insufficient, but a different unconsumed PLL remains controllable. */
    R_SYSTEM->BCKACR = 1;
    before = consumer_snapshot();
    assert(R_CGC_ClockStop(&ctrl, CGC_CLOCK_PLL) == FSP_ERR_IN_USE);
    consumer_unchanged(&before);
    R_SYSTEM->ESWCKCR = 1;
    assert(R_CGC_ClockStop(&ctrl, CGC_CLOCK_PLL2) == FSP_SUCCESS);
#endif
    puts("runtime peripheral-consumer protection passed: 144 cases");
}

static void check_nmi_and_callback(void)
{
    reset_fixture();
    cgc_instance_ctrl_t ctrl;
    open_control(&ctrl);
    source_ready(CGC_CLOCK_MAIN_OSC);
#if TEST_TARGET == 1 && TEST_CORE == 1
    /* HM14.2.14: shared oscillation-stop control/NMI enable belongs to primary CPU0. */
    assert(R_CGC_OscStopDetectEnable(&ctrl) == FSP_ERR_UNSUPPORTED);
    assert(group_registrations == 0U && R_ICU->NMIER == 0U && R_SYSTEM->OSTDCR == 0U);
    return;
#endif
    assert(R_CGC_OscStopDetectEnable(&ctrl) == FSP_SUCCESS);
    assert(group_registrations == 1);
    assert(R_ICU->NMIER == R_ICU_NMIER_OSTEN_Msk);
    assert(R_SYSTEM->OSTDCR == 0x81);
    assert(nmi_callback != NULL);
    nmi_callback(BSP_GRP_IRQ_OSC_STOP_DETECT);
    assert(callback_calls == 1);
    cgc_callback_args_t memory = {.event = CGC_EVENT_OSC_STOP_DETECT_SUBCLOCK, .p_context = NULL};
    expected_callback_memory = &memory;
    assert(R_CGC_CallbackSet(&ctrl, callback, &context, &memory) == FSP_SUCCESS);
    nmi_callback(BSP_GRP_IRQ_OSC_STOP_DETECT);
    assert(callback_calls == 2);
    assert(memory.event == CGC_EVENT_OSC_STOP_DETECT_SUBCLOCK);
    assert(memory.p_context == NULL);
    source_ready(CGC_CLOCK_MAIN_OSC);
    R_SYSTEM->OSTDSR = 1;
#if TEST_CHECKS
    assert(R_CGC_OscStopDetectDisable(&ctrl) == FSP_ERR_OSC_STOP_DETECTED);
#endif
    assert(R_CGC_OscStopStatusClear(&ctrl) == FSP_SUCCESS);
    assert(R_SYSTEM->OSTDSR == 0);
    assert(R_SYSTEM->OSTDCR == 0);
    assert(R_CGC_OscStopDetectDisable(&ctrl) == FSP_SUCCESS);
    assert(protection_disable_calls == protection_enable_calls);
}

static void check_sources_and_frequency_limit(void)
{
    static const cgc_clock_t sources[] = {
        CGC_CLOCK_HOCO, CGC_CLOCK_LOCO, CGC_CLOCK_SUBCLOCK, CGC_CLOCK_MAIN_OSC,
    };
    for (unsigned i = 0; i < sizeof(sources) / sizeof(sources[0]); ++i)
    {
        reset_fixture();
        cgc_instance_ctrl_t ctrl;
        open_control(&ctrl);
        assert(R_CGC_ClockStart(&ctrl, sources[i], NULL) == FSP_SUCCESS);
        assert(R_CGC_ClockCheck(&ctrl, sources[i]) == FSP_SUCCESS);
#if TEST_FLL
        if (sources[i] == CGC_CLOCK_HOCO)
        {
            assert(R_SYSTEM->FLLCR1 == 1);
            assert(fll_started && fll_hoco_ready);
            fll_settled();
            assert(fll_elapsed_us >= TEST_FLL_MIN_US);
        }
#endif
        assert(R_CGC_ClockStop(&ctrl, sources[i]) == FSP_SUCCESS);
        assert(R_CGC_ClockCheck(&ctrl, sources[i]) == FSP_ERR_CLOCK_INACTIVE);
        assert(R_SYSTEM->FLLCR1 == 0);
        assert(protection_disable_calls == protection_enable_calls);
    }
    for (unsigned input = CGC_PLL_DIV_1; input <= CGC_PLL_DIV_3; ++input)
    {
        reset_fixture();
        cgc_instance_ctrl_t ctrl;
        open_control(&ctrl);
        source_ready(CGC_CLOCK_MAIN_OSC);
        cgc_pll_cfg_t cfg = pll_config();
        cfg.divider = (cgc_pll_div_t) input;
        cfg.multiplier = BSP_CLOCKS_PLL_MUL(50U * (input + 1U), 0);
        assert(R_CGC_ClockStart(&ctrl, CGC_CLOCK_PLL, &cfg) == FSP_SUCCESS);
        assert(pll_frequencies[0][0] == 200000000U);
    }
    for (unsigned input = CGC_PLL_DIV_2; input <= CGC_PLL_DIV_3; ++input)
    {
        reset_fixture();
        cgc_instance_ctrl_t ctrl;
        open_control(&ctrl);
        assert(R_CGC_ClockStart(&ctrl, CGC_CLOCK_HOCO, NULL) == FSP_SUCCESS);
        cgc_pll_cfg_t cfg = pll_config();
        cfg.source_clock = CGC_CLOCK_HOCO;
        cfg.divider = (cgc_pll_div_t) input;
        cfg.multiplier = BSP_CLOCKS_PLL_MUL(25U * (input + 1U), 0);
        assert(R_CGC_ClockStart(&ctrl, CGC_CLOCK_PLL, &cfg) == FSP_SUCCESS);
        assert(R_SYSTEM->PLLCCR_b.PLSRCSEL == 1);
        assert(pll_frequencies[0][0] == 200000000U);
    }
    reset_fixture();
    cgc_instance_ctrl_t ctrl;
    open_control(&ctrl);
    cgc_divider_cfg_t dividers = independent_dividers();
    source_ready(CGC_CLOCK_HOCO);
    R_SYSTEM->PLLCR = 0;
    R_SYSTEM->PLLCCR_b.PLSRCSEL = 1;
    sync_stability_flags();
    pll_frequencies[0][0] = 1000000000U;
#if TEST_CHECKS
    /* The limit applies to physical CPU0 even when CPU1 executes this API. */
    assert(R_CGC_SystemClockSet(&ctrl, CGC_CLOCK_PLL, &dividers) == FSP_ERR_ASSERTION);
#endif
    dividers.sckdivcr2_b.cpuclk_div = CGC_SYS_CLOCK_DIV_2;
    assert(R_CGC_SystemClockSet(&ctrl, CGC_CLOCK_PLL, &dividers) == FSP_SUCCESS);
    assert(protection_disable_calls == protection_enable_calls);
}

static void check_invalid_inputs(void)
{
#if TEST_CHECKS
    reset_fixture();
    cgc_instance_ctrl_t ctrl;
    open_control(&ctrl);
    cgc_pll_cfg_t cfg = pll_config();
    source_ready(CGC_CLOCK_MAIN_OSC);
    static const unsigned invalid_p[] = {0,1,5,7,9,10,15,17,255};
    static const unsigned invalid_qr[] = {0,1,7,11,16,255};
    for (unsigned i = 0; i < sizeof(invalid_p) / sizeof(invalid_p[0]); ++i)
    {
        cfg = pll_config();
        cfg.out_div_p = (cgc_pll_out_div_t) invalid_p[i];
        assert(R_CGC_ClockStart(&ctrl, CGC_CLOCK_PLL, &cfg) == FSP_ERR_ASSERTION);
    }
    for (unsigned i = 0; i < sizeof(invalid_qr) / sizeof(invalid_qr[0]); ++i)
    {
        cfg = pll_config();
        cfg.out_div_q = (cgc_pll_out_div_t) invalid_qr[i];
        assert(R_CGC_ClockStart(&ctrl, CGC_CLOCK_PLL, &cfg) == FSP_ERR_ASSERTION);
        cfg = pll_config();
        cfg.out_div_r = (cgc_pll_out_div_t) invalid_qr[i];
        assert(R_CGC_ClockStart(&ctrl, CGC_CLOCK_PLL, &cfg) == FSP_ERR_ASSERTION);
    }
    cfg = pll_config();
    cfg.divider = CGC_PLL_DIV_4;
    assert(R_CGC_ClockStart(&ctrl, CGC_CLOCK_PLL, &cfg) == FSP_ERR_ASSERTION);
    cfg = pll_config();
    cfg.source_clock = CGC_CLOCK_MOCO;
    assert(R_CGC_ClockStart(&ctrl, CGC_CLOCK_PLL, &cfg) == FSP_ERR_ASSERTION);
    cfg = pll_config();
    cfg.multiplier = BSP_CLOCKS_PLL_MUL(39, 66);
    assert(R_CGC_ClockStart(&ctrl, CGC_CLOCK_PLL, &cfg) == FSP_ERR_ASSERTION);
    cfg.multiplier = BSP_CLOCKS_PLL_MUL(301, 0);
    assert(R_CGC_ClockStart(&ctrl, CGC_CLOCK_PLL, &cfg) == FSP_ERR_ASSERTION);
    cfg = pll_config();
    cfg.multiplier = CGC_PLL_MUL_40_0;
    assert(R_CGC_ClockStart(&ctrl, CGC_CLOCK_PLL, &cfg) == FSP_ERR_ASSERTION);
    cfg = pll_config();
    cfg.source_clock = CGC_CLOCK_HOCO;
    cfg.divider = CGC_PLL_DIV_1;
    source_ready(CGC_CLOCK_HOCO);
    assert(R_CGC_ClockStart(&ctrl, CGC_CLOCK_PLL, &cfg) == FSP_ERR_ASSERTION);
    assert(R_CGC_ClockStart(&ctrl, (cgc_clock_t) 7, NULL) == FSP_ERR_ASSERTION);
    assert(R_CGC_ClockStop(&ctrl, (cgc_clock_t) -1) == FSP_ERR_ASSERTION);
    assert(R_CGC_ClockCheck(&ctrl, (cgc_clock_t) 7) == FSP_ERR_ASSERTION);
    assert(R_CGC_ClockStart(&ctrl, CGC_CLOCK_PLL, NULL) == FSP_ERR_ASSERTION);
    assert(R_CGC_ClocksCfg(&ctrl, NULL) == FSP_ERR_ASSERTION);
    assert(R_CGC_SystemClockSet(&ctrl, CGC_CLOCK_MOCO, NULL) == FSP_ERR_ASSERTION);
    assert(R_CGC_CallbackSet(&ctrl, NULL, NULL, NULL) == FSP_ERR_ASSERTION);
    assert(R_CGC_Close(&ctrl) == FSP_SUCCESS);
    cgc_divider_cfg_t dividers = uniform_dividers(0);
    assert(R_CGC_ClockStart(&ctrl, CGC_CLOCK_HOCO, NULL) == FSP_ERR_NOT_OPEN);
    assert(R_CGC_ClockStop(&ctrl, CGC_CLOCK_HOCO) == FSP_ERR_NOT_OPEN);
    assert(R_CGC_ClockCheck(&ctrl, CGC_CLOCK_HOCO) == FSP_ERR_NOT_OPEN);
    assert(R_CGC_SystemClockSet(&ctrl, CGC_CLOCK_MOCO, &dividers) == FSP_ERR_NOT_OPEN);
    assert(R_CGC_SystemClockGet(&ctrl, NULL, NULL) == FSP_ERR_NOT_OPEN);
    assert(R_CGC_OscStopDetectEnable(&ctrl) == FSP_ERR_NOT_OPEN);
    assert(R_CGC_OscStopDetectDisable(&ctrl) == FSP_ERR_NOT_OPEN);
    assert(R_CGC_OscStopStatusClear(&ctrl) == FSP_ERR_NOT_OPEN);
#endif
}

int main(void)
{
    check_api_and_open_close();
    check_system_dividers();
    check_pll_options();
    check_clocks_configuration();
    check_peripheral_consumers();
    check_nmi_and_callback();
    check_sources_and_frequency_limit();
    check_invalid_inputs();
    puts("production CGC behavior passed");
    return 0;
}
