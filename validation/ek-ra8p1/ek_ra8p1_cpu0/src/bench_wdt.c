#include "hal_data.h"

#include <inttypes.h>
#include <stdio.h>

void bench_emit(const char * text);
void bench_wdt_report_boot(void);
bool bench_wdt(void);

#if (BSP_CFG_CPU_CORE != 0) || BSP_TZ_SECURE_BUILD || BSP_TZ_NONSECURE_BUILD
 #error "This fixture requires the CPU0 Flat bench"
#endif

/* RA8P1 HM §§7.2.1–7.2.2: read-only option words, not generated image contents. */
#define BENCH_OFS0_ADDR        (0x02C9F040UL)
#define BENCH_OFS2_ADDR        (0x02C9F044UL)
#define BENCH_PCLKB_HZ         (12000000U)
#define BENCH_WDTCR            (0x2281U) /* 75% -> 25%, PCLKB/8192, 4096 counts. */
#define BENCH_RELOAD_MAX       (0x0FFFU)
#define BENCH_RELOAD_MIN       (0x0F00U)
#define BENCH_REFRESH_MAX      (0x07FFU)
#define BENCH_REFRESH_MIN      (0x06FFU)

static bool wdt_attempted;

void bench_wdt_report_boot(void)
{
    /* Call before READY. The owner startup does not write RSTSR1. Never clear flags here. */
    const uint32_t rstsr1 = R_SYSTEM->RSTSR1;
    char line[72];
    (void) snprintf(line, sizeof(line), "WDT BOOT RSTSR1=%08" PRIx32 " WDT0RF=%u\r\n",
                    rstsr1, (0U != (rstsr1 & R_SYSTEM_RSTSR1_WDT0RF_Msk)) ? 1U : 0U);
    bench_emit(line);
}

static bool wdt_wait_count(uint32_t min, uint32_t max, uint32_t polls, bool refresh, uint32_t * count)
{
    for (uint32_t i = 0; i < polls; ++i)
    {
        /* Keep the in-window sample and refresh request together. Never log in this interval. */
        const uint32_t irq_state = __get_PRIMASK();
        __disable_irq();
        fsp_err_t err = g_bench_wdt.p_api->counterGet(g_bench_wdt.p_ctrl, count);
        const bool in_range = (FSP_SUCCESS == err) && (*count >= min) && (*count <= max);
        if (in_range && refresh)
        {
            err = g_bench_wdt.p_api->refresh(g_bench_wdt.p_ctrl);
        }
        __set_PRIMASK(irq_state);

        if (FSP_SUCCESS != err)
        {
            return false;
        }
        if (in_range)
        {
            return true;
        }
        if (refresh && (*count < min))
        {
            return false;
        }
        R_BSP_SoftwareDelay(2U, BSP_DELAY_UNITS_MILLISECONDS);
    }
    return false;
}

static void wdt_await_reset(const char * message) __attribute__((noreturn));

static void wdt_await_reset(const char * message)
{
    bench_emit(message);
    /* Returning would allow another bench command while WDT0 is still armed. */
    for (;;)
    {
        __NOP();
    }
}

bool bench_wdt(void)
{
    if (wdt_attempted)
    {
        bench_emit("WDT BLOCK already attempted this boot\r\n");
        return false;
    }

    if ((0xFFFFFFFFU != BSP_CFG_ROM_REG_OFS0) || (0xFFFFFFEFU != BSP_CFG_ROM_REG_OFS2) ||
        (0xFFFFFFFFU != *(volatile uint32_t const *) BENCH_OFS0_ADDR) ||
        (0xFFFFFFEFU != *(volatile uint32_t const *) BENCH_OFS2_ADDR))
    {
        bench_emit("WDT BLOCK unexpected option words\r\n");
        return false;
    }

    if ((0U != (R_SYSTEM->RSTSR1 & R_SYSTEM_RSTSR1_WDT0RF_Msk)) || (0U != R_WDT0->WDTSR))
    {
        bench_emit("WDT BLOCK stale cause or non-reset WDT0 state\r\n");
        return false;
    }

    if ((24000000U != BSP_CFG_XTAL_HZ) || (BSP_CLOCKS_SOURCE_CLOCK_MAIN_OSC != R_SYSTEM->SCKSCR) ||
        (0U == (R_SYSTEM->OSCSF & R_SYSTEM_OSCSF_MOSCSF_Msk)) ||
        (0U != (R_SYSTEM->OSTDSR & R_SYSTEM_OSTDSR_OSTDF_Msk)) ||
        (BENCH_PCLKB_HZ != R_FSP_SystemClockHzGet(FSP_PRIV_CLOCK_PCLKB)) ||
        (0U != (R_CPU_CTRL->CPU1ACTCSR & (R_CPU_CTRL_CPU1ACTCSR_ACT_Msk | R_CPU_CTRL_CPU1ACTCSR_ACTREQ_Msk))))
    {
        bench_emit("WDT BLOCK unexpected PCLKB or CPU1 state\r\n");
        return false;
    }

    const uint32_t dhcsr = DCB->DHCSR;
    const uint32_t dbgstopcr = R_CPU_DBG->DBGSTOPCR;
    char line[88];
    (void) snprintf(line, sizeof(line), "WDT PREARM DHCSR=%08" PRIx32 " DBGSTOPCR=%08" PRIx32 "\r\n",
                    dhcsr, dbgstopcr);
    bench_emit(line);
    if (0U != (dhcsr & DCB_DHCSR_C_DEBUGEN_Msk))
    {
        bench_emit("WDT BLOCK halting debug enabled\r\n");
        return false;
    }
    /* C_DEBUGEN clear alone does not rule out OCD; parent must establish undebugged free-run. */

    wdt_cfg_t const * const cfg = g_bench_wdt.p_cfg;
    if ((WDT_TIMEOUT_4096 != cfg->timeout) || (WDT_CLOCK_DIVISION_8192 != cfg->clock_division) ||
        (WDT_WINDOW_START_75 != cfg->window_start) || (WDT_WINDOW_END_25 != cfg->window_end) ||
        (WDT_RESET_CONTROL_RESET != cfg->reset_control) || (WDT_STOP_CONTROL_DISABLE != cfg->stop_control) ||
        (NULL != cfg->p_callback))
    {
        bench_emit("WDT BLOCK unexpected generated configuration\r\n");
        return false;
    }

    wdt_attempted = true;
    if ((FSP_SUCCESS != g_bench_wdt.p_api->open(g_bench_wdt.p_ctrl, cfg)) ||
        (BENCH_WDTCR != R_WDT0->WDTCR) || (R_WDT0_WDTRCR_RSTIRQS_Msk != R_WDT0->WDTRCR) ||
        (0U != R_WDT0->WDTCSTPR) || (0U != R_WDT0->WDTSR))
    {
        bench_emit("WDT BLOCK open or WDT0 register readback\r\n");
        return false;
    }

    bench_emit("WDT START 4096 counts PCLKB=12000000 /8192\r\n");
    if (0U != (DCB->DHCSR & DCB_DHCSR_C_DEBUGEN_Msk))
    {
        bench_emit("WDT BLOCK halting debug enabled\r\n");
        return false;
    }
    if (FSP_SUCCESS != g_bench_wdt.p_api->refresh(g_bench_wdt.p_ctrl))
    {
        wdt_await_reset("WDT FAIL start request\r\n");
    }

    uint32_t reloaded = 0U;
    if (!wdt_wait_count(BENCH_RELOAD_MIN, BENCH_RELOAD_MAX, 20U, false, &reloaded))
    {
        wdt_await_reset("WDT FAIL no start reload\r\n");
    }

    /* HM Table 28.3: 0x0BFF -> 0x03FF. Stay well inside the window despite read/refresh latency. */
    for (unsigned int n = 1U; n <= 7U; ++n)
    {
        uint32_t count = 0U;
        if (!wdt_wait_count(BENCH_REFRESH_MIN, BENCH_REFRESH_MAX, 1000U, true, &count) ||
            !wdt_wait_count(BENCH_RELOAD_MIN, BENCH_RELOAD_MAX, 20U, false, &reloaded))
        {
            wdt_await_reset("WDT FAIL midpoint refresh or reload\r\n");
        }
        (void) snprintf(line, sizeof(line), "WDT REFRESH n=%u count=%04" PRIx32 " reload=%04" PRIx32 "\r\n",
                        n, count, reloaded);
        bench_emit(line);
    }
    wdt_await_reset("WDT STOP no more refreshes; expecting WDT0 reset\r\n");
}
