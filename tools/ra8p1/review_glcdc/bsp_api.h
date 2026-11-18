#ifndef REVIEW_GLCDC_BSP_H
#define REVIEW_GLCDC_BSP_H
#define BSP_API_H
#include "bsp_exceptions.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "fsp_common_api.h"
#define __PACKED_STRUCT struct __attribute__((packed))
#define __IOM volatile
#define __IM volatile const
#define __OM volatile
#if TEST_LEGACY == 1
#include "R7FA8D1BH.h"
#elif TEST_LEGACY == 2
#include "R7FA6M3AH.h"
#else
#include "R7KA8P1KF.h"
#endif
#undef R_GLCDC
extern R_GLCDC_Type review_regs;
R_GLCDC_Type * review_access(void);
#if TEST_OBJECT
#define R_GLCDC (&review_regs)
#else
#define R_GLCDC review_access()
#endif
#define FSP_CONTEXT_SAVE
#define FSP_CONTEXT_RESTORE
#define FSP_ERROR_RETURN(c,e) do { if (!(c)) return (e); } while (0)
#define FSP_ASSERT(c) FSP_ERROR_RETURN(c, FSP_ERR_ASSERTION)
#define R_BSP_MODULE_START(ip,ch) review_module(1)
#define R_BSP_MODULE_STOP(ip,ch) review_module(0)
#define BSP_DELAY_UNITS_MICROSECONDS 1
void review_module(int start);
void R_BSP_SoftwareDelay(uint32_t n, int unit);
void R_BSP_IrqDisable(IRQn_Type irq);
void R_BSP_IrqCfgEnable(IRQn_Type irq, uint32_t priority, void * context);
void R_BSP_IrqStatusClear(IRQn_Type irq);
IRQn_Type R_FSP_CurrentIrqGet(void);
#endif
