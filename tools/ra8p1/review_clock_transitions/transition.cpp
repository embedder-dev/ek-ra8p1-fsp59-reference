// Primary independent anchors: HM 9.2.2/3 pp327-331; 60.4.3 pp3559-3560.
// Every production clock-register write is checked, not just the final register image.
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <algorithm>
#include <vector>
#include "configuration.h"
static bool observing;
static void check_clocks();
struct Register {
    uint32_t value = 0;
    operator uint32_t() const { return value; }
    Register &operator=(uint32_t v) { value = v; if (observing) check_clocks(); return *this; }
};
static struct { Register SCKDIVCR, SCKDIVCR2, SCKSCR, MOCOCR; } system_regs;
static struct { Register MRCPFB, MRCFREQ, MREFREQ; } mram_regs;
#define R_SYSTEM (&system_regs)
#define R_MRAM (&mram_regs)
static uint32_t g_clock_freq[11] = {48000000,8000000,32768,24000000,32768,1000000000};
static uint32_t SystemCoreClock;
static const unsigned divisors[16] = {1,2,4,8,16,32,64,0,3,6,12,24,0,0,0,0};
static std::vector<uint32_t> packed_writes;
static unsigned waits, prefetch_reads, delays, moco_delays;
static unsigned mhz(unsigned hz) { return hz <= 32768 ? 0 : (hz + 999999) / 1000000; }
static void check_clocks() {
    unsigned d[12];
    for (unsigned i=0; i<8; ++i) d[i] = (system_regs.SCKDIVCR.value >> (4*i)) & 15;
    for (unsigned i=0; i<4; ++i) d[8+i] = (system_regs.SCKDIVCR2.value >> (4*i)) & 15;
    bool thirds=false, halves=false;
    for (auto &v : d) { assert(divisors[v]); thirds |= v>=8; halves |= v>0 && v<8; v=divisors[v]; }
    assert(!(thirds && halves));
    assert(d[6] % d[11] == 0); // MRI:ICLK=N:1
    for (unsigned i=8; i<11; ++i) assert(d[11] % d[i] == 0); // CPU0/CPU1/NPU:MRI=N:1
    for (unsigned i : {2U,3U,4U,7U}) assert(d[i] % d[6] == 0); // ICLK >= PCLKA/B, BCLK, MRP
    unsigned hz = g_clock_freq[system_regs.SCKSCR.value];
    assert(hz/d[8] <= 1000000000 && hz/d[9] <= 250000000 && hz/d[10] <= 500000000);
    assert(hz/d[11] <= 250000000 && hz/d[6] <= 250000000 && hz/d[7] <= 125000000);
    assert(hz/d[3] <= 125000000 && hz/d[2] <= 62500000);
    assert((mram_regs.MRCFREQ.value & 0x3ff) >= mhz(hz/d[11]));
    assert((mram_regs.MREFREQ.value & 0xff) >= mhz(hz/d[7]));
    packed_writes.push_back(system_regs.SCKDIVCR2.value);
}
#define BSP_FEATURE_CGC_REGISTER_SET_B 0
#define BSP_FEATURE_CGC_HAS_CPUCLK 1
#define BSP_FEATURE_CGC_SCKDIVCR2_HAS_EXTRA_CLOCKS 1
#define BSP_PRV_CPUCK_MASK 15U
#define FSP_PRIV_CLOCK_ICLK 24U
#define FSP_PRV_SCKDIVCR_DIV_MASK 15U
#define BSP_DELAY_UNITS_MICROSECONDS 1U
#define BSP_MOCO_FREQ_HZ 8000000U
#define BSP_CLOCKS_SOURCE_CLOCK_MOCO 1U
#define BSP_FEATURE_CGC_MOCO_STABILIZATION_MAX_US 4U
#define BSP_CFG_CLOCK_SETTLING_DELAY_US 2U
#define BSP_MAX_CLOCK_CHANGE_THRESHOLD 200000000U
#define R_MRAM_MRCFREQ_KEY_Pos 24U
#define R_MRAM_MREFREQ_KEY_Pos 24U
#define R_MRAM_MRCFREQ_MRCMHZ_Msk 0x3ffU
#define R_MRAM_MREFREQ_MREMHZ_Msk 0xffU
#define FSP_HARDWARE_REGISTER_WAIT(reg, expected) do { assert((reg)==(expected)); ++waits; } while (0)
#define FSP_REGISTER_READ(reg) do { (void)(reg); ++prefetch_reads; } while (0)
static void SystemCoreClockUpdate() {
    unsigned shift = BSP_CFG_CPU_CORE ? 4 : 0;
    SystemCoreClock = g_clock_freq[system_regs.SCKSCR.value] /
                      divisors[(system_regs.SCKDIVCR2.value >> shift) & 15];
}
static void R_BSP_SoftwareDelay(unsigned us, unsigned units) {
    assert(units == 1 && (us == 2 || us == 4));
    if (us == 4) { assert(system_regs.MOCOCR.value == 0); ++moco_delays; }
    else ++delays;
}
static uint8_t bsp_clock_set_prechange(uint32_t) { return 0; }
static void bsp_clock_set_postchange(uint32_t, uint8_t) {}
#include "production_mram.inc"
#include "production_transition.inc"
#include "production_runtime.inc"
#define BSP_CFG_CLOCK_SOURCE 5U
#define BSP_PRV_STARTUP_SCKDIVCR 0x54444444U
#define BSP_PRV_STARTUP_SCKDIVCR2 0x4321U
#include "production_cold.inc"
static void initial(unsigned source, uint32_t d, uint16_t d2) {
    observing=false;
    system_regs.SCKSCR=source; system_regs.SCKDIVCR=d; system_regs.SCKDIVCR2=d2; system_regs.MOCOCR=source!=1;
    unsigned hz=g_clock_freq[source];
    mram_regs.MRCPFB=1;
    mram_regs.MRCFREQ=0x1e000000|mhz(hz/divisors[d2>>12]);
    mram_regs.MREFREQ=0xe1000000|mhz(hz/divisors[d>>28]);
    waits=prefetch_reads=delays=moco_delays=0; packed_writes.clear();
    SystemCoreClockUpdate(); observing=true; check_clocks();
}
static void finish(unsigned source, uint32_t d, uint16_t d2) {
    check_clocks();
    assert(system_regs.SCKSCR.value==source && system_regs.SCKDIVCR.value==d && system_regs.SCKDIVCR2.value==d2);
    unsigned hz=g_clock_freq[source];
    assert(mram_regs.MRCFREQ.value==(0x1e000000|mhz(hz/divisors[d2>>12])));
    assert(mram_regs.MREFREQ.value==(0xe1000000|mhz(hz/divisors[d>>28])));
    assert(mram_regs.MRCPFB.value==(hz/divisors[d2>>12]>100000000));
    assert(SystemCoreClock==hz/divisors[(d2>>(BSP_CFG_CPU_CORE?4:0))&15]);
    assert(prefetch_reads==3 && waits>0);
}
static void run(unsigned old_source,uint32_t old_d,uint16_t old_d2,unsigned source,uint32_t d,uint16_t d2) {
    initial(old_source,old_d,old_d2); bsp_prv_clock_set(source,d,d2); finish(source,d,d2);
}
int main() {
    initial(1,0,0); bsp_prv_clock_set_hard_reset(); finish(5,0x54444444,0x4321);
#if BSP_CFG_CLOCK_SETTLING_DELAY_ENABLE
    assert(std::find(packed_writes.begin(),packed_writes.end(),0x4322)!=packed_writes.end());
    assert(std::find(packed_writes.begin(),packed_writes.end(),0x7322)==packed_writes.end());
#endif
    // Equal/faster source, but slower divided MRI; inverse direction on slower source.
    run(0,0x11111111,0,5,0x66666666,0x5555);
    run(5,0x66666666,0x6666,0,0x11111111,0);
    run(5,0x43333433,0x2220,5,0x66666666,0x5431);
    run(5,0x66666666,0x5431,5,0x43333433,0x2220);
    // Independent /3 fields and both divider-family crossings through MOCO.
    run(1,0,0,5,0xA99AAB99,0x9898);
    run(5,0xA99AAB99,0x9898,5,0x43333433,0x2220);
    assert(system_regs.MOCOCR.value==1 && moco_delays==1);
    run(5,0x43333433,0x2220,5,0xA99AAB99,0x9898);
    // All /64 and /24 legal extrema, mixed independent old/new field directions.
    for (unsigned i=0; i<100; ++i) {
        run(5,0x66666666,0x6666,0,0x11111111,0);
        run(0,0x11111111,0,5,0xBBBBBBBB,0xBBBB);
        run(5,0xBBBBBBBB,0xBBBB,5,0x54444444,0x4321);
    }
    std::puts("transition/cold-start independent numeric and every-write order anchors passed");
}
