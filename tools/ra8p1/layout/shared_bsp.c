/* Behavioral assertions against production IRQ, group IRQ, protection and port code. */
#include "bsp_api.h"

R_SYSTEM_Type test_system;
R_ICU_Type test_icu;
R_ICU_COMMON_Type test_common;
R_CPSCU_Type test_cpscu;
R_PFS_Type test_pfs;
R_PMISC_Type test_pmisc;
R_MSTP_Type test_mstp;
test_nvic_t test_nvic;
unsigned test_critical_depth;
static unsigned read_count;
static unsigned callback_count;
static uint32_t callback_bits;
extern volatile uint16_t g_protect_counters[4];
extern bsp_grp_irq_cb_t g_bsp_group_irq_sources[BSP_FEATURE_ICU_NMIER_MAX_INDEX + 1];
void NMI_Handler(void);
fsp_err_t R_BSP_GroupIrqWrite(bsp_grp_irq_t irq, bsp_grp_irq_cb_t callback);

/* Includes bit 31, the next word, the final local IRQ and a PDM event. */
const bsp_interrupt_event_t g_interrupt_event_link_select[BSP_ICU_VECTOR_NUM_ENTRIES] =
{
    [0] = 31, [1] = 32, [95] = 193
};

void test_register_read(uint32_t value)
{
    (void) value;
    ++read_count;
}

void test_register_wait(uint32_t actual, uint32_t expected)
{
    assert(expected == 0U);
    assert(actual == test_icu.NMICLR);
    /* Emulate the effect of the clear register, not an interrupt source. */
    uint32_t cleared = test_icu.NMISR & ~test_icu.NMICLR;
    memcpy((unsigned char *) &test_icu + offsetof(R_ICU_Type, NMISR), &cleared, sizeof(cleared));
}

static void callback(bsp_grp_irq_t irq)
{
    ++callback_count;
    callback_bits |= 1U << irq;
}

int main(void)
{
    /* Nested clients must not relock each other's registers. */
    R_BSP_RegisterProtectDisable(BSP_REG_PROTECT_CGC);
    R_BSP_RegisterProtectDisable(BSP_REG_PROTECT_SAR);
    R_BSP_RegisterProtectDisable(BSP_REG_PROTECT_SAR);
#if BSP_TZ_NONSECURE_BUILD
    assert(test_system.PRCR_NS == 0xA511U);
    assert(test_system.PRCR_S == 0U);
#else
    assert(test_system.PRCR_S == 0xA511U);
    assert(test_system.PRCR_NS == 0U);
#endif
    assert(g_protect_counters[BSP_REG_PROTECT_SAR] == 2U);
    R_BSP_RegisterProtectEnable(BSP_REG_PROTECT_SAR);
    assert(g_protect_counters[BSP_REG_PROTECT_SAR] == 1U);
    R_BSP_RegisterProtectEnable(BSP_REG_PROTECT_SAR);
    R_BSP_RegisterProtectEnable(BSP_REG_PROTECT_CGC);
    R_BSP_RegisterProtectEnable(BSP_REG_PROTECT_CGC);
    assert(g_protect_counters[BSP_REG_PROTECT_CGC] == 0U);
    assert(read_count >= 4U);
    assert(test_critical_depth == 0U);

    memset(&test_cpscu, 0x5A, sizeof(test_cpscu));
    memset(&test_common, 0xA5, sizeof(test_common));
    bsp_irq_cfg();
    assert(test_icu.IELSR[0] == 31U);
    assert(test_icu.IELSR[1] == 32U);
    assert(test_icu.IELSR[95] == 193U);
    assert(test_icu.IELSR[2] == 0U);
#if BSP_TZ_NONSECURE_BUILD
    /* S-TYPE-6 routing is owned by the secure image, never written from NS. */
    assert(test_common.INTSELR[0] == 0xA5A5A5A5U);
#else
 #if BSP_CFG_CPU_CORE == 1
    assert(test_common.INTSELR[0] == (0xA5A5A5A5U | 0x80000000U));
    assert(test_common.INTSELR[1] == (0xA5A5A5A5U | 1U));
    assert(test_common.INTSELR[6] == (0xA5A5A5A5U | 2U));
 #else
    assert(test_common.INTSELR[0] == (0xA5A5A5A5U & ~0x80000000U));
    assert(test_common.INTSELR[1] == (0xA5A5A5A5U & ~1U));
    assert(test_common.INTSELR[6] == (0xA5A5A5A5U & ~2U));
 #endif
#endif
#if BSP_TZ_SECURE_BUILD
 #if BSP_CFG_CPU_CORE == 1
    assert(test_cpscu.ICUSARJ == 0xFFFFFFFCU);
    assert(test_cpscu.ICUSARK == 0xFFFFFFFFU);
    assert(test_cpscu.ICUSARL == 0x7FFFFFFFU);
    assert(test_cpscu.ICUSARG == 0x5A5A5A5AU);
 #else
    assert(test_cpscu.ICUSARG == 0xFFFFFFFCU);
    assert(test_cpscu.ICUSARH == 0xFFFFFFFFU);
    assert(test_cpscu.ICUSARI == 0x7FFFFFFFU);
    assert(test_cpscu.ICUSARJ == 0x5A5A5A5AU);
 #endif
    assert(test_nvic.ITNS[0] == 0xFFFFFFFCU);
    assert(test_nvic.ITNS[2] == 0x7FFFFFFFU);
#else
    assert(test_cpscu.ICUSARG == 0x5A5A5A5AU);
    assert(test_cpscu.ICUSARJ == 0x5A5A5A5AU);
#endif
    test_icu.IELSR[1] |= R_ICU_IELSR_IR_Msk | R_ICU_IELSR_DTCE_Msk;
    R_BSP_IrqClearPending((IRQn_Type) 1);
    assert(test_icu.IELSR[1] == (32U | R_ICU_IELSR_DTCE_Msk));
    assert(test_nvic.ICPR[0] == 2U);
    R_BSP_IrqCfgEnable((IRQn_Type) 1, 3U, &test_common);
    assert(R_FSP_IsrContextGet((IRQn_Type) 1) == &test_common);
    assert(test_nvic.IPR[1] == 0x30U);
    assert(test_nvic.ISER[0] == 2U);

    /* High NMI bits must reach the registered callback, and disabled sources must not. */
    uint32_t status = (1U << 1) | (1U << 17) | (1U << 18) | (1U << 20);
    memcpy((unsigned char *) &test_icu + offsetof(R_ICU_Type, NMISR), &status, sizeof(status));
    test_icu.NMIER = status & ~(1U << 18);
    assert(R_BSP_GroupIrqWrite(BSP_GRP_IRQ_WDT_ERROR, callback) == FSP_SUCCESS);
    assert(R_BSP_GroupIrqWrite(BSP_GRP_IRQ_MRAM_CODE_READ, callback) == FSP_SUCCESS);
    assert(R_BSP_GroupIrqWrite(BSP_GRP_IRQ_IPC, callback) == FSP_SUCCESS);
    NMI_Handler();
    assert(callback_count == 3U);
    assert(callback_bits == test_icu.NMIER);
    assert(test_icu.NMICLR == test_icu.NMIER);
    assert(test_icu.NMISR == (1U << 18));

    R_BSP_PinAccessEnable();
    R_BSP_PinAccessEnable();
    R_BSP_PinCfg(BSP_IO_PORT_06_PIN_00, 0U);
    R_BSP_PinWrite(BSP_IO_PORT_06_PIN_00, BSP_IO_LEVEL_HIGH);
    assert(test_pfs.PORT[6].PIN[0].PmnPFS == 5U);
    R_BSP_PinAccessDisable();
    assert(g_protect_pfswe_counter == 1U);
    R_BSP_PinAccessDisable();
    assert(g_protect_pfswe_counter == 0U);
#if FSP_PRIV_TZ_USE_SECURE_REGS
    assert(test_pmisc.PWPRS == 0x80U);
    assert(test_pmisc.PWPR == 0U);
#else
    assert(test_pmisc.PWPR == 0x80U);
    assert(test_pmisc.PWPRS == 0U);
#endif
    assert(test_critical_depth == 0U);

    test_mstp.MSTPCRA = 0xFFFFFFFFU;
    R_BSP_MODULE_START(FSP_IP_DMAC, 7);
    assert(test_mstp.MSTPCRA == (0xFFFFFFFFU & ~(1U << (22U + BSP_CFG_CPU_CORE))));
    R_BSP_MODULE_STOP(FSP_IP_DTC, 0);
    assert(test_mstp.MSTPCRA == 0xFFFFFFFFU);
    R_BSP_MODULE_START(FSP_IP_ADC, 0);
    assert(test_mstp.MSTPCRD == 0U);
    R_BSP_MODULE_STOP(FSP_IP_ADC, 0);
    assert(test_mstp.MSTPCRD == (1U << 21));
    /* HM 11.2.9 p.450: DAC0/DAC1 are independently gated at bits 20/19. */
    test_mstp.MSTPCRD = 0xFFFFFFFFU;
    R_BSP_MODULE_START(FSP_IP_DAC, 0);
    assert(test_mstp.MSTPCRD == (0xFFFFFFFFU & ~(1U << 20)));
    R_BSP_MODULE_START(FSP_IP_DAC, 1);
    assert(test_mstp.MSTPCRD == (0xFFFFFFFFU & ~((1U << 20) | (1U << 19))));
    R_BSP_MODULE_STOP(FSP_IP_DAC, 0);
    assert(test_mstp.MSTPCRD == (0xFFFFFFFFU & ~(1U << 19)));
    R_BSP_MODULE_STOP(FSP_IP_DAC, 1);
    assert(test_mstp.MSTPCRD == 0xFFFFFFFFU);
    test_mstp.MSTPCRC = 0xFFFFFFFFU;
    R_BSP_MODULE_START(FSP_IP_PDM, 2);
    assert(test_mstp.MSTPCRC == (0xFFFFFFFFU & ~(1U << 24)));
    R_BSP_MODULE_STOP(FSP_IP_PDM, 0);
    assert(test_mstp.MSTPCRC == 0xFFFFFFFFU);
    return 0;
}
