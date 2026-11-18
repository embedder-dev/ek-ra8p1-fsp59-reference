#ifndef REVIEW_WDT_OPTIONS_BSP_API_H
#define REVIEW_WDT_OPTIONS_BSP_API_H

#include "../review_wdt/bsp_api.h"

#undef BSP_TZ_NONSECURE_BUILD
#define BSP_TZ_NONSECURE_BUILD TEST_NONSECURE

typedef struct st_review_wdt_scb
{
    volatile uint32_t AIRCR;
} review_wdt_scb_t;
extern review_wdt_scb_t review_wdt_scb;
#define SCB (&review_wdt_scb)
#define SCB_AIRCR_BFHFNMINS_Msk (1UL << 13)

#endif
