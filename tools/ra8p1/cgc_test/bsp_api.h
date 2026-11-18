#ifndef BSP_API_H
#define BSP_API_H
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define FSP_HEADER
#define FSP_FOOTER
#define BSP_CMSE_NONSECURE_CALL
#define BSP_TZ_SECURE_BUILD 0
#define BSP_TZ_NONSECURE_BUILD 0
#define BSP_ALT_BUILD 0
#define BSP_CFG_CPU_CORE TEST_CORE
#define BSP_CFG_USE_LOW_VOLTAGE_MODE 0
#define BSP_CFG_XTAL_HZ TEST_XTAL_HZ
#define BSP_HOCO_HZ 48000000U
#define BSP_MOCO_HZ 8000000U
#define BSP_CFG_CLOCK_SOURCE 1
#define BSP_CFG_FLL_ENABLE TEST_FLL
#define BSP_CFG_SLEEP_MODE_DELAY_ENABLE 0
#define BSP_CFG_RTOS_SLEEP_MODE_DELAY_ENABLE 0
#define FSP_PRV_SCKDIVCR_DIV_MASK 15U
#define FSP_PARAMETER_NOT_USED(value) ((void) (value))
#define FSP_ERROR_RETURN(condition, error) do { if (!(condition)) return (error); } while (0)
#define FSP_ASSERT(condition) FSP_ERROR_RETURN(condition, FSP_ERR_ASSERTION)
#define FSP_RETURN(error) return (error)
#define FSP_HARDWARE_REGISTER_WAIT(reg, value) cgc_test_wait((uint32_t) (reg), (uint32_t) (value), #reg)

typedef enum e_fsp_err {
    FSP_SUCCESS, FSP_ERR_ASSERTION, FSP_ERR_ALREADY_OPEN, FSP_ERR_NOT_OPEN,
    FSP_ERR_IN_USE, FSP_ERR_CLOCK_ACTIVE, FSP_ERR_OSC_STOP_DET_ENABLED,
    FSP_ERR_NOT_STABILIZED, FSP_ERR_PLL_SRC_INACTIVE, FSP_ERR_INVALID_STATE,
    FSP_ERR_CLOCK_INACTIVE, FSP_ERR_LOW_VOLTAGE_MODE, FSP_ERR_UNSUPPORTED,
    FSP_ERR_OSC_STOP_DETECTED, FSP_ERR_OSC_STOP_CLOCK_ACTIVE,
    FSP_ERR_INVALID_HW_CONDITION, FSP_ERR_NO_CALLBACK_MEMORY
} fsp_err_t;

#include "bsp_feature.h"
#ifdef TEST_BCLKA
 #undef BSP_FEATURE_BSP_HAS_BCLKA_CLOCK
 #define BSP_FEATURE_BSP_HAS_BCLKA_CLOCK TEST_BCLKA
#endif
#ifdef TEST_ESW
 #undef BSP_FEATURE_BSP_HAS_ESW_CLOCK
 #define BSP_FEATURE_BSP_HAS_ESW_CLOCK TEST_ESW
#endif
#if TEST_TARGET != 2
 #include "bsp_override.h"
#endif
#include "bsp_group_irq.h"
#if TEST_TARGET == 1
 #include "R7KA8P1KF.h"
#elif TEST_TARGET == 2
 #include "R7FA4M3AF.h"
#else
 #include "R7FA8M1AH.h"
#endif
#include "bsp_clocks.h"

extern R_SYSTEM_Type cgc_test_system;
extern R_ICU_Type cgc_test_icu;
#undef R_SYSTEM
#undef R_ICU
#define R_SYSTEM (&cgc_test_system)
#define R_ICU (&cgc_test_icu)
#define BSP_REG_PROTECT_CGC 1U
#define BSP_REG_PROTECT_OM_LPC_BATT 2U
#define BSP_DELAY_UNITS_MICROSECONDS 1U
#define FSP_PRIV_CLOCK_PLL1P 5U
void cgc_test_wait(uint32_t actual, uint32_t expected, char const * reg);
void R_BSP_RegisterProtectDisable(uint32_t mask);
void R_BSP_RegisterProtectEnable(uint32_t mask);
void R_BSP_SoftwareDelay(uint32_t delay, uint32_t units);
void R_BSP_FlashCacheDisable(void);
void R_BSP_FlashCacheEnable(void);
void R_BSP_GroupIrqWrite(bsp_grp_irq_t irq, void (* callback)(bsp_grp_irq_t));
uint32_t R_BSP_SourceClockHzGet(uint32_t source);
extern uint32_t SystemCoreClock;
#endif
