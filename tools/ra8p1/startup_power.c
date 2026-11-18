/* Controlled graphics-domain state transitions; no physical target is accessed. */
#include <assert.h>
#include <stdint.h>
#ifndef BSP_TZ_NONSECURE_BUILD
#define BSP_TZ_NONSECURE_BUILD 0
#endif
#define FSP_PRIV_TZ_USE_SECURE_REGS (!BSP_TZ_NONSECURE_BUILD)
#define BSP_REG_PROTECT_OM_LPC_BATT 1U
#define R_SYSTEM_PGCSAR_NONSEC1_Msk 2U
#define R_SYSTEM_PDCTRGD_PDDE_Msk 1U
#define R_SYSTEM_PDCTRGD_PDCSF_Msk 0x40U
#define R_SYSTEM_PDCTRGD_PDPGSF_Msk 0x80U
static struct { volatile uint32_t PGCSAR; volatile uint8_t PDCTRGD; } regs;
#define R_SYSTEM (&regs)
static unsigned disabled, enabled, waits;
static void R_BSP_RegisterProtectDisable(unsigned reg) {
    assert(reg == BSP_REG_PROTECT_OM_LPC_BATT);
    assert(disabled == 0 && enabled == 0);
    disabled++;
}
static void R_BSP_RegisterProtectEnable(unsigned reg) {
    assert(reg == BSP_REG_PROTECT_OM_LPC_BATT);
    assert(disabled == 1 && enabled == 0 && regs.PDCTRGD == 0);
    enabled++;
}
static void settle(unsigned expected) {
    assert(disabled == 1 && enabled == 0);
    if (waits == 0) {
        assert(expected == 0);
        /* Complete any in-flight transition according to its requested PDDE state. */
        if ((regs.PDCTRGD & R_SYSTEM_PDCTRGD_PDCSF_Msk) != 0) {
            regs.PDCTRGD = (regs.PDCTRGD & R_SYSTEM_PDCTRGD_PDDE_Msk) ? 0x81U : 0U;
        }
    } else if (expected == R_SYSTEM_PDCTRGD_PDPGSF_Msk) {
        assert(regs.PDCTRGD == 0x81U);
    } else {
        assert(expected == 0 && regs.PDCTRGD == 0);
    }
    waits++;
}
#define FSP_HARDWARE_REGISTER_WAIT(reg, expected) do { settle(expected); assert((reg) == (expected)); } while (0)
/* PRODUCTION */
static void check(uint32_t attribution, uint8_t state, unsigned should_run, unsigned expected_waits) {
    disabled = enabled = waits = 0;
    regs.PGCSAR = attribution;
    regs.PDCTRGD = state;
    bsp_init_graphics_power_domain();
    assert(disabled == should_run && enabled == should_run);
    assert(waits == expected_waits);
    assert(regs.PDCTRGD == (should_run ? 0U : state));
    assert(regs.PGCSAR == attribution);
    if (should_run) {
        bsp_init_graphics_power_domain();
        assert(disabled == 1 && enabled == 1 && waits == expected_waits);
    }
}
int main(void) {
    /* NONSEC1 alone selects the domain owner; all unrelated attribution bits may differ. */
    uint32_t owned = BSP_TZ_NONSECURE_BUILD ? 0xffU : 0xfdU;
    uint32_t other = owned ^ R_SYSTEM_PGCSAR_NONSEC1_Msk;
    check(owned, 0x81U, 1, 3);  /* powered off */
    check(owned, 0xc1U, 1, 3);  /* power-off transition already in progress */
    check(owned, 0xc0U, 1, 2);  /* power-on transition already in progress */
    check(owned, 0x00U, 0, 0);  /* already on: no writes */
    check(other, 0x81U, 0, 0);  /* differently attributed: no access to the domain */
    return 0;
}
