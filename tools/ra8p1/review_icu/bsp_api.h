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
#define FSP_CONTEXT_SAVE
#define FSP_CONTEXT_RESTORE
#define FSP_PARAMETER_NOT_USED(value) ((void) (value))
#define FSP_ERROR_RETURN(condition, error) do { if (!(condition)) { return (error); } } while (0)
#define FSP_ASSERT(condition) FSP_ERROR_RETURN(condition, FSP_ERR_ASSERTION)
#define FSP_INVALID_VECTOR ((IRQn_Type) -1)
#define BSP_IRQ_DISABLED 0xFFU

typedef int32_t IRQn_Type;
typedef enum e_fsp_err
{
    FSP_SUCCESS,
    FSP_ERR_ASSERTION,
    FSP_ERR_ALREADY_OPEN,
    FSP_ERR_NOT_OPEN,
    FSP_ERR_UNSUPPORTED,
    FSP_ERR_INVALID_ARGUMENT,
    FSP_ERR_IP_CHANNEL_NOT_PRESENT,
    FSP_ERR_IRQ_BSP_DISABLED,
    FSP_ERR_NO_CALLBACK_MEMORY
} fsp_err_t;

/* HM14.2.12: IRQCR0-15, four intervening bytes, IRQCR16-31.
 * The legacy aliases let the same complete driver compile for stock devices. */
typedef struct st_review_icu_irqcr_bits
{
    volatile uint8_t IRQMD : 2;
    volatile uint8_t reserved0 : 2;
    volatile uint8_t FCLKSEL : 2;
    volatile uint8_t reserved1 : 1;
    volatile uint8_t FLTEN : 1;
} review_icu_irqcr_bits_t;

typedef struct st_review_icu_registers
{
    union
    {
        volatile uint8_t IRQCR[36];
        volatile uint8_t IRQCRa[36];
        review_icu_irqcr_bits_t IRQCR_b[36];
        review_icu_irqcr_bits_t IRQCRa_b[36];
    };
    /* HM14.2.17: IELSR0-95, IR at bit16. */
    volatile uint32_t IELSR[96];
} review_icu_registers_t;

extern review_icu_registers_t review_icu[2];
extern review_icu_registers_t review_icu_common;
/* Count base accesses: a read/clear/restore cycle must not hide a vectorless access. */
review_icu_registers_t * review_icu_access(void);
#define R_ICU (review_icu_access())
#define R_ICU_COMMON (&review_icu_common)
#define R_ICU_IELSR_IR_Msk (0x00010000UL)

/* Required by the unchanged LOCO-filter path on older devices. */
#define R_ICU_IRQCR_LOCOSEL_Pos 6U
#define FSP_PRIV_CLOCK_LOCO 0
#define BSP_DELAY_LOOPS_CALCULATE(cycles) (cycles)
extern uint32_t SystemCoreClock;
uint32_t R_BSP_SourceClockHzGet(int clock);
void bsp_prv_software_delay_loop(uint32_t loops);

void R_BSP_IrqCfg(IRQn_Type irq, uint8_t ipl, void * context);
void R_BSP_IrqEnable(IRQn_Type irq);
void R_BSP_IrqDisable(IRQn_Type irq);
void R_BSP_IrqStatusClear(IRQn_Type irq);
void R_FSP_IsrContextSet(IRQn_Type irq, void * context);
void * R_FSP_IsrContextGet(IRQn_Type irq);
IRQn_Type R_FSP_CurrentIrqGet(void);

#endif
