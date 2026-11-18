#ifndef REVIEW_I3C_BSP_API_H
#define REVIEW_I3C_BSP_API_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "bsp_feature.h"
#define BSP_API_H
#define BSP_ALIGN_VARIABLE(n) __attribute__((aligned(n)))
#define BSP_FORCE_INLINE __attribute__((always_inline))
#define __IOM volatile
#define __IM volatile const
#define __OM volatile
#include "fsp_common_api.h"
#include "registers.h"
typedef int IRQn_Type;
extern R_I3C0_Type review_registers;
extern unsigned review_waits, review_starts, review_stops;
extern unsigned review_disabled, review_pending, review_context_cleared;
extern void * review_context;
extern const char * review_wait_expression;
void review_wait(const char * expression);
void review_stop(void);
#define R_I3C0 (&review_registers)
#define R_I3C1 (&review_registers)
#define FSP_ERROR_RETURN(c,e) do { if (!(c)) { return (e); } } while (0)
#define FSP_ASSERT(c) FSP_ERROR_RETURN(c, FSP_ERR_ASSERTION)
#define FSP_HARDWARE_REGISTER_WAIT(a,b) do { review_wait(#a); (void) (a); (void) (b); } while (0)
#define FSP_CONTEXT_SAVE
#define FSP_CONTEXT_RESTORE
#define R_BSP_MODULE_START(ip,ch) do { (void) (ch); review_starts++; } while (0)
#define R_BSP_MODULE_STOP(ip,ch) do { (void) (ch); review_stop(); } while (0)
static inline void R_BSP_IrqCfgEnable(int irq, unsigned ipl, void * ctx)
{ (void) irq; (void) ipl; review_context = ctx; }
static inline void R_BSP_IrqDisable(int irq) { review_disabled |= 1U << irq; }
static inline void R_BSP_IrqClearPending(int irq) { review_pending |= 1U << irq; }
static inline void R_BSP_IrqStatusClear(int irq) { (void) irq; }
static inline void R_BSP_IrqEnableNoClear(int irq) { (void) irq; }
static inline void R_FSP_IsrContextSet(int irq, void * ctx)
{ if (ctx == NULL) { review_context_cleared |= 1U << irq; } }
static inline int R_FSP_CurrentIrqGet(void) { return 5; }
static inline void * R_FSP_IsrContextGet(int irq) { (void) irq; return review_context; }
#endif
