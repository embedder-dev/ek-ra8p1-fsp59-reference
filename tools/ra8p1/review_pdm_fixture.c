/* Native production-C regression controls anchored to RA8P1 HM rev1.30:
 * 50.2.19 INPSEL, table50.18 stereo, 50.3.7 overwrite, 50.5.1 DAT level,
 * table50.16 settling and table70.50 guaranteed MOCO minimum (7.2MHz).
 * Clang coverage callbacks model asynchronous FIFO activity without editing the driver. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "r_pdm.h"

acquisition_pdm_t g_acquisition_pdm;
static void * contexts[16];
static IRQn_Type current_irq;
static unsigned pending[16], callbacks, fifo_reads, inject_at, inject_clear;
static pdm_instance_ctrl_t * observed;
static uint32_t previous_samples, elapsed_us;
static pdm_callback_args_t result;
static unsigned injected;

/* Only the production translation unit is instrumented. Each completed FIFO pop
 * changes samples; the next basic block models that pop and an asynchronous write.
 * Tests assert the injection actually fired before trusting the outcome. */
void __sanitizer_cov_trace_pc_guard_init(uint32_t * start, uint32_t * stop)
{
    for (uint32_t * p = start; p < stop; ++p) { *p = 1; }
}
void __sanitizer_cov_trace_pc_guard(uint32_t * guard)
{
    (void) guard;
    if (observed && observed->active && observed->samples != previous_samples)
    {
        assert(observed->samples == previous_samples + 1U);
        previous_samples = observed->samples;
        ++fifo_reads;
        assert(observed->p_reg->PDDSR > 0U);
        --observed->p_reg->PDDSR;
        if (inject_at == fifo_reads)
        {
            observed->p_reg->PDSR |= 1U << 27; /* BFOWDF: asynchronous overwrite */
            ++injected;
        }
    }
}
void acquisition_module_start(uint32_t ip, uint32_t channel) { (void) ip; assert(channel == 0U); }
void * R_FSP_IsrContextGet(IRQn_Type irq) { assert(irq >= 0 && irq < 16); return contexts[irq]; }
void R_FSP_IsrContextSet(IRQn_Type irq, void * context) { contexts[irq] = context; }
IRQn_Type R_FSP_CurrentIrqGet(void) { return current_irq; }
void R_BSP_IrqCfgEnable(IRQn_Type irq, uint32_t ipl, void * context)
{ assert(ipl == 12U); contexts[irq] = context; }
void R_BSP_IrqDisable(IRQn_Type irq) { (void) irq; }
void R_BSP_IrqEnable(IRQn_Type irq) { (void) irq; }
void R_BSP_IrqStatusClear(IRQn_Type irq)
{
    pending[irq] = 0U; /* ICU edge latch clear (HM14.2.17), not peripheral level clear. */
    if (observed && observed->active && irq == observed->p_cfg->dat_irq && inject_clear)
    {
        if (inject_clear == 1U) { observed->p_reg->PDDSR = 16U; }
        else { observed->p_reg->PDSR |= 1U << 27; }
        inject_clear = 0U;
        ++injected;
    }
}
void NVIC_SetPendingIRQ(IRQn_Type irq) { pending[irq] = 1U; }
void R_BSP_SoftwareDelay(uint32_t delay, uint32_t units)
{
    assert(units == BSP_DELAY_UNITS_MICROSECONDS);
    elapsed_us = delay;
    for (unsigned ch = 0; ch < 3; ++ch)
    {
        if (R_PDM->CH[ch].PDSTRTR) { R_PDM->CH[ch].PDSR |= 1U; }
    }
}
uint32_t R_FSP_SystemClockHzGet(uint32_t clock) { (void) clock; return 62500000U; }
void pdm_dat_isr(void);
void pdm_err_isr(void);
static void callback(pdm_callback_args_t * args) { result = *args; ++callbacks; }
static pdm_cfg_t cfg(pdm_extended_cfg_t * ext, unsigned ch)
{
    *ext = (pdm_extended_cfg_t) {.input = PDM_INPUT_RISING, .sinc_order = 4,
        .fifo_threshold = 4, .lower_limit = 0x80000, .upper_limit = 0x7FFFF};
    return (pdm_cfg_t) {.channel = (uint8_t) ch, .ipl = 12,
        .dat_irq = (IRQn_Type) (ch * 2U), .err_irq = (IRQn_Type) (ch * 2U + 1U),
        .p_callback = callback, .p_extend = ext};
}
static void capture(unsigned during_read, unsigned at_clear, unsigned length)
{
    pdm_instance_ctrl_t ctrl = {0};
    pdm_extended_cfg_t ext;
    pdm_cfg_t config = cfg(&ext, 2);
    uint32_t buffer[34];
    for (unsigned i = 0; i < 34; ++i) { buffer[i] = 0xDEADBEEFU; }
    assert(FSP_SUCCESS == R_PDM_Open(&ctrl, &config));
    assert(FSP_SUCCESS == R_PDM_Start(&ctrl, buffer + 1, length));
    observed = &ctrl;
    inject_at = during_read;
    inject_clear = at_clear;
    ctrl.p_reg->PDDSR = 16U;
    ctrl.p_reg->PDDRR = 0x12345;
    current_irq = config.dat_irq;
    pdm_dat_isr();
    if (during_read || at_clear) { assert(injected == 1U); }
    if (during_read || at_clear == 2U)
    {
        assert(callbacks == 0U); /* Never COMPLETE for corrupted data. */
        assert(ctrl.active && ctrl.p_buffer == buffer + 1);
        assert(pending[config.err_irq] == 1U);
        /* Hardware stop acknowledgement; isolate the finite-stop model from this test. */
        ctrl.p_reg->PDSR &= ~1U;
        current_irq = config.err_irq;
        pdm_err_isr();
        assert(callbacks == 1U && result.event == PDM_EVENT_ERROR);
        assert(result.error == (1U << 27) && result.p_buffer == buffer + 1);
        pdm_err_isr();
        assert(callbacks == 1U && !ctrl.active);
    }
    else if (at_clear)
    {
        assert(callbacks == 0U && ctrl.active && ctrl.samples == 16U);
        assert(pending[config.dat_irq] == 1U); /* Still-high DAT requires software repend. */
        pdm_dat_isr();
        assert(callbacks == 1U && result.event == PDM_EVENT_COMPLETE && result.samples == 32U);
    }
    else
    {
        assert(callbacks == 1U && result.event == PDM_EVENT_COMPLETE && result.samples == length);
    }
    assert(buffer[0] == 0xDEADBEEFU && buffer[length + 1U] == 0xDEADBEEFU);
    assert(fifo_reads == ctrl.samples && fifo_reads <= length);
}
static void settling(void)
{
    /* M values independently copied from HM table50.7; compute six physical
     * stage times separately, rather than copying the driver's summed numerator. */
    static unsigned const dec[] = {125,62,42,31,25,21,18,16,14,12,11,10,9,9,8,8};
    for (unsigned order = 1; order <= 4; ++order)
    {
        for (unsigned div = 0; div < 16; ++div)
        {
            memset(&g_acquisition_pdm, 0, sizeof(g_acquisition_pdm));
            memset(contexts, 0, sizeof(contexts));
            pdm_instance_ctrl_t ctrl = {0};
            pdm_extended_cfg_t ext;
            pdm_cfg_t config = cfg(&ext, 2);
            ext.sinc_order = (uint8_t) order;
            ext.clock_div = (uint8_t) div;
            ext.microphone_delay_us = 37;
            assert(FSP_SUCCESS == R_PDM_Open(&ctrl, &config));
            uint32_t d = 2U * (div + 1U), m = dec[div];
            uint32_t stages[] = {4U + d/2U, d/2U, order*d*m, d*m + 5U, 10U*d*m + 12U, 38U*d*m + 22U};
            uint32_t clocks = 0;
            for (unsigned i = 0; i < 6; ++i) { clocks += stages[i]; }
            assert((elapsed_us - 37U) * 72U >= clocks * 10U);
            assert((elapsed_us - 38U) * 72U < clocks * 10U); /* minimal rounded-up bound */
        }
    }
}
static void stereo(unsigned scenario)
{
    for (unsigned ch = 0; ch < 3; ++ch)
    {
        memset(&g_acquisition_pdm, 0, sizeof(g_acquisition_pdm));
        memset(contexts, 0, sizeof(contexts));
        pdm_instance_ctrl_t source = {0}, left = {0};
        pdm_extended_cfg_t se, le;
        unsigned src = (ch + 2U) % 3U; /* HM50.2.19 explicitly defines CH0 <- CH2. */
        pdm_cfg_t sc = cfg(&se, src), lc = cfg(&le, ch);
        le.input = PDM_INPUT_PREVIOUS_FALLING;
        if (scenario != 0U) { assert(FSP_SUCCESS == R_PDM_Open(&source, &sc)); }
        if (scenario == 1U) { source.p_reg->PDSR = 0U; }
        if (scenario == 2U) { le.sinc_order = 3; }
        if (scenario == 3U) { le.clock_div = 1; }
        if (scenario == 4U) { le.fifo_threshold = 3; }
        if (scenario == 5U) { source.p_reg->PDMDSR |= 3U << 24; } /* mandatory SDMAMD */
        if (scenario == 6U) { source.p_reg->PDMDSR |= 1U; } /* not a rising source */
        if (scenario == 7U) { source.p_reg->PDSFCR ^= 1U << 24; } /* SINCRNG mismatch */
        if (scenario <= 7U)
        {
            assert(FSP_ERR_INVALID_ARGUMENT == R_PDM_Open(&left, &lc));
            assert(left.open == 0U && R_PDM->CH[ch].PDSTRTR == 0U);
        }
        else
        {
            /* Table50.18 permits unique shifts, DBIS and coefficients. */
            le.high_pass_shift = 1; le.compensation_shift = 2; le.low_pass_shift = 3;
            le.sample_format = PDM_SAMPLE_FORMAT_16_BITS_18_4;
            assert(FSP_SUCCESS == R_PDM_Open(&left, &lc));
            if (scenario == 8U)
            {
                assert(FSP_ERR_IN_USE == R_PDM_Stop(&source));
                assert(FSP_ERR_IN_USE == R_PDM_Close(&source));
                assert(source.open != 0U && left.open != 0U);
                left.p_reg->PDSR = 0; /* Emulated consumer stop acknowledgement. */
                assert(FSP_SUCCESS == R_PDM_Close(&left));
                source.p_reg->PDSR = 0;
                assert(FSP_SUCCESS == R_PDM_Close(&source));
            }
            if (scenario == 9U)
            {
                uint32_t buffer[16];
                source.p_reg->PDSR = 0; /* externally stopped/error source */
                assert(FSP_ERR_INVALID_ARGUMENT == R_PDM_Start(&left, buffer, 16));
                assert(!left.active && left.p_reg->PDDRCR == 0);
            }
        }
    }
}
static void equivalent_dividers(void)
{
    /* Table50.7: 26/28 divisions share M=9; 30/32 share M=8. The falling
     * CKDIV does not drive the microphone (table50.18). Do not overconstrain it. */
    for (unsigned source_div = 12; source_div < 16; ++source_div)
    {
        for (unsigned order = 1; order <= 4; ++order)
        {
            memset(&g_acquisition_pdm, 0, sizeof(g_acquisition_pdm));
            memset(contexts, 0, sizeof(contexts));
            pdm_instance_ctrl_t source = {0}, left = {0};
            pdm_extended_cfg_t se, le;
            pdm_cfg_t sc = cfg(&se, 2), lc = cfg(&le, 0);
            se.clock_div = (uint8_t) source_div;
            le.clock_div = (uint8_t) (source_div ^ 1U);
            se.sinc_order = le.sinc_order = (uint8_t) order;
            le.input = PDM_INPUT_PREVIOUS_FALLING;
            assert(FSP_SUCCESS == R_PDM_Open(&source, &sc));
            assert(FSP_SUCCESS == R_PDM_Open(&left, &lc));
            uint32_t d = 2U * (source_div + 1U), m = source_div < 14U ? 9U : 8U;
            uint32_t clocks = (4U + d/2U) + d/2U + order*d*m + (d*m + 5U) +
                              (10U*d*m + 12U) + (38U*d*m + 22U);
            assert(elapsed_us * 72U >= clocks * 10U);
            assert((elapsed_us - 1U) * 72U < clocks * 10U);
        }
    }
}
int main(int argc, char ** argv)
{
    assert(argc == 2);
    unsigned scenario = (unsigned) strtoul(argv[1], NULL, 10);
    if (scenario == 0) { capture(4, 0, 16); }
    else if (scenario == 1) { capture(0, 1, 32); }
    else if (scenario == 2) { capture(0, 2, 32); }
    else if (scenario == 3) { settling(); }
    else if (scenario == 4) { capture(0, 0, 16); }
    else if (scenario == 5) { capture(16, 0, 16); }
    else if (scenario == 6) { capture(0, 2, 16); }
    else if (scenario == 7) { equivalent_dividers(); }
    else { stereo(scenario - 10U); }
    puts("PDM review regression passed");
    return 0;
}
