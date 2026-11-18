#ifndef BSP_API_H
#define BSP_API_H
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include "fsp_common_api.h"
#include "bsp_feature.h"
#include "bsp_elc.h"
#include "bsp_override.h"
#if TEST_TARGET
#include "R7KA8P1KF.h"
#elif TEST_LEGACY_RA6T2
#include "R7FA6T2BD.h"
#else
#include "R7FA8M1AH.h"
#endif
extern R_SYSTEM_Type test_system;
extern R_ICU_Type test_icu[2];
#undef R_SYSTEM
#undef R_ICU
#define R_SYSTEM (&test_system)
#define R_ICU (&test_icu[BSP_CFG_CPU_CORE])
#if TEST_TARGET
extern R_ICU_COMMON_Type test_common;
#undef R_ICU_COMMON
#define R_ICU_COMMON (&test_common)
#endif
/* Retain real assertion line-number behavior for legacy object comparison. */
void review_assert(unsigned line);
#define FSP_ERROR_RETURN(condition, error) { if (!(condition)) { return (error); } }
#define FSP_ASSERT(condition) do { if (!(condition)) { review_assert(__LINE__); return FSP_ERR_ASSERTION; } } while (0)
static inline void review_register_wait(uint32_t value, uint32_t expected) { assert(value == expected); }
#define FSP_HARDWARE_REGISTER_WAIT(value, expected) review_register_wait((value), (expected))
#define FSP_STYPE3_REG8_READ(value, secure) (value)
#define BSP_REG_PROTECT_OM_LPC_BATT 1
#define BSP_REG_PROTECT_CGC 2
void R_BSP_RegisterProtectDisable(int protect);
void R_BSP_RegisterProtectEnable(int protect);
#endif
