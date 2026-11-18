/*
* Copyright (c) 2026 Renesas Electronics Corporation and/or its affiliates
*
* SPDX-License-Identifier: BSD-3-Clause
*/

/*******************************************************************************************************************//**
 * @addtogroup PDM
 * @{
 **********************************************************************************************************************/
#include "r_pdm.h"

#define PDM_PRV_OPEN             (0x0050444DU)
#define PDM_PRV_ERROR_MASK       (0x08070000U)
#define PDM_PRV_CLEAR_MASK       (0x08070002U)
#define PDM_PRV_FIFO_VALID_WORDS (30U)
#define PDM_PRV_STOP_RETRIES     (10000U)
#define PDM_PRV_STEREO_MODE_MASK (0x03000071U) /* INPSEL, SFMD and SDMAMD (HM 50.2.19). */
#define PDM_PRV_STEREO_SINC_MASK (0x1FFF0000U) /* SINCDEC and SINCRNG; falling CKDIV is unused. */

#if BSP_TZ_SECURE_BUILD
 #define PDM_PRV_NONSECURE_ACCESS CMSE_AU_NONSECURE | CMSE_MPU_READWRITE
 #if defined(__ARMCC_VERSION) || defined(__ICCARM__)
typedef void (BSP_CMSE_NONSECURE_CALL * pdm_prv_ns_callback)(pdm_callback_args_t * p_args);
 #elif defined(__GNUC__)
typedef BSP_CMSE_NONSECURE_CALL void (*volatile pdm_prv_ns_callback)(pdm_callback_args_t * p_args);
 #endif
#endif

/* HM table 50.7: only these decimation/clip combinations are qualified by this driver. */
static uint8_t const g_pdm_decimation[16] = {125, 62, 42, 31, 25, 21, 18, 16, 14, 12, 11, 10, 9, 9, 8, 8};
static uint8_t const g_pdm_range[4][16] =
{
    {26, 27, 27, 28, 28, 28, 28, 28, 29, 29, 29, 29, 29, 29, 29, 29},
    {19, 21, 22, 23, 23, 24, 24, 24, 25, 25, 26, 26, 26, 26, 26, 26},
    {12, 15, 16, 18, 19, 19, 20, 20, 21, 22, 22, 23, 23, 23, 23, 23},
    { 5,  9, 11, 13, 14, 15, 16, 16, 17, 18, 19, 19, 20, 20, 20, 20},
};

/* HM table 50.3 reset coefficients, explicitly restored on reopen (module clock is shared). */
static pdm_coefficients_t const g_pdm_coefficients =
{
    .high_pass = {0x3F61, 0x3EC1, 0x4000, 0xC000},
    .compensation = {0x1FE8, 0x0039, 0x003C, 0x1E56, 0x01DC, 0x06E1,
                     0x01DC, 0x1E56, 0x003C, 0x0039, 0x1FE8},
    .low_pass = {0x0400, 0x1FF8, 0x000A, 0x1FF0, 0x0018, 0x1FDC, 0x0034,
                 0x1FB3, 0x0076, 0x1F2E, 0x0289, 0x0289, 0x1F2E, 0x0076,
                 0x1FB3, 0x0034, 0x1FDC, 0x0018, 0x1FF0, 0x000A, 0x1FF8},
};

static void pdm_coefficients_write(pdm_instance_ctrl_t * p_ctrl);
static void pdm_filter_start(pdm_instance_ctrl_t * p_ctrl);
static fsp_err_t pdm_filter_stop(pdm_instance_ctrl_t * p_ctrl);
static void pdm_call_callback(pdm_instance_ctrl_t * p_ctrl, pdm_callback_args_t * p_args);
static void pdm_buffer_release(pdm_instance_ctrl_t * p_ctrl);
static bool pdm_source_check(pdm_cfg_t const * p_cfg);
#if PDM_CFG_PARAM_CHECKING_ENABLE
static fsp_err_t pdm_open_check(pdm_instance_ctrl_t * p_ctrl, pdm_cfg_t const * p_cfg);
#endif
void pdm_dat_isr(void);
void pdm_err_isr(void);

pdm_api_t const g_pdm_on_pdm =
{
    .open = R_PDM_Open,
    .start = R_PDM_Start,
    .stop = R_PDM_Stop,
    .statusGet = R_PDM_StatusGet,
    .close = R_PDM_Close,
    .callbackSet = R_PDM_CallbackSet,
};

/*******************************************************************************************************************//**
 * Open and start the filter/clock. Implements pdm_api_t::open.
 * @retval FSP_SUCCESS                  Filter initialized; no application buffer is owned.
 * @retval FSP_ERR_ASSERTION            Required pointer is NULL.
 * @retval FSP_ERR_ALREADY_OPEN         This control block is already open.
 * @retval FSP_ERR_IP_CHANNEL_NOT_PRESENT Channel does not exist.
 * @retval FSP_ERR_INVALID_ARGUMENT     Invalid mode, filter, coefficient, limit, or clock configuration.
 * @retval FSP_ERR_IRQ_BSP_DISABLED     A mandatory data/error IRQ is unavailable.
 * @retval FSP_ERR_IN_USE               Channel or IRQ is already owned.
 * @retval FSP_ERR_NO_CALLBACK_MEMORY   Non-secure callback requires CallbackSet after Open with NULL callback.
 **********************************************************************************************************************/
fsp_err_t R_PDM_Open (pdm_ctrl_t * const p_api_ctrl, pdm_cfg_t const * const p_cfg)
{
    pdm_instance_ctrl_t * p_ctrl = (pdm_instance_ctrl_t *) p_api_ctrl;
#if PDM_CFG_PARAM_CHECKING_ENABLE
    fsp_err_t err = pdm_open_check(p_ctrl, p_cfg);
    FSP_ERROR_RETURN(FSP_SUCCESS == err, err);
#endif
    pdm_extended_cfg_t const * p_extend = (pdm_extended_cfg_t const *) p_cfg->p_extend;
    /* Keep register selection, lookup bounds and mandatory IRQs safe when optional checks are disabled. */
    FSP_ERROR_RETURN((p_cfg->channel < 3U) &&
                     (0U != (BSP_FEATURE_PDM_CHANNELS & (1U << p_cfg->channel))), FSP_ERR_IP_CHANNEL_NOT_PRESENT);
    FSP_ERROR_RETURN((p_cfg->dat_irq >= 0) && (p_cfg->err_irq >= 0) &&
                     (p_cfg->dat_irq != p_cfg->err_irq) && (p_cfg->ipl <= 15U), FSP_ERR_IRQ_BSP_DISABLED);
    FSP_ERROR_RETURN((p_extend->sinc_order >= 1U) && (p_extend->sinc_order <= 4U) &&
                     (p_extend->clock_div <= 15U) && (p_extend->fifo_threshold <= 4U), FSP_ERR_INVALID_ARGUMENT);
    uint32_t pclk = R_FSP_SystemClockHzGet(FSP_PRIV_CLOCK_PCLKB);
    FSP_ERROR_RETURN((pclk >= 1000000U) && (pclk <= 62500000U), FSP_ERR_INVALID_ARGUMENT);
    FSP_ERROR_RETURN((NULL == R_FSP_IsrContextGet(p_cfg->dat_irq)) &&
                     (NULL == R_FSP_IsrContextGet(p_cfg->err_irq)), FSP_ERR_IN_USE);
#if BSP_TZ_SECURE_BUILD
    /* Non-secure callbacks need working memory installed by CallbackSet after Open. */
    FSP_ERROR_RETURN((NULL == p_cfg->p_callback) ||
                     (NULL == cmse_check_address_range((void *) p_cfg->p_callback, sizeof(void *),
                                                       CMSE_AU_NONSECURE)), FSP_ERR_NO_CALLBACK_MEMORY);
#endif
    R_BSP_MODULE_START(FSP_IP_PDM, 0);
    R_PDM_CH_Type * p_reg = &R_PDM->CH[p_cfg->channel];
    FSP_ERROR_RETURN(0U == (p_reg->PDSR & R_PDM_CH_PDSR_STATE_Msk), FSP_ERR_IN_USE);
    FSP_ERROR_RETURN(pdm_source_check(p_cfg), FSP_ERR_INVALID_ARGUMENT);

    p_ctrl->p_cfg = p_cfg;
    p_ctrl->p_reg = p_reg;
    p_ctrl->p_buffer = NULL;
    p_ctrl->length = 0U;
    p_ctrl->samples = 0U;
    p_ctrl->active = false;
    p_ctrl->filtering = false;
    p_ctrl->p_callback = p_cfg->p_callback;
    p_ctrl->p_callback_memory = NULL;
    p_ctrl->p_context = p_cfg->p_context;

    p_reg->PDICR = 0U;
    p_reg->PDDRCR = 0U;
    p_reg->PDSDCR = 0U;
    uint32_t order = (uint32_t) p_extend->sinc_order & 3U;
    p_reg->PDMDSR = (uint32_t) p_extend->input | (order << R_PDM_CH_PDMDSR_SFMD_Pos) |
                   ((uint32_t) p_extend->high_pass_shift << R_PDM_CH_PDMDSR_HFIS_Pos) |
                   ((uint32_t) p_extend->compensation_shift << R_PDM_CH_PDMDSR_CFIS_Pos) |
                   ((uint32_t) p_extend->low_pass_shift << R_PDM_CH_PDMDSR_LFIS_Pos) |
                   ((uint32_t) p_extend->sample_format << R_PDM_CH_PDMDSR_DBIS_Pos);
    p_reg->PDSFCR = p_extend->clock_div |
                   (((uint32_t) g_pdm_decimation[p_extend->clock_div] - 1U) << R_PDM_CH_PDSFCR_SINCDEC_Pos) |
                   ((uint32_t) g_pdm_range[p_extend->sinc_order - 1U][p_extend->clock_div] <<
                    R_PDM_CH_PDSFCR_SINCRNG_Pos);
    pdm_coefficients_write(p_ctrl);
    p_reg->PDDBCR = p_extend->fifo_threshold;
    p_reg->PDSCTSR = p_extend->short_circuit_low | ((uint32_t) p_extend->short_circuit_high << 16U);
    p_reg->PDOVLTR = p_extend->lower_limit;
    p_reg->PDOVUTR = p_extend->upper_limit;
    pdm_filter_start(p_ctrl);
    R_BSP_IrqCfgEnable(p_cfg->dat_irq, p_cfg->ipl, p_ctrl);
    R_BSP_IrqCfgEnable(p_cfg->err_irq, p_cfg->ipl, p_ctrl);
    p_ctrl->open = PDM_PRV_OPEN;
    return FSP_SUCCESS;
}

/*******************************************************************************************************************//**
 * Begin a finite CPU/interrupt capture. Implements pdm_api_t::start.
 * @retval FSP_SUCCESS               Capture armed.
 * @retval FSP_ERR_ASSERTION         Required pointer is NULL.
 * @retval FSP_ERR_NOT_OPEN          Instance is closed.
 * @retval FSP_ERR_IN_USE            An application buffer is already owned.
 * @retval FSP_ERR_INVALID_ALIGNMENT Buffer is not aligned to uint32_t.
 * @retval FSP_ERR_INVALID_SIZE      Zero, byte-size/address overflow, or not a multiple of FIFO threshold.
 * @retval FSP_ERR_TIMEOUT           Previous stop has not completed.
 * @retval FSP_ERR_INVALID_ARGUMENT  Falling-input source is stopped or no longer matches.
 * @retval FSP_ERR_INVALID_ADDRESS   Non-secure callback cannot access the buffer.
 **********************************************************************************************************************/
fsp_err_t R_PDM_Start (pdm_ctrl_t * const p_api_ctrl, uint32_t * const p_buffer, uint32_t const samples)
{
    pdm_instance_ctrl_t * p_ctrl = (pdm_instance_ctrl_t *) p_api_ctrl;
#if PDM_CFG_PARAM_CHECKING_ENABLE
    FSP_ASSERT(p_ctrl);
    FSP_ASSERT(p_buffer);
    FSP_ERROR_RETURN(PDM_PRV_OPEN == p_ctrl->open, FSP_ERR_NOT_OPEN);
    FSP_ERROR_RETURN(0U == ((uintptr_t) p_buffer & 3U), FSP_ERR_INVALID_ALIGNMENT);
    pdm_extended_cfg_t const * p_extend = (pdm_extended_cfg_t const *) p_ctrl->p_cfg->p_extend;
    FSP_ERROR_RETURN((samples > 0U) && (samples <= UINT32_MAX / sizeof(uint32_t)) &&
                     ((uintptr_t) p_buffer <= UINTPTR_MAX - ((uintptr_t) samples * sizeof(uint32_t))) &&
                     (0U == (samples % (1U << p_extend->fifo_threshold))), FSP_ERR_INVALID_SIZE);
#endif
    FSP_ERROR_RETURN(!p_ctrl->active, FSP_ERR_IN_USE);
    FSP_ERROR_RETURN(pdm_source_check(p_ctrl->p_cfg), FSP_ERR_INVALID_ARGUMENT);
#if BSP_TZ_SECURE_BUILD
    FSP_ERROR_RETURN(!cmse_is_nsfptr(p_ctrl->p_callback) ||
                     (NULL != cmse_check_address_range(p_buffer, samples * sizeof(uint32_t),
                                                        PDM_PRV_NONSECURE_ACCESS)), FSP_ERR_INVALID_ADDRESS);
#endif
    if (!p_ctrl->filtering)
    {
        uint32_t retries = PDM_PRV_STOP_RETRIES;
        while (0U != (p_ctrl->p_reg->PDSR & R_PDM_CH_PDSR_STATE_Msk))
        {
            FSP_ERROR_RETURN(0U != --retries, FSP_ERR_TIMEOUT);
        }
        pdm_filter_start(p_ctrl);
    }
    R_BSP_IrqDisable(p_ctrl->p_cfg->dat_irq);
    R_BSP_IrqDisable(p_ctrl->p_cfg->err_irq);
    p_ctrl->p_buffer = p_buffer;
    p_ctrl->length = samples;
    p_ctrl->samples = 0U;
    p_ctrl->active = true;
    p_ctrl->p_reg->PDSCR = PDM_PRV_CLEAR_MASK;
    p_ctrl->p_reg->PDDRCR = 1U;
    /* HM figure 50.19: DATRE initially exposes 30 old words; discard before enabling interrupts. */
    for (uint32_t i = 0U; i < PDM_PRV_FIFO_VALID_WORDS; i++)
    {
        volatile uint32_t discard = p_ctrl->p_reg->PDDRR;
        FSP_PARAMETER_NOT_USED(discard);
    }
    p_ctrl->p_reg->PDSCR = PDM_PRV_CLEAR_MASK;
    R_BSP_IrqStatusClear(p_ctrl->p_cfg->dat_irq);
    R_BSP_IrqStatusClear(p_ctrl->p_cfg->err_irq);
    p_ctrl->p_reg->PDICR = R_PDM_CH_PDICR_IDRE_Msk | R_PDM_CH_PDICR_IEDE_Msk;
    R_BSP_IrqEnable(p_ctrl->p_cfg->err_irq);
    R_BSP_IrqEnable(p_ctrl->p_cfg->dat_irq);
    return FSP_SUCCESS;
}

/*******************************************************************************************************************//**
 * Stop filtering/capture and return buffer ownership without callback. Implements pdm_api_t::stop.
 * @retval FSP_SUCCESS       Stopped; safe to reuse the buffer.
 * @retval FSP_ERR_ASSERTION Required pointer is NULL.
 * @retval FSP_ERR_NOT_OPEN  Instance is closed.
 * @retval FSP_ERR_IN_USE    Stop the falling-input consumer before its source.
 * @retval FSP_ERR_TIMEOUT   Hardware did not stop; IRQs/data reads are disabled; retry Stop before Close/Start.
 **********************************************************************************************************************/
fsp_err_t R_PDM_Stop (pdm_ctrl_t * const p_api_ctrl)
{
    pdm_instance_ctrl_t * p_ctrl = (pdm_instance_ctrl_t *) p_api_ctrl;
#if PDM_CFG_PARAM_CHECKING_ENABLE
    FSP_ASSERT(p_ctrl);
    FSP_ERROR_RETURN(PDM_PRV_OPEN == p_ctrl->open, FSP_ERR_NOT_OPEN);
#endif
    /* Stop the falling consumer before removing its source clock/data (HM 50.3.5). */
    R_PDM_CH_Type * p_next = &R_PDM->CH[(p_ctrl->p_cfg->channel + 1U) % 3U];
    FSP_ERROR_RETURN((0U != (p_ctrl->p_reg->PDMDSR & 1U)) ||
                     (0U == (p_next->PDSR & R_PDM_CH_PDSR_STATE_Msk)) ||
                     (0U == (p_next->PDMDSR & 1U)), FSP_ERR_IN_USE);
    R_BSP_IrqDisable(p_ctrl->p_cfg->dat_irq);
    R_BSP_IrqDisable(p_ctrl->p_cfg->err_irq);
    return pdm_filter_stop(p_ctrl);
}

/*******************************************************************************************************************//**
 * Read status. Implements pdm_api_t::statusGet.
 * @retval FSP_SUCCESS       Status read.
 * @retval FSP_ERR_ASSERTION Required pointer is NULL.
 * @retval FSP_ERR_NOT_OPEN  Instance is closed.
 **********************************************************************************************************************/
fsp_err_t R_PDM_StatusGet (pdm_ctrl_t * const p_api_ctrl, pdm_status_t * const p_status)
{
    pdm_instance_ctrl_t * p_ctrl = (pdm_instance_ctrl_t *) p_api_ctrl;
#if PDM_CFG_PARAM_CHECKING_ENABLE
    FSP_ASSERT(p_ctrl);
    FSP_ASSERT(p_status);
    FSP_ERROR_RETURN(PDM_PRV_OPEN == p_ctrl->open, FSP_ERR_NOT_OPEN);
#endif
    p_status->active = p_ctrl->active;
    p_status->filtering = p_ctrl->filtering;
    p_status->samples = p_ctrl->samples;
    p_status->hardware_status = p_ctrl->p_reg->PDSR;
    return FSP_SUCCESS;
}

/*******************************************************************************************************************//**
 * Stop and detach both IRQ contexts. Implements pdm_api_t::close. Shared module clock is retained for other channels.
 * @retval FSP_SUCCESS       Closed.
 * @retval FSP_ERR_ASSERTION Required pointer is NULL.
 * @retval FSP_ERR_NOT_OPEN  Instance is closed.
 * @retval FSP_ERR_IN_USE    Close the falling-input consumer before its source.
 * @retval FSP_ERR_TIMEOUT   Hardware did not stop; instance remains open for a retry.
 **********************************************************************************************************************/
fsp_err_t R_PDM_Close (pdm_ctrl_t * const p_api_ctrl)
{
    pdm_instance_ctrl_t * p_ctrl = (pdm_instance_ctrl_t *) p_api_ctrl;
    fsp_err_t err = R_PDM_Stop(p_api_ctrl);
    FSP_ERROR_RETURN(FSP_SUCCESS == err, err);
    p_ctrl->open = 0U;
    R_FSP_IsrContextSet(p_ctrl->p_cfg->dat_irq, NULL);
    R_FSP_IsrContextSet(p_ctrl->p_cfg->err_irq, NULL);
    R_BSP_IrqStatusClear(p_ctrl->p_cfg->dat_irq);
    R_BSP_IrqStatusClear(p_ctrl->p_cfg->err_irq);
    p_ctrl->p_callback = NULL;
    return FSP_SUCCESS;
}

/*******************************************************************************************************************//**
 * Set callback and optional non-secure working memory. Implements pdm_api_t::callbackSet.
 * @retval FSP_SUCCESS                Callback set.
 * @retval FSP_ERR_ASSERTION          Required pointer is NULL.
 * @retval FSP_ERR_NOT_OPEN           Instance is closed.
 * @retval FSP_ERR_IN_USE             Cannot change callback while a buffer is active.
 * @retval FSP_ERR_NO_CALLBACK_MEMORY Non-secure callback memory is missing or not non-secure.
 **********************************************************************************************************************/
fsp_err_t R_PDM_CallbackSet (pdm_ctrl_t * const p_api_ctrl, void (* p_callback)(pdm_callback_args_t *),
                            void const * const p_context, pdm_callback_args_t * const p_callback_memory)
{
    pdm_instance_ctrl_t * p_ctrl = (pdm_instance_ctrl_t *) p_api_ctrl;
#if PDM_CFG_PARAM_CHECKING_ENABLE
    FSP_ASSERT(p_ctrl);
    FSP_ASSERT(p_callback);
    FSP_ERROR_RETURN(PDM_PRV_OPEN == p_ctrl->open, FSP_ERR_NOT_OPEN);
#endif
    FSP_ERROR_RETURN(!p_ctrl->active, FSP_ERR_IN_USE);
#if BSP_TZ_SECURE_BUILD
    bool callback_is_secure =
        (NULL == cmse_check_address_range((void *) p_callback, sizeof(void *), CMSE_AU_NONSECURE));
    pdm_callback_args_t * p_checked = cmse_check_pointed_object(p_callback_memory, PDM_PRV_NONSECURE_ACCESS);
    FSP_ERROR_RETURN(callback_is_secure || (NULL != p_checked), FSP_ERR_NO_CALLBACK_MEMORY);
    p_ctrl->p_callback = callback_is_secure ? p_callback :
                        (void (*)(pdm_callback_args_t *)) cmse_nsfptr_create(p_callback);
#else
    p_ctrl->p_callback = p_callback;
#endif
    p_ctrl->p_context = p_context;
    p_ctrl->p_callback_memory = p_callback_memory;
    return FSP_SUCCESS;
}

#if PDM_CFG_PARAM_CHECKING_ENABLE
static fsp_err_t pdm_open_check (pdm_instance_ctrl_t * p_ctrl, pdm_cfg_t const * p_cfg)
{
    FSP_ASSERT(p_ctrl);
    FSP_ASSERT(p_cfg);
    FSP_ASSERT(p_cfg->p_extend);
    pdm_extended_cfg_t const * p_extend = (pdm_extended_cfg_t const *) p_cfg->p_extend;
    FSP_ERROR_RETURN(PDM_PRV_OPEN != p_ctrl->open, FSP_ERR_ALREADY_OPEN);
    FSP_ERROR_RETURN(((PDM_INPUT_RISING == p_extend->input) || (PDM_INPUT_PREVIOUS_FALLING == p_extend->input)) &&
                     (p_extend->high_pass_shift <= 3U) && (p_extend->compensation_shift <= 3U) &&
                     (p_extend->low_pass_shift <= 3U) &&
                     ((((uint32_t) p_extend->sample_format <= 3U)) ||
                      (((uint32_t) p_extend->sample_format >= 8U) && ((uint32_t) p_extend->sample_format <= 12U))) &&
                     (0U == (p_extend->error_enable & ~PDM_PRV_ERROR_MASK)) &&
                     (p_extend->short_circuit_low <= 0x1FFFU) && (p_extend->short_circuit_high <= 0x1FFFU) &&
                     (p_extend->lower_limit <= 0xFFFFFU) && (p_extend->upper_limit <= 0xFFFFFU) &&
                     (p_extend->microphone_delay_us <= UINT32_MAX - 100000U), FSP_ERR_INVALID_ARGUMENT);
    if (NULL != p_extend->p_coefficients)
    {
        for (uint32_t i = 0U; i < 11U; i++)
        {
            FSP_ERROR_RETURN(p_extend->p_coefficients->compensation[i] <= 0x1FFFU, FSP_ERR_INVALID_ARGUMENT);
        }
        for (uint32_t i = 0U; i < 21U; i++)
        {
            FSP_ERROR_RETURN(p_extend->p_coefficients->low_pass[i] <= 0x1FFFU, FSP_ERR_INVALID_ARGUMENT);
        }
    }
    return FSP_SUCCESS;
}
#endif

static void pdm_coefficients_write (pdm_instance_ctrl_t * p_ctrl)
{
    pdm_extended_cfg_t const * p_extend = (pdm_extended_cfg_t const *) p_ctrl->p_cfg->p_extend;
    pdm_coefficients_t const * p_c = p_extend->p_coefficients;
    if (NULL == p_c)
    {
        p_c = &g_pdm_coefficients;
    }
    p_ctrl->p_reg->PDHFCS0R = p_c->high_pass[0];
    p_ctrl->p_reg->PDHFCK1R = p_c->high_pass[1];
    p_ctrl->p_reg->PDHFCH0R = p_c->high_pass[2];
    p_ctrl->p_reg->PDHFCH1R = p_c->high_pass[3];
#define PDM_PRV_CP_WRITE(n, i) p_ctrl->p_reg->PDCFCH##n##R = p_c->compensation[i]
    PDM_PRV_CP_WRITE(00, 0); PDM_PRV_CP_WRITE(01, 1); PDM_PRV_CP_WRITE(02, 2);
    PDM_PRV_CP_WRITE(03, 3); PDM_PRV_CP_WRITE(04, 4); PDM_PRV_CP_WRITE(05, 5);
    PDM_PRV_CP_WRITE(06, 6); PDM_PRV_CP_WRITE(07, 7); PDM_PRV_CP_WRITE(08, 8);
    PDM_PRV_CP_WRITE(09, 9); PDM_PRV_CP_WRITE(10, 10);
#undef PDM_PRV_CP_WRITE
    p_ctrl->p_reg->PDLFCH010R = p_c->low_pass[0];
#define PDM_PRV_LP_WRITE(n, i) p_ctrl->p_reg->PDLFCH1##n##R = p_c->low_pass[i]
    PDM_PRV_LP_WRITE(00, 1); PDM_PRV_LP_WRITE(01, 2); PDM_PRV_LP_WRITE(02, 3);
    PDM_PRV_LP_WRITE(03, 4); PDM_PRV_LP_WRITE(04, 5); PDM_PRV_LP_WRITE(05, 6);
    PDM_PRV_LP_WRITE(06, 7); PDM_PRV_LP_WRITE(07, 8); PDM_PRV_LP_WRITE(08, 9);
    PDM_PRV_LP_WRITE(09, 10); PDM_PRV_LP_WRITE(10, 11); PDM_PRV_LP_WRITE(11, 12);
    PDM_PRV_LP_WRITE(12, 13); PDM_PRV_LP_WRITE(13, 14); PDM_PRV_LP_WRITE(14, 15);
    PDM_PRV_LP_WRITE(15, 16); PDM_PRV_LP_WRITE(16, 17); PDM_PRV_LP_WRITE(17, 18);
    PDM_PRV_LP_WRITE(18, 19); PDM_PRV_LP_WRITE(19, 20);
#undef PDM_PRV_LP_WRITE
}

/* HM 50.2.19: INPSEL=1 selects CH(n-1), wrapping CH0 to CH2.
 * Table 50.18 requires matched SFMD, filter modes,
 * decimation/range and PDDBCR. HFMD/CFMD/LFMD/SDHFMD are reserved in this IP's mode
 * register; this driver always writes zero there and to SDMAMD (HM 50.2.19). */
static bool pdm_source_check (pdm_cfg_t const * p_cfg)
{
    pdm_extended_cfg_t const * p_extend = (pdm_extended_cfg_t const *) p_cfg->p_extend;
    if (PDM_INPUT_RISING == p_extend->input)
    {
        return true;
    }
    if (PDM_INPUT_PREVIOUS_FALLING != p_extend->input)
    {
        return false;
    }
    R_PDM_CH_Type * p_source = &R_PDM->CH[(p_cfg->channel + 2U) % 3U];
    uint32_t mode = ((uint32_t) p_extend->sinc_order & 3U) << R_PDM_CH_PDMDSR_SFMD_Pos;
    uint32_t sinc = (((uint32_t) g_pdm_decimation[p_extend->clock_div] - 1U) <<
                     R_PDM_CH_PDSFCR_SINCDEC_Pos) |
                    ((uint32_t) g_pdm_range[p_extend->sinc_order - 1U][p_extend->clock_div] <<
                     R_PDM_CH_PDSFCR_SINCRNG_Pos);
    return ((p_source->PDSR & (R_PDM_CH_PDSR_STATE_Msk | PDM_PRV_ERROR_MASK)) == R_PDM_CH_PDSR_STATE_Msk) &&
           ((p_source->PDMDSR & PDM_PRV_STEREO_MODE_MASK) == mode) &&
           ((p_source->PDSFCR & PDM_PRV_STEREO_SINC_MASK) == sinc) &&
           (p_source->PDDBCR == p_extend->fifo_threshold);
}

static void pdm_filter_start (pdm_instance_ctrl_t * p_ctrl)
{
    pdm_extended_cfg_t const * p_extend = (pdm_extended_cfg_t const *) p_ctrl->p_cfg->p_extend;
    uint32_t div = p_extend->clock_div;
    if (PDM_INPUT_PREVIOUS_FALLING == p_extend->input)
    {
        /* The falling consumer's own CKDIV is unused (table 50.18). */
        div = R_PDM->CH[(p_ctrl->p_cfg->channel + 2U) % 3U].PDSFCR & 15U;
    }
    p_ctrl->p_reg->PDSTRTR = 1U;
    /* HM table 50.16: internal settling at the guaranteed MOCO minimum 7.2MHz
     * (table 70.50), rounded up independently of the microphone's additional delay. */
    uint32_t d = 2U * (div + 1U);
    uint32_t cycles = 43U + d + (((uint32_t) p_extend->sinc_order + 49U) * d *
                               g_pdm_decimation[p_extend->clock_div]);
    R_BSP_SoftwareDelay(((cycles * 10U + 71U) / 72U) + p_extend->microphone_delay_us,
                        BSP_DELAY_UNITS_MICROSECONDS);
    p_ctrl->p_reg->PDSCR = PDM_PRV_CLEAR_MASK;
    p_ctrl->p_reg->PDSDCR = p_extend->error_enable | R_PDM_CH_PDSDCR_BFOWDE_Msk;
    p_ctrl->filtering = true;
}

static void pdm_buffer_release (pdm_instance_ctrl_t * p_ctrl)
{
    p_ctrl->p_reg->PDICR = 0U;
    p_ctrl->p_reg->PDDRCR = 0U;
    p_ctrl->active = false;
    p_ctrl->p_buffer = NULL;
    p_ctrl->length = 0U;
}

static fsp_err_t pdm_filter_stop (pdm_instance_ctrl_t * p_ctrl)
{
    p_ctrl->p_reg->PDSTPTR = 1U;
    /* Disable CPU reception even on timeout, so ownership always returns to the caller. */
    pdm_buffer_release(p_ctrl);
    p_ctrl->filtering = false;
    uint32_t retries = PDM_PRV_STOP_RETRIES;
    while (0U != (p_ctrl->p_reg->PDSR & R_PDM_CH_PDSR_STATE_Msk))
    {
        FSP_ERROR_RETURN(0U != --retries, FSP_ERR_TIMEOUT);
    }
    p_ctrl->p_reg->PDSDCR = 0U;
    p_ctrl->p_reg->PDSCR = PDM_PRV_CLEAR_MASK;
    return FSP_SUCCESS;
}

static void pdm_call_callback (pdm_instance_ctrl_t * p_ctrl, pdm_callback_args_t * p_args)
{
    if (NULL == p_ctrl->p_callback)
    {
        return;
    }
    pdm_callback_args_t args;
    pdm_callback_args_t * p_args_memory = p_ctrl->p_callback_memory;
    if (NULL == p_args_memory)
    {
        p_args_memory = p_args;
    }
    else
    {
        args = *p_args_memory;
        *p_args_memory = *p_args;
    }
#if BSP_TZ_SECURE_BUILD
    if (!cmse_is_nsfptr(p_ctrl->p_callback))
    {
        p_ctrl->p_callback(p_args_memory);
    }
    else
    {
        pdm_prv_ns_callback p_callback = (pdm_prv_ns_callback) p_ctrl->p_callback;
        p_callback(p_args_memory);
    }
#else
    p_ctrl->p_callback(p_args_memory);
#endif
    if (NULL != p_ctrl->p_callback_memory)
    {
        *p_ctrl->p_callback_memory = args;
    }
}

/** Data ISR drains a bounded FIFO snapshot. Data and error IRQs have the same priority, so cannot preempt each other. */
void pdm_dat_isr (void)
{
    FSP_CONTEXT_SAVE
    IRQn_Type irq = R_FSP_CurrentIrqGet();
    pdm_instance_ctrl_t * p_ctrl = (pdm_instance_ctrl_t *) R_FSP_IsrContextGet(irq);
    if ((NULL != p_ctrl) && p_ctrl->active)
    {
        if (0U == (p_ctrl->p_reg->PDSR & PDM_PRV_ERROR_MASK))
        {
            uint32_t count = p_ctrl->p_reg->PDDSR & 0xFFU;
            if (count > PDM_PRV_FIFO_VALID_WORDS)
            {
                count = PDM_PRV_FIFO_VALID_WORDS;
            }
            while ((count > 0U) && (p_ctrl->samples < p_ctrl->length))
            {
                p_ctrl->p_buffer[p_ctrl->samples] = p_ctrl->p_reg->PDDRR;
                p_ctrl->samples++;
                count--;
            }
            if (p_ctrl->samples == p_ctrl->length)
            {
                /* End FIFO reception before the final error check, so subsequent data
                 * cannot overwrite a completed capture (HM 50.3.7). Keep ownership until checked. */
                p_ctrl->p_reg->PDICR = 0U;
                p_ctrl->p_reg->PDDRCR = 0U;
            }
        }
        /* Clear the ICU edge latch before rechecking either level. Clearing it after
         * the occupancy test loses a threshold crossing in between (HM 50.5.1, 14.2.17). */
        R_BSP_IrqStatusClear(irq);
        if (0U != (p_ctrl->p_reg->PDSR & PDM_PRV_ERROR_MASK))
        {
            /* Includes errors raised asynchronously during the FIFO drain. */
            NVIC_SetPendingIRQ(p_ctrl->p_cfg->err_irq);
        }
        else if (p_ctrl->samples == p_ctrl->length)
        {
            pdm_callback_args_t args = {.event = PDM_EVENT_COMPLETE, .error = 0U,
                .p_buffer = p_ctrl->p_buffer, .samples = p_ctrl->samples, .p_context = p_ctrl->p_context};
            pdm_buffer_release(p_ctrl);
            pdm_call_callback(p_ctrl, &args);
        }
        else
        {
            pdm_extended_cfg_t const * p_extend = (pdm_extended_cfg_t const *) p_ctrl->p_cfg->p_extend;
            if ((p_ctrl->p_reg->PDDSR & 0xFFU) >= (1U << p_extend->fifo_threshold))
            {
                NVIC_SetPendingIRQ(irq);
            }
        }
    }
    else
    {
        R_BSP_IrqStatusClear(irq);
    }
    FSP_CONTEXT_RESTORE
}

/** Error ISR stops the channel; Start may be retried after hardware STATE becomes zero. */
void pdm_err_isr (void)
{
    FSP_CONTEXT_SAVE
    IRQn_Type irq = R_FSP_CurrentIrqGet();
    pdm_instance_ctrl_t * p_ctrl = (pdm_instance_ctrl_t *) R_FSP_IsrContextGet(irq);
    if ((NULL != p_ctrl) && p_ctrl->active)
    {
        uint32_t errors = p_ctrl->p_reg->PDSR & PDM_PRV_ERROR_MASK;
        if (0U != errors)
        {
            pdm_callback_args_t args = {.event = PDM_EVENT_ERROR, .error = errors,
                .p_buffer = p_ctrl->p_buffer, .samples = p_ctrl->samples, .p_context = p_ctrl->p_context};
            fsp_err_t err = pdm_filter_stop(p_ctrl);
            FSP_PARAMETER_NOT_USED(err); /* STATE remains observable; Start/Close explicitly report stop timeouts. */
            p_ctrl->p_reg->PDSCR = errors;
            R_BSP_IrqStatusClear(irq);
            pdm_call_callback(p_ctrl, &args);
            FSP_CONTEXT_RESTORE
            return;
        }
    }
    R_BSP_IrqStatusClear(irq);
    FSP_CONTEXT_RESTORE
}

/*******************************************************************************************************************//**
 * @} (end addtogroup PDM)
 **********************************************************************************************************************/
