/*
* Copyright (c) 2026 Renesas Electronics Corporation and/or its affiliates
*
* SPDX-License-Identifier: BSD-3-Clause
*/

/*******************************************************************************************************************//**
 * @addtogroup PDM
 * @{
 **********************************************************************************************************************/
#ifndef R_PDM_H
#define R_PDM_H

#include "bsp_api.h"
#include "r_pdm_cfg.h"
#include "r_pdm_api.h"

FSP_HEADER

/** Input selection is relative to the processing channel, not the physical microphone connector. */
typedef enum e_pdm_input
{
    PDM_INPUT_RISING          = 0,      ///< Rising edge of this channel's physical input
    PDM_INPUT_PREVIOUS_FALLING = 1,      ///< Falling edge of previous physical input (channel 0 wraps to input 2)
} pdm_input_t;

/** Hardware FIFO format. Every sample occupies a uint32_t, with sign extension only through bit 19. */
typedef enum e_pdm_sample_format
{
    PDM_SAMPLE_FORMAT_20_BITS       = 0,
    PDM_SAMPLE_FORMAT_20_BITS_SHIFT1 = 1,
    PDM_SAMPLE_FORMAT_20_BITS_SHIFT2 = 2,
    PDM_SAMPLE_FORMAT_20_BITS_SHIFT3 = 3,
    PDM_SAMPLE_FORMAT_16_BITS_18_4   = 8,
    PDM_SAMPLE_FORMAT_16_BITS_17_3   = 9,
    PDM_SAMPLE_FORMAT_16_BITS_16_2   = 10,
    PDM_SAMPLE_FORMAT_16_BITS_15_1   = 11,
    PDM_SAMPLE_FORMAT_16_BITS_14_0   = 12,
} pdm_sample_format_t;

/** Optional filter coefficients. NULL selects the documented reset coefficients, rewritten on every Open. */
typedef struct st_pdm_coefficients
{
    uint16_t high_pass[4];              ///< s(0), k(1), h(0), h(1), signed Q14 encodings
    uint16_t compensation[11];          ///< h(0)..h(10), signed 13-bit Q11 encodings (upper bits zero)
    uint16_t low_pass[21];              ///< h0(10), h1(0)..h1(19), signed 13-bit Q11 encodings
} pdm_coefficients_t;

/** Hardware settings accessed through pdm_cfg_t::p_extend. Immutable while open.
 * Falling-input stereo requires the previous physical channel to be opened first in rising mode
 * and remain filtering. SFMD, SINCDEC/SINCRNG and FIFO threshold must match (HM table 50.18);
 * shifts, word format and coefficients may differ. Filter bypass modes are not exposed by this IP.
 * Open and Start validate the source registers even with parameter checking disabled. Stop/Close
 * the falling consumer before its source. A source ERROR forcibly stops its clock; the application
 * must stop the consumer before recovering the source. All channels belong to one exclusive core. */
typedef struct st_pdm_extended_cfg
{
    pdm_input_t         input;
    pdm_sample_format_t sample_format;
    uint8_t             clock_div;      ///< CKDIV encoding 0..15: MOCO / (2 * (clock_div + 1))
    uint8_t             sinc_order;     ///< 1..4. Decimation/clip are selected from HM table 50.7.
    uint8_t             high_pass_shift;///< 0..3
    uint8_t             compensation_shift; ///< 0..3
    uint8_t             low_pass_shift; ///< 0..3
    uint8_t             fifo_threshold; ///< DATRITHR encoding 0..4 (1,2,4,8,16 words)
    pdm_coefficients_t const * p_coefficients;
    uint32_t microphone_delay_us;       ///< Additional microphone startup/settling time from its datasheet
    uint32_t error_enable;              ///< OR of pdm_error_t. FIFO overflow detection is always enabled.
    uint16_t short_circuit_low;         ///< 13-bit consecutive-zero limit
    uint16_t short_circuit_high;        ///< 13-bit consecutive-one limit
    uint32_t lower_limit;               ///< Signed 20-bit raw encoding, upper bits zero
    uint32_t upper_limit;               ///< Signed 20-bit raw encoding, upper bits zero
} pdm_extended_cfg_t;

/** Instance-owned state. Do not modify; initialize to zero before first Open.
 * One instance per processing channel on the exclusively owning core; see pdm_api_t. */
typedef struct st_pdm_instance_ctrl
{
    uint32_t open;
    pdm_cfg_t const * p_cfg;
    R_PDM_CH_Type * p_reg;
    uint32_t * p_buffer;
    uint32_t length;
    volatile uint32_t samples;
    volatile bool active;
    bool filtering;
    void (* p_callback)(pdm_callback_args_t * p_args);
    pdm_callback_args_t * p_callback_memory;
    void const * p_context;
} pdm_instance_ctrl_t;

extern pdm_api_t const g_pdm_on_pdm;

fsp_err_t R_PDM_Open(pdm_ctrl_t * const p_ctrl, pdm_cfg_t const * const p_cfg);
/** Finite capture; aligned uint32_t buffer and positive sample count, multiple of FIFO threshold.
 * Ownership returns on COMPLETE/ERROR or Stop; no cyclic overwrite is performed. IRQ callback is optional.
 * FIFO data predating Start is discarded. Callers must not access the active buffer or change clocks while open. */
fsp_err_t R_PDM_Start(pdm_ctrl_t * const p_ctrl, uint32_t * const p_buffer, uint32_t const samples);
fsp_err_t R_PDM_Stop(pdm_ctrl_t * const p_ctrl);
fsp_err_t R_PDM_StatusGet(pdm_ctrl_t * const p_ctrl, pdm_status_t * const p_status);
fsp_err_t R_PDM_Close(pdm_ctrl_t * const p_ctrl);
fsp_err_t R_PDM_CallbackSet(pdm_ctrl_t * const p_ctrl, void (* p_callback)(pdm_callback_args_t *),
                            void const * const p_context, pdm_callback_args_t * const p_callback_memory);

FSP_FOOTER
#endif
/*******************************************************************************************************************//**
 * @} (end defgroup PDM)
 **********************************************************************************************************************/
