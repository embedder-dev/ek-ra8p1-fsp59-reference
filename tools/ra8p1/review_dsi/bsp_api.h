#ifndef REVIEW_DSI_BSP_API_H
#define REVIEW_DSI_BSP_API_H
#define BSP_API_H
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "fsp_common_api.h"
#include "bsp_exceptions.h"
#if TEST_TARGET
 #include "R7KA8P1KF.h"
#else
 #include "R7FA8D1BH.h"
#endif
#undef R_DSILINK
#undef R_DPHYCNT
#undef R_GLCDC
R_DSILINK_Type * review_dsi(void);
R_DPHYCNT_Type * review_phy(void);
R_GLCDC_Type * review_glcdc(void);
#define R_DSILINK review_dsi()
#define R_DPHYCNT review_phy()
#define R_GLCDC review_glcdc()
#define BSP_CMSE_NONSECURE_CALL
#define FSP_CONTEXT_SAVE
#define FSP_CONTEXT_RESTORE
#define __PACKED_STRUCT struct __attribute__((packed))
#define FSP_ERROR_RETURN(c,e) do { if (!(c)) return (e); } while (0)
#define FSP_ASSERT(c) FSP_ERROR_RETURN(c, FSP_ERR_ASSERTION)
/* Register waits model only peripheral completion; production writes are intact. */
#define FSP_HARDWARE_REGISTER_WAIT(r,v) do { review_wait(); } while (0)
#define R_BSP_MODULE_START(ip,ch) review_module_start()
#define R_BSP_MODULE_STOP(ip,ch) review_module_stop()
#define FSP_PRIV_CLOCK_PCLKA 0
#define CMSE_AU_NONSECURE 1
void * review_cmse(void * p, size_t size, unsigned flags);
#define cmse_check_address_range(p,s,f) review_cmse((p),(s),(f))
#define cmse_is_nsfptr(p) (!((uintptr_t) (p) & 1U))
void review_wait(void);
void review_module_start(void);
void review_module_stop(void);
uint32_t R_FSP_SystemClockHzGet(int clock);
void R_BSP_IrqCfgEnable(IRQn_Type irq, uint32_t ipl, void * context);
void R_BSP_IrqDisable(IRQn_Type irq);
void R_FSP_IsrContextSet(IRQn_Type irq, void * context);
void * R_FSP_IsrContextGet(IRQn_Type irq);
IRQn_Type R_FSP_CurrentIrqGet(void);
void R_BSP_IrqStatusClear(IRQn_Type irq);
#endif
