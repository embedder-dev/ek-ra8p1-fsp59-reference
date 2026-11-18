#ifndef REVIEW_THREADX_BSP_API_H
#define REVIEW_THREADX_BSP_API_H
#include <stdint.h>
#include <stddef.h>
#include "bsp_feature.h"

#define __NVIC_PRIO_BITS 4U
#define __MPU_PRESENT 0U
#define __FPU_PRESENT 1U
#define __DSP_PRESENT 1U
#define __ICACHE_PRESENT 0U
#define __DCACHE_PRESENT 0U
#define __Vendor_SysTickConfig 0U
typedef enum IRQn {
    NonMaskableInt_IRQn = -14, HardFault_IRQn = -13, MemoryManagement_IRQn = -12,
    BusFault_IRQn = -11, UsageFault_IRQn = -10, SecureFault_IRQn = -9,
    SVCall_IRQn = -5, DebugMonitor_IRQn = -4, PendSV_IRQn = -2, SysTick_IRQn = -1,
    Test_IRQn = 0
} IRQn_Type;
#if TEST_CORE == 0
#define RENESAS_CORTEX_M85
#include "core_cm85.h"
#else
#define RENESAS_CORTEX_M33
#include "core_cm33.h"
#endif

#define BSP_CFG_CPU_CORE TEST_CORE
#define BSP_TZ_NONSECURE_BUILD TEST_NS
#define BSP_TZ_SECURE_BUILD (!TEST_NS)
#define BSP_ALIGN_VARIABLE(n) __attribute__((aligned(n)))
#define BSP_CMSE_NONSECURE_ENTRY
#define FSP_PARAMETER_NOT_USED(x) ((void) (x))
#define BSP_DELAY_UNITS_MICROSECONDS 1
void R_BSP_SoftwareDelay(uint32_t count, unsigned units);
void test_wfi(void);
void test_unrecoverable(void);
extern uint32_t SystemCoreClock;
#define BSP_CFG_HANDLE_UNRECOVERABLE_ERROR(x) test_unrecoverable()
/* Register/idle model only. All other core intrinsics and SysTick_Config are original CMSIS. */
#undef __WFI
#define __WFI() test_wfi()

typedef struct {
    volatile uint16_t SBYCR;
    volatile uint16_t PRCR;
    volatile uint16_t PRCR_S;
    volatile uint16_t PRCR_NS;
    volatile uint32_t LPMSAR;
    volatile uint8_t LPSCR;
} test_system_t;
extern test_system_t test_system_s, test_system_ns;
test_system_t * test_system(unsigned ns);
#define R_SYSTEM test_system(TEST_NS)
#define R_SYSTEM_NS test_system(1)
/* HM 11.2.1, 11.2.21; these are independent of the candidate header. */
#define R_SYSTEM_LPMSAR_NONSEC1_Msk (1U << 1)
#define R_SYSTEM_LPSCR_LPMD_Msk 0xFU
#define R_SYSTEM_SBYCR_SSBY_Msk 0x8000U
#endif
