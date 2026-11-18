/* Production C executed on anonymous host memory, never a target. */
#include "r_mram.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
/* Include unchanged production C to exercise the private mapping path on host memory. */
#include "r_mram.c"

#define DEST 0x0200E000U
#define SOURCE 0x20008000U
#define COMMAND (*(volatile uint8_t *)(uintptr_t)0x40120000U)
#define HW(type, member) (*(volatile type *)((uintptr_t)R_MRAM + offsetof(R_MRAM_Type, member)))
struct fixture_scb fixture_scb;
static uint32_t mask;
static unsigned pages, program_ticks, extra_ticks, stop_commands, status_clears;
#if BSP_CFG_CPU_CORE == 1
static unsigned flush_ticks;
#endif
static unsigned cache_disable, cache_enable, cache_invalidate;
static bool programming, extra_running, seen_store, saw_drain;
static int fault;

uint32_t __get_PRIMASK(void) { return mask; }
void __disable_irq(void) { mask = 1U; }
void __set_PRIMASK(uint32_t value) { mask = value; }
void SCB_DisableDCache(void) { cache_disable++; fixture_scb.CCR = 0U; }
void SCB_EnableDCache(void) { cache_enable++; fixture_scb.CCR = SCB_CCR_DC_Msk; }
void SCB_InvalidateICache(void) { cache_invalidate++; }

void fixture_barrier(int kind)
{
#if BSP_CFG_CPU_CORE == 1
    if (kind == 1 && ((R_CACHE->CCACTL | R_CACHE->SCACTL) & 0x300U))
    {
        assert((R_MRAM->MRCPC1 & 1U) == 0U);
        if (R_CACHE->CCACTL & 0x300U) { R_CACHE->CCAFCT = 3U; R_CACHE->CCACTL = (fault == 6) ? 1U : 0U; }
        if (R_CACHE->SCACTL & 0x300U) { R_CACHE->SCAFCT = 3U; R_CACHE->SCACTL = (fault == 6) ? 1U : 0U; }
        flush_ticks = 0U;
    }
    if (kind == 3 && (R_CACHE->CCAFCT | R_CACHE->SCAFCT))
    {
        assert((R_MRAM->MRCPC1 & 1U) == 0U);
        if (++flush_ticks == 3U) { R_CACHE->CCAFCT = 0U; R_CACHE->SCAFCT = 0U; }
    }
#endif
    if ((kind == 0 || kind == 1) && (R_MRAM->MRCPC1 & 1U))
    {
        assert(mask == 1U && R_MRAM->MRCPFB == 0U);
#if BSP_CFG_CPU_CORE == 1
        assert((R_CACHE->CCACTL | R_CACHE->SCACTL | R_CACHE->CCAFCT | R_CACHE->SCAFCT) == 0U);
#else
        assert(fixture_scb.CCR == 0U);
#endif
        if (!programming && !seen_store)
        {
            programming = true;
            seen_store = true;
            pages++;
            program_ticks = 0U;
            R_MRAM->MRCPS = 0U;
        }
        if (kind == 1) { saw_drain = true; }
    }
    if (kind == 3 && programming)
    {
        assert((R_MRAM->MRCPC1 & 1U) != 0U);
        if (++program_ticks == 2U) { R_MRAM->MRCPS = 0x20U; programming = false; }
    }
    if (kind == 1 && R_MRAM->MRCFLR == 0xC301U && !programming)
    {
        R_MRAM->MRCFLR = 0U;
        seen_store = false;
    }
    if (kind == 1 && R_MRAM->MENTRYR == 0xAA80U)
    {
        R_MRAM->MENTRYR = 0x80U;
    }
    if (kind == 1 && R_MRAM->MENTRYR == 0x80U)
    {
        if (COMMAND == 0xD0U && !extra_running)
        {
            extra_running = true;
            extra_ticks = 0U;
            HW(uint32_t, MSTATR) = 0U;
            if (fault == 2) { R_MRAM->MASTAT = 0x10U; HW(uint32_t, MSTATR) = 0x8000U; }
        }
        if (COMMAND == 0xB3U)
        {
            stop_commands++;
            if (fault != 3) { HW(uint32_t, MSTATR) = 0x8000U; R_MRAM->MASTAT = 0U; }
        }
        if (COMMAND == 0x50U)
        {
            status_clears++;
            if (fault != 5) { R_MRAM->MASTAT = 0U; HW(uint32_t, MSTATR) = 0x8000U; }
        }
    }
    if (kind == 3 && extra_running && fault == 0)
    {
        if (++extra_ticks == 2U) { HW(uint32_t, MSTATR) = 0x8000U; }
    }
    if (kind == 1 && R_MRAM->MENTRYR == 0xAA00U)
    {
        R_MRAM->MENTRYR = (fault == 4) ? 0x80U : 0U;
        if (fault != 4) { extra_running = false; COMMAND = 0U; }
    }
}

#if !BSP_TZ_NONSECURE_BUILD
static void map_at(uintptr_t address, size_t size)
{
    assert(mmap((void *)address, size, PROT_READ | PROT_WRITE,
                MAP_PRIVATE | MAP_ANON | MAP_FIXED, -1, 0) == (void *)address);
}

static void initialize(void)
{
    map_at(0x02000000U, 0x100000U);
    map_at(0x12000000U, 0x100000U);
    map_at(SOURCE & ~0xFFFU, 0x1000U);
    map_at(0x00008000U, 0x1000U);
    /* Do not map over the executable when testing helpers in NS TCM. */
#ifndef TEST_TCM_HELPER
    map_at(0x10008000U, 0x1000U);
#endif
    map_at((uintptr_t)R_MRAM, 0x4000U);
    map_at((uintptr_t)R_CACHE, 0x1000U);
    map_at(0x40120000U, 0x1000U);
    map_at(0x02C9F000U, 0x1000U);
    map_at(0x02E17000U, 0x1000U);
    R_MRAM->MRCPS = 0x20U;
    R_MRAM->MRCPFB = 1U;
    HW(uint32_t, MSTATR) = 0x8000U;
    HW(uint32_t, MSUASMON) = 0x80008000U;
    HW(uint8_t, MREZS) = 1U;
    fixture_scb.CCR = SCB_CCR_DC_Msk;
    memset((void *)(uintptr_t)SOURCE, 0x3CU, 32U);
}

#endif

int main(int argc, char **argv)
{
    assert(argc == 2);
    mram_instance_ctrl_t ctrl = {0};
    mram_extended_cfg_t ext = {DEST, DEST + 0x2000U, 8U, true};
#if BSP_TZ_NONSECURE_BUILD
    ext.write_window_start += 0x10000000U;
    ext.write_window_end += 0x10000000U;
#endif
    flash_cfg_t cfg = {.p_extend = &ext};
#if BSP_TZ_NONSECURE_BUILD
    /* No register, source or destination mappings: any hardware access faults. */
    assert(strcmp(argv[1], "nonsecure") == 0);
    assert(R_MRAM_Open(&ctrl, &cfg) == FSP_SUCCESS);
    flash_status_t status = FLASH_STATUS_IDLE;
    assert(R_MRAM_StatusGet(&ctrl, &status) == FSP_ERR_UNSUPPORTED);
    assert(status == FLASH_STATUS_BUSY);
    assert(R_MRAM_Write(&ctrl, SOURCE, ext.write_window_start, 1U) == FSP_ERR_UNSUPPORTED);
    assert(R_MRAM_Erase(&ctrl, ext.write_window_start + 1U, 1U) == FSP_ERR_UNSUPPORTED);
    flash_result_t blank = FLASH_RESULT_BLANK;
    assert(R_MRAM_BlankCheck(&ctrl, ext.write_window_start, 1U, &blank) == FSP_ERR_UNSUPPORTED);
    assert(blank == FLASH_RESULT_BLANK);
    assert(R_MRAM_Reset(&ctrl) == FSP_ERR_UNSUPPORTED);
    uint32_t count = 123U;
    assert(R_MRAM_AntiRollbackCounterRead(&ctrl, FLASH_ARC_SEC, &count) == FSP_ERR_UNSUPPORTED);
    assert(R_MRAM_AntiRollbackCounterIncrement(&ctrl, FLASH_ARC_SEC) == FSP_ERR_UNSUPPORTED);
    assert(R_MRAM_StartUpAreaSelect(&ctrl, FLASH_STARTUP_AREA_BLOCK0, true) == FSP_ERR_UNSUPPORTED);
    assert(R_MRAM_Close(&ctrl) == FSP_SUCCESS);
#else
    bool rejected = strcmp(argv[1], "irreversible-rejected") == 0;
    if (!rejected) { initialize(); }
    assert(R_MRAM_Open(&ctrl, &cfg) == FSP_SUCCESS);
    if (rejected)
    {
        /* No MMIO mappings: refusal must precede even admission-register reads. */
        for (uint32_t budget = 1U; budget <= 2U; budget++)
        {
            ctrl.timeout = budget;
            assert(R_MRAM_AntiRollbackCounterIncrement(&ctrl, FLASH_ARC_SEC) == FSP_ERR_UNSUPPORTED);
            assert(R_MRAM_AntiRollbackCounterIncrement(&ctrl, FLASH_ARC_OEMBL) == FSP_ERR_UNSUPPORTED);
            assert(R_MRAM_StartUpAreaSelect(&ctrl, FLASH_STARTUP_AREA_BLOCK0, false) == FSP_ERR_UNSUPPORTED);
            assert(R_MRAM_StartUpAreaSelect(&ctrl, FLASH_STARTUP_AREA_BLOCK1, false) == FSP_ERR_UNSUPPORTED);
            assert(!ctrl.busy && !ctrl.extra_recovery_required);
        }
        ext.enable_extra_commands = false;
        assert(R_MRAM_AntiRollbackCounterIncrement(&ctrl, FLASH_ARC_SEC) == FSP_ERR_NOT_ENABLED);
        assert(R_MRAM_StartUpAreaSelect(&ctrl, FLASH_STARTUP_AREA_BLOCK0, false) == FSP_ERR_NOT_ENABLED);
    }
    else if (strcmp(argv[1], "erase") == 0)
    {
        memset((void *)(uintptr_t)DEST, 0x55, 0x2000U);
        assert(R_MRAM_Erase(&ctrl, DEST + 2047U, 1U) == FSP_SUCCESS);
        assert(*(uint8_t *)(uintptr_t)DEST == 0xFFU);
        assert(*(uint8_t *)(uintptr_t)(DEST + 2047U) == 0xFFU);
        assert(*(uint8_t *)(uintptr_t)(DEST + 2048U) == 0x55U);
        assert(R_MRAM_Erase(&ctrl, DEST - 1U, 1U) == FSP_ERR_INVALID_ADDRESS);
        assert(R_MRAM_Erase(&ctrl, ext.write_window_end - 1U, 2U) == FSP_ERR_INVALID_ADDRESS);
        assert(R_MRAM_Erase(&ctrl, 0x020FFFFFU, 2U) == FSP_ERR_INVALID_ADDRESS);
        ctrl.window_start++;
        assert(R_MRAM_Erase(&ctrl, DEST + 1U, 1U) == FSP_ERR_INVALID_ADDRESS);
        ctrl.window_start--;
        ctrl.window_end--;
        assert(R_MRAM_Erase(&ctrl, ext.write_window_end - 1U, 1U) == FSP_ERR_INVALID_ADDRESS);
    }
    else if (strcmp(argv[1], "tcm") == 0)
    {
        memset((void *)(uintptr_t)0x8000U, 0x69, 32U);
        ctrl.window_start = 0x8000U;
        assert(R_MRAM_Write(&ctrl, 0x8000U, 0x02008000U, 32U) == FSP_SUCCESS);
        assert(memcmp((void *)(uintptr_t)0x8000U, (void *)(uintptr_t)0x02008000U, 32U) == 0);
#ifndef TEST_TCM_HELPER
        memset((void *)(uintptr_t)0x10008000U, 0x96, 32U);
        assert(R_MRAM_Write(&ctrl, 0x10008000U, 0x02008000U, 32U) == FSP_SUCCESS);
        assert(memcmp((void *)(uintptr_t)0x10008000U, (void *)(uintptr_t)0x02008000U, 32U) == 0);
#endif
        assert(R_MRAM_Write(&ctrl, 0x12008000U, 0x02008000U, 32U) == FSP_ERR_INVALID_ADDRESS);
    }
    else if (strcmp(argv[1], "cache") == 0)
    {
        for (unsigned enabled = 0U; enabled < 4U; enabled++)
        for (unsigned wt = 0U; wt < 4U; wt++)
        {
            uint32_t c_enable = enabled & 1U;
            uint32_t s_enable = (enabled >> 1U) & 1U;
            R_CACHE->CCACTL = c_enable;
            R_CACHE->SCACTL = s_enable;
            R_CACHE->CCAWTA = wt & 1U;
            R_CACHE->SCAWTA = (wt >> 1U) & 1U;
            assert(R_MRAM_Write(&ctrl, SOURCE, DEST, 1U) == FSP_SUCCESS);
#if BSP_CFG_CPU_CORE == 1
            assert(R_CACHE->CCACTL == c_enable && R_CACHE->SCACTL == s_enable);
            assert(flush_ticks == 3U);
            assert(cache_disable == 0U && cache_enable == 0U && cache_invalidate == 0U);
#else
            assert(cache_disable == enabled * 4U + wt + 1U && cache_invalidate == cache_disable);
            assert(R_CACHE->CCACTL == c_enable && R_CACHE->SCACTL == s_enable);
#endif
            assert(saw_drain && mask == 0U && R_MRAM->MRCPFB == 1U && !ctrl.busy);
            assert(R_MRAM->MRCPC1 == 0x6800U && R_MRAM->MRCPS == 0x20U);
        }
    }
    else if (strcmp(argv[1], "cache-refusal") == 0)
    {
        fault = 6;
        R_CACHE->CCACTL = 1U;
        R_CACHE->SCACTL = 1U;
        *(uint8_t *)(uintptr_t)DEST = 0x55U;
        assert(R_MRAM_Write(&ctrl, SOURCE, DEST, 1U) == FSP_ERR_WRITE_FAILED);
        assert(*(uint8_t *)(uintptr_t)DEST == 0x55U && pages == 0U);
        assert(R_MRAM->MRCPC1 == 0U && R_MRAM->MRCFLR == 0U);
        assert(!ctrl.busy && mask == 0U && R_MRAM->MRCPFB == 1U);
        assert(R_CACHE->CCACTL == 1U && R_CACHE->SCACTL == 1U);
    }
    else if (strcmp(argv[1], "startup") == 0)
    {
        uint16_t data[8] = {0};
        for (uint32_t bt = 0U; bt < 2U; bt++)
        for (uint32_t sas = 0U; sas < 4U; sas++)
        {
            HW(uint32_t, MSUASMON) = (bt << 31U) | 0x8000U;
            R_MRAM->MSUACR = (uint16_t)sas;
            uint16_t expected = (uint16_t)((sas & 2U) ? sas : (bt ? 2U : 3U));
            assert(R_MRAM_StartUpAreaSelect(&ctrl, FLASH_STARTUP_AREA_BLOCK1, false) == FSP_ERR_UNSUPPORTED);
            assert(R_MRAM->MSUACR == sas);
            /* Bypass only public admission, on fake memory, to verify SAS preservation. */
            assert(r_mram_extra(&ctrl, 0x40U, 0U, data, NULL, NULL) == FSP_SUCCESS);
            assert((R_MRAM->MSUACR & 3U) == expected);
            assert(R_MRAM->MENTRYR == 0U && !ctrl.busy);
        }
        assert(R_MRAM_StartUpAreaSelect(&ctrl, FLASH_STARTUP_AREA_BLOCK0, true) == FSP_SUCCESS);
        assert((R_MRAM->MSUACR & 3U) == FLASH_STARTUP_AREA_BLOCK0);
        assert(R_MRAM_StartUpAreaSelect(&ctrl, FLASH_STARTUP_AREA_BLOCK1, true) == FSP_SUCCESS);
        assert((R_MRAM->MSUACR & 3U) == FLASH_STARTUP_AREA_BLOCK1);
        assert(R_MRAM_StartUpAreaSelect(&ctrl, FLASH_STARTUP_AREA_BTFLG, true) == FSP_SUCCESS);
        assert((R_MRAM->MSUACR & 3U) == FLASH_STARTUP_AREA_BTFLG);
    }
    else if (strcmp(argv[1], "recovery") == 0)
    {
        fault = 3;
        ctrl.timeout = 1U;
        uint32_t count = 123U;
        assert(R_MRAM_AntiRollbackCounterRead(&ctrl, FLASH_ARC_SEC, &count) == FSP_ERR_TIMEOUT);
        assert(count == 123U && ctrl.busy);
        assert(R_MRAM->MENTRYR == 0x80U && stop_commands == 0U && mask == 0U);
        flash_status_t status;
        assert(R_MRAM_StatusGet(&ctrl, &status) == FSP_SUCCESS && status == FLASH_STATUS_BUSY);
        assert(R_MRAM_Close(&ctrl) == FSP_ERR_IN_USE && ctrl.open != 0U);
        assert(R_MRAM_Reset(&ctrl) == FSP_ERR_IN_USE && ctrl.busy);
        assert(R_MRAM_Write(&ctrl, SOURCE, DEST, 1U) == FSP_ERR_IN_USE);
        HW(uint32_t, MSTATR) = 0x8000U;
        R_MRAM->MASTAT = 0x10U;
        fault = 5;
        assert(R_MRAM_Reset(&ctrl) == FSP_ERR_WRITE_FAILED);
        assert(ctrl.busy && R_MRAM->MENTRYR == 0x80U);
        fault = 4;
        assert(R_MRAM_Reset(&ctrl) == FSP_ERR_WRITE_FAILED);
        assert(ctrl.busy && R_MRAM->MENTRYR == 0x80U);
        fault = 0;
        assert(R_MRAM_Reset(&ctrl) == FSP_SUCCESS);
        assert(R_MRAM->MENTRYR == 0U && !ctrl.busy);
        assert(status_clears >= 2U && stop_commands == 0U);
        assert(R_MRAM_StatusGet(&ctrl, &status) == FSP_SUCCESS && status == FLASH_STATUS_IDLE);
    }
    else { assert(0); }
#endif
    assert(pages < 100000U && cache_enable <= cache_disable && cache_invalidate <= cache_disable);
    assert(stop_commands == 0U && status_clears < 100U);
    (void)saw_drain;
#if BSP_CFG_CPU_CORE == 1
    (void)flush_ticks;
#endif
    puts("review MRAM fixture passed");
    return 0;
}
