/* Host-only MMIO oracle for the complete production OSPI TU, not a flash/crypto emulator. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "r_ospi_b.h"

static R_XSPI0_Type regs[2];
static unsigned accesses, starts, mapped_writes;
static uintptr_t write_address;
static uint64_t written[4];
static unsigned active_unit, active_channel;
static const uint32_t bases[2][2] = {{0x80000000U, 0x90000000U}, {0x70000000U, 0x78000000U}};
static const uint32_t windows[2] = {0x10000000U, 0x08000000U};

static bool mapped(uintptr_t a)
{
    return a >= 0x70000000U && a < 0xa0000000U;
}

static void * resolve(void * p, unsigned bytes)
{
    uintptr_t a = (uintptr_t) p;
    for (unsigned u = 0; u < 2U; ++u)
    {
        uintptr_t base = 0x46000000U + u * 0x1000U;
        if (a >= base && a - base + bytes <= sizeof(regs[u]))
        {
            accesses++;
            return (uint8_t *) &regs[u] + a - base;
        }
    }
    assert(a > UINT32_MAX);
    return p;
}

static void memory_write(void * p, uint64_t v, unsigned bytes)
{
    if (!mapped((uintptr_t) p))
    {
        memcpy(resolve(p, bytes), &v, bytes);
        return;
    }
    assert(bytes == 8U && "destination bus width changed");
    assert(mapped_writes < 4U);
    accesses++;
    write_address = (uintptr_t) p;
    written[mapped_writes++] = v;
}

#define READ(width, type) type review_read##width(void * p) { type v; memcpy(&v, resolve(p, sizeof(v)), sizeof(v)); return v; }
#define WRITE(width, type) void review_write##width(void * p, type v) { memory_write(p, v, sizeof(v)); }
READ(8, uint8_t)
READ(16, uint16_t)
READ(32, uint32_t)
READ(64, uint64_t)
WRITE(8, uint8_t)
WRITE(16, uint16_t)
WRITE(32, uint32_t)
WRITE(64, uint64_t)
/* Redirect the old, non-volatile mapped store too, retaining the original source load and its UBSan check. */
void review_store64(void * p, uint64_t v) { memory_write(p, v, sizeof(v)); }
void review_module_start(unsigned ip, unsigned channel) { (void) ip; (void) channel; starts++; }

static ospi_b_timing_setting_t timing;
static spi_flash_erase_command_t erases[] = {{.command = 0x20U, .size = 8U}, {.command = 0xc7U, .size = SPI_FLASH_ERASE_SIZE_CHIP_ERASE}};
static ospi_b_extended_cfg_t ext;
static spi_flash_cfg_t cfg;
static ospi_b_instance_ctrl_t ctrl;

static void open_case(unsigned unit, unsigned channel, unsigned encoding)
{
    ext = (ospi_b_extended_cfg_t) {.ospi_b_unit = unit, .channel = channel, .p_timing_settings = &timing,
                                  .data_latch_delay_clocks = 1U};
    cfg = (spi_flash_cfg_t) {.p_extend = &ext, .address_bytes = (spi_flash_address_bytes_t) encoding,
                            .spi_protocol = SPI_FLASH_PROTOCOL_EXTENDED_SPI, .page_size_bytes = 256U,
                            .read_command = 0xbU, .page_program_command = 2U,
                            .p_erase_command_list = erases, .erase_command_list_length = 2U};
    ctrl = (ospi_b_instance_ctrl_t) {0};
    active_unit = unit;
    active_channel = channel;
    memset(regs, 0, sizeof(regs));
    assert(R_OSPI_B_Open(&ctrl, &cfg) == FSP_SUCCESS);
}

/* HM45.2.1.4 p3001: apply the emitted register fields to the transmitted MSByte. */
static uint32_t frame_address(uint32_t cpu_address)
{
    uint32_t cmcfg = regs[active_unit].CMCFGCS[active_channel].CMCFG0;
    unsigned bytes = ((cmcfg >> 2U) & 3U) + 1U;
    uint32_t mask = bytes == 4U ? UINT32_MAX : ((1U << (bytes * 8U)) - 1U);
    uint32_t selected = ((cmcfg >> 16U) & 255U) << ((bytes - 1U) * 8U);
    return ((cpu_address & ~selected) | (((cmcfg >> 24U) << ((bytes - 1U) * 8U)) & selected)) & mask;
}

static void mapping_cases(void)
{
    const unsigned encodings[] = {0U, 1U, 2U, 3U, 0x13U};
    const uint32_t masks[2][5] = {{0U, 0U, 0U, 0xf0U, 0xf0U}, {0U, 0U, 0U, 0xf8U, 0xf8U}};
    for (unsigned u = 0; u < 2U; ++u)
    for (unsigned ch = 0; ch < 2U; ++ch)
    for (unsigned e = 0; e < 5U; ++e)
    {
        open_case(u, ch, encodings[e]);
        uint32_t cmcfg = regs[u].CMCFGCS[ch].CMCFG0;
        assert(((cmcfg >> 16U) & 255U) == masks[u][e] && "ADDRPEN erased valid address bits");
        assert(((cmcfg >> 2U) & 3U) == (encodings[e] & 3U));
        uint32_t size = e < 3U ? (1U << ((e + 1U) * 8U)) : windows[u];
        const uint32_t offsets[] = {0U, 1U, size / 2U, size - 1U};
        for (unsigned i = 0; i < 4U; ++i)
            assert(frame_address(bases[u][ch] + offsets[i]) == offsets[i] && "mapped flash address aliased");
        assert(R_OSPI_B_Close(&ctrl) == FSP_SUCCESS);
    }
}

static void bounds_cases(void)
{
    for (unsigned u = 0; u < 2U; ++u)
    for (unsigned ch = 0; ch < 2U; ++ch)
    for (unsigned e = 0; e < 5U; ++e)
    {
        unsigned enc = e == 4U ? 0x13U : e;
        uint32_t size = e < 3U ? (1U << ((e + 1U) * 8U)) : windows[u];
        uint32_t base = bases[u][ch];
        open_case(u, ch, enc);
        assert(R_OSPI_B_Erase(&ctrl, (uint8_t *)(uintptr_t)(base + size - 8U), 8U) == FSP_SUCCESS);
        assert(regs[u].CDBUF[0].CDA == size - 8U);
        assert(((regs[u].CDBUF[0].CDT >> 2U) & 7U) == ((enc & 3U) + 1U));
        assert(R_OSPI_B_Erase(&ctrl, (uint8_t *)(uintptr_t)base, SPI_FLASH_ERASE_SIZE_CHIP_ERASE) == FSP_SUCCESS);
        assert(((regs[u].CDBUF[0].CDT >> 2U) & 7U) == 0U);
        uint64_t data[2] = {0x0102030405060708ULL, 0U};
        mapped_writes = 0U;
        assert(R_OSPI_B_Write(&ctrl, (uint8_t *)data, (uint8_t *)(uintptr_t)(base + size - 8U), 8U) == FSP_SUCCESS);
        assert(mapped_writes == 1U && write_address == base + size - 8U && written[0] == data[0]);
        const uint32_t bad[] = {base + size, base + size + 8U, base - 8U, 0xfffffff8U};
        for (unsigned i = 0; i < 4U; ++i)
        {
            unsigned before = accesses;
            assert(R_OSPI_B_Erase(&ctrl, (uint8_t *)(uintptr_t)bad[i], 8U) == FSP_ERR_INVALID_ADDRESS && "command address width bound missing");
            assert(R_OSPI_B_Write(&ctrl, (uint8_t *)data, (uint8_t *)(uintptr_t)bad[i], 8U) == FSP_ERR_INVALID_ADDRESS);
            assert(accesses == before && "invalid command touched MMIO");
        }
        unsigned before = accesses;
        assert(R_OSPI_B_Erase(&ctrl, (uint8_t *)(uintptr_t)(base + size - 4U), 8U) == FSP_ERR_INVALID_ADDRESS);
        assert(accesses == before);
        /* Cross the 24-bit limit, not just the physical window or a page boundary. */
        if (e == 2U)
        {
            cfg.page_size_bytes = 0x02000000U;
            before = accesses;
            assert(R_OSPI_B_Write(&ctrl, (uint8_t *)data, (uint8_t *)(uintptr_t)(base + 0x00fffff8U), 16U) == FSP_ERR_INVALID_ADDRESS);
            assert(accesses == before);
        }
        uint32_t success = 1U << (30U + ch);
        memcpy((void *)&regs[u].INTS, &success, sizeof(success));
        ext.p_autocalibration_preamble_pattern_addr = (uint8_t *)(uintptr_t)(base + size - 16U);
        ctrl.spi_protocol = SPI_FLASH_PROTOCOL_8D_8D_8D;
        assert(R_OSPI_B_AutoCalibrate(&ctrl) == FSP_SUCCESS);
        assert(regs[u].CCCTLCS[ch].CCCTL3 == size - 16U);
        assert(((regs[u].CCCTLCS[ch].CCCTL1 >> 2U) & 7U) == ((enc & 3U) + 1U));
        ext.p_autocalibration_preamble_pattern_addr += 8U;
        before = accesses;
        assert(R_OSPI_B_AutoCalibrate(&ctrl) == FSP_ERR_INVALID_ADDRESS);
        assert(accesses == before);
        assert(R_OSPI_B_Close(&ctrl) == FSP_SUCCESS);
    }
    const unsigned invalid_encodings[] = {4U, 0x14U, 0xffU};
    for (unsigned i = 0; i < 3U; ++i)
    {
        ctrl = (ospi_b_instance_ctrl_t) {0};
        cfg.address_bytes = (spi_flash_address_bytes_t) invalid_encodings[i];
        unsigned before = accesses, before_starts = starts;
        assert(R_OSPI_B_Open(&ctrl, &cfg) == FSP_ERR_INVALID_ARGUMENT);
        assert(accesses == before && starts == before_starts);
    }
}

static void unaligned_cases(void)
{
    _Alignas(8) uint8_t data[32];
    for (unsigned i = 0; i < sizeof(data); ++i) data[i] = i + 1U;
    for (unsigned unit = 0; unit < 2U; ++unit)
    for (unsigned ch = 0; ch < 2U; ++ch)
    {
        open_case(unit, ch, 3U);
        for (unsigned alignment = 0; alignment < 8U; ++alignment)
        {
            mapped_writes = 0U;
            assert(R_OSPI_B_Write(&ctrl, data + alignment, (uint8_t *)(uintptr_t)(bases[unit][ch] + 0x100U), 16U) == FSP_SUCCESS);
            assert(mapped_writes == 2U && write_address == bases[unit][ch] + 0x108U);
            assert(memcmp(written, data + alignment, 16U) == 0);
        }
        assert(R_OSPI_B_Close(&ctrl) == FSP_SUCCESS);
    }
}

static void null_table_cases(void)
{
    const spi_flash_protocol_t protocols[] = {SPI_FLASH_PROTOCOL_EXTENDED_SPI, SPI_FLASH_PROTOCOL_8D_8D_8D,
        SPI_FLASH_PROTOCOL_1S_2S_2S, SPI_FLASH_PROTOCOL_2S_2S_2S, SPI_FLASH_PROTOCOL_1S_4S_4S, SPI_FLASH_PROTOCOL_4S_4S_4S};
    for (unsigned u = 0; u < 2U; ++u)
    for (unsigned ch = 0; ch < 2U; ++ch)
    {
        open_case(u, ch, 3U);
        for (unsigned p = 0; p < sizeof(protocols) / sizeof(protocols[0]); ++p)
        {
            ext.p_xspi_command_set = NULL;
            assert(R_OSPI_B_SpiProtocolSet(&ctrl, protocols[p]) == FSP_SUCCESS);
            assert(ctrl.p_cmd_set == NULL);
            assert((regs[u].CMCFGCS[ch].CMCFG1 & 0xffffU) == 0xb00U);
            ospi_b_table_t table = {.length = 1U, .p_table = NULL};
            ext.p_xspi_command_set = &table;
            assert(R_OSPI_B_SpiProtocolSet(&ctrl, protocols[p]) == FSP_SUCCESS);
            assert(ctrl.p_cmd_set == NULL);
            ospi_b_xspi_command_set_t command = {.protocol = protocols[p], .read_command = 0xee11U,
                                                .command_bytes = OSPI_B_COMMAND_BYTES_2};
            table.p_table = &command;
            assert(R_OSPI_B_SpiProtocolSet(&ctrl, protocols[p]) == FSP_SUCCESS);
            assert((protocols[p] == SPI_FLASH_PROTOCOL_EXTENDED_SPI) ? ctrl.p_cmd_set == NULL : ctrl.p_cmd_set == &command);
            table.length = 0U;
            assert(R_OSPI_B_SpiProtocolSet(&ctrl, protocols[p]) == FSP_SUCCESS);
            assert(ctrl.p_cmd_set == NULL);
        }
        assert(R_OSPI_B_Close(&ctrl) == FSP_SUCCESS);
        /* Same optional NULL contract applies to open with a non-SPI protocol. */
        ctrl = (ospi_b_instance_ctrl_t) {0};
        ext.p_xspi_command_set = NULL;
        cfg.spi_protocol = SPI_FLASH_PROTOCOL_1S_4S_4S;
        assert(R_OSPI_B_Open(&ctrl, &cfg) == FSP_SUCCESS);
        assert(R_OSPI_B_Close(&ctrl) == FSP_SUCCESS);
    }
}

int main(int argc, char ** argv)
{
    const char * which = argc > 1 ? argv[1] : "all";
    if (!strcmp(which, "all") || !strcmp(which, "map")) mapping_cases();
    if (!strcmp(which, "all") || !strcmp(which, "bounds")) bounds_cases();
    if (!strcmp(which, "all") || !strcmp(which, "unaligned")) unaligned_cases();
    if (!strcmp(which, "all") || !strcmp(which, "null")) null_table_cases();
    puts("OSPI cases passed");
    return 0;
}
