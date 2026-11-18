#include <assert.h>
#include <stdio.h>
#include "r_gpt.h"
#include "r_ospi_b.h"

static R_PDG_Type pdg;
static R_GPT0_Type gpt;
static R_GPT_GTCLK_Type gtclk;
static R_SYSTEM_Type system_regs;
static R_XSPI0_Type ospi[2];
static unsigned starts, delays, pdg_writes, bypass_writes;
static uint32_t source_hz, peripheral_hz;
static uintptr_t xip_address;
static unsigned source_selected;
static uint16_t control_history[8];
static bool gtwp_readback_pending;
static unsigned gtwp_readbacks;

static void * resolve(void * p, unsigned bytes)
{
    uintptr_t a = (uintptr_t) p;
#define REGION(base,obj) if (a >= (base) && a - (base) + bytes <= sizeof(obj)) return (uint8_t *) &(obj) + a - (base)
    REGION(0x41000000U, gpt);
    REGION(0x43000000U, gtclk);
    REGION(0x44000000U, system_regs);
    REGION(0x45000000U, pdg);
    REGION(0x46000000U, ospi[0]);
    REGION(0x46001000U, ospi[1]);
#undef REGION
    /* Only XiP's dummy data reads may touch an external mapped window. */
    if (a >= 0x68000000U && a < 0xa0000000U)
    {
        static uint64_t zero;
        assert(bytes == 1U);
        xip_address = a;
        return &zero;
    }
    assert(a > UINT32_MAX);
    return p;
}
static void observe_read(void * p, unsigned bytes)
{
    if ((bytes == 4U) && (resolve(p,bytes) == (void *)&gpt.GTWP) && gtwp_readback_pending)
    {
        gtwp_readback_pending = false;
        gtwp_readbacks++;
    }
}
#define READ(width,type) type review_read##width(void * p) { type v; observe_read(p,sizeof(v)); memcpy(&v, resolve(p,sizeof(v)),sizeof(v)); return v; }
#define WRITE(width,type) void review_write##width(void * p,type v) { observe(p,(uint64_t)v); memcpy(resolve(p,sizeof(v)),&v,sizeof(v)); }
static void observe(void * p, uint64_t v)
{
    uintptr_t a = (uintptr_t) p;
    if ((p == (void *)&gpt.GTWP) || (a == 0x41000000U + offsetof(R_GPT0_Type,GTWP)))
    {
        gtwp_readback_pending = (v & 1U) == 0U;
    }
    if (a >= 0x45000018U && a < 0x45000038U)
    {
        /* HM24.2.3: the read must follow the WP change, not merely precede it. */
        assert(!gtwp_readback_pending && "PDG delay write preceded GTWP readback");
    }
    if (a == 0x45000000U)
    {
        assert(starts != 0U);
        assert(pdg_writes < 8U);
        control_history[pdg_writes++] = (uint16_t) v;
    }
    if (a == 0x45000002U)
    {
        if (v & 15U) assert(delays >= 2U);
        bypass_writes++;
    }
}
READ(8,uint8_t)
READ(16,uint16_t)
READ(32,uint32_t)
READ(64,uint64_t)
WRITE(8,uint8_t)
WRITE(16,uint16_t)
WRITE(32,uint32_t)
WRITE(64,uint64_t)

void review_module_start(unsigned ip, unsigned channel) { (void)channel; if (ip == FSP_IP_GPT_PDG) starts++; }
uint32_t R_FSP_SystemClockHzGet(unsigned clock) { (void)clock; return peripheral_hz; }
uint32_t R_BSP_SourceClockHzGet(fsp_priv_source_clock_t clock) { source_selected = clock; return source_hz; }
void R_BSP_SoftwareDelay(unsigned delay, unsigned units)
{
    (void)units;
    if (delays == 0U) { assert(delay >= 20U); assert((pdg.GTDLYCR & 3U) == 3U); }
    else { assert(delay >= 1U); assert((pdg.GTDLYCR & 3U) == 1U); }
    delays++;
}
void R_BSP_IrqCfgEnable(IRQn_Type a,uint8_t b,void *c) { (void)a;(void)b;(void)c; }
void R_BSP_IrqDisable(IRQn_Type a) { (void)a; }
void R_BSP_IrqClearPending(IRQn_Type a) { (void)a; }
void R_FSP_IsrContextSet(IRQn_Type a, void *p) { (void)a;(void)p; }
void R_BSP_IrqEnable(IRQn_Type a) { (void)a; }
void R_BSP_IrqEnableNoClear(IRQn_Type a) { (void)a; }
void R_BSP_IrqStatusClear(IRQn_Type a) { (void)a; }
IRQn_Type R_FSP_CurrentIrqGet(void) { return 0; }
void * R_FSP_IsrContextGet(IRQn_Type a) { (void)a;return NULL; }

static void pdg_case(uint32_t frequency, bool valid)
{
    memset(&pdg,0xa5,sizeof(pdg));
    starts = delays = pdg_writes = bypass_writes = 0U;
    peripheral_hz = source_hz = frequency;
    system_regs.GPTCKDIVCR = 0U;
    system_regs.GPTCKCR = 5U;
    assert(R_GPT_PwmOutputDelayInitialize() == (valid ? FSP_SUCCESS : FSP_ERR_INVALID_STATE));
    if (!valid)
    {
        assert(starts == 0U && delays == 0U && pdg_writes == 0U && bypass_writes == 0U);
        return;
    }
    assert(starts == 1U && delays == 2U && pdg_writes == 3U);
    uint16_t range = frequency > 160000000U ? 0x100U : 0U;
    assert(control_history[0] == (range | 2U));
    assert(control_history[1] == (range | 3U));
    assert(control_history[2] == (range | 1U));
    assert(pdg.GTDLYCR2 == 0U);
#if PROTECT
    assert(gpt.GTWP == 0xa501U);
#endif
#if !BYPASS
    assert(source_selected == 5U);
#endif
    for (unsigned ch = 0; ch < 4; ++ch)
    {
        gpt_instance_ctrl_t ctrl = {0};
        timer_cfg_t cfg = {.channel = ch, .mode = TIMER_MODE_PWM};
        ctrl.open = 0x00475054U;
        ctrl.p_cfg = &cfg;
        ctrl.p_reg = &gpt;
        ctrl.channel_mask = 1U << ch;
        gpt.GTPR = 100U;
        uint32_t up = 0x8000U;
        memcpy((void *)&gpt.GTST, &up, sizeof(up));
        for (unsigned pin = 0; pin < 2; ++pin)
        {
            for (unsigned edge = 0; edge < 2; ++edge)
            {
                for (unsigned delay = 0; delay < 32; ++delay)
                {
                    unsigned reads_before = gtwp_readbacks;
                    assert(R_GPT_PwmOutputDelaySet(&ctrl, (gpt_pwm_output_delay_edge_t)edge,
                               (gpt_pwm_output_delay_setting_t)delay,pin) == FSP_SUCCESS);
#if PROTECT
                    assert(gtwp_readbacks > reads_before);
#else
                    assert(gtwp_readbacks == reads_before);
#endif
                    unsigned offset = (edge ? 0x28U : 0x18U) + 4U * ch + 2U * pin;
                    uint16_t value;
                    memcpy(&value, (uint8_t *)&pdg + offset, sizeof(value));
                    assert(value == delay * 4U);
                    assert((pdg.GTDLYCR2 & (1U << ch)) != 0U);
                }
            }
        }
        assert(R_GPT_PwmOutputDelaySet(&ctrl,GPT_PWM_OUTPUT_DELAY_EDGE_RISING,
                                      GPT_PWM_OUTPUT_DELAY_SETTING_BYPASS,0) == FSP_SUCCESS);
        assert((pdg.GTDLYCR2 & (1U << ch)) == 0U);
#if CHECKS
        ctrl.channel_mask = 1U << 4;
        assert(R_GPT_PwmOutputDelaySet(&ctrl,GPT_PWM_OUTPUT_DELAY_EDGE_RISING,
                                      GPT_PWM_OUTPUT_DELAY_SETTING_0_32,0) == FSP_ERR_INVALID_CHANNEL);
        ctrl.channel_mask = 1U << ch;
        gpt.GTCCR[2] = 98U;
        assert(R_GPT_PwmOutputDelaySet(&ctrl,GPT_PWM_OUTPUT_DELAY_EDGE_RISING,
                                      GPT_PWM_OUTPUT_DELAY_SETTING_0_32,0) == FSP_ERR_INVALID_STATE);
        gpt.GTCCR[2] = 0U;
        uint32_t down = 0U;
        memcpy((void *)&gpt.GTST, &down, sizeof(down));
        for (unsigned compare = 0; compare <= 3U; ++compare)
        {
            gpt.GTCCR[2] = compare;
            assert(R_GPT_PwmOutputDelaySet(&ctrl,GPT_PWM_OUTPUT_DELAY_EDGE_RISING,
                       GPT_PWM_OUTPUT_DELAY_SETTING_1_32,0) ==
                       (compare <= 2U ? FSP_ERR_INVALID_STATE : FSP_SUCCESS));
        }
        cfg.mode = TIMER_MODE_TRIANGLE_WAVE_SYMMETRIC_PWM;
        gpt.GTCCR[2] = 2U;
        assert(R_GPT_PwmOutputDelaySet(&ctrl,GPT_PWM_OUTPUT_DELAY_EDGE_RISING,
                                      GPT_PWM_OUTPUT_DELAY_SETTING_1_32,0) == FSP_ERR_INVALID_STATE);
        memcpy((void *)&gpt.GTST, &up, sizeof(up));
        assert(R_GPT_PwmOutputDelaySet(&ctrl,GPT_PWM_OUTPUT_DELAY_EDGE_RISING,
                                      GPT_PWM_OUTPUT_DELAY_SETTING_1_32,0) == FSP_SUCCESS);
        cfg.mode = TIMER_MODE_PWM;
        gpt.GTPR = 1U;
        gpt.GTCCR[2] = 0U;
        assert(R_GPT_PwmOutputDelaySet(&ctrl,GPT_PWM_OUTPUT_DELAY_EDGE_RISING,
                                      GPT_PWM_OUTPUT_DELAY_SETTING_1_32,0) == FSP_ERR_INVALID_STATE);
        assert(R_GPT_PwmOutputDelaySet(&ctrl,GPT_PWM_OUTPUT_DELAY_EDGE_RISING,
                                      GPT_PWM_OUTPUT_DELAY_SETTING_1_32,2) == FSP_ERR_ASSERTION);
#endif
    }
}

static void ospi_cases(void)
{
    static const uint32_t windows[2][2] = {{0x80000000U,0x90000000U},{0x70000000U,0x78000000U}};
    static const uint32_t sizes[2] = {0x10000000U,0x08000000U};
    const spi_flash_erase_command_t commands[] = {{.command = 0x20U,.size = 4096U}};
    ospi_b_timing_setting_t timing = {0};
    for (unsigned unit = 0; unit < 2; ++unit)
    {
        for (unsigned channel = 0; channel < 2; ++channel)
        {
            ospi_b_extended_cfg_t ext = {.ospi_b_unit = unit, .channel = channel,
                                        .data_latch_delay_clocks = 1U, .p_timing_settings = &timing};
            spi_flash_cfg_t cfg = {.p_extend = &ext,.address_bytes = SPI_FLASH_ADDRESS_BYTES_4,
                .spi_protocol = SPI_FLASH_PROTOCOL_EXTENDED_SPI,.page_size_bytes = 256U,
                .p_erase_command_list = commands,.erase_command_list_length = 1U};
            ospi_b_instance_ctrl_t ctrl = {0};
            memset(&ospi[unit],0,sizeof(ospi[unit]));
            assert(R_OSPI_B_Open(&ctrl,&cfg) == FSP_SUCCESS);
            assert((uintptr_t) ctrl.p_reg == 0x46000000U + 0x1000U * unit);
            assert(((ospi[unit].CMCFGCS[channel].CMCFG0 >> 16U) & 255U) == (unit ? 0xf8U : 0xf0U));
            for (unsigned i = 0; i < 3; ++i)
            {
                uint32_t offset = i == 0 ? 0U : (i == 1 ? 0x12345000U % sizes[unit] : sizes[unit] - 4096U);
                assert(R_OSPI_B_Erase(&ctrl,(uint8_t *)(uintptr_t)(windows[unit][channel] + offset),4096U) == FSP_SUCCESS);
                assert(ospi[unit].CDBUF[0].CDA == offset);
            }
            uint32_t bad[] = {0x68000000U, windows[unit][channel] - 1U,
                windows[unit][channel] + sizes[unit], 0xffffffffU};
            for (unsigned i = 0; i < sizeof(bad)/sizeof(bad[0]); ++i)
            {
                R_XSPI0_Type saved;
                memcpy(&saved,&ospi[unit],sizeof(saved));
                assert(R_OSPI_B_Erase(&ctrl,(uint8_t *)(uintptr_t)bad[i],4096U) == FSP_ERR_INVALID_ADDRESS);
                uint64_t data = 0U;
                assert(R_OSPI_B_Write(&ctrl,(uint8_t *)&data,(uint8_t *)(uintptr_t)(bad[i] & ~7U),8U) == FSP_ERR_INVALID_ADDRESS);
                assert(memcmp(&saved,&ospi[unit],sizeof(saved)) == 0);
            }
            assert(R_OSPI_B_Erase(&ctrl,(uint8_t *)(uintptr_t)(windows[unit][channel] + sizes[unit] - 8U),4096U)
                   == FSP_ERR_INVALID_ADDRESS);
            xip_address = 0U;
            assert(R_OSPI_B_XipEnter(&ctrl) == FSP_SUCCESS);
            assert(xip_address == windows[unit][channel]);
            xip_address = 0U;
            assert(R_OSPI_B_XipExit(&ctrl) == FSP_SUCCESS);
            assert(xip_address == windows[unit][channel]);
            ext.p_autocalibration_preamble_pattern_addr = (uint8_t *)(uintptr_t)(windows[unit][channel] + sizes[unit] - 16U);
            uint32_t calibration_status = 1U << (R_XSPI0_INTS_CASUCCS_Pos + channel);
            memcpy((void *)&ospi[unit].INTS, &calibration_status, sizeof(calibration_status));
            ctrl.spi_protocol = SPI_FLASH_PROTOCOL_8D_8D_8D;
            assert(R_OSPI_B_AutoCalibrate(&ctrl) == FSP_SUCCESS);
            assert(ospi[unit].CCCTLCS[channel].CCCTL3 == sizes[unit] - 16U);
            ext.p_autocalibration_preamble_pattern_addr = (uint8_t *)(uintptr_t)(windows[unit][channel] + sizes[unit] - 8U);
            assert(R_OSPI_B_AutoCalibrate(&ctrl) == FSP_ERR_INVALID_ADDRESS);
            assert(R_OSPI_B_Close(&ctrl) == FSP_SUCCESS);
        }
    }
    ospi_b_extended_cfg_t ext = {.ospi_b_unit = 32U};
    spi_flash_cfg_t cfg = {.p_extend = &ext};
    ospi_b_instance_ctrl_t ctrl = {0};
    assert(R_OSPI_B_Open(&ctrl,&cfg) == FSP_ERR_IP_CHANNEL_NOT_PRESENT);
    ext.ospi_b_unit = 0U; ext.channel = 32U;
    assert(R_OSPI_B_Open(&ctrl,&cfg) == FSP_ERR_IP_CHANNEL_NOT_PRESENT);
}

int main(void)
{
    uint32_t frequencies[] = {79999999U,80000000U,155000000U,160000000U,160000001U,300000000U,300000001U};
    for (unsigned i = 0; i < sizeof(frequencies)/sizeof(frequencies[0]); ++i)
        pdg_case(frequencies[i],frequencies[i] >= 80000000U && frequencies[i] <= 300000000U);
#if !BYPASS
    static const unsigned divisors[] = {1,2,4,6,8,3,5,10,16,32};
    for (unsigned i = 0; i < 10U; ++i)
    {
        source_hz = 80000000U * divisors[i];
        system_regs.GPTCKDIVCR = i;
        starts = delays = pdg_writes = bypass_writes = 0U;
        fsp_err_t expected = (i == 5U || i == 6U) ? FSP_ERR_INVALID_STATE : FSP_SUCCESS;
        assert(R_GPT_PwmOutputDelayInitialize() == expected);
        if (expected == FSP_SUCCESS) assert(pdg.GTDLYCR == 1U);
        else assert(starts == 0U && pdg_writes == 0U);
    }
    system_regs.GPTCKDIVCR = 10U;
    assert(R_GPT_PwmOutputDelayInitialize() == FSP_ERR_INVALID_STATE);
#endif
    ospi_cases();
    puts("peripheral capability cases passed");
    return 0;
}
