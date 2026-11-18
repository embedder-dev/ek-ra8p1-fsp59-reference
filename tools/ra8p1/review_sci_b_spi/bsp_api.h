#ifndef REVIEW_SCI_B_SPI_BSP_API_H
#define REVIEW_SCI_B_SPI_BSP_API_H
#define BSP_API_H
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "fsp_common_api.h"
#define BSP_CFG_XTAL_HZ (24000000U)
#define BSP_CMSE_NONSECURE_CALL
#define FSP_PRIV_CLOCK_PCLKA (0U)
#include "bsp_feature.h"
#define __IOM volatile
#define __IM volatile const
#define __OM volatile
#include "registers.h"

typedef int IRQn_Type;
extern R_SCI_B0_Type review_regs[10];
#define R_SCI0_BASE ((uintptr_t) &review_regs[0])
#define R_SCI1_BASE ((uintptr_t) &review_regs[1])
#define BSP_TZ_SECURE_BUILD (0)
#define BSP_TZ_NONSECURE_BUILD (0)
#define FSP_ASSERT(c) FSP_ERROR_RETURN(c, FSP_ERR_ASSERTION)
#define FSP_ERROR_RETURN(c,e) do { if (!(c)) { return (e); } } while (0)
#define FSP_CONTEXT_SAVE
#define FSP_CONTEXT_RESTORE
#define R_BSP_MODULE_START(ip,ch) ((void) (ch))
#define R_BSP_MODULE_STOP(ip,ch) ((void) (ch))
void review_poll(void);
#define FSP_HARDWARE_REGISTER_WAIT(a,b) do { while ((a) != (b)) { review_poll(); } } while (0)
void R_BSP_IrqCfgEnable(IRQn_Type irq, uint8_t priority, void * context);
void R_BSP_IrqDisable(IRQn_Type irq);
void R_BSP_IrqEnableNoClear(IRQn_Type irq);
void R_BSP_IrqStatusClear(IRQn_Type irq);
IRQn_Type R_FSP_CurrentIrqGet(void);
void * R_FSP_IsrContextGet(IRQn_Type irq);
uint32_t R_FSP_SystemClockHzGet(unsigned clock);
uint32_t R_FSP_SciSpiClockHzGet(void);
uint32_t R_FSP_SciClockHzGet(void);
#endif
