#include "hal_data.h"

#include <inttypes.h>
#include <stdio.h>

void bench_emit(const char * text);
bool bench_cgc(bool divide);

/* The accepted r020 XTAL profile has PCLKA/B/C at /2 and all other system dividers at /1. */
#define BENCH_XTAL_HZ      (24000000U)
#define BENCH_SCKDIVCR     (0x00001110U)
#define BENCH_GPT0_GTPR    (239999U)

static bool cgc_open;

typedef struct
{
    uint32_t sckdivcr;
    uint32_t pclkd_hz;
    uint32_t gpt0_gtcr;
    uint32_t gpt0_gtpr;
    uint32_t gptclkcr;
    uint32_t sci8_ccr2;
    uint32_t sci8_ccr3;
    uint16_t sckdivcr2;
    uint16_t cpu1actcsr;
    uint8_t sckscr;
    uint8_t oscsf;
    uint8_t mosccr;
    uint8_t momcr;
    uint8_t ostdsr;
    uint8_t cpu1waitcr;
    uint8_t scickcr;
    uint8_t scickdivcr;
} cgc_state_t;

static cgc_state_t cgc_read(void)
{
    cgc_state_t state = {
        .sckdivcr = R_SYSTEM->SCKDIVCR,
        .gpt0_gtcr = R_GPT0->GTCR,
        .gpt0_gtpr = R_GPT0->GTPR,
        .gptclkcr = R_GPT_GTCLK->GTCLKCR,
        .sci8_ccr2 = R_SCI_B8->CCR2,
        .sci8_ccr3 = R_SCI_B8->CCR3,
        .sckdivcr2 = R_SYSTEM->SCKDIVCR2,
        .cpu1actcsr = R_CPU_CTRL->CPU1ACTCSR,
        .sckscr = R_SYSTEM->SCKSCR,
        .oscsf = R_SYSTEM->OSCSF,
        .mosccr = R_SYSTEM->MOSCCR,
        .momcr = R_SYSTEM->MOMCR,
        .ostdsr = R_SYSTEM->OSTDSR,
        .cpu1waitcr = R_CPU_CTRL->CPU1WAITCR,
        .scickcr = R_SYSTEM->SCICKCR,
        .scickdivcr = R_SYSTEM->SCICKDIVCR,
    };
    uint32_t pckd = (state.sckdivcr & R_SYSTEM_SCKDIVCR_PCKD_Msk) >> R_SYSTEM_SCKDIVCR_PCKD_Pos;
    if ((CGC_CLOCK_MAIN_OSC == state.sckscr) && (CGC_SYS_CLOCK_DIV_2 >= pckd))
    {
        state.pclkd_hz = R_BSP_SourceClockHzGet(FSP_PRIV_CLOCK_MAIN_OSC) >> pckd;
    }
    return state;
}

static void cgc_emit_state(const char * phase, const cgc_state_t * state)
{
    char line[160];
    (void) snprintf(line, sizeof(line),
                    "CGC %s SCKSCR=%02x SCKDIVCR=%08" PRIx32 " SCKDIVCR2=%04x PCLKD_HZ=%" PRIu32
                    " OSCSF=%02x MOSCCR=%02x MOMCR=%02x OSTDSR=%02x CPU1ACTCSR=%04x CPU1WAITCR=%02x\r\n",
                    phase, state->sckscr, state->sckdivcr, state->sckdivcr2, state->pclkd_hz,
                    state->oscsf, state->mosccr, state->momcr, state->ostdsr, state->cpu1actcsr, state->cpu1waitcr);
    bench_emit(line);
    (void) snprintf(line, sizeof(line),
                    "CGC %s SCICKCR=%02x SCICKDIVCR=%02x SCI8_CCR2=%08" PRIx32 " SCI8_CCR3=%08" PRIx32
                    " GPTCLKCR=%08" PRIx32 " GPT0_GTCR=%08" PRIx32 " GPT0_GTPR=%" PRIu32 "\r\n",
                    phase, state->scickcr, state->scickdivcr, state->sci8_ccr2, state->sci8_ccr3,
                    state->gptclkcr, state->gpt0_gtcr, state->gpt0_gtpr);
    bench_emit(line);
}

static uint32_t cgc_sckdivcr(bool divide)
{
    uint32_t pckd = divide ? CGC_SYS_CLOCK_DIV_2 : CGC_SYS_CLOCK_DIV_1;
    return BENCH_SCKDIVCR | (pckd << R_SYSTEM_SCKDIVCR_PCKD_Pos);
}

static bool cgc_matches(const cgc_state_t * state, bool divide)
{
    return (0U == BSP_CFG_CPU_CORE) && (BENCH_XTAL_HZ == BSP_CFG_XTAL_HZ) &&
           (CGC_CLOCK_MAIN_OSC == state->sckscr) && (cgc_sckdivcr(divide) == state->sckdivcr) &&
           (0U == state->sckdivcr2) && ((BENCH_XTAL_HZ / (divide ? 2U : 1U)) == state->pclkd_hz) &&
           (0U == (state->mosccr & R_SYSTEM_MOSCCR_MOSTP_Msk)) &&
           (0U == (state->momcr & R_SYSTEM_MOMCR_MOSEL_Msk)) &&
           (0U != (state->oscsf & R_SYSTEM_OSCSF_MOSCSF_Msk)) &&
           (0U == (state->ostdsr & R_SYSTEM_OSTDSR_OSTDF_Msk)) &&
           (0U == (state->cpu1actcsr & (R_CPU_CTRL_CPU1ACTCSR_ACT_Msk | R_CPU_CTRL_CPU1ACTCSR_ACTREQ_Msk))) &&
           (CGC_CLOCK_MAIN_OSC == state->scickcr) && (0U == state->scickdivcr) &&
           (0x80000C10U == state->sci8_ccr2) && (0x00009200U == state->sci8_ccr3) &&
           (R_GPT_GTCLK_GTCLKCR_BPEN_Msk == state->gptclkcr) &&
           (R_GPT0_GTCR_CST_Msk == state->gpt0_gtcr) && (BENCH_GPT0_GTPR == state->gpt0_gtpr);
}

static bool cgc_check(fsp_err_t err, const char * operation)
{
    if (FSP_SUCCESS == err)
    {
        return true;
    }
    char line[64];
    (void) snprintf(line, sizeof(line), "CGC FAIL %s err=%u\r\n", operation, (unsigned int) err);
    bench_emit(line);
    return false;
}

static bool cgc_get(const cgc_state_t * state, cgc_clock_t * source, cgc_divider_cfg_t * dividers)
{
    if (!cgc_check(R_CGC_SystemClockGet(g_cgc.p_ctrl, source, dividers), "SystemClockGet"))
    {
        return false;
    }
    if (((uint32_t) *source != state->sckscr) || (dividers->sckdivcr_w != state->sckdivcr) ||
        (dividers->sckdivcr2 != state->sckdivcr2))
    {
        bench_emit("CGC FAIL SystemClockGet disagrees with registers\r\n");
        return false;
    }
    return true;
}

bool bench_cgc(bool divide)
{
    cgc_state_t before = cgc_read();
    cgc_emit_state("BEFORE", &before);
    if (!cgc_matches(&before, false) && !cgc_matches(&before, true))
    {
        bench_emit("CGC FAIL unexpected live profile\r\n");
        return false;
    }
    if (!cgc_open)
    {
        if (!cgc_check(R_CGC_Open(g_cgc.p_ctrl, g_cgc.p_cfg), "Open"))
        {
            return false;
        }
        cgc_open = true;
    }

    cgc_clock_t source;
    cgc_divider_cfg_t dividers;
    if (!cgc_get(&before, &source, &dividers))
    {
        return false;
    }
    fsp_err_t err = FSP_SUCCESS;
    const bool changed = (before.sckdivcr != cgc_sckdivcr(divide));
    if (changed)
    {
        /* The BEFORE output must also be drained before changing clocks. */
        if (0U == R_SCI_B8->CSR_b.TEND)
        {
            bench_emit("CGC FAIL SCI8 not drained\r\n");
            return false;
        }
        dividers.sckdivcr_b.pclkd_div = divide ? CGC_SYS_CLOCK_DIV_2 : CGC_SYS_CLOCK_DIV_1;
        err = R_CGC_SystemClockSet(g_cgc.p_ctrl, source, &dividers);
    }

    cgc_state_t after = cgc_read();
    cgc_emit_state("AFTER", &after);
    if (!cgc_check(err, "SystemClockSet") || !cgc_get(&after, &source, &dividers))
    {
        return false;
    }
    if (!cgc_matches(&after, divide) || (after.cpu1waitcr != before.cpu1waitcr))
    {
        bench_emit("CGC FAIL unexpected readback\r\n");
        return false;
    }
    char line[64];
    (void) snprintf(line, sizeof(line), "CGC PASS PCLKD=/%u (%s)\r\n",
                    divide ? 2U : 1U, changed ? "changed" : "unchanged");
    bench_emit(line);
    return true;
}
