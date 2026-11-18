/* Host-only register model for compiling the production shared BSP consumers.
 * Device layouts come from the generated header; processor primitives are test doubles.
 */
#ifndef RA8P1_SHARED_BSP_FIXTURE_H
#define RA8P1_SHARED_BSP_FIXTURE_H
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "bsp_exceptions.h"
#include "R7KA8P1KF.h"

#define FSP_HEADER
#define FSP_FOOTER
#define BSP_SECTION_FLASH_GAP
#define BSP_SECTION_EARLY_INIT
#define BSP_WEAK_REFERENCE __attribute__((weak))
#define __STATIC_INLINE static inline
#define BSP_VECTOR_TABLE_MAX_ENTRIES 112
#define BSP_CORTEX_VECTOR_TABLE_ENTRIES 16
#define BSP_ICU_VECTOR_NUM_ENTRIES 96
#define BSP_FEATURE_ICU_HAS_IELSR 1
#define BSP_FEATURE_ICU_FIXED_IELSR_COUNT 0
#define BSP_FEATURE_ICU_NMIER_MAX_INDEX 20
#define BSP_FEATURE_ICU_HAS_COMMON_REGS 1
#define BSP_FEATURE_BSP_HAS_PRCR_S 1
#define BSP_FEATURE_BSP_MSTP_PER_CORE_DMAC_DTC 1
#define BSP_FEATURE_BSP_MSTP_ADC_MSTPD21 1
#define BSP_PERIPHERAL_PDM_PRESENT 1
#define BSP_FEATURE_TZ_HAS_TRUSTZONE 1
#define BSP_FEATURE_TZ_VERSION 2
#define BSP_FEATURE_IOPORT_VERSION 2
#define BSP_CFG_PFS_PROTECT 1
#define BSP_CFG_MCU_PART_SERIES 8
#define BSP_CFG_PARAM_CHECKING_ENABLE 1
#define BSP_ALT_BUILD 0
#define FSP_PRIV_TZ_USE_SECURE_REGS (!BSP_TZ_NONSECURE_BUILD)
#define FSP_ASSERT(condition) assert(condition)
#define FSP_SUCCESS 0
#define FSP_CRITICAL_SECTION_DEFINE
#define FSP_CRITICAL_SECTION_ENTER (++test_critical_depth)
#define FSP_CRITICAL_SECTION_EXIT (--test_critical_depth)
#define FSP_REGISTER_READ(reg) test_register_read((uint32_t) (reg))
#define FSP_HARDWARE_REGISTER_WAIT(reg, value) test_register_wait((uint32_t) (reg), (value))
#define __DMB() ((void) 0)
#define __DSB() ((void) 0)
#define __ISB() ((void) 0)
#define __COMPILER_BARRIER() ((void) 0)
typedef int fsp_err_t;
typedef uint32_t bsp_interrupt_event_t;

extern R_SYSTEM_Type test_system;
extern R_ICU_Type test_icu;
extern R_ICU_COMMON_Type test_common;
extern R_CPSCU_Type test_cpscu;
extern R_PFS_Type test_pfs;
extern R_PMISC_Type test_pmisc;
extern R_MSTP_Type test_mstp;
#undef R_SYSTEM
#undef R_ICU
#undef R_ICU_COMMON
#undef R_CPSCU
#undef R_PFS
#undef R_PMISC
#undef R_MSTP
#define R_SYSTEM (&test_system)
#define R_ICU (&test_icu)
#define R_ICU_COMMON (&test_common)
#define R_CPSCU (&test_cpscu)
#define R_PFS (&test_pfs)
#define R_PMISC (&test_pmisc)
#define R_MSTP (&test_mstp)
extern unsigned test_critical_depth;
void test_register_read(uint32_t value);
void test_register_wait(uint32_t actual, uint32_t expected);
typedef struct
{
    uint32_t ICPR[3];
    uint32_t ISER[3];
    uint32_t ICER[3];
    uint32_t ITNS[3];
    uint8_t IPR[96];
} test_nvic_t;
extern test_nvic_t test_nvic;
#define NVIC (&test_nvic)
#define NVIC_SetPriority(irq, priority) (NVIC->IPR[(irq)] = (uint8_t) ((priority) << 4))

#include "bsp_override.h"
#include "bsp_register_protection.h"
void R_BSP_RegisterProtectEnable(bsp_reg_protect_t protection);
void R_BSP_RegisterProtectDisable(bsp_reg_protect_t protection);
#include "bsp_irq.h"
#include "bsp_group_irq.h"
#include "bsp_io.h"
#include "bsp_module_stop.h"
#endif
