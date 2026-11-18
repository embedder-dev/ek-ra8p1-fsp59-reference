#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "r_wdt.h"
#include "bsp_cfg.h"
#if BSP_FEATURE_WDT_PER_CORE && TEST_CORE == 1
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

_Static_assert(sizeof(R_WDT0_Type) == 0x100, "per-core WDT stride");
_Static_assert(offsetof(R_WDT0_Type, WDTCR) == 2, "WDTCR offset");
_Static_assert(offsetof(R_WDT0_Type, WDTRCR) == 6, "WDTRCR offset");
_Static_assert(offsetof(R_WDT0_Type, WDTCSTPR) == 8, "WDTCSTPR offset");

R_WDT0_Type review_wdt_registers[2];
review_wdt_icu_t review_wdt_icu;
static void (*group_callback)(bsp_grp_irq_t);
static unsigned registrations;
static unsigned callback_calls;
static void const *expected_context;

void R_BSP_GroupIrqWrite(bsp_grp_irq_t irq, void (*callback)(bsp_grp_irq_t))
{
    assert(irq == BSP_GRP_IRQ_WDT_ERROR);
    assert(callback != NULL);
    group_callback = callback;
    ++registrations;
}

uint32_t R_FSP_SystemClockHzGet(fsp_priv_clock_t clock)
{
    assert(clock == FSP_PRIV_CLOCK_PCLKB);
    return 125000000U;
}

static void callback(wdt_callback_args_t *args)
{
    assert(args != NULL);
    assert(args->p_context == expected_context);
    ++callback_calls;
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
    };
    return cfg;
}

static void check_open(wdt_cfg_t const *cfg, uint32_t before, fsp_err_t expected)
{
    wdt_instance_ctrl_t ctrl = {0};
    R_WDT0_Type sentinel;
    memset(&sentinel, 0xA5, sizeof(sentinel));
    memset(review_wdt_registers, 0xA5, sizeof(review_wdt_registers));
    review_wdt_icu.NMIER = before;
    registrations = 0;
    callback_calls = 0;
    group_callback = NULL;
    expected_context = cfg->p_context;
    assert(R_WDT_Open(&ctrl, cfg) == expected);
    unsigned selected = BSP_FEATURE_WDT_PER_CORE ? TEST_CORE : 0;
    assert(memcmp(&review_wdt_registers[1U - selected], &sentinel, sizeof(sentinel)) == 0);
    if (expected != FSP_SUCCESS)
    {
        assert(ctrl.wdt_open == 0);
        assert(registrations == 0);
        assert(review_wdt_icu.NMIER == before);
        assert(memcmp(&review_wdt_registers[selected], &sentinel, sizeof(sentinel)) == 0);
        return;
    }
    assert(ctrl.wdt_open != 0);
#if TEST_AUTO
    assert(memcmp(&review_wdt_registers[selected], &sentinel, sizeof(sentinel)) == 0);
#else
    assert(review_wdt_registers[selected].WDTCR == 0x3362);
    assert(review_wdt_registers[selected].WDTRCR == (TEST_NMI ? 0 : 0x80));
    assert(review_wdt_registers[selected].WDTCSTPR == 0x80);
#endif
    assert(registrations == (TEST_NMI ? 1U : 0U));
#if TEST_NMI
 #if BSP_FEATURE_ICU_NMIER_MAX_INDEX > 15
    assert(review_wdt_icu.NMIER == (before | R_ICU_NMIER_WDTEN_Msk));
 #else
    /* A plain host register records the pristine legacy assignment, not W1S semantics. */
    assert(review_wdt_icu.NMIER == R_ICU_NMIER_WDTEN_Msk);
 #endif
    assert(ctrl.p_callback == cfg->p_callback);
    assert(ctrl.p_context == cfg->p_context);
    assert(ctrl.p_callback_memory == NULL);
    assert(group_callback != NULL);
    group_callback(BSP_GRP_IRQ_WDT_ERROR);
    assert(callback_calls == 1);
#else
    assert(review_wdt_icu.NMIER == before);
#endif
#if TEST_CHECKS
    assert(R_WDT_Open(&ctrl, cfg) == FSP_ERR_ALREADY_OPEN);
#endif
}

static void preservation(void)
{
    /* HM14.2.14: ordinary R/W enables at 5,14,16,17,18,20, plus write-once bits. */
    static const uint32_t seeds[] = {
        0, 1U << 5, 1U << 14, 1U << 16, 1U << 17, 1U << 18, 1U << 20,
        0x0017F0EDU, 0x001240A5U, 0x0005B048U, 0x0017F0EFU,
    };
    wdt_cfg_t cfg = valid_config();
    for (unsigned i = 0; i < sizeof(seeds) / sizeof(seeds[0]); ++i)
    {
        check_open(&cfg, seeds[i], FSP_SUCCESS);
    }
}

static void unused_auto_fields(void)
{
    assert(TEST_AUTO);
    wdt_cfg_t cfg = {.p_callback = TEST_NMI ? callback : NULL};
    fsp_err_t expected = FSP_SUCCESS;
#if TEST_CHECKS && !BSP_FEATURE_WDT_PER_CORE
    /* Stock FSP 5.9 checks timeout even in autostart; preserve its behavior. */
    expected = FSP_ERR_ASSERTION;
#endif
    check_open(&cfg, 0x0017F0EDU, expected);
    cfg.timeout = (wdt_timeout_t) -1;
    cfg.clock_division = (wdt_clock_division_t) -1;
    cfg.window_start = (wdt_window_start_t) -1;
    cfg.window_end = (wdt_window_end_t) -1;
    cfg.reset_control = (wdt_reset_control_t) -1;
    cfg.stop_control = (wdt_stop_control_t) -1;
    check_open(&cfg, 0x0017F0EDU, expected);
}

static void invalid_register_fields(void)
{
    assert(!TEST_AUTO);
#if TEST_CHECKS && BSP_FEATURE_WDT_PER_CORE
    /* A field accepted in autostart must still be rejected before register writes. */
    wdt_cfg_t cfg = valid_config();
    cfg.timeout = WDT_TIMEOUT_128;
    check_open(&cfg, 0x0017F0EDU, FSP_ERR_ASSERTION);
    cfg = valid_config();
    cfg.clock_division = WDT_CLOCK_DIVISION_1;
    check_open(&cfg, 0x0017F0EDU, FSP_ERR_ASSERTION);
    cfg = valid_config();
    cfg.window_start = (wdt_window_start_t) 4;
    check_open(&cfg, 0x0017F0EDU, FSP_ERR_ASSERTION);
    cfg = valid_config();
    cfg.window_end = (wdt_window_end_t) 4;
    check_open(&cfg, 0x0017F0EDU, FSP_ERR_ASSERTION);
    cfg = valid_config();
    cfg.reset_control = (wdt_reset_control_t) 2;
    check_open(&cfg, 0x0017F0EDU, FSP_ERR_ASSERTION);
    cfg = valid_config();
    cfg.stop_control = (wdt_stop_control_t) 2;
    check_open(&cfg, 0x0017F0EDU, FSP_ERR_ASSERTION);
#endif
}

int main(int argc, char **argv)
{
    assert(argc == 2);
#if BSP_FEATURE_WDT_PER_CORE && TEST_CORE == 1
    map_cpu1_options();
#endif
    if (strcmp(argv[1], "preservation") == 0)
    {
        preservation();
    }
    else if (strcmp(argv[1], "autostart") == 0)
    {
        unused_auto_fields();
    }
    else
    {
        assert(strcmp(argv[1], "register") == 0);
        invalid_register_fields();
    }
    puts("review WDT production checks passed");
    return 0;
}
