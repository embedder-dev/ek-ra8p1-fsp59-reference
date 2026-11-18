/* SCISPI-001..003 oracles: HM39.6.5 Fig39.69, 39.19.6 and 39.19.15.
 * LLVM substitutes only volatile loads/stores in the complete production TU.
 * This model deliberately delays internal stop, TDR->TSR and ORER clearing. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "r_sci_b_spi.h"

R_SCI_B0_Type review_regs[10];
static sci_b_spi_instance_ctrl_t ctrl;
static spi_cfg_t cfg;
static sci_b_spi_extended_cfg_t ext;
static spi_callback_args_t callback_memory;
static uint8_t source[] = {0xA5, 0x3C, 0xE1};
static uint8_t destination[3];
static uint32_t ccr0, cesr, csr, rdr;
static unsigned stop_delay, empty_delay, clear_delay;
static unsigned polls, drains, callbacks, writes, shifts, scenario;
static bool restart;
static uint8_t transmitted[3], shifted[3];
struct access { char kind; size_t offset; uint32_t value; };
static struct access accesses[128];
static unsigned naccess;
#define RUN (R_SCI_B0_CCR0_TE_Msk | R_SCI_B0_CCR0_RE_Msk)
#define INTERRUPTS (R_SCI_B0_CCR0_TIE_Msk | R_SCI_B0_CCR0_RIE_Msk | R_SCI_B0_CCR0_TEIE_Msk)
#define INTERNAL (R_SCI_B0_CESR_TIST_Msk | R_SCI_B0_CESR_RIST_Msk)
#define OFF(r) offsetof(R_SCI_B0_Type, r)
_Static_assert(OFF(CESR) == 0x1c, "HM39 CESR address");
_Static_assert(OFF(CSR) == 0x48, "HM39 CSR address");
_Static_assert(OFF(TDR) == 0x04, "HM39 TDR address");
_Static_assert(OFF(RDR) == 0x00, "HM39 RDR address");
_Static_assert(R_SCI_B0_CSR_ORER_Msk == (1UL << 24), "HM39 ORER");
_Static_assert(R_SCI_B0_CSR_TDRE_Msk == (1UL << 29), "HM39 TDRE");

static void record(char kind, size_t offset, uint32_t value)
{
    assert(naccess < sizeof(accesses) / sizeof(accesses[0]));
    accesses[naccess++] = (struct access) {kind, offset, value};
}
static size_t offset_of(void const * address)
{
    uintptr_t base = (uintptr_t) &review_regs[cfg.channel];
    uintptr_t actual = (uintptr_t) address;
    assert(actual >= base && actual < base + sizeof(R_SCI_B0_Type));
    return actual - base;
}
uint32_t review_mmio_read32(void const * address)
{
    size_t off = offset_of(address);
    uint32_t result = 0;
    if (off == OFF(CCR0)) { result = ccr0; }
    else if (off == OFF(CSR))
    {
        if (empty_delay && --empty_delay == 0U)
        {
            assert(shifts < sizeof(shifted));
            shifted[shifts++] = transmitted[writes - 1U];
            csr |= R_SCI_B0_CSR_TDRE_Msk;
        }
        if (clear_delay && --clear_delay == 0U) { csr &= ~R_SCI_B0_CSR_ORER_Msk; }
        result = csr;
    }
    else if (off == OFF(RDR))
    {
        if (scenario == 1U) { assert(cesr == 0U && (ccr0 & RUN) == 0U); }
        drains++;
        result = rdr;
        csr &= ~R_SCI_B0_CSR_RDRF_Msk;
    }
    else { assert(!"unexpected 32-bit MMIO read"); }
    record('R', off, result);
    return result;
}
uint8_t review_mmio_read8(void const * address)
{
    size_t off = offset_of(address);
    assert(off == OFF(CESR));
    if (stop_delay && --stop_delay == 0U) { cesr = 0U; }
    record('R', off, cesr);
    return (uint8_t) cesr;
}
void review_mmio_write32(void * address, uint32_t value)
{
    size_t off = offset_of(address);
    record('W', off, value);
    if (off == OFF(CCR0))
    {
        if ((value & RUN) && !(ccr0 & RUN)) { assert(cesr == 0U); }
        if ((ccr0 & RUN) && !(value & RUN))
        {
            if (scenario == 1U) { assert(!(ccr0 & INTERRUPTS)); }
            cesr = INTERNAL;
            stop_delay = 4U;
        }
        ccr0 = value;
    }
    else if (off == OFF(CFCLR))
    {
        assert(value == R_SCI_B0_CFCLR_ORERC_Msk);
        assert(drains == 1U && cesr == 0U && !(ccr0 & RUN));
        clear_delay = 3U;
    }
    else if (off == OFF(TDR))
    {
        assert((ccr0 & R_SCI_B0_CCR0_TE_Msk) != 0U);
        assert(writes < sizeof(transmitted));
        /* Any premature second preload overwrites the first byte. */
        assert((csr & R_SCI_B0_CSR_TDRE_Msk) != 0U);
        transmitted[writes++] = (uint8_t) value;
        csr &= ~R_SCI_B0_CSR_TDRE_Msk;
        empty_delay = 3U;
    }
    else { assert(!"unexpected MMIO write"); }
}
void review_mmio_write8(void * address, uint8_t value)
{ (void) address; (void) value; assert(!"unexpected byte write"); }
/* DTC descriptors also have volatile members; these are RAM, never SCI MMIO. */
static void descriptor_address(void const * address)
{
    uintptr_t actual = (uintptr_t) address;
    uintptr_t base = (uintptr_t) review_regs;
    assert(actual < base || actual >= base + sizeof(review_regs));
}
uint16_t review_mmio_read16(void const * address)
{ descriptor_address(address); return *(volatile uint16_t const *) address; }
void review_mmio_write16(void * address, uint16_t value)
{ descriptor_address(address); *(volatile uint16_t *) address = value; }
void * review_mmio_readptr(void const * address)
{ descriptor_address(address); return *(void * volatile const *) address; }
void review_mmio_writeptr(void * address, void * value)
{ descriptor_address(address); *(void * volatile *) address = value; }
void review_poll(void) { polls++; assert(polls < 64U); }
void R_BSP_IrqCfgEnable(IRQn_Type irq, uint8_t priority, void * context)
{ (void) irq; (void) priority; (void) context; }
void R_BSP_IrqDisable(IRQn_Type irq) { assert(irq == cfg.rxi_irq); }
void R_BSP_IrqEnableNoClear(IRQn_Type irq) { assert(irq == cfg.rxi_irq); }
void R_BSP_IrqStatusClear(IRQn_Type irq) { assert(irq == cfg.eri_irq || irq == cfg.tei_irq); }
IRQn_Type R_FSP_CurrentIrqGet(void) { return scenario == 1U ? cfg.eri_irq : cfg.tei_irq; }
void * R_FSP_IsrContextGet(IRQn_Type irq) { (void) irq; return &ctrl; }
uint32_t R_FSP_SystemClockHzGet(unsigned clock) { (void) clock; return 125000000U; }
uint32_t R_FSP_SciSpiClockHzGet(void) { return 24000000U; }
uint32_t R_FSP_SciClockHzGet(void) { return 24000000U; }
void sci_b_spi_eri_isr(void);
void sci_b_spi_tei_isr(void);

static unsigned find(char kind, size_t offset, unsigned start)
{
    for (unsigned i = start; i < naccess; i++)
    { if (accesses[i].kind == kind && accesses[i].offset == offset) { return i; } }
    assert(!"required MMIO access missing");
    return 0;
}
static void callback(spi_callback_args_t * args)
{
    assert(args->channel == cfg.channel && args->p_context == &cfg);
    assert(args == &callback_memory);
    assert(cesr == 0U && stop_delay == 0U && !(ccr0 & RUN));
    assert(args->event == (scenario == 1U ? SPI_EVENT_ERR_READ_OVERFLOW : SPI_EVENT_TRANSFER_COMPLETE));
    unsigned stopped = find('R', OFF(CESR), 0);
    while (accesses[stopped].value) { stopped = find('R', OFF(CESR), stopped + 1U); }
    if (scenario == 1U)
    {
        assert(drains == 1U && !(csr & (R_SCI_B0_CSR_ORER_Msk | R_SCI_B0_CSR_RDRF_Msk)));
        unsigned read = find('R', OFF(RDR), stopped + 1U);
        unsigned clear = find('W', OFF(CFCLR), read + 1U);
        unsigned acknowledged = find('R', OFF(CSR), clear + 1U);
        while (accesses[acknowledged].value & R_SCI_B0_CSR_ORER_Msk)
        { acknowledged = find('R', OFF(CSR), acknowledged + 1U); }
        assert(acknowledged > clear);
    }
    callbacks++;
    if (restart)
    {
        csr |= R_SCI_B0_CSR_TDRE_Msk;
        assert(R_SCI_B_SPI_WriteRead(&ctrl, source, destination, 1, SPI_BIT_WIDTH_8_BITS) == FSP_SUCCESS);
        assert((ccr0 & RUN) == RUN && ctrl.tx_count == 1U && ctrl.rx_count == 0U);
    }
}
static void setup(unsigned channel)
{
    memset(&ctrl, 0, sizeof(ctrl));
    memset(&cfg, 0, sizeof(cfg));
    memset(&ext, 0, sizeof(ext));
    cfg.channel = (uint8_t) channel;
    cfg.rxi_irq = 10; cfg.txi_irq = 11; cfg.tei_irq = 12; cfg.eri_irq = 13;
    cfg.p_extend = &ext;
    ctrl.open = 0x53434953U;
    ctrl.p_cfg = &cfg;
    ctrl.p_reg = &review_regs[channel];
    ctrl.p_callback = callback;
    ctrl.p_context = &cfg;
    ctrl.p_callback_memory = &callback_memory;
    memset(&callback_memory, 0xA5, sizeof(callback_memory));
    csr = R_SCI_B0_CSR_TDRE_Msk;
}
int main(int argc, char ** argv)
{
    assert(argc == 4);
    scenario = (unsigned) strtoul(argv[1], NULL, 0);
    unsigned parameter = (unsigned) strtoul(argv[2], NULL, 0);
    setup((unsigned) strtoul(argv[3], NULL, 0));
    if (scenario == 1U || scenario == 2U)
    {
        restart = parameter != 0U;
        ccr0 = RUN | INTERRUPTS;
        if (scenario == 2U) { ccr0 &= ~R_SCI_B0_CCR0_RIE_Msk; }
        cesr = INTERNAL;
        if (scenario == 1U) { csr |= R_SCI_B0_CSR_ORER_Msk | R_SCI_B0_CSR_RDRF_Msk; rdr = 0x12ABU; }
        spi_callback_args_t saved = callback_memory;
        if (scenario == 1U) { sci_b_spi_eri_isr(); } else { sci_b_spi_tei_isr(); }
        assert(callbacks == 1U && polls >= 3U);
        assert(memcmp(&saved, &callback_memory, sizeof(saved)) == 0);
        assert(restart || !(ccr0 & (RUN | INTERRUPTS)));
    }
    else if (scenario == 3U)
    {
        cfg.operating_mode = SPI_MODE_SLAVE;
        ccr0 = R_SCI_B0_CCR0_SSE_Msk;
        bool dummy = (parameter & 1U) != 0U;
        unsigned count = (parameter & 2U) ? 2U : 1U;
        fsp_err_t err = dummy ? R_SCI_B_SPI_Read(&ctrl, destination, count, SPI_BIT_WIDTH_8_BITS) :
                               R_SCI_B_SPI_WriteRead(&ctrl, source, destination, count, SPI_BIT_WIDTH_8_BITS);
        assert(err == FSP_SUCCESS && writes == count && ctrl.tx_count == count);
        assert(transmitted[0] == (dummy ? 0U : source[0]));
        if (count == 2U)
        {
            assert(shifts == 1U && shifted[0] == transmitted[0]);
            assert(transmitted[1] == (dummy ? 0U : source[1]));
            assert(polls == 2U);
            unsigned first = find('W', OFF(TDR), 0);
            unsigned second = find('W', OFF(TDR), first + 1U);
            unsigned empty = find('R', OFF(CSR), first + 1U);
            while (!(accesses[empty].value & R_SCI_B0_CSR_TDRE_Msk))
            { empty = find('R', OFF(CSR), empty + 1U); }
            assert(empty < second);
        }
        else { assert(shifts == 0U && polls == 0U); }
        assert(ccr0 & R_SCI_B0_CCR0_SSE_Msk);
    }
    else if (scenario == 4U)
    {
        /* Public admission must not trust CCR0=0 while the previous stop is in flight. */
        cesr = INTERNAL; stop_delay = 4U;
        assert(R_SCI_B_SPI_Write(&ctrl, source, 1, SPI_BIT_WIDTH_8_BITS) == FSP_SUCCESS);
        assert(cesr == 0U && polls == 3U && (ccr0 & R_SCI_B0_CCR0_TE_Msk));
        unsigned acknowledged = find('R', OFF(CESR), 0);
        while (accesses[acknowledged].value)
        { acknowledged = find('R', OFF(CESR), acknowledged + 1U); }
        assert(find('W', OFF(CCR0), 0) > acknowledged);
    }
    else if (scenario == 5U)
    {
        ccr0 = parameter ? R_SCI_B0_CCR0_TE_Msk : R_SCI_B0_CCR0_RE_Msk;
        assert(R_SCI_B_SPI_Write(&ctrl, source, 1, SPI_BIT_WIDTH_8_BITS) == FSP_ERR_IN_USE);
        assert(naccess == 1U && ctrl.count == 0U && callbacks == 0U);
    }
    else { assert(!"unknown scenario"); }
    puts("production SCI_B SPI focused case passed");
    return 0;
}
