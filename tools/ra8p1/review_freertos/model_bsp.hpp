/* Delayed SysTick model: writes to VAL do not load the counter until a later source-clock edge.
 * Armv8-M Exception Model User Guide, Basic SysTick Timer Operation; HM 2.12. */
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#define BSP_FEATURE_BSP_HAS_SECONDARY_CORE TEST_TARGET
#define BSP_FEATURE_BSP_HAS_PRCR_S TEST_TARGET
#define BSP_FEATURE_BSP_HAS_SP_MON 0
#define BSP_FEATURE_LPM_HAS_SBYCR_SSBY 0
#define BSP_FEATURE_LPM_HAS_LPSCR 1
#define BSP_CFG_RTOS_IDLE_SLEEP 1
#define BSP_DONT_REMOVE __attribute__((used))
#define BSP_FORCE_INLINE __attribute__((always_inline))
#define FSP_PARAMETER_NOT_USED(x) ((void) (x))
#define BSP_CFG_HANDLE_UNRECOVERABLE_ERROR(x) review_fatal(x)
#define RM_FREERTOS_PORT_CFG_HW_STACK_MONITOR_ENABLE 0
#define RENESAS_CORTEX_M85 1
#define __NVIC_PRIO_BITS 4
#define __FPU_USED TEST_FPU
#define SysTick_CTRL_ENABLE_Msk 1U
#define SysTick_CTRL_TICKINT_Msk 2U
#define SysTick_CTRL_CLKSOURCE_Msk 4U
#define SysTick_CTRL_COUNTFLAG_Msk (1U << 16)
#define SCB_SCR_SLEEPDEEP_Msk 4U
#define SCB_ICSR_PENDSTSET_Msk (1U << 26)
#define SCB_ICSR_PENDSVSET_Msk (1U << 28)
#define SCB_ICSR_VECTPENDING_Msk (0x1ffU << 12)
#define SCB_ICSR_VECTACTIVE_Msk 0x1ffU
#define R_SYSTEM_LPSCR_LPMD_Msk 3U
#define R_MSTP_MSTPCRA_MSTPA16_Msk (1UL << 16)
#define BSP_DELAY_UNITS_MICROSECONDS 1
#define PendSV_IRQn (-2)
#define SysTick_IRQn (-1)
typedef int IRQn_Type;
struct System { uint32_t PRCR, PRCR_S, PRCR_NS, LPSCR; };
struct Scb { uint32_t SCR, ICSR; };
struct Mstp { uint32_t MSTPCRA; };
static System system_regs;
static Scb scb_regs;
static Mstp mstp_regs;
#define R_SYSTEM (&system_regs)
#define SCB (&scb_regs)
#define R_MSTP (&mstp_regs)
static uint32_t SystemCoreClock = 24000000U;
static uint32_t tick_load, tick_val, tick_ctrl, countflag, latch_delay, first_latched;
static uint32_t sleep_counts, tick_steps, tick_increments, sleeps, nops, enables, wfi_nops;
static bool reload_pending, irq_disabled, abort_sleep, wake_restarts_npu;
static jmp_buf fatal_jump;
static void edge(void)
{
    if (!(tick_ctrl & SysTick_CTRL_ENABLE_Msk)) return;
    if (reload_pending)
    {
        if (latch_delay) { --latch_delay; return; }
        tick_val = tick_load;
        reload_pending = false;
        if (first_latched == UINT32_MAX) first_latched = tick_load;
    }
    else if (tick_val)
    {
        if (--tick_val == 0)
        {
            countflag = SysTick_CTRL_COUNTFLAG_Msk;
            if (tick_ctrl & SysTick_CTRL_TICKINT_Msk) SCB->ICSR |= SCB_ICSR_PENDSTSET_Msk;
            reload_pending = true;
        }
    }
}
struct Register
{
    unsigned id;
    operator uint32_t() const
    {
        /* Deliberately delay latching a fractional reload across several MMIO accesses. */
        edge();
        if (id == 0) return tick_load;
        if (id == 1) return tick_val;
        uint32_t result = tick_ctrl | countflag;
        countflag = 0;
        return result;
    }
    void operator=(uint32_t value)
    {
        if (id == 0) tick_load = value;
        else if (id == 1)
        {
            tick_val = 0;
            reload_pending = true;
            latch_delay = 4;
            first_latched = UINT32_MAX;
            countflag = 0;
        }
        else tick_ctrl = value & ~SysTick_CTRL_COUNTFLAG_Msk;
    }
};
struct Tick { Register LOAD{0}, VAL{1}, CTRL{2}; };
static Tick systick_regs;
#define SysTick (&systick_regs)
static void __disable_irq(void) { irq_disabled = true; }
static void __enable_irq(void) { irq_disabled = false; ++enables; }
static void __DSB(void) {}
static void __ISB(void) {}
static void __NOP(void) { ++nops; }
static uint32_t __get_BASEPRI(void) { return 0; }
static void __set_BASEPRI(uint32_t) {}
static uint32_t __get_PRIMASK(void) { return irq_disabled; }
static void __set_PRIMASK(uint32_t value) { irq_disabled = value; }
static uint32_t __get_CONTROL(void) { return 0; }
static uint32_t __get_IPSR(void) { return 0; }
static void __BKPT(unsigned) {}
static void NVIC_SetPriority(int, uint32_t) {}
static uint32_t NVIC_GetPriority(int) { return 15; }
static uint32_t NVIC_GetPriorityGrouping(void) { return 0; }
static IRQn_Type R_FSP_CurrentIrqGet(void) { return -1; }
static void review_fatal(uint32_t) { longjmp(fatal_jump, 1); }
static void review_assert(uint32_t) { assert(!"production configASSERT"); }
static void R_BSP_SoftwareDelay(uint32_t, uint32_t) {}
static uint32_t SysTick_Config(uint32_t counts)
{
    if (counts == 0 || counts > 0x1000000U) return 1;
    SysTick->LOAD = counts - 1;
    SysTick->VAL = 0;
    SysTick->CTRL = 7;
    return 0;
}
static void __WFI(void)
{
    assert(irq_disabled);
    assert(!(SCB->SCR & SCB_SCR_SLEEPDEEP_Msk));
    ++sleeps;
    wfi_nops = nops;
    if (wake_restarts_npu) R_MSTP->MSTPCRA = 0;
    /* Advance only source-clock time in WFI, without conflating MMIO with the requested sleep duration. */
    if (sleep_counts)
    {
        uint32_t budget = tick_load + 1;
        reload_pending = false;
        latch_delay = 0;
        if (sleep_counts < budget) tick_val = budget - sleep_counts;
        else
        {
            countflag = SysTick_CTRL_COUNTFLAG_Msk;
            SCB->ICSR |= SCB_ICSR_PENDSTSET_Msk;
            uint32_t after = sleep_counts - budget;
            tick_val = after ? (tick_load - after) : 0;
            reload_pending = !after;
        }
    }
}
