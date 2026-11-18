/*
 * Copyright (c) 2026 Renesas Electronics Corporation and/or its affiliates
 * SPDX-License-Identifier: BSD-3-Clause
 */
#ifndef R_MRAM_H
#define R_MRAM_H

#include "bsp_api.h"
#include "r_mram_cfg.h"
#include "r_flash_api.h"

FSP_HEADER

/** @addtogroup MRAM
 * @{
 * Blocking code-MRAM programming. Open and CallbackSet retain instance-owned callback
 * state for the flash interface; no operation invokes completion callbacks or supports BGO.
 * Reserve the entire writable window outside all
 * images, vectors and live data, including the other core's image. Only one core
 * or bus master may own MRAM programming. NMI handlers/vectors must be in RAM.
 * The linker must copy .code_in_ram before any modifying API is called.
 * W-HUK zeroization can interrupt programming: a failed destination is undefined
 * and must not be read or executed until it has been successfully reprogrammed.
 * Direct non-secure status, read/blank-check and modifying operations are rejected:
 * the mandatory zeroization interlock is secure-only. Use an authorized secure instance.
 * Counter increment and permanent startup selection require calibrated command timing
 * unavailable from the conflicting published maxima, and return FSP_ERR_UNSUPPORTED
 * before touching hardware even when extra commands are enabled. Temporary startup
 * selection and counter reads remain available to an authorized secure instance.
 * A counter-read polling timeout retains busy state until Reset confirms completion
 * and recovers extra read mode; a permanently unresponsive sequencer requires reset.
 */
typedef struct st_mram_extended_cfg
{
    uint32_t write_window_start;       ///< Code MRAM address; start == end disables writes.
    uint32_t write_window_end;         ///< Exclusive end, in the same alias as start.
    uint32_t timeout;                  ///< Observation poll budget, not elapsed time; never authorizes Forced Stop.
    bool     enable_extra_commands;    ///< Opt-in for secure counter reads/temporary startup selection; not irreversible commands.
} mram_extended_cfg_t;

typedef struct st_mram_instance_ctrl
{
    uint32_t open;
    flash_cfg_t const * p_cfg;
    void (* p_callback)(flash_callback_args_t * p_args);
    void const * p_context;
    flash_callback_args_t * p_callback_memory;
    uint32_t window_start;             ///< Physical offset, independent of security alias.
    uint32_t window_end;
    uint32_t timeout;
    volatile bool busy;
    bool extra_recovery_required;       ///< Retained extra-mode fault; Reset retries only after hardware is ready.
} mram_instance_ctrl_t;

extern flash_api_t const g_flash_on_mram;

fsp_err_t R_MRAM_Open(flash_ctrl_t * const p_ctrl, flash_cfg_t const * const p_cfg);
fsp_err_t R_MRAM_Write(flash_ctrl_t * const p_ctrl, uint32_t const src_address,
                       uint32_t const flash_address, uint32_t const num_bytes);
fsp_err_t R_MRAM_Erase(flash_ctrl_t * const p_ctrl, uint32_t const address, uint32_t const num_blocks);
fsp_err_t R_MRAM_BlankCheck(flash_ctrl_t * const p_ctrl, uint32_t const address, uint32_t const num_bytes,
                            flash_result_t * const p_blank_check_result);
fsp_err_t R_MRAM_InfoGet(flash_ctrl_t * const p_ctrl, flash_info_t * const p_info);
fsp_err_t R_MRAM_Close(flash_ctrl_t * const p_ctrl);
fsp_err_t R_MRAM_StatusGet(flash_ctrl_t * const p_ctrl, flash_status_t * const p_status);
fsp_err_t R_MRAM_AccessWindowSet(flash_ctrl_t * const p_ctrl, uint32_t const start_addr, uint32_t const end_addr);
fsp_err_t R_MRAM_AccessWindowClear(flash_ctrl_t * const p_ctrl);
fsp_err_t R_MRAM_IdCodeSet(flash_ctrl_t * const p_ctrl, uint8_t const * const p_id_bytes, flash_id_code_mode_t mode);
fsp_err_t R_MRAM_Reset(flash_ctrl_t * const p_ctrl);
fsp_err_t R_MRAM_UpdateFlashClockFreq(flash_ctrl_t * const p_ctrl);
fsp_err_t R_MRAM_StartUpAreaSelect(flash_ctrl_t * const p_ctrl, flash_startup_area_swap_t swap_type,
                                  bool is_temporary);
fsp_err_t R_MRAM_BankSwap(flash_ctrl_t * const p_ctrl);
fsp_err_t R_MRAM_CallbackSet(flash_ctrl_t * const p_ctrl, void (* p_callback)(flash_callback_args_t *),
                             void const * const p_context, flash_callback_args_t * const p_callback_memory);
fsp_err_t R_MRAM_AntiRollbackCounterIncrement(flash_ctrl_t * const p_ctrl, flash_arc_t counter);
fsp_err_t R_MRAM_AntiRollbackCounterRefresh(flash_ctrl_t * const p_ctrl, flash_arc_t counter);
fsp_err_t R_MRAM_AntiRollbackCounterRead(flash_ctrl_t * const p_ctrl, flash_arc_t counter, uint32_t * const p_count);
fsp_err_t R_MRAM_UserLockableAreaWrite(flash_ctrl_t * const p_ctrl, uint32_t const src_address,
                                      uint32_t const flash_address, uint32_t const num_bytes);

/** @} */
FSP_FOOTER
#endif
