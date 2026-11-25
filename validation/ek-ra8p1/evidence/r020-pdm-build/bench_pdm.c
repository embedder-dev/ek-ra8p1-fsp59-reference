#include "hal_data.h"

#include <inttypes.h>
#include <stdio.h>

void bench_emit(const char * text);
bool bench_pdm(void);
void bench_pdm_callback(pdm_callback_args_t * args);

enum
{
    PDM_BENCH_SAMPLES = 2048,
    PDM_BENCH_TIMEOUT_MS = 500,
    PDM_BENCH_SIGN = 1U << 19,
    PDM_BENCH_MASK = (1U << 20) - 1U,
};

static uint32_t pcm[PDM_BENCH_SAMPLES];
static volatile struct
{
    uint32_t complete;
    uint32_t errors;
    uint32_t overruns;
    uint32_t flags;
    uint32_t samples;
    bool buffer_matches;
} capture;

void bench_pdm_callback(pdm_callback_args_t * args)
{
    capture.samples = args->samples;
    capture.buffer_matches = (args->p_buffer == pcm);
    capture.flags |= args->error;
    if ((args->error & PDM_ERROR_FIFO_OVERFLOW) != 0U)
    {
        ++capture.overruns;
    }
    if (args->event == PDM_EVENT_COMPLETE)
    {
        ++capture.complete;
    }
    else if (args->event == PDM_EVENT_ERROR)
    {
        ++capture.errors;
    }
}

static bool pdm_check(fsp_err_t err, const char * operation)
{
    if (FSP_SUCCESS == err)
    {
        return true;
    }
    char line[64];
    (void) snprintf(line, sizeof(line), "PDM %s err=%u\r\n", operation, (unsigned int) err);
    bench_emit(line);
    return false;
}

static bool pdm_preflight(void)
{
    const uint32_t pclkb = R_FSP_SystemClockHzGet(FSP_PRIV_CLOCK_PCLKB);
    const uint32_t moco_stopped = R_SYSTEM->MOCOCR & R_SYSTEM_MOCOCR_MCSTP_Msk;
    const uint32_t pin_mask = R_PFS_PORT_PIN_PmnPFS_PMR_Msk | R_PFS_PORT_PIN_PmnPFS_PSEL_Msk |
                              R_PFS_PORT_PIN_PmnPFS_ASEL_Msk;
    const uint32_t mux = R_PFS_PORT_PIN_PmnPFS_PMR_Msk | IOPORT_PERIPHERAL_PDM;
    const uint32_t p812 = R_PFS->PORT[8].PIN[12].PmnPFS;
    const uint32_t p502 = R_PFS->PORT[5].PIN[2].PmnPFS;
    char line[128];
    (void) snprintf(line, sizeof(line), "PDM preflight PCLKB=%" PRIu32 " MCSTP=%" PRIu32
                    " P812=%08" PRIx32 " P502=%08" PRIx32 "\r\n", pclkb, moco_stopped, p812, p502);
    bench_emit(line);
    return (moco_stopped == 0U) && (pclkb >= 1000000U) && (pclkb <= 62500000U) &&
           ((p812 & pin_mask) == mux) && ((p502 & pin_mask) == mux);
}

static bool pdm_report_pcm(void)
{
    int32_t min = INT32_MAX;
    int32_t max = INT32_MIN;
    int32_t sum = 0;
    uint32_t sum_abs = 0U;
    uint32_t clips = 0U;
    for (uint32_t i = 0U; i < PDM_BENCH_SAMPLES; ++i)
    {
        /* HM 50.2.65: unshifted PDDRR is signed 20-bit with the sign at bit 19. */
        const int32_t sample = (int32_t) ((pcm[i] & PDM_BENCH_MASK) ^ PDM_BENCH_SIGN) - PDM_BENCH_SIGN;
        min = (sample < min) ? sample : min;
        max = (sample > max) ? sample : max;
        sum += sample;
        sum_abs += (uint32_t) ((sample < 0) ? -sample : sample);
        if ((sample == -PDM_BENCH_SIGN) || (sample == PDM_BENCH_SIGN - 1))
        {
            ++clips;
        }
    }
    char line[128];
    (void) snprintf(line, sizeof(line), "PDM PCM min=%" PRId32 " max=%" PRId32 " mean=%" PRId32
                    " mean_abs=%" PRIu32 " clips=%" PRIu32 "\r\n",
                    min, max, sum / PDM_BENCH_SAMPLES, sum_abs / PDM_BENCH_SAMPLES, clips);
    bench_emit(line);
    return (min != max) && (clips < PDM_BENCH_SAMPLES);
}

bool bench_pdm(void)
{
    if (!pdm_preflight() || !pdm_check(g_bench_pdm.p_api->open(g_bench_pdm.p_ctrl, g_bench_pdm.p_cfg), "open"))
    {
        bench_emit("PDM FAIL\r\n");
        return false;
    }

    capture.complete = 0U;
    capture.errors = 0U;
    capture.overruns = 0U;
    capture.flags = 0U;
    capture.samples = 0U;
    capture.buffer_matches = false;

    const fsp_err_t started = g_bench_pdm.p_api->start(g_bench_pdm.p_ctrl, pcm, PDM_BENCH_SAMPLES);
    bool timed_out = false;
    if (FSP_SUCCESS == started)
    {
        for (uint32_t ms = 0U; (ms < PDM_BENCH_TIMEOUT_MS) &&
             (capture.complete == 0U) && (capture.errors == 0U); ++ms)
        {
            R_BSP_SoftwareDelay(1U, BSP_DELAY_UNITS_MILLISECONDS);
        }
        timed_out = (capture.complete == 0U) && (capture.errors == 0U);
    }

    /* r020 Close stops reception and detaches both IRQs. Do not inspect PCM while owned by the ISR. */
    const fsp_err_t closed = g_bench_pdm.p_api->close(g_bench_pdm.p_ctrl);
    const bool start_ok = pdm_check(started, "start");
    const bool close_ok = pdm_check(closed, "close");
    char line[128];
    (void) snprintf(line, sizeof(line), "PDM capture samples=%" PRIu32 " complete=%" PRIu32 " errors=%" PRIu32
                    " overruns=%" PRIu32 " flags=0x%08" PRIx32 " timeout=%u\r\n",
                    capture.samples, capture.complete, capture.errors, capture.overruns, capture.flags,
                    (unsigned int) timed_out);
    bench_emit(line);
    const bool passed = start_ok && close_ok && !timed_out && (capture.complete == 1U) && (capture.errors == 0U) &&
                        (capture.flags == 0U) && capture.buffer_matches && (capture.samples == PDM_BENCH_SAMPLES) &&
                        pdm_report_pcm();
    bench_emit(passed ? "PDM PASS\r\n" : "PDM FAIL\r\n");
    return passed;
}
