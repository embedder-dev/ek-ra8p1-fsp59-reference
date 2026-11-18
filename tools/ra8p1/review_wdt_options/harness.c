#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include REVIEW_WDT_SOURCE

R_WDT0_Type review_wdt_registers[2];
review_wdt_icu_t review_wdt_icu;
review_wdt_scb_t review_wdt_scb;
static unsigned registrations;
static unsigned callback_calls;
static void (*group_callback)(bsp_grp_irq_t);

void R_BSP_GroupIrqWrite(bsp_grp_irq_t irq, void (*callback)(bsp_grp_irq_t))
{
    assert(irq == BSP_GRP_IRQ_WDT_ERROR);
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
    assert(args->p_context == &callback_calls);
    ++callback_calls;
}

static wdt_cfg_t config(void)
{
    wdt_cfg_t cfg = {
        .timeout = WDT_TIMEOUT_8192,
        .clock_division = WDT_CLOCK_DIVISION_512,
        .window_start = WDT_WINDOW_START_100,
        .window_end = WDT_WINDOW_END_0,
        .reset_control = TEST_NMI ? WDT_RESET_CONTROL_NMI : WDT_RESET_CONTROL_RESET,
        .stop_control = WDT_STOP_CONTROL_ENABLE,
        .p_callback = TEST_NMI ? callback : NULL,
        .p_context = &callback_calls,
    };
    return cfg;
}

/* HM7.2.6-7.2.7 addresses. Only this host fixture maps or initializes them. */
#define OPTIONS_SEC ((uint32_t *) (uintptr_t) 0x02C9F0C4U)
#define OPTIONS_NS  ((uint32_t *) (uintptr_t) 0x12C9F4C4U)
#define OPTIONS_SEL ((uint32_t *) (uintptr_t) 0x02C9F124U)
#define WDT_FIELDS 0x5FFE0000U

static void *option_pages[2];
static size_t page_size;

static void map_options(void)
{
    long size = sysconf(_SC_PAGESIZE);
    assert(size > 0);
    /* Rosetta reports 4KB pages on a host whose fixed mappings require 16KB alignment. */
    page_size = (size_t) size < 0x4000U ? 0x4000U : (size_t) size;
    uintptr_t addresses[] = {(uintptr_t) OPTIONS_SEC, (uintptr_t) OPTIONS_NS};
    for (unsigned i = 0; i < 2; ++i)
    {
        void *base = (void *) (addresses[i] & ~((uintptr_t) page_size - 1U));
        option_pages[i] = mmap(base, page_size, PROT_NONE,
                               MAP_PRIVATE | MAP_ANON | MAP_FIXED, -1, 0);
        if (option_pages[i] != base)
        {
            perror("fixed option-page mapping");
            fprintf(stderr, "requested %p, returned %p\n", base, option_pages[i]);
        }
        assert(option_pages[i] == base);
    }
    assert(((uintptr_t) OPTIONS_SEL & ~((uintptr_t) page_size - 1U)) == (uintptr_t) option_pages[0]);
}

static void set_options(uint32_t actual, uint32_t selector)
{
    for (unsigned i = 0; i < 2; ++i)
    {
        assert(mprotect(option_pages[i], page_size, PROT_READ | PROT_WRITE) == 0);
    }
    /* Every bit in the unselected word disagrees with the effective value. */
    *OPTIONS_SEC = (actual & ~selector) | (~actual & selector);
    *OPTIONS_NS = (actual & selector) | (~actual & ~selector);
    *OPTIONS_SEL = selector;
    for (unsigned i = 0; i < 2; ++i)
    {
        assert(mprotect(option_pages[i], page_size, PROT_READ) == 0);
    }
}

static void check_accepted(void)
{
    memset(review_wdt_registers, 0xA5, sizeof(review_wdt_registers));
    R_WDT0_Type before[2];
    memcpy(before, review_wdt_registers, sizeof(before));
    review_wdt_icu.NMIER = 0x0017F0EDU;
    registrations = 0;
    callback_calls = 0;
    group_callback = NULL;
    review_wdt_scb.AIRCR = TEST_NONSECURE ? SCB_AIRCR_BFHFNMINS_Msk : 0;
    wdt_instance_ctrl_t ctrl = {0};
    wdt_cfg_t cfg = config();
    assert(R_WDT_Open(&ctrl, &cfg) == FSP_SUCCESS);
    assert(ctrl.wdt_open == WDT_OPEN);
    unsigned selected = BSP_FEATURE_WDT_PER_CORE ? TEST_CORE : 0;
    assert(memcmp(&before[1U - selected], &review_wdt_registers[1U - selected], sizeof(before[0])) == 0);
#if TEST_AUTO
    assert(memcmp(before, review_wdt_registers, sizeof(before)) == 0);
#else
    assert(review_wdt_registers[selected].WDTCR == 0x3362);
    assert(review_wdt_registers[selected].WDTRCR == (TEST_NMI ? 0 : 0x80));
    assert(review_wdt_registers[selected].WDTCSTPR == 0x80);
#endif
    assert(registrations == (TEST_NMI ? 1U : 0U));
#if TEST_NMI
 #if BSP_FEATURE_ICU_NMIER_MAX_INDEX > 15
    assert(review_wdt_icu.NMIER == 0x0017F0EFU);
 #else
    assert(review_wdt_icu.NMIER == 2U);
 #endif
    assert(gp_wdt_ctrl == &ctrl);
    assert(group_callback != NULL);
    group_callback(BSP_GRP_IRQ_WDT_ERROR);
    assert(callback_calls == 1);
#else
    assert(review_wdt_icu.NMIER == 0x0017F0EDU);
#endif
}

static void check_rejected(void)
{
    R_WDT0_Type before[2];
    wdt_instance_ctrl_t ctrl;
    wdt_instance_ctrl_t previous = {0};
    memset(&ctrl, 0xA5, sizeof(ctrl));
    wdt_instance_ctrl_t saved = ctrl;
    memset(review_wdt_registers, 0xA5, sizeof(review_wdt_registers));
    memcpy(before, review_wdt_registers, sizeof(before));
    review_wdt_icu.NMIER = 0x0017F0EDU;
    review_wdt_scb.AIRCR = 0x5A5A5A5AU;
    gp_wdt_ctrl = &previous;
    registrations = 0;
    callback_calls = 0;
    group_callback = NULL;
    wdt_cfg_t cfg = config();
    assert(R_WDT_Open(&ctrl, &cfg) == FSP_ERR_INVALID_STATE);
    assert(memcmp(&ctrl, &saved, sizeof(ctrl)) == 0);
    assert(memcmp(before, review_wdt_registers, sizeof(before)) == 0);
    assert(review_wdt_icu.NMIER == 0x0017F0EDU);
    assert(review_wdt_scb.AIRCR == 0x5A5A5A5AU);
    assert(gp_wdt_ctrl == &previous);
    assert(registrations == 0);
    assert(callback_calls == 0);
    assert(group_callback == NULL);
    /* Admission must precede even control/config dereferences and parameter checks. */
    assert(R_WDT_Open(NULL, NULL) == FSP_ERR_INVALID_STATE);
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    if (strcmp(argv[1], "nonsecure") == 0)
    {
        /* No option pages are mapped: any attempted secure read faults this test. */
        assert(TEST_NONSECURE && TEST_CORE == 1 && BSP_FEATURE_WDT_PER_CORE);
        check_rejected();
    }
    else if (strcmp(argv[1], "unaffected") == 0)
    {
        /* CPU0 and legacy must not touch the unmapped CPU1 option words. */
        assert(TEST_CORE == 0 || !BSP_FEATURE_WDT_PER_CORE);
        check_accepted();
    }
    else
    {
        assert(TEST_CORE == 1 && BSP_FEATURE_WDT_PER_CORE && !TEST_NONSECURE);
        map_options();
        static const uint32_t selectors[] = {
            0, WDT_FIELDS, 0x00020000U, 0x000C0000U, 0x00F00000U,
            0x03000000U, 0x0C000000U, 0x10000000U, 0x40000000U,
            0x43F00000U, 0x1C0E0000U,
        };
        for (unsigned i = 0; i < sizeof(selectors) / sizeof(selectors[0]); ++i)
        {
            if (strcmp(argv[1], "match") == 0)
            {
                set_options(TEST_SELECTED_OFS, selectors[i]);
                check_accepted();
            }
            else if (strcmp(argv[1], "reserved") == 0)
            {
                set_options(TEST_SELECTED_OFS ^ ~WDT_FIELDS, selectors[i] | ~WDT_FIELDS);
                check_accepted();
            }
            else
            {
                assert(strcmp(argv[1], "mismatch") == 0);
                for (unsigned bit = 0; bit < 32; ++bit)
                {
                    if (WDT_FIELDS & (1U << bit))
                    {
                        set_options(TEST_SELECTED_OFS ^ (1U << bit), selectors[i]);
                        check_rejected();
                    }
                }
            }
        }
    }
    puts("WDT option admission passed");
    return 0;
}
