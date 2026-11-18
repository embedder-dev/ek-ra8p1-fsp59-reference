/* Independent oracles: HM54.1 tables54.4/5,54.5.6.1,54.5.10.4,70.6 tables70.99/100. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "r_adc_b.h"
#include REVIEW_SOURCE

R_ADC_B0_Type g_acquisition_adc;
acquisition_tsn_t g_acquisition_tsn;
struct st_acquisition_cal g_acquisition_cal;
acquisition_system_t g_acquisition_system;
review_admission_system_t g_admission_system;
static adc_b_instance_ctrl_t ctrl;
static adc_cfg_t cfg;
static adc_b_extended_cfg_t ext;
static adc_b_isr_cfg_t isr;
static uint32_t source_hz = 60000000U;
static unsigned modules, callbacks, irq_clears;
static bool restart;
uint32_t R_FSP_SystemClockHzGet(uint32_t clock) { assert(clock == 12U); return 120000000U; }
uint32_t R_BSP_SourceClockHzGet(fsp_priv_source_clock_t source) { (void) source; return source_hz; }
void acquisition_adc_wait(volatile uint32_t * reg, uint32_t expected) { *reg = expected; }
void acquisition_adc_module(bool start, uint32_t ip, uint32_t channel)
{ (void) start; (void) ip; (void) channel; modules++; }
void R_BSP_IrqCfgEnable(IRQn_Type irq, uint8_t ipl, void * context)
{ (void) irq; (void) ipl; (void) context; }
void R_BSP_IrqDisable(IRQn_Type irq) { (void) irq; }
void R_BSP_IrqStatusClear(IRQn_Type irq) { assert(irq == 12); irq_clears++; }
void * R_FSP_IsrContextGet(IRQn_Type irq) { assert(irq == 12); return &ctrl; }
void R_FSP_IsrContextSet(IRQn_Type irq, void * context) { (void) irq; (void) context; }
IRQn_Type R_FSP_CurrentIrqGet(void) { return 12; }
void R_BSP_SoftwareDelay(uint32_t delay, uint32_t units) { (void) delay; (void) units; }
static void callback(adc_callback_args_t * args)
{
    assert(args->event == ADC_EVENT_FIFO_OVERFLOW && args->group_mask == 0x101U);
    assert(R_ADC_B->ADFIFODCR == 0xCAFEU);
    assert(irq_clears == 1U && R_ADC_B->ADFIFOERSCR == 0x101U);
    callbacks++;
    if (restart)
    {
        assert(R_ADC_B_ScanStart(&ctrl) == FSP_SUCCESS);
        R_ADC_B->ADSR = 1U;
        R_ADC_B->ADFIFOERSCR = 0xBEEFU;
    }
}
static void setup(void)
{
    memset(&g_acquisition_adc, 0, sizeof(g_acquisition_adc));
    memset(&ctrl, 0, sizeof(ctrl)); memset(&cfg, 0, sizeof(cfg)); memset(&ext, 0, sizeof(ext));
    memset(&isr, 0xFF, sizeof(isr)); memset(&g_admission_system, 0, sizeof(g_admission_system));
    cfg.p_extend = &ext; ctrl.p_cfg = &cfg;
    ctrl.opened = ctrl.initialized = 0x41444348U;
    ctrl.adc_state = ADC_B_CONVERTER_STATE_READY;
    ctrl.cached_adsystr = 1U;
    ext.p_isr_cfg = &isr;
    isr.calibration_end_irq_adc_0 = 1; isr.calibration_end_irq_adc_1 = 2;
    ext.sync_operation_control = 0x30005U;
    ext.conversion_state = 6U | (6U << 8U);
    ext.calibration_adc_state = 95U | (6U << 16U);
    modules = callbacks = irq_clears = 0;
}
static void fifo(unsigned active, unsigned enable, unsigned rearm)
{
    setup(); ctrl.p_callback = enable ? callback : NULL; restart = rearm;
    R_ADC_B->ADSR = active; R_ADC_B->ADFIFOERSR = 0x101U;
    R_ADC_B->ADFIFODCR = 0xCAFEU; R_ADC_B->ADSTOPR = 0xBEEFU;
    adc_b_fifoovf_isr();
    assert(R_ADC_B->ADFIFODCR == 0xCAFEU && R_ADC_B->ADSTOPR == 0xBEEFU);
    assert(callbacks == enable && irq_clears == 1U);
    assert(R_ADC_B->ADFIFOERSCR == ((enable && rearm) ? 0xBEEFU : 0x101U));
    assert(R_ADC_B->ADSR == ((enable && rearm) ? 1U : active));
}
static void timing(unsigned hz, unsigned cst0, unsigned cst1, unsigned low, unsigned source, unsigned divider)
{
    setup(); ctrl.opened = 0; source_hz = hz;
    ext.clock_control_bits.source_selection = source;
    ext.clock_control_bits.divider = divider;
    ext.conversion_state = cst0 | (cst1 << 8U);
#ifdef REVIEW_LOW_VOLTAGE
    ext.low_voltage = low;
#else
    (void) low;
#endif
    R_ADC_B->ADCNVSTR = 0xBEEFU;
    /* HM70.99: 100..200ns; HM70.100: exactly200ns; HM54.2.4.10: equal CST. */
    uint32_t input_hz = source == 2U ? 120000000U : hz;
    uint64_t time = (uint64_t)cst0 * (divider + 1U) * 1000000000ULL;
    bool valid = source <= 2U && divider <= 4U && cst0 >= 3U &&
                 input_hz >= 25000000U * (divider + 1U) && input_hz <= 60000000U * (divider + 1U) &&
                 cst0 == cst1 && time >= (uint64_t)input_hz * (low ? 200U : 100U) &&
                 time <= (uint64_t)input_hz * 200U;
    fsp_err_t err = R_ADC_B_Open(&ctrl, &cfg);
    assert((err == FSP_SUCCESS) == valid);
    if (!valid) { assert(modules == 0U && R_ADC_B->ADCNVSTR == 0xBEEFU && ctrl.opened == 0U); }
}
static void source_mode(unsigned channel, unsigned unit, unsigned differential, unsigned unsigned_data)
{
    setup();
    adc_b_virtual_channel_cfg_t vc = {.channel_id = 0};
    vc.channel_cfg_bits.group = 1U; vc.channel_cfg_bits.channel = channel;
    vc.channel_cfg_bits.differential = differential;
    vc.channel_control_c_bits.data_is_unsigned = unsigned_data;
    adc_b_virtual_channel_cfg_t * channels[] = {&vc};
    adc_b_group_cfg_t group = {.scan_group_id = 0, .converter_selection = unit,
        .virtual_channel_count = 1, .p_virtual_channels = channels};
    adc_b_group_cfg_t * groups[] = {&group};
    adc_b_scan_cfg_t scan = {.group_count = 1, .p_adc_groups = groups};
    ext.converter_selection[0] = unit;
    bool diagnosis = channel == 96U || channel == 97U ||
                     (channel >= 112U && channel <= 114U) || (channel >= 116U && channel <= 118U);
    bool supported = channel <= 22U || diagnosis || channel == 100U || channel == 101U ||
                     channel == 102U || channel == 104U || channel == 105U;
    bool unit_ok = channel >= 16U && channel <= 22U;
    if (channel <= 15U) { unit_ok = unit ? (channel >= 6U && channel <= 11U) || channel == 13U || channel == 15U : channel <= 5U || channel == 12U || channel == 14U; }
    if (channel >= 96U) { unit_ok = diagnosis ? (unit ? channel == 97U || channel >= 116U : channel == 96U || (channel >= 112U && channel <= 114U)) : true; }
    bool diff_ok = diagnosis ? differential : (!differential || (channel <= 10U && !(channel & 1U)));
    bool valid = supported && unit_ok && diff_ok && (unsigned_data != differential);
    R_ADC_B->ADCHCR0 = 0xBEEFU; R_ADC_B->ADSGER = 0xABCDU;
    R_ADC_B0_Type before = g_acquisition_adc;
    fsp_err_t err = R_ADC_B_ScanCfg(&ctrl, &scan);
    assert((err == FSP_SUCCESS) == valid);
    if (!valid)
    {
        assert(memcmp(&before, &g_acquisition_adc, sizeof(before)) == 0);
        assert(ctrl.adc_state == ADC_B_CONVERTER_STATE_READY);
    }
    else
    {
        assert(R_ADC_B->ADCHCR0 == vc.channel_cfg);
        assert(R_ADC_B->ADDOPCRC0 == vc.channel_control_c);
    }
}
static void overlap(unsigned channel, unsigned active, unsigned armed, unsigned together, unsigned same_unit)
{
    setup();
    ctrl.cached_adsystr = 0x101U;
    R_ADC_B->ADSGER = 0x101U;
    R_ADC_B->ADSGCR0 = 0U; R_ADC_B->ADSGCR2 = same_unit ? 0U : 1U;
    R_ADC_B->ADCHCR0 = 1U | (channel << 8U);
    R_ADC_B->ADCHCR1 = 9U | (channel << 8U);
    R_ADC_B->ADGRSR = active ? 1U : 0U;
    R_ADC_B->ADTRGENR = armed ? 1U : 0U;
    R_ADC_B->ADSYSTR = 0xCAFEU;
    /* Unit-distinct sources are irrelevant to this collision oracle. */
    bool valid = same_unit || !(active || armed || together);
    fsp_err_t err = together ? R_ADC_B_ScanStart(&ctrl) : R_ADC_B_ScanGroupStart(&ctrl, 0x100U);
    assert((err == FSP_SUCCESS) == valid);
    if (!valid) { assert(R_ADC_B->ADSYSTR == 0xCAFEU && R_ADC_B->ADTRGENR == (armed ? 1U : 0U)); }
    if (!active && !armed && !together && !same_unit)
    {
        /* Conversion has ended; stale software-start writes must not ban sequential reuse. */
        R_ADC_B->ADGRSR = 0U;
        assert(R_ADC_B_ScanGroupStart(&ctrl, 1U) == FSP_SUCCESS);
    }
}
int main(int argc, char ** argv)
{
    assert(argc >= 2);
    if (!strcmp(argv[1], "fifo")) { fifo(atoi(argv[2]), atoi(argv[3]), atoi(argv[4])); }
    else if (!strcmp(argv[1], "timing"))
    {
        timing(strtoul(argv[2],NULL,0), atoi(argv[3]), atoi(argv[4]), atoi(argv[5]),
               argc > 6 ? (unsigned)atoi(argv[6]) : 0U, argc > 7 ? (unsigned)atoi(argv[7]) : 0U);
    }
    else if (!strcmp(argv[1], "source")) { source_mode(atoi(argv[2]), atoi(argv[3]), atoi(argv[4]), atoi(argv[5])); }
    else { overlap(atoi(argv[2]), atoi(argv[3]), atoi(argv[4]), atoi(argv[5]), atoi(argv[6])); }
    puts("ADC admission oracle passed"); return 0;
}
