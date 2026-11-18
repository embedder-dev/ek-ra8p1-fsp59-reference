// Host-only keyed-register model; the clock update body is extracted unchanged.
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
#include "configuration.h"
#include "production_keys.inc"

struct Protection
{
    explicit Protection(uint16_t mask) : writable_mask(mask), state(0) {}
    uint16_t writable_mask;
    uint16_t state;
    std::vector<uint16_t> writes;

    operator uint16_t() const { return state; } // PRKEY is write-only.
    Protection & operator=(uint16_t value)
    {
        writes.push_back(value);
        if ((value & 0xFF00U) == 0xA500U)
        {
            state = value & writable_mask;
        }
        return *this;
    }
};

struct Registers
{
    Protection PRCR_S{0x3BU};  // HM 13.2.1: PRC0, PRC1, PRC3, PRC4, PRC5.
    Protection PRCR_NS{0x1BU}; // HM 13.2.2: PRC0, PRC1, PRC3, PRC4.
    struct { unsigned OCTACKSREQ, OCTACKSRDY; } OCTACKCR_b{};
    uint8_t OCTACKCR{};
    uint8_t OCTACKDIVCR{};
    uint8_t USBCKCR{}, CANFDCKCR{}, USB60CKCR{}, I3CCKCR{}, SCICKCR{};
    uint8_t SPICKCR{}, ADCCKCR{}, GPTCKCR{}, LCDCKCR{};
};

static Registers registers;
#define R_SYSTEM (&registers)
#define R_SYSTEM_OCTACKCR_OCTACKSREQ_Msk 0x40U
struct bsp_octaclk_settings_t { uint8_t divider, source_clock; };
static uint16_t initial_protection;
static bsp_octaclk_settings_t requested;
static unsigned waits;
static uint8_t old_divider;
#if defined(TEST_OCTA_REAL_STOP)
static struct { uint32_t MSTPCRB{}, MSTPCRC{}, MSTPCRD{}, MSTPCRE{}; } module_stops;
#define R_MSTP (&module_stops)
#define BSP_DELAY_UNITS_MICROSECONDS 1U
static uint32_t initial_stop;
static unsigned stop_waits;
static void R_BSP_SoftwareDelay(uint32_t, uint32_t)
{
    assert(false && "HM9.2.45 OCTA uses read confirmation, not a timed wait");
}
#endif

static Protection & active()
{
#if BSP_TZ_NONSECURE_BUILD
    return registers.PRCR_NS;
#else
    return registers.PRCR_S;
#endif
}

static Protection & inactive()
{
#if BSP_TZ_NONSECURE_BUILD
    return registers.PRCR_S;
#else
    return registers.PRCR_NS;
#endif
}

static void wait_for_state(char const * name, unsigned ready)
{
    assert(active().writes.size() == 1);
    assert(active().writes[0] == (0xA503U | initial_protection));
    assert(active().state == (initial_protection | 3U));
    assert(inactive().writes.empty());
#if defined(TEST_OCTA_REAL_STOP)
    if (std::strstr(name, "**pp_stop"))
    {
        assert(old_divider != 0U && ready == 0x30000U && stop_waits == 0U);
        assert(waits == 0U && registers.OCTACKCR_b.OCTACKSREQ == 0U);
        assert(module_stops.MSTPCRB == (initial_stop | 0x30000U));
        stop_waits++;
        return;
    }
    assert(stop_waits == (old_divider != 0U ? 1U : 0U));
    assert(module_stops.MSTPCRB == (initial_stop | (old_divider ? 0x30000U : 0U)));
#else
    (void) name;
#endif
    if (ready)
    {
        assert(waits == 0);
        assert(registers.OCTACKCR_b.OCTACKSREQ == 1);
        assert(registers.OCTACKDIVCR == old_divider);
        assert(registers.OCTACKCR == 1U);
    }
    else
    {
        assert(waits == 1);
        assert(registers.OCTACKDIVCR == requested.divider);
        assert(registers.OCTACKCR == requested.source_clock);
    }
    registers.OCTACKCR_b.OCTACKSRDY = ready;
    waits++;
}

#define FSP_HARDWARE_REGISTER_WAIT(reg, value) do { wait_for_state(#reg, value); assert((reg) == (value)); } while (0)
#define FSP_REGISTER_READ(reg) ((void) static_cast<uint16_t>(reg))
#define FSP_PARAMETER_NOT_USED(value) ((void)(value))
#include "production_octaclk.inc"

int main()
{
    // Reject unkeyed writes, and never return a previously written key.
    Protection model{0x3B};
    model = 0xA518;
    assert(static_cast<uint16_t>(model) == 0x18);
    model = 0x0003;
    assert(static_cast<uint16_t>(model) == 0x18);

    unsigned cases = 0;
    for (uint16_t mask = 0; mask <= active().writable_mask; mask++)
    {
        if (mask & ~active().writable_mask) { continue; }
        for (uint8_t source : {1, 5, 6, 7, 8, 9, 10})
        {
            for (uint8_t divider : {0, 1, 2, 3, 4, 7, 8, 9})
            for (uint8_t initial_divider : {0, 1, 9})
            for (uint32_t saved_stop : {0x123U, 0x10123U, 0x30123U})
            {
                active().state = initial_protection = mask;
                active().writes.clear();
                inactive().state = 0x18;
                inactive().writes.clear();
                registers.OCTACKCR_b.OCTACKSREQ = 0;
                registers.OCTACKCR_b.OCTACKSRDY = 0;
                registers.OCTACKCR = 1U;
                registers.OCTACKDIVCR = old_divider = initial_divider;
#if defined(TEST_OCTA_REAL_STOP)
                module_stops.MSTPCRB = initial_stop = saved_stop;
                module_stops.MSTPCRC = module_stops.MSTPCRD = module_stops.MSTPCRE = 0xA5A5A5A5U;
                stop_waits = 0U;
#else
                (void) saved_stop;
#endif
                waits = 0;
                requested = {divider, source};
                R_BSP_OctaclkUpdate(&requested);
                assert(waits == 2);
                assert(active().writes.size() == 2);
                assert(active().writes[1] == (0xA500U | mask));
                assert(active().state == mask);
                assert(inactive().writes.empty());
                assert(inactive().state == 0x18);
                assert(registers.OCTACKDIVCR == divider);
                assert(registers.OCTACKCR == source);
#if defined(TEST_OCTA_REAL_STOP)
                assert(stop_waits == (old_divider ? 1U : 0U));
                assert(module_stops.MSTPCRB == initial_stop);
                assert(module_stops.MSTPCRC == 0xA5A5A5A5U && module_stops.MSTPCRD == 0xA5A5A5A5U &&
                       module_stops.MSTPCRE == 0xA5A5A5A5U);
#endif
                cases++;
            }
        }
    }
    std::printf("keyed protection and OCTA settings passed: %u cases\n", cases);
}
