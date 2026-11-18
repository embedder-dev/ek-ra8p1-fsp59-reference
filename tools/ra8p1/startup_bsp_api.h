/* Controlled BSP configuration; register and CMSIS definitions are production inputs. */
#ifndef STARTUP_BSP_API_H
#define STARTUP_BSP_API_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#define BSP_TZ_CFG_SKIP_INIT 0
#define BSP_CFG_SKIP_INIT 0
#define BSP_CFG_EARLY_INIT 1
#define BSP_CFG_C_RUNTIME_INIT 1
#define BSP_CFG_PFS_PROTECT 1
#define BSP_CFG_BOOT_IMAGE 0
#define BSP_CFG_STACK_MAIN_BYTES 1024U
#define BSP_MOCO_HZ 8000000U
#define BSP_CFG_SECONDARY_CORE_START_ADDRESS 0x02080000U
#ifndef BSP_CFG_DCACHE_ENABLED
#define BSP_CFG_DCACHE_ENABLED 0
#endif
#define BSP_CMSE_NONSECURE_CALL
#define BSP_DONT_REMOVE __attribute__((used))
#define BSP_WEAK_REFERENCE __attribute__((weak))
#define BSP_SECTION_EARLY_INIT
#define FSP_PARAMETER_NOT_USED(x) ((void) (x))
#define FSP_REGISTER_READ(reg) ((void) (reg))
#define FSP_HARDWARE_REGISTER_WAIT(reg, value) while ((reg) != (value)) {}
#define BSP_REG_PROTECT_SAR 0
#define BSP_REG_PROTECT_OM_LPC_BATT 1
#define BSP_IO_PWPR_PFSWE_OFFSET 6U
#define FSP_PRIV_TZ_USE_SECURE_REGS (!BSP_TZ_NONSECURE_BUILD)
#define R_BSP_MODULE_START(ip, ch) ((void) 0)
#define R_BSP_MODULE_STOP(ip, ch) ((void) 0)
#define FSP_IP_TFU 0
#define FSP_IP_MACL 1
#if BSP_CFG_CPU_CORE == 0
#define RENESAS_CORTEX_M85
#endif
#include "bsp_feature.h"
#include "bsp_peripheral.h"
#include "bsp_exceptions.h"
#include "R7KA8P1KF.h"
#define BSP_TZ_CFG_TCMSAR 0U
#define BSP_TZ_CFG_TCMSABARC 0x10000U
#define BSP_TZ_CFG_TCMSABARS 0x10000U
#define BSP_TZ_CFG_DMACSAR 0U
#define BSP_TZ_CFG_DTCSAR 0U
#define BSP_TZ_CFG_EXCEPTION_RESPONSE 0U
#define BSP_TZ_CFG_PSARB 0U
#define BSP_TZ_CFG_PSARC 0U
#define BSP_TZ_CFG_PSARD 0U
#define BSP_TZ_CFG_PSARE 0U
#define BSP_TZ_CFG_MSSAR 0U
#define BSP_TZ_CFG_RSTSAR 0U
#define BSP_TZ_CFG_PVDSAR 0U
#define BSP_TZ_CFG_CGFSAR 0U
#define BSP_TZ_CFG_LPMSAR 0U
#define BSP_TZ_CFG_DPFSAR1 0U
#define BSP_TZ_CFG_ICUSARA 0U
#define BSP_TZ_CFG_ICUSARB 0U
#define BSP_TZ_CFG_ICUSARE 0U
#define BSP_TZ_CFG_ICUSARF 0U
#define BSP_TZ_CFG_MSAR 0U
#define BSP_TZ_CFG_SRAMSAR 0U
#define BSP_TZ_CFG_MMPUSARA 0U
#define BSP_TZ_CFG_BUSSARA 0U
#define BSP_TZ_CFG_BUSSARB 0U
#define BSP_TZ_CFG_BUSSARC 0U
#define BSP_TZ_CFG_NON_SECURE_APPLICATION_FALLBACK 0
extern uint32_t g_protect_pfswe_counter;
typedef void (*bsp_grp_irq_cb_t)(void *);
typedef enum {
    BSP_WARM_START_RESET, BSP_WARM_START_POST_CLOCK, BSP_WARM_START_POST_C
} bsp_warm_start_event_t;
void R_BSP_RegisterProtectDisable(unsigned reg);
void R_BSP_RegisterProtectEnable(unsigned reg);
void R_BSP_Init_RTC(void);
void bsp_clock_freq_var_init(void);
void bsp_clock_init(void);
void bsp_irq_cfg(void);
void bsp_init(void * args);
#endif
