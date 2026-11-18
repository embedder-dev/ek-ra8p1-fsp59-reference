/* Executes production drivers against host RAM, never a probe or target. */
#include "bsp_api.h"
#include "r_mram.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#ifdef TEST_DAC_B
 #include "r_dac_b.h"
#endif

fixture_mram_t fixture_mram;
R_DAC_B0_Type fixture_dac[2];
struct fixture_scb fixture_scb;
static uint32_t irq_mask;
static unsigned int cache_disabled;
static unsigned int cache_enabled;
static unsigned int cache_invalidated;
static unsigned int pages;
static int fault;
static unsigned int busy_ticks;
static bool extra_active;
static bool programming_active;
static unsigned int extra_commands;
static unsigned int modules[2];
static unsigned int stopped[2];
static uint32_t delays[32];
static uint32_t delay_control[32][2];
static uint16_t delay_data[32][2];
static unsigned int delay_count;
static unsigned int flash_callbacks;
static void flash_callback(flash_callback_args_t * p_args) { (void) p_args; flash_callbacks++; }
static void flash_callback_replacement(flash_callback_args_t * p_args) { (void) p_args; flash_callbacks++; }
#if BSP_TZ_SECURE_BUILD
static bool nonsecure_callback;
static bool nonsecure_memory;
void * fixture_cmse_range(void * p, size_t size, unsigned flags)
{
    (void) size;
    if ((p == (void *) flash_callback) || (p == (void *) flash_callback_replacement))
    {
        return nonsecure_callback ? p : NULL;
    }
    assert(flags == (CMSE_AU_NONSECURE | CMSE_MPU_READWRITE));
    return nonsecure_memory ? p : NULL;
}
#endif

static void test_mram_callbacks(void)
{
    mram_instance_ctrl_t ctrl = {0};
    mram_extended_cfg_t ext = {.timeout = 8U};
    flash_callback_args_t memory = {0};
    flash_cfg_t cfg = {.p_extend = &ext, .p_callback = flash_callback, .p_context = &ext};
    flash_instance_t instance = {.p_ctrl = &ctrl, .p_cfg = &cfg, .p_api = &g_flash_on_mram};
#if MRAM_CFG_PARAM_CHECKING_ENABLE
    assert(instance.p_api->callbackSet(NULL, flash_callback, NULL, NULL) == FSP_ERR_ASSERTION);
    assert(instance.p_api->callbackSet(instance.p_ctrl, flash_callback, NULL, NULL) == FSP_ERR_NOT_OPEN);
#endif
    assert(instance.p_api->open(instance.p_ctrl, instance.p_cfg) == FSP_SUCCESS);
    assert(ctrl.p_callback == flash_callback && ctrl.p_context == &ext && ctrl.p_callback_memory == NULL);
#if MRAM_CFG_PARAM_CHECKING_ENABLE
    assert(instance.p_api->callbackSet(instance.p_ctrl, NULL, NULL, NULL) == FSP_ERR_ASSERTION);
#endif
    assert(instance.p_api->callbackSet(instance.p_ctrl, flash_callback_replacement, &cfg, &memory) == FSP_SUCCESS);
    assert(ctrl.p_callback == flash_callback_replacement && ctrl.p_context == &cfg && ctrl.p_callback_memory == &memory);
#if BSP_TZ_SECURE_BUILD
    nonsecure_callback = true;
    assert(instance.p_api->callbackSet(instance.p_ctrl, flash_callback, &ctrl, NULL) == FSP_ERR_NO_CALLBACK_MEMORY);
    assert(instance.p_api->callbackSet(instance.p_ctrl, flash_callback, &ctrl, &memory) == FSP_ERR_NO_CALLBACK_MEMORY);
    assert(ctrl.p_callback == flash_callback_replacement && ctrl.p_context == &cfg && ctrl.p_callback_memory == &memory);
    nonsecure_memory = true;
    assert(instance.p_api->callbackSet(instance.p_ctrl, flash_callback, &ctrl, &memory) == FSP_SUCCESS);
    assert(ctrl.p_callback == flash_callback && ctrl.p_context == &ctrl && ctrl.p_callback_memory == &memory);
    nonsecure_callback = false;
    nonsecure_memory = false;
#endif
    assert(instance.p_api->close(instance.p_ctrl) == FSP_SUCCESS);
    cfg.p_callback = NULL;
    cfg.p_context = NULL;
    assert(instance.p_api->open(instance.p_ctrl, instance.p_cfg) == FSP_SUCCESS);
    assert(ctrl.p_callback == NULL && ctrl.p_context == NULL && ctrl.p_callback_memory == NULL);
    assert(instance.p_api->close(instance.p_ctrl) == FSP_SUCCESS);
    assert(flash_callbacks == 0U);
}

/* Model hardware-owned RO status without weakening the production header's qualifiers. */
#define FIXTURE_HW(type, member) \
    (*(volatile type *) ((uint8_t *) &fixture_mram + offsetof(fixture_mram_t, member)))

_Static_assert(offsetof(fixture_mram_t, MSADDR) == 0x2030, "MSADDR: HM60.5.19 p3574");
_Static_assert(offsetof(fixture_mram_t, MRCPC0) == 0x3000, "MRCPC0");
_Static_assert(offsetof(fixture_mram_t, MRCPC1) == 0x3004, "MRCPC1");
_Static_assert(offsetof(fixture_mram_t, MRCPS) == 0x3010, "MRCPS");
_Static_assert(offsetof(fixture_mram_t, MRCFLR) == 0x3030, "MRCFLR");
_Static_assert(offsetof(fixture_mram_t, MCTRCNTR) == 0x2060, "MCTRCNTR");
_Static_assert(offsetof(fixture_mram_t, MENTRYR) == 0x2084, "MENTRYR");
_Static_assert(offsetof(fixture_mram_t, MSUASMON) == 0x20dc, "MSUASMON");
_Static_assert(offsetof(fixture_mram_t, MSUACR) == 0x20e8, "MSUACR");

uint32_t __get_PRIMASK(void) { return irq_mask; }
void __set_PRIMASK(uint32_t mask) { irq_mask = mask; }
void __disable_irq(void) { irq_mask = 1U; }
void SCB_DisableDCache(void) { cache_disabled++; SCB->CCR &= ~SCB_CCR_DC_Msk; }
void SCB_EnableDCache(void) { cache_enabled++; SCB->CCR |= SCB_CCR_DC_Msk; }
void SCB_InvalidateICache(void) { cache_invalidated++; }
void fixture_module_start(uint8_t unit) { assert(unit < 2); modules[unit]++; }
void fixture_module_stop(uint8_t unit) { assert(unit < 2); stopped[unit]++; }
void R_BSP_SoftwareDelay(uint32_t duration, int units)
{
    assert(units == BSP_DELAY_UNITS_MICROSECONDS);
    assert(delay_count < 32);
    for (unsigned int unit = 0; unit < 2U; unit++)
    {
        delay_control[delay_count][unit] = fixture_dac[unit].DACR0;
        delay_data[delay_count][unit] = fixture_dac[unit].DADR;
    }
    delays[delay_count++] = duration;
}

void fixture_barrier(int barrier)
{
    if (barrier == 0)
    {
        assert(irq_mask == 1);
        assert((SCB->CCR & SCB_CCR_DC_Msk) == 0);
        assert(R_MRAM->MRCPFB == 0);
        pages++;
        programming_active = true;
        R_MRAM->MRCPS = 0U;
        busy_ticks = 0U;
    }
    if (barrier == 2) { programming_active = false; }
    if (barrier == 3 && programming_active)
    {
        assert(R_MRAM->MRCFLR == 0xC301);
        assert(irq_mask == 1 && cache_disabled > 0 && R_MRAM->MRCPFB == 0);
        assert((SCB->CCR & SCB_CCR_DC_Msk) == 0);
        busy_ticks++;
        if (fault == 8)
        {
            FIXTURE_HW(uint8_t, MREZS) = (busy_ticks < 3U) ? 2U : 0U;
        }
        if (fault == 9) { FIXTURE_HW(uint8_t, MREZS) = 0U; }
        if (fault != 2 || busy_ticks > 12U)
        {
            R_MRAM->MRCPS = (uint8_t) (0x20U | (fault == 1 ? 1U : (fault == 3 ? 2U : 0U)));
        }
    }
    if (barrier == 1 && R_MRAM->MENTRYR == 0xAA80)
    {
        R_MRAM->MENTRYR = 0x80;
        extra_active = true;
    }
    if (barrier == 1 && extra_active)
    {
        volatile uint8_t * command = (volatile uint8_t *)(uintptr_t)0x40120000;
        if (*command == 0xD0)
        {
            extra_commands++;
            if (fault == 10 || fault == 11)
            {
                FIXTURE_HW(uint8_t, MREZS) = (fault == 10) ? 2U : 0U;
                FIXTURE_HW(uint32_t, MCNTDTR0) = 0U;
                FIXTURE_HW(uint32_t, MCNTDTR1) = 0U;
            }
            if (fault == 4)
            {
                FIXTURE_HW(uint32_t, MSTATR) = 0U;
            }
            else if (fault == 5)
            {
                R_MRAM->MASTAT = 0x10;
            }
        }
        if (*command == 0x50 || *command == 0xB3)
        {
            R_MRAM->MASTAT = 0U;
            FIXTURE_HW(uint32_t, MSTATR) = 0x8000;
        }
    }
    if (barrier == 1 && R_MRAM->MENTRYR == 0xAA00)
    {
        R_MRAM->MENTRYR = 0U;
        extra_active = false;
    }
    if (barrier == 1 && R_MRAM->MCTRCNTR == 0x4501)
    {
        FIXTURE_HW(uint8_t, MCTRSTATR) = (fault == 6) ? 1U : 0U;
        if (fault == 7) { FIXTURE_HW(uint8_t, MREZS) = 2U; }
        R_MRAM->MCTRCNTR = 0U;
    }
}

static void * map_at(uintptr_t address, size_t size)
{
    void * result = mmap((void *) address, size, PROT_READ | PROT_WRITE,
                         MAP_PRIVATE | MAP_ANON | MAP_FIXED, -1, 0);
    if (result == MAP_FAILED)
    {
        perror("host fixture mmap");
        return NULL;
    }
    assert(result == (void *) address);
    return result;
}

static void reset_regs(void)
{
    memset(&fixture_mram, 0, sizeof(fixture_mram));
    memset(fixture_dac, 0, sizeof(fixture_dac));
    R_MRAM->MRCPS = 0x20;
    FIXTURE_HW(uint32_t, MSTATR) = 0x8000;
    R_MRAM->MRCPFB = 1;
    FIXTURE_HW(uint32_t, MSUASMON) = 0x80008000;
    SCB->CCR = SCB_CCR_DC_Msk | SCB_CCR_IC_Msk;
    irq_mask = 0;
    fault = 0;
    extra_active = false;
    delay_count = 0;
}

static void test_mram_zeroization(char const * scenario)
{
    reset_regs();
    mram_instance_ctrl_t ctrl = {0};
    mram_extended_cfg_t ext = {0x02080000U, 0x02082000U, 8U, true};
#if BSP_TZ_NONSECURE_BUILD
    ext.write_window_start += 0x10000000U;
    ext.write_window_end += 0x10000000U;
#endif
    flash_cfg_t cfg = {.p_extend = &ext};
    uint8_t * destination = (uint8_t *)(uintptr_t)ext.write_window_start;
    memset(destination, 0xA5, 96U);
    memset((void *)(uintptr_t)0x20000000U, 0x3C, 96U);
    assert(R_MRAM_Open(&ctrl, &cfg) == FSP_SUCCESS);
    flash_status_t status;
#if BSP_TZ_NONSECURE_BUILD
    FSP_PARAMETER_NOT_USED(scenario);
    assert(R_MRAM_StatusGet(&ctrl, &status) == FSP_ERR_UNSUPPORTED && status == FLASH_STATUS_BUSY);
    assert(R_MRAM_Write(&ctrl, 0x20000000U, ext.write_window_start, 70U) == FSP_ERR_UNSUPPORTED);
    assert(R_MRAM_Erase(&ctrl, ext.write_window_start, 1U) == FSP_ERR_UNSUPPORTED);
    assert(pages == 0U && destination[0] == 0xA5U && destination[69] == 0xA5U);
    assert(R_MRAM->MRCPC0 == 0U && R_MRAM->MRCPC1 == 0U && R_MRAM->MRCFLR == 0U);
    assert(R_MRAM_Close(&ctrl) == FSP_SUCCESS);
    return;
#endif
    if (strcmp(scenario, "zeroization-status") == 0)
    {
        FIXTURE_HW(uint8_t, MREZS) = 2U;
        assert(R_MRAM->MSTATR == 0x8000U);
        assert(R_MRAM_StatusGet(&ctrl, &status) == FSP_SUCCESS && status == FLASH_STATUS_BUSY);
        assert(R_MRAM_Close(&ctrl) == FSP_ERR_IN_USE && ctrl.open != 0U);
        assert(R_MRAM_Reset(&ctrl) == FSP_ERR_IN_USE);
        flash_result_t result = FLASH_RESULT_BLANK;
        assert(R_MRAM_BlankCheck(&ctrl, ext.write_window_start, 1U, &result) == FSP_ERR_IN_USE);
        assert(result == FLASH_RESULT_BLANK);
    }
    else if (strcmp(scenario, "zeroization-admission") == 0)
    {
        FIXTURE_HW(uint8_t, MREZS) = 2U;
        irq_mask = 1U;
        assert(R_MRAM_Write(&ctrl, 0x20000000U, ext.write_window_start, 70U) == FSP_ERR_IN_USE);
        assert(R_MRAM_Erase(&ctrl, ext.write_window_start, 1U) == FSP_ERR_IN_USE);
        assert(pages == 0U && destination[0] == 0xA5U && destination[69] == 0xA5U);
        assert(R_MRAM->MRCPC0 == 0U && R_MRAM->MRCPC1 == 0U && R_MRAM->MRCFLR == 0U);
        assert(cache_disabled == 0U && cache_enabled == 0U && cache_invalidated == 0U);
        assert(R_MRAM->MRCPFB == 1U && R_MRAM->MRCPS == 0x20U && irq_mask == 1U && !ctrl.busy);
#if !BSP_TZ_NONSECURE_BUILD
        uint32_t count = 123U;
        assert(R_MRAM_AntiRollbackCounterRead(&ctrl, FLASH_ARC_SEC, &count) == FSP_ERR_IN_USE);
        assert(count == 123U);
        assert(R_MRAM_AntiRollbackCounterIncrement(&ctrl, FLASH_ARC_SEC) == FSP_ERR_UNSUPPORTED);
        assert(R_MRAM_StartUpAreaSelect(&ctrl, FLASH_STARTUP_AREA_BLOCK1, true) == FSP_ERR_IN_USE);
        assert(extra_commands == 0U && R_MRAM->MENTRYR == 0U && R_MRAM->MSUACR == 0U);
#endif
    }
#if !BSP_TZ_NONSECURE_BUILD
    else if (strncmp(scenario, "zeroization-extra", 17U) == 0)
    {
        FIXTURE_HW(uint8_t, MREZS) = 1U;
        fault = (strcmp(scenario, "zeroization-extra-active") == 0) ? 10 : 11;
        uint32_t count = 123U;
        assert(R_MRAM_AntiRollbackCounterRead(&ctrl, FLASH_ARC_SEC, &count) == FSP_ERR_WRITE_FAILED);
        assert(count == 123U && ctrl.busy == (fault == 10) && irq_mask == 0U);
        assert(R_MRAM_StatusGet(&ctrl, &status) == FSP_SUCCESS);
        assert(status == ((fault == 10) ? FLASH_STATUS_BUSY : FLASH_STATUS_IDLE));
        assert(R_MRAM->MENTRYR == ((fault == 10) ? 0x80U : 0U));
        if (fault == 10) { assert(*(volatile uint8_t *)(uintptr_t)0x40120000U == 0xD0U); }
    }
#endif
    else
    {
        FIXTURE_HW(uint8_t, MREZS) = 1U;
        fault = (strcmp(scenario, "zeroization-interrupted") == 0) ? 8 : 9;
        assert(R_MRAM_Write(&ctrl, 0x20000000U, ext.write_window_start, 70U) == FSP_ERR_WRITE_FAILED);
        assert(pages == 1U && destination[32] == 0xA5U && destination[69] == 0xA5U);
        assert(R_MRAM->MREZS == 0U && (fault != 8 || busy_ticks == 3U));
        assert(R_MRAM->MRCPC0 == (BSP_TZ_NONSECURE_BUILD ? 0x8600U : 0U));
        assert(R_MRAM->MRCPC1 == (BSP_TZ_NONSECURE_BUILD ? 0U : 0x6800U));
        assert(!ctrl.busy && irq_mask == 0U && R_MRAM->MRCPFB == 1U);
        assert(cache_disabled == 1U && cache_enabled == 1U && cache_invalidated == 1U);
        assert(R_MRAM_StatusGet(&ctrl, &status) == FSP_SUCCESS && status == FLASH_STATUS_IDLE);
        fault = 0;
        assert(R_MRAM_Write(&ctrl, 0x20000000U, ext.write_window_start + 32U, 1U) == FSP_SUCCESS);
    }
}

static void test_mram(void)
{
    reset_regs();
    mram_instance_ctrl_t ctrl = {0};
    mram_extended_cfg_t ext = {0x02080000, 0x02082000, 8U, true};
#if BSP_TZ_NONSECURE_BUILD
    ext.write_window_start += 0x10000000;
    ext.write_window_end += 0x10000000;
#endif
    flash_cfg_t cfg = {.p_extend = &ext, .p_callback = flash_callback, .p_context = &ext};
    uint32_t dest = ext.write_window_start;
    uint8_t * source = (uint8_t *)(uintptr_t)0x20000000;
    for (unsigned int i = 0; i < 128; i++) { source[i] = (uint8_t)(i * 3U); }
#if MRAM_CFG_PARAM_CHECKING_ENABLE
    assert(R_MRAM_Open(NULL, &cfg) == FSP_ERR_ASSERTION);
    assert(R_MRAM_Open(&ctrl, NULL) == FSP_ERR_ASSERTION);
    flash_cfg_t bad_cfg = {.p_extend = NULL};
    assert(R_MRAM_Open(&ctrl, &bad_cfg) == FSP_ERR_ASSERTION);
    flash_status_t closed_status;
    flash_info_t closed_info;
    flash_result_t closed_blank;
    uint32_t closed_count;
    assert(R_MRAM_Write(&ctrl, 0U, 0U, 0U) == FSP_ERR_NOT_OPEN);
    assert(R_MRAM_Erase(&ctrl, 0U, 0U) == FSP_ERR_NOT_OPEN);
    assert(R_MRAM_BlankCheck(&ctrl, 0U, 0U, &closed_blank) == FSP_ERR_NOT_OPEN);
    assert(R_MRAM_InfoGet(&ctrl, &closed_info) == FSP_ERR_NOT_OPEN);
    assert(R_MRAM_StatusGet(&ctrl, &closed_status) == FSP_ERR_NOT_OPEN);
    assert(R_MRAM_AccessWindowSet(&ctrl, 0U, 0U) == FSP_ERR_NOT_OPEN);
    assert(R_MRAM_AccessWindowClear(&ctrl) == FSP_ERR_NOT_OPEN);
    assert(R_MRAM_IdCodeSet(&ctrl, NULL, FLASH_ID_CODE_MODE_UNLOCKED) == FSP_ERR_NOT_OPEN);
    assert(R_MRAM_Reset(&ctrl) == FSP_ERR_NOT_OPEN);
    assert(R_MRAM_UpdateFlashClockFreq(&ctrl) == FSP_ERR_NOT_OPEN);
    assert(R_MRAM_StartUpAreaSelect(&ctrl, FLASH_STARTUP_AREA_BLOCK0, true) == FSP_ERR_NOT_OPEN);
    assert(R_MRAM_BankSwap(&ctrl) == FSP_ERR_NOT_OPEN);
    assert(R_MRAM_AntiRollbackCounterIncrement(&ctrl, FLASH_ARC_SEC) == FSP_ERR_NOT_OPEN);
    assert(R_MRAM_AntiRollbackCounterRefresh(&ctrl, FLASH_ARC_SEC) == FSP_ERR_NOT_OPEN);
    assert(R_MRAM_AntiRollbackCounterRead(&ctrl, FLASH_ARC_SEC, &closed_count) == FSP_ERR_NOT_OPEN);
    assert(R_MRAM_UserLockableAreaWrite(&ctrl, 0U, 0U, 0U) == FSP_ERR_NOT_OPEN);
    assert(R_MRAM_Close(&ctrl) == FSP_ERR_NOT_OPEN);
#endif
    cfg.data_flash_bgo = true;
    assert(R_MRAM_Open(&ctrl, &cfg) == FSP_ERR_UNSUPPORTED);
    cfg.data_flash_bgo = false;
    ext.timeout = 0;
    assert(R_MRAM_Open(&ctrl, &cfg) == FSP_ERR_INVALID_ARGUMENT);
    ext.timeout = 8;
    assert(R_MRAM_Open(&ctrl, &cfg) == FSP_SUCCESS);
#if MRAM_CFG_PARAM_CHECKING_ENABLE
    assert(R_MRAM_Open(&ctrl, &cfg) == FSP_ERR_ALREADY_OPEN);
#endif
    assert(g_flash_on_mram.write == R_MRAM_Write);
#if BSP_TZ_NONSECURE_BUILD
    flash_status_t ns_status = FLASH_STATUS_IDLE;
    assert(R_MRAM_StatusGet(&ctrl, &ns_status) == FSP_ERR_UNSUPPORTED && ns_status == FLASH_STATUS_BUSY);
    assert(R_MRAM_Write(&ctrl, 0x20000000U, dest, 1U) == FSP_ERR_UNSUPPORTED);
    assert(R_MRAM_Erase(&ctrl, dest + 1U, 1U) == FSP_ERR_UNSUPPORTED);
    assert(R_MRAM_Reset(&ctrl) == FSP_ERR_UNSUPPORTED);
    assert(R_MRAM_Close(&ctrl) == FSP_SUCCESS);
    return;
#endif
    assert(R_MRAM_Write(&ctrl, 0x20000001, dest + 29U, 70U) == FSP_SUCCESS);
    assert(memcmp((void *)(uintptr_t)(dest + 29U), source + 1, 70U) == 0);
    assert(pages == 4);
    assert(R_MRAM->MRCPC0 == (BSP_TZ_NONSECURE_BUILD ? 0x8600 : 0));
    assert(R_MRAM->MRCPC1 == (BSP_TZ_NONSECURE_BUILD ? 0 : 0x6800));
    assert(R_MRAM->MRCPFB == 1);
    assert(irq_mask == 0 && !ctrl.busy);
    assert(cache_disabled == 1 && cache_enabled == 1 && cache_invalidated == 1);
    assert(SCB->CCR == (SCB_CCR_DC_Msk | SCB_CCR_IC_Msk));
    unsigned int before = pages;
    assert(R_MRAM_Write(&ctrl, 0x20000000, dest, 0) == FSP_ERR_INVALID_SIZE);
    assert(R_MRAM_Write(&ctrl, UINT32_MAX - 2U, dest, 4U) == FSP_ERR_INVALID_ADDRESS);
    assert(R_MRAM_Write(&ctrl, 0x20000000, UINT32_MAX, 2U) == FSP_ERR_INVALID_ADDRESS);
    assert(R_MRAM_Write(&ctrl, 0x20000000, dest - 1U, 1U) == FSP_ERR_INVALID_ADDRESS);
    assert(R_MRAM_Write(&ctrl, 0x20000000, ext.write_window_end, 1U) == FSP_ERR_INVALID_ADDRESS);
    assert(R_MRAM_Write(&ctrl, dest, dest + 1U, 8U) == FSP_ERR_INVALID_ADDRESS);
    assert(R_MRAM_Write(&ctrl, 0x120ffffc, dest, 8U) == FSP_ERR_INVALID_ADDRESS);
#if !BSP_TZ_NONSECURE_BUILD
    assert(R_MRAM_Write(&ctrl, dest + 0x10000000, dest, 8U) == FSP_ERR_INVALID_ADDRESS);
#endif
    assert(R_MRAM_Write(&ctrl, 0x20000000, 0x02c9f040, 4U) == FSP_ERR_INVALID_ADDRESS);
    assert(R_MRAM_Write(&ctrl, 0x20000000, 0, 4U) == FSP_ERR_INVALID_ADDRESS);
    assert(pages == before);
    ctrl.busy = true;
    assert(R_MRAM_Write(&ctrl, 0x20000000, dest, 1U) == FSP_ERR_IN_USE);
    ctrl.busy = false;
    R_MRAM->MRCPS = 0x80;
    assert(R_MRAM_Write(&ctrl, 0x20000000, dest, 1U) == FSP_ERR_IN_USE);
    assert(R_MRAM_Reset(&ctrl) == FSP_ERR_IN_USE);
    R_MRAM->MRCPS = 0x20;
    FIXTURE_HW(uint32_t, MSTATR) = 0;
    assert(R_MRAM_Write(&ctrl, 0x20000000, dest, 1U) == FSP_ERR_IN_USE);
    FIXTURE_HW(uint32_t, MSTATR) = 0x8000;
    fault = 1;
    assert(R_MRAM_Write(&ctrl, 0x20000000, dest, 1U) == FSP_ERR_WRITE_FAILED);
    assert((R_MRAM->MRCPS & 3U) == 0 && !ctrl.busy && irq_mask == 0);
    fault = 3;
    assert(R_MRAM_Write(&ctrl, 0x20000000, dest, 1U) == FSP_ERR_WRITE_FAILED);
    assert((R_MRAM->MRCPS & 3U) == 0);
    fault = 2;
    assert(R_MRAM_Write(&ctrl, 0x20000000, dest, 1U) == FSP_ERR_TIMEOUT);
    assert(busy_ticks == 13U && R_MRAM->MRCPS == 0x20U);
    assert(!ctrl.busy && irq_mask == 0 && R_MRAM->MRCPFB == 1);
    fault = 0;
    R_MRAM->MRCPS = 0x20;
    assert(R_MRAM_Erase(&ctrl, dest + 1U, 1U) == FSP_SUCCESS);
    assert(R_MRAM_Erase(&ctrl, dest, UINT32_MAX) == FSP_ERR_INVALID_BLOCKS);
    assert(R_MRAM_Erase(&ctrl, dest, 1U) == FSP_SUCCESS);
    flash_result_t result;
    assert(R_MRAM_BlankCheck(&ctrl, dest, 2048U, &result) == FSP_SUCCESS && result == FLASH_RESULT_BLANK);
    assert(R_MRAM_Write(&ctrl, 0x20000000, dest + 1U, 1U) == FSP_SUCCESS);
    assert(R_MRAM_BlankCheck(&ctrl, dest, 2048U, &result) == FSP_SUCCESS && result == FLASH_RESULT_NOT_BLANK);
    assert(R_MRAM_BlankCheck(&ctrl, dest, UINT32_MAX, &result) == FSP_ERR_INVALID_ADDRESS);
    flash_info_t info;
    assert(R_MRAM_InfoGet(&ctrl, &info) == FSP_SUCCESS);
    assert(info.code_flash.num_regions == 1 && info.code_flash.p_block_array->block_size_write == 1);
    assert(info.data_flash.num_regions == 0 && info.data_flash.p_block_array == NULL);
    assert(R_MRAM_IdCodeSet(&ctrl, NULL, FLASH_ID_CODE_MODE_UNLOCKED) == FSP_ERR_UNSUPPORTED);
    assert(R_MRAM_UpdateFlashClockFreq(&ctrl) == FSP_ERR_UNSUPPORTED);
    assert(R_MRAM_UserLockableAreaWrite(&ctrl, 0U, 0U, 0U) == FSP_ERR_UNSUPPORTED);
    assert(R_MRAM_AccessWindowClear(&ctrl) == FSP_ERR_UNSUPPORTED);
    assert(R_MRAM_AccessWindowSet(&ctrl, dest, dest + 2048) == FSP_ERR_UNSUPPORTED);
    assert(R_MRAM_BankSwap(&ctrl) == FSP_ERR_UNSUPPORTED);
    assert(R_MRAM_AntiRollbackCounterRefresh(&ctrl, FLASH_ARC_SEC) == FSP_ERR_UNSUPPORTED);
    assert(R_MRAM_AntiRollbackCounterRead(&ctrl, (flash_arc_t)99, &before) == FSP_ERR_INVALID_ARGUMENT);
    ext.enable_extra_commands = false;
    assert(R_MRAM_AntiRollbackCounterRead(&ctrl, FLASH_ARC_SEC, &before) == FSP_ERR_NOT_ENABLED);
    ext.enable_extra_commands = true;
#if BSP_TZ_NONSECURE_BUILD
    assert(R_MRAM_AntiRollbackCounterRead(&ctrl, FLASH_ARC_SEC, &before) == FSP_ERR_UNSUPPORTED);
#else
    FIXTURE_HW(uint32_t, MCNTDTR0) = UINT32_MAX;
    FIXTURE_HW(uint32_t, MCNTDTR1) = 0x7U;
    assert(R_MRAM_AntiRollbackCounterRead(&ctrl, FLASH_ARC_SEC, &before) == FSP_SUCCESS);
    assert(before == 35 && R_MRAM->MCNTSELR == 1 && R_MRAM->MENTRYR == 0);
    volatile uint16_t * arccs = (volatile uint16_t *)(uintptr_t)0x02e17932;
    *arccs = 3U;
    assert(R_MRAM_AntiRollbackCounterRead(&ctrl, FLASH_ARC_NSEC_0, &before) == FSP_ERR_NOT_ENABLED);
    *arccs = 0U;
    assert(R_MRAM_AntiRollbackCounterRead(&ctrl, FLASH_ARC_NSEC_3, &before) == FSP_SUCCESS);
    assert(before == 35 && R_MRAM->MCNTSELR == 7);
    *arccs = 1U;
    assert(R_MRAM_AntiRollbackCounterRead(&ctrl, FLASH_ARC_NSEC_3, &before) == FSP_ERR_INVALID_ARGUMENT);
    assert(R_MRAM_AntiRollbackCounterRead(&ctrl, FLASH_ARC_NSEC_0, &before) == FSP_SUCCESS);
    assert(before == 140 && R_MRAM->MCNTSELR == 7);
    unsigned int commands_before = extra_commands;
    uint8_t select_before = R_MRAM->MCNTSELR;
    /* Irreversible-command timing is source-blocked; rejection must precede MMIO. */
    assert(R_MRAM_AntiRollbackCounterIncrement(&ctrl, FLASH_ARC_OEMBL) == FSP_ERR_UNSUPPORTED);
    assert(extra_commands == commands_before && R_MRAM->MCNTSELR == select_before);
    assert(R_MRAM_StartUpAreaSelect(&ctrl, FLASH_STARTUP_AREA_BLOCK1, true) == FSP_SUCCESS);
    assert(R_MRAM->MSUACR == 0x6603);
    assert(R_MRAM_StartUpAreaSelect(&ctrl, FLASH_STARTUP_AREA_BTFLG, false) == FSP_ERR_INVALID_ARGUMENT);
    commands_before = extra_commands;
    uint32_t address_before = R_MRAM->MSADDR;
    assert(R_MRAM_StartUpAreaSelect(&ctrl, FLASH_STARTUP_AREA_BLOCK1, false) == FSP_ERR_UNSUPPORTED);
    assert(extra_commands == commands_before && R_MRAM->MSADDR == address_before && R_MRAM->MSUACR == 0x6603U);
    FIXTURE_HW(uint32_t, MSUASMON) = 0x8000U;
    assert(R_MRAM_StartUpAreaSelect(&ctrl, FLASH_STARTUP_AREA_BLOCK0, false) == FSP_ERR_UNSUPPORTED);
    assert(extra_commands == commands_before && R_MRAM->MSADDR == address_before && R_MRAM->MSUACR == 0x6603U);
    FIXTURE_HW(uint32_t, MSUASMON) = 0;
    assert(R_MRAM_StartUpAreaSelect(&ctrl, FLASH_STARTUP_AREA_BLOCK0, true) == FSP_ERR_WRITE_FAILED);
    FIXTURE_HW(uint32_t, MSUASMON) = 0x80008000;
    fault = 4;
    assert(R_MRAM_AntiRollbackCounterRead(&ctrl, FLASH_ARC_SEC, &before) == FSP_ERR_TIMEOUT);
    assert(R_MRAM->MENTRYR == 0x80U && R_MRAM->MASTAT == 0 && ctrl.busy && irq_mask == 0);
    FIXTURE_HW(uint32_t, MSTATR) = 0x8000U;
    fault = 0;
    assert(R_MRAM_Reset(&ctrl) == FSP_SUCCESS && !ctrl.busy && R_MRAM->MENTRYR == 0U);
    fault = 5;
    assert(R_MRAM_AntiRollbackCounterRead(&ctrl, FLASH_ARC_SEC, &before) == FSP_ERR_WRITE_FAILED);
    assert(R_MRAM->MENTRYR == 0 && R_MRAM->MASTAT == 0);
#endif
    assert(busy_ticks != 0U);
#if !BSP_TZ_NONSECURE_BUILD
    assert(extra_commands >= 5U);
#endif
    assert(extra_commands < 100U);
    fault = 0;
    R_MRAM->MRCPS = 0x20;
    assert(R_MRAM_Close(&ctrl) == FSP_SUCCESS);
    mram_instance_ctrl_t read_only = {0};
    ext.write_window_start = ext.write_window_end = 0;
    assert(R_MRAM_Open(&read_only, &cfg) == FSP_SUCCESS);
    assert(R_MRAM_Write(&read_only, 0x20000000, dest, 1U) == FSP_ERR_INVALID_ADDRESS);
    assert(R_MRAM_Close(&read_only) == FSP_SUCCESS);
}

#ifdef TEST_DAC_B
/* Independent timing oracle: HM55.3.2 p3504 steps1–5 and Table70.114 p4258.
 * Delay-boundary RAM snapshots prove software ordering, not physical analog timing.
 */
static uint16_t dac_initial(dac_b_instance_ctrl_t const * ctrl)
{
    dac_b_extended_cfg_t const * ext = (dac_b_extended_cfg_t const *) ctrl->p_cfg->p_extend;
    uint16_t value = ext->voltage_mode == DAC_B_VOLTAGE_LOW ? 0x1F8U : 0xE0U;
    return ext->data_format == DAC_DATA_FORMAT_FLUSH_LEFT ? (uint16_t) (value << 4U) : value;
}

static void dac_prepared(unsigned int tick, dac_b_instance_ctrl_t const * ctrl)
{
    unsigned int channel = ctrl->p_cfg->channel;
    assert(delay_control[tick][channel] == 0x80000000U);
    assert(delay_data[tick][channel] == dac_initial(ctrl));
    assert((uint64_t) delays[tick] * 1000U >= 4U); /* tSU >= 4 ns before DACEN/DAE. */
}

static fsp_err_t dac_start_timed(dac_b_instance_ctrl_t * ctrl)
{
    dac_b_extended_cfg_t const * ext = (dac_b_extended_cfg_t const *) ctrl->p_cfg->p_extend;
    dac_b_instance_ctrl_t * pair = ext->p_pair;
    unsigned int first = delay_count;
    fsp_err_t result = R_DAC_B_Start(ctrl);
    assert(result == FSP_SUCCESS);
    if (ext->trigger == DAC_B_TRIGGER_ELC)
    {
        /* The external ELC edge and its timing are not simulated by this host fixture. */
        assert(delay_count == first);
        return result;
    }
    unsigned int units = pair == NULL ? 1U : 2U;
    dac_b_instance_ctrl_t * controls[2] = {ctrl, pair};
    assert(delay_count >= first + units + 1U);
    for (unsigned int unit = 0; unit < units; unit++)
    {
        dac_prepared(first + unit, controls[unit]);
    }
    unsigned int tick = first + units;
    unsigned int channel = ctrl->p_cfg->channel;
    uint32_t enable = pair == NULL ? 1U : 0x8000U;
    assert(delay_control[tick][channel] == (0x80000000U | enable));
    assert(delays[tick] >= 6U); /* tDISOUT starts after DACEN/DAE, not at Open. */
    for (unsigned int unit = 0; unit < units; unit++)
    {
        assert(delay_data[tick][controls[unit]->p_cfg->channel] == dac_initial(controls[unit]));
    }
    if (pair != NULL)
    {
        assert(delay_control[tick][pair->p_cfg->channel] == 0x80000000U);
    }
    tick++;
    for (unsigned int unit = 0; unit < units; unit++)
    {
        dac_b_instance_ctrl_t * current = controls[unit];
        dac_b_extended_cfg_t const * current_ext = (dac_b_extended_cfg_t const *) current->p_cfg->p_extend;
        channel = current->p_cfg->channel;
        uint32_t expected = unit == 0U ? enable : 0U;
        if (current_ext->output == DAC_B_OUTPUT_PIN)
        {
            assert(tick < delay_count && delays[tick] >= 6U); /* tDSLPUP2 after switching. */
            assert(delay_control[tick][channel] == expected);
            assert(delay_data[tick][channel] == dac_initial(current));
            tick++;
        }
        else
        {
            expected |= 0x80000000U;
        }
        assert(tick < delay_count && delays[tick] >= 6U); /* Conversion after sample write. */
        assert(delay_control[tick][channel] == expected);
        assert(delay_data[tick][channel] == current->sample);
        tick++;
    }
    assert(tick == delay_count);
    return result;
}

static void test_dac_b(void)
{
    reset_regs();
    dac_b_extended_cfg_t ext = {.timeout = 8};
    dac_cfg_t cfg = {.p_extend = &ext};
    dac_b_instance_ctrl_t ctrl = {0};
#if DAC_B_CFG_PARAM_CHECKING_ENABLE
    assert(R_DAC_B_Open(NULL, &cfg) == FSP_ERR_ASSERTION);
    assert(R_DAC_B_Open(&ctrl, NULL) == FSP_ERR_ASSERTION);
    dac_cfg_t bad_cfg = {.p_extend = NULL};
    assert(R_DAC_B_Open(&ctrl, &bad_cfg) == FSP_ERR_ASSERTION);
    assert(R_DAC_B_Write(&ctrl, 0U) == FSP_ERR_NOT_OPEN);
    assert(R_DAC_B_Start(&ctrl) == FSP_ERR_NOT_OPEN);
    assert(R_DAC_B_Stop(&ctrl) == FSP_ERR_NOT_OPEN);
    assert(R_DAC_B_Close(&ctrl) == FSP_ERR_NOT_OPEN);
#endif
    cfg.channel = 32;
    assert(R_DAC_B_Open(&ctrl, &cfg) == FSP_ERR_IP_CHANNEL_NOT_PRESENT);
    cfg.channel = 2;
    assert(R_DAC_B_Open(&ctrl, &cfg) == FSP_ERR_IP_CHANNEL_NOT_PRESENT);
    cfg.channel = 0;
    cfg.ad_da_synchronized = true;
    assert(R_DAC_B_Open(&ctrl, &cfg) == FSP_ERR_UNSUPPORTED);
    cfg.ad_da_synchronized = false;
    ext.timeout = 0;
    assert(R_DAC_B_Open(&ctrl, &cfg) == FSP_ERR_INVALID_ARGUMENT);
    ext.timeout = 8;
    ext.data_format = (dac_data_format_t)2;
    assert(R_DAC_B_Open(&ctrl, &cfg) == FSP_ERR_INVALID_ARGUMENT);
    ext.data_format = DAC_DATA_FORMAT_FLUSH_RIGHT;
    ext.voltage_mode = (dac_b_voltage_mode_t)2;
    assert(R_DAC_B_Open(&ctrl, &cfg) == FSP_ERR_INVALID_ARGUMENT);
    ext.voltage_mode = DAC_B_VOLTAGE_NORMAL;
#if BSP_TZ_NONSECURE_BUILD
    assert(R_DAC_B_Open(&ctrl, &cfg) == FSP_ERR_UNSUPPORTED);
    ext.calibration_preloaded = true;
#else
    R_MRAM->MENTRYR = 0x80;
    assert(R_DAC_B_Open(&ctrl, &cfg) == FSP_ERR_IN_USE);
    R_MRAM->MENTRYR = 0;
    FIXTURE_HW(uint8_t, MCTRSTATR) = 1;
    assert(R_DAC_B_Open(&ctrl, &cfg) == FSP_ERR_IN_USE);
    FIXTURE_HW(uint8_t, MCTRSTATR) = 0;
    FIXTURE_HW(uint8_t, MREZS) = 2;
    assert(R_DAC_B_Open(&ctrl, &cfg) == FSP_ERR_IN_USE);
    FIXTURE_HW(uint8_t, MREZS) = 0;
    fault = 6;
    assert(R_DAC_B_Open(&ctrl, &cfg) == FSP_ERR_TIMEOUT);
    assert(ctrl.open == 0 && irq_mask == 0);
    FIXTURE_HW(uint8_t, MCTRSTATR) = 0;
    fault = 7;
    assert(R_DAC_B_Open(&ctrl, &cfg) == FSP_ERR_INVALID_STATE);
    assert(ctrl.open == 0 && irq_mask == 0);
    reset_regs();
    R_MRAM->MCTRLSR = 3;
#endif
    assert(R_DAC_B_Open(&ctrl, &cfg) == FSP_SUCCESS);
#if !BSP_TZ_NONSECURE_BUILD
    assert(R_MRAM->MCTRLSR == 3 && R_MRAM->MCTRCNTR == 0 && irq_mask == 0);
#endif
    assert(R_DAC_B_Close(&ctrl) == FSP_SUCCESS);
    for (uint8_t channel = 0; channel < 2; channel++)
    for (unsigned int format = 0; format < 2; format++)
    for (unsigned int voltage = 0; voltage < 2; voltage++)
    for (unsigned int output = 0; output < 2; output++)
    for (unsigned int trigger = 0; trigger < 2; trigger++)
    {
        reset_regs();
        memset(&ctrl, 0, sizeof(ctrl));
        cfg.channel = channel;
        ext.data_format = (dac_data_format_t)format;
        ext.voltage_mode = (dac_b_voltage_mode_t)voltage;
        ext.output = (dac_b_output_t)output;
        ext.trigger = (dac_b_trigger_t)trigger;
        ext.calibration_preloaded = true;
        assert(R_DAC_B_Open(&ctrl, &cfg) == FSP_SUCCESS);
        assert(ctrl.p_reg == &fixture_dac[channel]);
        assert(fixture_dac[1U - channel].DACR0 == 0);
        assert(ctrl.p_reg->DACR0 == 0x80000000U);
        assert(ctrl.p_reg->DACR1 == (format ? 0x10000U : 0));
        assert(ctrl.p_reg->DACR2 == (voltage ? 0x100U : 0));
        uint16_t initial = voltage ? 0x1F8U : 0xE0U;
        assert(ctrl.p_reg->DADR == (format ? (uint16_t)(initial << 4U) : initial));
        assert(delay_count == 1U);
        dac_prepared(0U, &ctrl);
        uint16_t sample = format ? 0xFFF0U : 0x0FFFU;
        assert(R_DAC_B_Write(&ctrl, sample) == FSP_SUCCESS);
#if DAC_B_CFG_PARAM_CHECKING_ENABLE
        assert(R_DAC_B_Write(&ctrl, format ? 0xFFF1U : 0x1000U) == FSP_ERR_INVALID_ARGUMENT);
        assert(ctrl.sample == sample && ctrl.p_reg->DADR == sample);
#else
        sample = format ? 0xFFF1U : 0x1000U;
        assert(R_DAC_B_Write(&ctrl, sample) == FSP_SUCCESS);
        assert(ctrl.sample == sample && ctrl.p_reg->DADR == sample);
#endif
        assert(dac_start_timed(&ctrl) == FSP_SUCCESS);
        assert(ctrl.started && ctrl.p_reg->DADR == sample);
        assert((ctrl.p_reg->DACR0 & 1U) == (trigger ? 0U : 1U));
        assert((ctrl.p_reg->DACR0 >> 31U) == output);
        assert(R_DAC_B_Start(&ctrl) == FSP_ERR_IN_USE);
        if (trigger) { ctrl.p_reg->DACR0 |= 1U; } /* ELC_DAn hardware action. */
        assert(R_DAC_B_Stop(&ctrl) == FSP_SUCCESS);
        assert((ctrl.p_reg->DACR0 & 0x8001U) == 0 && !ctrl.started);
        assert(dac_start_timed(&ctrl) == FSP_SUCCESS);
        assert(R_DAC_B_Close(&ctrl) == FSP_SUCCESS);
        assert(ctrl.open == 0 && (ctrl.p_reg->DACR0 & 0x8001U) == 0);
        assert(stopped[channel] > 0 && modules[channel] > 0);
    }
    reset_regs();
    dac_b_instance_ctrl_t peer = {0};
    memset(&ctrl, 0, sizeof(ctrl));
    ext = (dac_b_extended_cfg_t){.p_pair = &peer, .timeout = 8, .calibration_preloaded = true};
    dac_b_extended_cfg_t peer_ext = {.p_pair = &ctrl, .timeout = 8, .calibration_preloaded = true};
    dac_cfg_t peer_cfg = {.channel = 1, .p_extend = &peer_ext};
    cfg.channel = 0;
    assert(R_DAC_B_Open(&ctrl, &cfg) == FSP_SUCCESS);
    assert(R_DAC_B_Start(&ctrl) == FSP_ERR_INVALID_STATE);
    assert(R_DAC_B_Open(&peer, &peer_cfg) == FSP_SUCCESS);
    /* Pair ownership must remain distinct even if a caller violates configuration immutability. */
    peer_cfg.channel = 0;
    assert(R_DAC_B_Start(&ctrl) == FSP_ERR_INVALID_STATE);
    assert(!ctrl.started && !peer.started);
    assert((ctrl.p_reg->DACR0 & 0x8001U) == 0U && (peer.p_reg->DACR0 & 0x8001U) == 0U);
    peer_cfg.channel = 1;
    peer_ext.p_pair = NULL;
    assert(R_DAC_B_Start(&ctrl) == FSP_ERR_INVALID_STATE);
    peer_ext.p_pair = &ctrl;
    assert(R_DAC_B_Write(&ctrl, 1000) == FSP_SUCCESS);
    assert(R_DAC_B_Write(&peer, 2000) == FSP_SUCCESS);
    assert(dac_start_timed(&ctrl) == FSP_SUCCESS);
    assert(ctrl.started && peer.started && (ctrl.p_reg->DACR0 & 0x8000U));
    assert(ctrl.p_reg->DADR == 1000 && peer.p_reg->DADR == 2000);
    assert(R_DAC_B_Stop(&peer) == FSP_SUCCESS);
    assert(!ctrl.started && !peer.started);
    assert((ctrl.p_reg->DACR0 & 0x8001U) == 0 && (peer.p_reg->DACR0 & 0x8001U) == 0);
    assert(R_DAC_B_Close(&ctrl) == FSP_SUCCESS);
    assert(R_DAC_B_Close(&peer) == FSP_SUCCESS);
    assert(g_dac_on_dac_b.write == R_DAC_B_Write);
}
#endif

#ifdef TEST_MEMORY_ANALOG_DEFAULTS
extern flash_instance_t const g_mram0;
extern dac_instance_t const g_dac_b0;
static void default_lifecycle(void)
{
    reset_regs();
    mram_extended_cfg_t const * p_mram_ext = (mram_extended_cfg_t const *) g_mram0.p_cfg->p_extend;
    assert(p_mram_ext->write_window_start == p_mram_ext->write_window_end);
    assert(!p_mram_ext->enable_extra_commands && p_mram_ext->timeout > 0U);
    assert(g_mram0.p_api->open(g_mram0.p_ctrl, g_mram0.p_cfg) == FSP_SUCCESS);
    flash_status_t status;
    flash_info_t info;
    flash_result_t result;
#if BSP_TZ_NONSECURE_BUILD
    assert(g_mram0.p_api->statusGet(g_mram0.p_ctrl, &status) == FSP_ERR_UNSUPPORTED && status == FLASH_STATUS_BUSY);
#else
    assert(g_mram0.p_api->statusGet(g_mram0.p_ctrl, &status) == FSP_SUCCESS && status == FLASH_STATUS_IDLE);
#endif
    assert(g_mram0.p_api->infoGet(g_mram0.p_ctrl, &info) == FSP_SUCCESS);
    uint32_t address = info.code_flash.p_block_array->block_section_st_addr;
    memset((void *)(uintptr_t)address, 0xFF, 16U);
#if BSP_TZ_NONSECURE_BUILD
    assert(g_mram0.p_api->blankCheck(g_mram0.p_ctrl, address, 16U, &result) == FSP_ERR_UNSUPPORTED);
#else
    assert(g_mram0.p_api->blankCheck(g_mram0.p_ctrl, address, 16U, &result) == FSP_SUCCESS);
    assert(result == FLASH_RESULT_BLANK);
#endif
    assert(g_mram0.p_api->write(g_mram0.p_ctrl, 0x20000000U, address, 1U) == FSP_ERR_INVALID_ADDRESS);
    assert(g_mram0.p_api->erase(g_mram0.p_ctrl, address, 1U) == FSP_ERR_INVALID_ADDRESS);
    assert(g_mram0.p_api->antiRollbackCounterIncrement(g_mram0.p_ctrl, FLASH_ARC_SEC) == FSP_ERR_NOT_ENABLED);
    assert(g_mram0.p_api->close(g_mram0.p_ctrl) == FSP_SUCCESS);
    dac_b_extended_cfg_t const * p_dac_ext = (dac_b_extended_cfg_t const *) g_dac_b0.p_cfg->p_extend;
    assert(p_dac_ext->timeout > 0U && p_dac_ext->p_pair == NULL && !p_dac_ext->calibration_preloaded);
#if BSP_TZ_NONSECURE_BUILD
    /* The MDF requires explicit secure-startup calibration for a non-secure stack. */
    assert(g_dac_b0.p_api->open(g_dac_b0.p_ctrl, g_dac_b0.p_cfg) == FSP_ERR_UNSUPPORTED);
#else
    assert(g_dac_b0.p_api->open(g_dac_b0.p_ctrl, g_dac_b0.p_cfg) == FSP_SUCCESS);
    assert(g_dac_b0.p_api->write(g_dac_b0.p_ctrl, 0x0123U) == FSP_SUCCESS);
    assert(g_dac_b0.p_api->start(g_dac_b0.p_ctrl) == FSP_SUCCESS);
    assert(R_DAC_B0->DADR == 0x0123U && (R_DAC_B0->DACR0 & 1U) != 0U);
    assert(g_dac_b0.p_api->stop(g_dac_b0.p_ctrl) == FSP_SUCCESS);
    assert(g_dac_b0.p_api->close(g_dac_b0.p_ctrl) == FSP_SUCCESS);
#endif
}
#endif

int main(int argc, char ** argv)
{
    if (!map_at(0x02000000, 0x100000) || !map_at(0x12000000, 0x100000) ||
        !map_at(0x20000000, 0x10000) || !map_at(0x40120000, 0x10000) ||
        !map_at(0x02c9f000, 0x10000) || !map_at(0x02e17000, 0x10000))
    {
        return 77;
    }
    if (argc == 2)
    {
        test_mram_zeroization(argv[1]);
        puts("production zeroization safety passed");
        return 0;
    }
#ifdef TEST_MEMORY_ANALOG_DEFAULTS
    default_lifecycle();
#endif
    test_mram();
    reset_regs();
    test_mram_callbacks();
    assert(flash_callbacks == 0U);
    puts("production MRAM fixture passed");
#ifdef TEST_DAC_B
    test_dac_b();
    puts("production DAC_B fixture passed");
#endif
    return 0;
}
