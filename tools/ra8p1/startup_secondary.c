/* Controlled register test of the production secondary-core release function. */
#include <assert.h>
#include <stdint.h>
#define BSP_PRV_PRCR_KEY 0xA500U
#define BSP_CFG_SECONDARY_CORE_START_ADDRESS 0x02080000U
#define R_CPU_CTRL_CPU1ACTCSR_ACT_Msk 0x80U
#define R_CPU_CTRL_CPU1ACTCSR_ACTREQ_Msk 1U
#define R_CPU_CTRL_CPU1WAITCR_CPUWAIT_Msk 1U
#define R_CPU_CTRL_CPU1CRPT_PROTECT_Msk 1U
static struct {
    uint16_t CPU1CRPT;
    uint8_t CPU1WAITCR;
    uint32_t CPU1INITVTOR;
    uint16_t CPU1ACTCSR;
} regs;
#define R_CPU_CTRL (&regs)
static unsigned barriers;
static void barrier(void) {
    assert(regs.CPU1INITVTOR == 0x02080000U);
    if (barriers == 0) {
        assert(regs.CPU1CRPT == 0xA500U);
        assert(regs.CPU1WAITCR == 1 && regs.CPU1ACTCSR == 0);
    } else if (barriers == 1) {
        assert(regs.CPU1WAITCR == 1 && regs.CPU1ACTCSR == 0x80U);
    } else {
        assert(barriers == 2);
        assert(regs.CPU1WAITCR == 0 && regs.CPU1CRPT == 0xA501U);
    }
    barriers++;
}
#define __DSB() barrier()
#define FSP_HARDWARE_REGISTER_WAIT(reg, expected) do { \
    assert(regs.CPU1ACTCSR == 0xA501U); \
    assert(regs.CPU1WAITCR == 1 && barriers == 1); \
    regs.CPU1ACTCSR = 0x80U; \
    assert((reg) == (expected)); \
} while (0)
/* PRODUCTION */
int main(void) {
    regs.CPU1CRPT = 1;
    bsp_start_secondary_core();
    assert(barriers == 3);
    assert(regs.CPU1WAITCR == 0 && regs.CPU1ACTCSR == 0x80U);
    bsp_start_secondary_core();
    assert(barriers == 3);
    assert(regs.CPU1WAITCR == 0 && regs.CPU1CRPT == 0xA501U);
    return 0;
}
