/* Native transport fixture for complete production drivers, not an IP model.
 * Expected values below are literal HM Rev1.30 contracts, independent of SVD
 * masks and the production expressions. No physical timing is established. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "bsp_api.h"
#include "production_phy.c"
#include "production_dsi.c"
#include "generated_config.h"

static R_DSILINK_Type dsi;
static R_DPHYCNT_Type phy;
static R_GLCDC_Type glcdc;
static mipi_dsi_instance_ctrl_t ctrl;
static mipi_phy_ctrl_t phy_ctrl;
static mipi_phy_timing_t const phy_timing = {.t_init = 75001, .t_clk_prep = 8};
static mipi_phy_cfg_t const phy_cfg = {.pll_settings.raw = 0x123400, .lp_divisor = 4,
                                     .p_timing = &phy_timing};
static mipi_phy_instance_t const phy_instance = {.p_ctrl = &phy_ctrl, .p_cfg = &phy_cfg};
static mipi_dsi_timing_t const timing = {1, 2, 3, 4};
static mipi_dsi_extended_cfg_t const extended = {0};
static mipi_dsi_cfg_t cfg;
static unsigned accesses, starts, callbacks, ns_callback, scenario;

static void set_word(void * base, size_t offset, uint32_t value)
{
    memcpy((uint8_t *) base + offset, &value, sizeof(value));
}

R_DSILINK_Type * review_dsi(void) { ++accesses; return &dsi; }
R_GLCDC_Type * review_glcdc(void) { ++accesses; return &glcdc; }
R_DPHYCNT_Type * review_phy(void)
{
    ++accesses;
#if TEST_TARGET
    if (scenario == 1 && phy.DPHYPWRCR_b.PWRSEN)
    {
        assert(phy.DPHYMDC == 1U); /* HM65.3.1: mode before LDO/PLL. */
    }
#endif
    return &phy;
}
void review_wait(void) {}
void review_module_start(void) { ++starts; }
void review_module_stop(void) {}
uint32_t R_FSP_SystemClockHzGet(int clock) { (void) clock; return 125000000; }
void R_BSP_IrqCfgEnable(IRQn_Type irq, uint32_t ipl, void * context)
{ (void) irq; (void) ipl; (void) context; }
void R_BSP_IrqDisable(IRQn_Type irq) { (void) irq; }
void R_FSP_IsrContextSet(IRQn_Type irq, void * context) { (void) irq; (void) context; }
void * R_FSP_IsrContextGet(IRQn_Type irq) { (void) irq; return &ctrl; }
IRQn_Type R_FSP_CurrentIrqGet(void) { return (IRQn_Type) 0; }
void R_BSP_IrqStatusClear(IRQn_Type irq) { (void) irq; }
void * review_cmse(void * p, size_t size, unsigned flags)
{ (void) size; (void) flags; return ns_callback ? p : NULL; }

static void callback(mipi_dsi_callback_args_t * args)
{
    ++callbacks;
    if (args->event == MIPI_DSI_EVENT_RECEIVE && scenario == 9)
    {
        uintptr_t result = (uintptr_t) args->p_result;
        assert(result < (uintptr_t) &dsi || result >= (uintptr_t) (&dsi + 1));
        assert(dsi.RXRSSCR == 0U);
        assert(args->p_result->data[0] == 0xA5);
        assert(args->p_result->data[1] == 0x5A);
        assert(args->p_result->cmd_id == 0x1C);
        set_word(&dsi, 0x240, 0);
        assert(args->p_result->data[0] == 0xA5); /* One stable word snapshot. */
    }
}

static void setup(void)
{
    memset(&dsi, 0, sizeof(dsi));
    memset(&phy, 0, sizeof(phy));
    memset(&glcdc, 0, sizeof(glcdc));
    memset(&ctrl, 0, sizeof(ctrl));
    cfg = (mipi_dsi_cfg_t) {.p_mipi_phy_instance = &phy_instance, .p_timing = &timing,
        .p_extend = &extended, .p_callback = callback, .num_lanes = 2,
        .video_mode_delay = 161, .ulps_wakeup_period = 98};
    ctrl.open = MIPI_DSI_OPEN;
    ctrl.p_cfg = &cfg;
    ctrl.p_callback = callback;
    g_video_started = false;
    accesses = starts = callbacks = 0;
}

int main(int argc, char ** argv)
{
    assert(argc == 2);
    scenario = (unsigned) strtoul(argv[1], NULL, 0);
    setup();
    if (scenario == 1)
    {
        assert(r_mipi_phy_open(&phy_ctrl, &phy_cfg) == FSP_SUCCESS);
#if TEST_TARGET
        assert(phy.DPHYMDC == 1U);
#endif
    }
    else if (scenario == 2)
    {
        dsi_init_timing(&cfg);
        dsi_init_video(&cfg);
        assert(dsi.TXSETR == 0x00010301U);
        assert(dsi.VMSET1R == (0x00530000U | (161U << 2)));
    }
    else if (scenario == 3)
    {
        /* HM66.2.15/36/41/46/55/59: every documented clearable bit;
         * live bits and reserved ones are deliberately injected. */
        set_word(&dsi, 0x5D0, UINT32_MAX);
        mipi_dsi_seq0_isr(); assert(dsi.SQCH0SCR == 0x7D000110U);
        set_word(&dsi, 0x610, UINT32_MAX);
        mipi_dsi_seq1_isr(); assert(dsi.SQCH1SCR == 0x7D080110U);
        set_word(&dsi, 0x200, UINT32_MAX);
        mipi_dsi_rcv_isr(); assert(dsi.RXSCR == 0x57F7C507U);
        set_word(&dsi, 0x300, UINT32_MAX);
        mipi_dsi_ferr_isr(); assert(dsi.FERRSCR == 0x001F0007U);
        set_word(&dsi, 0x320, UINT32_MAX);
        mipi_dsi_ppi_isr(); assert(dsi.PLSCR == 0x3F003000U);
        /* Avoid fatal recovery reset path in this isolated mask check. */
        set_word(&dsi, 0x410, 0xFF2FFFFFU);
        mipi_dsi_vin1_isr(); assert(dsi.VMSCR == 0x0000000BU);
        set_word(&dsi, 0x410, UINT32_MAX);
        g_video_started = false;
        assert(dsi_stop(&ctrl) == FSP_SUCCESS);
        assert(dsi.VMSCR == 0x00D0000BU);
        set_word(&dsi, 0x224, UINT32_MAX);
        mipi_dsi_status_t status;
        assert(R_MIPI_DSI_StatusGet(&ctrl, &status) == FSP_SUCCESS);
        assert(status.ack_err_accumulated.bits == UINT32_MAX);
        assert(dsi.AKEPSCR == 0x000FFFFFU);
    }
    else if (scenario == 4)
    {
        dsi_init_video(&g_generated_cfg);
        assert(dsi.VMVSSETR_b.VSA + dsi.VMVPSETR_b.VBP +
               dsi.VMVSSETR_b.VACT + dsi.VMVPSETR_b.VFP == 900U);
        assert(dsi.VMHSSETR_b.HSA + dsi.VMHPSETR_b.HBP +
               dsi.VMHSSETR_b.HACT + dsi.VMHPSETR_b.HFP == 600U);
        dsi_init_timing(&g_generated_cfg);
        assert(dsi.ULPSSETR_b.WKUP == 98U);
        assert(dsi.ULPSSETR_b.WKUP * 128U > 12500U); /* fLPCLK = 12.5 MHz. */
    }
    else if (scenario == 5)
    {
        for (unsigned polarity = 0; polarity < 2; ++polarity)
        {
            cfg.vertical_sync_polarity = cfg.horizontal_sync_polarity = polarity;
            dsi_init_video(&cfg);
            assert((dsi.VMVSSETR & 0x8000U) == ((1U - polarity) << 15));
            assert((dsi.VMHSSETR & 0x8000U) == ((1U - polarity) << 15));
        }
    }
    else if (scenario == 6)
    {
        for (unsigned lp = 0; lp < 2; ++lp)
        {
            for (unsigned action = 0; action < 32; ++action)
            {
                mipi_dsi_cmd_t cmd = {.flags = (mipi_dsi_cmd_flag_t) (0x20U | action | (lp ? 0x40U : 0)),
                                       .cmd_id = (mipi_dsi_cmd_id_t) 0x05};
                unsigned before = accesses;
                fsp_err_t err = R_MIPI_DSI_Command(&ctrl, &cmd);
                if (action != 0 && action != 8)
                {
                    assert(err == FSP_ERR_INVALID_ARGUMENT);
                    assert(accesses == before); /* Rejection before any MMIO. */
                }
                else
                {
                    assert(err == FSP_SUCCESS);
                    size_t offset = lp ? 0x780 : 0x800;
                    uint32_t const * reg = (uint32_t const *) ((uint8_t *) &dsi + offset);
                    assert((reg[0] & 0x0C000000U) == 0U); /* AUX BTA must be 00. */
                    assert(reg[2] == (0x00400000U | (action << 24)));
                }
            }
        }
    }
    else if (scenario == 7)
    {
        uint8_t tx[8] = {0}, rx[8] = {0};
        for (unsigned bta = 0; bta < 4; ++bta)
        {
            mipi_dsi_cmd_t cmd = {.flags = (mipi_dsi_cmd_flag_t) bta,
                .cmd_id = (mipi_dsi_cmd_id_t) 0x39, .tx_len = sizeof(tx),
                .p_tx_buffer = tx, .p_rx_buffer = rx};
            assert(R_MIPI_DSI_Command(&ctrl, &cmd) == FSP_SUCCESS);
            assert(dsi.SQCH1DSC0DR == (uint32_t) (uintptr_t) ((bta >= 2) ? rx : tx));
        }
    }
    else if (scenario == 8)
    {
        dsi.HSCLKSETR = 1U; /* Noncontinuous mode, HSCLST still set by Open. */
        assert(R_MIPI_DSI_UlpsEnter(&ctrl, MIPI_DSI_LANE_CLOCK) == FSP_ERR_INVALID_MODE);
        assert(dsi.ULPSCR == 0U && !ctrl.clock_ulps_active && !ctrl.ulps_status);
        dsi.HSCLKSETR = 0U;
        assert(R_MIPI_DSI_UlpsEnter(&ctrl, MIPI_DSI_LANE_CLOCK) == FSP_SUCCESS);
        assert(dsi.ULPSCR == 0x01000000U);
    }
    else if (scenario == 9)
    {
        set_word(&dsi, 0x240, 0x039C5AA5U);
        mipi_dsi_rcv_isr();
        assert(callbacks == 1U);
        assert(dsi.RXRSSCR == 1U && dsi.RXRINFOOWSCR == 0U);
    }
    else if (scenario == 10)
    {
#if BSP_TZ_SECURE_BUILD
        ctrl.open = 0;
        ns_callback = 1;
        assert(R_MIPI_DSI_Open(&ctrl, &cfg) == FSP_ERR_NO_CALLBACK_MEMORY);
        assert(accesses == 0U && starts == 0U && ctrl.open == 0U);
#endif
        ctrl.open = 0;
        ns_callback = 0;
        glcdc.SYSCNT.PANEL_CLK_b.CLKEN = 1U;
        assert(R_MIPI_DSI_Open(&ctrl, &cfg) == FSP_SUCCESS);
        assert(ctrl.open == MIPI_DSI_OPEN && starts == 1U && callbacks == 1U);
        assert(ctrl.p_callback_memory == NULL && ctrl.p_callback == callback);
    }
    puts("production DSI scenario passed");
    return 0;
}
