/* BSP-004 host fixture; oracle: RA8P1 HM 14.2.14, pp. 545-547. */
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include "bsp_feature.h"

typedef void (* bsp_grp_irq_cb_t)(unsigned int irq);

volatile uint32_t g_protect_pfswe_counter;
volatile uint16_t g_protect_counters[4];
uint32_t SystemCoreClock;
#define BSP_MOCO_HZ 8000000U

/* Slots 0..20 model RA8P1 callbacks; slot 21 is the adjacent canary.
 * The same oversized backing store observes the exact legacy 16-slot write
 * footprint without invoking legacy out-of-bounds behavior on smaller arrays. */
bsp_grp_irq_cb_t g_bsp_group_irq_sources[22];

static void sentinel_callback(unsigned int irq)
{
    (void) irq;
}

static void canary_callback(unsigned int irq)
{
    (void) irq;
}

#if TEST_TARGET
_Static_assert(BSP_FEATURE_ICU_NMIER_MAX_INDEX == 20U, "RA8P1 NMIER ends at IPCEN (20)");
#else
_Static_assert(BSP_FEATURE_ICU_NMIER_MAX_INDEX <= 15U, "Expected a legacy NMIER layout");
#endif

/* PRODUCTION */

int main(void)
{
    for (unsigned int i = 0; i <= 20U; i++)
    {
        g_bsp_group_irq_sources[i] = sentinel_callback;
    }
    g_bsp_group_irq_sources[21] = canary_callback;

    bsp_init_uninitialized_vars();

    /* Expected counts come from the manual and original BSP, not the loop. */
    const unsigned int cleared_count = TEST_TARGET ? 21U : 16U;
    for (unsigned int i = 0; i <= 20U; i++)
    {
        bsp_grp_irq_cb_t expected = (i < cleared_count) ? NULL : sentinel_callback;
        if (g_bsp_group_irq_sources[i] != expected)
        {
            fprintf(stderr, "callback slot %u: expected %s\n", i,
                    (expected == NULL) ? "cleared" : "sentinel preserved");
            return 1;
        }
    }
    if (g_bsp_group_irq_sources[21] != canary_callback)
    {
        fprintf(stderr, "adjacent canary slot 21 was overwritten\n");
        return 1;
    }
    return 0;
}
