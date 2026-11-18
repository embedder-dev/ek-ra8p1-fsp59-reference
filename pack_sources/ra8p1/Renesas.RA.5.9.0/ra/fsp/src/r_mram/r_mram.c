/*
 * Copyright (c) 2026 Renesas Electronics Corporation and/or its affiliates
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include "r_mram.h"

#define MRAM_OPEN                (0x4D52414DUL)
#define MRAM_PRV_BASE            (0x02000000UL)
#define MRAM_PRV_NS_BASE         (0x12000000UL)
#define MRAM_PRV_SIZE            (0x00100000UL)
#define MRAM_PRV_BLOCK_SIZE      (2048U)
#define MRAM_PRV_BUSY            (0x80U)
#define MRAM_PRV_FULL            (0x40U)
#define MRAM_PRV_EMPTY           (0x20U)
#define MRAM_PRV_ERRORS          (0x03U)
#define MRAM_PRV_READY           (0x8000UL)
#define MRAM_PRV_ZEROIZING       (0x02U)
#define MRAM_PRV_NOT_ZEROIZED    (0x01U)
#define MRAM_PRV_EXTRA_ERRORS    (0xB85020UL)
#define MRAM_PRV_RAM             BSP_PLACE_IN_SECTION(".code_in_ram") __attribute__((noinline))

#if MRAM_CFG_PARAM_CHECKING_ENABLE
 #define MRAM_PRV_CHECK(p)                         \
    FSP_ASSERT(NULL != (p));                       \
    FSP_ERROR_RETURN(MRAM_OPEN == (p)->open, FSP_ERR_NOT_OPEN)
#else
 #define MRAM_PRV_CHECK(p)
#endif

static fsp_err_t r_mram_range(uint32_t address, uint32_t bytes, uint32_t * p_offset);
static fsp_err_t r_mram_program(mram_instance_ctrl_t * p_ctrl, uint32_t source, uint32_t address,
                                uint32_t bytes, bool fill) MRAM_PRV_RAM;
static fsp_err_t r_mram_extra(mram_instance_ctrl_t * p_ctrl, uint8_t command, uint8_t counter,
                              uint16_t const * p_data, uint32_t * p_low, uint32_t * p_high) MRAM_PRV_RAM;
static fsp_err_t r_mram_extra_check(mram_instance_ctrl_t * p_ctrl, bool irreversible);
#if !BSP_TZ_NONSECURE_BUILD
static fsp_err_t r_mram_read_mode(mram_instance_ctrl_t * p_ctrl) MRAM_PRV_RAM;
#endif
static fsp_err_t r_mram_counter_select(flash_arc_t counter, uint8_t * p_select);
static fsp_err_t r_mram_unsupported(flash_ctrl_t * p_api_ctrl);

flash_api_t const g_flash_on_mram =
{
    .open = R_MRAM_Open,
    .write = R_MRAM_Write,
    .erase = R_MRAM_Erase,
    .blankCheck = R_MRAM_BlankCheck,
    .infoGet = R_MRAM_InfoGet,
    .close = R_MRAM_Close,
    .statusGet = R_MRAM_StatusGet,
    .accessWindowSet = R_MRAM_AccessWindowSet,
    .accessWindowClear = R_MRAM_AccessWindowClear,
    .idCodeSet = R_MRAM_IdCodeSet,
    .reset = R_MRAM_Reset,
    .updateFlashClockFreq = R_MRAM_UpdateFlashClockFreq,
    .startupAreaSelect = R_MRAM_StartUpAreaSelect,
    .bankSwap = R_MRAM_BankSwap,
    .callbackSet = R_MRAM_CallbackSet,
    .antiRollbackCounterIncrement = R_MRAM_AntiRollbackCounterIncrement,
    .antiRollbackCounterRefresh = R_MRAM_AntiRollbackCounterRefresh,
    .antiRollbackCounterRead = R_MRAM_AntiRollbackCounterRead,
    .userLockableAreaWrite = R_MRAM_UserLockableAreaWrite,
};

/** @addtogroup MRAM
 * @{ */

/** Implements flash_api_t::open.
 * @retval FSP_SUCCESS Opened, with writes confined to the explicitly reserved window.
 * @retval FSP_ERR_ASSERTION NULL argument.
 * @retval FSP_ERR_ALREADY_OPEN Already open.
 * @retval FSP_ERR_UNSUPPORTED Data-flash BGO requested (there is no data flash).
 * @retval FSP_ERR_INVALID_ADDRESS Invalid writable window.
 * @retval FSP_ERR_INVALID_ARGUMENT Zero polling budget.
 */
fsp_err_t R_MRAM_Open (flash_ctrl_t * const p_api_ctrl, flash_cfg_t const * const p_cfg)
{
    mram_instance_ctrl_t * p_ctrl = (mram_instance_ctrl_t *) p_api_ctrl;
#if MRAM_CFG_PARAM_CHECKING_ENABLE
    FSP_ASSERT(NULL != p_ctrl);
    FSP_ASSERT(NULL != p_cfg);
    FSP_ASSERT(NULL != p_cfg->p_extend);
    FSP_ERROR_RETURN(MRAM_OPEN != p_ctrl->open, FSP_ERR_ALREADY_OPEN);
#endif
    mram_extended_cfg_t const * p_extend = (mram_extended_cfg_t const *) p_cfg->p_extend;
    FSP_ERROR_RETURN(!p_cfg->data_flash_bgo, FSP_ERR_UNSUPPORTED);
    FSP_ERROR_RETURN(0U != p_extend->timeout, FSP_ERR_INVALID_ARGUMENT);
    uint32_t offset = 0U;
    if (p_extend->write_window_start != p_extend->write_window_end)
    {
        FSP_ERROR_RETURN(p_extend->write_window_end > p_extend->write_window_start, FSP_ERR_INVALID_ADDRESS);
        fsp_err_t err = r_mram_range(p_extend->write_window_start,
                                     p_extend->write_window_end - p_extend->write_window_start, &offset);
        FSP_ERROR_RETURN(FSP_SUCCESS == err, err);
    }
    p_ctrl->window_start = offset;
    p_ctrl->window_end = offset + p_extend->write_window_end - p_extend->write_window_start;
    p_ctrl->p_cfg = p_cfg;
    p_ctrl->p_callback = p_cfg->p_callback;
    p_ctrl->p_context = p_cfg->p_context;
    p_ctrl->p_callback_memory = NULL;
    p_ctrl->timeout = p_extend->timeout;
    p_ctrl->busy = false;
    p_ctrl->extra_recovery_required = false;
    p_ctrl->open = MRAM_OPEN;
    return FSP_SUCCESS;
}

/** Implements flash_api_t::write. Byte writes are supported, including unaligned buffers.
 * @retval FSP_SUCCESS Written and synchronized.
 * @retval FSP_ERR_ASSERTION NULL control.
 * @retval FSP_ERR_NOT_OPEN Not open.
 * @retval FSP_ERR_INVALID_ADDRESS Outside code MRAM/reserved window, overflow or overlapping source.
 * @retval FSP_ERR_INVALID_SIZE Empty request.
 * @retval FSP_ERR_IN_USE Another programming operation is active.
 * @retval FSP_ERR_INVALID_LINKED_ADDRESS Programming helper was not relocated to RAM.
 * @retval FSP_ERR_WRITE_FAILED Hardware protection or programming/ECC error.
 * @retval FSP_ERR_TIMEOUT Hardware did not complete within the polling budget.
 */
fsp_err_t R_MRAM_Write (flash_ctrl_t * const p_api_ctrl, uint32_t const src_address,
                       uint32_t const flash_address, uint32_t const num_bytes)
{
    mram_instance_ctrl_t * p_ctrl = (mram_instance_ctrl_t *) p_api_ctrl;
    MRAM_PRV_CHECK(p_ctrl);
    uint32_t offset;
    fsp_err_t err = r_mram_range(flash_address, num_bytes, &offset);
    FSP_ERROR_RETURN(FSP_SUCCESS == err, err);
    FSP_ERROR_RETURN((offset >= p_ctrl->window_start) && (offset < p_ctrl->window_end) &&
                     (num_bytes <= p_ctrl->window_end - offset), FSP_ERR_INVALID_ADDRESS);
    FSP_ERROR_RETURN((0U != src_address) && (num_bytes - 1U <= UINT32_MAX - src_address),
                     FSP_ERR_INVALID_ADDRESS);
    uint32_t src_offset;
    /* Low code addresses are core-local TCM, not MRAM aliases (HM5.1, HM2.17.1.1). */
    uint32_t source_alias = src_address;
    if (((source_alias >= MRAM_PRV_BASE) && (source_alias - MRAM_PRV_BASE < MRAM_PRV_SIZE)) ||
        ((source_alias >= MRAM_PRV_NS_BASE) && (source_alias - MRAM_PRV_NS_BASE < MRAM_PRV_SIZE)))
    {
        err = r_mram_range(source_alias, num_bytes, &src_offset);
        FSP_ERROR_RETURN(FSP_SUCCESS == err, err);
        FSP_ERROR_RETURN((src_offset + num_bytes <= offset) || (offset + num_bytes <= src_offset),
                         FSP_ERR_INVALID_ADDRESS);
    }
    return r_mram_program(p_ctrl, src_address, flash_address, num_bytes, false);
}

/** Implements flash_api_t::erase by programming ones, not by a nonexistent erase command.
 * @retval FSP_SUCCESS Requested 2-KB logical blocks filled with 0xFF.
 * @retval FSP_ERR_INVALID_BLOCKS Zero blocks or multiplication overflow.
 * @retval FSP_ERR_INVALID_ADDRESS Containing blocks extend outside reserved code window.
 * @retval FSP_ERR_ASSERTION NULL control.
 * @retval FSP_ERR_NOT_OPEN Not open.
 * @retval FSP_ERR_IN_USE Busy.
 * @retval FSP_ERR_INVALID_LINKED_ADDRESS RAM helper not relocated.
 * @retval FSP_ERR_TIMEOUT Hardware timeout.
 * @retval FSP_ERR_WRITE_FAILED Programming or protection error.
 */
fsp_err_t R_MRAM_Erase (flash_ctrl_t * const p_api_ctrl, uint32_t const address, uint32_t const num_blocks)
{
    mram_instance_ctrl_t * p_ctrl = (mram_instance_ctrl_t *) p_api_ctrl;
    MRAM_PRV_CHECK(p_ctrl);
    FSP_ERROR_RETURN((0U != num_blocks) && (num_blocks <= MRAM_PRV_SIZE / MRAM_PRV_BLOCK_SIZE),
                     FSP_ERR_INVALID_BLOCKS);
    uint32_t block_address = address - (address % MRAM_PRV_BLOCK_SIZE);
    uint32_t bytes = num_blocks * MRAM_PRV_BLOCK_SIZE;
    uint32_t offset;
    fsp_err_t err = r_mram_range(block_address, bytes, &offset);
    FSP_ERROR_RETURN(FSP_SUCCESS == err, err);
    FSP_ERROR_RETURN((offset >= p_ctrl->window_start) && (offset < p_ctrl->window_end) &&
                     (bytes <= p_ctrl->window_end - offset), FSP_ERR_INVALID_ADDRESS);
    return r_mram_program(p_ctrl, 0U, block_address, bytes, true);
}

/** Implements flash_api_t::blankCheck.
 * @retval FSP_SUCCESS Result reports whether all bytes are 0xFF.
 * @retval FSP_ERR_ASSERTION NULL control/result.
 * @retval FSP_ERR_NOT_OPEN Not open.
 * @retval FSP_ERR_INVALID_ADDRESS Outside code MRAM or overflowing range.
 * @retval FSP_ERR_INVALID_SIZE Empty request.
 * @retval FSP_ERR_IN_USE Programming active.
 */
fsp_err_t R_MRAM_BlankCheck (flash_ctrl_t * const p_api_ctrl, uint32_t const address, uint32_t const num_bytes,
                            flash_result_t * const p_blank_check_result)
{
    mram_instance_ctrl_t * p_ctrl = (mram_instance_ctrl_t *) p_api_ctrl;
    MRAM_PRV_CHECK(p_ctrl);
#if MRAM_CFG_PARAM_CHECKING_ENABLE
    FSP_ASSERT(NULL != p_blank_check_result);
#endif
    uint32_t offset;
    fsp_err_t err = r_mram_range(address, num_bytes, &offset);
    FSP_ERROR_RETURN(FSP_SUCCESS == err, err);
    flash_status_t status;
    fsp_err_t status_err = R_MRAM_StatusGet(p_ctrl, &status);
    FSP_ERROR_RETURN(FSP_SUCCESS == status_err, status_err);
    FSP_ERROR_RETURN(FLASH_STATUS_IDLE == status, FSP_ERR_IN_USE);
    *p_blank_check_result = FLASH_RESULT_BLANK;
    uint8_t const volatile * p_data = (uint8_t const volatile *) (uintptr_t) address;
    for (uint32_t i = 0U; i < num_bytes; i++)
    {
        if (UINT8_MAX != p_data[i])
        {
            *p_blank_check_result = FLASH_RESULT_NOT_BLANK;
            break;
        }
    }
    return FSP_SUCCESS;
}

/** Implements flash_api_t::infoGet. No data-flash region exists.
 * @retval FSP_SUCCESS Information returned.
 * @retval FSP_ERR_ASSERTION NULL argument.
 * @retval FSP_ERR_NOT_OPEN Not open.
 */
fsp_err_t R_MRAM_InfoGet (flash_ctrl_t * const p_api_ctrl, flash_info_t * const p_info)
{
    mram_instance_ctrl_t * p_ctrl = (mram_instance_ctrl_t *) p_api_ctrl;
    MRAM_PRV_CHECK(p_ctrl);
    FSP_PARAMETER_NOT_USED(p_ctrl);
#if MRAM_CFG_PARAM_CHECKING_ENABLE
    FSP_ASSERT(NULL != p_info);
#endif
    static flash_block_info_t const region =
    {
#if BSP_TZ_NONSECURE_BUILD
        MRAM_PRV_NS_BASE, MRAM_PRV_NS_BASE + MRAM_PRV_SIZE - 1U, MRAM_PRV_BLOCK_SIZE, 1U
#else
        MRAM_PRV_BASE, MRAM_PRV_BASE + MRAM_PRV_SIZE - 1U, MRAM_PRV_BLOCK_SIZE, 1U
#endif
    };
    p_info->code_flash.num_regions = 1U;
    p_info->code_flash.p_block_array = &region;
    p_info->data_flash.num_regions = 0U;
    p_info->data_flash.p_block_array = NULL;
    return FSP_SUCCESS;
}

/** Implements flash_api_t::statusGet.
 * @retval FSP_SUCCESS Software and both sequencers' busy state returned.
 * @retval FSP_ERR_ASSERTION NULL argument.
 * @retval FSP_ERR_NOT_OPEN Not open.
 */
fsp_err_t R_MRAM_StatusGet (flash_ctrl_t * const p_api_ctrl, flash_status_t * const p_status)
{
    mram_instance_ctrl_t * p_ctrl = (mram_instance_ctrl_t *) p_api_ctrl;
    MRAM_PRV_CHECK(p_ctrl);
#if MRAM_CFG_PARAM_CHECKING_ENABLE
    FSP_ASSERT(NULL != p_status);
#endif
#if BSP_TZ_NONSECURE_BUILD
    /* MREZS is S-TYPE-6 even through the NS register alias. Its zeroization
     * interlock cannot be replaced by MRDY; use an authorized secure instance.
     */
    FSP_PARAMETER_NOT_USED(p_ctrl);
    *p_status = FLASH_STATUS_BUSY;
    return FSP_ERR_UNSUPPORTED;
#else
    bool busy = p_ctrl->busy || (0U != (R_MRAM->MRCPS & (MRAM_PRV_BUSY | MRAM_PRV_FULL))) ||
                (0U == (R_MRAM->MSTATR & MRAM_PRV_READY)) || (0U != (R_MRAM->MCTRSTATR & 1U)) ||
                (0U != R_MRAM->MENTRYR) || (0U != (R_MRAM->MREZS & MRAM_PRV_ZEROIZING));
    *p_status = busy ? FLASH_STATUS_BUSY : FLASH_STATUS_IDLE;
    return FSP_SUCCESS;
#endif
}

/** Implements flash_api_t::close.
 * @retval FSP_SUCCESS Closed without altering existing protection configuration.
 * @retval FSP_ERR_ASSERTION NULL control.
 * @retval FSP_ERR_NOT_OPEN Not open.
 * @retval FSP_ERR_IN_USE Busy.
 */
fsp_err_t R_MRAM_Close (flash_ctrl_t * const p_api_ctrl)
{
    mram_instance_ctrl_t * p_ctrl = (mram_instance_ctrl_t *) p_api_ctrl;
    MRAM_PRV_CHECK(p_ctrl);
#if BSP_TZ_NONSECURE_BUILD
    /* A standalone NS instance never starts hardware operations. */
    FSP_ERROR_RETURN(!p_ctrl->busy, FSP_ERR_IN_USE);
#else
    flash_status_t status;
    fsp_err_t status_err = R_MRAM_StatusGet(p_ctrl, &status);
    FSP_ERROR_RETURN(FSP_SUCCESS == status_err, status_err);
    FSP_ERROR_RETURN(FLASH_STATUS_IDLE == status, FSP_ERR_IN_USE);
#endif
    p_ctrl->open = 0U;
    return FSP_SUCCESS;
}

/** Implements flash_api_t::reset. Code programming has no forced-stop command.
 * @retval FSP_SUCCESS Stale code-program error flags cleared.
 * @retval FSP_ERR_ASSERTION NULL control.
 * @retval FSP_ERR_NOT_OPEN Not open.
 * @retval FSP_ERR_IN_USE Code sequencer active; reset must not discard buffered writes.
 * @retval FSP_ERR_WRITE_FAILED Error flags could not be cleared.
 */
fsp_err_t R_MRAM_Reset (flash_ctrl_t * const p_api_ctrl)
{
    mram_instance_ctrl_t * p_ctrl = (mram_instance_ctrl_t *) p_api_ctrl;
    MRAM_PRV_CHECK(p_ctrl);
#if !BSP_TZ_NONSECURE_BUILD
    if (p_ctrl->extra_recovery_required)
    {
        return r_mram_extra(p_ctrl, 0x50U, 0U, NULL, NULL, NULL);
    }
#endif
    flash_status_t status;
    fsp_err_t status_err = R_MRAM_StatusGet(p_ctrl, &status);
    FSP_ERROR_RETURN(FSP_SUCCESS == status_err, status_err);
    FSP_ERROR_RETURN(FLASH_STATUS_IDLE == status, FSP_ERR_IN_USE);
    for (uint32_t i = 0U; i < p_ctrl->timeout; i++)
    {
        uint8_t program_status = R_MRAM->MRCPS;
        if (0U == (program_status & MRAM_PRV_ERRORS))
        {
            return FSP_SUCCESS;
        }
        R_MRAM->MRCPS = 0U;
    }
    return FSP_ERR_WRITE_FAILED;
}

/** Implements flash_api_t::startupAreaSelect. Secure, explicit opt-in operation.
 * @retval FSP_SUCCESS Startup selection written.
 * @retval FSP_ERR_ASSERTION NULL control.
 * @retval FSP_ERR_NOT_OPEN Not open.
 * @retval FSP_ERR_INVALID_ARGUMENT Invalid selection/temporary combination.
 * @retval FSP_ERR_NOT_ENABLED Extra operations not opted in.
 * @retval FSP_ERR_UNSUPPORTED Non-secure caller or permanent update without calibrated timing.
 * @retval FSP_ERR_WRITE_FAILED FSPR protection or command error.
 * @retval FSP_ERR_IN_USE MRAM/zeroization/configuration transfer busy.
 * @retval FSP_ERR_INVALID_LINKED_ADDRESS Helper not in RAM.
 * @retval FSP_ERR_TIMEOUT Command timeout.
 */
fsp_err_t R_MRAM_StartUpAreaSelect (flash_ctrl_t * const p_api_ctrl, flash_startup_area_swap_t swap_type,
                                  bool is_temporary)
{
    mram_instance_ctrl_t * p_ctrl = (mram_instance_ctrl_t *) p_api_ctrl;
    MRAM_PRV_CHECK(p_ctrl);
    FSP_ERROR_RETURN((FLASH_STARTUP_AREA_BTFLG == swap_type) || (FLASH_STARTUP_AREA_BLOCK0 == swap_type) ||
                     (FLASH_STARTUP_AREA_BLOCK1 == swap_type), FSP_ERR_INVALID_ARGUMENT);
    FSP_ERROR_RETURN(is_temporary || (FLASH_STARTUP_AREA_BTFLG != swap_type), FSP_ERR_INVALID_ARGUMENT);
    fsp_err_t err = r_mram_extra_check(p_ctrl, !is_temporary);
    FSP_ERROR_RETURN(FSP_SUCCESS == err, err);
#if !BSP_TZ_NONSECURE_BUILD
    FSP_ERROR_RETURN(0U != (R_MRAM->MSUASMON & 0x8000U), FSP_ERR_WRITE_FAILED);
    if (is_temporary)
    {
        return r_mram_extra(p_ctrl, 0x66U, (uint8_t) swap_type, NULL, NULL, NULL);
    }
    uint16_t data[8];
    uint16_t const volatile * p_sas = (uint16_t const volatile *) (uintptr_t) 0x02C9F070UL;
    for (uint32_t i = 0U; i < 8U; i++)
    {
        data[i] = p_sas[i];
    }
    /* SAS.BTFLG is bit 31 of the word at offset 4 (HM60.9.3, Figure 60.26). */
    data[3] = (uint16_t) ((data[3] & 0x7FFFU) |
                          ((FLASH_STARTUP_AREA_BLOCK0 == swap_type) ? 0x8000U : 0U));
    return r_mram_extra(p_ctrl, 0x40U, 0U, data, NULL, NULL);
#else
    return FSP_ERR_UNSUPPORTED;
#endif
}

/** Implements flash_api_t::antiRollbackCounterRead. Returns unary population count, not raw OTP bits.
 * @retval FSP_SUCCESS Count returned (0..64 per segment).
 * @retval FSP_ERR_ASSERTION NULL argument.
 * @retval FSP_ERR_NOT_OPEN Not open.
 * @retval FSP_ERR_INVALID_ARGUMENT Invalid counter.
 * @retval FSP_ERR_NOT_ENABLED Extra operations disabled.
 * @retval FSP_ERR_UNSUPPORTED Non-secure caller.
 * @retval FSP_ERR_IN_USE Sequencer busy.
 * @retval FSP_ERR_WRITE_FAILED Command/protection error.
 * @retval FSP_ERR_TIMEOUT Command timeout.
 * @retval FSP_ERR_INVALID_LINKED_ADDRESS RAM helper not relocated.
 */
fsp_err_t R_MRAM_AntiRollbackCounterRead (flash_ctrl_t * const p_api_ctrl, flash_arc_t counter,
                                        uint32_t * const p_count)
{
    mram_instance_ctrl_t * p_ctrl = (mram_instance_ctrl_t *) p_api_ctrl;
    MRAM_PRV_CHECK(p_ctrl);
#if MRAM_CFG_PARAM_CHECKING_ENABLE
    FSP_ASSERT(NULL != p_count);
#endif
    FSP_ERROR_RETURN((uint32_t) counter <= (uint32_t) FLASH_ARC_NSEC_3, FSP_ERR_INVALID_ARGUMENT);
    uint8_t select;
    fsp_err_t err = r_mram_extra_check(p_ctrl, false);
    FSP_ERROR_RETURN(FSP_SUCCESS == err, err);
    err = r_mram_counter_select(counter, &select);
    FSP_ERROR_RETURN(FSP_SUCCESS == err, err);
    uint32_t segments = 1U;
#if !BSP_TZ_NONSECURE_BUILD
    if ((FLASH_ARC_NSEC_0 == counter) &&
        (1U == (*((uint16_t const volatile *) (uintptr_t) 0x02E17932UL) & 3U)))
    {
        segments = 4U;
    }
#endif
    uint32_t count = 0U;
    for (uint32_t segment = 0U; segment < segments; segment++)
    {
        uint32_t low = 0U;
        uint32_t high = 0U;
        err = r_mram_extra(p_ctrl, 0x39U, (uint8_t) (select + segment), NULL, &low, &high);
        FSP_ERROR_RETURN(FSP_SUCCESS == err, err);
        for (uint32_t i = 0U; i < 32U; i++)
        {
            count += (low >> i) & 1U;
            count += (high >> i) & 1U;
        }
    }
    *p_count = count;
    return FSP_SUCCESS;
}

/** Implements flash_api_t::antiRollbackCounterIncrement.
 * Irreversible commands require calibrated maximum timing before they can be admitted.
 * @retval FSP_ERR_ASSERTION NULL control.
 * @retval FSP_ERR_NOT_OPEN Not open.
 * @retval FSP_ERR_INVALID_ARGUMENT Invalid counter.
 * @retval FSP_ERR_NOT_ENABLED Extra operations disabled.
 * @retval FSP_ERR_UNSUPPORTED Calibrated maximum command timing is unavailable, or non-secure caller.
 * @retval FSP_ERR_IN_USE Sequencer busy.
 * @retval FSP_ERR_WRITE_FAILED Command/protection error.
 * @retval FSP_ERR_TIMEOUT Command timeout.
 * @retval FSP_ERR_INVALID_LINKED_ADDRESS RAM helper not relocated.
 */
fsp_err_t R_MRAM_AntiRollbackCounterIncrement (flash_ctrl_t * const p_api_ctrl, flash_arc_t counter)
{
    mram_instance_ctrl_t * p_ctrl = (mram_instance_ctrl_t *) p_api_ctrl;
    MRAM_PRV_CHECK(p_ctrl);
    FSP_ERROR_RETURN((uint32_t) counter <= (uint32_t) FLASH_ARC_NSEC_3, FSP_ERR_INVALID_ARGUMENT);
    uint8_t select;
    fsp_err_t err = r_mram_extra_check(p_ctrl, true);
    FSP_ERROR_RETURN(FSP_SUCCESS == err, err);
    err = r_mram_counter_select(counter, &select);
    FSP_ERROR_RETURN(FSP_SUCCESS == err, err);
    /* OEMBL requires the immediately preceding command to read that counter. */
    if (FLASH_ARC_OEMBL == counter)
    {
        uint32_t low;
        uint32_t high;
        err = r_mram_extra(p_ctrl, 0x39U, select, NULL, &low, &high);
        FSP_ERROR_RETURN(FSP_SUCCESS == err, err);
    }
    return r_mram_extra(p_ctrl, 0x35U, select, NULL, NULL, NULL);
}

/* These flash-interface operations have no corresponding MRAM operation:
 * access window (MRAM uses per-block protection), flash ID, bank swap, FCLK,
 * counter refresh, and flash user-lockable area.
 */
fsp_err_t R_MRAM_AccessWindowSet (flash_ctrl_t * const p_ctrl, uint32_t const start_addr, uint32_t const end_addr)
{
    FSP_PARAMETER_NOT_USED(start_addr);
    FSP_PARAMETER_NOT_USED(end_addr);
    return r_mram_unsupported(p_ctrl);
}

fsp_err_t R_MRAM_AccessWindowClear (flash_ctrl_t * const p_ctrl)
{
    return r_mram_unsupported(p_ctrl);
}

fsp_err_t R_MRAM_IdCodeSet (flash_ctrl_t * const p_ctrl, uint8_t const * const p_id_bytes, flash_id_code_mode_t mode)
{
    FSP_PARAMETER_NOT_USED(p_id_bytes);
    FSP_PARAMETER_NOT_USED(mode);
    return r_mram_unsupported(p_ctrl);
}

fsp_err_t R_MRAM_UpdateFlashClockFreq (flash_ctrl_t * const p_ctrl)
{
    return r_mram_unsupported(p_ctrl);
}

fsp_err_t R_MRAM_BankSwap (flash_ctrl_t * const p_ctrl)
{
    return r_mram_unsupported(p_ctrl);
}

/** Implements flash_api_t::callbackSet. Stores callback state only: all MRAM operations
 * remain blocking and do not generate BGO/completion callbacks.
 * @retval FSP_SUCCESS Callback and context stored.
 * @retval FSP_ERR_ASSERTION Required control/callback pointer is NULL.
 * @retval FSP_ERR_NOT_OPEN Instance is closed.
 * @retval FSP_ERR_NO_CALLBACK_MEMORY Non-secure callback memory is absent or not non-secure writable memory.
 */
fsp_err_t R_MRAM_CallbackSet (flash_ctrl_t * const p_api_ctrl, void (* p_callback)(flash_callback_args_t *),
                             void const * const p_context, flash_callback_args_t * const p_callback_memory)
{
    mram_instance_ctrl_t * p_ctrl = (mram_instance_ctrl_t *) p_api_ctrl;
#if MRAM_CFG_PARAM_CHECKING_ENABLE
    FSP_ASSERT(NULL != p_ctrl);
    FSP_ASSERT(NULL != p_callback);
    FSP_ERROR_RETURN(MRAM_OPEN == p_ctrl->open, FSP_ERR_NOT_OPEN);
#endif
#if BSP_TZ_SECURE_BUILD
    bool callback_is_secure =
        (NULL == cmse_check_address_range((void *) p_callback, sizeof(void *), CMSE_AU_NONSECURE));
    flash_callback_args_t * const p_checked =
        cmse_check_pointed_object(p_callback_memory, CMSE_AU_NONSECURE | CMSE_MPU_READWRITE);
    FSP_ERROR_RETURN(callback_is_secure || (NULL != p_checked), FSP_ERR_NO_CALLBACK_MEMORY);
    p_ctrl->p_callback = callback_is_secure ? p_callback :
                        (void (*)(flash_callback_args_t *)) cmse_nsfptr_create(p_callback);
#else
    p_ctrl->p_callback = p_callback;
#endif
    p_ctrl->p_context = p_context;
    p_ctrl->p_callback_memory = p_callback_memory;
    return FSP_SUCCESS;
}

fsp_err_t R_MRAM_AntiRollbackCounterRefresh (flash_ctrl_t * const p_ctrl, flash_arc_t counter)
{
    FSP_PARAMETER_NOT_USED(counter);
    return r_mram_unsupported(p_ctrl);
}

fsp_err_t R_MRAM_UserLockableAreaWrite (flash_ctrl_t * const p_ctrl, uint32_t const src_address,
                                      uint32_t const flash_address, uint32_t const num_bytes)
{
    FSP_PARAMETER_NOT_USED(src_address);
    FSP_PARAMETER_NOT_USED(flash_address);
    FSP_PARAMETER_NOT_USED(num_bytes);
    return r_mram_unsupported(p_ctrl);
}

/** @} */

static fsp_err_t r_mram_unsupported (flash_ctrl_t * p_api_ctrl)
{
    mram_instance_ctrl_t * p_ctrl = (mram_instance_ctrl_t *) p_api_ctrl;
    MRAM_PRV_CHECK(p_ctrl);
    FSP_PARAMETER_NOT_USED(p_ctrl);
    return FSP_ERR_UNSUPPORTED;
}

static fsp_err_t r_mram_range (uint32_t address, uint32_t bytes, uint32_t * p_offset)
{
    FSP_ERROR_RETURN(0U != bytes, FSP_ERR_INVALID_SIZE);
#if BSP_TZ_NONSECURE_BUILD
    FSP_ERROR_RETURN(address >= MRAM_PRV_NS_BASE, FSP_ERR_INVALID_ADDRESS);
#else
    if ((address >= MRAM_PRV_BASE) && (address - MRAM_PRV_BASE < MRAM_PRV_SIZE))
    {
        *p_offset = address - MRAM_PRV_BASE;
        FSP_ERROR_RETURN(bytes <= MRAM_PRV_SIZE - *p_offset, FSP_ERR_INVALID_ADDRESS);
        return FSP_SUCCESS;
    }
#endif
    FSP_ERROR_RETURN((address >= MRAM_PRV_NS_BASE) && (address - MRAM_PRV_NS_BASE < MRAM_PRV_SIZE),
                     FSP_ERR_INVALID_ADDRESS);
    *p_offset = address - MRAM_PRV_NS_BASE;
    FSP_ERROR_RETURN(bytes <= MRAM_PRV_SIZE - *p_offset, FSP_ERR_INVALID_ADDRESS);
    return FSP_SUCCESS;
}

/* All code executed between first store and completion lives in .code_in_ram.
 * Interrupt masking does not mask NMI: the application must relocate NMI code/vectors.
 * Exclusive ownership of the other core and DMA is an application prerequisite.
 */
static fsp_err_t r_mram_program (mram_instance_ctrl_t * p_ctrl, uint32_t source, uint32_t address,
                                uint32_t bytes, bool fill)
{
#if BSP_TZ_NONSECURE_BUILD
    FSP_PARAMETER_NOT_USED(p_ctrl);
    FSP_PARAMETER_NOT_USED(source);
    FSP_PARAMETER_NOT_USED(address);
    FSP_PARAMETER_NOT_USED(bytes);
    FSP_PARAMETER_NOT_USED(fill);
    return FSP_ERR_UNSUPPORTED;
#else
    uintptr_t pc = (uintptr_t) r_mram_program;
    FSP_ERROR_RETURN(!(((pc >= MRAM_PRV_BASE) && (pc - MRAM_PRV_BASE < MRAM_PRV_SIZE)) ||
                     ((pc >= MRAM_PRV_NS_BASE) && (pc - MRAM_PRV_NS_BASE < MRAM_PRV_SIZE))),
                     FSP_ERR_INVALID_LINKED_ADDRESS);
    uint32_t primask = __get_PRIMASK();
    __disable_irq();
    uint8_t zeroization = R_MRAM->MREZS;
    if (p_ctrl->busy || (0U != (R_MRAM->MRCPS & (MRAM_PRV_BUSY | MRAM_PRV_FULL))) ||
        (0U == (R_MRAM->MSTATR & MRAM_PRV_READY)) || (0U != (R_MRAM->MCTRSTATR & 1U)) ||
        (0U != R_MRAM->MENTRYR) || (0U != (zeroization & MRAM_PRV_ZEROIZING)))
    {
        __set_PRIMASK(primask);
        return FSP_ERR_IN_USE;
    }
    p_ctrl->busy = true;
    uint8_t prefetch = R_MRAM->MRCPFB;
    R_MRAM->MRCPFB = 0U;
    volatile uint8_t dummy = R_MRAM->MRCPFB;
    dummy = R_MRAM->MRCPFB;
    dummy = R_MRAM->MRCPFB;
    FSP_PARAMETER_NOT_USED(dummy);
#if BSP_CFG_CPU_CORE == 1
    /* CPU1's Code/System caches are outside the CM33 core. Disable with write
     * back and flush, then wait for completion (HM2.16.3.3, HM2.16.3.13).
     * CPU0 must never operate these shared maintenance registers.
     */
    while (0U != (R_CACHE->CCAFCT | R_CACHE->SCAFCT))
    {
        __NOP();
    }
    uint32_t ccache = R_CACHE->CCACTL & 1U;
    uint32_t scache = R_CACHE->SCACTL & 1U;
    R_CACHE->CCACTL = (R_CACHE->CCAWTA & 1U) ? 0x100U : 0x300U;
    R_CACHE->SCACTL = (R_CACHE->SCAWTA & 1U) ? 0x100U : 0x300U;
    __DSB();
    while (0U != (R_CACHE->CCAFCT | R_CACHE->SCAFCT))
    {
        __NOP();
    }
    __DSB();
    __ISB();
    if (0U != ((R_CACHE->CCACTL | R_CACHE->SCACTL) & 1U))
    {
        /* Do not open MRAM protection if cache disable was not accepted. */
        R_CACHE->CCACTL = ccache;
        R_CACHE->SCACTL = scache;
        R_MRAM->MRCPFB = prefetch;
        __DSB();
        __ISB();
        p_ctrl->busy = false;
        __set_PRIMASK(primask);
        return FSP_ERR_WRITE_FAILED;
    }
#elif defined(__DCACHE_PRESENT) && (__DCACHE_PRESENT == 1U)
    uint32_t dcache = SCB->CCR & SCB_CCR_DC_Msk;
    SCB_DisableDCache();
#endif
    volatile uint16_t * p_protect = &R_MRAM->MRCPC0;
    uint16_t key = 0x8600U;
#if !BSP_TZ_NONSECURE_BUILD
    if (address < MRAM_PRV_NS_BASE)
    {
        p_protect = &R_MRAM->MRCPC1;
        key = 0x6800U;
    }
#endif
    uint16_t protection = (uint16_t) (*p_protect & 1U);
    fsp_err_t err = FSP_SUCCESS;
    R_MRAM->MRCPS = 0U;
    *p_protect = (uint16_t) (key | 1U);
    if (0U == (*p_protect & 1U))
    {
        err = FSP_ERR_WRITE_FAILED;
    }
    while ((0U != bytes) && (FSP_SUCCESS == err))
    {
        uint8_t zeroization_status = R_MRAM->MREZS;
        if ((0U != (zeroization_status & MRAM_PRV_ZEROIZING)) ||
            (0U != ((zeroization_status ^ zeroization) & MRAM_PRV_NOT_ZEROIZED)))
        {
            err = FSP_ERR_WRITE_FAILED;
            break;
        }
        uint32_t count = 32U - (address & 31U);
        if (count > bytes)
        {
            count = bytes;
        }
        uint8_t data[32];
        for (uint32_t i = 0U; i < count; i++)
        {
            data[i] = fill ? UINT8_MAX : *((uint8_t const volatile *) (uintptr_t) (source + i));
        }
        for (uint32_t i = 0U; i < count; i++)
        {
            *((uint8_t volatile *) (uintptr_t) (address + i)) = data[i];
        }
        __DMB();
        /* Complete every store before flushing the controller's program buffer. */
        __DSB();
        if (0U == (R_MRAM->MRCPS & MRAM_PRV_EMPTY))
        {
            R_MRAM->MRCFLR = 0xC301U;
        }
        uint32_t wait = p_ctrl->timeout;
        while (true)
        {
            zeroization_status = R_MRAM->MREZS;
            /* MRDY does not describe W-HUK zeroing. WHUKZF also catches a zeroing
             * operation completed between polls; interrupted data is undefined (HM60.14).
             */
            if ((0U != (zeroization_status & MRAM_PRV_ZEROIZING)) ||
                (0U != ((zeroization_status ^ zeroization) & MRAM_PRV_NOT_ZEROIZED)))
            {
                err = FSP_ERR_WRITE_FAILED;
            }
            if (((R_MRAM->MRCPS & (MRAM_PRV_EMPTY | MRAM_PRV_BUSY)) == MRAM_PRV_EMPTY) &&
                (0U == (zeroization_status & MRAM_PRV_ZEROIZING)))
            {
                break;
            }
            if (0U != wait)
            {
                wait--;
            }
            else if (FSP_SUCCESS == err)
            {
                /* Code MRAM has no forced stop. Drain in RAM before restoring caches/IRQs;
                 * a permanently unresponsive sequencer requires an external/watchdog reset.
                 */
                err = FSP_ERR_TIMEOUT;
            }
            __NOP();
        }
        if ((FSP_SUCCESS == err) && (0U != (R_MRAM->MRCPS & MRAM_PRV_ERRORS)))
        {
            err = FSP_ERR_WRITE_FAILED;
        }
        source += count;
        address += count;
        bytes -= count;
    }
    __DSB();
    *p_protect = (uint16_t) (key | protection);
    /* Clear only observed W0C flags, retrying as required by section 60.5.36. */
    for (uint32_t i = 0U; i < p_ctrl->timeout; i++)
    {
        if (0U == (R_MRAM->MRCPS & MRAM_PRV_ERRORS))
        {
            break;
        }
        R_MRAM->MRCPS = 0U;
    }
    __DSB();
#if BSP_CFG_CPU_CORE == 1
    R_CACHE->CCACTL = ccache;
    R_CACHE->SCACTL = scache;
#else
 #if defined(__ICACHE_PRESENT) && (__ICACHE_PRESENT == 1U)
    SCB_InvalidateICache();
 #endif
 #if defined(__DCACHE_PRESENT) && (__DCACHE_PRESENT == 1U)
    if (0U != dcache)
    {
        SCB_EnableDCache();
    }
 #endif
#endif
    R_MRAM->MRCPFB = prefetch;
    __DSB();
    __ISB();
    p_ctrl->busy = false;
    __set_PRIMASK(primask);
    return err;
#endif
}

#if !BSP_TZ_NONSECURE_BUILD
/* HM60.7.4.3 requires ready, unlocked and a verified MENTRYR readback. No
 * operation here cancels an active command or guesses its maximum duration.
 */
static fsp_err_t r_mram_read_mode (mram_instance_ctrl_t * p_ctrl)
{
    FSP_ERROR_RETURN((0U != (R_MRAM->MSTATR & MRAM_PRV_READY)) &&
                     (0U == (R_MRAM->MREZS & MRAM_PRV_ZEROIZING)) &&
                     (0U == (R_MRAM->MCTRSTATR & 1U)) &&
                     (0U == (R_MRAM->MRCPS & (MRAM_PRV_BUSY | MRAM_PRV_FULL))), FSP_ERR_IN_USE);
    if (0U != R_MRAM->MENTRYR)
    {
        if (0U != (R_MRAM->MASTAT & 0x18U))
        {
            *((volatile uint8_t *) (uintptr_t) 0x40120000UL) = 0x50U;
            __DSB();
            FSP_ERROR_RETURN((0U == (R_MRAM->MASTAT & 0x18U)) &&
                             (0U == (R_MRAM->MSTATR & MRAM_PRV_EXTRA_ERRORS)), FSP_ERR_WRITE_FAILED);
        }
        R_MRAM->MENTRYR = 0xAA00U;
        __DSB();
    }
    FSP_ERROR_RETURN((0U == R_MRAM->MENTRYR) && (0U == (R_MRAM->MASTAT & 0x18U)) &&
                     (0U == (R_MRAM->MREZS & MRAM_PRV_ZEROIZING)), FSP_ERR_WRITE_FAILED);
    p_ctrl->extra_recovery_required = false;
    p_ctrl->busy = false;
    return FSP_SUCCESS;
}
#endif

static fsp_err_t r_mram_extra_check (mram_instance_ctrl_t * p_ctrl, bool irreversible)
{
    mram_extended_cfg_t const * p_extend = (mram_extended_cfg_t const *) p_ctrl->p_cfg->p_extend;
    FSP_ERROR_RETURN(p_extend->enable_extra_commands, FSP_ERR_NOT_ENABLED);
#if BSP_TZ_NONSECURE_BUILD
    FSP_PARAMETER_NOT_USED(irreversible);
    return FSP_ERR_UNSUPPORTED;
#else
    /* HM70.16/TU 2026-02-06 disagree on maximum command times. An uncalibrated
     * polling budget cannot authorize an irreversible command or its Forced Stop.
     */
    FSP_ERROR_RETURN(!irreversible, FSP_ERR_UNSUPPORTED);
    FSP_ERROR_RETURN(!p_ctrl->busy && (0U == (R_MRAM->MRCPS & (MRAM_PRV_BUSY | MRAM_PRV_FULL))) &&
                     (0U != (R_MRAM->MSTATR & MRAM_PRV_READY)) && (0U == (R_MRAM->MREZS & MRAM_PRV_ZEROIZING)) &&
                     (0U == (R_MRAM->MCTRSTATR & 1U)) && (0U == R_MRAM->MENTRYR), FSP_ERR_IN_USE);
    return FSP_SUCCESS;
#endif
}

static fsp_err_t r_mram_counter_select (flash_arc_t counter, uint8_t * p_select)
{
    FSP_ERROR_RETURN((uint32_t) counter <= (uint32_t) FLASH_ARC_NSEC_3, FSP_ERR_INVALID_ARGUMENT);
#if !BSP_TZ_NONSECURE_BUILD
    if (counter >= FLASH_ARC_NSEC_0)
    {
        uint16_t config = *((uint16_t const volatile *) (uintptr_t) 0x02E17932UL) & 3U;
        FSP_ERROR_RETURN(config <= 1U, FSP_ERR_NOT_ENABLED);
        FSP_ERROR_RETURN((0U == config) || (FLASH_ARC_NSEC_0 == counter), FSP_ERR_INVALID_ARGUMENT);
    }
#endif
    *p_select = (uint8_t) ((counter <= FLASH_ARC_OEMBL) ? (uint32_t) counter + 1U : (uint32_t) counter + 2U);
    return FSP_SUCCESS;
}

static fsp_err_t r_mram_extra (mram_instance_ctrl_t * p_ctrl, uint8_t command, uint8_t counter,
                              uint16_t const * p_data, uint32_t * p_low, uint32_t * p_high)
{
#if BSP_TZ_NONSECURE_BUILD
    FSP_PARAMETER_NOT_USED(p_ctrl);
    FSP_PARAMETER_NOT_USED(command);
    FSP_PARAMETER_NOT_USED(counter);
    FSP_PARAMETER_NOT_USED(p_data);
    FSP_PARAMETER_NOT_USED(p_low);
    FSP_PARAMETER_NOT_USED(p_high);
    return FSP_ERR_UNSUPPORTED;
#else
    uintptr_t pc = (uintptr_t) r_mram_extra;
    FSP_ERROR_RETURN(!((pc >= MRAM_PRV_BASE) && (pc - MRAM_PRV_BASE < MRAM_PRV_SIZE)) &&
                     !((pc >= MRAM_PRV_NS_BASE) && (pc - MRAM_PRV_NS_BASE < MRAM_PRV_SIZE)),
                     FSP_ERR_INVALID_LINKED_ADDRESS);
    if (0x50U == command)
    {
        FSP_ERROR_RETURN(p_ctrl->extra_recovery_required, FSP_ERR_INVALID_STATE);
        uint32_t recovery_primask = __get_PRIMASK();
        __disable_irq();
        fsp_err_t recovery_err = r_mram_read_mode(p_ctrl);
        __set_PRIMASK(recovery_primask);
        return recovery_err;
    }
    uint32_t primask = __get_PRIMASK();
    __disable_irq();
    uint8_t zeroization = R_MRAM->MREZS;
    if (p_ctrl->busy || (0U == (R_MRAM->MSTATR & MRAM_PRV_READY)) ||
        (0U != (R_MRAM->MRCPS & (MRAM_PRV_BUSY | MRAM_PRV_FULL))) ||
        (0U != (zeroization & MRAM_PRV_ZEROIZING)) ||
        (0U != (R_MRAM->MCTRSTATR & 1U)) || (0U != R_MRAM->MENTRYR))
    {
        __set_PRIMASK(primask);
        return FSP_ERR_IN_USE;
    }
    p_ctrl->busy = true;
    fsp_err_t err = FSP_SUCCESS;
    if (0x66U == command)
    {
        R_MRAM->MSUACR = (uint16_t) (0x6600U | counter);
        __DSB();
        __ISB();
        p_ctrl->busy = false;
        __set_PRIMASK(primask);
        return FSP_SUCCESS;
    }
    if (0x40U == command)
    {
        /* SAS2/3 overrides BTFLG. Preserve that effective mapping until reset. */
        uint16_t selection = (uint16_t) (R_MRAM->MSUACR & 3U);
        if (0U == (selection & 2U))
        {
            selection = (R_MRAM->MSUASMON >> 31U) ? 2U : 3U;
        }
        R_MRAM->MSUACR = (uint16_t) (0x6600U | selection);
        __DSB();
        __ISB();
    }
    volatile uint8_t * p_command = (volatile uint8_t *) (uintptr_t) 0x40120000UL;
    p_ctrl->extra_recovery_required = true;
    R_MRAM->MENTRYR = 0xAA80U;
    __DSB();
    if (0U == (R_MRAM->MENTRYR & 0x80U))
    {
        err = FSP_ERR_WRITE_FAILED;
    }
    if ((FSP_SUCCESS == err) && (0U != (R_MRAM->MASTAT & 0x18U)))
    {
        *p_command = 0x50U;
        __DSB();
        if (0U != (R_MRAM->MASTAT & 0x18U))
        {
            err = FSP_ERR_WRITE_FAILED;
        }
    }
    if (FSP_SUCCESS == err)
    {
        if (0x40U == command)
        {
            R_MRAM->MSADDR = 0x02C9F070UL;
            *p_command = command;
            *p_command = 8U;
            for (uint32_t i = 0U; i < 8U; i++)
            {
                *((volatile uint16_t *) p_command) = p_data[i];
            }
        }
        else
        {
            R_MRAM->MCNTSELR = counter;
            *p_command = command;
        }
        *p_command = 0xD0U;
        __DSB();
        uint32_t wait = p_ctrl->timeout;
        while ((0U == (R_MRAM->MSTATR & MRAM_PRV_READY)) && (0U != wait))
        {
            wait--;
            __NOP();
        }
        if (0U == (R_MRAM->MSTATR & MRAM_PRV_READY))
        {
            err = FSP_ERR_TIMEOUT;
        }
        else if ((0U != (R_MRAM->MSTATR & MRAM_PRV_EXTRA_ERRORS)) ||
                 (0U != (R_MRAM->MASTAT & 0x18U)) ||
                 (0U != ((R_MRAM->MREZS ^ zeroization) & (MRAM_PRV_ZEROIZING | MRAM_PRV_NOT_ZEROIZED))))
        {
            err = FSP_ERR_WRITE_FAILED;
        }
        else if (0x39U == command)
        {
            *p_low = R_MRAM->MCNTDTR0;
            *p_high = R_MRAM->MCNTDTR1;
        }
    }
    /* A polling budget is not an elapsed-time guarantee. Never force-stop an
     * irreversible command on that basis; Reset can retry read-mode recovery
     * after hardware completes. Until then the instance remains busy.
     */
    fsp_err_t recovery_err = r_mram_read_mode(p_ctrl);
    if (FSP_SUCCESS == err)
    {
        err = recovery_err;
    }
    __set_PRIMASK(primask);
    return err;
#endif
}
