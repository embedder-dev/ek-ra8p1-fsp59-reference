/* Host-only control-flow/MMIO model. Oracles: stock 5.9 startup; HM 2.16.3.3, 2.16.5.2. */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "bsp_feature.h"

/* Keep the production ownership/cache capabilities. Unrelated hardware is stubbed. */
#undef BSP_FEATURE_TZ_VERSION
#define BSP_FEATURE_TZ_VERSION 0
#undef BSP_FEATURE_TZ_HAS_TRUSTZONE
#define BSP_FEATURE_TZ_HAS_TRUSTZONE 0
#undef BSP_FEATURE_BSP_VBATT_HAS_VBTBPCR1
#define BSP_FEATURE_BSP_VBATT_HAS_VBTBPCR1 0
#undef BSP_FEATURE_BSP_VBATT_HAS_VBTCR1_BPWSWSTP
#define BSP_FEATURE_BSP_VBATT_HAS_VBTCR1_BPWSWSTP 0
#undef BSP_FEATURE_TFU_SUPPORTED
#define BSP_FEATURE_TFU_SUPPORTED 0
#undef BSP_FEATURE_MACL_SUPPORTED
#define BSP_FEATURE_MACL_SUPPORTED 0
#undef BSP_FEATURE_BSP_HAS_SP_MON
#define BSP_FEATURE_BSP_HAS_SP_MON 0
#undef BSP_FEATURE_BSP_RESET_TRNG
#define BSP_FEATURE_BSP_RESET_TRNG 0
#undef BSP_FEATURE_BSP_HAS_ITCM
#define BSP_FEATURE_BSP_HAS_ITCM 0
#undef BSP_FEATURE_BSP_HAS_DTCM
#define BSP_FEATURE_BSP_HAS_DTCM 0
#if !BSP_FEATURE_BSP_HAS_SECONDARY_CORE
#undef BSP_FEATURE_BSP_HAS_GRAPHICS_DOMAIN
#define BSP_FEATURE_BSP_HAS_GRAPHICS_DOMAIN 0
#endif

#define BSP_TZ_SECURE_BUILD 0
#define BSP_TZ_NONSECURE_BUILD 0
#define FSP_PRIV_TZ_USE_SECURE_REGS 0
#define BSP_CFG_PFS_PROTECT 1
#define BSP_CFG_BOOT_IMAGE 0
#define BSP_CFG_EARLY_INIT 1
#define BSP_CFG_C_RUNTIME_INIT 1
#define BSP_CFG_DCACHE_ENABLED 0
#define BSP_CFG_SECONDARY_CORE_START_ADDRESS 0x02080000U
#define BSP_CFG_C_CACHE_LINE_SIZE 2U
#define __STATIC_INLINE static inline
#define R_CACHE_CCACTL_FC_Msk 0x0100U
#define R_CACHE_CCACTL_WB_Msk 0x0200U

static char trace[256];
static size_t trace_size;
static void event(char value)
{
    assert(trace_size + 1U < sizeof(trace));
    trace[trace_size++] = value;
    trace[trace_size] = '\0';
}

static struct {
    uint32_t CCACTL;
    union {
        uint32_t CCAFCT;
        struct { uint32_t FC : 1; uint32_t WB : 1; } CCAFCT_b;
    };
    struct { uint32_t WT; } CCAWTA_b;
    uint32_t CCALCF;
} cache;
static struct { uint32_t FCACHEE, FCACHEIV; } fcache;
static uint32_t previous_ctl, previous_fct;
static unsigned cache_accesses, flushes, completions, enables;
static bool dirty;

/* C MMIO lvalues stay unchanged. Observe each previous write on the next access. */
static void observe_cache(void)
{
    if (cache.CCAFCT != previous_fct)
    {
        assert(cache.CCAFCT == 1U || cache.CCAFCT == 3U);
        event('F');
        flushes++;
        previous_fct = cache.CCAFCT;
    }
    if (cache.CCACTL != previous_ctl)
    {
        assert(cache.CCAFCT == 0U);
        if (cache.CCACTL == 1U)
        {
            event('E');
            enables++;
        }
        else if (cache.CCACTL & R_CACHE_CCACTL_FC_Msk)
        {
            cache.CCAFCT = (cache.CCACTL >> 8U) & 3U;
            previous_fct = cache.CCAFCT;
            event('F');
            flushes++;
        }
        else
        {
            assert(cache.CCACTL == 0U);
            event('X');
        }
        previous_ctl = cache.CCACTL;
    }
}

#define R_CACHE (cache_pointer())
static void * cache_pointer(void)
{
    observe_cache();
    cache_accesses++;
    return &cache;
}
/* Use a typed expression for production's unchanged member syntax. */
#undef R_CACHE
#define R_CACHE ((__typeof__(cache) *) cache_pointer())
#define R_FCACHE (&fcache)

static void wait_register(uint32_t * reg, uint32_t value)
{
    observe_cache();
    if (reg == &cache.CCAFCT)
    {
        if (*reg != 0U)
        {
            assert(value == 0U);
            *reg = 0U;
            previous_fct = 0U;
            dirty = false;
            completions++;
            event('W');
        }
    }
    else
    {
        assert(reg == &fcache.FCACHEIV);
        *reg = 0U;
    }
    assert(*reg == value);
}
#define FSP_HARDWARE_REGISTER_WAIT(reg, value) wait_register(&(reg), (value))

/* CACHE FUNCTIONS */

#if TEST_SYSTEM
static struct { uint32_t VTOR; } scb;
#define SCB (&scb)
static void * __Vectors[1];
static uint32_t bss[2], data[2], etext;
#define __bss_start__ bss[0]
#define __bss_end__ bss[1]
#define __data_start__ data[0]
#define __data_end__ data[1]
#define __etext etext
static void constructor(void) { event('K'); }
static void (* __init_array_start[])(void) = {constructor};
#define __init_array_end (&__init_array_start[1])
static void * runtime_zero(void * p, int value, size_t size)
{
    assert(p == bss && value == 0 && size == sizeof(uint32_t));
    event('Z');
    return p;
}
static void * runtime_copy(void * p, const void * source, size_t size)
{
    assert(p == data && source == &etext && size == sizeof(uint32_t));
    event('D');
    return p;
}
#undef memset
#undef memcpy
#define memset runtime_zero
#define memcpy runtime_copy
static void bsp_init_uninitialized_vars(void) { event('A'); }
#if BSP_FEATURE_BSP_HAS_CTCM
static void bsp_init_ctcm(void) { event('T'); }
#endif
static void bsp_clock_init(void) { event('G'); R_BSP_FlashCacheEnable(); }
static void bsp_clock_freq_var_init(void) { event('L'); }
static void SystemCoreClockUpdate(void) { observe_cache(); event('U'); }
static void R_BSP_Init_RTC(void) { event('V'); }
#if BSP_FEATURE_BSP_HAS_GRAPHICS_DOMAIN
static void bsp_init_graphics_power_domain(void) { event('H'); }
#endif
#if BSP_FEATURE_CGC_HAS_EXTRACLK2 && BSP_FEATURE_BSP_POWER_DOMAIN_TYPE != 1
static void bsp_internal_prv_enable_extra_power_domain(void) { event('J'); }
#endif
static void bsp_irq_cfg(void) { event('I'); }
static void bsp_init(void * argument) { assert(argument == NULL); event('B'); }
#if BSP_FEATURE_BSP_HAS_SECONDARY_CORE && BSP_CFG_CPU_CORE == 0
static void bsp_start_secondary_core(void) { event('S'); }
#endif
#define BSP_WARM_START_RESET 0
#define BSP_WARM_START_POST_CLOCK 1
#define BSP_WARM_START_POST_C 2
static void R_BSP_WarmStart(unsigned stage)
{
    observe_cache();
    assert(stage <= 2U);
    event("RPC"[stage]);
}

/* SYSTEM FUNCTION */
#line 1000 "fixture.c"
#undef memset
#undef memcpy
#endif

static void reset_model(bool warm)
{
    memset(&cache, 0, sizeof(cache));
    memset(&fcache, 0, sizeof(fcache));
    previous_ctl = 0U;
    previous_fct = 0U;
    cache_accesses = flushes = completions = enables = 0U;
    trace_size = 0U;
    trace[0] = '\0';
    /* A disabled write-back cache can retain dirty lines; reset cache RAM is unknown. */
    dirty = true;
    cache.CCAWTA_b.WT = warm ? 0U : 1U;
}

int main(int argc, char ** argv)
{
    assert(argc == 2);
    bool warm = strcmp(argv[1], "warm") == 0 || strcmp(argv[1], "disable_wb") == 0;
    reset_model(warm);
    if (strcmp(argv[1], "startup") == 0 || strcmp(argv[1], "resume") == 0)
    {
#if TEST_SYSTEM
        SystemInit();
#else
        abort();
#endif
    }
    else
    {
        R_BSP_FlashCacheEnable();
        observe_cache();
        if (strcmp(argv[1], "warm") == 0)
        {
            /* Re-enabling must not discard dirty data (HM 2.16.3.3, p166). */
            assert(dirty);
            assert(flushes == 0U);
        }
        else if (strcmp(argv[1], "disable") == 0 || strcmp(argv[1], "disable_wb") == 0)
        {
            R_BSP_FlashCacheDisable();
        }
        else if (strcmp(argv[1], "busy") == 0)
        {
            cache.CCAFCT = previous_fct = 3U;
            cache.CCACTL = previous_ctl = 0U;
            R_BSP_FlashCacheEnable();
        }
    }
    observe_cache();
    printf("%s|access=%u,flush=%u,complete=%u,enable=%u,dirty=%u,ctl=%u,line=%u,flash=%u\n",
           trace, cache_accesses, flushes, completions, enables, dirty,
           cache.CCACTL, cache.CCALCF, fcache.FCACHEE);
    return 0;
}
