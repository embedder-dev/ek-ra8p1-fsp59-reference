#include "r_icu.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

review_icu_registers_t review_icu[2];
review_icu_registers_t review_icu_common;
uint32_t SystemCoreClock = 100000000U;

static unsigned irq_cfg_calls;
static unsigned bank_accesses;
static IRQn_Type configured_irq;
static void * configured_context;
static uint8_t configured_ipl;
static icu_extended_cfg_t extension = { .filter_src = EXTERNAL_IRQ_DIGITAL_FILTER_PCLK_DIV };

#define REQUIRE(condition) do { if (!(condition)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); return 1; \
} } while (0)

review_icu_registers_t * review_icu_access(void)
{
    ++bank_accesses;
    return &review_icu[BSP_CFG_CPU_CORE];
}

void R_BSP_IrqCfg(IRQn_Type irq, uint8_t ipl, void * context)
{
    ++irq_cfg_calls;
    configured_irq = irq;
    configured_context = context;
    configured_ipl = ipl;
}

void R_BSP_IrqEnable(IRQn_Type irq) { (void) irq; }
void R_BSP_IrqDisable(IRQn_Type irq) { (void) irq; }
void R_BSP_IrqStatusClear(IRQn_Type irq) { (void) irq; }
void R_FSP_IsrContextSet(IRQn_Type irq, void * context) { (void) irq; (void) context; }
void * R_FSP_IsrContextGet(IRQn_Type irq) { (void) irq; return configured_context; }
IRQn_Type R_FSP_CurrentIrqGet(void) { return configured_irq; }
uint32_t R_BSP_SourceClockHzGet(int clock) { (void) clock; return 32768U; }
void bsp_prv_software_delay_loop(uint32_t loops) { (void) loops; }

static external_irq_cfg_t configuration(uint8_t channel, IRQn_Type irq, unsigned trigger)
{
    external_irq_cfg_t result =
    {
        .channel = channel,
        .ipl = 5U,
        .irq = irq,
        .trigger = (external_irq_trigger_t) trigger,
        .clock_source_div = EXTERNAL_IRQ_CLOCK_SOURCE_DIV_32,
        .filter_enable = true,
        .p_context = &review_icu_common,
        .p_extend = &extension,
    };
    return result;
}

static void initialize(void)
{
    memset(review_icu, 0x5A, sizeof(review_icu));
    memset(&review_icu_common, 0xA5, sizeof(review_icu_common));
    irq_cfg_calls = 0U;
    bank_accesses = 0U;
    configured_irq = -100;
    configured_context = NULL;
    configured_ipl = 0U;
}

static int supported(void)
{
    /* Every physical channel and encoding, including both sides of the NMICR gap. */
    for (unsigned channel = 0U; channel < 32U; ++channel)
    {
        for (unsigned trigger = 0U; trigger < 4U; ++trigger)
        {
            for (unsigned filtering = 0U; filtering < 2U; ++filtering)
            {
                for (unsigned divider = 0U; divider < 4U; ++divider)
                {
                    initialize();
                    icu_instance_ctrl_t ctrl = {0};
                    IRQn_Type irq = channel & 1U ? 95 : 0;
                    external_irq_cfg_t cfg = configuration((uint8_t) channel, irq, trigger);
                    cfg.filter_enable = filtering != 0U;
                    cfg.clock_source_div = (external_irq_clock_source_div_t) divider;
                    R_ICU->IELSR[irq] = 0x0100023FU;
                    review_icu_registers_t expected[2];
                    memcpy(expected, review_icu, sizeof(expected));
                    review_icu_registers_t common_expected = review_icu_common;
                    /* Literal mapping and encodings from HM14.2.12, not driver macros. */
                    unsigned offset = channel < 16U ? channel : channel + 4U;
                    common_expected.IRQCRa[offset] = (uint8_t) (trigger | (divider << 4) | (filtering << 7));
                    REQUIRE(FSP_SUCCESS == R_ICU_ExternalIrqOpen(&ctrl, &cfg));
                    REQUIRE(0 == memcmp(&review_icu_common, &common_expected, sizeof(common_expected)));
                    REQUIRE(0 == memcmp(review_icu, expected, sizeof(expected)));
                    REQUIRE(1U == irq_cfg_calls);
                    REQUIRE(irq == configured_irq);
                    REQUIRE(cfg.ipl == configured_ipl);
                    REQUIRE(&ctrl == configured_context);
                    REQUIRE(ctrl.open != 0U && ctrl.channel == channel && ctrl.irq == irq);
                    REQUIRE(ctrl.p_context == cfg.p_context);
                    REQUIRE(FSP_SUCCESS == R_ICU_ExternalIrqClose(&ctrl));
                    REQUIRE(0U == ctrl.open);
                }
            }
        }
    }
    return 0;
}

static int pending(void)
{
    for (unsigned dtce = 0U; dtce < 2U; ++dtce)
    {
        for (IRQn_Type irq = 0; irq < 96; ++irq)
        {
            initialize();
            icu_instance_ctrl_t ctrl = {0};
            external_irq_cfg_t cfg = configuration(31U, irq, 2U);
            /* IR is already pending; unrelated event selection/DTCE must survive. */
            R_ICU->IELSR[irq] = 0x000103FFU | (dtce << 24);
            review_icu_registers_t expected[2];
            memcpy(expected, review_icu, sizeof(expected));
            expected[BSP_CFG_CPU_CORE].IELSR[irq] = 0x000003FFU | (dtce << 24);
            REQUIRE(FSP_SUCCESS == R_ICU_ExternalIrqOpen(&ctrl, &cfg));
            REQUIRE(0 == memcmp(review_icu, expected, sizeof(expected)));
            REQUIRE(0U == (R_ICU->IELSR[irq] & 0x00010000U));
        }
    }
    return 0;
}

static int vectorless(void)
{
    initialize();
    icu_instance_ctrl_t ctrl = {0};
    external_irq_cfg_t cfg = configuration(16U, FSP_INVALID_VECTOR, 1U);
    cfg.ipl = BSP_IRQ_DISABLED;
    review_icu_registers_t expected[2];
    memcpy(expected, review_icu, sizeof(expected));
    review_icu_registers_t common_expected = review_icu_common;
    common_expected.IRQCRa[20] = 0xA1U;
    REQUIRE(FSP_SUCCESS == R_ICU_ExternalIrqOpen(&ctrl, &cfg));
    REQUIRE(0U == bank_accesses);
    REQUIRE(0U == irq_cfg_calls);
    REQUIRE(0 == memcmp(review_icu, expected, sizeof(expected)));
    REQUIRE(0 == memcmp(&review_icu_common, &common_expected, sizeof(common_expected)));
    REQUIRE(FSP_INVALID_VECTOR == ctrl.irq && 16U == ctrl.channel && ctrl.open != 0U);
    REQUIRE(FSP_SUCCESS == R_ICU_ExternalIrqClose(&ctrl));
    return 0;
}

static int invalid_trigger(unsigned trigger)
{
    initialize();
    icu_instance_ctrl_t ctrl = {0};
    icu_instance_ctrl_t before_ctrl = ctrl;
    external_irq_cfg_t cfg = configuration(0U, 0, trigger);
    review_icu_registers_t expected[2];
    memcpy(expected, review_icu, sizeof(expected));
    review_icu_registers_t common_expected = review_icu_common;
    REQUIRE(FSP_ERR_UNSUPPORTED == R_ICU_ExternalIrqOpen(&ctrl, &cfg));
    REQUIRE(0U == irq_cfg_calls);
    REQUIRE(0 == memcmp(&ctrl, &before_ctrl, sizeof(ctrl)));
    REQUIRE(0 == memcmp(review_icu, expected, sizeof(expected)));
    REQUIRE(0 == memcmp(&review_icu_common, &common_expected, sizeof(common_expected)));
    return 0;
}

static int invalid_channel(uint8_t channel)
{
    initialize();
    icu_instance_ctrl_t ctrl = {0};
    icu_instance_ctrl_t before_ctrl = ctrl;
    external_irq_cfg_t cfg = configuration(channel, 0, 0U);
    review_icu_registers_t expected[2];
    memcpy(expected, review_icu, sizeof(expected));
    review_icu_registers_t common_expected = review_icu_common;
    REQUIRE(FSP_ERR_IP_CHANNEL_NOT_PRESENT == R_ICU_ExternalIrqOpen(&ctrl, &cfg));
    REQUIRE(0U == irq_cfg_calls);
    REQUIRE(0 == memcmp(&ctrl, &before_ctrl, sizeof(ctrl)));
    REQUIRE(0 == memcmp(review_icu, expected, sizeof(expected)));
    REQUIRE(0 == memcmp(&review_icu_common, &common_expected, sizeof(common_expected)));
    return 0;
}

static int unchecked_admission(void)
{
    initialize();
    icu_instance_ctrl_t ctrl = {0};
    external_irq_cfg_t cfg = configuration(0U, 0, 4U);
    /* With checks disabled, caller-owned invalid values are not newly rejected. */
    REQUIRE(FSP_SUCCESS == R_ICU_ExternalIrqOpen(&ctrl, &cfg));
    REQUIRE(ctrl.open != 0U);
    return 0;
}

int main(int argc, char ** argv)
{
    if (argc < 2) { return 2; }
    int result;
    if (0 == strcmp(argv[1], "supported")) { result = supported(); }
    else if (0 == strcmp(argv[1], "pending")) { result = pending(); }
    else if (0 == strcmp(argv[1], "vectorless")) { result = vectorless(); }
    else if (0 == strcmp(argv[1], "unchecked")) { result = unchecked_admission(); }
    else if (argc == 3 && 0 == strcmp(argv[1], "trigger"))
    {
        result = invalid_trigger((unsigned) strtoul(argv[2], NULL, 0));
    }
    else if (argc == 3 && 0 == strcmp(argv[1], "channel"))
    {
        result = invalid_channel((uint8_t) strtoul(argv[2], NULL, 0));
    }
    else { return 2; }
    if (!result) { printf("production ICU: %s passed\n", argv[1]); }
    return result;
}
