/* Included after unmodified kernel headers and selected production C function bodies. */
extern "C" eSleepModeStatus eTaskConfirmSleepModeStatus(void)
{
    return abort_sleep ? eAbortSleep : eStandardSleep;
}
extern "C" void vTaskStepTick(TickType_t ticks)
{
    assert(irq_disabled);
    tick_steps += ticks;
    assert(tick_steps <= 9U); /* The independently specified next unblock point is tick 10. */
}
extern "C" BaseType_t xTaskIncrementTick(void) { ++tick_increments; return pdFALSE; }

int main(int argc, char ** argv)
{
    assert(argc == 2);
    SystemCoreClock = 1000000U;
#if 0 == portNVIC_SYSTICK_CLK_BIT
    SystemCoreClock = 24000000U;
#endif
    if (argv[1][0] == 'i')
    {
        SystemCoreClock = 24000000U;
        if (!setjmp(fatal_jump))
        {
            vPortSetupTimerInterrupt();
            assert(!"invalid timer setup was accepted");
        }
        assert(tick_ctrl == 0U);
        return 0;
    }
    vPortSetupTimerInterrupt();
    assert(tick_load == 999U);
#if 0 == portNVIC_SYSTICK_CLK_BIT
    assert((tick_ctrl & 4U) == 0U);
#else
    assert((tick_ctrl & 4U) != 0U);
#endif
    tick_val = 800U;
    reload_pending = false;
    first_latched = UINT32_MAX;
    if (argv[1][0] == 's')
    {
        SystemCoreClock = 1000000000U;
        R_MSTP->MSTPCRA = 0U;
        SCB->SCR = 0x16U;
        R_SYSTEM->LPSCR = 3U;
        R_SYSTEM->PRCR_S = R_SYSTEM->PRCR_NS = 5U;
        __disable_irq();
        rm_freertos_port_sleep_preserving_lpm(1U);
#if BSP_CFG_CPU_CORE == 0
        assert(sleeps == 0U && nops == 0U); /* No permission to stop the NPU. */
#else
        assert(sleeps == 1U && nops == 0U);
#endif
        assert(R_MSTP->MSTPCRA == 0U);
        assert(SCB->SCR == 0x16U && R_SYSTEM->LPSCR == 3U);
        assert(irq_disabled); /* Tickless must restore the timebase before interrupts run. */
        sleeps = nops = 0;
        R_MSTP->MSTPCRA = 1U << 16;
        wake_restarts_npu = true; /* Return wait must use entry conditions even if the owner restarts the NPU. */
        rm_freertos_port_sleep_preserving_lpm(1U);
        assert(sleeps == 1U);
#if BSP_CFG_CPU_CORE == 0
        assert(wfi_nops >= 30000U && nops - wfi_nops >= 30000U);
#else
        assert(nops == 0U);
#endif
        assert(SCB->SCR == 0x16U && R_SYSTEM->LPSCR == 3U);
        assert(R_MSTP->MSTPCRA == 0U);
        SystemCoreClock = 24000000U;
        nops = sleeps = 0;
        rm_freertos_port_sleep_preserving_lpm(1U);
        assert(sleeps == 1U && nops == 0U);
        return 0;
    }
    if (argv[1][0] == 'a')
    {
        abort_sleep = true;
        vPortSuppressTicksAndSleep(10U);
        assert(tick_val == 800U && tick_load == 999U && tick_steps == 0U && sleeps == 0U);
        return 0;
    }
    if (argv[1][0] == 'p')
    {
        SCB->ICSR |= SCB_ICSR_PENDSTSET_Msk;
        vPortSuppressTicksAndSleep(10U);
        assert(tick_val == 800U && tick_load == 999U && tick_steps == 0U && sleeps == 0U);
        return 0;
    }
    uint32_t expected_steps = 0U, expected_remaining = 550U;
    sleep_counts = 250U;
    switch (argv[1][0])
    {
        case 'z': sleep_counts = 0U; expected_remaining = 800U; break;
        case 'o': sleep_counts = 799U; expected_remaining = 2U; break; /* One clock rounds up to a nonzero LOAD. */
        case 'b': sleep_counts = 800U; expected_steps = 1U; expected_remaining = 1000U; break;
        case 'c': sleep_counts = 1250U; expected_steps = 1U; expected_remaining = 550U; break;
        case 'x': sleep_counts = 9800U; expected_steps = 9U; expected_remaining = 1000U; break;
        case 'l': sleep_counts = 9850U; expected_steps = 9U; expected_remaining = 950U; break;
        default: break;
    }
    vPortSuppressTicksAndSleep(10U);
    assert(tick_steps == expected_steps);
    assert(first_latched == expected_remaining - 1U); /* Delayed reload, independently expected countdown. */
    assert(tick_load == 999U);
    assert(!irq_disabled);
    if (SCB->ICSR & SCB_ICSR_PENDSTSET_Msk)
    {
        SysTick_Handler();
        assert(tick_steps + tick_increments == 10U);
    }
    return 0;
}
