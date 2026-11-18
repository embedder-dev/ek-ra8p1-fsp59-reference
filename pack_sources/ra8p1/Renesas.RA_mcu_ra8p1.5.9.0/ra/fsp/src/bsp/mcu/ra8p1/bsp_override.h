/*
* Copyright (c) 2020 - 2025 Renesas Electronics Corporation and/or its affiliates
*
* SPDX-License-Identifier: BSD-3-Clause
*/

/*******************************************************************************************************************//**
 * @addtogroup BSP_MCU_RA8P1
 * @{
 **********************************************************************************************************************/

/** @} (end addtogroup BSP_MCU_RA8P1) */

#ifndef BSP_OVERRIDE_H
#define BSP_OVERRIDE_H

#include <stdint.h>

/***********************************************************************************************************************
 * Macro definitions
 **********************************************************************************************************************/

#define BSP_OVERRIDE_CGC_SYS_CLOCK_DIV_T
#define BSP_OVERRIDE_CGC_DIVIDER_CFG_T
#define BSP_OVERRIDE_GROUP_IRQ_T
#define BSP_OVERRIDE_LVD_PERIPHERAL_T
#define BSP_OVERRIDE_LPM_SNOOZE_CANCEL_T
#define BSP_OVERRIDE_LPM_STANDBY_WAKE_SOURCE_T
#define BSP_OVERRIDE_ADC_CHANNEL_T
#define ADC_B_CHANNEL_MASK_EXT_OFFSET    (32U)

/***********************************************************************************************************************
 * Typedef definitions
 **********************************************************************************************************************/

/** SCKDIVCR and SCKDIVCR2 division encodings (HM 9.2.2-9.2.3). */
typedef enum e_cgc_sys_clock_div
{
    CGC_SYS_CLOCK_DIV_1  = 0,          ///< System clock divided by 1
    CGC_SYS_CLOCK_DIV_2  = 1,          ///< System clock divided by 2
    CGC_SYS_CLOCK_DIV_4  = 2,          ///< System clock divided by 4
    CGC_SYS_CLOCK_DIV_8  = 3,          ///< System clock divided by 8
    CGC_SYS_CLOCK_DIV_16 = 4,          ///< System clock divided by 16
    CGC_SYS_CLOCK_DIV_32 = 5,          ///< System clock divided by 32
    CGC_SYS_CLOCK_DIV_64 = 6,          ///< System clock divided by 64
    CGC_SYS_CLOCK_DIV_3  = 8,          ///< System clock divided by 3
    CGC_SYS_CLOCK_DIV_6  = 9,          ///< System clock divided by 6
    CGC_SYS_CLOCK_DIV_12 = 10,         ///< System clock divided by 12
    CGC_SYS_CLOCK_DIV_24 = 11,         ///< System clock divided by 24
} cgc_sys_clock_div_t;

/** Clock divider register images. CPUCLK denotes physical CPU0, not the executing core. */
typedef struct st_cgc_divider_cfg
{
    union
    {
        uint32_t sckdivcr_w;
        union
        {
            struct
            {
                cgc_sys_clock_div_t pclkd_div : 4;
                cgc_sys_clock_div_t pclkc_div : 4;
                cgc_sys_clock_div_t pclkb_div : 4;
                cgc_sys_clock_div_t pclka_div : 4;
                cgc_sys_clock_div_t bclk_div  : 4;
                cgc_sys_clock_div_t pclke_div : 4;
                cgc_sys_clock_div_t iclk_div  : 4;
                cgc_sys_clock_div_t fclk_div  : 4; ///< Legacy API spelling for the MRPCLK field; not a FACI clock.
            };
            struct
            {
                uint32_t           : 28;
                cgc_sys_clock_div_t mrpclk_div : 4;
            };
        } sckdivcr_b;
    };
    union
    {
        uint16_t sckdivcr2;
        union
        {
            struct
            {
                uint16_t cpuclk_div  : 4; ///< CPUCK0
                uint16_t cpuclk1_div : 4; ///< CPUCK1
                uint16_t npuclk_div  : 4; ///< NPUCK
                uint16_t mriclk_div  : 4; ///< MRICK
            };
            struct
            {
                uint16_t               : 4;
                uint16_t extraclk1_div : 4; ///< CPUCK1, shared BSP spelling
                uint16_t extraclk2_div : 4; ///< NPUCK, shared BSP spelling
                uint16_t extraclk3_div : 4; ///< MRICK, shared BSP spelling
            };
        } sckdivcr2_b;
    };
} cgc_divider_cfg_t;

/** Snooze is not supported. Only the neutral API value is available. */
typedef enum e_lpm_snooze_cancel
{
    LPM_SNOOZE_CANCEL_SOURCE_NONE = 0U, ///< No snooze cancel source
} lpm_snooze_cancel_t;

/** Software Standby wake factors in [WUPEN1:WUPEN0] (HM 14.2.19-20). */
typedef enum e_lpm_standby_wake_source
{
    LPM_STANDBY_WAKE_SOURCE_IRQ0    = (1ULL << 0),
    LPM_STANDBY_WAKE_SOURCE_IRQ1    = (1ULL << 1),
    LPM_STANDBY_WAKE_SOURCE_IRQ2    = (1ULL << 2),
    LPM_STANDBY_WAKE_SOURCE_IRQ3    = (1ULL << 3),
    LPM_STANDBY_WAKE_SOURCE_IRQ4    = (1ULL << 4),
    LPM_STANDBY_WAKE_SOURCE_IRQ5    = (1ULL << 5),
    LPM_STANDBY_WAKE_SOURCE_IRQ6    = (1ULL << 6),
    LPM_STANDBY_WAKE_SOURCE_IRQ7    = (1ULL << 7),
    LPM_STANDBY_WAKE_SOURCE_IRQ8    = (1ULL << 8),
    LPM_STANDBY_WAKE_SOURCE_IRQ9    = (1ULL << 9),
    LPM_STANDBY_WAKE_SOURCE_IRQ10   = (1ULL << 10),
    LPM_STANDBY_WAKE_SOURCE_IRQ11   = (1ULL << 11),
    LPM_STANDBY_WAKE_SOURCE_IRQ12   = (1ULL << 12),
    LPM_STANDBY_WAKE_SOURCE_IRQ13   = (1ULL << 13),
    LPM_STANDBY_WAKE_SOURCE_IRQ14   = (1ULL << 14),
    LPM_STANDBY_WAKE_SOURCE_IRQ15   = (1ULL << 15),
    LPM_STANDBY_WAKE_SOURCE_IWDT    = (1ULL << 16),
    LPM_STANDBY_WAKE_SOURCE_LVD1    = (1ULL << 18), ///< PVD1
    LPM_STANDBY_WAKE_SOURCE_LVD2    = (1ULL << 19), ///< PVD2
    LPM_STANDBY_WAKE_SOURCE_VBATT   = (1ULL << 20),
    LPM_STANDBY_WAKE_SOURCE_RTCALM  = (1ULL << 24),
    LPM_STANDBY_WAKE_SOURCE_RTCPRD  = (1ULL << 25),
    LPM_STANDBY_WAKE_SOURCE_USBHS   = (1ULL << 26),
    LPM_STANDBY_WAKE_SOURCE_USBFS   = (1ULL << 27),
    LPM_STANDBY_WAKE_SOURCE_AGT1UD  = (1ULL << 28),
    LPM_STANDBY_WAKE_SOURCE_AGT1CA  = (1ULL << 29),
    LPM_STANDBY_WAKE_SOURCE_AGT1CB  = (1ULL << 30),
    LPM_STANDBY_WAKE_SOURCE_IIC0    = (1ULL << 31),
    LPM_STANDBY_WAKE_SOURCE_COMPHS0 = (1ULL << 35),
    LPM_STANDBY_WAKE_SOURCE_SOSTD   = (1ULL << 39),
    LPM_STANDBY_WAKE_SOURCE_ULP0U   = (1ULL << 40),
    LPM_STANDBY_WAKE_SOURCE_ULP0A   = (1ULL << 41),
    LPM_STANDBY_WAKE_SOURCE_ULP0B   = (1ULL << 42),
    LPM_STANDBY_WAKE_SOURCE_I3C0    = (1ULL << 43),
    LPM_STANDBY_WAKE_SOURCE_ULP1U   = (1ULL << 44),
    LPM_STANDBY_WAKE_SOURCE_ULP1A   = (1ULL << 45),
    LPM_STANDBY_WAKE_SOURCE_ULP1B   = (1ULL << 46),
    LPM_STANDBY_WAKE_SOURCE_PDM     = (1ULL << 47),
    LPM_STANDBY_WAKE_SOURCE_IRQ16   = (1ULL << 48),
    LPM_STANDBY_WAKE_SOURCE_IRQ17   = (1ULL << 49),
    LPM_STANDBY_WAKE_SOURCE_IRQ18   = (1ULL << 50),
    LPM_STANDBY_WAKE_SOURCE_IRQ19   = (1ULL << 51),
    LPM_STANDBY_WAKE_SOURCE_IRQ20   = (1ULL << 52),
    LPM_STANDBY_WAKE_SOURCE_IRQ21   = (1ULL << 53),
    LPM_STANDBY_WAKE_SOURCE_IRQ22   = (1ULL << 54),
    LPM_STANDBY_WAKE_SOURCE_IRQ23   = (1ULL << 55),
    LPM_STANDBY_WAKE_SOURCE_IRQ24   = (1ULL << 56),
    LPM_STANDBY_WAKE_SOURCE_IRQ25   = (1ULL << 57),
    LPM_STANDBY_WAKE_SOURCE_IRQ26   = (1ULL << 58),
    LPM_STANDBY_WAKE_SOURCE_IRQ27   = (1ULL << 59),
    LPM_STANDBY_WAKE_SOURCE_IRQ28   = (1ULL << 60),
    LPM_STANDBY_WAKE_SOURCE_IRQ29   = (1ULL << 61),
    LPM_STANDBY_WAKE_SOURCE_IRQ30   = (1ULL << 62),
    LPM_STANDBY_WAKE_SOURCE_IRQ31   = (1ULL << 63),
} lpm_standby_wake_source_t;

typedef uint64_t lpm_standby_wake_source_bits_t;

/** NMIER bit numbers in the executing core's ICU instance (HM 14.2.14). */
typedef enum e_bsp_grp_irq
{
    BSP_GRP_IRQ_IWDT_ERROR      = 0,   ///< IWDT underflow/refresh error
    BSP_GRP_IRQ_WDT_ERROR       = 1,   ///< Local WDT0 or WDT1 underflow/refresh error
    BSP_GRP_IRQ_LVD1            = 2,   ///< PVD1
    BSP_GRP_IRQ_LVD2            = 3,   ///< PVD2
    BSP_GRP_IRQ_SUB_OSC_STOP    = 5,   ///< Sub-clock oscillation stop
    BSP_GRP_IRQ_OSC_STOP_DETECT = 6,   ///< Main clock oscillation stop
    BSP_GRP_IRQ_NMI_PIN         = 7,   ///< NMI pin
    BSP_GRP_IRQ_MPU_BUS_TZF     = 12,  ///< Bus/MPU/TrustZone filter error
    BSP_GRP_IRQ_COMMON_MEMORY   = 13,  ///< Common memory error
    BSP_GRP_IRQ_LOCAL_MEMORY    = 14,  ///< Local memory error
    BSP_GRP_IRQ_LOCKUP          = 15,  ///< CPU lockup
    BSP_GRP_IRQ_FPU_EXCEPTION   = 16,  ///< FPU exception
    BSP_GRP_IRQ_MRAM_CODE_READ  = 17,  ///< Code MRAM read error
    BSP_GRP_IRQ_MRAM_EXTRA_READ = 18,  ///< Extra MRAM read error
    BSP_GRP_IRQ_IPC             = 20,  ///< Inter-processor NMI
} bsp_grp_irq_t;

/** PVDm/PVDn comparator threshold encodings (HM 8.2). */
typedef enum
{
    LVD_THRESHOLD_MONITOR_LEVEL_3_86V = 0x03UL, ///< 3.86 V
    LVD_THRESHOLD_MONITOR_LEVEL_3_14V = 0x04UL, ///< 3.14 V
    LVD_THRESHOLD_MONITOR_LEVEL_3_10V = 0x05UL, ///< 3.10 V
    LVD_THRESHOLD_MONITOR_LEVEL_3_08V = 0x06UL, ///< 3.08 V
    LVD_THRESHOLD_MONITOR_LEVEL_2_85V = 0x07UL, ///< 2.85 V
    LVD_THRESHOLD_MONITOR_LEVEL_2_83V = 0x08UL, ///< 2.83 V
    LVD_THRESHOLD_MONITOR_LEVEL_2_80V = 0x09UL, ///< 2.80 V
    LVD_THRESHOLD_MONITOR_LEVEL_2_62V = 0x0AUL, ///< 2.62 V
    LVD_THRESHOLD_MONITOR_LEVEL_2_33V = 0x0BUL, ///< 2.33 V
    LVD_THRESHOLD_MONITOR_LEVEL_1_90V = 0x0CUL, ///< 1.90 V
    LVD_THRESHOLD_MONITOR_LEVEL_1_86V = 0x0DUL, ///< 1.86 V
    LVD_THRESHOLD_MONITOR_LEVEL_1_74V = 0x0EUL, ///< 1.74 V
    LVD_THRESHOLD_MONITOR_LEVEL_1_71V = 0x0FUL, ///< 1.71 V
    LVD_THRESHOLD_NOT_AVAILABLE     = 0xFFUL, ///< Not used
} lvd_threshold_t;

/** ADC16H clock selectors, HM 54.2.1.3. */
typedef enum e_adc_b_clock_source
{
    ADC_B_CLOCK_SOURCE_ADCCLK = 0,
    ADC_B_CLOCK_SOURCE_GPT    = 1,
    ADC_B_CLOCK_SOURCE_PCLKA  = 2,
} adc_b_clock_source_t;

/** ADC16H has 33 virtual channels, HM 54.2.3.1. */
typedef enum e_adc_b_virtual_channel
{
    ADC_B_VIRTUAL_CHANNEL_0  = 0,
    ADC_B_VIRTUAL_CHANNEL_1  = 1,
    ADC_B_VIRTUAL_CHANNEL_2  = 2,
    ADC_B_VIRTUAL_CHANNEL_3  = 3,
    ADC_B_VIRTUAL_CHANNEL_4  = 4,
    ADC_B_VIRTUAL_CHANNEL_5  = 5,
    ADC_B_VIRTUAL_CHANNEL_6  = 6,
    ADC_B_VIRTUAL_CHANNEL_7  = 7,
    ADC_B_VIRTUAL_CHANNEL_8  = 8,
    ADC_B_VIRTUAL_CHANNEL_9  = 9,
    ADC_B_VIRTUAL_CHANNEL_10 = 10,
    ADC_B_VIRTUAL_CHANNEL_11 = 11,
    ADC_B_VIRTUAL_CHANNEL_12 = 12,
    ADC_B_VIRTUAL_CHANNEL_13 = 13,
    ADC_B_VIRTUAL_CHANNEL_14 = 14,
    ADC_B_VIRTUAL_CHANNEL_15 = 15,
    ADC_B_VIRTUAL_CHANNEL_16 = 16,
    ADC_B_VIRTUAL_CHANNEL_17 = 17,
    ADC_B_VIRTUAL_CHANNEL_18 = 18,
    ADC_B_VIRTUAL_CHANNEL_19 = 19,
    ADC_B_VIRTUAL_CHANNEL_20 = 20,
    ADC_B_VIRTUAL_CHANNEL_21 = 21,
    ADC_B_VIRTUAL_CHANNEL_22 = 22,
    ADC_B_VIRTUAL_CHANNEL_23 = 23,
    ADC_B_VIRTUAL_CHANNEL_24 = 24,
    ADC_B_VIRTUAL_CHANNEL_25 = 25,
    ADC_B_VIRTUAL_CHANNEL_26 = 26,
    ADC_B_VIRTUAL_CHANNEL_27 = 27,
    ADC_B_VIRTUAL_CHANNEL_28 = 28,
    ADC_B_VIRTUAL_CHANNEL_29 = 29,
    ADC_B_VIRTUAL_CHANNEL_30 = 30,
    ADC_B_VIRTUAL_CHANNEL_31 = 31,
    ADC_B_VIRTUAL_CHANNEL_32 = 32,
    ADC_B_VIRTUAL_CHANNEL_COUNT
} adc_b_virtual_channel_t;

/** Physical and extended channel encodings, HM tables 54.4/54.5 and 54.2.3.1. */
typedef enum e_adc_channel
{
    ADC_CHANNEL_0  = 0,
    ADC_CHANNEL_1  = 1,
    ADC_CHANNEL_2  = 2,
    ADC_CHANNEL_3  = 3,
    ADC_CHANNEL_4  = 4,
    ADC_CHANNEL_5  = 5,
    ADC_CHANNEL_6  = 6,
    ADC_CHANNEL_7  = 7,
    ADC_CHANNEL_8  = 8,
    ADC_CHANNEL_9  = 9,
    ADC_CHANNEL_10 = 10,
    ADC_CHANNEL_11 = 11,
    ADC_CHANNEL_12 = 12,
    ADC_CHANNEL_13 = 13,
    ADC_CHANNEL_14 = 14,
    ADC_CHANNEL_15 = 15,
    ADC_CHANNEL_16 = 16,
    ADC_CHANNEL_17 = 17,
    ADC_CHANNEL_18 = 18,
    ADC_CHANNEL_19 = 19,
    ADC_CHANNEL_20 = 20,
    ADC_CHANNEL_21 = 21,
    ADC_CHANNEL_22 = 22,
    ADC_CHANNEL_SELF_DIAGNOSIS_0    = 0x60,
    ADC_CHANNEL_SELF_DIAGNOSIS_1    = 0x61,
    ADC_CHANNEL_TEMPERATURE         = 0x64,
    ADC_CHANNEL_VOLT                = 0x65,
    ADC_CHANNEL_VBATT               = 0x66,
    ADC_CHANNEL_DA0                 = 0x68,
    ADC_CHANNEL_DA1                 = 0x69,
    ADC_CHANNEL_SELF_DIAGNOSIS_SH0  = 0x70,
    ADC_CHANNEL_SELF_DIAGNOSIS_SH1  = 0x71,
    ADC_CHANNEL_SELF_DIAGNOSIS_SH2  = 0x72,
    ADC_CHANNEL_SELF_DIAGNOSIS_SH4  = 0x74,
    ADC_CHANNEL_SELF_DIAGNOSIS_SH5  = 0x75,
    ADC_CHANNEL_SELF_DIAGNOSIS_SH6  = 0x76,
    ADC_CHANNEL_LAST_EXTERNAL       = ADC_CHANNEL_22,
    ADC_CHANNEL_FIRST_INTERNAL      = ADC_CHANNEL_SELF_DIAGNOSIS_0,
    ADC_CHANNEL_LAST_INTERNAL       = ADC_CHANNEL_SELF_DIAGNOSIS_SH6,
} adc_channel_t;

/** Result/error mask: physical channels use bits 0..22; extended sources use bits 32..54. */
typedef enum e_adc_b_channel_mask
{
    ADC_B_CHANNEL_MASK_NONE = 0ULL,
    ADC_B_CHANNEL_MASK_0    = (1ULL << 0),
    ADC_B_CHANNEL_MASK_1    = (1ULL << 1),
    ADC_B_CHANNEL_MASK_2    = (1ULL << 2),
    ADC_B_CHANNEL_MASK_3    = (1ULL << 3),
    ADC_B_CHANNEL_MASK_4    = (1ULL << 4),
    ADC_B_CHANNEL_MASK_5    = (1ULL << 5),
    ADC_B_CHANNEL_MASK_6    = (1ULL << 6),
    ADC_B_CHANNEL_MASK_7    = (1ULL << 7),
    ADC_B_CHANNEL_MASK_8    = (1ULL << 8),
    ADC_B_CHANNEL_MASK_9    = (1ULL << 9),
    ADC_B_CHANNEL_MASK_10   = (1ULL << 10),
    ADC_B_CHANNEL_MASK_11   = (1ULL << 11),
    ADC_B_CHANNEL_MASK_12   = (1ULL << 12),
    ADC_B_CHANNEL_MASK_13   = (1ULL << 13),
    ADC_B_CHANNEL_MASK_14   = (1ULL << 14),
    ADC_B_CHANNEL_MASK_15   = (1ULL << 15),
    ADC_B_CHANNEL_MASK_16   = (1ULL << 16),
    ADC_B_CHANNEL_MASK_17   = (1ULL << 17),
    ADC_B_CHANNEL_MASK_18   = (1ULL << 18),
    ADC_B_CHANNEL_MASK_19   = (1ULL << 19),
    ADC_B_CHANNEL_MASK_20   = (1ULL << 20),
    ADC_B_CHANNEL_MASK_21   = (1ULL << 21),
    ADC_B_CHANNEL_MASK_22   = (1ULL << 22),
    ADC_B_CHANNEL_MASK_DIAGNOSIS_0 = (1ULL << 32),
    ADC_B_CHANNEL_MASK_DIAGNOSIS_1 = (1ULL << 33),
    ADC_B_CHANNEL_MASK_TEMPERATURE = (1ULL << 36),
    ADC_B_CHANNEL_MASK_VOLT        = (1ULL << 37),
    ADC_B_CHANNEL_MASK_VBATT       = (1ULL << 38),
    ADC_B_CHANNEL_MASK_DAC0        = (1ULL << 40),
    ADC_B_CHANNEL_MASK_DAC1        = (1ULL << 41),
    ADC_B_CHANNEL_MASK_DIAGNOSIS_SH0 = (1ULL << 48),
    ADC_B_CHANNEL_MASK_DIAGNOSIS_SH1 = (1ULL << 49),
    ADC_B_CHANNEL_MASK_DIAGNOSIS_SH2 = (1ULL << 50),
    ADC_B_CHANNEL_MASK_DIAGNOSIS_SH4 = (1ULL << 52),
    ADC_B_CHANNEL_MASK_DIAGNOSIS_SH5 = (1ULL << 53),
    ADC_B_CHANNEL_MASK_DIAGNOSIS_SH6 = (1ULL << 54),
} adc_b_channel_mask_t;

#endif
