// Each mask below is an independent literal from its OWN HM clock-control section.
// USB 9.2.44 B11/12; OCTA 9.2.45 B16/17 (read confirm, no timed wait);
// CANFD 9.2.46 C26/27; USB60 9.2.47 B12; I3C 9.2.48 B4;
// SCI 9.2.54 B22..31; SPI 9.2.55 B18/19; ADC 9.2.56 D21;
// GPT 9.2.57 E18..21/E27..31; LCD 9.2.58 C4 (pp360-375).
// Datasheet Table2.50 p115: FLL 1920us standard / 2150us SiP.
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include "configuration.h"
#define RA8P1_LAYOUT_NATIVE_CM85_H
#define RA8P1_LAYOUT_NATIVE_CM33_H
#define __IM volatile
#define __OM volatile
#define __IOM volatile
#include "R7KA8P1KF.h"
#undef R_SYSTEM
#undef R_MSTP
static R_SYSTEM_Type regs;
static R_MSTP_Type mstp;
#define R_SYSTEM (&regs)
#define R_MSTP (&mstp)
#include "production_keys.inc"
#define BSP_FEATURE_BSP_HAS_PRCR_S 1
#define BSP_FEATURE_TZ_VERSION 2
#define BSP_FEATURE_CGC_HAS_CPUCLK 1
#define BSP_FEATURE_CGC_HAS_PLL2 1
#define BSP_FEATURE_CGC_STARTUP_OPCCR_MODE 0
#define BSP_PRV_STARTUP_OPERATING_MODE 0
#define BSP_PRV_OPERATING_MODE_HIGH_SPEED 0
#define BSP_PRV_OPERATING_MODE_LOW_SPEED 3
#define BSP_CLOCKS_SOURCE_CLOCK_HOCO 0U
#define BSP_CLOCKS_SOURCE_CLOCK_MAIN_OSC 3U
#define BSP_CLOCKS_CLOCK_DISABLED 255U
#define BSP_CLOCK_CFG_SUBCLOCK_POPULATED 1
#define BSP_FEATURE_CGC_HAS_FLL 1
#define BSP_CFG_FLL_ENABLE TEST_FLL
#include "production_fll.inc"
#define BSP_PRV_FLL_FLLCR2 0x1e8U
#define BSP_PRV_HOCO_USED 1
#define BSP_PRV_STABILIZE_HOCO 1
#define BSP_PRV_PLL_SUPPORTED 1
#define BSP_PRV_PLL_USED 1
#define BSP_PRV_PLL2_SUPPORTED 1
#define BSP_PRV_PLL2_USED 1
#define BSP_PRV_PLLCCR 0x12600U
#define BSP_PRV_PLLCCR2 0x246U
#define BSP_PRV_PLL2CCR 0x12b00U
#define BSP_PRV_PLL2CCR2 0x246U
#define BSP_PRV_STABILIZE_PLL 1
#define BSP_PRV_ASYNC_PLL2_USED 1
#define BSP_CFG_PLL_SOURCE (TEST_PLL_HOCO ? 0 : 3)
#define BSP_CFG_PLL2_SOURCE (TEST_PLL_HOCO ? 3 : 0)
#define BSP_CFG_CLOCK_SOURCE 5U
#define BSP_PRV_STARTUP_SCKDIVCR 0x43333433U
#define BSP_PRV_STARTUP_SCKDIVCR2 0x2220U
#define BSP_CFG_CPUCLK_DIV 0U
#define BSP_CFG_CLKOUT_SOURCE 255U
#define BSP_CFG_OCTA_SOURCE 255U
#define BSP_CFG_UCK_SOURCE 5U
#define BSP_PRV_UCK_DIV 1U
#define BSP_FEATURE_BSP_HAS_USB_CLOCK_REQ 1
#define BSP_FEATURE_BSP_HAS_USBCKDIVCR 1
#define BSP_FEATURE_BSP_HAS_USB_CLOCK_SEL 1
#define BSP_FEATURE_BSP_HAS_CANFD_CLOCK 1
#define BSP_CFG_CANFDCLK_SOURCE 3U
#define BSP_CFG_CANFDCLK_DIV 2U
#define BSP_PRV_PERIPHERAL_CLK_REQ_BIT_MASK 0x40U
#define BSP_PRV_PERIPHERAL_CLK_RDY_BIT_MASK 0x80U
#define BSP_PRV_PERIPHERAL_CLK_RDY_BIT_POS 7U
#define BSP_FEATURE_BSP_HAS_OCTASPI_CLOCK 1
#define BSP_DELAY_UNITS_MICROSECONDS 1U
static uint32_t g_clock_freq[11] = {48000000,8000000,32768,24000000,32768,1000000000};
typedef struct { uint8_t source_clock, divider; } bsp_octaclk_settings_t;
static volatile uint8_t *control, *divider;
static volatile uint32_t *stop;
static unsigned expected_mask, old_div, old_source, stop_confirms, stopped_waits, started_waits, elapsed;
static unsigned voltage_waits, fll_elapsed, pll_waits, system_sets, sosc_ready;
static bool startup;
static void check_stop_before_request() {
    assert(stop && ((*stop & expected_mask) == expected_mask));
    assert((*control & 0x40U) == 0 && *divider == old_div);
}
static void wait_register(char const *name, unsigned expected) {
    if (std::strstr(name,"VSCR")) {
        assert(expected==0 && regs.PLLCR==1 && regs.PLL2CR==1);
        if (++voltage_waits==2) assert(regs.VSCR==1);
        return;
    }
    if (std::strstr(name,"OSCSF")) {
        if (std::strstr(name,"HOCOSF")) { regs.OSCSF_b.HOCOSF=1; return; }
        assert(voltage_waits==2 && regs.VSCR==1);
        assert(!TEST_FLL || fll_elapsed>=2150);
        ++pll_waits;
        regs.OSCSF_b.PLLSF=regs.OSCSF_b.PLL2SF=1;
        return;
    }
    if (std::strstr(name,"**pp_stop")) {
        // The selected module mask must be visible before any CKSREQ write.
        if (!startup) check_stop_before_request();
        ++stop_confirms;
        return;
    }
    if (startup) {
        if (std::strstr(name,"USBCKCR")) {
            control=&regs.USBCKCR; divider=&regs.USBCKDIVCR;
            stop=&mstp.MSTPCRB; expected_mask=0x1800;
        } else {
            control=&regs.CANFDCKCR; divider=&regs.CANFDCKDIVCR;
            stop=&mstp.MSTPCRC; expected_mask=0x0c000000;
        }
    }
    assert(((*control & 0x40U)!=0)==(expected!=0));
    if (expected) {
        if (old_div) {
            assert((*stop & expected_mask)==expected_mask && stop_confirms);
            if (control!=&regs.OCTACKCR) assert(elapsed>0);
        }
        *control|=0x80; ++stopped_waits;
    } else {
        *control&=0x7f; ++started_waits;
    }
}
#define FSP_HARDWARE_REGISTER_WAIT(reg, expected) do { wait_register(#reg,expected); assert((reg)==(expected)); } while (0)
#define FSP_REGISTER_READ(reg) ((void)(reg))
#define FSP_PARAMETER_NOT_USED(v) ((void)(v))
static void R_BSP_SoftwareDelay(unsigned us, unsigned units) {
    assert(units==1);
    if (startup && us==2150) {
        assert(sosc_ready && regs.HOCOCR==0 && regs.FLLCR1==1);
        assert(regs.PLLCR==1 && regs.PLL2CR==1);
        fll_elapsed+=us; return;
    }
    assert(us>0); elapsed+=us;
}
#include "production_stop.inc"
#include "production_peripheral.inc"
#include "production_octa.inc"
void R_BSP_FlashCacheEnable() {}
void bsp_prv_operating_mode_set(unsigned mode) { assert(mode==0); }
void bsp_clock_freq_var_init() {}
void bsp_soft_reset_prepare() { regs.PLLCR=regs.PLL2CR=1; }
void bsp_prv_sosc_init() { ++sosc_ready; }
void bsp_prv_clock_set(unsigned, unsigned, unsigned) { assert(voltage_waits==2 && pll_waits==2); ++system_sets; }
void bsp_prv_clock_set_hard_reset() { bsp_prv_clock_set(0,0,0); }
#include "production_init.inc"
struct Domain { volatile uint8_t *ctrl, *div; volatile uint32_t *mstp; unsigned mask; };
int main() {
    Domain domains[] = {
        {&regs.USBCKCR,&regs.USBCKDIVCR,&mstp.MSTPCRB,0x00001800},
        {&regs.OCTACKCR,&regs.OCTACKDIVCR,&mstp.MSTPCRB,0x00030000},
        {&regs.CANFDCKCR,&regs.CANFDCKDIVCR,&mstp.MSTPCRC,0x0c000000},
        {&regs.USB60CKCR,&regs.USB60CKDIVCR,&mstp.MSTPCRB,0x00001000},
        {&regs.I3CCKCR,&regs.I3CCKDIVCR,&mstp.MSTPCRB,0x00000010},
        {&regs.SCICKCR,&regs.SCICKDIVCR,&mstp.MSTPCRB,0xffc00000},
        {&regs.SPICKCR,&regs.SPICKDIVCR,&mstp.MSTPCRB,0x000c0000},
        {&regs.ADCCKCR,&regs.ADCCKDIVCR,&mstp.MSTPCRD,0x00200000},
        {&regs.GPTCKCR,&regs.GPTCKDIVCR,&mstp.MSTPCRE,0xf83c0000},
        {&regs.LCDCKCR,&regs.LCDCKDIVCR,&mstp.MSTPCRC,0x00000010},
    };
    for (auto d : domains) for (unsigned initial : {0U,0x55555555U,0xffffffffU})
        for (unsigned source : {1U,2U,3U,5U}) for (unsigned div : {0U,1U,9U}) {
        std::memset(&regs,0,sizeof(regs)); std::memset(&mstp,0,sizeof(mstp));
        control=d.ctrl; divider=d.div; stop=d.mstp; expected_mask=d.mask;
        *stop=initial; *control=source; *divider=div;
        old_div=div; old_source=source; stop_confirms=elapsed=stopped_waits=started_waits=0;
        if (control==&regs.OCTACKCR) {
#if BSP_TZ_NONSECURE_BUILD
            regs.PRCR_NS=0x18;
#else
            regs.PRCR_S=0x38;
#endif
            bsp_octaclk_settings_t requested{3,2}; R_BSP_OctaclkUpdate(&requested);
#if BSP_TZ_NONSECURE_BUILD
            assert(regs.PRCR_NS==0xa518);
#else
            assert(regs.PRCR_S==0xa538);
#endif
        } else bsp_peripheral_clock_set(control,divider,2,3);
        assert(*stop==initial && *divider==2 && (*control & 15)==3);
        assert(stopped_waits==1 && started_waits==1 && stop_confirms==(div?1U:0U));
        if (div && control!=&regs.OCTACKCR) {
            // Four nominal cycles must exceed two cycles even at -10% LOCO/MOCO.
            unsigned divisor=div==9?32:2;
            uint64_t minimum_ns=(2000000000ULL*divisor*10)/(uint64_t(g_clock_freq[old_source])*9);
            assert(uint64_t(elapsed)*1000>=minimum_ns);
        } else assert(elapsed==0);
    }
    std::memset(&regs,0,sizeof(regs)); std::memset(&mstp,0,sizeof(mstp));
    startup=true; regs.PLLCR=regs.PLL2CR=1; regs.VSCR=2;
    regs.USBCKCR=regs.CANFDCKCR=1;
    regs.USBCKDIVCR=regs.CANFDCKDIVCR=old_div=1;
    stop_confirms=elapsed=0;
    bsp_clock_init();
    assert(voltage_waits==2 && pll_waits==2 && system_sets==1);
    assert(fll_elapsed==(TEST_FLL?2150U:0U));
    assert(regs.CANFDCKCR==3 && regs.CANFDCKDIVCR==2); // MOSC is encoding 3, NOT reset MOCO=1.
    assert(regs.USBCKCR==5 && regs.USBCKDIVCR==1);
    assert(mstp.MSTPCRB==0 && mstp.MSTPCRC==0);
    std::puts("per-domain masks, request/read/delay order, voltage/FLL/PLL and MOSC anchors passed");
}
