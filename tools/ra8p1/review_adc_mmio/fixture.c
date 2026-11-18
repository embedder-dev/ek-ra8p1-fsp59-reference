/* ADC-010 oracle: r_adc_api.h ordinal events, never a flag set.
 * ADC-018 oracle: HM 54.5.10.2/.5 pp3471-3472; a pop returns all four bytes.
 * Ordinary RAM cannot emulate FIFO side effects; ARM codegen is checked separately. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "r_adc_b.h"

R_ADC_B0_Type g_acquisition_adc;
acquisition_tsn_t g_acquisition_tsn;
struct st_acquisition_cal g_acquisition_cal;
acquisition_system_t g_acquisition_system;
static adc_b_instance_ctrl_t ctrl;
static adc_cfg_t cfg;
static adc_b_extended_cfg_t ext;
static unsigned callbacks;
static unsigned clears;
static unsigned waits;
static unsigned expected_callbacks;
static bool expect_failure;
static bool use_memory;
static adc_callback_args_t records[2];
static adc_callback_args_t callback_memory;

_Static_assert(ADC_EVENT_CALIBRATION_COMPLETE == 3, "FSP5.9 ordinal contract");
_Static_assert(ADC_EVENT_CONVERSION_ERROR == 6, "FSP5.9 ordinal contract");
_Static_assert(ADC_EVENT_OVERFLOW == 7, "FSP5.9 ordinal contract");
_Static_assert(sizeof(adc_b_fifo_data_t) == sizeof(uint32_t), "FIFO object representation");
_Static_assert(offsetof(R_ADC_B0_Type, ADFIFODR0) == 0x2200, "HM54 FIFO data address");
_Static_assert(offsetof(R_ADC_B0_Type, ADFIFOSR0) == 0xCD0, "HM54 FIFO status address");

void acquisition_adc_wait(volatile uint32_t * reg, uint32_t expected)
{
    assert(reg == &R_ADC_B->ADSR && expected == 0U && *reg == 0U);
    waits++;
}
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
void adc_b_calend0_isr(void);
void adc_b_calend1_isr(void);

static void callback(adc_callback_args_t * args)
{
    assert(callbacks < expected_callbacks && callbacks < 2U);
    assert(args->p_context == &cfg);
    assert(args->group_mask == ADC_GROUP_MASK_NONE);
    assert(args->unit == ADC_B_UNIT_MASK_UNDEFINED);
    assert(args->channel == (adc_channel_t) UINT8_MAX);
    assert(!use_memory || args == &callback_memory);
    assert(ctrl.adc_state == (expect_failure ? ADC_B_CONVERTER_STATE_CALIBRATION_FAIL :
                             ADC_B_CONVERTER_STATE_READY));
    records[callbacks++] = *args;
    if (args->event == ADC_EVENT_CONVERSION_ERROR)
    {
        /* The callback may inspect/clear the shared status before a second event is delivered. */
        R_ADC_B->ADOVFCHSR0 = 0U;
        R_ADC_B->ADOVFEXSR = 0U;
    }
}

static void setup(void)
{
    memset(&g_acquisition_adc, 0, sizeof(g_acquisition_adc));
    memset(&ctrl, 0, sizeof(ctrl));
    memset(&cfg, 0, sizeof(cfg));
    memset(&ext, 0, sizeof(ext));
    memset(records, 0, sizeof(records));
    memset(&callback_memory, 0xA5, sizeof(callback_memory));
    callbacks = clears = waits = 0U;
    cfg.p_extend = &ext;
    ctrl.p_cfg = &cfg;
    ctrl.opened = ctrl.initialized = 0x41444348;
    ctrl.p_callback = callback;
    ctrl.p_context = &cfg;
}

static void calibration(unsigned unit, unsigned flags, unsigned phase, bool enabled, bool memory)
{
    setup();
    unsigned other_flags = flags >> 2U;
    flags &= 3U;
    expect_failure = flags != 0U;
    use_memory = memory;
    expected_callbacks = flags == 3U ? 2U : ((flags || phase) ? 1U : 0U);
    ctrl.adc_state = phase ? ADC_B_CONVERTER_STATE_SH_4_6_CALIBRATING :
                           (unit ? ADC_B_CONVERTER_STATE_ADC_1_CALIBRATING :
                            ADC_B_CONVERTER_STATE_ADC_0_CALIBRATING);
    ext.sample_and_hold_enable_mask = 0x77U;
    R_ADC_B->ADSHCR0 = 0x101U;
    R_ADC_B->ADSHCR1 = 0x202U;
    R_ADC_B->ADCALSTR = 0xDEADU;
    R_ADC_B->ADERSR = ((flags & 1U) ? (1U << unit) : 0U) |
                     ((other_flags & 1U) ? (1U << (1U - unit)) : 0U);
    R_ADC_B->ADOVFERSR = ((flags & 2U) ? (1U << unit) : 0U) |
                        ((other_flags & 2U) ? (1U << (1U - unit)) : 0U);
    R_ADC_B->ADOVFCHSR0 = (1U << 2) | (1U << 17);
    R_ADC_B->ADOVFEXSR = (1U << 4) | (1U << 22);
    adc_callback_args_t saved = callback_memory;
    if (!enabled) { ctrl.p_callback = NULL; }
    if (memory) { ctrl.p_callback_memory = &callback_memory; }
    if (unit) { adc_b_calend1_isr(); } else { adc_b_calend0_isr(); }
    assert(callbacks == (enabled ? expected_callbacks : 0U));
    assert(memcmp(&saved, &callback_memory, sizeof(saved)) == 0);
    assert(clears == 1U && waits == 1U);
    assert(R_ADC_B->ADCALENDSCR == (1U << unit));
    if (flags)
    {
        assert(ctrl.adc_state == ADC_B_CONVERTER_STATE_CALIBRATION_FAIL);
        assert(R_ADC_B->ADCALSTR == 0U);
        /* Failed calibration must not advance into the next phase. */
        assert(R_ADC_B->ADSHCR0 == 0x101U && R_ADC_B->ADSHCR1 == 0x202U);
        if (enabled)
        {
            unsigned index = 0U;
            if (flags & 1U)
            {
                assert(records[index].event == ADC_EVENT_CONVERSION_ERROR);
                assert(records[index].channel_mask == 0U);
                index++;
            }
            if (flags & 2U)
            {
                assert(records[index].event == ADC_EVENT_OVERFLOW);
                assert(records[index].channel_mask ==
                       ((1ULL << 2) | (1ULL << 17) | (1ULL << 36) | (1ULL << 54)));
            }
        }
    }
    else if (phase)
    {
        assert(ctrl.adc_state == ADC_B_CONVERTER_STATE_READY && R_ADC_B->ADCALSTR == 0U);
        if (enabled) { assert(records[0].event == ADC_EVENT_CALIBRATION_COMPLETE); }
    }
    else
    {
        assert(R_ADC_B->ADCALSTR == (unit ? 0x4U : 0x300U));
        assert(ctrl.adc_state == (unit ? ADC_B_CONVERTER_STATE_SH_0_2_CALIBRATING :
                                 ADC_B_CONVERTER_STATE_ADC_1_CALIBRATING));
    }
}

static void fifo(unsigned group, unsigned vacant)
{
    setup();
    adc_b_fifo_read_t result;
    memset(&result, 0x5A, sizeof(result));
    unsigned count = vacant < 8U ? 8U - vacant : 0U;
    const uint32_t word = 0xE5A6B7C8U;
    /* Seed by byte offset independently of the driver's register-address macro. */
    unsigned char * registers = (unsigned char *) &g_acquisition_adc;
    memcpy(registers + 0x2200U + 4U * group, &word, sizeof(word));
    uint32_t status = (group & 1U) ? ((vacant << 16) | 0xFU) : (vacant | 0xF0000U);
    memcpy(registers + 0xCD0U + 4U * (group / 2U), &status, sizeof(status));
    adc_b_fifo_read_t saved = result;
    fsp_err_t err = R_ADC_B_FifoRead(&ctrl, (adc_group_mask_t) (1U << group), &result);
    assert(err == (count ? FSP_SUCCESS : FSP_ERR_UNDERFLOW));
    assert(result.count == count);
    for (unsigned i = 0U; i < 8U; i++)
    {
        if (i < count)
        {
            assert(memcmp(&result.fifo_data[i], &word, sizeof(word)) == 0);
            assert(result.fifo_data[i].data == 0xB7C8U);
            assert(result.fifo_data[i].physical_channel == (adc_channel_t) 0x65);
            assert(result.fifo_data[i].err == 1U);
        }
        else { assert(memcmp(&result.fifo_data[i], &saved.fifo_data[i], sizeof(word)) == 0); }
    }
    assert(R_ADC_B->ADFIFOERSCR == (1U << (16U + group)));
    assert(callbacks == 0U && clears == 0U && waits == 0U);
}

int main(int argc, char ** argv)
{
    assert(argc >= 2);
    if (strcmp(argv[1], "calibration") == 0)
    {
        assert(argc == 7);
        calibration((unsigned) atoi(argv[2]), (unsigned) atoi(argv[3]), (unsigned) atoi(argv[4]),
                    atoi(argv[5]) != 0, atoi(argv[6]) != 0);
    }
    else
    {
        assert(strcmp(argv[1], "fifo") == 0 && argc == 4);
        fifo((unsigned) atoi(argv[2]), (unsigned) atoi(argv[3]));
    }
    puts("production ADC_B focused case passed");
    return 0;
}
