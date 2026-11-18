#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "r_wdt.h"
#include "bsp_cfg.h"
#if TEST_PER_CORE && TEST_CORE == 1
 #include <sys/mman.h>
 #include <unistd.h>

static void map_cpu1_options(void)
{
    /* HM7.2.6-7.2.7: initialize actual option addresses, then make both pages read-only. */
    uint32_t *sec = (uint32_t *) (uintptr_t) 0x02C9F0C4U;
    uint32_t *ns = (uint32_t *) (uintptr_t) 0x12C9F4C4U;
    uint32_t *sel = (uint32_t *) (uintptr_t) 0x02C9F124U;
    long size = sysconf(_SC_PAGESIZE);
    assert(size > 0);
    /* Rosetta reports 4KB pages on a host whose fixed mappings require 16KB alignment. */
    size_t page_size = (size_t) size < 0x4000U ? 0x4000U : (size_t) size;
    uintptr_t addresses[] = {(uintptr_t) sec, (uintptr_t) ns};
    void *pages[2];
    for (unsigned i = 0; i < 2; ++i)
    {
        void *base = (void *) (addresses[i] & ~((uintptr_t) page_size - 1U));
        pages[i] = mmap(base, page_size, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANON | MAP_FIXED, -1, 0);
        if (pages[i] != base)
        {
            perror("fixed option-page mapping");
            fprintf(stderr, "requested %p, returned %p\n", base, pages[i]);
        }
        assert(pages[i] == base);
    }
    assert(((uintptr_t) sel & ~((uintptr_t) page_size - 1U)) == (uintptr_t) pages[0]);
    uint32_t actual = BSP_CFG_ROM_REG_OFS3;
    uint32_t selector = 0x43F00000U;
    /* Unselected fields disagree, so admission must use both words and the selector. */
    *sec = (actual & ~selector) | (~actual & selector);
    *ns = (actual & selector) | (~actual & ~selector);
    *sel = selector;
    for (unsigned i = 0; i < 2; ++i)
    {
        assert(mprotect(pages[i], page_size, PROT_READ) == 0);
    }
}
#endif

_Static_assert(sizeof(R_WDT0_Type) == 0x100, "local WDT stride");
_Static_assert(offsetof(R_WDT0_Type, WDTCR) == 2, "WDTCR offset");
_Static_assert(offsetof(R_WDT0_Type, WDTSR) == 4, "WDTSR offset");
_Static_assert(offsetof(R_WDT0_Type, WDTRCR) == 6, "WDTRCR offset");
_Static_assert(offsetof(R_WDT0_Type, WDTCSTPR) == 8, "WDTCSTPR offset");

R_WDT0_Type wdt_test_local[2];
R_WDT0_Type wdt_test_legacy;
wdt_test_icu_t wdt_test_icu;
unsigned wdt_test_refresh_writes;
static unsigned group_registrations;
static unsigned callback_calls;
static void (* group_callback)(bsp_grp_irq_t);
static void const * expected_context;
static wdt_callback_args_t * expected_memory;
static unsigned clock_reads;
static const unsigned context_one = 1;
#if TEST_NMI
static const unsigned context_two = 2;
#endif

void R_BSP_GroupIrqWrite(bsp_grp_irq_t irq, void (* callback)(bsp_grp_irq_t))
{
    assert(irq == BSP_GRP_IRQ_WDT_ERROR);
    assert(callback != NULL);
    group_callback = callback;
    ++group_registrations;
}

uint32_t R_FSP_SystemClockHzGet(fsp_priv_clock_t clock)
{
    assert(clock == FSP_PRIV_CLOCK_PCLKB);
    ++clock_reads;
    return 125000000U;
}

static void callback(wdt_callback_args_t * args)
{
    assert(args != NULL);
    assert(args->p_context == expected_context);
    if (expected_memory != NULL)
    {
        assert(args == expected_memory);
    }
    ++callback_calls;
}

static R_WDT0_Type * selected(void)
{
#if TEST_PER_CORE
    return &wdt_test_local[TEST_CORE];
#else
    return &wdt_test_legacy;
#endif
}

static void reset_fixture(void)
{
    memset(wdt_test_local, 0xA5, sizeof(wdt_test_local));
    memset(&wdt_test_legacy, 0xA5, sizeof(wdt_test_legacy));
    memset(&wdt_test_icu, 0, sizeof(wdt_test_icu));
    memset(selected(), 0, sizeof(*selected()));
    wdt_test_refresh_writes = 0;
    group_registrations = 0;
    group_callback = NULL;
    callback_calls = 0;
    expected_context = &context_one;
    expected_memory = NULL;
    clock_reads = 0;
}

static void assert_unselected_untouched(void)
{
    R_WDT0_Type sentinel;
    memset(&sentinel, 0xA5, sizeof(sentinel));
    for (unsigned i = 0; i < 2; ++i)
    {
        if (&wdt_test_local[i] != selected())
        {
            assert(memcmp(&sentinel, &wdt_test_local[i], sizeof(sentinel)) == 0);
        }
    }
    if (&wdt_test_legacy != selected())
    {
        assert(memcmp(&sentinel, &wdt_test_legacy, sizeof(sentinel)) == 0);
    }
}

static wdt_cfg_t valid_config(void)
{
    wdt_cfg_t cfg = {
        .timeout = WDT_TIMEOUT_8192,
        .clock_division = WDT_CLOCK_DIVISION_512,
        .window_start = WDT_WINDOW_START_100,
        .window_end = WDT_WINDOW_END_0,
        .reset_control = TEST_NMI ? WDT_RESET_CONTROL_NMI : WDT_RESET_CONTROL_RESET,
        .stop_control = WDT_STOP_CONTROL_ENABLE,
        .p_callback = TEST_NMI ? callback : NULL,
        .p_context = &context_one,
        .p_extend = NULL,
    };
    return cfg;
}

static void check_api_table(void)
{
    assert(g_wdt_on_wdt.open == R_WDT_Open);
    assert(g_wdt_on_wdt.refresh == R_WDT_Refresh);
    assert(g_wdt_on_wdt.statusGet == R_WDT_StatusGet);
    assert(g_wdt_on_wdt.statusClear == R_WDT_StatusClear);
    assert(g_wdt_on_wdt.counterGet == R_WDT_CounterGet);
    assert(g_wdt_on_wdt.timeoutGet == R_WDT_TimeoutGet);
    assert(g_wdt_on_wdt.callbackSet == R_WDT_CallbackSet);
}

static void check_open_and_register_routing(void)
{
    reset_fixture();
    wdt_instance_ctrl_t ctrl = {0};
    wdt_cfg_t cfg = valid_config();
    selected()->WDTCR = 0x1234;
    selected()->WDTRCR = 0x56;
    selected()->WDTCSTPR = 0x78;
    assert(g_wdt_on_wdt.open(&ctrl, &cfg) == FSP_SUCCESS);
    assert(ctrl.wdt_open != 0);
#if TEST_AUTO
    assert(selected()->WDTCR == 0x1234);
    assert(selected()->WDTRCR == 0x56);
    assert(selected()->WDTCSTPR == 0x78);
#else
    assert(selected()->WDTCR == 0x3362);
    assert(selected()->WDTRCR == (TEST_NMI ? 0 : 0x80));
    assert(selected()->WDTCSTPR == 0x80);
#endif
    assert(wdt_test_refresh_writes == 0);
    assert(group_registrations == (TEST_NMI ? 1U : 0U));
    assert(wdt_test_icu.NMIER == (TEST_NMI ? 2U : 0U));
#if TEST_NMI
    assert(ctrl.p_callback == callback);
    assert(ctrl.p_context == &context_one);
    assert(ctrl.p_callback_memory == NULL);
    assert(group_callback != NULL);
    group_callback(BSP_GRP_IRQ_WDT_ERROR);
    assert(callback_calls == 1);
#endif
#if TEST_CHECKS
    R_WDT0_Type before;
    memcpy(&before, selected(), sizeof(before));
    assert(R_WDT_Open(&ctrl, &cfg) == FSP_ERR_ALREADY_OPEN);
    assert(memcmp(&before, selected(), sizeof(before)) == 0);
    assert(group_registrations == (TEST_NMI ? 1U : 0U));
#endif
    assert_unselected_untouched();
}

static void check_refresh_status_counter(void)
{
    reset_fixture();
    wdt_instance_ctrl_t ctrl = {0};
    wdt_cfg_t cfg = valid_config();
    assert(R_WDT_Open(&ctrl, &cfg) == FSP_SUCCESS);
    selected()->refresh_trace[0] = 0xA5;
    selected()->refresh_trace[1] = 0x5A;
    assert(g_wdt_on_wdt.refresh(&ctrl) == FSP_SUCCESS);
    assert(wdt_test_refresh_writes == 2);
    assert(selected()->refresh_trace[0] == 0);
    assert(selected()->refresh_trace[1] == 0xFF);
    static const unsigned counts[] = {0, 1, 0x1234, 0x3FFF};
    for (unsigned i = 0; i < sizeof(counts) / sizeof(counts[0]); ++i)
    {
        for (unsigned flags = 0; flags < 4; ++flags)
        {
            selected()->WDTSR = (uint16_t) ((flags << 14) | counts[i]);
            uint32_t count = UINT32_MAX;
            assert(g_wdt_on_wdt.counterGet(&ctrl, &count) == FSP_SUCCESS);
            assert(count == counts[i]);
            wdt_status_t status = WDT_STATUS_OVERFLOW;
#if TEST_NMI_SUPPORTED
            assert(g_wdt_on_wdt.statusGet(&ctrl, &status) == FSP_SUCCESS);
            assert((unsigned) status == flags);
#else
            assert(g_wdt_on_wdt.statusGet(&ctrl, &status) == FSP_ERR_UNSUPPORTED);
            assert(status == WDT_STATUS_OVERFLOW);
#endif
        }
    }
    for (unsigned clear = 0; clear < 4; ++clear)
    {
        selected()->WDTSR = 0xFFFF;
#if TEST_NMI_SUPPORTED
        assert(g_wdt_on_wdt.statusClear(&ctrl, (wdt_status_t) clear) == FSP_SUCCESS);
        assert(selected()->WDTSR == (uint16_t) ((~clear & 3U) << 14));
#else
        assert(g_wdt_on_wdt.statusClear(&ctrl, (wdt_status_t) clear) == FSP_ERR_UNSUPPORTED);
        assert(selected()->WDTSR == 0xFFFF);
#endif
    }
    assert_unselected_untouched();
}

static void check_callback_update_and_memory(void)
{
#if TEST_NMI
    reset_fixture();
    wdt_instance_ctrl_t ctrl = {0};
    wdt_cfg_t cfg = valid_config();
    assert(R_WDT_Open(&ctrl, &cfg) == FSP_SUCCESS);
    wdt_callback_args_t memory = {.p_context = &context_one};
    expected_context = &context_two;
    expected_memory = &memory;
    assert(g_wdt_on_wdt.callbackSet(&ctrl, callback, &context_two, &memory) == FSP_SUCCESS);
    assert(ctrl.p_callback_memory == &memory);
    group_callback(BSP_GRP_IRQ_WDT_ERROR);
    assert(callback_calls == 1);
    assert(memory.p_context == &context_one);
    expected_memory = NULL;
    assert(R_WDT_CallbackSet(&ctrl, callback, &context_two, NULL) == FSP_SUCCESS);
    group_callback(BSP_GRP_IRQ_WDT_ERROR);
    assert(callback_calls == 2);
    ctrl.p_callback = NULL;
    group_callback(BSP_GRP_IRQ_WDT_ERROR);
    assert(callback_calls == 2);
    assert(group_registrations == 1);
    assert_unselected_untouched();
#endif
}

static void check_timeout_and_divider(void)
{
    reset_fixture();
    wdt_instance_ctrl_t ctrl = {0};
    wdt_cfg_t cfg = valid_config();
    assert(R_WDT_Open(&ctrl, &cfg) == FSP_SUCCESS);
    wdt_timeout_values_t timeout = {0};
#if TEST_AUTO
    /* The selected OFS word says 16384 clocks, CKS=15 (/128), whereas
     * p_cfg and the other core's OFS word deliberately disagree. */
    selected()->WDTCR = 0;
    assert(g_wdt_on_wdt.timeoutGet(&ctrl, &timeout) == FSP_SUCCESS);
    assert(timeout.timeout_clocks == 16384);
    assert(timeout.clock_frequency_hz == 125000000U / 128U);
    assert(clock_reads == 1);
#else
    static const struct { wdt_timeout_t value; unsigned clocks; } timeouts[] = {
        {WDT_TIMEOUT_1024, 1024}, {WDT_TIMEOUT_4096, 4096},
        {WDT_TIMEOUT_8192, 8192}, {WDT_TIMEOUT_16384, 16384},
    };
    static const struct { wdt_clock_division_t value; unsigned divisor; } dividers[] = {
        {WDT_CLOCK_DIVISION_4, 4}, {WDT_CLOCK_DIVISION_64, 64},
        {WDT_CLOCK_DIVISION_128, 128}, {WDT_CLOCK_DIVISION_512, 512},
        {WDT_CLOCK_DIVISION_2048, 2048}, {WDT_CLOCK_DIVISION_8192, 8192},
#if !TEST_PER_CORE
        {WDT_CLOCK_DIVISION_1, 1}, {WDT_CLOCK_DIVISION_16, 16},
        {WDT_CLOCK_DIVISION_32, 32}, {WDT_CLOCK_DIVISION_256, 256},
#endif
    };
    for (unsigned t = 0; t < sizeof(timeouts) / sizeof(timeouts[0]); ++t)
    {
        for (unsigned d = 0; d < sizeof(dividers) / sizeof(dividers[0]); ++d)
        {
            reset_fixture();
            memset(&ctrl, 0, sizeof(ctrl));
            cfg.timeout = timeouts[t].value;
            cfg.clock_division = dividers[d].value;
            assert(R_WDT_Open(&ctrl, &cfg) == FSP_SUCCESS);
            assert((selected()->WDTCR & 3U) == t);
            assert(((selected()->WDTCR >> 4) & 15U) == (unsigned) dividers[d].value);
            assert(R_WDT_TimeoutGet(&ctrl, &timeout) == FSP_SUCCESS);
            assert(timeout.timeout_clocks == timeouts[t].clocks);
            assert(timeout.clock_frequency_hz == 125000000U / dividers[d].divisor);
            assert(clock_reads == 1);
            assert_unselected_untouched();
        }
    }
    for (unsigned start = 0; start < 4; ++start)
    {
        for (unsigned end = 0; end < 4; ++end)
        {
            for (unsigned stop = 0; stop < 2; ++stop)
            {
                reset_fixture();
                memset(&ctrl, 0, sizeof(ctrl));
                cfg.window_start = (wdt_window_start_t) start;
                cfg.window_end = (wdt_window_end_t) end;
                cfg.stop_control = (wdt_stop_control_t) stop;
                assert(R_WDT_Open(&ctrl, &cfg) == FSP_SUCCESS);
                assert(((selected()->WDTCR >> 12) & 3U) == start);
                assert(((selected()->WDTCR >> 8) & 3U) == end);
                assert(selected()->WDTCSTPR == (stop << 7));
                assert_unselected_untouched();
            }
        }
    }
#endif
    assert_unselected_untouched();
}

#if TEST_PER_CORE && TEST_AUTO
static void assert_autostart_config_accepted(wdt_cfg_t const * cfg)
{
    reset_fixture();
    wdt_instance_ctrl_t ctrl = {0};
    R_WDT0_Type before;
    memcpy(&before, selected(), sizeof(before));
    expected_context = cfg->p_context;
    assert(R_WDT_Open(&ctrl, cfg) == FSP_SUCCESS);
    assert(ctrl.wdt_open != 0);
    assert(memcmp(&before, selected(), sizeof(before)) == 0);
    assert(wdt_test_refresh_writes == 0);
    assert(group_registrations == (TEST_NMI ? 1U : 0U));
    assert(wdt_test_icu.NMIER == (TEST_NMI ? 2U : 0U));
#if TEST_NMI
    assert(ctrl.p_callback == cfg->p_callback);
    assert(ctrl.p_context == cfg->p_context);
    assert(ctrl.p_callback_memory == NULL);
    assert(group_callback != NULL);
    group_callback(BSP_GRP_IRQ_WDT_ERROR);
    assert(callback_calls == 1);
#endif
    assert_unselected_untouched();
}
#endif

static void check_autostart_unused_fields(void)
{
#if TEST_PER_CORE && TEST_AUTO
    wdt_cfg_t cfg = {.p_callback = TEST_NMI ? callback : NULL};
    assert_autostart_config_accepted(&cfg);
    cfg.timeout = (wdt_timeout_t) -1;
    cfg.clock_division = (wdt_clock_division_t) -1;
    cfg.window_start = (wdt_window_start_t) -1;
    cfg.window_end = (wdt_window_end_t) -1;
    cfg.reset_control = (wdt_reset_control_t) -1;
    cfg.stop_control = (wdt_stop_control_t) -1;
    assert_autostart_config_accepted(&cfg);
#endif
}

#if TEST_CHECKS
static void assert_open_rejected(wdt_cfg_t const * cfg)
{
    reset_fixture();
    wdt_instance_ctrl_t ctrl = {0};
    R_WDT0_Type before;
    memcpy(&before, selected(), sizeof(before));
    assert(R_WDT_Open(&ctrl, cfg) == FSP_ERR_ASSERTION);
    assert(ctrl.wdt_open == 0);
    assert(memcmp(&before, selected(), sizeof(before)) == 0);
    assert(group_registrations == 0);
    assert(wdt_test_icu.NMIER == 0);
    assert_unselected_untouched();
}

static void check_register_field_config(wdt_cfg_t const * cfg)
{
#if TEST_PER_CORE && TEST_AUTO
    /* HM28.3.1: option memory supplies these fields in target autostart mode. */
    assert_autostart_config_accepted(cfg);
#else
    assert_open_rejected(cfg);
#endif
}
#endif

static void check_invalid_inputs(void)
{
#if TEST_CHECKS
    reset_fixture();
    wdt_instance_ctrl_t ctrl = {0};
    wdt_cfg_t cfg = valid_config();
    uint32_t count = 0;
    wdt_timeout_values_t timeout = {0};
    wdt_status_t status = WDT_STATUS_NO_ERROR;
    assert(R_WDT_Open(NULL, &cfg) == FSP_ERR_ASSERTION);
    assert(R_WDT_Open(&ctrl, NULL) == FSP_ERR_ASSERTION);
    assert(R_WDT_Refresh(NULL) == FSP_ERR_ASSERTION);
    assert(R_WDT_Refresh(&ctrl) == FSP_ERR_NOT_OPEN);
    assert(R_WDT_CounterGet(NULL, &count) == FSP_ERR_ASSERTION);
    assert(R_WDT_CounterGet(&ctrl, NULL) == FSP_ERR_ASSERTION);
    assert(R_WDT_CounterGet(&ctrl, &count) == FSP_ERR_NOT_OPEN);
    assert(R_WDT_TimeoutGet(NULL, &timeout) == FSP_ERR_ASSERTION);
    assert(R_WDT_TimeoutGet(&ctrl, NULL) == FSP_ERR_ASSERTION);
    assert(R_WDT_TimeoutGet(&ctrl, &timeout) == FSP_ERR_NOT_OPEN);
    assert(R_WDT_CallbackSet(NULL, callback, NULL, NULL) == FSP_ERR_ASSERTION);
    assert(R_WDT_CallbackSet(&ctrl, NULL, NULL, NULL) == FSP_ERR_ASSERTION);
    assert(R_WDT_CallbackSet(&ctrl, callback, NULL, NULL) == FSP_ERR_NOT_OPEN);
#if TEST_NMI_SUPPORTED
    assert(R_WDT_StatusGet(NULL, &status) == FSP_ERR_ASSERTION);
    assert(R_WDT_StatusGet(&ctrl, NULL) == FSP_ERR_ASSERTION);
    assert(R_WDT_StatusGet(&ctrl, &status) == FSP_ERR_NOT_OPEN);
    assert(R_WDT_StatusClear(NULL, WDT_STATUS_UNDERFLOW) == FSP_ERR_ASSERTION);
    assert(R_WDT_StatusClear(&ctrl, WDT_STATUS_UNDERFLOW) == FSP_ERR_NOT_OPEN);
#else
    assert(R_WDT_StatusGet(NULL, &status) == FSP_ERR_UNSUPPORTED);
    assert(R_WDT_StatusClear(NULL, WDT_STATUS_UNDERFLOW) == FSP_ERR_UNSUPPORTED);
#endif
    assert(wdt_test_refresh_writes == 0);
    assert(group_registrations == 0);
    static const int invalid_timeouts[] = {-1, 0, 1, 3, 7, 255};
    for (unsigned i = 0; i < sizeof(invalid_timeouts) / sizeof(invalid_timeouts[0]); ++i)
    {
        cfg = valid_config();
        cfg.timeout = (wdt_timeout_t) invalid_timeouts[i];
        check_register_field_config(&cfg);
    }
    cfg = valid_config();
#if TEST_AUTO || TEST_REGISTER_NMI
    cfg.p_callback = TEST_NMI ? NULL : callback;
#else
    cfg.reset_control = WDT_RESET_CONTROL_NMI;
    cfg.p_callback = callback;
#endif
    assert_open_rejected(&cfg);
#if TEST_PER_CORE
    /* RA8P1 WDTCR.CKS permits exactly 1,4,15,6,7,8. In particular,
     * several valid legacy enum values do not exist on this peripheral. */
    static const int invalid_dividers[] = {-1, 0, 2, 3, 5, 9, 10, 11, 12, 13, 14, 16, 255};
    for (unsigned i = 0; i < sizeof(invalid_dividers) / sizeof(invalid_dividers[0]); ++i)
    {
        cfg = valid_config();
        cfg.clock_division = (wdt_clock_division_t) invalid_dividers[i];
        check_register_field_config(&cfg);
    }
    static const int invalid_fields[] = {-1, 4, 255};
    for (unsigned i = 0; i < sizeof(invalid_fields) / sizeof(invalid_fields[0]); ++i)
    {
        cfg = valid_config();
        cfg.window_start = (wdt_window_start_t) invalid_fields[i];
        check_register_field_config(&cfg);
        cfg = valid_config();
        cfg.window_end = (wdt_window_end_t) invalid_fields[i];
        check_register_field_config(&cfg);
    }
    static const int invalid_binary_fields[] = {-1, 2, 255};
    for (unsigned i = 0; i < sizeof(invalid_binary_fields) / sizeof(invalid_binary_fields[0]); ++i)
    {
        cfg = valid_config();
        cfg.reset_control = (wdt_reset_control_t) invalid_binary_fields[i];
        check_register_field_config(&cfg);
        cfg = valid_config();
        cfg.stop_control = (wdt_stop_control_t) invalid_binary_fields[i];
        check_register_field_config(&cfg);
    }
#endif
    reset_fixture();
    cfg = valid_config();
    assert(R_WDT_Open(&ctrl, &cfg) == FSP_SUCCESS);
    assert(R_WDT_CallbackSet(&ctrl, NULL, NULL, NULL) == FSP_ERR_ASSERTION);
    assert_unselected_untouched();
#endif
}

int main(void)
{
#if TEST_PER_CORE && TEST_CORE == 1
    map_cpu1_options();
#endif
    check_api_table();
    check_open_and_register_routing();
    check_refresh_status_counter();
    check_callback_update_and_memory();
    check_timeout_and_divider();
    check_autostart_unused_fields();
    check_invalid_inputs();
    puts("production WDT behavior passed");
    return 0;
}
