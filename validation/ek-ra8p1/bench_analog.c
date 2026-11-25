#include "hal_data.h"

#include <inttypes.h>
#include <stdio.h>

void bench_emit(const char * text);
bool bench_analog(void);
void bench_analog_adc_callback(adc_callback_args_t * args);

enum
{
    ANALOG_LOW = 384,
    ANALOG_HIGH = 3712,
    ANALOG_ERROR_LIMIT = 82,
    ANALOG_REPEATS = 4,
    ANALOG_RAMP_INTERVALS = 32,
    ANALOG_RAMP_STEP = (ANALOG_HIGH - ANALOG_LOW) / ANALOG_RAMP_INTERVALS,
};

static volatile bool calibration_done;
static volatile bool scan_done;

typedef struct
{
    uint16_t min;
    uint16_t max;
    uint16_t mean;
    bool in_bounds;
} analog_point_t;

void bench_analog_adc_callback(adc_callback_args_t * args)
{
    if (ADC_EVENT_CALIBRATION_COMPLETE == args->event)
    {
        calibration_done = true;
    }
    if ((ADC_EVENT_SCAN_COMPLETE == args->event) && (ADC_GROUP_MASK_0 == args->group_mask))
    {
        scan_done = true;
    }
}

static bool analog_check(fsp_err_t err, const char * operation)
{
    if (FSP_SUCCESS == err)
    {
        return true;
    }
    char line[80];
    (void) snprintf(line, sizeof(line), "ANALOG FAIL %s err=%u\r\n", operation, (unsigned int) err);
    bench_emit(line);
    return false;
}

static bool analog_wait(volatile const bool * done, uint32_t timeout_ms, const char * operation)
{
    while (!*done && (timeout_ms > 0U))
    {
        R_BSP_SoftwareDelay(1U, BSP_DELAY_UNITS_MILLISECONDS);
        --timeout_ms;
    }
    return analog_check(*done ? FSP_SUCCESS : FSP_ERR_TIMEOUT, operation);
}

static bool analog_preflight(void)
{
    const uint32_t oscsf = R_SYSTEM->OSCSF;
    const uint32_t control = R_SYSTEM->ADCCKCR;
    const uint32_t divider = R_SYSTEM->ADCCKDIVCR;
    const uint32_t pclka = R_FSP_SystemClockHzGet(FSP_PRIV_CLOCK_PCLKA);
    const uint32_t hoco = R_BSP_SourceClockHzGet(BSP_CLOCKS_SOURCE_CLOCK_HOCO);
    char line[112];
    (void) snprintf(line, sizeof(line), "ANALOG clock OSCSF=%02" PRIx32 " ADCCKCR=%02" PRIx32
                    " ADCCKDIVCR=%02" PRIx32 " HOCO=%" PRIu32 " PCLKA=%" PRIu32 "\r\n",
                    oscsf, control, divider, hoco, pclka);
    bench_emit(line);

    /* HM 9.2.56: no ADC clock output while switching ready is set. */
    const uint32_t switch_mask = R_SYSTEM_ADCCKCR_ADCCKSREQ_Msk | R_SYSTEM_ADCCKCR_ADCCKSRDY_Msk;
    if (((control & switch_mask) != 0U) || ((control & R_SYSTEM_ADCCKCR_ADCCKSEL_Msk) != BSP_CLOCKS_SOURCE_CLOCK_HOCO) ||
        (divider != BSP_CLOCKS_ADC_CLOCK_DIV_1) || ((oscsf & R_SYSTEM_OSCSF_HOCOSF_Msk) == 0U) ||
        (hoco != 48000000U) || (pclka < hoco))
    {
        bench_emit("ANALOG FAIL clock requires stable 48 MHz ADCCLK and PCLKA >= ADCLK\r\n");
        return false;
    }

    /* HM 54.11.21 prohibits digital PORT0 outputs while sampling AN001. */
    const uint32_t digital = R_PFS_PORT_PIN_PmnPFS_PDR_Msk | R_PFS_PORT_PIN_PmnPFS_PMR_Msk;
    for (unsigned int pin = 0U; pin < 16U; ++pin)
    {
        const uint32_t pfs = R_PFS->PORT[0].PIN[pin].PmnPFS;
        const bool loopback_pin = (pin == 1U) || (pin == 14U);
        const uint32_t analog_mask = R_PFS_PORT_PIN_PmnPFS_ASEL_Msk | R_PFS_PORT_PIN_PmnPFS_PCR_Msk |
                                     R_PFS_PORT_PIN_PmnPFS_ISEL_Msk;
        if (((pfs & digital) != 0U) || (loopback_pin && ((pfs & analog_mask) != R_PFS_PORT_PIN_PmnPFS_ASEL_Msk)))
        {
            (void) snprintf(line, sizeof(line), "ANALOG FAIL P0%02u PFS=%08" PRIx32 "\r\n", pin, pfs);
            bench_emit(line);
            return false;
        }
    }
    return true;
}

static bool analog_sample(const char * phase, unsigned int index, uint16_t command, analog_point_t * point)
{
    if (!analog_check(g_analog_dac.p_api->write(g_analog_dac.p_ctrl, command), "DAC write"))
    {
        return false;
    }
    R_BSP_SoftwareDelay(30U, BSP_DELAY_UNITS_MILLISECONDS);

    /* Equal board references: DAC VREFH * D/4096 maps to ADC0 code D. */
    const int expected = (int) command;
    uint16_t raw[ANALOG_REPEATS];
    int error[ANALOG_REPEATS];
    unsigned int sum = 0U;
    point->min = UINT16_MAX;
    point->max = 0U;
    point->in_bounds = true;
    for (unsigned int i = 0U; i < ANALOG_REPEATS; ++i)
    {
        scan_done = false;
        if (!analog_check(g_analog_adc.p_api->scanGroupStart(g_analog_adc.p_ctrl, ADC_GROUP_MASK_0), "ADC trigger") ||
            !analog_wait(&scan_done, 20U, "ADC scan") ||
            !analog_check(g_analog_adc.p_api->read(g_analog_adc.p_ctrl, ADC_CHANNEL_1, &raw[i]), "ADC read AN001"))
        {
            return false;
        }
        error[i] = (int) raw[i] - expected;
        point->in_bounds = point->in_bounds && (raw[i] <= 4095U) &&
                           (error[i] >= -ANALOG_ERROR_LIMIT) && (error[i] <= ANALOG_ERROR_LIMIT);
        if (raw[i] < point->min)
        {
            point->min = raw[i];
        }
        if (raw[i] > point->max)
        {
            point->max = raw[i];
        }
        sum += raw[i];
        /* HM 54.11: allow at least six PCLKA cycles before retriggering the same group. */
        R_BSP_SoftwareDelay(1U, BSP_DELAY_UNITS_MICROSECONDS);
    }
    point->mean = (uint16_t) ((sum + (ANALOG_REPEATS / 2U)) / ANALOG_REPEATS);
    char line[192];
    (void) snprintf(line, sizeof(line), "ANALOG %s i=%u dac=%u exp=%d raw=%u,%u,%u,%u err=%d,%d,%d,%d"
                    " mean=%u min=%u max=%u bound=%s\r\n", phase, index, (unsigned int) command, expected,
                    (unsigned int) raw[0], (unsigned int) raw[1], (unsigned int) raw[2], (unsigned int) raw[3],
                    error[0], error[1], error[2], error[3], (unsigned int) point->mean,
                    (unsigned int) point->min, (unsigned int) point->max, point->in_bounds ? "ok" : "FAIL");
    bench_emit(line);
    return true;
}

static bool analog_measure(void)
{
    static const uint16_t levels[] = {ANALOG_LOW, 1024U, 2048U, 3072U, ANALOG_HIGH};
    analog_point_t point;
    bool bounded = true;
    for (unsigned int i = 0U; i < (sizeof(levels) / sizeof(levels[0])); ++i)
    {
        if (!analog_sample("level", i, levels[i], &point))
        {
            return false;
        }
        bounded = bounded && point.in_bounds;
    }

    uint16_t first = 0U;
    uint16_t previous = 0U;
    uint16_t min = UINT16_MAX;
    uint16_t max = 0U;
    unsigned int non_increasing = 0U;
    for (unsigned int i = 0U; i <= ANALOG_RAMP_INTERVALS; ++i)
    {
        const uint16_t command = (uint16_t) (ANALOG_LOW + (i * ANALOG_RAMP_STEP));
        if (!analog_sample("ramp", i, command, &point))
        {
            return false;
        }
        bounded = bounded && point.in_bounds;
        if (i == 0U)
        {
            first = point.mean;
        }
        else if (point.mean <= previous)
        {
            ++non_increasing;
        }
        previous = point.mean;
        if (point.min < min)
        {
            min = point.min;
        }
        if (point.max > max)
        {
            max = point.max;
        }
    }
    char line[128];
    (void) snprintf(line, sizeof(line), "ANALOG ramp min=%u max=%u first=%u last=%u non_increasing=%u\r\n",
                    (unsigned int) min, (unsigned int) max, (unsigned int) first, (unsigned int) previous,
                    non_increasing);
    bench_emit(line);
    return bounded && (non_increasing == 0U);
}

bool bench_analog(void)
{
    bool passed = false;
    if (analog_preflight() && analog_check(g_analog_adc.p_api->open(g_analog_adc.p_ctrl, g_analog_adc.p_cfg), "ADC open"))
    {
        calibration_done = false;
        if (analog_check(g_analog_adc.p_api->scanCfg(g_analog_adc.p_ctrl, g_analog_adc.p_channel_cfg), "ADC ScanCfg") &&
            analog_check(g_analog_adc.p_api->calibrate(g_analog_adc.p_ctrl, NULL), "ADC calibrate") &&
            analog_wait(&calibration_done, 500U, "ADC calibration") &&
            analog_check(g_analog_dac.p_api->open(g_analog_dac.p_ctrl, g_analog_dac.p_cfg), "DAC open"))
        {
            passed = analog_check(g_analog_dac.p_api->write(g_analog_dac.p_ctrl, ANALOG_LOW), "DAC prime") &&
                     analog_check(g_analog_dac.p_api->start(g_analog_dac.p_ctrl), "DAC start") && analog_measure();
            const bool dac_stopped = analog_check(g_analog_dac.p_api->stop(g_analog_dac.p_ctrl), "DAC stop");
            const bool dac_closed = analog_check(g_analog_dac.p_api->close(g_analog_dac.p_ctrl), "DAC close");
            passed = passed && dac_stopped && dac_closed;
        }
        const bool adc_closed = analog_check(g_analog_adc.p_api->close(g_analog_adc.p_ctrl), "ADC close");
        passed = passed && adc_closed;
    }
    bench_emit(passed ? "ANALOG PASS\r\n" : "ANALOG FAIL\r\n");
    return passed;
}
