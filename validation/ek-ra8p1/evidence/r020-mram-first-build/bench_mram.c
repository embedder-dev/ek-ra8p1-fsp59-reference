#include "hal_data.h"
#include "r_mram.h"

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

void bench_emit(const char * text);
bool bench_mram(const char * command);

#if (BSP_CFG_CPU_CORE != 0) || BSP_TZ_SECURE_BUILD || BSP_TZ_NONSECURE_BUILD || !BSP_CFG_C_RUNTIME_INIT
 #error "MRAM fixture requires the GNU CPU0 Flat bench with C runtime initialization"
#endif

#define MRAM_START     (0x0207F800U)
#define MRAM_END       (0x02080000U)
#define MRAM_SIZE      (2048U)
#define MRAM_BASE      (0x02000000U)
#define SRAM_START     (0x22000000U)
#define SRAM_END       (0x220D0000U)
#define MRAM_CLOCK_HZ  (24000000U)
#define MRAM_CLOCK_MHZ (24U)
#define VECTOR_ALIGN   (512U)

/* HM §§7.2.8–9, 60.8.3, 60.9.1.2: BPS bit 255; PBPS bit 63 protects BPS bits 252–255. */
#define BPS_SEC_WORD   (0x02C9F21CU)
#define PBPS_SEC_WORD  (0x02E17704U)
#define PROTECTION_BIT (UINT32_C(1) << 31)

#if ((MRAM_START % MRAM_SIZE) != 0) || ((MRAM_END - MRAM_START) != MRAM_SIZE)
 #error "MRAM fixture window must be exactly one aligned block"
#endif

typedef enum
{
    MRAM_IDLE,
    MRAM_ARMED,
    MRAM_DIRTY,
    MRAM_DONE,
} mram_stage_t;

static mram_stage_t stage;
static uint8_t pattern[MRAM_SIZE] BSP_ALIGN_VARIABLE(32);
static uintptr_t vectors[BSP_VECTOR_TABLE_MAX_ENTRIES] BSP_ALIGN_VARIABLE(VECTOR_ALIGN);
_Static_assert(sizeof(vectors) <= VECTOR_ALIGN, "VTOR alignment too small for this core");

static void mram_exception(void) BSP_PLACE_IN_SECTION(".code_in_ram") __attribute__((noreturn, noinline));

static void mram_exception(void)
{
    /* NMI and faults must not fetch from MRAM or return to a possibly incomplete operation. */
    for (;;)
    {
        __NOP();
    }
}

static bool code_idle(void)
{
    /* Require empty and no sticky programming errors; don't clear evidence in preflight. */
    return (R_MRAM->MRCPS == R_MRAM_MRCPS_ABUFEMP_Msk) &&
           (0U != (R_MRAM->MSTATR & R_MRAM_MSTATR_MRDY_Msk)) &&
           (0U == R_MRAM->MASTAT) && (0U == R_MRAM->MENTRYR) &&
           (0U == (R_MRAM->MCTRSTATR & (R_MRAM_MCTRSTATR_TRBUSY_Msk | R_MRAM_MCTRSTATR_TRMD_Msk))) &&
           (R_MRAM->MREZS == R_MRAM_MREZS_WHUKZF_Msk);
}

static bool read_ecc_clean(void)
{
    return 0U == (R_MRAM->MRCRAES & (R_MRAM_MRCRAES_DECERRC_Msk | R_MRAM_MRCRAES_TEDERRC_Msk));
}

static const char * preflight(void)
{
    const flash_cfg_t * const cfg = g_bench_mram.p_cfg;
    const mram_extended_cfg_t * const ext = cfg->p_extend;
    if ((NULL == ext) || (ext->write_window_start != MRAM_START) || (ext->write_window_end != MRAM_END) ||
        (0U == ext->timeout) || ext->enable_extra_commands || cfg->data_flash_bgo || (NULL != cfg->p_callback))
    {
        return "MRAM BLOCK unexpected generated configuration\r\n";
    }

    if ((0U != __get_IPSR()) || (0U != __get_PRIMASK()) || (0U != __get_BASEPRI()) ||
        (0U != (DCB->DHCSR & DCB_DHCSR_C_DEBUGEN_Msk)) || (0U != R_CPU_DBG->DBGNVMCR) ||
        (0U != (R_CPU_CTRL->CPU1ACTCSR & (R_CPU_CTRL_CPU1ACTCSR_ACT_Msk | R_CPU_CTRL_CPU1ACTCSR_ACTREQ_Msk))))
    {
        return "MRAM BLOCK interrupt, debug or CPU1 state\r\n";
    }

    if ((0U == (R_MSTP->MSTPCRA & R_MSTP_MSTPCRA_MSTPA22_Msk)) &&
        ((0U != (R_DMA->DMAST & R_DMA_DMAST_DMST_Msk)) || (0U != (R_DTC->DTCST & R_DTC_DTCST_DTCST_Msk)) ||
         (0U != (R_DTC->DTCSTS & R_DTC_DTCSTS_ACT_Msk))))
    {
        return "MRAM BLOCK CPU0 DMA or DTC enabled\r\n";
    }

    /* HM §52.3.3.5, Table 52.1 and §52.8.11: CMS counts 32 KiB units from MRAM_BASE. */
    const uint32_t cms = (R_PSCU->CMSAMON & R_PSCU_CMSAMON_CMS_Msk) >> R_PSCU_CMSAMON_CMS_Pos;
    if (((cms != 0x1FFU) && ((cms < (MRAM_END - MRAM_BASE) / 32768U) || (cms > 32U))) ||
        (0U == (*(const volatile uint32_t *) BPS_SEC_WORD & PROTECTION_BIT)) ||
        (0U == (*(const volatile uint32_t *) PBPS_SEC_WORD & PROTECTION_BIT)) ||
        (0U != (R_MRAM->MRCPC0 | R_MRAM->MRCPC1 | R_MRAM->MRCBPROT0 | R_MRAM->MRCBPROT1)))
    {
        return "MRAM BLOCK unknown attribution or protected block\r\n";
    }

    if ((MRAM_CLOCK_HZ != BSP_CFG_XTAL_HZ) || (BSP_CLOCKS_SOURCE_CLOCK_MAIN_OSC != R_SYSTEM->SCKSCR) ||
        (0U == (R_SYSTEM->OSCSF & R_SYSTEM_OSCSF_MOSCSF_Msk)) ||
        (0U != (R_SYSTEM->OSTDSR & R_SYSTEM_OSTDSR_OSTDF_Msk)) ||
        (MRAM_CLOCK_HZ != R_FSP_SystemClockHzGet(FSP_PRIV_CLOCK_MRICLK)) ||
        (MRAM_CLOCK_HZ != R_FSP_SystemClockHzGet(FSP_PRIV_CLOCK_MRPCLK)) ||
        (MRAM_CLOCK_MHZ != R_MRAM->MRCFREQ) || (MRAM_CLOCK_MHZ != R_MRAM->MREFREQ) ||
        (0U != R_MRAM->MRCPFB) || (0U != (SCB->CCR & SCB_CCR_DC_Msk)) || (0U != R_MRAM->MRPSC))
    {
        return "MRAM BLOCK unexpected clocks, cache or programming mode\r\n";
    }

    /* Require register-start watchdog options and a fresh bench that never ran wdt-arm. */
    if ((UINT32_MAX != *(const volatile uint32_t *) 0x02C9F040U) || (0U != R_WDT0->WDTSR) ||
        !code_idle() || !read_ecc_clean() || (0U != (R_MRAM->MRCEECC & R_MRAM_MRCEECC_ECCBYPC_Msk)) ||
        (0U != (R_MRAM->MRCDECC & R_MRAM_MRCDECC_DECDISC_Msk)))
    {
        return "MRAM BLOCK watchdog, sequencer or ECC state\r\n";
    }

    const uintptr_t fault_pc = (uintptr_t) mram_exception & ~(uintptr_t) 1U;
    if (((uintptr_t) vectors < SRAM_START) || ((uintptr_t) vectors > SRAM_END - sizeof(vectors)) ||
        ((uintptr_t) pattern < SRAM_START) || ((uintptr_t) pattern > SRAM_END - sizeof(pattern)) ||
        (fault_pc < SRAM_START) || (fault_pc >= SRAM_END) ||
        (0U != (__get_CONTROL() & CONTROL_SPSEL_Msk)) || (__get_MSP() <= SRAM_START) || (__get_MSP() > SRAM_END))
    {
        return "MRAM BLOCK code, vectors, source or stack outside CPU0 SRAM\r\n";
    }
    return NULL;
}

static uint8_t pattern_byte(uint32_t offset)
{
    return (uint8_t) (0xA5U ^ (offset & 0xFFU) ^ (0x1DU * (offset >> 8U)));
}

static bool mram_verify(bool written)
{
    const volatile uint8_t * const readback = (const volatile uint8_t *) MRAM_START;
    for (uint32_t i = 0U; i < MRAM_SIZE; ++i)
    {
        const uint8_t actual = readback[i];
        const uint8_t expected = written ? pattern_byte(i) : UINT8_MAX;
        if (actual != expected)
        {
            char line[72];
            (void) snprintf(line, sizeof(line), "MRAM FAIL mismatch +%04" PRIx32 " got=%02x expected=%02x\r\n",
                             i, (unsigned int) actual, (unsigned int) expected);
            bench_emit(line);
            return false;
        }
    }
    if (!read_ecc_clean())
    {
        bench_emit("MRAM FAIL readback ECC\r\n");
        return false;
    }
    return true;
}

static bool mram_program(bool write)
{
    const char * const refusal = preflight();
    if (NULL != refusal)
    {
        bench_emit(refusal);
        return false;
    }

    fsp_err_t err = R_MRAM_Open(g_bench_mram.p_ctrl, g_bench_mram.p_cfg);
    if (FSP_SUCCESS != err)
    {
        bench_emit("MRAM FAIL open\r\n");
        return false;
    }

    /* No UART call from here until the driver has drained the code sequencer and restored protection. */
    const uint32_t saved_irq = __get_PRIMASK();
    __disable_irq();
    const uint32_t saved_vtor = SCB->VTOR;
    for (size_t i = 0U; i < BSP_VECTOR_TABLE_MAX_ENTRIES; ++i)
    {
        vectors[i] = (uintptr_t) mram_exception;
    }
    SCB->VTOR = (uint32_t) (uintptr_t) vectors;
    __DSB();
    __ISB();
    if (SCB->VTOR == (uint32_t) (uintptr_t) vectors)
    {
        stage = MRAM_DIRTY;
        err = write ? R_MRAM_Write(g_bench_mram.p_ctrl, (uint32_t) (uintptr_t) pattern, MRAM_START, MRAM_SIZE) :
                      R_MRAM_Erase(g_bench_mram.p_ctrl, MRAM_START, 1U);
    }
    else
    {
        err = FSP_ERR_INVALID_LINKED_ADDRESS;
    }
    SCB->VTOR = saved_vtor;
    __DSB();
    __ISB();
    __set_PRIMASK(saved_irq);

    const fsp_err_t close_err = R_MRAM_Close(g_bench_mram.p_ctrl);
    if ((FSP_SUCCESS != err) || (FSP_SUCCESS != close_err))
    {
        char line[72];
        (void) snprintf(line, sizeof(line), "MRAM FAIL %s err=%d close=%d\r\n", write ? "write" : "erase",
                         (int) err, (int) close_err);
        bench_emit(line);
        return false;
    }
    if (!code_idle() || (0U != (R_MRAM->MRCPC0 | R_MRAM->MRCPC1 | R_MRAM->MRCBPROT0 | R_MRAM->MRCBPROT1)) ||
        (0U != (SCB->CCR & SCB_CCR_DC_Msk)) || (0U != R_MRAM->MRCPFB))
    {
        bench_emit("MRAM FAIL unexpected post-program state; no readback\r\n");
        return false;
    }

    return mram_verify(write);
}

bool bench_mram(const char * command)
{
    if (NULL == command)
    {
        return false;
    }
    const bool arm = (0 == strcmp(command, "mram-arm"));
    const bool resume = (0 == strcmp(command, "mram-resume"));
    const bool write = (0 == strcmp(command, "mram-write"));
    const bool clean = (0 == strcmp(command, "mram-clean"));
    if (!(arm || resume || write || clean))
    {
        return false;
    }
    if ((MRAM_IDLE == stage) && (arm || resume))
    {
        const char * const refusal = preflight();
        if (NULL != refusal)
        {
            bench_emit(refusal);
            return false;
        }
        if (resume)
        {
            if (!mram_verify(true))
            {
                return false;
            }
            stage = MRAM_DIRTY;
            bench_emit("MRAM RESUMED verified pattern; cleanup only; no writes\r\n");
        }
        else
        {
            stage = MRAM_ARMED;
            bench_emit("MRAM ARMED 0207f800..02080000; no writes\r\n");
        }
        return true;
    }
    if ((MRAM_ARMED == stage) && write)
    {
        for (uint32_t i = 0U; i < MRAM_SIZE; ++i)
        {
            pattern[i] = pattern_byte(i);
        }
        if (!mram_program(false))
        {
            return false;
        }
        bench_emit("MRAM ERASE verified 2048 bytes of ff\r\n");
        if (!mram_program(true))
        {
            return false;
        }
        bench_emit("MRAM WRITE verified 2048 bytes; awaiting host readback\r\n");
        return true;
    }
    if ((MRAM_DIRTY == stage) && clean)
    {
        if (!mram_program(false))
        {
            return false;
        }
        stage = MRAM_DONE;
        bench_emit("MRAM CLEAN verified 2048 bytes of ff\r\n");
        return true;
    }
    bench_emit("MRAM BLOCK unexpected command order\r\n");
    return false;
}
