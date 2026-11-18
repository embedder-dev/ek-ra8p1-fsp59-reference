#ifndef REVIEW_PERIPHERAL_CAPABILITIES_BSP_H
#define REVIEW_PERIPHERAL_CAPABILITIES_BSP_H
#define BSP_API_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "fsp_common_api.h"
#define BSP_CFG_XTAL_HZ (24000000U)
#define BSP_CMSE_NONSECURE_CALL
#define BSP_TZ_SECURE_BUILD (0)
#define BSP_TZ_NONSECURE_BUILD (0)
#define BSP_CFG_PARAM_CHECKING_ENABLE CHECKS
#define __IOM volatile
#define __IM volatile const
#define __OM volatile
#include "bsp_feature.h"
#include "bsp_peripheral.h"
#include "registers.h"
typedef int IRQn_Type;
typedef unsigned fsp_priv_source_clock_t;
#define FSP_PRIV_CLOCK_PCLKD 0U
#define FSP_PRIV_CLOCK_PCLKA 1U
#define BSP_DELAY_UNITS_MICROSECONDS 0U
#define FSP_INVALID_VECTOR (-1)
#define FSP_IP_GPT 0U
#define FSP_IP_GPT_PDG 1U
#define FSP_IP_OSPI 2U
#define FSP_ASSERT(c) FSP_ERROR_RETURN(c, FSP_ERR_ASSERTION)
#define FSP_ERROR_RETURN(c,e) do { if (!(c)) return (e); } while (0)
#define FSP_RETURN(e) return (e)
#define FSP_CONTEXT_SAVE
#define FSP_CONTEXT_RESTORE
#define FSP_CRITICAL_SECTION_DEFINE
#define FSP_CRITICAL_SECTION_ENTER
#define FSP_CRITICAL_SECTION_EXIT
#define __STATIC_INLINE static inline
#define __DMB() ((void)0)
#define __NOP() ((void)0)
#define R_BSP_MODULE_START(ip,ch) review_module_start(ip,ch)
#define R_BSP_MODULE_STOP(ip,ch) ((void)(ch))
#define FSP_HARDWARE_REGISTER_WAIT(a,b) ((void)0)
void review_module_start(unsigned ip, unsigned channel);
uint32_t R_FSP_SystemClockHzGet(unsigned clock);
uint32_t R_BSP_SourceClockHzGet(fsp_priv_source_clock_t clock);
void R_BSP_SoftwareDelay(unsigned delay, unsigned units);
void R_BSP_IrqCfgEnable(IRQn_Type irq, uint8_t priority, void * context);
void R_BSP_IrqDisable(IRQn_Type irq);
void R_BSP_IrqClearPending(IRQn_Type irq);
void R_FSP_IsrContextSet(IRQn_Type irq, void * context);
void R_BSP_IrqEnable(IRQn_Type irq);
void R_BSP_IrqEnableNoClear(IRQn_Type irq);
void R_BSP_IrqStatusClear(IRQn_Type irq);
IRQn_Type R_FSP_CurrentIrqGet(void);
void * R_FSP_IsrContextGet(IRQn_Type irq);
#endif
