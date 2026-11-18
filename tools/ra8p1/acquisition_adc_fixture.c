/* Host execution of production ADC_B, including its real calibration and scan/error ISRs. */
#include <stdio.h>
#include <string.h>
#include "r_adc_b.h"

R_ADC_B0_Type g_acquisition_adc;
acquisition_tsn_t g_acquisition_tsn;
struct st_acquisition_cal g_acquisition_cal;
acquisition_system_t g_acquisition_system;
_Static_assert(ADC_B_VIRTUAL_CHANNEL_COUNT == 33, "ADC16H virtual channel count");
_Static_assert(ADC_B_CLOCK_SOURCE_ADCCLK == 0, "ADC16H ADCCLK selector");
_Static_assert(ADC_CHANNEL_LAST_EXTERNAL == 22, "ADC16H physical channel count");
_Static_assert(ADC_CHANNEL_TEMPERATURE == 0x64, "ADC16H temperature channel encoding");
_Static_assert(ADC_CHANNEL_VOLT == 0x65, "ADC16H reference channel encoding");
_Static_assert(ADC_CHANNEL_LAST_INTERNAL == 0x76, "ADC16H last diagnosis channel");
_Static_assert(ADC_B_CHANNEL_MASK_TEMPERATURE == (1ULL << 36), "ADC16H extended channel mask");
static void * g_context[64];
static unsigned g_cleared[64];
static IRQn_Type g_irq;
static unsigned g_callbacks;
static adc_callback_args_t g_callback;

void acquisition_adc_wait(volatile uint32_t * reg, uint32_t expected)
{
    if (reg == &R_ADC_B->ADCLKSR) { *reg = R_ADC_B->ADCLKENR; }
    assert(*reg == expected);
}
void acquisition_adc_module(bool start, uint32_t ip, uint32_t channel)
{ (void) start; (void) ip; assert(channel == 0U); }
void R_BSP_IrqCfgEnable(IRQn_Type irq, uint8_t ipl, void * ctx)
{ assert(irq >= 0 && irq < 64 && ipl == 12U); g_context[irq] = ctx; }
void R_BSP_IrqDisable(IRQn_Type irq) { assert(irq >= 0 && irq < 64); }
void R_BSP_IrqStatusClear(IRQn_Type irq) { assert(irq >= 0 && irq < 64); g_cleared[irq]++; }
void * R_FSP_IsrContextGet(IRQn_Type irq) { return g_context[irq]; }
void R_FSP_IsrContextSet(IRQn_Type irq, void * ctx) { g_context[irq] = ctx; }
IRQn_Type R_FSP_CurrentIrqGet(void) { return g_irq; }
void R_BSP_SoftwareDelay(uint32_t delay, uint32_t units) { (void) delay; (void) units; }
uint32_t R_FSP_SystemClockHzGet(uint32_t clock)
{
    assert(clock == FSP_PRIV_CLOCK_PCLKA);
    return 120000000U;
}
uint32_t R_BSP_SourceClockHzGet(fsp_priv_source_clock_t source)
{
    assert(source == 0U);
    return 50000000U;
}
void adc_b_calend0_isr(void);
void adc_b_calend1_isr(void);
void adc_b_adi0_isr(void);
void adc_b_err0_isr(void);

static void callback(adc_callback_args_t * args) { g_callback = *args; g_callbacks++; }

static void setup(adc_b_extended_cfg_t * ext, adc_b_isr_cfg_t * isr, adc_cfg_t * cfg)
{
    memset(&g_acquisition_adc, 0, sizeof(g_acquisition_adc));
    memset(g_context, 0, sizeof(g_context));
    memset(g_cleared, 0, sizeof(g_cleared));
    memset(ext, 0, sizeof(*ext));
    memset(isr, 0xFF, sizeof(*isr));
    memset(cfg, 0, sizeof(*cfg));
    isr->calibration_end_irq_adc_0 = 0;
    isr->calibration_end_irq_adc_1 = 1;
    isr->scan_end_irq_group_0 = 2;
    isr->conversion_error_irq_adc_0 = 3;
    isr->calibration_end_ipl_adc_0 = 12;
    isr->calibration_end_ipl_adc_1 = 12;
    isr->scan_end_ipl_group_0 = 12;
    isr->conversion_error_ipl_adc_0 = 12;
    ext->p_isr_cfg = isr;
    ext->sync_operation_control = 0x30064U;
    ext->calibration_adc_state = 95U | (5U << 16);
    ext->calibration_sample_and_hold = 95U | (5U << 16);
    ext->conversion_state = (5U << R_ADC_B0_ADCNVSTR_CST0_Pos) | (5U << R_ADC_B0_ADCNVSTR_CST1_Pos);
    for (unsigned i = 0; i < 8; i++) { ext->user_gain_tables[i] = 0x4000U; }
    cfg->p_extend = ext;
    cfg->p_callback = callback;
    cfg->p_context = &g_callbacks;
    g_callbacks = 0U;
}

static adc_b_scan_cfg_t scan_config(adc_b_virtual_channel_cfg_t * vc, adc_b_group_cfg_t * group,
                                  adc_b_virtual_channel_cfg_t ** vcs, adc_b_group_cfg_t ** groups)
{
    memset(vc, 0, sizeof(*vc));
    vc->channel_control_c_bits.data_is_unsigned = 1U;
    memset(group, 0, sizeof(*group));
    vcs[0] = vc;
    groups[0] = group;
    group->p_virtual_channels = vcs;
    group->virtual_channel_count = 1;
    group->scan_end_interrupt_enable = true;
    adc_b_scan_cfg_t scan = {.group_count = 1U, .p_adc_groups = groups};
    return scan;
}

static void lifecycle_and_calibration(void)
{
    adc_b_extended_cfg_t ext;
    adc_b_isr_cfg_t isr;
    adc_cfg_t cfg;
    adc_b_instance_ctrl_t ctrl = {0};
    setup(&ext, &isr, &cfg);
    ext.user_offset_tables[0] = -1;
    ext.group_priority_enable = 3;
    ext.adc_b_converter_mode[1].mode = ADC_B_CONVERTER_MODE_CONTINUOUS_SCAN;
    ext.sample_and_hold_enable_mask = ADC_B_SAMPLE_AND_HOLD_MASK_UNIT_0 | ADC_B_SAMPLE_AND_HOLD_MASK_UNIT_4;
    assert(FSP_SUCCESS == g_adc_on_adc_b.open(&ctrl, &cfg));
    assert(R_ADC_B->ADGSPCR == 0xF07U);
    assert(R_ADC_B->ADUOFTR0 == 0xFFFFU && R_ADC_B->ADUGTR0 == 0x4000U);
    assert(R_ADC_B0_ADUGTR_UGAIN_INTEGER_Pos == 14);
    adc_b_virtual_channel_cfg_t vc, *vcs[1];
    adc_b_group_cfg_t group, *groups[1];
    adc_b_scan_cfg_t scan = scan_config(&vc, &group, vcs, groups);
    vc.channel_id = ADC_B_VIRTUAL_CHANNEL_32;
    assert(FSP_SUCCESS == R_ADC_B_ScanCfg(&ctrl, &scan));
#if ADC_B_CFG_PARAM_CHECKING_ENABLE
    assert(FSP_ERR_INVALID_STATE == R_ADC_B_ScanStart(&ctrl));
#endif
    assert(FSP_SUCCESS == R_ADC_B_Calibrate(&ctrl, NULL));
    assert(R_ADC_B->ADCALSTR == 0x3U);
    g_irq = 0; adc_b_calend0_isr();
    assert(R_ADC_B->ADCALSTR == 0x300U && g_callbacks == 0U);
    g_irq = 1; adc_b_calend1_isr();
    assert(R_ADC_B->ADCALSTR == 0x4U && g_callbacks == 0U);
    g_irq = 0; adc_b_calend0_isr();
    assert(R_ADC_B->ADCALSTR == 0x400U && g_callbacks == 0U);
    g_irq = 1; adc_b_calend1_isr();
    assert(R_ADC_B->ADCALSTR == 0U && g_callbacks == 1U);
    assert(ctrl.adc_state == ADC_B_CONVERTER_STATE_READY);
    assert(g_callback.event == ADC_EVENT_CALIBRATION_COMPLETE);
    assert(FSP_SUCCESS == R_ADC_B_ScanStart(&ctrl));
    assert(R_ADC_B->ADSYSTR == 1U);
    R_ADC_B->ADSYSTR = 0U;
    g_irq = 2; adc_b_adi0_isr();
    assert(g_callbacks == 2U && g_callback.event == ADC_EVENT_SCAN_COMPLETE);
    g_irq = 3; adc_b_err0_isr();
    assert(g_callbacks == 3U && (g_callback.event & ADC_EVENT_CONVERSION_ERROR));
    assert(g_callback.p_context == &g_callbacks && g_cleared[3] == 1U);
    assert(FSP_SUCCESS == R_ADC_B_Close(&ctrl));
}

static void calibration_skip_and_failure(void)
{
    adc_b_extended_cfg_t ext;
    adc_b_isr_cfg_t isr;
    adc_cfg_t cfg;
    adc_b_instance_ctrl_t ctrl = {0};
    setup(&ext, &isr, &cfg);
    assert(FSP_SUCCESS == R_ADC_B_Open(&ctrl, &cfg));
    assert(FSP_SUCCESS == R_ADC_B_Calibrate(&ctrl, NULL));
    g_irq = 0; adc_b_calend0_isr();
    assert(R_ADC_B->ADCALSTR == 0x300U && g_callbacks == 0U);
    g_irq = 1; adc_b_calend1_isr();
    assert(ctrl.adc_state == ADC_B_CONVERTER_STATE_READY && g_callbacks == 1U);
    assert(FSP_SUCCESS == R_ADC_B_Calibrate(&ctrl, NULL));
    R_ADC_B->ADERSR = 1U;
    g_irq = 0; adc_b_calend0_isr();
    assert(ctrl.adc_state == ADC_B_CONVERTER_STATE_CALIBRATION_FAIL);
    assert(R_ADC_B->ADCALSTR == 0U && g_callbacks == 2U);
    assert(g_callback.event & ADC_EVENT_CONVERSION_ERROR);
    R_ADC_B->ADERSR = 0U;
    assert(FSP_SUCCESS == R_ADC_B_Close(&ctrl));
}

#if ADC_B_CFG_PARAM_CHECKING_ENABLE
static void validation_and_erratum(void)
{
    adc_b_extended_cfg_t ext;
    adc_b_isr_cfg_t isr;
    adc_cfg_t cfg;
    adc_b_instance_ctrl_t ctrl = {0};
    setup(&ext, &isr, &cfg);
    ext.clock_control_bits.divider = ADC_B_CLOCK_DIV_6;
    assert(FSP_ERR_INVALID_ARGUMENT == R_ADC_B_Open(&ctrl, &cfg));
    ext.clock_control_bits.divider = ADC_B_CLOCK_DIV_1;
    ext.sync_operation_control_bits.period_cycle = 4U;
    assert(FSP_ERR_INVALID_ARGUMENT == R_ADC_B_Open(&ctrl, &cfg));
    ext.sync_operation_control_bits.period_cycle = 256U;
    assert(FSP_ERR_INVALID_ARGUMENT == R_ADC_B_Open(&ctrl, &cfg));
    ext.sync_operation_control_bits.period_cycle = 100U;
    ext.user_gain_tables[0] = 0x10000U;
    assert(FSP_ERR_INVALID_ARGUMENT == R_ADC_B_Open(&ctrl, &cfg));
    ext.user_gain_tables[0] = 0x4000U;
    ext.group_priority_enable = 1U;
    ext.adc_b_converter_mode[0].method = ADC_B_CONVERSION_METHOD_HYBRID;
    assert(FSP_ERR_INVALID_MODE == R_ADC_B_Open(&ctrl, &cfg));
    ext.adc_b_converter_mode[0].method = ADC_B_CONVERSION_METHOD_SAR;
    ext.single_ended_overflow_strict = true;
    assert(FSP_SUCCESS == R_ADC_B_Open(&ctrl, &cfg));
    adc_b_virtual_channel_cfg_t vc, *vcs[1];
    adc_b_group_cfg_t group, *groups[1];
    adc_b_scan_cfg_t scan = scan_config(&vc, &group, vcs, groups);
    vc.channel_id = (adc_b_virtual_channel_t)33;
    assert(FSP_ERR_INVALID_CHANNEL == R_ADC_B_ScanCfg(&ctrl, &scan));
    vc.channel_id = ADC_B_VIRTUAL_CHANNEL_32;
    vc.channel_control_b_bits.addition_average_mode = ADC_B_ADD_AVERAGE_AVERAGE_ENABLE;
    assert(FSP_ERR_INVALID_ARGUMENT == R_ADC_B_ScanCfg(&ctrl, &scan));
    vc.channel_cfg_bits.differential = 1U;
    vc.channel_control_c_bits.data_is_unsigned = 0U;
    assert(FSP_SUCCESS == R_ADC_B_ScanCfg(&ctrl, &scan));
    vc.channel_cfg_bits.differential = 0U;
    vc.channel_control_c_bits.data_is_unsigned = 1U;
    vc.channel_control_b_bits.addition_average_mode = 0U;
    vc.channel_control_a_bits.offset_table_id = 1U;
    ext.user_offset_tables[0] = -2;
    assert(FSP_ERR_INVALID_ARGUMENT == R_ADC_B_ScanCfg(&ctrl, &scan));
    ext.user_offset_tables[0] = 0;
    assert(FSP_SUCCESS == R_ADC_B_ScanCfg(&ctrl, &scan));
    assert(FSP_SUCCESS == R_ADC_B_Close(&ctrl));
}

static void synchronous_sampling_table(void)
{
    adc_b_extended_cfg_t ext;
    adc_b_isr_cfg_t isr;
    adc_cfg_t cfg;
    adc_b_instance_ctrl_t ctrl = {0};
    setup(&ext, &isr, &cfg);
    ext.sync_operation_control = 10U;
    ext.calibration_adc_state = 15U | (5U << 16);
    /* HM54.2.4.10 requires equal CST for the two converters. */
    ext.conversion_state = (5U << R_ADC_B0_ADCNVSTR_CST0_Pos) | (5U << R_ADC_B0_ADCNVSTR_CST1_Pos);
    ext.sampling_state_table[15] = 15U;
    assert(FSP_SUCCESS == R_ADC_B_Open(&ctrl, &cfg));
    adc_b_virtual_channel_cfg_t vc, *vcs[1];
    adc_b_group_cfg_t group, *groups[1];
    adc_b_scan_cfg_t scan = scan_config(&vc, &group, vcs, groups);
    vc.channel_id = ADC_B_VIRTUAL_CHANNEL_32;
    vc.channel_cfg_bits.sample_table_id = 15U;
    assert(FSP_SUCCESS == R_ADC_B_ScanCfg(&ctrl, &scan));
    ext.sampling_state_table[15] = 14U;
    assert(FSP_ERR_INVALID_STATE == R_ADC_B_ScanCfg(&ctrl, &scan));
    group.converter_selection = ADC_B_UNIT_ID_1;
    vc.channel_cfg_bits.channel = ADC_CHANNEL_6;
    ext.converter_selection_0 = 1U;
    ext.sampling_state_table[15] = 13U;
    assert(FSP_ERR_INVALID_STATE == R_ADC_B_ScanCfg(&ctrl, &scan));
    ext.sampling_state_table[15] = 15U;
    assert(FSP_SUCCESS == R_ADC_B_ScanCfg(&ctrl, &scan));
    assert(FSP_SUCCESS == R_ADC_B_Close(&ctrl));
}

static void temperature_latch_protection(void)
{
    adc_b_extended_cfg_t ext;
    adc_b_isr_cfg_t isr;
    adc_cfg_t cfg;
    adc_b_instance_ctrl_t ctrl = {0};
    setup(&ext, &isr, &cfg);
    memset(&g_acquisition_system, 0, sizeof(g_acquisition_system));
    memset(&g_acquisition_tsn, 0, sizeof(g_acquisition_tsn));
    g_acquisition_system.PRCR_S = 0x11U;
    assert(FSP_SUCCESS == R_ADC_B_Open(&ctrl, &cfg));
    adc_b_virtual_channel_cfg_t vc, *vcs[1];
    adc_b_group_cfg_t group, *groups[1];
    adc_b_scan_cfg_t scan = scan_config(&vc, &group, vcs, groups);
    vc.channel_cfg_bits.channel = ADC_CHANNEL_TEMPERATURE;
    assert(FSP_SUCCESS == R_ADC_B_ScanCfg(&ctrl, &scan));
    assert(g_acquisition_system.PRCR_S == 0xA511U);
    assert(g_acquisition_system.TEMPRLR_b.LOCK == 1U);
    assert(g_acquisition_system.TEMPRCR_b.TSNKEEP == 1U);
    assert(g_acquisition_tsn.TSCR_b.TSEN == 1U && g_acquisition_tsn.TSCR_b.TSOE == 1U);
    assert(FSP_SUCCESS == R_ADC_B_Close(&ctrl));
    assert(g_acquisition_tsn.TSCR_b.TSEN == 0U && g_acquisition_tsn.TSCR_b.TSOE == 0U);
}

static void priority_group_restrictions(void)
{
    adc_b_extended_cfg_t ext;
    adc_b_isr_cfg_t isr;
    adc_cfg_t cfg;
    adc_b_instance_ctrl_t ctrl = {0};
    setup(&ext, &isr, &cfg);
    ext.group_priority_enable = 1U;
    ext.sample_and_hold_enable_mask = ADC_B_SAMPLE_AND_HOLD_MASK_UNIT_0;
    assert(FSP_SUCCESS == R_ADC_B_Open(&ctrl, &cfg));
    adc_b_virtual_channel_cfg_t vc[2] = {0}, *vcs[2] = {&vc[0], &vc[1]};
    adc_b_group_cfg_t group[2] = {0}, *groups[2] = {&group[0], &group[1]};
    adc_b_scan_cfg_t scan = {.group_count = 2U, .p_adc_groups = groups};
    for (unsigned i = 0U; i < 2U; i++)
    {
        vc[i].channel_id = (adc_b_virtual_channel_t) i;
        vc[i].channel_cfg_bits.channel = i;
        vc[i].channel_control_c_bits.data_is_unsigned = 1U;
        group[i].scan_group_id = (adc_group_id_t) i;
        group[i].p_virtual_channels = &vcs[i];
        group[i].virtual_channel_count = 1U;
    }
    assert(FSP_ERR_INVALID_ARGUMENT == R_ADC_B_ScanCfg(&ctrl, &scan));
    vc[1].channel_cfg_bits.channel = 12U;
    assert(FSP_SUCCESS == R_ADC_B_ScanCfg(&ctrl, &scan));
    group[1].scan_group_id = group[0].scan_group_id;
    assert(FSP_ERR_INVALID_ARGUMENT == R_ADC_B_ScanCfg(&ctrl, &scan));
    assert(FSP_SUCCESS == R_ADC_B_Close(&ctrl));
}
#endif

int main(void)
{
    lifecycle_and_calibration();
    calibration_skip_and_failure();
#if ADC_B_CFG_PARAM_CHECKING_ENABLE
    validation_and_erratum();
    synchronous_sampling_table();
    temperature_latch_protection();
    priority_group_restrictions();
#endif
    puts("production r_adc_b: variant calibration, priority, scan/error IRQs and overflow checks passed");
    return 0;
}
