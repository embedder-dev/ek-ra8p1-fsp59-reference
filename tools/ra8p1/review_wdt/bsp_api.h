#ifndef BSP_API_H
#define BSP_API_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "bsp_feature.h"

#define FSP_HEADER
#define FSP_FOOTER
#define BSP_CMSE_NONSECURE_CALL
#define BSP_TZ_SECURE_BUILD 0
#define BSP_TZ_NONSECURE_BUILD 0
#define FSP_PARAMETER_NOT_USED(value) ((void) (value))
#define FSP_ERROR_RETURN(condition, error) do { if (!(condition)) { return (error); } } while (0)
#define FSP_ASSERT(condition) FSP_ERROR_RETURN(condition, FSP_ERR_ASSERTION)

typedef enum e_fsp_err
{
    FSP_SUCCESS,
    FSP_ERR_ASSERTION,
    FSP_ERR_ALREADY_OPEN,
    FSP_ERR_NOT_OPEN,
    FSP_ERR_UNSUPPORTED,
    FSP_ERR_INVALID_ARGUMENT,
    FSP_ERR_INVALID_STATE,
    FSP_ERR_NO_CALLBACK_MEMORY
} fsp_err_t;

typedef struct st_review_wdt_registers
{
    volatile uint8_t WDTRR;
    uint8_t reserved0;
    volatile uint16_t WDTCR;
    volatile uint16_t WDTSR;
    volatile uint8_t WDTRCR;
    uint8_t reserved1;
    volatile uint8_t WDTCSTPR;
    uint8_t padding[0x100 - 9];
} R_WDT0_Type;

extern R_WDT0_Type review_wdt_registers[2];
#define R_WDT0 (&review_wdt_registers[0])
#define R_WDT (&review_wdt_registers[0])

typedef struct st_review_wdt_icu
{
    volatile uint32_t NMIER;
} review_wdt_icu_t;
extern review_wdt_icu_t review_wdt_icu;
#define R_ICU (&review_wdt_icu)
#define R_ICU_NMIER_WDTEN_Msk (1U << 1)

typedef enum e_bsp_grp_irq { BSP_GRP_IRQ_WDT_ERROR = 1 } bsp_grp_irq_t;
typedef enum e_fsp_priv_clock { FSP_PRIV_CLOCK_PCLKB = 4 } fsp_priv_clock_t;
void R_BSP_GroupIrqWrite(bsp_grp_irq_t irq, void (* callback)(bsp_grp_irq_t));
uint32_t R_FSP_SystemClockHzGet(fsp_priv_clock_t clock);

#endif
