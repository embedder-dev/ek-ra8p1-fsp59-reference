/* Execute production r_pdm.c against controlled registers; no audio/hardware qualification is implied. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "r_pdm.h"

_Static_assert(sizeof(R_PDM_CH_Type) == 0x100, "HM channel stride");
_Static_assert(offsetof(acquisition_pdm_t, CH[2].PDDRR) == 0x3E8, "HM FIFO offset");
_Static_assert(offsetof(R_PDM_CH_Type, PDSCTSR) == 0xC4, "HM detector threshold offset");
_Static_assert(offsetof(R_PDM_CH_Type, PDLFCH119R) == 0xB4, "HM final LP coefficient offset");

acquisition_pdm_t g_acquisition_pdm;
static void * g_contexts[16];
static bool g_enabled[16];
static unsigned g_clear[16], g_pending[16];
static IRQn_Type g_irq;
static uint32_t g_clock = 62500000U;
static uint32_t g_delay;
static unsigned g_starts, g_callbacks;
static pdm_callback_args_t g_args;
static pdm_instance_ctrl_t * gp_callback_ctrl;
static bool g_restart_in_callback;
static uint32_t g_next_buffer[16];
#if BSP_TZ_SECURE_BUILD
bool g_acquisition_ns_callback;
bool g_acquisition_ns_memory;
void * g_acquisition_callback_address;
void * acquisition_cmse_range(void * p, size_t size, unsigned flags)
{
    (void) size;
    (void) flags;
    if (p == g_acquisition_callback_address)
    {
        return g_acquisition_ns_callback ? p : NULL;
    }
    return g_acquisition_ns_memory ? p : NULL;
}
#endif

void acquisition_module_start(uint32_t ip, uint32_t channel) { (void) ip; assert(channel == 0U); g_starts++; }
void * R_FSP_IsrContextGet(IRQn_Type irq) { assert(irq >= 0 && irq < 16); return g_contexts[irq]; }
void R_FSP_IsrContextSet(IRQn_Type irq, void * ctx) { assert(irq >= 0 && irq < 16); g_contexts[irq] = ctx; }
IRQn_Type R_FSP_CurrentIrqGet(void) { return g_irq; }
void R_BSP_IrqCfgEnable(IRQn_Type irq, uint32_t ipl, void * ctx)
{ assert(ipl == 12U); R_FSP_IsrContextSet(irq, ctx); g_enabled[irq] = true; }
void R_BSP_IrqDisable(IRQn_Type irq) { g_enabled[irq] = false; }
void R_BSP_IrqEnable(IRQn_Type irq) { g_enabled[irq] = true; }
void R_BSP_IrqStatusClear(IRQn_Type irq) { g_clear[irq]++; }
void NVIC_SetPendingIRQ(IRQn_Type irq) { g_pending[irq]++; }
void R_BSP_SoftwareDelay(uint32_t delay, uint32_t units) { assert(units == 0U); g_delay = delay; }
uint32_t R_FSP_SystemClockHzGet(uint32_t clock) { assert(clock == FSP_PRIV_CLOCK_PCLKB); return g_clock; }
void pdm_dat_isr(void);
void pdm_err_isr(void);

static void callback(pdm_callback_args_t * p_args)
{
    assert(!gp_callback_ctrl->active);
    assert(gp_callback_ctrl->p_buffer == NULL);
    g_args = *p_args;
    g_callbacks++;
    if (g_restart_in_callback)
    {
        assert(FSP_SUCCESS == R_PDM_Start(gp_callback_ctrl, g_next_buffer, 16U));
    }
}

static pdm_cfg_t config(pdm_extended_cfg_t * p_extend)
{
    *p_extend = (pdm_extended_cfg_t) {
        .input = PDM_INPUT_RISING, .sample_format = PDM_SAMPLE_FORMAT_20_BITS,
        .clock_div = 0U, .sinc_order = 4U, .fifo_threshold = 4U,
        .lower_limit = 0x80000U, .upper_limit = 0x7FFFFU,
    };
    pdm_cfg_t cfg = {
        .channel = 2U, .dat_irq = 2, .err_irq = 3, .ipl = 12U,
        .p_callback = callback, .p_context = &g_clock, .p_extend = p_extend,
    };
    return cfg;
}

static void reset(void)
{
    memset(&g_acquisition_pdm, 0, sizeof(g_acquisition_pdm));
    memset(g_contexts, 0, sizeof(g_contexts));
    memset(g_enabled, 0, sizeof(g_enabled));
    memset(g_clear, 0, sizeof(g_clear));
    memset(g_pending, 0, sizeof(g_pending));
    g_callbacks = 0U;
    g_starts = 0U;
    g_clock = 62500000U;
    g_delay = 0U;
    g_restart_in_callback = false;
#if BSP_TZ_SECURE_BUILD
    g_acquisition_ns_callback = false;
    g_acquisition_ns_memory = false;
    g_acquisition_callback_address = (void *) callback;
#endif
}

static void configuration_matrix(void)
{
    static uint8_t const dec[16] = {125,62,42,31,25,21,18,16,14,12,11,10,9,9,8,8};
    /* Independently transcribed acceptance values, HM table50.7. */
    static uint8_t const clips[4][16] = {
        {26,27,27,28,28,28,28,28,29,29,29,29,29,29,29,29},
        {19,21,22,23,23,24,24,24,25,25,26,26,26,26,26,26},
        {12,15,16,18,19,19,20,20,21,22,22,23,23,23,23,23},
        {5,9,11,13,14,15,16,16,17,18,19,19,20,20,20,20}};
    static pdm_sample_format_t const formats[] = {0,1,2,3,8,9,10,11,12};
    for (uint8_t ch = 0; ch < 3; ch++)
    {
        for (uint8_t order = 1; order <= 4; order++)
        {
            for (uint8_t div = 0; div < 16; div++)
            {
                for (unsigned f = 0; f < sizeof(formats)/sizeof(formats[0]); f++)
                {
                    reset();
                    pdm_instance_ctrl_t ctrl = {0};
                    pdm_extended_cfg_t ext;
                    pdm_cfg_t cfg = config(&ext);
                    cfg.channel = ch;
                    ext.sinc_order = order;
                    ext.clock_div = div;
                    ext.sample_format = formats[f];
                    pdm_instance_ctrl_t source_ctrl = {0};
                    pdm_extended_cfg_t source_ext = ext;
                    pdm_cfg_t source_cfg = cfg;
                    source_cfg.channel = (uint8_t) ((ch + 2U) % 3U);
                    source_cfg.dat_irq = 4;
                    source_cfg.err_irq = 5;
                    source_cfg.p_extend = &source_ext;
                    assert(FSP_SUCCESS == R_PDM_Open(&source_ctrl, &source_cfg));
                    source_ctrl.p_reg->PDSR = 1U; /* Source filter/clock is running. */
                    ext.input = PDM_INPUT_PREVIOUS_FALLING;
                    assert(FSP_SUCCESS == R_PDM_Open(&ctrl, &cfg));
                    assert(ctrl.p_reg == &R_PDM->CH[ch]);
                    assert((ctrl.p_reg->PDSFCR & 15U) == div);
                    assert(((ctrl.p_reg->PDSFCR >> 16) & 255U) == (uint32_t)dec[div] - 1U);
                    assert(((ctrl.p_reg->PDSFCR >> 24) & 31U) == clips[order - 1U][div]);
                    assert((ctrl.p_reg->PDMDSR >> 28) == (uint32_t)formats[f]);
                    assert((ctrl.p_reg->PDMDSR & 1U) == 1U);
                    assert(((ctrl.p_reg->PDMDSR >> 4) & 7U) == (order & 3U));
                    assert(g_delay > 1000U);
                    assert(ctrl.p_reg->PDLFCH102R == 0x1FF0U);
                    assert(ctrl.p_reg->PDLFCH119R == 0x1FF8U);
                    assert(ctrl.p_reg->PDCFCH10R == 0x1FE8U);
                    assert(FSP_SUCCESS == R_PDM_Close(&ctrl));
                    source_ctrl.p_reg->PDSR = 0U; /* Emulated stop acknowledgement. */
                    assert(FSP_SUCCESS == R_PDM_Close(&source_ctrl));
                }
            }
        }
    }
}

#if PDM_CFG_PARAM_CHECKING_ENABLE
static void invalid_parameters(void)
{
    reset();
    pdm_instance_ctrl_t ctrl = {0};
    pdm_extended_cfg_t ext;
    pdm_cfg_t cfg = config(&ext);
    uint32_t buffer[16];
    assert(FSP_ERR_ASSERTION == R_PDM_Open(NULL, &cfg));
    assert(FSP_ERR_ASSERTION == R_PDM_Open(&ctrl, NULL));
    pdm_cfg_t bad_cfg = {.p_extend = NULL};
    assert(FSP_ERR_ASSERTION == R_PDM_Open(&ctrl, &bad_cfg));
    pdm_status_t status;
    assert(FSP_ERR_NOT_OPEN == R_PDM_StatusGet(&ctrl, &status));
    assert(FSP_ERR_NOT_OPEN == R_PDM_CallbackSet(&ctrl, callback, NULL, NULL));
    assert(FSP_ERR_NOT_OPEN == R_PDM_Start(&ctrl, buffer, 16U));
    assert(FSP_ERR_NOT_OPEN == R_PDM_Stop(&ctrl));
    assert(FSP_ERR_NOT_OPEN == R_PDM_Close(&ctrl));
#define REJECT_CFG(field, value, error) do { pdm_cfg_t bad = cfg; bad.field = (value); \
    assert((error) == R_PDM_Open(&ctrl, &bad)); assert(g_starts == 0U); } while (0)
    REJECT_CFG(channel, 3U, FSP_ERR_IP_CHANNEL_NOT_PRESENT);
    REJECT_CFG(channel, 255U, FSP_ERR_IP_CHANNEL_NOT_PRESENT);
#define REJECT(field, value, error) do { pdm_extended_cfg_t bad_ext = ext; pdm_cfg_t bad = cfg; \
    bad_ext.field = (value); bad.p_extend = &bad_ext; \
    assert((error) == R_PDM_Open(&ctrl, &bad)); assert(g_starts == 0U); } while (0)
    REJECT(sinc_order, 0U, FSP_ERR_INVALID_ARGUMENT);
    REJECT(sinc_order, 5U, FSP_ERR_INVALID_ARGUMENT);
    REJECT(clock_div, 16U, FSP_ERR_INVALID_ARGUMENT);
    REJECT(input, (pdm_input_t)2, FSP_ERR_INVALID_ARGUMENT);
    REJECT(sample_format, (pdm_sample_format_t)4, FSP_ERR_INVALID_ARGUMENT);
    REJECT(sample_format, (pdm_sample_format_t)13, FSP_ERR_INVALID_ARGUMENT);
    REJECT(sample_format, (pdm_sample_format_t)-1, FSP_ERR_INVALID_ARGUMENT);
    REJECT(high_pass_shift, 4U, FSP_ERR_INVALID_ARGUMENT);
    REJECT(compensation_shift, 4U, FSP_ERR_INVALID_ARGUMENT);
    REJECT(low_pass_shift, 4U, FSP_ERR_INVALID_ARGUMENT);
    REJECT(fifo_threshold, 5U, FSP_ERR_INVALID_ARGUMENT);
    REJECT(error_enable, 1U, FSP_ERR_INVALID_ARGUMENT);
    REJECT(short_circuit_low, 8192U, FSP_ERR_INVALID_ARGUMENT);
    REJECT(short_circuit_high, 8192U, FSP_ERR_INVALID_ARGUMENT);
    REJECT(lower_limit, 0x100000U, FSP_ERR_INVALID_ARGUMENT);
    REJECT(upper_limit, 0x100000U, FSP_ERR_INVALID_ARGUMENT);
    REJECT(microphone_delay_us, UINT32_MAX, FSP_ERR_INVALID_ARGUMENT);
    REJECT_CFG(dat_irq, -1, FSP_ERR_IRQ_BSP_DISABLED);
    REJECT_CFG(err_irq, -1, FSP_ERR_IRQ_BSP_DISABLED);
    REJECT_CFG(err_irq, 2, FSP_ERR_IRQ_BSP_DISABLED);
    pdm_coefficients_t coefficients = {0};
    coefficients.compensation[10] = 8192U;
    REJECT(p_coefficients, &coefficients, FSP_ERR_INVALID_ARGUMENT);
    coefficients.compensation[10] = 0U;
    coefficients.low_pass[20] = 8192U;
    REJECT(p_coefficients, &coefficients, FSP_ERR_INVALID_ARGUMENT);
#undef REJECT
#undef REJECT_CFG
    g_clock = 62500001U;
    assert(FSP_ERR_INVALID_ARGUMENT == R_PDM_Open(&ctrl, &cfg));
    g_clock = 999999U;
    assert(FSP_ERR_INVALID_ARGUMENT == R_PDM_Open(&ctrl, &cfg));
    g_clock = 1000000U;
    assert(FSP_SUCCESS == R_PDM_Open(&ctrl, &cfg));
    assert(FSP_ERR_ALREADY_OPEN == R_PDM_Open(&ctrl, &cfg));
    assert(FSP_ERR_ASSERTION == R_PDM_Start(&ctrl, NULL, 16U));
    assert(FSP_ERR_INVALID_ALIGNMENT == R_PDM_Start(&ctrl, (uint32_t *)((uintptr_t)buffer + 1U), 16U));
    assert(FSP_ERR_INVALID_SIZE == R_PDM_Start(&ctrl, buffer, 0U));
    assert(FSP_ERR_INVALID_SIZE == R_PDM_Start(&ctrl, buffer, 1U));
    assert(FSP_ERR_INVALID_SIZE == R_PDM_Start(&ctrl, buffer, UINT32_MAX));
    assert(FSP_ERR_INVALID_SIZE == R_PDM_Start(&ctrl, (uint32_t *)(UINTPTR_MAX - 3U), 16U));
    assert(FSP_ERR_ASSERTION == R_PDM_StatusGet(&ctrl, NULL));
    assert(FSP_ERR_ASSERTION == R_PDM_CallbackSet(&ctrl, NULL, NULL, NULL));
    assert(FSP_SUCCESS == R_PDM_Close(&ctrl));
}
#endif

static void mandatory_safety(void)
{
    reset();
    pdm_instance_ctrl_t ctrl = {0};
    pdm_extended_cfg_t ext;
    pdm_cfg_t cfg = config(&ext);
    cfg.channel = 3U;
    assert(FSP_ERR_IP_CHANNEL_NOT_PRESENT == R_PDM_Open(&ctrl, &cfg));
    cfg.channel = 2U;
    cfg.dat_irq = -1;
    assert(FSP_ERR_IRQ_BSP_DISABLED == R_PDM_Open(&ctrl, &cfg));
    cfg.dat_irq = cfg.err_irq;
    assert(FSP_ERR_IRQ_BSP_DISABLED == R_PDM_Open(&ctrl, &cfg));
    cfg.dat_irq = 2;
    cfg.ipl = 16U;
    assert(FSP_ERR_IRQ_BSP_DISABLED == R_PDM_Open(&ctrl, &cfg));
    cfg.ipl = 12U;
    ext.sinc_order = 0U;
    assert(FSP_ERR_INVALID_ARGUMENT == R_PDM_Open(&ctrl, &cfg));
    ext.sinc_order = 4U;
    ext.clock_div = 16U;
    assert(FSP_ERR_INVALID_ARGUMENT == R_PDM_Open(&ctrl, &cfg));
    ext.clock_div = 0U;
    ext.fifo_threshold = 5U;
    assert(FSP_ERR_INVALID_ARGUMENT == R_PDM_Open(&ctrl, &cfg));
    ext.fifo_threshold = 4U;
    g_clock = 62500001U;
    assert(FSP_ERR_INVALID_ARGUMENT == R_PDM_Open(&ctrl, &cfg));
    assert(g_starts == 0U && ctrl.open == 0U);
}

static void fifo_and_lifecycle(void)
{
    reset();
    pdm_instance_ctrl_t ctrl = {0}, other = {0}, duplicate = {0};
    pdm_extended_cfg_t ext;
    pdm_cfg_t cfg = config(&ext);
    pdm_cfg_t cfg0 = cfg;
    cfg0.channel = 0U;
    pdm_extended_cfg_t ext0 = ext;
    cfg0.p_extend = &ext0;
    ext0.input = PDM_INPUT_PREVIOUS_FALLING;
    cfg0.dat_irq = 4;
    cfg0.err_irq = 5;
    assert(FSP_SUCCESS == g_pdm_on_pdm.open(&ctrl, &cfg));
    assert(FSP_ERR_IN_USE == R_PDM_Open(&duplicate, &cfg));
    ctrl.p_reg->PDSR = 1U; /* CH0 falling input depends on the running CH2 source. */
    assert(FSP_SUCCESS == R_PDM_Open(&other, &cfg0));
    ctrl.p_reg->PDSR = 0U;
    pdm_cfg_t conflicting_cfg = cfg;
    conflicting_cfg.dat_irq = 6;
    conflicting_cfg.err_irq = 7;
    ctrl.p_reg->PDSR = 1U;
    assert(FSP_ERR_IN_USE == R_PDM_Open(&duplicate, &conflicting_cfg));
    assert(duplicate.open == 0U && R_FSP_IsrContextGet(6) == NULL);
    ctrl.p_reg->PDSR = 0U;
    assert(R_PDM->CH[0].PDMDSR == 1U);
    assert(ctrl.p_reg->PDSCR == 0x08070002U);
    assert(ctrl.p_reg->PDSDCR == PDM_ERROR_FIFO_OVERFLOW);
    assert(ctrl.p_reg->PDICR == 0U);
    pdm_callback_args_t memory = {.samples = 1234U};
    gp_callback_ctrl = &ctrl;
    assert(FSP_SUCCESS == R_PDM_CallbackSet(&ctrl, callback, &g_clock, &memory));
    uint32_t guarded[34];
    for (unsigned i = 0; i < 34; i++) { guarded[i] = 0xDEADBEEFU; }
    assert(FSP_SUCCESS == R_PDM_Start(&ctrl, &guarded[1], 32U));
    assert(ctrl.p_reg->PDDRCR == 1U);
    assert(ctrl.p_reg->PDICR == 0x00010004U);
    assert(FSP_ERR_IN_USE == R_PDM_Start(&ctrl, &guarded[1], 32U));
    assert(FSP_ERR_IN_USE == R_PDM_CallbackSet(&ctrl, callback, NULL, NULL));
    assert(other.active == false && other.samples == 0U);
    g_irq = cfg.dat_irq;
    ctrl.p_reg->PDDSR = 8U;
    ctrl.p_reg->PDDRR = 0xF8000U;
    pdm_dat_isr();
    assert(ctrl.active && ctrl.samples == 8U && g_callbacks == 0U);
    assert(guarded[1] == 0xF8000U && guarded[8] == 0xF8000U && guarded[9] == 0xDEADBEEFU);
    ctrl.p_reg->PDDSR = 30U;
    ctrl.p_reg->PDDRR = 0x12345U;
    pdm_dat_isr();
    assert(!ctrl.active && ctrl.filtering && ctrl.p_buffer == NULL);
    assert(g_callbacks == 1U && g_args.event == PDM_EVENT_COMPLETE && g_args.samples == 32U);
    assert(g_args.p_buffer == &guarded[1] && g_args.p_context == &g_clock);
    assert(memory.samples == 1234U);
    assert(guarded[0] == 0xDEADBEEFU && guarded[33] == 0xDEADBEEFU);
    assert(ctrl.p_reg->PDICR == 0U && ctrl.p_reg->PDDRCR == 0U);
    pdm_dat_isr();
    assert(g_callbacks == 1U);
    pdm_status_t status;
    assert(FSP_SUCCESS == R_PDM_StatusGet(&ctrl, &status));
    assert(!status.active && status.samples == 32U);
    assert(FSP_SUCCESS == R_PDM_Start(&ctrl, &guarded[1], 16U));
    ctrl.p_reg->PDSR = PDM_ERROR_FIFO_OVERFLOW | PDM_ERROR_SHORT_CIRCUIT;
    pdm_dat_isr();
    assert(ctrl.samples == 0U && g_callbacks == 1U);
    g_irq = cfg.err_irq;
    pdm_err_isr();
    assert(!ctrl.active && !ctrl.filtering);
    assert(g_callbacks == 2U && g_args.event == PDM_EVENT_ERROR);
    assert(g_args.error == (PDM_ERROR_FIFO_OVERFLOW | PDM_ERROR_SHORT_CIRCUIT));
    assert(ctrl.p_reg->PDSCR == g_args.error && ctrl.p_reg->PDSTPTR == 1U);
    pdm_err_isr();
    assert(g_callbacks == 2U);
    ctrl.p_reg->PDSR = 0U;
    assert(FSP_SUCCESS == R_PDM_Start(&ctrl, &guarded[1], 16U));
    assert(FSP_SUCCESS == R_PDM_Stop(&ctrl));
    assert(!ctrl.active && !ctrl.filtering && !g_enabled[cfg.dat_irq] && !g_enabled[cfg.err_irq]);
    assert(FSP_SUCCESS == R_PDM_Start(&ctrl, &guarded[1], 16U));
    assert(g_enabled[cfg.dat_irq] && g_enabled[cfg.err_irq]);
    ctrl.p_reg->PDSR = 1U;
    assert(FSP_ERR_TIMEOUT == R_PDM_Close(&ctrl));
    assert(ctrl.open != 0U && ctrl.p_buffer == NULL && !ctrl.active);
    assert(FSP_ERR_TIMEOUT == R_PDM_Start(&ctrl, &guarded[1], 16U));
    ctrl.p_reg->PDSR = 0U;
    assert(FSP_SUCCESS == R_PDM_Close(&ctrl));
    assert(R_FSP_IsrContextGet(cfg.dat_irq) == NULL && R_FSP_IsrContextGet(cfg.err_irq) == NULL);
    assert(other.open != 0U && other.filtering);
    pdm_dat_isr();
    assert(FSP_SUCCESS == R_PDM_Close(&other));
    assert(FSP_SUCCESS == R_PDM_Open(&ctrl, &cfg));
    assert(FSP_SUCCESS == R_PDM_Close(&ctrl));
}

static void callback_restart_and_coefficients(void)
{
    reset();
    pdm_instance_ctrl_t ctrl = {0};
    pdm_extended_cfg_t ext;
    pdm_cfg_t cfg = config(&ext);
    pdm_coefficients_t coefficients = {.high_pass = {1,2,3,4}};
    coefficients.compensation[10] = 0x1FFFU;
    coefficients.low_pass[20] = 0x1234U;
    ext.p_coefficients = &coefficients;
    ext.high_pass_shift = 1;
    ext.compensation_shift = 2;
    ext.low_pass_shift = 3;
    ext.error_enable = PDM_ERROR_SHORT_CIRCUIT | PDM_ERROR_UPPER_LIMIT | PDM_ERROR_LOWER_LIMIT;
    ext.short_circuit_high = 8191U;
    ext.short_circuit_low = 12U;
    assert(FSP_SUCCESS == R_PDM_Open(&ctrl, &cfg));
    assert(ctrl.p_reg->PDHFCS0R == 1U && ctrl.p_reg->PDCFCH10R == 0x1FFFU);
    assert(ctrl.p_reg->PDLFCH119R == 0x1234U);
    assert(ctrl.p_reg->PDSCTSR == 0x1FFF000CU);
    assert(ctrl.p_reg->PDMDSR == 0x32100U);
    assert(ctrl.p_reg->PDSDCR == 0x08070000U);
    gp_callback_ctrl = &ctrl;
    uint32_t buffer[16];
    assert(FSP_SUCCESS == R_PDM_Start(&ctrl, buffer, 16U));
    ctrl.p_reg->PDDSR = 16U;
    g_irq = cfg.dat_irq;
    g_restart_in_callback = true;
    pdm_dat_isr();
    assert(g_callbacks == 1U && ctrl.active && ctrl.p_buffer == g_next_buffer && ctrl.samples == 0U);
    assert(FSP_SUCCESS == R_PDM_Close(&ctrl));
}

#if BSP_TZ_SECURE_BUILD
static void secure_callback_memory(void)
{
    reset();
    pdm_instance_ctrl_t ctrl = {0};
    pdm_extended_cfg_t ext;
    pdm_cfg_t cfg = config(&ext);
    g_acquisition_ns_callback = true;
    assert(FSP_ERR_NO_CALLBACK_MEMORY == R_PDM_Open(&ctrl, &cfg));
    assert(g_starts == 0U && ctrl.open == 0U && R_FSP_IsrContextGet(cfg.dat_irq) == NULL);
    cfg.p_callback = NULL;
    assert(FSP_SUCCESS == R_PDM_Open(&ctrl, &cfg));
    pdm_callback_args_t memory = {.samples = 999U};
    assert(FSP_ERR_NO_CALLBACK_MEMORY == R_PDM_CallbackSet(&ctrl, callback, NULL, NULL));
    assert(FSP_ERR_NO_CALLBACK_MEMORY == R_PDM_CallbackSet(&ctrl, callback, NULL, &memory));
    g_acquisition_ns_memory = true;
    assert(FSP_SUCCESS == R_PDM_CallbackSet(&ctrl, callback, NULL, &memory));
    uint32_t buffer[16];
    g_acquisition_ns_memory = false;
    assert(FSP_ERR_INVALID_ADDRESS == R_PDM_Start(&ctrl, buffer, 16U));
    g_acquisition_ns_memory = true;
    gp_callback_ctrl = &ctrl;
    assert(FSP_SUCCESS == R_PDM_Start(&ctrl, buffer, 16U));
    ctrl.p_reg->PDDSR = 16U;
    g_irq = cfg.dat_irq;
    pdm_dat_isr();
    assert(memory.samples == 999U && g_callbacks == 1U);
    assert(FSP_SUCCESS == R_PDM_Close(&ctrl));
}
#endif

#ifdef TEST_PDM_DEFAULTS
extern pdm_instance_t const g_pdm0;
static void default_lifecycle(void)
{
    reset();
    pdm_extended_cfg_t const * p_ext = (pdm_extended_cfg_t const *) g_pdm0.p_cfg->p_extend;
    assert(p_ext != NULL && p_ext->input == PDM_INPUT_RISING);
    assert(g_pdm0.p_cfg->channel == 2U && g_pdm0.p_cfg->ipl == 12U);
    assert(g_pdm0.p_cfg->dat_irq == 2 && g_pdm0.p_cfg->err_irq == 3);
    assert(FSP_SUCCESS == g_pdm0.p_api->open(g_pdm0.p_ctrl, g_pdm0.p_cfg));
    pdm_status_t status;
    assert(FSP_SUCCESS == g_pdm0.p_api->statusGet(g_pdm0.p_ctrl, &status));
    assert(!status.active && status.filtering && status.samples == 0U);
    uint32_t buffer[16];
    assert(FSP_SUCCESS == g_pdm0.p_api->start(g_pdm0.p_ctrl, buffer, 16U));
    R_PDM->CH[2].PDDSR = 16U;
    R_PDM->CH[2].PDDRR = 0x12345U;
    g_irq = g_pdm0.p_cfg->dat_irq;
    pdm_dat_isr();
    assert(FSP_SUCCESS == g_pdm0.p_api->statusGet(g_pdm0.p_ctrl, &status));
    assert(!status.active && status.samples == 16U && buffer[15] == 0x12345U && g_callbacks == 0U);
    assert(FSP_SUCCESS == g_pdm0.p_api->stop(g_pdm0.p_ctrl));
    assert(FSP_SUCCESS == g_pdm0.p_api->close(g_pdm0.p_ctrl));
}
#endif

int main(void)
{
#ifdef TEST_PDM_DEFAULTS
    default_lifecycle();
#endif
    configuration_matrix();
#if PDM_CFG_PARAM_CHECKING_ENABLE
    invalid_parameters();
#endif
    mandatory_safety();
    fifo_and_lifecycle();
    callback_restart_and_coefficients();
#if BSP_TZ_SECURE_BUILD
    secure_callback_memory();
#endif
    puts("production r_pdm: configuration/state/FIFO/error/ownership cases passed");
    return 0;
}
