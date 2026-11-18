/* Host MMIO model for the complete production OSPI and DMAC translation units.
 * DMA completion follows HM17.4.1 p786. Fault wrappers otherwise forward to real DMAC APIs. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "r_ospi_b.h"
#include "r_dmac.h"

_Static_assert(sizeof(R_DMAC0_Type) == 0x34U, "canonical type size is not the channel stride");
_Static_assert(offsetof(R_DMAC0_Type, DMBWR) == 0x30U, "HM17.2.19 offset");
_Static_assert(BSP_FEATURE_DMAC_MAX_CHANNEL == 8U, "HM17.2.19 channels 0..7");
_Static_assert(R_DMAC1_BASE - R_DMAC0_BASE == 0x40U, "canonical adjacent-instance stride");
_Static_assert(R_DMAC0_BASE == (REVIEW_NONSECURE ? 0x5000a000U : 0x4000a000U), "CPU-local security view");

static R_XSPI0_Type ospi[2];
static R_DMA_Type dma;
static R_ICU_Type icu;
static uint8_t channels[8U * 0x40U];
static unsigned active_channel, bwe_writes, completions, remaining_reads, mmio_accesses;
static unsigned module_starts[4][2], module_stops[4][2];
static unsigned opens, closes, disables, reconfigs, software_starts, infos;
static bool in_write, pending, hold_active;
static uint8_t source_data[65537];
static uint32_t expected_dest, expected_length = 16U;
static enum { NONE, OPEN_ERROR, RECONFIG_ERROR, RECONFIG_AFTER_ERROR, START_ERROR, START_AFTER_ERROR,
              INFO_ERROR, INFO_LATER_ERROR } fault;
static enum { ABORT_OK, DISABLE_ERROR, DISABLE_NO_EFFECT, ACT_STUCK, CLOSE_ERROR } abort_fault;
static transfer_ctrl_t * last_closed;
static transfer_info_t info;
static const uint32_t flash[2][2] = {{0x80000000U, 0x90000000U}, {0x70000000U, 0x78000000U}};

static uintptr_t channel_address(void)
{
    return (REVIEW_NONSECURE ? 0x5000a000U : 0x4000a000U) + 0x40U * active_channel;
}

static void * resolve(void * p, unsigned bytes)
{
    uintptr_t a = (uintptr_t) p;
    if (a <= UINT32_MAX)
        mmio_accesses++;
    uintptr_t base = REVIEW_NONSECURE ? 0x5000a000U : 0x4000a000U;
    if (a >= base && a - base + bytes <= sizeof(channels))
        return channels + (a - base);
    if (a >= R_DMA_BASE && a - R_DMA_BASE + bytes <= sizeof(dma))
        return (uint8_t *) &dma + (a - R_DMA_BASE);
    if (a >= R_ICU_BASE && a - R_ICU_BASE + bytes <= sizeof(icu))
        return (uint8_t *) &icu + (a - R_ICU_BASE);
    for (unsigned u = 0; u < 2U; ++u)
    {
        base = 0x46000000U + 0x1000U * u;
        if (a >= base && a - base + bytes <= sizeof(ospi[u]))
            return (uint8_t *) &ospi[u] + (a - base);
    }
    assert(a > UINT32_MAX && "DMBWR address mismatch: MMIO outside canonical DMA aperture");
    return p;
}

static uint64_t memory_read(void * p, unsigned bytes)
{
    uintptr_t a = (uintptr_t) p;
    if (pending && !hold_active && a == channel_address() + 8U && ++remaining_reads == 2U)
    {
        /* Normal-mode completion clears count and DTE together, HM17.4.1 p786. */
        memset(channels + 0x40U * active_channel + 8U, 0, 4U);
        channels[0x40U * active_channel + 0x1cU] = 0U;
        channels[0x40U * active_channel + 0x1eU] = 0x10U;
        completions++;
        pending = false;
    }
    uint64_t value = 0U;
    memcpy(&value, resolve(p, bytes), bytes);
    return value;
}

static void memory_write(void * p, uint64_t value, unsigned bytes)
{
    uintptr_t a = (uintptr_t) p;
    uintptr_t bank = REVIEW_NONSECURE ? 0x5000a000U : 0x4000a000U;
    bool icu_access = a >= R_ICU_BASE && a - R_ICU_BASE + bytes <= sizeof(icu);
    if (in_write && a >= bank && a < bank + 0x10000U && a != R_DMA_BASE && !icu_access)
    {
        assert(a >= channel_address() && a + bytes <= channel_address() + 0x34U &&
               "DMBWR address mismatch: write reached wrong DMA channel");
    }
    if (a == channel_address() + 0x30U)
    {
        assert(bytes == 1U && "DMBWR bus width must be one byte");
        assert(value == 0U || value == 1U);
        assert(((dma.DMAST & 1U) == 0U || (channels[0x40U * active_channel + 0x1cU] & 1U) == 0U) &&
               "DMBWR setting condition violated: DMAST=1 and DTE=1");
        uint8_t before[sizeof(channels)];
        memcpy(before, channels, sizeof(before));
        memcpy(resolve(p, bytes), &value, bytes);
        before[0x40U * active_channel + 0x30U] = (uint8_t) value;
        assert(memcmp(before, channels, sizeof(before)) == 0 && "DMBWR changed another byte");
        bwe_writes++;
        return;
    }
    memcpy(resolve(p, bytes), &value, bytes);
    if (a == channel_address() + 0x1cU && value == 0U && abort_fault != ACT_STUCK)
    {
        pending = false;
        channels[0x40U * active_channel + 0x1eU] &= (uint8_t) ~0x80U;
    }
    if (a == channel_address() + 0x1dU && (value & 1U))
    {
        assert((channels[0x40U * active_channel + 0x1cU] & 1U) == 1U);
        assert(channels[0x40U * active_channel + 0x30U] == 1U);
        assert((channels[0x40U * active_channel + 0x10U + 1U] & 0xc0U) == 0U);
        assert(info.transfer_settings_word_b.mode == TRANSFER_MODE_NORMAL);
        assert(info.transfer_settings_word_b.size == TRANSFER_SIZE_1_BYTE);
        assert(info.length == expected_length && "DMA length narrowed");
        assert(info.p_src == source_data && (uintptr_t) info.p_dest == expected_dest);
        uint32_t address, count;
        memcpy(&address, channels + 0x40U * active_channel, sizeof(address));
        assert(address == (uint32_t) (uintptr_t) source_data);
        memcpy(&address, channels + 0x40U * active_channel + 4U, sizeof(address));
        assert(address == expected_dest);
        memcpy(&count, channels + 0x40U * active_channel + 8U, sizeof(count));
        assert(count == expected_length && "DMA count narrowed");
        channels[0x40U * active_channel + 0x1eU] = 0x80U;
        pending = true;
        remaining_reads = 0U;
    }
}

#define READ(width, type) type review_read##width(void * p) { return (type) memory_read(p, sizeof(type)); }
#define WRITE(width, type) void review_write##width(void * p, type value) { memory_write(p, value, sizeof(value)); }
READ(8, uint8_t)
READ(16, uint16_t)
READ(32, uint32_t)
READ(64, uint64_t)
WRITE(8, uint8_t)
WRITE(16, uint16_t)
WRITE(32, uint32_t)
WRITE(64, uint64_t)
void * review_readptr(void * p) { return (void *) (uintptr_t) memory_read(p, sizeof(void *)); }
void review_writeptr(void * p, void * value) { memory_write(p, (uintptr_t) value, sizeof(void *)); }

void review_module_start(unsigned ip, unsigned channel) { module_starts[ip][ip == FSP_IP_DMAC ? 0U : channel]++; }
void review_module_stop(unsigned ip, unsigned channel) { module_stops[ip][ip == FSP_IP_DMAC ? 0U : channel]++; }
void R_BSP_IrqCfgEnable(IRQn_Type irq, uint8_t priority, void * context) { (void) irq; (void) priority; (void) context; }
void R_BSP_IrqDisable(IRQn_Type irq) { (void) irq; }
void R_FSP_IsrContextSet(IRQn_Type irq, void * context) { (void) irq; (void) context; }
void R_BSP_IrqStatusClear(IRQn_Type irq) { (void) irq; }
IRQn_Type R_FSP_CurrentIrqGet(void) { return 0; }
void * R_FSP_IsrContextGet(IRQn_Type irq) { (void) irq; return NULL; }
void R_BSP_SoftwareDelay(unsigned delay, unsigned units) { (void) delay; (void) units; }

static fsp_err_t injected_open(transfer_ctrl_t * p, transfer_cfg_t const * c)
{
    opens++;
    return fault == OPEN_ERROR ? FSP_ERR_NOT_ENABLED : R_DMAC_Open(p, c);
}
static fsp_err_t injected_reconfigure(transfer_ctrl_t * p, transfer_info_t * i)
{
    reconfigs++;
    if (fault == RECONFIG_ERROR)
        return FSP_ERR_NOT_ENABLED;
    fsp_err_t err = R_DMAC_Reconfigure(p, i);
    return fault == RECONFIG_AFTER_ERROR ? FSP_ERR_NOT_ENABLED : err;
}
static fsp_err_t injected_start(transfer_ctrl_t * p, transfer_start_mode_t mode)
{
    software_starts++;
    if (fault == START_ERROR)
        return FSP_ERR_NOT_ENABLED;
    fsp_err_t err = R_DMAC_SoftwareStart(p, mode);
    return fault == START_AFTER_ERROR ? FSP_ERR_NOT_ENABLED : err;
}
static fsp_err_t injected_info(transfer_ctrl_t * p, transfer_properties_t * i)
{
    infos++;
    if (fault == INFO_ERROR || (fault == INFO_LATER_ERROR && infos >= 2U))
        return FSP_ERR_NOT_ENABLED;
    return R_DMAC_InfoGet(p, i);
}
static fsp_err_t injected_disable(transfer_ctrl_t * p)
{
    disables++;
    if (abort_fault == DISABLE_ERROR)
        return FSP_ERR_NOT_ENABLED;
    if (abort_fault == DISABLE_NO_EFFECT)
        return FSP_SUCCESS;  /* Success must not replace DTE/ACT readback. */
    return R_DMAC_Disable(p);
}
static fsp_err_t injected_close(transfer_ctrl_t * p)
{
    closes++;
    last_closed = p;
    return abort_fault == CLOSE_ERROR ? FSP_ERR_NOT_ENABLED : R_DMAC_Close(p);
}
static transfer_api_t api;

static void initialize(unsigned channel)
{
    active_channel = channel;
    pending = in_write = hold_active = false;
    fault = NONE;
    abort_fault = ABORT_OK;
    bwe_writes = completions = remaining_reads = mmio_accesses = 0U;
    opens = closes = disables = reconfigs = software_starts = infos = 0U;
    last_closed = NULL;
    memset(module_starts, 0, sizeof(module_starts));
    memset(module_stops, 0, sizeof(module_stops));
    memset(channels, 0xa5, sizeof(channels));
    channels[0x40U * channel + 0x1eU] = 0U;
    channels[0x40U * channel + 0x30U] = 0U;
    memset(&dma, 0, sizeof(dma));
    memset(&icu, 0, sizeof(icu));
    memset(ospi, 0, sizeof(ospi));
    info = (transfer_info_t) {.length = 16U};
    expected_length = 16U;
    api = g_transfer_on_dmac;
    api.open = injected_open;
    api.reconfigure = injected_reconfigure;
    api.softwareStart = injected_start;
    api.infoGet = injected_info;
    api.disable = injected_disable;
    api.close = injected_close;
}

static void one_case(unsigned channel, unsigned unit, unsigned cs, bool invalid, bool pre_enabled)
{
    initialize(channel);
    dmac_extended_cfg_t dext = {.channel = channel, .activation_source = ELC_EVENT_NONE};
    transfer_cfg_t dcfg = {.p_info = &info, .p_extend = &dext};
    dmac_instance_ctrl_t dctrl = {0};
    transfer_instance_t transfer = {.p_ctrl = &dctrl, .p_cfg = &dcfg, .p_api = &api};
    ospi_b_timing_setting_t timing = {0};
    ospi_b_extended_cfg_t ext = {.ospi_b_unit = unit, .channel = cs, .p_timing_settings = &timing,
                                .p_lower_lvl_transfer = &transfer, .data_latch_delay_clocks = 1U};
    spi_flash_cfg_t cfg = {.p_extend = &ext, .address_bytes = SPI_FLASH_ADDRESS_BYTES_4,
                          .spi_protocol = SPI_FLASH_PROTOCOL_EXTENDED_SPI, .page_size_bytes = 256U,
                          .read_command = 0xbU, .page_program_command = 2U};
    ospi_b_instance_ctrl_t ctrl = {0};
    assert(R_OSPI_B_Open(&ctrl, &cfg) == FSP_SUCCESS);
    assert(dctrl.open != 0U && (uintptr_t) dctrl.p_reg == channel_address());
    assert((dma.DMAST & 1U) == 1U);
    assert((channels[0x40U * channel + 0x1cU] & 1U) == 0U);
    uint8_t before[sizeof(channels)];
    memcpy(before, channels, sizeof(before));
    if (invalid)
        dext.channel = 8U;
    if (pre_enabled)
    {
        info.p_src = source_data;
        info.p_dest = (void *) (uintptr_t) flash[unit][cs];
        assert(R_DMAC_Reconfigure(&dctrl, &info) == FSP_SUCCESS);
    }
    in_write = true;
    for (unsigned pass = 0; pass < 2U; ++pass)
    {
        for (unsigned i = 0; i < expected_length; ++i)
            source_data[i] = (uint8_t) (i + channel + pass + 1U);
        expected_dest = flash[unit][cs] + 0x100U * pass;
        fsp_err_t err = R_OSPI_B_Write(&ctrl, source_data, (uint8_t *) (uintptr_t) expected_dest,
                                     expected_length);
        if (invalid)
        {
            assert(err == FSP_ERR_IP_CHANNEL_NOT_PRESENT && "invalid DMA channel not rejected");
            assert(bwe_writes == 0U);
            assert(memcmp(before, channels, sizeof(before)) == 0);
            break;
        }
        assert(err == FSP_SUCCESS);
        assert(bwe_writes == 2U * (pass + 1U) && completions == pass + 1U);
        for (unsigned other = 0; other < 8U; ++other)
            if (other != channel)
                assert(memcmp(before + 0x40U * other, channels + 0x40U * other, 0x40U) == 0);
        assert(channels[0x40U * channel + 0x30U] == 0U);
        assert((channels[0x40U * channel + 0x1cU] & 1U) == 0U);
    }
    in_write = false;
    if (invalid)
        dext.channel = channel;
    assert(R_OSPI_B_Close(&ctrl) == FSP_SUCCESS);
    assert(dctrl.open == 0U);
}

typedef struct
{
    dmac_extended_cfg_t dext;
    transfer_cfg_t dcfg;
    dmac_instance_ctrl_t dctrl;
    transfer_instance_t transfer;
    ospi_b_timing_setting_t timing;
    ospi_b_extended_cfg_t ext;
    spi_flash_cfg_t cfg;
    ospi_b_instance_ctrl_t ctrl;
} rig_t;

static void setup(rig_t * r, unsigned channel, unsigned unit, unsigned cs)
{
    *r = (rig_t) {0};
    r->dext = (dmac_extended_cfg_t) {.channel = channel, .activation_source = ELC_EVENT_NONE};
    r->dcfg = (transfer_cfg_t) {.p_info = &info, .p_extend = &r->dext};
    r->transfer = (transfer_instance_t) {.p_ctrl = &r->dctrl, .p_cfg = &r->dcfg, .p_api = &api};
    r->ext = (ospi_b_extended_cfg_t) {.ospi_b_unit = unit, .channel = cs, .p_timing_settings = &r->timing,
                                    .p_lower_lvl_transfer = &r->transfer, .data_latch_delay_clocks = 1U};
    r->cfg = (spi_flash_cfg_t) {.p_extend = &r->ext, .address_bytes = SPI_FLASH_ADDRESS_BYTES_4,
                              .spi_protocol = SPI_FLASH_PROTOCOL_EXTENDED_SPI, .page_size_bytes = 0x20000U,
                              .read_command = 0xbU, .page_program_command = 2U};
}

static fsp_err_t write_rig(rig_t * r, uint32_t length)
{
    expected_length = length;
    expected_dest = flash[r->ext.ospi_b_unit][r->ext.channel];
    in_write = true;
    fsp_err_t err = R_OSPI_B_Write(&r->ctrl, source_data, (uint8_t *) (uintptr_t) expected_dest, length);
    in_write = false;
    return err;
}

static void length_case(unsigned channel, unsigned unit, unsigned cs, uint32_t length)
{
    initialize(channel);
    rig_t r;
    setup(&r, channel, unit, cs);
    assert(R_OSPI_B_Open(&r.ctrl, &r.cfg) == FSP_SUCCESS);
    unsigned before = mmio_accesses;
    fsp_err_t err = write_rig(&r, length);
    if (length > 65535U)
    {
        assert(err == FSP_ERR_INVALID_SIZE && "oversize DMA accepted");
        assert(mmio_accesses == before && bwe_writes == 0U && software_starts == 0U && reconfigs == 0U);
    }
    else
        assert(err == FSP_SUCCESS && completions == 1U);
    assert(R_OSPI_B_Close(&r.ctrl) == FSP_SUCCESS);
}

static void wren_case(unsigned channel, unsigned unit, unsigned cs)
{
    initialize(channel);
    rig_t r;
    setup(&r, channel, unit, cs);
    r.cfg.write_enable_command = 6U;
    /* With no status command, the actual helper cannot verify WEL and returns WRITE_FAILED. */
    assert(R_OSPI_B_Open(&r.ctrl, &r.cfg) == FSP_SUCCESS);
    assert(write_rig(&r, 16U) == FSP_ERR_WRITE_FAILED && "WREN error ignored");
    assert(bwe_writes == 0U && software_starts == 0U && reconfigs == 0U && !pending);
    r.cfg.write_enable_command = 0U;
    assert(write_rig(&r, 16U) == FSP_SUCCESS);
    assert(R_OSPI_B_Close(&r.ctrl) == FSP_SUCCESS);
}

static void recovery_barrier(rig_t * r)
{
    unsigned before = mmio_accesses;
    spi_flash_status_t status;
    spi_flash_direct_transfer_t direct = {0};
    assert(R_OSPI_B_Open(&r->ctrl, &r->cfg) == FSP_ERR_IN_USE);
    assert(write_rig(r, 16U) == FSP_ERR_IN_USE);
    assert(R_OSPI_B_DirectTransfer(&r->ctrl, &direct, SPI_FLASH_DIRECT_TRANSFER_DIR_READ) == FSP_ERR_IN_USE);
    assert(R_OSPI_B_Erase(&r->ctrl, (uint8_t *) (uintptr_t) expected_dest, 8U) == FSP_ERR_IN_USE);
    assert(R_OSPI_B_StatusGet(&r->ctrl, &status) == FSP_ERR_IN_USE);
    assert(R_OSPI_B_SpiProtocolSet(&r->ctrl, SPI_FLASH_PROTOCOL_EXTENDED_SPI) == FSP_ERR_IN_USE);
    assert(R_OSPI_B_AutoCalibrate(&r->ctrl) == FSP_ERR_IN_USE);
    assert(R_OSPI_B_XipEnter(&r->ctrl) == FSP_ERR_IN_USE);
    assert(R_OSPI_B_XipExit(&r->ctrl) == FSP_ERR_IN_USE);
    assert(mmio_accesses == before && "recovery operation reached MMIO");
}

static void error_case(unsigned channel, unsigned unit, unsigned cs, unsigned fail, unsigned abort)
{
    initialize(channel);
    rig_t r;
    setup(&r, channel, unit, cs);
    assert(R_OSPI_B_Open(&r.ctrl, &r.cfg) == FSP_SUCCESS);
    fault = fail;
    abort_fault = abort;
    hold_active = true;
    fsp_err_t err = write_rig(&r, 16U);
    if (abort != ABORT_OK)
    {
        assert(err == FSP_ERR_IN_USE && "failed cleanup did not retain recovery state");
        assert(channels[0x40U * channel + 0x30U] == 1U && "BWE cleared before quiescence");
        assert(info.p_src == source_data && (uintptr_t) info.p_dest == expected_dest);
        recovery_barrier(&r);
        unsigned before = bwe_writes;
        assert(R_OSPI_B_Close(&r.ctrl) == FSP_ERR_IN_USE);
        assert(bwe_writes == before && r.dctrl.open != 0U);
        abort_fault = ABORT_OK;
        assert(R_OSPI_B_Close(&r.ctrl) == FSP_SUCCESS);
        assert(r.dctrl.open == 0U && r.ctrl.open == 0U && !pending);
        fault = NONE;
        assert(R_OSPI_B_Open(&r.ctrl, &r.cfg) == FSP_SUCCESS);
    }
    else
    {
        assert(err == FSP_ERR_NOT_ENABLED && "DMA error not propagated");
        assert(channels[0x40U * channel + 0x30U] == 0U && "BWE left enabled after DMA failure");
        assert((channels[0x40U * channel + 0x1cU] & 1U) == 0U && !pending);
        fault = NONE;
    }
    hold_active = false;
    assert(write_rig(&r, 16U) == FSP_SUCCESS && "retry has stale DMA state");
    abort_fault = CLOSE_ERROR;
    assert(R_OSPI_B_Close(&r.ctrl) == FSP_ERR_IN_USE && r.dctrl.open != 0U);
    recovery_barrier(&r);
    abort_fault = ABORT_OK;
    assert(R_OSPI_B_Close(&r.ctrl) == FSP_SUCCESS);
    assert(r.dctrl.open == 0U && r.ctrl.open == 0U);
}

static void open_case(unsigned channel, unsigned unit, unsigned cs, unsigned kind)
{
    initialize(channel);
    rig_t live, attempt;
    setup(&live, channel, unit, cs ^ 1U);
    assert(R_OSPI_B_Open(&live.ctrl, &live.cfg) == FSP_SUCCESS);
    setup(&attempt, channel, unit, cs);
    dmac_instance_ctrl_t foreign = {0};
    /* Kind 0: lower Open rejects. Kind 1: the same lower ctrl is already owned. */
    if (kind == 1U)
    {
        attempt.transfer.p_ctrl = &foreign;
        foreign = live.dctrl;
    }
    fault = kind == 0U ? OPEN_ERROR : NONE;
    uint8_t dma_before[sizeof(channels)];
    memcpy(dma_before, channels, sizeof(channels));
    R_XSPI0_Type ospi_before = ospi[unit];
    dmac_instance_ctrl_t foreign_before = foreign;
    unsigned starts_before = module_starts[FSP_IP_OSPI][unit], stops_before = module_stops[FSP_IP_OSPI][unit];
    unsigned accesses_before = mmio_accesses, opens_before = opens;
    fsp_err_t err = R_OSPI_B_Open(&attempt.ctrl, &attempt.cfg);
    assert(err == (kind == 0U ? FSP_ERR_NOT_ENABLED : FSP_ERR_ALREADY_OPEN) && "lower Open error ignored");
    assert(attempt.ctrl.open == 0U && attempt.dctrl.open == 0U);
    assert(memcmp(&foreign, &foreign_before, sizeof(foreign)) == 0 && "foreign DMAC changed");
    assert(memcmp(dma_before, channels, sizeof(channels)) == 0);
    assert(memcmp(&ospi_before, &ospi[unit], sizeof(ospi_before)) == 0);
    assert(starts_before == module_starts[FSP_IP_OSPI][unit] && stops_before == module_stops[FSP_IP_OSPI][unit]);
    assert(accesses_before == mmio_accesses && closes == 0U && opens == opens_before + (kind == 0U));
    fault = NONE;
    assert(live.dctrl.open != 0U);
    assert(R_OSPI_B_Close(&live.ctrl) == FSP_SUCCESS);
}

static void late_open_case(unsigned channel, unsigned unit, unsigned cs, bool cleanup_failure)
{
    initialize(channel);
    rig_t live, attempt;
    unsigned other = channel ^ 1U;
    setup(&live, other, unit, cs ^ 1U);
    channels[0x40U * other + 0x1eU] = 0U;
    assert(R_OSPI_B_Open(&live.ctrl, &live.cfg) == FSP_SUCCESS);
    setup(&attempt, channel, unit, cs);
    attempt.cfg.spi_protocol = SPI_FLASH_PROTOCOL_8D_8D_8D;
    attempt.ext.data_latch_delay_clocks = 0U;
    attempt.ext.p_autocalibration_preamble_pattern_addr = (uint8_t *) 0x1234U;
    R_XSPI0_Type previous = ospi[unit];
    unsigned stops_before = module_stops[FSP_IP_OSPI][unit];
    abort_fault = cleanup_failure ? CLOSE_ERROR : ABORT_OK;
    assert(R_OSPI_B_Open(&attempt.ctrl, &attempt.cfg) ==
           (cleanup_failure ? FSP_ERR_IN_USE : FSP_ERR_INVALID_ADDRESS) && "late Open failed rollback");
    assert(ospi[unit].BMCTL0 == previous.BMCTL0 && ospi[unit].WRAPCFG == previous.WRAPCFG);
    assert(memcmp(&ospi[unit].CMCFGCS[cs ^ 1U], &previous.CMCFGCS[cs ^ 1U], sizeof(previous.CMCFGCS[0])) == 0);
    assert(module_stops[FSP_IP_OSPI][unit] == stops_before && live.dctrl.open != 0U);
    assert(last_closed == (transfer_ctrl_t *) &attempt.dctrl && "closed someone else's DMA resource");
    if (cleanup_failure)
    {
        recovery_barrier(&attempt);
        abort_fault = ABORT_OK;
        assert(R_OSPI_B_Close(&attempt.ctrl) == FSP_SUCCESS);
    }
    assert(attempt.ctrl.open == 0U && attempt.dctrl.open == 0U);
    attempt.cfg.spi_protocol = SPI_FLASH_PROTOCOL_EXTENDED_SPI;
    attempt.ext.data_latch_delay_clocks = 1U;
    assert(R_OSPI_B_Open(&attempt.ctrl, &attempt.cfg) == FSP_SUCCESS);
    assert(R_OSPI_B_Close(&attempt.ctrl) == FSP_SUCCESS);
    active_channel = other;
    assert(R_OSPI_B_Close(&live.ctrl) == FSP_SUCCESS);
}

static void solo_late_open_case(unsigned channel, unsigned unit, unsigned cs, bool cleanup_failure)
{
    initialize(channel);
    rig_t r;
    setup(&r, channel, unit, cs);
    r.cfg.spi_protocol = SPI_FLASH_PROTOCOL_8D_8D_8D;
    r.ext.data_latch_delay_clocks = 0U;
    r.ext.p_autocalibration_preamble_pattern_addr = (uint8_t *) 0x1234U;
    abort_fault = cleanup_failure ? CLOSE_ERROR : ABORT_OK;
    assert(R_OSPI_B_Open(&r.ctrl, &r.cfg) == (cleanup_failure ? FSP_ERR_IN_USE : FSP_ERR_INVALID_ADDRESS));
    assert(module_starts[FSP_IP_OSPI][unit] == 1U && module_stops[FSP_IP_OSPI][unit] == !cleanup_failure);
    if (cleanup_failure)
    {
        recovery_barrier(&r);
        abort_fault = ABORT_OK;
        assert(R_OSPI_B_Close(&r.ctrl) == FSP_SUCCESS);
    }
    assert(r.ctrl.open == 0U && r.dctrl.open == 0U && module_stops[FSP_IP_OSPI][unit] == 1U);
    r.cfg.spi_protocol = SPI_FLASH_PROTOCOL_EXTENDED_SPI;
    r.ext.data_latch_delay_clocks = 1U;
    assert(R_OSPI_B_Open(&r.ctrl, &r.cfg) == FSP_SUCCESS);
    assert(R_OSPI_B_Close(&r.ctrl) == FSP_SUCCESS);
}

int main(int argc, char ** argv)
{
    if (argc > 1)
    {
        const char * mode = argv[1];
        if (!strcmp(mode, "invalid"))
            one_case(0U, 0U, 0U, true, false);
        else if (!strcmp(mode, "pre-enabled"))
            one_case(0U, 0U, 0U, false, true);
        else if (!strcmp(mode, "length65536"))
            length_case(0U, 0U, 0U, 65536U);
        else if (!strcmp(mode, "length65537"))
            length_case(0U, 0U, 0U, 65537U);
        else if (!strcmp(mode, "wren"))
            wren_case(0U, 0U, 0U);
        else if (!strcmp(mode, "open-error"))
            open_case(0U, 0U, 0U, 0U);
        else if (!strcmp(mode, "foreign"))
            open_case(0U, 0U, 0U, 1U);
        else if (!strcmp(mode, "reconfigure"))
            error_case(0U, 0U, 0U, RECONFIG_ERROR, ABORT_OK);
        else if (!strcmp(mode, "start"))
            error_case(0U, 0U, 0U, START_ERROR, ABORT_OK);
        else if (!strcmp(mode, "info"))
            error_case(0U, 0U, 0U, INFO_ERROR, ABORT_OK);
        else if (!strcmp(mode, "abort"))
            error_case(0U, 0U, 0U, INFO_ERROR, DISABLE_ERROR);
        else if (!strcmp(mode, "abort-dte"))
            error_case(0U, 0U, 0U, START_ERROR, DISABLE_NO_EFFECT);
        else if (!strcmp(mode, "abort-act"))
            error_case(0U, 0U, 0U, INFO_ERROR, ACT_STUCK);
        else
            one_case((unsigned) strtoul(mode, NULL, 10), 0U, 0U, false, false);
    }
    else
    {
#if CHECKS
        initialize(0U);
        rig_t missing_transfer;
        setup(&missing_transfer, 0U, 0U, 0U);
        missing_transfer.ext.p_lower_lvl_transfer = NULL;
        assert(R_OSPI_B_Open(&missing_transfer.ctrl, &missing_transfer.cfg) == FSP_ERR_ASSERTION);
        assert(opens == 0U && mmio_accesses == 0U && missing_transfer.ctrl.open == 0U);
#endif
        for (unsigned ch = 0; ch < 8U; ++ch)
        for (unsigned unit = 0; unit < 2U; ++unit)
        for (unsigned cs = 0; cs < 2U; ++cs)
        {
            one_case(ch, unit, cs, false, false);
            length_case(ch, unit, cs, 1U);
            length_case(ch, unit, cs, 65535U);
            length_case(ch, unit, cs, 65536U);
            length_case(ch, unit, cs, 65537U);
            wren_case(ch, unit, cs);
            open_case(ch, unit, cs, 0U);
            open_case(ch, unit, cs, 1U);
            late_open_case(ch, unit, cs, false);
            late_open_case(ch, unit, cs, true);
            solo_late_open_case(ch, unit, cs, false);
            solo_late_open_case(ch, unit, cs, true);
            for (unsigned f = RECONFIG_ERROR; f <= INFO_LATER_ERROR; ++f)
                error_case(ch, unit, cs, f, ABORT_OK);
            for (unsigned f = DISABLE_ERROR; f <= ACT_STUCK; ++f)
                error_case(ch, unit, cs, INFO_ERROR, f);
            error_case(ch, unit, cs, START_ERROR, DISABLE_NO_EFFECT);
        }
        one_case(0U, 0U, 0U, true, false);
    }
    puts("OSPI DMA cases passed");
    return 0;
}
