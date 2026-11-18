/*
 * Copyright (c) 2026 Renesas Electronics Corporation and/or its affiliates
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include "r_dac_b.h"

#define DAC_B_OPEN            (0x44414342UL)
#define DAC_B_PRV_ENABLE      (1UL)
#define DAC_B_PRV_COLLECTIVE  (1UL << 15U)
#define DAC_B_PRV_INTERNAL    (1UL << 31U)
#define DAC_B_PRV_FORMAT      (1UL << 16U)
#define DAC_B_PRV_LOW_VOLT    (1UL << 8U)

#if DAC_B_CFG_PARAM_CHECKING_ENABLE
 #define DAC_B_PRV_CHECK(p)                        \
    FSP_ASSERT(NULL != (p));                       \
    FSP_ERROR_RETURN(DAC_B_OPEN == (p)->open, FSP_ERR_NOT_OPEN)
#else
 #define DAC_B_PRV_CHECK(p)
#endif

static fsp_err_t r_dac_b_calibrate(uint32_t timeout);
static fsp_err_t r_dac_b_pair_check(dac_b_instance_ctrl_t * p_ctrl, dac_b_instance_ctrl_t * p_pair);
static void r_dac_b_prepare(dac_b_instance_ctrl_t * p_ctrl);
static void r_dac_b_output(dac_b_instance_ctrl_t * p_ctrl);

const dac_api_t g_dac_on_dac_b =
{
    .open = R_DAC_B_Open,
    .close = R_DAC_B_Close,
    .write = R_DAC_B_Write,
    .start = R_DAC_B_Start,
    .stop = R_DAC_B_Stop,
};

/** @addtogroup DAC_B
 * @{ */

/** Implements dac_api_t::open. Leaves conversion disabled until Start or the selected ELC event.
 * @retval FSP_SUCCESS Initialized.
 * @retval FSP_ERR_ASSERTION NULL parameter or extended configuration.
 * @retval FSP_ERR_ALREADY_OPEN Control block already open.
 * @retval FSP_ERR_IP_CHANNEL_NOT_PRESENT Unit not present.
 * @retval FSP_ERR_INVALID_ARGUMENT Invalid format, voltage, output, trigger, pair or polling budget.
 * @retval FSP_ERR_UNSUPPORTED ADC synchronization requested, or nonsecure calibration not preloaded.
 * @retval FSP_ERR_IN_USE MRAM programming/configuration transfer active.
 * @retval FSP_ERR_TIMEOUT Coefficient transfer timed out.
 * @retval FSP_ERR_INVALID_STATE Coefficient transfer interrupted by W-HUK zeroing.
 */
fsp_err_t R_DAC_B_Open (dac_ctrl_t * const p_api_ctrl, dac_cfg_t const * const p_cfg)
{
    dac_b_instance_ctrl_t * p_ctrl = (dac_b_instance_ctrl_t *) p_api_ctrl;
#if DAC_B_CFG_PARAM_CHECKING_ENABLE
    FSP_ASSERT(NULL != p_ctrl);
    FSP_ASSERT(NULL != p_cfg);
    FSP_ASSERT(NULL != p_cfg->p_extend);
    FSP_ERROR_RETURN(DAC_B_OPEN != p_ctrl->open, FSP_ERR_ALREADY_OPEN);
#endif
    /* These checks protect register selection and absent hardware paths even when optional checking is off. */
    FSP_ERROR_RETURN((p_cfg->channel < 32U) &&
                     (0U != (BSP_FEATURE_DAC_B_CHANNEL_MASK & (1UL << p_cfg->channel))),
                     FSP_ERR_IP_CHANNEL_NOT_PRESENT);
    FSP_ERROR_RETURN(!p_cfg->ad_da_synchronized, FSP_ERR_UNSUPPORTED);
    dac_b_extended_cfg_t const * p_extend = (dac_b_extended_cfg_t const *) p_cfg->p_extend;
    FSP_ERROR_RETURN(((uint32_t) p_extend->data_format <= (uint32_t) DAC_DATA_FORMAT_FLUSH_LEFT) &&
                     ((uint32_t) p_extend->voltage_mode <= (uint32_t) DAC_B_VOLTAGE_LOW) &&
                     ((uint32_t) p_extend->output <= (uint32_t) DAC_B_OUTPUT_INTERNAL) &&
                     ((uint32_t) p_extend->trigger <= (uint32_t) DAC_B_TRIGGER_ELC) &&
                     (0U != p_extend->timeout) && (p_extend->p_pair != p_ctrl), FSP_ERR_INVALID_ARGUMENT);
    FSP_ERROR_RETURN((NULL == p_extend->p_pair) || (DAC_B_TRIGGER_SOFTWARE == p_extend->trigger),
                     FSP_ERR_INVALID_ARGUMENT);
    if (!p_extend->calibration_preloaded)
    {
        fsp_err_t err = r_dac_b_calibrate(p_extend->timeout);
        FSP_ERROR_RETURN(FSP_SUCCESS == err, err);
    }
    p_ctrl->p_cfg = p_cfg;
    p_ctrl->p_reg = (0U == p_cfg->channel) ? R_DAC_B0 : R_DAC_B1;
    p_ctrl->sample = 0U;
    p_ctrl->started = false;
    R_BSP_MODULE_START(FSP_IP_DAC, p_cfg->channel);
    r_dac_b_prepare(p_ctrl);
    p_ctrl->open = DAC_B_OPEN;
    return FSP_SUCCESS;
}

/** Implements dac_api_t::write. Optional checking validates unused bits. With checking disabled,
 * the full 16-bit value is written; hardware selects the twelve used bits (HM55.2.1).
 * @retval FSP_SUCCESS Sample stored; conversion uses the configured justification.
 * @retval FSP_ERR_ASSERTION NULL control.
 * @retval FSP_ERR_NOT_OPEN Not open.
 * @retval FSP_ERR_INVALID_ARGUMENT Value exceeds 12 bits or has nonzero low bits in left format.
 */
fsp_err_t R_DAC_B_Write (dac_ctrl_t * const p_api_ctrl, uint16_t value)
{
    dac_b_instance_ctrl_t * p_ctrl = (dac_b_instance_ctrl_t *) p_api_ctrl;
    DAC_B_PRV_CHECK(p_ctrl);
#if DAC_B_CFG_PARAM_CHECKING_ENABLE
    dac_b_extended_cfg_t const * p_extend = (dac_b_extended_cfg_t const *) p_ctrl->p_cfg->p_extend;
    FSP_ERROR_RETURN((DAC_DATA_FORMAT_FLUSH_RIGHT == p_extend->data_format) ? (value <= 0x0FFFU) :
                     (0U == (value & 0x000FU)), FSP_ERR_INVALID_ARGUMENT);
#endif
    p_ctrl->sample = value;
    p_ctrl->p_reg->DADR = value;
    return FSP_SUCCESS;
}

/** Implements dac_api_t::start. Collective mode requires two reciprocally configured open instances.
 * Both units must have matching security attribution for DAE to take effect (HM55.2.2).
 * @retval FSP_SUCCESS Output started, or armed for an externally configured ELC_DAn event.
 * @retval FSP_ERR_ASSERTION NULL control.
 * @retval FSP_ERR_NOT_OPEN Not open.
 * @retval FSP_ERR_IN_USE Already started.
 * @retval FSP_ERR_INVALID_STATE Collective peer not open/reciprocal, or peer already started.
 */
fsp_err_t R_DAC_B_Start (dac_ctrl_t * const p_api_ctrl)
{
    dac_b_instance_ctrl_t * p_ctrl = (dac_b_instance_ctrl_t *) p_api_ctrl;
    DAC_B_PRV_CHECK(p_ctrl);
    FSP_ERROR_RETURN(!p_ctrl->started, FSP_ERR_IN_USE);
    dac_b_extended_cfg_t const * p_extend = (dac_b_extended_cfg_t const *) p_ctrl->p_cfg->p_extend;
    dac_b_instance_ctrl_t * p_pair = p_extend->p_pair;
    if (NULL != p_pair)
    {
        fsp_err_t err = r_dac_b_pair_check(p_ctrl, p_pair);
        FSP_ERROR_RETURN(FSP_SUCCESS == err, err);
        FSP_ERROR_RETURN(!p_pair->started, FSP_ERR_INVALID_STATE);
    }
    if (DAC_B_TRIGGER_ELC == p_extend->trigger)
    {
        p_ctrl->p_reg->DACR0 = (DAC_B_OUTPUT_INTERNAL == p_extend->output) ? DAC_B_PRV_INTERNAL : 0U;
        p_ctrl->p_reg->DADR = p_ctrl->sample;
        p_ctrl->started = true;
        return FSP_SUCCESS;
    }
    r_dac_b_prepare(p_ctrl);
    if (NULL != p_pair)
    {
        r_dac_b_prepare(p_pair);
    }
    p_ctrl->p_reg->DACR0 = DAC_B_PRV_INTERNAL |
                          ((NULL == p_pair) ? DAC_B_PRV_ENABLE : DAC_B_PRV_COLLECTIVE);
    p_ctrl->started = true;
    /* Worst-case low-voltage preparation time covers both units of a collective start. */
    R_BSP_SoftwareDelay(6U, BSP_DELAY_UNITS_MICROSECONDS);
    r_dac_b_output(p_ctrl);
    if (NULL != p_pair)
    {
        r_dac_b_output(p_pair);
        p_pair->started = true;
    }
    return FSP_SUCCESS;
}

/** Implements dac_api_t::stop. The ELC event producer/link must be quiesced by its owner first.
 * @retval FSP_SUCCESS Conversion disabled (both units in collective mode).
 * @retval FSP_ERR_ASSERTION NULL control.
 * @retval FSP_ERR_NOT_OPEN Not open.
 * @retval FSP_ERR_INVALID_STATE Collective peer was closed or reconfigured.
 */
fsp_err_t R_DAC_B_Stop (dac_ctrl_t * const p_api_ctrl)
{
    dac_b_instance_ctrl_t * p_ctrl = (dac_b_instance_ctrl_t *) p_api_ctrl;
    DAC_B_PRV_CHECK(p_ctrl);
    dac_b_extended_cfg_t const * p_extend = (dac_b_extended_cfg_t const *) p_ctrl->p_cfg->p_extend;
    dac_b_instance_ctrl_t * p_pair = p_extend->p_pair;
    if ((NULL != p_pair) && p_ctrl->started)
    {
        fsp_err_t err = r_dac_b_pair_check(p_ctrl, p_pair);
        FSP_ERROR_RETURN(FSP_SUCCESS == err, err);
        p_pair->p_reg->DACR0 &= ~(DAC_B_PRV_ENABLE | DAC_B_PRV_COLLECTIVE);
        p_pair->started = false;
    }
    p_ctrl->p_reg->DACR0 &= ~(DAC_B_PRV_ENABLE | DAC_B_PRV_COLLECTIVE);
    p_ctrl->started = false;
    return FSP_SUCCESS;
}

/** Implements dac_api_t::close. Stops outputs before module stop; module stop alone retains analog output.
 * @retval FSP_SUCCESS Closed.
 * @retval FSP_ERR_ASSERTION NULL control.
 * @retval FSP_ERR_NOT_OPEN Not open.
 * @retval FSP_ERR_INVALID_STATE Collective peer was closed while conversion was active.
 */
fsp_err_t R_DAC_B_Close (dac_ctrl_t * const p_api_ctrl)
{
    dac_b_instance_ctrl_t * p_ctrl = (dac_b_instance_ctrl_t *) p_api_ctrl;
    DAC_B_PRV_CHECK(p_ctrl);
    fsp_err_t err = R_DAC_B_Stop(p_ctrl);
    FSP_ERROR_RETURN(FSP_SUCCESS == err, err);
    p_ctrl->open = 0U;
    R_BSP_MODULE_STOP(FSP_IP_DAC, p_ctrl->p_cfg->channel);
    return FSP_SUCCESS;
}

/** @} */

static fsp_err_t r_dac_b_pair_check (dac_b_instance_ctrl_t * p_ctrl, dac_b_instance_ctrl_t * p_pair)
{
    FSP_ERROR_RETURN((DAC_B_OPEN == p_pair->open) && (p_pair->p_cfg->channel != p_ctrl->p_cfg->channel),
                     FSP_ERR_INVALID_STATE);
    dac_b_extended_cfg_t const * p_extend = (dac_b_extended_cfg_t const *) p_pair->p_cfg->p_extend;
    FSP_ERROR_RETURN((p_extend->p_pair == p_ctrl) && (DAC_B_TRIGGER_SOFTWARE == p_extend->trigger),
                     FSP_ERR_INVALID_STATE);
    return FSP_SUCCESS;
}

static void r_dac_b_prepare (dac_b_instance_ctrl_t * p_ctrl)
{
    dac_b_extended_cfg_t const * p_extend = (dac_b_extended_cfg_t const *) p_ctrl->p_cfg->p_extend;
    p_ctrl->p_reg->DACR0 = DAC_B_PRV_INTERNAL;
    p_ctrl->p_reg->DACR1 = (DAC_DATA_FORMAT_FLUSH_LEFT == p_extend->data_format) ? DAC_B_PRV_FORMAT : 0U;
    p_ctrl->p_reg->DACR2 = (DAC_B_VOLTAGE_LOW == p_extend->voltage_mode) ? DAC_B_PRV_LOW_VOLT : 0U;
    uint16_t initial = (DAC_B_VOLTAGE_LOW == p_extend->voltage_mode) ? 0x01F8U : 0x00E0U;
    if (DAC_DATA_FORMAT_FLUSH_LEFT == p_extend->data_format)
    {
        initial = (uint16_t) (initial << 4U);
    }
    p_ctrl->p_reg->DADR = initial;
    R_BSP_SoftwareDelay(1U, BSP_DELAY_UNITS_MICROSECONDS); /* tSU >= 4 ns. */
}

static void r_dac_b_output (dac_b_instance_ctrl_t * p_ctrl)
{
    dac_b_extended_cfg_t const * p_extend = (dac_b_extended_cfg_t const *) p_ctrl->p_cfg->p_extend;
    if (DAC_B_OUTPUT_PIN == p_extend->output)
    {
        p_ctrl->p_reg->DACR0 &= ~DAC_B_PRV_INTERNAL;
        R_BSP_SoftwareDelay(6U, BSP_DELAY_UNITS_MICROSECONDS);
    }
    p_ctrl->p_reg->DADR = p_ctrl->sample;
    R_BSP_SoftwareDelay(6U, BSP_DELAY_UNITS_MICROSECONDS);
}

static fsp_err_t r_dac_b_calibrate (uint32_t timeout)
{
#if BSP_TZ_NONSECURE_BUILD
    FSP_PARAMETER_NOT_USED(timeout);
    return FSP_ERR_UNSUPPORTED;
#else
    fsp_err_t err = FSP_SUCCESS;
    FSP_CRITICAL_SECTION_DEFINE;
    FSP_CRITICAL_SECTION_ENTER;
    if ((0U != R_MRAM->MENTRYR) || (0U != (R_MRAM->MCTRSTATR & 5U)) ||
        (0U != (R_MRAM->MREZS & 2U)) || (0U == (R_MRAM->MSTATR & 0x8000U)) ||
        (0U != (R_MRAM->MRCPS & 0xC0U)))
    {
        err = FSP_ERR_IN_USE;
    }
    else
    {
        uint8_t list = R_MRAM->MCTRLSR;
        R_MRAM->MCTRLSR = 1U;
        R_MRAM->MCTRCNTR = 0x4501U;
        __DSB();
        while ((0U != (R_MRAM->MCTRSTATR & 1U)) && (0U != timeout))
        {
            timeout--;
            __NOP();
        }
        /* TRBUSY can clear during the final polling iteration. */
        if (0U != (R_MRAM->MCTRSTATR & 1U))
        {
            err = FSP_ERR_TIMEOUT;
        }
        else
        {
            R_MRAM->MCTRLSR = list;
            if (0U != (R_MRAM->MREZS & 2U))
            {
                err = FSP_ERR_INVALID_STATE;
            }
        }
    }
    FSP_CRITICAL_SECTION_EXIT;
    return err;
#endif
}
