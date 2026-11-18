/* HM25.2/25.4 model: W0C flags, delayed TCSTF, buffered running counter,
 * TSTOP capture destruction, CKS and filter settling. No target timing claim. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "r_agt.h"
void agt_int_isr(void);
_Static_assert(offsetof(R_AGTX0_Type, AGT16.AGT) == 0x00, "HM25.2.1");
_Static_assert(offsetof(R_AGTX0_Type, AGT16.AGTCMA) == 0x02, "HM25.2.2");
_Static_assert(offsetof(R_AGTX0_Type, AGT16.AGTCMB) == 0x04, "HM25.2.3");
_Static_assert(offsetof(R_AGTX0_Type, AGT16.CTRL) == 0x08, "HM25.2.4");
_Static_assert(offsetof(review_target_agt_t, AGT16.CTRL) == 0x08, "Production layout");
R_AGTX0_Type review_regs[2];
static agt_instance_ctrl_t ctrl;
static agt_extended_cfg_t ext;
static timer_cfg_t cfg;
static uint32_t pclkb = 1000000U;
static void * irq_context;
static unsigned starts, critical, publish_irq, callback_count, callback_mode, writes, waits;
static double now_us, switch_time[2], filter_time[2], force_until[2], counter_time[2];
static unsigned pending[2];
static timer_callback_args_t memory, ns_memory;
static void callback(timer_callback_args_t * p);
static void ns_callback(timer_callback_args_t * p);
static R_AGTX0_AGT16_CTRL_Type * regs(unsigned ch) { return &review_regs[ch].AGT16.CTRL; }
static unsigned channel(const volatile void * p)
{
    uintptr_t offset = (uintptr_t)p - (uintptr_t)review_regs;
    assert(offset < sizeof(review_regs));
    return (unsigned)(offset / sizeof(review_regs[0]));
}
static double frequency(unsigned ch)
{
    unsigned tck = regs(ch)->AGTMR1_b.TCK;
    if (tck == 4) return 29491.2 / (1U << regs(ch)->AGTMR2_b.CKS);
    if (tck == 6) return 32768.0 / (1U << regs(ch)->AGTMR2_b.CKS);
    if (tck == 1) return pclkb / 8.0;
    if (tck == 3) return pclkb / 2.0;
    return pclkb;
}
static void accessible(unsigned ch)
{
    assert(!pending[ch]);
    assert(now_us + 0.000001 >= force_until[ch]);
}
void review_write8(volatile uint8_t * reg, uint8_t value)
{
    unsigned ch = channel(reg);
    R_AGTX0_AGT16_CTRL_Type * r = regs(ch);
    accessible(ch);
    writes++;
    if (reg == &r->AGTCR)
    {
        uint8_t old = *reg;
        if (value & 4U)
        {
            force_until[ch] = now_us + 1000000.0 / frequency(ch);
            review_regs[ch].AGT16.AGT = UINT16_MAX;
            *reg = (uint8_t)(old & value & 0xf0U);
            return;
        }
        if ((old & 1U) != (value & 1U))
        {
            pending[ch] = 1U;
        }
        if (value & 1U)
        {
            unsigned filter = r->AGTIOC_b.TIPF;
            unsigned divisor = filter == 3 ? 32U : (filter == 2 ? 8U : 1U);
            if (filter) assert(now_us - filter_time[ch] + 0.000001 >= 5000000.0 * divisor / pclkb);
        }
        *reg = (uint8_t)((old & value & 0xf0U) | (old & 2U) | (value & 1U));
        return;
    }
    assert((r->AGTCR & 3U) == 0U);
    if (reg == &r->AGTMR2 && (value & 7U))
    {
        assert(now_us - switch_time[ch] + 0.000001 >= 1000000.0 / frequency(ch));
    }
    if (reg == &r->AGTMR1)
    {
        assert((r->AGTMR2 & 7U) == 0U);
        switch_time[ch] = now_us;
    }
    if (reg == &r->AGTIOC) filter_time[ch] = now_us;
    *reg = value;
    r->AGTCR |= 0xf0U; /* HM25.4.3 deliberately adversarial undefined flags. */
}
void review_write_tck(volatile uint8_t * reg, uint8_t value)
{
    review_write8(reg, (uint8_t)((*reg & 0x8fU) | (value << 4)));
}
void review_write16(volatile uint16_t * reg, uint16_t value)
{
    unsigned ch = channel(reg);
    accessible(ch);
    writes++;
    if (reg == &review_regs[ch].AGT16.AGT && (regs(ch)->AGTCR & 3U) == 3U)
    {
        assert(now_us - counter_time[ch] + 0.000001 >= 3000000.0 / frequency(ch));
        counter_time[ch] = now_us;
        /* HM25.3.1: enabled compare holds counter until underflow. */
        if (regs(ch)->AGTCMSR & 0x11U) return;
    }
    *reg = value;
}
void review_wait(unsigned value, volatile uint8_t * reg)
{
    unsigned ch = channel(reg);
    waits++;
    assert(value == (*reg & 1U));
    if (pending[ch])
    {
        unsigned event = (regs(ch)->AGTMR1_b.TMOD == 2U) || (regs(ch)->AGTMR1_b.TCK == 5U);
        now_us += event ? 2000000.0 / pclkb : 3000000.0 / frequency(ch);
        pending[ch] = 0U;
    }
    *reg = (uint8_t)((*reg & ~2U) | (value << 1));
}
void R_BSP_SoftwareDelay(uint32_t delay, int units)
{
    assert(units == BSP_DELAY_UNITS_MICROSECONDS);
    now_us += delay;
}
uint32_t R_FSP_SystemClockHzGet(int clock) { (void)clock; return pclkb; }
void review_module_start(unsigned ch) { assert(ch < 2U); starts++; }
void R_BSP_IrqCfgEnable(IRQn_Type irq, uint32_t ipl, void * context)
{ assert(irq >= 0); (void)ipl; irq_context = context; }
void NVIC_DisableIRQ(IRQn_Type irq) { (void)irq; }
void R_FSP_IsrContextSet(IRQn_Type irq, void * context) { (void)irq; irq_context = context; }
void * R_FSP_IsrContextGet(IRQn_Type irq) { (void)irq; return irq_context; }
IRQn_Type R_FSP_CurrentIrqGet(void) { return 0; }
void R_BSP_IrqStatusClear(IRQn_Type irq) { (void)irq; }
unsigned review_critical_enter(void) { unsigned saved = critical; critical = 1; return saved; }
void review_publication_point(void * p)
{
    (void)p;
    if (publish_irq && !critical)
    {
        publish_irq = 0;
        regs(cfg.channel)->AGTCR |= 0x20U;
        agt_int_isr();
    }
}
void review_critical_exit(unsigned saved) { critical = saved; review_publication_point(&ctrl); }
void * review_cmse_address(void * p) { return p == (void *)ns_callback ? p : NULL; }
void * review_cmse_memory(void * p) { return p == &ns_memory ? p : NULL; }
int review_cmse_ns(void (*p)(void *)) { return p == (void (*)(void *))ns_callback; }
static void callback(timer_callback_args_t * p)
{
    accessible(cfg.channel);
    callback_count++;
    assert(p->p_context == &cfg);
    if (callback_mode == 1)
    {
        assert(p->event == TIMER_EVENT_CAPTURE_A);
        assert(p->capture == 19U);
        assert((regs(cfg.channel)->AGTCR & 3U) == 0U);
    }
    if (callback_mode == 2)
    {
        assert(p->event == TIMER_EVENT_CYCLE_END);
        assert(R_AGT_Start(&ctrl) == FSP_SUCCESS);
    }
}
static void ns_callback(timer_callback_args_t * p)
{
    assert(p == &ns_memory);
    assert(p->p_context == &ext);
    callback_count++;
}
static void setup(void)
{
    memset(&ctrl, 0, sizeof(ctrl));
    memset(&ext, 0, sizeof(ext));
    memset(review_regs, 0, sizeof(review_regs));
    ext.count_source = AGT_CLOCK_PCLKB;
    ext.measurement_mode = AGT_MEASURE_DISABLED;
    cfg = (timer_cfg_t){ .mode = TIMER_MODE_PERIODIC, .period_counts = 100,
        .duty_cycle_counts = 25, .source_div = TIMER_SOURCE_DIV_1,
        .p_extend = &ext, .cycle_end_irq = 0, .p_callback = callback, .p_context = &cfg };
    starts = writes = waits = callback_count = callback_mode = publish_irq = critical = 0;
    now_us = 1000000;
    for (unsigned ch = 0; ch < 2; ch++)
    {
        pending[ch] = 0;
        counter_time[ch] = force_until[ch] = switch_time[ch] = filter_time[ch] = 0;
    }
}
static void open_ok(void) { assert(R_AGT_Open(&ctrl, &cfg) == FSP_SUCCESS); }
static void arguments(void)
{
    unsigned before = writes;
    cfg.p_extend = NULL;
    assert(R_AGT_Open(&ctrl, &cfg) == FSP_ERR_ASSERTION);
    cfg.p_extend = &ext;
    cfg.mode = TIMER_MODE_ONE_SHOT; cfg.p_callback = NULL; cfg.cycle_end_irq = -1;
    assert(R_AGT_Open(&ctrl, &cfg) == FSP_ERR_IRQ_BSP_DISABLED);
    cfg.mode = TIMER_MODE_PERIODIC; cfg.cycle_end_irq = 0;
    ext.count_source = AGT_CLOCK_AGT_UNDERFLOW;
    assert(R_AGT_Open(&ctrl, &cfg) == FSP_ERR_INVALID_ARGUMENT);
    cfg.channel = 1; cfg.source_div = TIMER_SOURCE_DIV_2;
    assert(R_AGT_Open(&ctrl, &cfg) == FSP_ERR_INVALID_ARGUMENT);
    ext.count_source = AGT_CLOCK_LOCO; cfg.source_div = TIMER_SOURCE_DIV_1;
    pclkb = 72089;
    assert(R_AGT_Open(&ctrl, &cfg) == FSP_ERR_INVALID_ARGUMENT);
    pclkb = 72090;
    ext.measurement_mode = AGT_MEASURE_PULSE_PERIOD; ext.agtoab_settings = 3;
    assert(R_AGT_Open(&ctrl, &cfg) == FSP_ERR_INVALID_ARGUMENT);
    ext.measurement_mode = AGT_MEASURE_DISABLED; ext.agtoab_settings = 0;
    cfg.mode = TIMER_MODE_PWM; cfg.duty_cycle_counts = cfg.period_counts;
    assert(R_AGT_Open(&ctrl, &cfg) == FSP_ERR_INVALID_ARGUMENT);
    cfg.duty_cycle_counts = 0;
    assert(R_AGT_Open(&ctrl, &cfg) == FSP_ERR_INVALID_ARGUMENT);
    assert(starts == 0 && writes == before && ctrl.open == 0);
    cfg.mode = TIMER_MODE_PERIODIC; cfg.duty_cycle_counts = 25;
    open_ok(); /* Boundary clock ratio is accepted. */
#if AGT_CFG_PARAM_CHECKING_ENABLE
    assert(R_AGT_Open(&ctrl, &cfg) == FSP_ERR_ALREADY_OPEN);
    assert(R_AGT_Start(NULL) == FSP_ERR_ASSERTION);
    assert(R_AGT_InfoGet(&ctrl, NULL) == FSP_ERR_ASSERTION);
    assert(R_AGT_StatusGet(&ctrl, NULL) == FSP_ERR_ASSERTION);
    agt_instance_ctrl_t closed = {0};
    assert(R_AGT_Enable(&closed) == FSP_ERR_NOT_OPEN);
    assert(R_AGT_Disable(&closed) == FSP_ERR_NOT_OPEN);
    assert(R_AGT_CallbackSet(&closed, callback, NULL, NULL) == FSP_ERR_NOT_OPEN);
#endif
}
int main(int argc, char ** argv)
{
    assert(argc == 2);
    setup();
#if REVIEW_NSC
    extern int review_nsc_check(void);
    if (!strcmp(argv[1], "nsc")) { assert(review_nsc_check()); return 0; }
#endif
    if (!strcmp(argv[1], "arguments")) { arguments(); return 0; }
    if (!strcmp(argv[1], "clock_switch"))
    {
        ext.count_source = AGT_CLOCK_LOCO; cfg.source_div = TIMER_SOURCE_DIV_128;
        open_ok();
    }
    else if (!strcmp(argv[1], "flags"))
    {
        open_ok();
        assert(R_AGT_Start(&ctrl) == FSP_SUCCESS);
        assert((regs(0)->AGTCR & 0xf0U) == 0);
    }
    else if (!strcmp(argv[1], "filter"))
    {
        ext.agtio_filter = AGT_AGTIO_FILTER_PCLKB_DIV_32;
        open_ok();
        assert(R_AGT_Start(&ctrl) == FSP_SUCCESS);
    }
    else if (!strcmp(argv[1], "interval"))
    {
#if AGT_CFG_INPUT_SUPPORT_ENABLE
        ext.measurement_mode = AGT_MEASURE_PULSE_WIDTH_LOW_LEVEL;
        open_ok(); assert(R_AGT_Start(&ctrl) == FSP_SUCCESS);
        timer_status_t status;
        assert(R_AGT_StatusGet(&ctrl, &status) == FSP_SUCCESS);
        regs(0)->AGTCR &= 3U; /* Isolate successive measurement writes from undefined startup flags. */
        for (unsigned i = 0; i < 2; i++)
        {
            regs(0)->AGTCR |= 0x10U;
            agt_int_isr();
        }
        assert(callback_count == 2);
#endif
    }
    else if (!strcmp(argv[1], "polarity_low"))
    {
        ext.agto = AGT_PIN_CFG_START_LEVEL_LOW;
        open_ok();
#if AGT_CFG_OUTPUT_SUPPORT_ENABLE
        assert(regs(0)->AGTIOC_b.TEDGSEL == 0);
#endif
    }
    else if (!strcmp(argv[1], "irq_required"))
    {
        cfg.p_callback = NULL; cfg.mode = TIMER_MODE_ONE_SHOT; cfg.cycle_end_irq = -1;
        assert(R_AGT_Open(&ctrl, &cfg) == FSP_ERR_IRQ_BSP_DISABLED);
        assert(starts == 0 && writes == 0);
    }
    else if (!strcmp(argv[1], "ratio"))
    {
        pclkb = 72089;
        ext.count_source = AGT_CLOCK_LOCO;
        assert(R_AGT_Open(&ctrl, &cfg) == FSP_ERR_INVALID_ARGUMENT);
        assert(starts == 0 && writes == 0);
    }
    else if (!strcmp(argv[1], "measurement_output"))
    {
        ext.measurement_mode = AGT_MEASURE_PULSE_PERIOD;
        ext.agtoab_settings = 0x30;
        assert(R_AGT_Open(&ctrl, &cfg) == FSP_ERR_INVALID_ARGUMENT);
        assert(starts == 0 && writes == 0);
    }
    else if (!strcmp(argv[1], "endpoint"))
    {
        cfg.mode = TIMER_MODE_PWM; cfg.duty_cycle_counts = 100;
        assert(R_AGT_Open(&ctrl, &cfg) == FSP_ERR_INVALID_ARGUMENT);
        assert(starts == 0 && writes == 0);
    }
    else if (!strcmp(argv[1], "clock_filter"))
    {
        ext.count_source = AGT_CLOCK_LOCO; cfg.source_div = TIMER_SOURCE_DIV_128;
        ext.agtio_filter = AGT_AGTIO_FILTER_PCLKB_DIV_32;
        open_ok();
        assert(now_us >= 1000194.0); /* >=34us new LOCO cycle +160us filter. */
        assert(R_AGT_Start(&ctrl) == FSP_SUCCESS);
        assert((regs(0)->AGTCR & 0xf0U) == 0U);
    }
    else if (!strcmp(argv[1], "enable"))
    {
        open_ok();
        assert(R_AGT_Enable(&ctrl) == FSP_SUCCESS);
        assert(R_AGT_Enable(&ctrl) == FSP_SUCCESS);
        assert(R_AGT_Disable(&ctrl) == FSP_SUCCESS);
        assert(R_AGT_Disable(&ctrl) == FSP_SUCCESS);
        assert(!pending[0]);
    }
    else if (!strcmp(argv[1], "counter"))
    {
        ext.agtoab_settings = 0x33;
        open_ok(); assert(R_AGT_Start(&ctrl) == FSP_SUCCESS);
        review_regs[0].AGT16.AGT = 43;
        assert(R_AGT_Reset(&ctrl) == FSP_SUCCESS);
        assert(review_regs[0].AGT16.AGT == 99);
        assert((regs(0)->AGTCR & 3U) == 3U);
        assert(R_AGT_PeriodSet(&ctrl, 55) == FSP_SUCCESS);
        assert(review_regs[0].AGT16.AGT == 54);
        assert(R_AGT_PeriodSet(&ctrl, 33) == FSP_SUCCESS);
        assert(review_regs[0].AGT16.AGT == 32);
    }
    else if (!strcmp(argv[1], "duty"))
    {
#if AGT_CFG_OUTPUT_SUPPORT_ENABLE
        cfg.mode = TIMER_MODE_PWM; ext.agtoab_settings = 0x37;
        open_ok();
        assert(review_regs[0].AGT16.AGTCMA == 74);
        assert(R_AGT_DutyCycleSet(&ctrl, 7, AGT_OUTPUT_PIN_AGTOA) == FSP_SUCCESS);
        assert(review_regs[0].AGT16.AGTCMA == 92);
        assert(R_AGT_DutyCycleSet(&ctrl, 7, AGT_OUTPUT_PIN_AGTOB) == FSP_SUCCESS);
        assert(review_regs[0].AGT16.AGTCMB == 7);
        assert(R_AGT_DutyCycleSet(&ctrl, 100, 0) == FSP_ERR_INVALID_ARGUMENT);
        assert(R_AGT_DutyCycleSet(&ctrl, 0, 0) == FSP_ERR_INVALID_ARGUMENT);
        assert(R_AGT_DutyCycleSet(&ctrl, 7, 3) != FSP_SUCCESS);
#else
        assert(R_AGT_DutyCycleSet(NULL, 7, 0) == FSP_ERR_UNSUPPORTED);
#endif
    }
    else if (!strcmp(argv[1], "close"))
    {
        ext.agtoab_settings = 0x33; ext.agto = AGT_PIN_CFG_START_LEVEL_HIGH;
        open_ok();
#if AGT_CFG_OUTPUT_SUPPORT_ENABLE
        assert(regs(0)->AGTIOC_b.TEDGSEL == 1);
#endif
        assert(R_AGT_Start(&ctrl) == FSP_SUCCESS);
        assert(R_AGT_Close(&ctrl) == FSP_SUCCESS);
        assert(regs(0)->AGTCMSR == 0 && regs(0)->AGTIOC == 0);
        assert((regs(0)->AGTCR & 3U) == 0 && ctrl.open == 0);
    }
    else if (!strcmp(argv[1], "event"))
    {
#if AGT_CFG_INPUT_SUPPORT_ENABLE
        ext.count_source = AGT_CLOCK_AGTIO; open_ok();
        timer_info_t info;
        assert(R_AGT_InfoGet(&ctrl, &info) == FSP_SUCCESS);
        assert(info.clock_frequency == 0 && info.period_counts == 100);
#endif
    }
    else if (!strcmp(argv[1], "chain"))
    {
        cfg.channel = 1; ext.count_source = AGT_CLOCK_AGT_UNDERFLOW;
        open_ok();
        assert(R_AGT_Start(&ctrl) == FSP_SUCCESS);
        assert(R_AGT_Stop(&ctrl) == FSP_SUCCESS);
        assert(regs(1)->AGTMR1_b.TCK == 0);
        assert(R_AGT_Start(&ctrl) == FSP_SUCCESS);
        assert(regs(1)->AGTMR1_b.TCK == 5 && !pending[1]);
    }
    else if (!strcmp(argv[1], "oneshot") || !strcmp(argv[1], "capture"))
    {
        cfg.mode = TIMER_MODE_ONE_SHOT;
        if (!strcmp(argv[1], "capture"))
        {
#if !AGT_CFG_INPUT_SUPPORT_ENABLE
            return 0;
#endif
            ext.measurement_mode = AGT_MEASURE_PULSE_WIDTH_LOW_LEVEL;
            callback_mode = 1;
        }
        else { callback_mode = 2; ext.agtoab_settings = 0x33; }
        open_ok();
        assert(R_AGT_Start(&ctrl) == FSP_SUCCESS);
        review_regs[0].AGT16.AGT = 80;
        regs(0)->AGTCR |= callback_mode == 1 ? 0x10U : 0x20U;
        agt_int_isr();
        assert(callback_count == 1);
        assert(!pending[0]);
    }
    else if (!strcmp(argv[1], "callback"))
    {
        open_ok();
        ns_memory = (timer_callback_args_t){ .event = TIMER_EVENT_CAPTURE_A, .capture = 0x1234 };
        timer_callback_args_t saved = ns_memory;
        publish_irq = 1;
        assert(R_AGT_CallbackSet(&ctrl, ns_callback, &ext, &ns_memory) == FSP_SUCCESS);
        assert(publish_irq == 0 && callback_count == 1);
        assert(!memcmp(&saved, &ns_memory, sizeof(saved)));
        assert(R_AGT_CallbackSet(&ctrl, callback, &cfg, &memory) == FSP_SUCCESS);
#if BSP_TZ_SECURE_BUILD && AGT_CFG_PARAM_CHECKING_ENABLE
        assert(R_AGT_CallbackSet(&ctrl, ns_callback, &ext, NULL) == FSP_ERR_NO_CALLBACK_MEMORY);
#endif
    }
    else abort();
    return 0;
}
