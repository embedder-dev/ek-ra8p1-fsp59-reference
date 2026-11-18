/* Test configuration; kernel declarations are the unmodified original 11.1.0 pack. */
#ifndef REVIEW_FREERTOS_CONFIG_H
#define REVIEW_FREERTOS_CONFIG_H
#include "bsp_api.h"
#define configUSE_PREEMPTION 1
#define configUSE_PORT_OPTIMISED_TASK_SELECTION 0
#ifndef configUSE_TICKLESS_IDLE
#define configUSE_TICKLESS_IDLE 1
#endif
#define configUSE_IDLE_HOOK 1
#define configUSE_TICK_HOOK 0
#define configCPU_CLOCK_HZ SystemCoreClock
#ifndef configTICK_RATE_HZ
#define configTICK_RATE_HZ 1000
#endif
#define configMAX_PRIORITIES 5
#define configMINIMAL_STACK_SIZE 128
#define configTIMER_TASK_STACK_DEPTH 384
#define configUSE_TIMERS 1
#define configTIMER_TASK_PRIORITY 3
#define configTIMER_QUEUE_LENGTH 10
#define configUSE_16_BIT_TICKS 0
#define configSUPPORT_STATIC_ALLOCATION 1
#define configSUPPORT_DYNAMIC_ALLOCATION 0
#define configMAX_SYSCALL_INTERRUPT_PRIORITY 16
#define configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY 1
#define configENABLE_MPU 0
#define configPRE_SLEEP_PROCESSING(x) ((void) (x))
#define configPOST_SLEEP_PROCESSING(x) ((void) (x))
#if BSP_CFG_PARAM_CHECKING_ENABLE
#define configASSERT(x) do { if (!(x)) review_assert(__LINE__); } while (0)
#endif
#define INCLUDE_vTaskSuspend 1
#define INCLUDE_vTaskDelete 1
#endif
