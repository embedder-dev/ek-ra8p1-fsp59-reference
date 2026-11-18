/* Independent requirements: RA8P1 HM Rev.1.30 §§9.2.4/6/9/15/19,
 * §§9.2.44-59/64-67, §§9.5.3/9.6.3, §14.2.14 and Tables70.49/70.50.
 * The real driver, device header, feature data and public cgc_api_t are compiled.
 * Hooks emulate elapsed stabilization, not the driver's transition algorithm. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "r_cgc.h"

R_SYSTEM_Type cgc_test_system;
R_ICU_Type cgc_test_icu;
uint32_t SystemCoreClock = 8000000U;
static uint32_t frequencies[2][3];
static unsigned writes, switches, callbacks, delays, delayed_us;
static unsigned test_case;
static bool enforce_references, enforce_fll_stop, enforce_busy;
static unsigned reference_waits, busy_waits;

static void set_flags(uint8_t flags)
{
    *(volatile uint8_t *) (void *) &R_SYSTEM->OSCSF = flags;
}
static void stable(void)
{
    set_flags((uint8_t) ((!R_SYSTEM->HOCOCR << 0) | (!R_SYSTEM->MOSCCR << 3) |
                        (!R_SYSTEM->PLLCR << 5) | (!R_SYSTEM->PLL2CR << 6)));
}
void review_wait_before(char const * reg)
{
    if (strstr(reg, "SYRACCR"))
    {
        if (enforce_busy && busy_waits == 0) assert(R_SYSTEM->LOCOCR == 0);
        ++busy_waits;
        *(volatile uint8_t *) (void *) &R_SYSTEM->SYRACCR = 0;
    }
    if (strstr(reg, "gp_cgc_clock_stp_registers"))
    {
        if (enforce_references)
        {
            /* The dependent oscillators have not settled until the driver polls them. */
            if (R_SYSTEM->MOCOCR) assert((R_SYSTEM->OSCSF & 0x69U) == 0x69U);
            if (R_SYSTEM->LOCOCR) assert((R_SYSTEM->OSCSF & 8U) != 0);
        }
        if (enforce_fll_stop && R_SYSTEM->HOCOCR) assert(R_SYSTEM->FLLCR1 == 1);
    }
    if (strstr(reg, "r_cgc_clock_check") || strstr(reg, "OSCSF"))
    {
        ++reference_waits;
        stable();
    }
}
void cgc_test_wait(uint32_t actual, uint32_t expected, char const * reg)
{
    if (actual != expected)
    {
        fprintf(stderr, "case%u wait %s: %u != %u\n", test_case, reg, actual, expected);
        abort();
    }
    if (!enforce_references) stable();
}
void R_BSP_RegisterProtectDisable(uint32_t mask) { (void) mask; ++writes; }
void R_BSP_RegisterProtectEnable(uint32_t mask) { (void) mask; }
void R_BSP_FlashCacheDisable(void) { }
void R_BSP_FlashCacheEnable(void) { }
void R_BSP_SoftwareDelay(uint32_t us, uint32_t units)
{
    assert(units == BSP_DELAY_UNITS_MICROSECONDS);
    assert(us != 0);
    ++delays;
    delayed_us += us;
}
void bsp_prv_operating_mode_set(uint8_t mode) { R_SYSTEM->OPCCR_b.OPCM = mode; }
void bsp_prv_prepare_pll(uint32_t clock, uint32_t const * const hz)
{
    memcpy(frequencies[clock - CGC_CLOCK_PLL], hz, sizeof(frequencies[0]));
}
void bsp_prv_clock_set(uint32_t clock, uint32_t div, uint16_t div2)
{
    /* Table9.4: FLL settling precedes checking/using direct HOCO. */
    if (test_case == 4 && TEST_FLL) assert(delayed_us >= 1920);
    ++switches;
    R_SYSTEM->SCKSCR = (uint8_t) clock;
    R_SYSTEM->SCKDIVCR = div;
    R_SYSTEM->SCKDIVCR2 = div2;
}
void R_BSP_GroupIrqWrite(bsp_grp_irq_t irq, void (* callback)(bsp_grp_irq_t))
{
    assert(irq == BSP_GRP_IRQ_OSC_STOP_DETECT && callback != NULL);
    ++callbacks;
}
uint32_t R_BSP_SourceClockHzGet(uint32_t clock)
{
    assert(clock == FSP_PRIV_CLOCK_PLL1P);
    return frequencies[0][0];
}

static void reset(cgc_instance_ctrl_t * ctrl)
{
    memset(&cgc_test_system, 0, sizeof(cgc_test_system));
    memset(&cgc_test_icu, 0, sizeof(cgc_test_icu));
    memset(frequencies, 0, sizeof(frequencies));
    R_SYSTEM->HOCOCR = R_SYSTEM->MOSCCR = R_SYSTEM->PLLCR = R_SYSTEM->PLL2CR = 1;
    R_SYSTEM->SCKSCR = 1;
    /* Disconnect consumers using the documented MOCO exception, not module stop. */
    R_SYSTEM->SCICKCR = R_SYSTEM->SPICKCR = R_SYSTEM->ADCCKCR = R_SYSTEM->GPTCKCR = 1;
    R_SYSTEM->LCDCKCR = R_SYSTEM->USBCKCR = R_SYSTEM->USB60CKCR = R_SYSTEM->I3CCKCR = 1;
    R_SYSTEM->OCTACKCR = R_SYSTEM->CANFDCKCR = R_SYSTEM->BCKACR = 1;
    R_SYSTEM->ESWCKCR = R_SYSTEM->ESWPCKCR = R_SYSTEM->ETHPCKCR = 1;
    writes = switches = callbacks = delays = delayed_us = reference_waits = busy_waits = 0;
    enforce_references = enforce_fll_stop = enforce_busy = false;
    stable();
    memset(ctrl, 0, sizeof(*ctrl));
    cgc_cfg_t cfg = {0};
    assert(g_cgc_on_cgc.open(ctrl, &cfg) == FSP_SUCCESS);
}
static cgc_pll_cfg_t pll(cgc_clock_t source, unsigned mhz, unsigned p)
{
    /* With24MHz /3 or48MHz /6 unavailable: HOCO /2 gives24MHz reference. */
    cgc_pll_cfg_t cfg = {.source_clock = source, .divider = CGC_PLL_DIV_1,
        .multiplier = BSP_CLOCKS_PLL_MUL(mhz / 24U, 0),
        .out_div_p = p, .out_div_q = 2, .out_div_r = 2};
    if (source == CGC_CLOCK_HOCO) cfg.divider = CGC_PLL_DIV_2;
    return cfg;
}
static cgc_clocks_cfg_t config(void)
{
    cgc_clocks_cfg_t cfg = {.system_clock = CGC_CLOCK_MOCO,
        .hoco_state = CGC_CLOCK_CHANGE_NONE, .moco_state = CGC_CLOCK_CHANGE_NONE,
        .loco_state = CGC_CLOCK_CHANGE_NONE, .mainosc_state = CGC_CLOCK_CHANGE_NONE,
        .pll_state = CGC_CLOCK_CHANGE_NONE, .pll2_state = CGC_CLOCK_CHANGE_NONE};
    cfg.divider_cfg.sckdivcr_w = 0x32233422U;
    cfg.divider_cfg.sckdivcr2 = 0x2120;
    return cfg;
}
static void ready(cgc_clock_t source)
{
    if (source == CGC_CLOCK_MAIN_OSC) R_SYSTEM->MOSCCR = 0;
    else R_SYSTEM->HOCOCR = 0;
    stable();
}

static void output_limits(void)
{
    cgc_instance_ctrl_t ctrl;
    for (unsigned unit = 0; unit < 2; ++unit)
    {
        reset(&ctrl);
        ready(CGC_CLOCK_MAIN_OSC);
        cgc_pll_cfg_t cfg = pll(CGC_CLOCK_MAIN_OSC, 2400, 2);
        fsp_err_t result = g_cgc_on_cgc.clockStart(&ctrl, (cgc_clock_t) (5 + unit), &cfg);
#if TEST_CHECKS
        assert(result == (unit ? FSP_SUCCESS : FSP_ERR_ASSERTION));
        if (!unit) assert(writes == 0 && R_SYSTEM->PLLCR == 1);
#else
        assert(result == FSP_SUCCESS);
#endif
        /* HM70.49: reject >1200MHz Q/R without lowering their1200MHz limit. */
        reset(&ctrl);
        ready(CGC_CLOCK_MAIN_OSC);
        cfg = pll(CGC_CLOCK_MAIN_OSC, 1920, 2);
        cfg.out_div_q = cfg.out_div_r = 10; /* /1.5:1280 is not legal. */
#if TEST_CHECKS
        assert(g_cgc_on_cgc.clockStart(&ctrl, (cgc_clock_t) (5 + unit), &cfg) == FSP_ERR_ASSERTION);
#endif
        cfg = pll(CGC_CLOCK_MAIN_OSC, 2400, 3);
        assert(g_cgc_on_cgc.clockStart(&ctrl, (cgc_clock_t) (5 + unit), &cfg) == FSP_SUCCESS);
        assert(frequencies[unit][0] == 800000000U);
        assert(frequencies[unit][1] == 1200000000U && frequencies[unit][2] == 1200000000U);
    }
    /* Boundary exactly1000MHz:24MHz /3 *250 /2. */
    reset(&ctrl);
    ready(CGC_CLOCK_MAIN_OSC);
    cgc_pll_cfg_t cfg = pll(CGC_CLOCK_MAIN_OSC, 1200, 2);
    cfg.divider = CGC_PLL_DIV_3;
    cfg.multiplier = BSP_CLOCKS_PLL_MUL(250, 0);
    assert(g_cgc_on_cgc.clockStart(&ctrl, CGC_CLOCK_PLL, &cfg) == FSP_SUCCESS);
    assert(frequencies[0][0] == 1000000000U);
}
static void prospective_hoco(void)
{
    cgc_instance_ctrl_t ctrl;
    for (unsigned start = 0; start < 2; ++start)
    {
        reset(&ctrl);
        ready(CGC_CLOCK_HOCO);
        cgc_clocks_cfg_t cfg = config();
        cfg.system_clock = CGC_CLOCK_PLL;
        cfg.pll_cfg = pll(CGC_CLOCK_HOCO, 1992, 2); /* CPU0=996MHz <=PLL1P1GHz but >HOCO960. */
        if (start) cfg.pll_state = CGC_CLOCK_CHANGE_START;
        else
        {
            R_SYSTEM->PLLCCR_b.PLSRCSEL = 1;
            R_SYSTEM->PLLCR = 0;
            frequencies[0][0] = 996000000U;
            stable();
            /* NONE ignores supplied PLL configuration, including its source. */
            cfg.pll_cfg.source_clock = CGC_CLOCK_MAIN_OSC;
        }
#if TEST_CHECKS
        assert(g_cgc_on_cgc.clocksCfg(&ctrl, &cfg) == FSP_ERR_ASSERTION);
        assert(writes == 0 && switches == 0);
#endif
        cfg.divider_cfg.sckdivcr2_b.cpuclk_div = CGC_SYS_CLOCK_DIV_2;
        assert(g_cgc_on_cgc.clocksCfg(&ctrl, &cfg) == FSP_SUCCESS);
    }
}
static void selectors(void)
{
    cgc_instance_ctrl_t ctrl;
    unsigned cases = 0;
    /* Offsets/mappings are literal HM9.2.44-58/64-67, not production masks. */
    static unsigned const offsets[] = {0x55,0x57,0x5B,0x5D,0x5F,0x74,0x75,0x76,0x77,0x78,0xDA,0xDB,0xDC,0xDE};
    static unsigned const selections[] = {0,2,3,4,5,6,7,8,9,10};
    for (unsigned domain = 0; domain < sizeof(offsets)/sizeof(offsets[0]); ++domain)
    for (unsigned s = 0; s < sizeof(selections)/sizeof(selections[0]); ++s)
    {
        unsigned source = selections[s];
        if ((domain == 4 || domain == 9 || (domain >= 10 && domain <= 12)) && source < 5) continue;
        if ((domain == 3 || domain == 5 || domain == 8) && (source == 2 || source == 4)) continue;
        if (domain == 13 && source < 5 && source != 3) continue;
        cgc_clock_t clock = (cgc_clock_t) (source < 5 ? source :
            (source == 5 || source == 7 || source == 8) ? 5 : 6);
        for (unsigned handshake = 0; handshake <= 0xC0; handshake += 0x40)
        {
            reset(&ctrl);
            ready(CGC_CLOCK_MAIN_OSC);
            ready(CGC_CLOCK_HOCO);
            R_SYSTEM->PLLCR = R_SYSTEM->PLL2CR = 0;
            stable();
            volatile uint8_t * selector = (volatile uint8_t *) (void *) R_SYSTEM + offsets[domain];
            *selector = (uint8_t) (source | handshake);
            assert(g_cgc_on_cgc.clockStop(&ctrl, clock) == FSP_ERR_IN_USE);
            assert(writes == 0);
            if (clock == CGC_CLOCK_PLL || clock == CGC_CLOCK_PLL2)
            {
                /* Both input dependencies are live, regardless of unused caller configs. */
                assert(g_cgc_on_cgc.clockStop(&ctrl, CGC_CLOCK_MAIN_OSC) == FSP_ERR_IN_USE);
                R_SYSTEM->PLLCCR_b.PLSRCSEL = R_SYSTEM->PLL2CCR_b.PL2SRCSEL = 1;
                assert(g_cgc_on_cgc.clockStop(&ctrl, CGC_CLOCK_HOCO) == FSP_ERR_IN_USE);
            }
            cgc_clocks_cfg_t cfg = config();
            switch (clock)
            {
                case CGC_CLOCK_HOCO: cfg.hoco_state = CGC_CLOCK_CHANGE_STOP; break;
                case CGC_CLOCK_LOCO: cfg.loco_state = CGC_CLOCK_CHANGE_STOP; break;
                case CGC_CLOCK_MAIN_OSC: cfg.mainosc_state = CGC_CLOCK_CHANGE_STOP; break;
                case CGC_CLOCK_PLL: cfg.pll_state = CGC_CLOCK_CHANGE_STOP; break;
                case CGC_CLOCK_PLL2: cfg.pll2_state = CGC_CLOCK_CHANGE_STOP; break;
                default: break; /* ClocksCfg deliberately has no SOSC action. */
            }
            if (clock != CGC_CLOCK_SUBCLOCK)
            {
                assert(g_cgc_on_cgc.clocksCfg(&ctrl, &cfg) == FSP_ERR_IN_USE);
                assert(writes == 0 && switches == 0);
            }
            ++cases;
        }
    }
    /* Enabled HOCO trace is also a consumer; disabled trace is not. */
    reset(&ctrl);
    ready(CGC_CLOCK_HOCO);
    R_SYSTEM->TRCKCR = 0x90;
    assert(g_cgc_on_cgc.clockStop(&ctrl, CGC_CLOCK_HOCO) == FSP_ERR_IN_USE);
    R_SYSTEM->TRCKCR = 0x10;
    assert(g_cgc_on_cgc.clockStop(&ctrl, CGC_CLOCK_HOCO) == FSP_SUCCESS);
    printf("selector cases=%u\n", cases);
}
static void direct_hoco_wait(void)
{
    cgc_instance_ctrl_t ctrl;
    reset(&ctrl);
    cgc_clocks_cfg_t cfg = config();
    cfg.system_clock = CGC_CLOCK_HOCO;
    cfg.hoco_state = CGC_CLOCK_CHANGE_START;
    assert(g_cgc_on_cgc.clocksCfg(&ctrl, &cfg) == FSP_SUCCESS);
#if TEST_FLL
    assert(delayed_us >= 1920 && delays != 0);
#else
    assert(delayed_us == 0);
#endif
}
static void deferred_fll_stop(void)
{
    cgc_instance_ctrl_t ctrl;
    reset(&ctrl);
    ready(CGC_CLOCK_HOCO);
    R_SYSTEM->FLLCR1 = 1;
    R_SYSTEM->SCKSCR = CGC_CLOCK_HOCO;
    enforce_fll_stop = true;
    cgc_clocks_cfg_t cfg = config();
    cfg.hoco_state = CGC_CLOCK_CHANGE_STOP;
    assert(g_cgc_on_cgc.clocksCfg(&ctrl, &cfg) == FSP_SUCCESS);
    assert(R_SYSTEM->HOCOCR == 1 && R_SYSTEM->FLLCR1 == 0);
    /* The same ordering applies to a deferred PLL1 input, with either system source. */
    for (unsigned system_pll = 0; system_pll < 2; ++system_pll)
    {
        reset(&ctrl);
        ready(CGC_CLOCK_HOCO);
        R_SYSTEM->PLLCR = 0;
        R_SYSTEM->PLLCCR_b.PLSRCSEL = 1;
        R_SYSTEM->FLLCR1 = 1;
        R_SYSTEM->SCKSCR = system_pll ? CGC_CLOCK_PLL : CGC_CLOCK_MOCO;
        stable();
        enforce_fll_stop = true;
        cfg = config();
        cfg.hoco_state = cfg.pll_state = CGC_CLOCK_CHANGE_STOP;
        assert(g_cgc_on_cgc.clocksCfg(&ctrl, &cfg) == FSP_SUCCESS);
        assert(R_SYSTEM->PLLCR == 1 && R_SYSTEM->HOCOCR == 1 && R_SYSTEM->FLLCR1 == 0);
    }
}
static void sosc_fll(void)
{
    cgc_instance_ctrl_t ctrl;
    reset(&ctrl);
    R_SYSTEM->FLLCR1 = 1;
    assert(g_cgc_on_cgc.clockStop(&ctrl, CGC_CLOCK_SUBCLOCK) == FSP_ERR_IN_USE);
    assert(R_SYSTEM->SOSCCR == 0 && writes == 0);
    R_SYSTEM->FLLCR1 = 0;
    assert(g_cgc_on_cgc.clockStop(&ctrl, CGC_CLOCK_SUBCLOCK) == FSP_SUCCESS);
}
static void stabilization_references(void)
{
    cgc_instance_ctrl_t ctrl;
    reset(&ctrl);
    R_SYSTEM->HOCOCR = R_SYSTEM->MOSCCR = R_SYSTEM->PLLCR = R_SYSTEM->PLL2CR = 0;
    set_flags(0);
    R_SYSTEM->SCKSCR = CGC_CLOCK_SUBCLOCK;
    enforce_references = true;
    cgc_clocks_cfg_t cfg = config();
    cfg.system_clock = CGC_CLOCK_SUBCLOCK;
    cfg.loco_state = cfg.moco_state = CGC_CLOCK_CHANGE_STOP;
    assert(g_cgc_on_cgc.clocksCfg(&ctrl, &cfg) == FSP_SUCCESS);
    assert(reference_waits != 0 && R_SYSTEM->MOCOCR == 1 && R_SYSTEM->LOCOCR == 1);
}
static void running_pll_none(void)
{
    cgc_instance_ctrl_t ctrl;
    for (unsigned unit = 0; unit < 2; ++unit)
    for (unsigned hoco = 0; hoco < 2; ++hoco)
    {
        reset(&ctrl);
        ready(CGC_CLOCK_HOCO);
        ready(CGC_CLOCK_MAIN_OSC);
        if (unit) { R_SYSTEM->PLL2CR = 0; R_SYSTEM->PLL2CCR_b.PL2SRCSEL = hoco; }
        else { R_SYSTEM->PLLCR = 0; R_SYSTEM->PLLCCR_b.PLSRCSEL = hoco; }
        stable();
        cgc_clocks_cfg_t cfg = config();
        cfg.pll_cfg.source_clock = cfg.pll2_cfg.source_clock = hoco ? CGC_CLOCK_MAIN_OSC : CGC_CLOCK_HOCO;
        if (hoco) cfg.hoco_state = CGC_CLOCK_CHANGE_STOP;
        else cfg.mainosc_state = CGC_CLOCK_CHANGE_STOP;
        assert(g_cgc_on_cgc.clocksCfg(&ctrl, &cfg) == FSP_ERR_IN_USE);
        assert(writes == 0 && switches == 0);
        cfg = config();
        cfg.pll_cfg.source_clock = cfg.pll2_cfg.source_clock = hoco ? CGC_CLOCK_MAIN_OSC : CGC_CLOCK_HOCO;
        if (hoco) cfg.mainosc_state = CGC_CLOCK_CHANGE_STOP;
        else cfg.hoco_state = CGC_CLOCK_CHANGE_STOP;
        assert(g_cgc_on_cgc.clocksCfg(&ctrl, &cfg) == FSP_SUCCESS);
    }
}
static void loco_busy(void)
{
    cgc_instance_ctrl_t ctrl;
    reset(&ctrl);
    *(volatile uint8_t *) (void *) &R_SYSTEM->SYRACCR = 1;
    enforce_busy = true;
    assert(g_cgc_on_cgc.clockStop(&ctrl, CGC_CLOCK_LOCO) == FSP_SUCCESS);
    assert(busy_waits >= 2 && R_SYSTEM->LOCOCR == 1);
}
static void nmi_ownership(void)
{
    cgc_instance_ctrl_t ctrl;
    reset(&ctrl);
    /* NMIER ordinary R/W safety sources at5,14,16,17,18,20 (HM14.2.14). */
    R_ICU->NMIER = 0x174020;
    fsp_err_t result = g_cgc_on_cgc.oscStopDetectEnable(&ctrl);
#if TEST_CORE
    assert(result == FSP_ERR_UNSUPPORTED);
    assert(R_ICU->NMIER == 0x174020 && callbacks == 0 && writes == 0);
#else
    assert(result == FSP_SUCCESS);
    assert(R_ICU->NMIER == 0x174060 && callbacks == 1);
#endif
}
int main(int argc, char ** argv)
{
    assert(argc == 2);
    test_case = (unsigned) strtoul(argv[1], NULL, 10);
    switch (test_case)
    {
        case 1: output_limits(); break;
        case 2: prospective_hoco(); break;
        case 3: selectors(); break;
        case 4: direct_hoco_wait(); break;
        case 5: deferred_fll_stop(); break;
        case 6: sosc_fll(); break;
        case 7: stabilization_references(); break;
        case 8: running_pll_none(); break;
        case 9: loco_busy(); break;
        case 10: nmi_ownership(); break;
        default: abort();
    }
    printf("CGC-%03u passed core=%u checks=%u fll=%u\n", test_case, (unsigned) TEST_CORE, (unsigned) TEST_CHECKS, (unsigned) TEST_FLL);
    return 0;
}
