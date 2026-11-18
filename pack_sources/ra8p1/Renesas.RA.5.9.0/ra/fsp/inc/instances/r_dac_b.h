/*
 * Copyright (c) 2026 Renesas Electronics Corporation and/or its affiliates
 * SPDX-License-Identifier: BSD-3-Clause
 */
#ifndef R_DAC_B_H
#define R_DAC_B_H
#include "bsp_api.h"
#include "r_dac_b_cfg.h"
#include "r_dac_api.h"

FSP_HEADER

/** @addtogroup DAC_B
 * @{
 * Each unit has one output. Channel 0 is DAC120/DA0, channel 1 DAC121/DA1.
 * VREFH is external; voltage_mode must agree with the applied reference.
 * Calibration transfer and each unit must have exclusive single-core ownership.
 * Applications must use one control block per unit; distinct controls cannot share a unit.
 * The MDF detects duplicates within a project only, not ownership across cores/projects.
 * The application must reserve disjoint units or assign both units to one core for collective operation.
 */
typedef enum e_dac_b_voltage_mode
{
    DAC_B_VOLTAGE_NORMAL = 0,           ///< VREFH >= 2.7 V.
    DAC_B_VOLTAGE_LOW = 1               ///< VREFH < 2.7 V.
} dac_b_voltage_mode_t;

typedef enum e_dac_b_output
{
    DAC_B_OUTPUT_PIN = 0,
    DAC_B_OUTPUT_INTERNAL = 1          ///< Comparator/ADC16H; no simultaneous pin output.
} dac_b_output_t;

typedef enum e_dac_b_trigger
{
    DAC_B_TRIGGER_SOFTWARE = 0,
    DAC_B_TRIGGER_ELC = 1              ///< Configure ELC_DA0/DA1 separately; quiesce before Stop/Close.
} dac_b_trigger_t;

struct st_dac_b_instance_ctrl;
typedef struct st_dac_b_extended_cfg
{
    dac_data_format_t data_format;
    dac_b_voltage_mode_t voltage_mode;
    dac_b_output_t output;
    dac_b_trigger_t trigger;
    struct st_dac_b_instance_ctrl * p_pair; ///< Reciprocal peer for collective DAE start/stop, NULL for individual.
    uint32_t timeout;                      ///< Maximum calibration polling iterations, nonzero.
    bool calibration_preloaded;            ///< Secure startup already transferred coefficient list 1.
} dac_b_extended_cfg_t;

typedef struct st_dac_b_instance_ctrl
{
    uint32_t open;
    R_DAC_B0_Type * p_reg;
    dac_cfg_t const * p_cfg;
    uint16_t sample;
    bool started;
} dac_b_instance_ctrl_t;

extern dac_api_t const g_dac_on_dac_b;
fsp_err_t R_DAC_B_Open(dac_ctrl_t * const p_ctrl, dac_cfg_t const * const p_cfg);
fsp_err_t R_DAC_B_Close(dac_ctrl_t * const p_ctrl);
fsp_err_t R_DAC_B_Write(dac_ctrl_t * const p_ctrl, uint16_t value);
fsp_err_t R_DAC_B_Start(dac_ctrl_t * const p_ctrl);
fsp_err_t R_DAC_B_Stop(dac_ctrl_t * const p_ctrl);

/** @} */
FSP_FOOTER
#endif
