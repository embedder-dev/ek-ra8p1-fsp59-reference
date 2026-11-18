/* Register/BSP boundary for complete ARM production-port compilation. */
#ifndef REVIEW_FREERTOS_BSP_H
#define REVIEW_FREERTOS_BSP_H
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#define BSP_FEATURE_BSP_HAS_SECONDARY_CORE TEST_TARGET
#define BSP_FEATURE_BSP_HAS_PRCR_S TEST_TARGET
#define BSP_FEATURE_BSP_HAS_SP_MON 0
#define BSP_FEATURE_LPM_HAS_SBYCR_SSBY 0
#define BSP_FEATURE_LPM_HAS_LPSCR 1
#define BSP_CFG_RTOS_IDLE_SLEEP 1
#ifndef RM_FREERTOS_PORT_CFG_HW_STACK_MONITOR_ENABLE
#define RM_FREERTOS_PORT_CFG_HW_STACK_MONITOR_ENABLE 0
#endif
#define BSP_DONT_REMOVE __attribute__((used))
#define BSP_FORCE_INLINE __attribute__((always_inline))
#define FSP_PARAMETER_NOT_USED(x) ((void) (x))
#define BSP_CFG_HANDLE_UNRECOVERABLE_ERROR(x) review_fatal(x)
#define BSP_DELAY_UNITS_MICROSECONDS 1
#define __NVIC_PRIO_BITS 4
#define __MPU_PRESENT 1
#define __DSP_PRESENT 1
#define __FPU_PRESENT TEST_FPU
#define __FPU_DP 1
#define __VTOR_PRESENT 1
#define __SAUREGION_PRESENT 1
#define __Vendor_SysTickConfig 0
#if BSP_CFG_CPU_CORE == 0
#define RENESAS_CORTEX_M85
#define __CM85_REV 0x0101
#include "review_irqs.h"
#include "core_cm85.h"
#else
#define RENESAS_CORTEX_M33
#define __CM33_REV 0x0004
#include "review_irqs.h"
#include "core_cm33.h"
#endif
struct review_system { volatile uint32_t PRCR, PRCR_S, PRCR_NS, LPSCR; };
struct review_mstp { volatile uint32_t MSTPCRA; };
extern struct review_system * const R_SYSTEM;
extern struct review_mstp * const R_MSTP;
#define R_SYSTEM_LPSCR_LPMD_Msk 3U
#define R_MSTP_MSTPCRA_MSTPA16_Msk (1UL << 16)
extern uint32_t SystemCoreClock;
void review_assert(uint32_t line);
void review_fatal(uint32_t error);
void R_BSP_SoftwareDelay(uint32_t, uint32_t);
IRQn_Type R_FSP_CurrentIrqGet(void);
#endif
