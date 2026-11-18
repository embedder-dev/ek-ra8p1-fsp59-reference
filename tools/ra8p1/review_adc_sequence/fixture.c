/* Independent oracles: HM54.3.8 p3421, 54.3.16.6 p3438,
 * 54.6.4.2 p3476, A3.2 p4290, 54.11.16 p3496. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "r_adc_b.h"
#include REVIEW_SOURCE

R_ADC_B0_Type g_acquisition_adc;
acquisition_tsn_t g_acquisition_tsn;
struct st_acquisition_cal g_acquisition_cal;
acquisition_system_t g_acquisition_system;
review_system_t g_review_system;
static adc_b_instance_ctrl_t ctrl;
static adc_cfg_t cfg;
static adc_b_extended_cfg_t ext;
static unsigned waits, clears, callbacks, reads;
static bool restart;
static unsigned locked;
void review_adc_lock(void) { assert(locked == 0U); locked++; }
void review_adc_unlock(void) { assert(locked == 1U); locked--; }
static uint32_t pclka = 120000000U;
static uint32_t async_hz = 180000000U;
uint32_t R_FSP_SystemClockHzGet(uint32_t clock) { assert(clock == 12U); return pclka; }
uint32_t R_BSP_SourceClockHzGet(fsp_priv_source_clock_t source)
{ assert(source == 5U); return async_hz * 6U; }
void review_adc_read(volatile uint32_t * reg) { assert(reg == &R_ADC_B->ADSR); reads++; }
void acquisition_adc_wait(volatile uint32_t * reg, uint32_t expected)
{ assert(reg == &R_ADC_B->ADSR && expected == 0U); *reg = 0; waits++; }
void acquisition_adc_module(bool start, uint32_t ip, uint32_t channel)
{ (void) start; (void) ip; (void) channel; }
void R_BSP_IrqCfgEnable(IRQn_Type irq, uint8_t ipl, void * context)
{ (void) irq; (void) ipl; (void) context; }
void R_BSP_IrqDisable(IRQn_Type irq) { (void) irq; }
void R_BSP_IrqStatusClear(IRQn_Type irq) { assert(irq == 12); clears++; }
void * R_FSP_IsrContextGet(IRQn_Type irq) { assert(irq == 12); return &ctrl; }
void R_FSP_IsrContextSet(IRQn_Type irq, void * context) { (void) irq; (void) context; }
IRQn_Type R_FSP_CurrentIrqGet(void) { return 12; }
void R_BSP_SoftwareDelay(uint32_t delay, uint32_t units) { (void) delay; (void) units; }
static void callback(adc_callback_args_t * args)
{
    assert(locked == 0U);
    callbacks++;
    if (args->event == ADC_EVENT_CALIBRATION_COMPLETE)
    {
        assert(waits >= 1U && clears >= 1U);
        assert(R_ADC_B->ADSR == 0U && R_ADC_B->ADCALSTR == 0U);
        assert(R_ADC_B->ADSYCR == ext.sync_operation_control);
        assert(ctrl.adc_state == ADC_B_CONVERTER_STATE_READY);
        if (restart)
        {
            assert(R_ADC_B_ScanStart(&ctrl) == FSP_SUCCESS);
            R_ADC_B->ADSR = 1U;
            R_ADC_B->ADCALSTR = 0xBEEFU;
        }
    }
    else
    {
        assert(ctrl.adc_state == ADC_B_CONVERTER_STATE_CALIBRATION_FAIL);
    }
}
static void setup(void)
{
    memset(&g_acquisition_adc, 0, sizeof(g_acquisition_adc));
    memset(&ctrl, 0, sizeof(ctrl)); memset(&cfg, 0, sizeof(cfg)); memset(&ext, 0, sizeof(ext));
    cfg.p_extend = &ext; ctrl.p_cfg = &cfg;
    ctrl.opened = ctrl.initialized = 0x41444348U;
    ctrl.p_callback = callback;
    ext.sync_operation_control = 0x30005U;
    ext.conversion_state = 5U | (7U << 8U);
    ext.calibration_adc_state = 95U | (9U << 16U);
    ext.sample_and_hold_config_012 = 20U | (2U << 16U);
    ext.sample_and_hold_config_456 = 40U | (4U << 16U);
    ext.sample_and_hold_enable_mask = 0x11U;
    ext.adc_filter_selection[0].bits = ext.adc_filter_selection[1].bits = 0x01010101U;
    g_review_system.ADCCKCR = g_review_system.GPTCKCR = 5U;
    g_review_system.ADCCKDIVCR = g_review_system.GPTCKDIVCR = 3U;
    callbacks = waits = clears = reads = 0U;
}
static void clock_test(unsigned source, unsigned divide, bool sync)
{
    setup();
    ext.clock_control_bits.source_selection = source;
    ext.clock_control_bits.divider = divide;
    if (sync) { ext.sync_operation_control &= ~(1U << 17U); }
    ext.start_trigger_delay_table[0] = 1U;
    ext.start_trigger_delay_table[8] = 200U;
    adc_b_group_cfg_t group = {.scan_group_id = 8, .converter_selection = ADC_B_UNIT_ID_1};
    adc_b_group_cfg_t * groups[] = {&group};
    adc_b_scan_cfg_t scan = {.group_count = 1, .p_adc_groups = groups};
    ctrl.cached_adtrgenr = 1U << 8;
    adc_b_calculate_wait_time(&ctrl, &scan);
    /* HM54.6.4.2: floor(Twait * PCLKA / 2) + 1; no configuration ordinal. */
    uint64_t cycles = 200U + (sync ? 10U : 4U);
    uint32_t input = source == 2U ? pclka : async_hz;
    unsigned expected = (unsigned) (cycles * pclka * (divide + 1U) / (2ULL * input)) + 1U;
    assert(ctrl.trigger_disable_wait_cycles == expected);
    assert(R_ADC_B_ScanStop(&ctrl) == FSP_SUCCESS);
    assert(reads == expected);
}
static void calibration_settings(void)
{
    setup();
    assert(adc_b_update_calibrate_state(&ctrl) == 3U);
    assert(R_ADC_B->ADCALSTCR == (95U | (5U << 16U)));
    assert(adc_b_update_calibrate_state(&ctrl) == 0x300U);
    assert(R_ADC_B->ADCALSTCR == (95U | (7U << 16U)));
    assert(adc_b_update_calibrate_state(&ctrl) == 4U);
    assert(R_ADC_B->ADCALSTCR == (95U | (5U << 16U)));
    assert(R_ADC_B->ADCALSHCR == (21U | (2U << 16U)));
    assert(adc_b_update_calibrate_state(&ctrl) == 0x400U);
    assert(R_ADC_B->ADCALSTCR == (95U | (7U << 16U)));
    assert(R_ADC_B->ADCALSHCR == (41U | (4U << 16U)));
}
static void synchronized_calibration(void)
{
    setup(); restart = false;
    ext.clock_control_bits.source_selection = ADC_B_CLOCK_SOURCE_PCLKA;
    ext.clock_control_bits.divider = ADC_B_CLOCK_DIV_4;
    ext.sync_operation_control = 10U;
    ext.conversion_state = 0x505U;
    ext.sample_and_hold_enable_mask = 1U;
    ext.sample_and_hold_config_012 = 5U | (5U << 16U);
    ext.sampling_state_table[0] = 5U;
    adc_b_virtual_channel_cfg_t channel = {.channel_id = 0, .channel_cfg = 1U,
                                          .channel_control_c = 1U << 20U};
    adc_b_virtual_channel_cfg_t * channels[] = {&channel};
    adc_b_group_cfg_t group = {.scan_group_id = 0, .converter_selection = ADC_B_UNIT_ID_0,
        .virtual_channel_count = 1, .p_virtual_channels = channels};
    adc_b_group_cfg_t * groups[] = {&group};
    adc_b_scan_cfg_t scan = {.group_count = 1, .p_adc_groups = groups};
    assert(R_ADC_B_ScanCfg(&ctrl, &scan) == FSP_SUCCESS);
    R_ADC_B->ADSYCR = 10U;
    assert(R_ADC_B_Calibrate(&ctrl, NULL) == FSP_SUCCESS);
    assert(R_ADC_B->ADSYCR == 0x3000AU && R_ADC_B->ADCALSTR == 3U);
    adc_b_calend0_isr();
    assert(R_ADC_B->ADSYCR == 0x3000AU && R_ADC_B->ADCALSTR == 0x300U);
    adc_b_calend1_isr();
    assert(R_ADC_B->ADSYCR == 0x3000AU && R_ADC_B->ADCALSTR == 4U);
    assert(R_ADC_B->ADCALSHCR == (6U | (5U << 16U)));
    adc_b_calend0_isr();
    assert(R_ADC_B->ADSYCR == 10U && R_ADC_B->ADCALSTR == 0U);
    assert(callbacks == 1U && waits == 3U && clears == 3U);
}
static void final_callback(unsigned unit)
{
    setup(); restart = true;
    ctrl.adc_state = ADC_B_CONVERTER_STATE_SH_4_6_CALIBRATING;
    ctrl.cached_adsystr = 1U;
    R_ADC_B->ADCALSTR = 0x400U;
    R_ADC_B->ADSR = 1U << (16U + unit);
    if (unit) { adc_b_calend1_isr(); } else { adc_b_calend0_isr(); }
    assert(callbacks == 1U && waits == 1U && clears == 1U);
    assert(R_ADC_B->ADSR == 1U && R_ADC_B->ADCALSTR == 0xBEEFU);
}
static void sticky_failure(unsigned unit, bool overflow, bool enable)
{
    setup(); if (!enable) { ctrl.p_callback = NULL; }
    ctrl.adc_state = unit ? ADC_B_CONVERTER_STATE_ADC_1_CALIBRATING : ADC_B_CONVERTER_STATE_ADC_0_CALIBRATING;
    if (overflow)
    {
        R_ADC_B->ADOVFERSR = 1U << unit;
        if (unit) { adc_b_resovf1_isr(); } else { adc_b_resovf0_isr(); }
        R_ADC_B->ADOVFERSR = 0U;
    }
    else
    {
        R_ADC_B->ADERSR = 1U << unit;
        if (unit) { adc_b_err1_isr(); } else { adc_b_err0_isr(); }
        R_ADC_B->ADERSR = 0U;
    }
    assert(ctrl.adc_state == ADC_B_CONVERTER_STATE_CALIBRATION_FAIL);
    R_ADC_B->ADCALSTR = 0xDEADU;
    if (unit) { adc_b_calend1_isr(); } else { adc_b_calend0_isr(); }
    assert(ctrl.adc_state == ADC_B_CONVERTER_STATE_CALIBRATION_FAIL);
    assert(callbacks == (enable ? 1U : 0U));
    assert(R_ADC_B->ADCALSTR == 0U && R_ADC_B->ADSYCR == ext.sync_operation_control);
}
static void sample_hold_mode(void)
{
    setup();
    /* ADCHCR: SGSEL=1, CNVCS=0/6, AINMD=1; S&H0 and S&H4. */
    R_ADC_B->ADCHCR0 = 1U | (1U << 15U);
    R_ADC_B->ADCHCR1 = 1U | (6U << 8U) | (1U << 15U);
    ctrl.adc_state = ADC_B_CONVERTER_STATE_ADC_1_CALIBRATING;
    assert(adc_b_update_calibrate_state(&ctrl) == 4U);
    assert(R_ADC_B->ADSHCR0 == 0x10001U && R_ADC_B->ADSHCR1 == 0x10001U);
}
#if ADC_B_CFG_PARAM_CHECKING_ENABLE
static void filter_settings(unsigned unit, unsigned filter)
{
    setup();
    adc_b_isr_cfg_t irqs = {.calibration_end_irq_adc_0 = 0, .calibration_end_irq_adc_1 = 1};
    ext.p_isr_cfg = &irqs;
    assert(adc_b_open_variant_check(&cfg) == FSP_SUCCESS);
    ext.adc_filter_selection[unit].bits &= ~(3U << (filter * 8U));
    ext.adc_filter_selection[unit].bits |= 2U << (filter * 8U);
    assert(adc_b_open_variant_check(&cfg) == FSP_ERR_INVALID_ARGUMENT);
}
static void admission(unsigned which)
{
    setup();
    adc_b_virtual_channel_cfg_t channels[4] = {0};
    adc_b_virtual_channel_cfg_t * pointers[] = {&channels[0], &channels[1], &channels[2], &channels[3]};
    adc_b_group_cfg_t group = {.scan_group_id = 7, .converter_selection = ADC_B_UNIT_ID_0,
                              .virtual_channel_count = 2, .p_virtual_channels = pointers};
    adc_b_group_cfg_t * groups[] = {&group};
    adc_b_scan_cfg_t scan = {.group_count = 1, .p_adc_groups = groups};
    channels[0].channel_id = 10; channels[1].channel_id = 2;
    channels[0].channel_cfg_bits.channel = 0; channels[1].channel_cfg_bits.channel = 2;
    if (which == 0U) /* S&H is array-first but hardware-last: must reject. */
    { assert(adc_b_scan_variant_check(&ext, &scan) == FSP_ERR_INVALID_ARGUMENT); return; }
    if (which == 1U) /* Reverse array order is legal if hardware S&H is first. */
    { channels[0].channel_id = 2; channels[1].channel_id = 10;
      assert(adc_b_scan_variant_check(&ext, &scan) == FSP_SUCCESS); return; }
    if (which == 2U) /* Conflicting AINMD for the same S&H circuit. */
    { channels[0].channel_cfg_bits.differential = 1; channels[1].channel_cfg_bits.channel = 1;
      assert(adc_b_scan_variant_check(&ext, &scan) == FSP_ERR_INVALID_ARGUMENT); return; }
    ext.sample_and_hold_enable_mask = 0;
    ext.adc_b_converter_mode[0].method = ADC_B_CONVERSION_METHOD_HYBRID;
    channels[0].channel_control_a_bits.digital_filter_id = 1;
    channels[1].channel_control_a_bits.digital_filter_id = 2;
    if (which == 3U) { group.virtual_channel_count = 1; }
    if (which == 4U) { channels[1].channel_control_a_bits.digital_filter_id = 0; }
    if (which == 5U) { channels[1].channel_control_a_bits.digital_filter_id = 1; }
    if (which == 6U) { ext.adc_filter_selection[0].bits = 0x01010201U; }
    assert(adc_b_scan_variant_check(&ext, &scan) == (which == 7U ? FSP_SUCCESS : FSP_ERR_INVALID_ARGUMENT));
}
#endif
int main(int argc, char ** argv)
{
    assert(argc >= 2);
    unsigned value = argc > 2 ? (unsigned) atoi(argv[2]) : 0U;
    switch (argv[1][0])
    {
        case 'w': clock_test(value, (unsigned) atoi(argv[3]), atoi(argv[4]) != 0); break;
        case 'c': calibration_settings(); break;
        case 'r': final_callback(value); break;
        case 'e': sticky_failure(value, atoi(argv[3]) != 0, atoi(argv[4]) != 0); break;
        case 's': sample_hold_mode(); break;
        case 'y': synchronized_calibration(); break;
#if ADC_B_CFG_PARAM_CHECKING_ENABLE
        case 'a': admission(value); break;
        case 'f': filter_settings(value, (unsigned) atoi(argv[3])); break;
#endif
        default: abort();
    }
    puts("ADC sequence oracle passed");
    return 0;
}
