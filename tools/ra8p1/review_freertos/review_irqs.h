typedef enum { NonMaskableInt_IRQn = -14, HardFault_IRQn = -13,
               MemoryManagement_IRQn = -12, BusFault_IRQn = -11, UsageFault_IRQn = -10,
               SecureFault_IRQn = -9, SVCall_IRQn = -5, DebugMonitor_IRQn = -4,
               PendSV_IRQn = -2, SysTick_IRQn = -1, Test_IRQn = 0 } IRQn_Type;
