#define TX_SOURCE_CODE
#include "tx_api.h"
#include "tx_initialize.h"
#include "tx_thread.h"
#include "tx_timer.h"
#if TEST_NSC
#include "tz_context.h"
#endif

#define STR_(x) #x
#define STR(x) STR_(x)
static void finish(unsigned status, char const * message) __attribute__((noreturn));
#define CHECK(x) do { if (!(x)) finish(1, "FAIL " STR(__LINE__) ": " #x "\n"); } while (0)

static void finish(unsigned status, char const * message)
{
    register uint32_t operation __asm("r0") = 4;
    register char const * text __asm("r1") = message;
    __asm volatile("bkpt 0xab" : "+r"(operation) : "r"(text) : "memory");
    uint32_t exit_data[2] = {0x20026, status};
    operation = 0x20;
    register void * argument __asm("r1") = exit_data;
    __asm volatile("bkpt 0xab" : "+r"(operation) : "r"(argument) : "memory");
    for (;;) {}
}

TX_THREAD * _tx_thread_current_ptr;
TX_THREAD * _tx_thread_execute_ptr;
volatile UINT _tx_thread_preempt_disable;
ULONG _tx_timer_time_slice;
volatile ULONG _tx_thread_system_state;
ULONG _tx_thread_created_count;
TX_THREAD * _tx_thread_created_ptr;
VOID * _tx_initialize_unused_memory;
VOID * _tx_thread_system_stack_ptr;
uint32_t SystemCoreClock;
test_system_t test_system_s, test_system_ns;
static TX_THREAD ready;
static unsigned expected_ns, expected_sleep, expected_mode, wfi_count, delay_count, forbidden_alias;
static unsigned application_called, high_level_called;
static unsigned error_expected;

void _tx_initialize_high_level(void) { CHECK(!error_expected); high_level_called++; }
void tx_application_define(void * memory) { (void) memory; CHECK(!error_expected); application_called++; }
void _tx_timer_interrupt(void) { finish(1, "Unexpected timer interrupt\n"); }
void _tx_execution_thread_exit(void) {}
void _tx_execution_thread_enter(void) {}
void _tx_execution_initialize(void) {}

test_system_t * test_system(unsigned ns)
{
    if (TEST_NS && !ns) forbidden_alias++;
    return ns ? &test_system_ns : &test_system_s;
}

void R_BSP_SoftwareDelay(uint32_t count, unsigned units)
{
    CHECK(count == 1 && units == BSP_DELAY_UNITS_MICROSECONDS);
    delay_count++;
    _tx_thread_execute_ptr = &ready;
}

void test_wfi(void)
{
    CHECK(expected_sleep);
    CHECK(__get_PRIMASK() == 1);
    test_system_t * owner = expected_ns ? &test_system_ns : &test_system_s;
    test_system_t * other = expected_ns ? &test_system_s : &test_system_ns;
    CHECK(owner->LPSCR == 0);
    CHECK(other->LPSCR == 0xDU);
    uint16_t saved = expected_ns ? 0x19 : 0x39;
    uint16_t actual = expected_ns ? owner->PRCR_NS : owner->PRCR_S;
    CHECK(actual == (expected_mode ? (0xA502U | saved) : saved));
    wfi_count++;
    _tx_thread_execute_ptr = &ready;
}

void test_unrecoverable(void)
{
    CHECK(error_expected);
    CHECK(!application_called && !high_level_called);
    CHECK(__get_PRIMASK() == 1);
    CHECK(0U == (SysTick->CTRL & (SysTick_CTRL_ENABLE_Msk | SysTick_CTRL_TICKINT_Msk)));
    finish(0, "PASS fatal initialization gate\n");
}

static void idle_contract(void)
{
    static unsigned const modes[] = {0, 4, 5, 8, 9, 10};
    for (unsigned ns = 0; ns < 2; ns++)
    {
        for (unsigned i = 0; i < sizeof(modes) / sizeof(modes[0]); i++)
        {
            test_system_s = (test_system_t) {.PRCR_S = 0x39, .PRCR_NS = 0x19, .LPSCR = 0xD};
            test_system_ns = test_system_s;
            test_system_s.LPMSAR = test_system_ns.LPMSAR = ns ? 2 : 0;
            test_system_t * owner = ns ? &test_system_ns : &test_system_s;
            owner->LPSCR = modes[i];
            expected_ns = ns;
            expected_mode = modes[i];
            expected_sleep = BSP_CFG_RTOS_IDLE_SLEEP && (!TEST_NS || ns);
            wfi_count = delay_count = forbidden_alias = 0;
            _tx_thread_execute_ptr = 0;
            CHECK(_tx_port_wait_thread_ready() == &ready);
            CHECK(_tx_thread_current_ptr == &ready);
            CHECK(wfi_count == expected_sleep);
            CHECK(delay_count == !expected_sleep);
            CHECK(!forbidden_alias);
            CHECK(owner->LPSCR == modes[i]);
            if (expected_sleep && expected_mode)
            {
                CHECK((ns ? owner->PRCR_NS : owner->PRCR_S) == (0xA500U | (ns ? 0x19U : 0x39U)));
            }
            else
            {
                CHECK(owner->PRCR_NS == 0x19 && owner->PRCR_S == 0x39);
            }
        }
    }
}

#if TEST_NSC
extern void _tx_port_svc_handler(UINT * stack);
static UINT free_request(TX_THREAD * thread)
{
    /* Same exception frame and SVC immediate decoding as a real SVC 2, without changing security state. */
    static uint8_t const svc[2] = {2, 0xDF};
    UINT frame[8] = {0};
    frame[0] = (UINT) thread;
    frame[6] = (UINT) (svc + 2);
    _tx_port_svc_handler(frame);
    return frame[0];
}

static void free_contract(void)
{
    TX_THREAD first = {0}, second = {0};
    CHECK(TZ_InitContextSystem_S() == 1);
    first.tx_thread_secure_stack_context = TZ_AllocModuleContext_S(0);
    CHECK(first.tx_thread_secure_stack_context != 0);
    UINT id = first.tx_thread_secure_stack_context;
    CHECK(free_request(&first) == TX_SUCCESS);
    CHECK(first.tx_thread_secure_stack_context == 0);
    second.tx_thread_secure_stack_context = TZ_AllocModuleContext_S(0);
    CHECK(second.tx_thread_secure_stack_context == id);
    /* A deleted TCB must not release a slot reallocated to another thread. This is the real kernel delete. */
    first.tx_thread_state = TX_COMPLETED;
    first.tx_thread_created_next = first.tx_thread_created_previous = &first;
    _tx_thread_created_ptr = &first;
    _tx_thread_created_count = 1;
    CHECK(_tx_thread_delete(&first) == TX_SUCCESS);
    CHECK(TZ_FreeModuleContext_S(second.tx_thread_secure_stack_context) == 1);
    first.tx_thread_secure_stack_context = 9;
    CHECK(free_request(&first) == TX_THREAD_ERROR);
    CHECK(first.tx_thread_secure_stack_context == 9);
    first.tx_thread_secure_stack_context = 0;
    CHECK(free_request(&first) == TX_THREAD_ERROR);
    CHECK(first.tx_thread_secure_stack_context == 0);
    first.tx_thread_secure_stack_context = TZ_AllocModuleContext_S(0);
    CHECK(free_request(&first) == TX_SUCCESS);
    CHECK(first.tx_thread_secure_stack_context == 0);
}
#endif

static void initialize_contract(void)
{
#if TEST_TICK_RATE == -1
    _Static_assert(TX_TIMER_TICKS_PER_SECOND == 100UL, "Original ThreadX default must remain 100 Hz");
#endif
    /* Clear BASEPRI so the test can verify the initialization's selected posture. */
    __set_BASEPRI(0);
    __disable_irq();
#if TEST_CASE == 2
    SystemCoreClock = TEST_CORE ? 250000000U : 1000000000U;
    error_expected = 1;
#elif TEST_CASE == 3
    SystemCoreClock = (0x1000000U + 1) * TX_TIMER_TICKS_PER_SECOND;
    error_expected = 1;
#elif TEST_CASE == 4
    SystemCoreClock = TX_TIMER_TICKS_PER_SECOND - 1;
    error_expected = 1;
#elif TEST_CASE == 5
    SystemCoreClock = 0;
    error_expected = 1;
#else
    SystemCoreClock = TEST_CORE ? 250000000U : 1000000000U;
#endif
    _tx_thread_system_state = 0;
    if (error_expected && !TEST_NO_TIMER)
    {
        _tx_initialize_kernel_enter();
        finish(1, "Invalid initialization returned\n");
    }
    _tx_initialize_low_level();
#ifndef TX_NO_TIMER
    CHECK(SysTick->LOAD == SystemCoreClock / TX_TIMER_TICKS_PER_SECOND - 1);
    CHECK(SysTick->CTRL & SysTick_CTRL_ENABLE_Msk);
    CHECK(NVIC_GetPriority(SysTick_IRQn) == (TX_PORT_CFG_SYSTICK_IPL > TX_PORT_MAX_IPL ? TX_PORT_CFG_SYSTICK_IPL : TX_PORT_MAX_IPL));
    SysTick->CTRL = 0;
    SystemCoreClock = 0x1000000U * TX_TIMER_TICKS_PER_SECOND;
    _tx_initialize_low_level();
    CHECK(SysTick->LOAD == 0xFFFFFF);
    SysTick->CTRL = 0;
#else
    CHECK(0U == (SysTick->CTRL & (SysTick_CTRL_ENABLE_Msk | SysTick_CTRL_TICKINT_Msk)));
#endif
    CHECK(NVIC_GetPriority(SVCall_IRQn) == 15);
    CHECK(NVIC_GetPriority(PendSV_IRQn) == 15);
}

static uint8_t thread_stack[1024] __attribute__((aligned(8)));
static void scheduled_thread(void)
{
    uint32_t required = 8U * 4U;
#if __FPU_USED
    required += 16U * 4U + 4U;
#endif
    uint32_t expected = ((uint32_t) ready.tx_thread_stack_start + required + 7U) & ~7U;
    CHECK(__get_PSPLIM() == expected);
    finish(0, "PASS real PendSV aligned PSPLIM\n");
}

void Reset_Handler(void)
{
    SCB->VTOR = 0x10000000;
    SCB->CPACR |= 0xFU << 20;
    __DSB(); __ISB();
    if (TEST_CASE == 7)
    {
        ready.tx_thread_stack_start = thread_stack + TEST_STACK_OFFSET;
        ready.tx_thread_stack_end = thread_stack + sizeof(thread_stack) - 1;
        _tx_thread_stack_build(&ready, scheduled_thread);
        _tx_thread_execute_ptr = &ready;
        _tx_thread_schedule();
        finish(1, "Scheduler returned\n");
    }
    else if (TEST_CASE && TEST_CASE != 6)
    {
        initialize_contract();
    }
    else
    {
        if (TEST_CASE != 6) idle_contract();
#if TEST_NSC
        free_contract();
#endif
    }
    finish(0, "PASS production ThreadX fixture\n");
}
void Default_Handler(void) { finish(1, "Unexpected exception\n"); }
extern void SVC_Handler(void);
extern void PendSV_Handler(void);
extern void SysTick_Handler(void);
__attribute__((section(".vectors"), used)) void * __Vectors[16] = {
    (void *) 0x30008000, Reset_Handler, Default_Handler, Default_Handler,
    Default_Handler, Default_Handler, Default_Handler, Default_Handler,
    0, 0, 0,
#if TEST_NSC
    SVC_Handler,
#else
    Default_Handler,
#endif
    Default_Handler, 0, PendSV_Handler,
#if TEST_NO_TIMER
    Default_Handler
#else
    SysTick_Handler
#endif
};
