/*
 * Copyright (c) 2026 Renesas Electronics Corporation and/or its affiliates
 * SPDX-License-Identifier: BSD-3-Clause
 */
#ifndef R_PDM_API_H
#define R_PDM_API_H

#include "bsp_api.h"

FSP_HEADER

/** @addtogroup PDM_API
 * @{ */

/** Event delivered from interrupt context. Only StatusGet and a new Start after COMPLETE are callback-safe. */
typedef enum e_pdm_event
{
    PDM_EVENT_COMPLETE = 0,
    PDM_EVENT_ERROR    = 1,
} pdm_event_t;

/** Capture error flags returned by the driver. */
typedef enum e_pdm_error
{
    PDM_ERROR_SHORT_CIRCUIT = 0x00010000U,
    PDM_ERROR_LOWER_LIMIT   = 0x00020000U,
    PDM_ERROR_UPPER_LIMIT   = 0x00040000U,
    PDM_ERROR_FIFO_OVERFLOW = 0x08000000U,
} pdm_error_t;

typedef struct st_pdm_callback_args
{
    pdm_event_t event;
    uint32_t   error;                   ///< OR of pdm_error_t; zero for COMPLETE.
    uint32_t * p_buffer;                ///< Ownership returned to application; partially valid on error.
    uint32_t   samples;                 ///< Valid uint32_t FIFO words in p_buffer.
    void const * p_context;
} pdm_callback_args_t;

/** Immutable while open. Hardware-specific settings are supplied through p_extend. */
typedef struct st_pdm_cfg
{
    uint8_t   channel;
    IRQn_Type dat_irq;
    IRQn_Type err_irq;
    uint8_t   ipl;                      ///< Data and error IRQs must use the same priority.
    void (* p_callback)(pdm_callback_args_t * p_args);
    void const * p_context;
    void const * p_extend;
} pdm_cfg_t;

typedef struct st_pdm_status
{
    bool     active;                    ///< A buffer is owned by the driver.
    bool     filtering;                 ///< Filters/clock running, also between completed buffers.
    uint32_t samples;
    uint32_t hardware_status;
} pdm_status_t;

typedef void pdm_ctrl_t;

/** Finite capture API. The application assigns the peripheral, shared clock and interrupts exclusively
 * to one core and serializes calls except the documented callback-safe calls. Open detects sequential
 * local duplicate ownership, not atomic reservations or cross-core access.
 * CPU-written buffers need no transfer driver or cache maintenance. */
typedef struct st_pdm_api
{
    fsp_err_t (* open)(pdm_ctrl_t * const p_ctrl, pdm_cfg_t const * const p_cfg);
    /** Aligned positive buffer length must be a multiple of the configured FIFO threshold.
     * Ownership returns on COMPLETE/ERROR or Stop; no cyclic overwrite occurs. Old FIFO data is discarded.
     * Do not access an active buffer or change clocks while open. */
    fsp_err_t (* start)(pdm_ctrl_t * const p_ctrl, uint32_t * const p_buffer, uint32_t const samples);
    fsp_err_t (* stop)(pdm_ctrl_t * const p_ctrl);
    fsp_err_t (* statusGet)(pdm_ctrl_t * const p_ctrl, pdm_status_t * const p_status);
    fsp_err_t (* close)(pdm_ctrl_t * const p_ctrl);
    fsp_err_t (* callbackSet)(pdm_ctrl_t * const p_ctrl, void (* p_callback)(pdm_callback_args_t *),
                              void const * const p_context, pdm_callback_args_t * const p_callback_memory);
} pdm_api_t;

typedef struct st_pdm_instance
{
    pdm_ctrl_t * p_ctrl;
    pdm_cfg_t const * p_cfg;
    pdm_api_t const * p_api;
} pdm_instance_t;

/** @} */
FSP_FOOTER
#endif
