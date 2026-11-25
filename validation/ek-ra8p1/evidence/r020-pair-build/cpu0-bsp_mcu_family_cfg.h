/* generated configuration header file - do not edit */
#ifndef BSP_MCU_FAMILY_CFG_H_
#define BSP_MCU_FAMILY_CFG_H_
/* _RA_CORE is supplied by e2 studio's selected processor. */
            #define BSP_PRV_CORE_ID_CM85 (1)
            #define BSP_PRV_CORE_ID_CM33 (2)
            #define BSP_PRV_CORE_ID_(core) BSP_PRV_CORE_ID_ ## core
            #define BSP_PRV_CORE_ID(core) BSP_PRV_CORE_ID_(core)
            #if !defined(_RA_CORE)
                #error "e2 studio must select _RA_CORE=CM85 or CM33"
            #elif BSP_PRV_CORE_ID(_RA_CORE) == 1
                #define BSP_CFG_CPU_CORE (0)
            #elif BSP_PRV_CORE_ID(_RA_CORE) == 2
                #define BSP_CFG_CPU_CORE (1)
            #else
                #error "Unsupported RA8P1 processor selected by _RA_CORE"
            #endif
            #include "bsp_mcu_device_pn_cfg.h"
            #include "bsp_mcu_device_cfg.h"
            #include "../../../ra/fsp/src/bsp/mcu/ra8p1/bsp_override.h"
            #include "../../../ra/fsp/src/bsp/mcu/ra8p1/bsp_mcu_info.h"
            #include "bsp_clock_cfg.h"
            #define BSP_MCU_GROUP_RA8P1 (1)
            #if (BSP_CFG_CPU_CORE == 0) && (0x02080000U != 0U)
                #define BSP_CFG_SECONDARY_CORE_START_ADDRESS (0x02080000U)
            #endif
            /* A disabled GPTCLK leaves the hardware on the reset oscillator unless GPT selects PCLKD. */
            #define BSP_CFG_GPT_COUNT_CLOCK_SOURCE (BSP_CFG_GPTCLK_SOURCE == BSP_CLOCKS_CLOCK_DISABLED)
            #define BSP_CFG_MRPCLK_DIV BSP_CFG_FCLK_DIV
            #define BSP_CFG_CPUCLK0_DIV BSP_CFG_CPUCLK_DIV
            #define BSP_CFG_CPUCLK1_DIV BSP_CFG_EXTRACLK1_DIV
            #define BSP_CFG_NPUCLK_DIV BSP_CFG_EXTRACLK2_DIV
            #define BSP_CFG_MRICLK_DIV BSP_CFG_EXTRACLK3_DIV
            #define BSP_LOCO_HZ                 (32768)
            #define BSP_MOCO_HZ                 (8000000)
            #define BSP_SUB_CLOCK_HZ            (0)
            #if   BSP_CFG_HOCO_FREQUENCY == 0
                #define BSP_HOCO_HZ                 (16000000)
            #elif BSP_CFG_HOCO_FREQUENCY == 1
                #define BSP_HOCO_HZ                 (18000000)
            #elif BSP_CFG_HOCO_FREQUENCY == 2
                #define BSP_HOCO_HZ                 (20000000)
            #elif BSP_CFG_HOCO_FREQUENCY == 4
                #define BSP_HOCO_HZ                 (32000000)
            #elif BSP_CFG_HOCO_FREQUENCY == 7
                #define BSP_HOCO_HZ                 (48000000)
            #else
                #error "Invalid HOCO frequency chosen (BSP_CFG_HOCO_FREQUENCY) in bsp_clock_cfg.h"
            #endif

            #define BSP_CFG_FLL_ENABLE                   (0)

            #define BSP_CFG_CLOCK_SETTLING_DELAY_ENABLE  (1)
            #define BSP_CFG_SLEEP_MODE_DELAY_ENABLE      (1)
            #define BSP_CFG_MSTP_CHANGE_DELAY_ENABLE     (1)
            #define BSP_CFG_RTOS_IDLE_SLEEP              (0)
            #define BSP_CFG_CLOCK_SETTLING_DELAY_US      (150)

            #if defined(BSP_PACKAGE_LQFP) && (BSP_PACKAGE_PINS == 100)
                #define BSP_MAX_CLOCK_CHANGE_THRESHOLD (180000000U)
            #elif defined(BSP_PACKAGE_LQFP)
                #define BSP_MAX_CLOCK_CHANGE_THRESHOLD (200000000U)
            #else
                #define BSP_MAX_CLOCK_CHANGE_THRESHOLD (240000000U)
            #endif

            #define BSP_CORTEX_VECTOR_TABLE_ENTRIES    (16U)
            #define BSP_VECTOR_TABLE_MAX_ENTRIES       (112U)
            #define BSP_CFG_INLINE_IRQ_FUNCTIONS       (1)

            #if defined(_RA_TZ_SECURE)
            #define BSP_TZ_SECURE_BUILD           (1)
            #define BSP_TZ_NONSECURE_BUILD        (0)
            #elif defined(_RA_TZ_NONSECURE)
            #define BSP_TZ_SECURE_BUILD           (0)
            #define BSP_TZ_NONSECURE_BUILD        (1)
            #else
            #define BSP_TZ_SECURE_BUILD           (0)
            #define BSP_TZ_NONSECURE_BUILD        (0)
            #endif

            /* TrustZone Settings */
            #define BSP_TZ_CFG_INIT_SECURE_ONLY       (BSP_CFG_CLOCKS_SECURE || (!BSP_CFG_CLOCKS_OVERRIDE))
            #define BSP_TZ_CFG_SKIP_INIT              (BSP_TZ_NONSECURE_BUILD && BSP_TZ_CFG_INIT_SECURE_ONLY)
            #define BSP_TZ_CFG_EXCEPTION_RESPONSE     (0)

            /* CMSIS TrustZone Settings */
            #define SCB_CSR_AIRCR_INIT                (1)
            #define SCB_AIRCR_BFHFNMINS_VAL           (0)
            #define SCB_AIRCR_SYSRESETREQS_VAL        (1)
            #define SCB_AIRCR_PRIS_VAL                (0)
            #define TZ_FPU_NS_USAGE                   (1)
#ifndef SCB_NSACR_CP10_11_VAL
            #define SCB_NSACR_CP10_11_VAL             (3U)
#endif

#ifndef FPU_FPCCR_TS_VAL
            #define FPU_FPCCR_TS_VAL                  (1U)
#endif
            #define FPU_FPCCR_CLRONRETS_VAL           (1)

#ifndef FPU_FPCCR_CLRONRET_VAL
            #define FPU_FPCCR_CLRONRET_VAL            (1)
#endif

            /* Type 1 Peripheral Security Attribution */

            /* Peripheral Security Attribution Register (PSAR) Settings */
#ifndef BSP_TZ_CFG_PSARB
#define BSP_TZ_CFG_PSARB (\
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 4U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 7U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 8U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 9U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 11U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 12U) | \
            ((((RA_NOT_DEFINED > 0) || (RA_NOT_DEFINED > 0)) ? 0U : 1U) << 16U) | \
            ((((RA_NOT_DEFINED > 0) || (RA_NOT_DEFINED > 0)) ? 0U : 1U) << 17U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 18U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 19U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 22U) | \
            ((((1 > 0)) ? 0U : 1U) << 23U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 24U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 25U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 26U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 27U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 28U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 29U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 30U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 31U))
#endif
#ifndef BSP_TZ_CFG_PSARC
#define BSP_TZ_CFG_PSARC (\
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 0U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 1U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 7U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 8U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 11U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 12U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 13U) | \
            ((((RA_NOT_DEFINED > 0) || (RA_NOT_DEFINED > 0) || (RA_NOT_DEFINED > 0) || (RA_NOT_DEFINED > 0)) ? 0U : 1U) << 15U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 16U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 24U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 26U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 27U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 28U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 30U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 31U))
#endif
#ifndef BSP_TZ_CFG_PSARD
#define BSP_TZ_CFG_PSARD (\
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 4U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 5U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 6U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 11U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 12U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 13U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 14U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 19U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 20U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 21U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 22U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 25U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 26U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 27U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 28U))
#endif
#ifndef BSP_TZ_CFG_PSARE
#define BSP_TZ_CFG_PSARE (\
            (1U << 0U) | \
            ((((1 > 0)) ? 0U : 1U) << 1U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 2U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 3U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 8U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 9U) | \
            ((((1 > 0) || (RA_NOT_DEFINED > 0) || (RA_NOT_DEFINED > 0) || (RA_NOT_DEFINED > 0) || (RA_NOT_DEFINED > 0) || (RA_NOT_DEFINED > 0) || (RA_NOT_DEFINED > 0) || (RA_NOT_DEFINED > 0) || (RA_NOT_DEFINED > 0) || (RA_NOT_DEFINED > 0) || (RA_NOT_DEFINED > 0) || (RA_NOT_DEFINED > 0) || (RA_NOT_DEFINED > 0) || (RA_NOT_DEFINED > 0)) ? 0U : 1U) << 15U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 18U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 19U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 20U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 21U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 27U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 28U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 29U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 30U) | \
            ((((1 > 0)) ? 0U : 1U) << 31U))
#endif
#ifndef BSP_TZ_CFG_MSSAR
#define BSP_TZ_CFG_MSSAR (\
            (1U << 0U) | \
            (1U << 1U) | \
            (1U << 2U) | \
            (1U << 3U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 16U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 22U) | \
            (1U << 23U) | \
            ((((RA_NOT_DEFINED > 0)) ? 0U : 1U) << 31U))
#endif

            /* Type 2 Peripheral Security Attribution */

            /* Security attribution for RSTSRn registers. */
#ifndef BSP_TZ_CFG_RSTSAR
#define BSP_TZ_CFG_RSTSAR (0x0000000FU)
#endif

            /* Security attribution for registers of LVD channels. */
#ifndef BSP_TZ_CFG_LVDSAR
            /* The LVD driver needs to access both channels. This means that the security attribution for both channels must be the same. */
#if (RA_NOT_DEFINED > 0) || (RA_NOT_DEFINED > 0)
#define BSP_TZ_CFG_LVDSAR (0U)
#else
#define BSP_TZ_CFG_LVDSAR (3U)
#endif
#endif
#ifndef BSP_TZ_CFG_PVDSAR
#define BSP_TZ_CFG_PVDSAR (BSP_TZ_CFG_LVDSAR)
#endif

            /* CPU0 owns CPU1 TCM control and boundary attribution; HM 2.17.3.1-2. */
#ifndef BSP_TZ_CFG_TCMSAR
#define BSP_TZ_CFG_TCMSAR (0U)
#endif
#ifndef BSP_TZ_CFG_TCMSABARC
#define BSP_TZ_CFG_TCMSABARC (0x10000U)
#endif
#ifndef BSP_TZ_CFG_TCMSABARS
#define BSP_TZ_CFG_TCMSABARS (0x10000U)
#endif
#if (BSP_TZ_CFG_TCMSAR != 0U) && ((BSP_TZ_CFG_TCMSABARC | BSP_TZ_CFG_TCMSABARS) != 0U)
#error "TCM control must be Secure while either CPU1 TCM contains Secure memory"
#endif

            /* Security attribution for LPM registers.
             * - OPCCR based on clock security.
             * - Set remaining registers based on LPM security.
             */
#ifndef BSP_TZ_CFG_LPMSAR
#define BSP_TZ_CFG_LPMSAR (\
    ((BSP_CFG_CLOCKS_SECURE == 0) ? 0x00200011U : 0U) | \
    ((RA_NOT_DEFINED > 0) ? 0U : 0x000E0106U))
#endif
            /* Deep Standby Interrupt Factor Security Attribution Register. */
#ifndef BSP_TZ_CFG_DPFSAR
#define BSP_TZ_CFG_DPFSAR ((RA_NOT_DEFINED > 0) ? 0U : 0xEF1FFFFFU)
#endif
#ifndef BSP_TZ_CFG_DPFSAR1
#define BSP_TZ_CFG_DPFSAR1 ((RA_NOT_DEFINED > 0) ? 0U : 0x0000FFFFU)
#endif
            /* RAM Standby Control Security Attribution Register. */
#ifndef BSP_TZ_CFG_RSCSAR
#define BSP_TZ_CFG_RSCSAR ((RA_NOT_DEFINED > 0) ? 0U : 0x00031FFFU)
#endif
            /* Power Gating Control Security Attribution Register */
#ifndef BSP_TZ_CFG_PGCSAR
#define BSP_TZ_CFG_PGCSAR ((0 << 1U))
#endif

            /* Security attribution for CGC registers. */
#ifndef BSP_TZ_CFG_CGFSAR
#if BSP_CFG_CLOCKS_SECURE
/* Protect all CGC registers from Non-secure write access. */
#define BSP_TZ_CFG_CGFSAR (0U)
#else
/* Allow Secure and Non-secure write access. */
#define BSP_TZ_CFG_CGFSAR (0x1F7F7FFDU)
#endif
#endif

            /* Security attribution for Battery Backup registers. */
#ifndef BSP_TZ_CFG_BBFSAR
#if 0
#define BSP_TZ_CFG_BBFSAR   (0U)
#else
#define BSP_TZ_CFG_BBFSAR   (0x7FU)
#endif
#endif

            /* Security attribution for Battery Backup registers (VBTBKRn). */
#ifndef BSP_TZ_CFG_VBRSABAR
#if 0
#define BSP_TZ_CFG_VBRSABAR (0xFFE0)
#else
#define BSP_TZ_CFG_VBRSABAR (0xED00)
#endif
#endif

            /* Security attribution for registers for IRQ channels. */
#ifndef BSP_TZ_CFG_ICUSARA
#define BSP_TZ_CFG_ICUSARA (\
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 0U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 1U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 2U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 3U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 4U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 5U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 6U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 7U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 8U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 9U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 10U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 11U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 12U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 13U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 14U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 15U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 16U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 17U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 18U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 19U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 20U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 21U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 22U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 23U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 24U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 25U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 26U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 27U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 28U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 29U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 30U) | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 31U))
#endif

            /* Security attribution for NMI registers. */
#ifndef BSP_TZ_CFG_ICUSARB
#define BSP_TZ_CFG_ICUSARB ((0U) | \
                          (0 << 1U) | \
                          (0U << 2U))
#endif

            /* CPU0 establishes both DMAC channel banks and matching MMPU attribution. */
#ifndef BSP_TZ_CFG_DMACCHSAR_LOCAL
#define BSP_TZ_CFG_DMACCHSAR_LOCAL (\
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 0U) /* DMAC Channel 0 */ | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 1U) /* DMAC Channel 1 */ | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 2U) /* DMAC Channel 2 */ | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 3U) /* DMAC Channel 3 */ | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 4U) /* DMAC Channel 4 */ | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 5U) /* DMAC Channel 5 */ | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 6U) /* DMAC Channel 6 */ | \
            (((RA_NOT_DEFINED > 0) ? 0U : 1U) << 7U) /* DMAC Channel 7 */)
#endif
#ifndef BSP_TZ_CFG_DMACCHSAR_CPU1
#define BSP_TZ_CFG_DMACCHSAR_CPU1 (0x00)
#endif
#if (BSP_TZ_CFG_DMACCHSAR_CPU1 & ~0xFFU) != 0U
#error "CPU1 Non-secure DMA channel mask must be an integer from 0 to 0xFF"
#endif
#ifndef BSP_TZ_CFG_DMACCHSAR
#define BSP_TZ_CFG_DMACCHSAR (BSP_TZ_CFG_DMACCHSAR_LOCAL | (BSP_TZ_CFG_DMACCHSAR_CPU1 << 16U))
#endif

            /* Security attribution registers for WUPEN0. */
#ifndef BSP_TZ_CFG_ICUSARE
#define BSP_TZ_CFG_ICUSARE ((RA_NOT_DEFINED > 0) ? 0U : 0xFF1D0000U)
#endif

            /* Security attribution registers for WUPEN1. */
#ifndef BSP_TZ_CFG_ICUSARF
#define BSP_TZ_CFG_ICUSARF ((RA_NOT_DEFINED > 0) ? 0U : 0x0000FF88U)
#endif

            /* Trusted Event Route Control Register for IELSR, DMAC.DELSR and ELC.ELSR. Note that currently Trusted Event Route Control is not supported. */
#ifndef BSP_TZ_CFG_TEVTRCR
#define BSP_TZ_CFG_TEVTRCR (0)
#endif

            /* Security attribution register for ELCR, ELSEGR0, ELSEGR1 Security Attribution. */
#ifndef BSP_TZ_CFG_ELCSARA
 #define BSP_TZ_CFG_ELCSARA (0x0000001FU)
#endif

            /* Set DTCSTSAR if the Secure program uses the DTC. */
#if RA_NOT_DEFINED == RA_NOT_DEFINED
 #define BSP_TZ_CFG_DTC_USED (0U)
#else
 #define BSP_TZ_CFG_DTC_USED (1U)
#endif

            /* CPU0 establishes both controller banks; reserved bits remain zero (HM 17.2.3, 18.2.1). */
#ifndef BSP_TZ_CFG_DMACSAR
#define BSP_TZ_CFG_DMACSAR (((((BSP_TZ_CFG_DMACCHSAR & 0xFFU) == 0xFFU) ? 1U : 0U)) | \
                           ((0U) << 16U))
#endif
#ifndef BSP_TZ_CFG_DTCSAR
#define BSP_TZ_CFG_DTCSAR (((BSP_TZ_CFG_DTC_USED ? 0U : 1U)) | \
                          ((0U) << 16U))
#endif

            /* MRAM security attribution; HM 60.5.13. */
#ifndef BSP_TZ_CFG_MSAR
#define BSP_TZ_CFG_MSAR (\
    ((BSP_CFG_CLOCKS_SECURE == 0) ? 0x000AU : 0U) | \
    ((RA_NOT_DEFINED > 0) ? 0U : 0xEE15U))
#endif
#ifndef BSP_TZ_CFG_FSAR
#define BSP_TZ_CFG_FSAR (0U)
#endif

            /* Security attribution for SRAM registers. */
#ifndef BSP_TZ_CFG_SRAMSAR
/* If the CGC registers are only accessible in Secure mode, than there is no reason for Non Secure applications to access
 * SRAM0WTEN and therefore there is no reason to access PRCR2. */
    #define BSP_TZ_CFG_SRAMSAR (\
        ((1U) << 0U) | /* SRAMSA0 */\
        ((1U) << 1U) | /* SRAMSA1 */\
        ((1U) << 2U) | /* SRAMSA2 */\
        ((1U) << 3U) | /* SRAMSA3 */\
        ((BSP_CFG_CLOCKS_SECURE == 0) ? (1U << 8U) : 0U) /* SRAMWTSA */)
#endif

            /* Security attribution for the DMAC Bus Master MPU settings. */
#ifndef BSP_TZ_CFG_MMPUSARA
    /* The DMAC Bus Master MPU settings should align with the DMAC channel settings. */
    #define BSP_TZ_CFG_MMPUSARA (BSP_TZ_CFG_DMACCHSAR)
#endif

            /* Security Attribution Register A for BUS Control registers. */
#ifndef BSP_TZ_CFG_BUSSARA
    #define BSP_TZ_CFG_BUSSARA (1U)
#endif
            /* Security Attribution Register B for BUS Control registers. */
#ifndef BSP_TZ_CFG_BUSSARB
    #define BSP_TZ_CFG_BUSSARB (1U)
#endif
            /* Security Attribution Register C for BUS Control registers. */
#ifndef BSP_TZ_CFG_BUSSARC
    #define BSP_TZ_CFG_BUSSARC (1U)
#endif

            /* Enable Uninitialized Non-Secure Application Fallback. */
#ifndef BSP_TZ_CFG_NON_SECURE_APPLICATION_FALLBACK
    #define BSP_TZ_CFG_NON_SECURE_APPLICATION_FALLBACK (1U)
#endif


            #define OFS_SEQ1 0xA001A001 | (1 << 1) | (3 << 2)
            #define OFS_SEQ2 (15 << 4) | (3 << 8) | (3 << 10)
            #define OFS_SEQ3 (1 << 12) | (1 << 14) | (1 << 17)
            #define OFS_SEQ4 (3 << 18) |(15 << 20) | (3 << 24) | (3 << 26)
            #define OFS_SEQ5 (1 << 28) | (1 << 30)
            #define BSP_CFG_ROM_REG_OFS0 (OFS_SEQ1 | OFS_SEQ2 | OFS_SEQ3 | OFS_SEQ4 | OFS_SEQ5)

            #define BSP_CFG_ROM_REG_OFS2 (0xFFFFFFC0U | (1 << 0) | (1U << 1U) | (1U << 2U) | (1U << 3U) | (2U << 4U))

            /* WDT1 options: reserved OFS3 bits must be programmed as zero (HM 7.2.6). */
#ifndef BSP_CFG_ROM_REG_OFS3
#define BSP_CFG_ROM_REG_OFS3 (\
            (1 << 17) | \
            (3 << 18) | \
            (15 << 20) | \
            (3 << 24) | \
            (3 << 26) | \
            (1 << 28) | \
            (1 << 30))
#endif
#ifndef BSP_CFG_ROM_REG_OFS3_SEL
#define BSP_CFG_ROM_REG_OFS3_SEL (\
            ((0U << 17U)) | \
            ((0U << 18U)) | \
            ((0U << 20U)) | \
            ((0U << 24U)) | \
            ((0U << 26U)) | \
            ((0U << 28U)) | \
            ((0U << 30U)))
#endif

            /* Option Function Select Register 1 Security Attribution */
#ifndef BSP_CFG_ROM_REG_OFS1_SEL
#if defined(_RA_TZ_SECURE) || defined(_RA_TZ_NONSECURE)
            #define BSP_CFG_ROM_REG_OFS1_SEL (0x00000000U | ((0U << 0U)) | ((0U << 3U)) | ((0U << 5U)) | ((BSP_CFG_CLOCKS_SECURE == 0) ? 0xF00U : 0U) | ((0U << 24U)) | ((0U << 25U)))
#else
            #define BSP_CFG_ROM_REG_OFS1_SEL (0x00000000U)
#endif
#endif
            #define BSP_CFG_ROM_REG_OFS1_INITECCEN (0 << 25)
            /* HOCOFRQ0 uses the clock-tree encoding; reserved bits remain one (HM 7.2.4). */
            #define BSP_CFG_ROM_REG_OFS1 (0xFCFFF0D0U | (1 << 3) | (7) | (1 << 5) | (1 << 8) | (BSP_CFG_HOCO_FREQUENCY << 9U) | (1 << 24) | (BSP_CFG_ROM_REG_OFS1_INITECCEN))

            /* Used to create IELS values for the interrupt initialization table g_interrupt_event_link_select. */
            #define BSP_PRV_IELS_ENUM(vector)    (ELC_ ## vector)

            /* Dual Mode Select Register */
#ifndef BSP_CFG_ROM_REG_DUALSEL
            #define BSP_CFG_ROM_REG_DUALSEL (0xFFFFFFF8U | (0x7U))
#endif

            /* MRAM protection: HM 7.2.8-9, 60.8.3 and 60.9.1.2. */
#define BSP_CFG_ROM_REG_BPS_WORD_COUNT (16U)
#define BSP_CFG_ROM_REG_PBPS_WORD_COUNT (4U)
#ifndef BSP_CFG_ROM_REG_BPS0
#define BSP_CFG_ROM_REG_BPS0 (~( 0U))
#endif
#ifndef BSP_CFG_ROM_REG_BPS1
#define BSP_CFG_ROM_REG_BPS1 (~( 0U))
#endif
#ifndef BSP_CFG_ROM_REG_BPS2
#define BSP_CFG_ROM_REG_BPS2 (~( 0U))
#endif
#ifndef BSP_CFG_ROM_REG_BPS3
#define BSP_CFG_ROM_REG_BPS3 (~( 0U))
#endif
#ifndef BSP_CFG_ROM_REG_BPS4
#define BSP_CFG_ROM_REG_BPS4 (~( 0U))
#endif
#ifndef BSP_CFG_ROM_REG_BPS5
#define BSP_CFG_ROM_REG_BPS5 (~( 0U))
#endif
#ifndef BSP_CFG_ROM_REG_BPS6
#define BSP_CFG_ROM_REG_BPS6 (~( 0U))
#endif
#ifndef BSP_CFG_ROM_REG_BPS7
#define BSP_CFG_ROM_REG_BPS7 (~( 0U))
#endif
#ifndef BSP_CFG_ROM_REG_BPS8
#define BSP_CFG_ROM_REG_BPS8 (~( 0U))
#endif
#ifndef BSP_CFG_ROM_REG_BPS9
#define BSP_CFG_ROM_REG_BPS9 (~( 0U))
#endif
#ifndef BSP_CFG_ROM_REG_BPS10
#define BSP_CFG_ROM_REG_BPS10 (~( 0U))
#endif
#ifndef BSP_CFG_ROM_REG_BPS11
#define BSP_CFG_ROM_REG_BPS11 (~( 0U))
#endif
#ifndef BSP_CFG_ROM_REG_BPS12
#define BSP_CFG_ROM_REG_BPS12 (~( 0U))
#endif
#ifndef BSP_CFG_ROM_REG_BPS13
#define BSP_CFG_ROM_REG_BPS13 (~( 0U))
#endif
#ifndef BSP_CFG_ROM_REG_BPS14
#define BSP_CFG_ROM_REG_BPS14 (~( 0U))
#endif
#ifndef BSP_CFG_ROM_REG_BPS15
#define BSP_CFG_ROM_REG_BPS15 (~( 0U))
#endif
#ifndef BSP_CFG_ROM_REG_PBPS0
#define BSP_CFG_ROM_REG_PBPS0 (~( 0U))
#endif
#ifndef BSP_CFG_ROM_REG_PBPS1
#define BSP_CFG_ROM_REG_PBPS1 (~( 0U))
#endif
#ifndef BSP_CFG_ROM_REG_PBPS2
#define BSP_CFG_ROM_REG_PBPS2 (~( 0U))
#endif
#ifndef BSP_CFG_ROM_REG_PBPS3
#define BSP_CFG_ROM_REG_PBPS3 (~( 0U))
#endif
#ifndef BSP_CLOCK_CFG_MAIN_OSC_WAIT
            #define BSP_CLOCK_CFG_MAIN_OSC_WAIT (9)
#endif

            /* FSBL Control Register 0 */
#ifndef BSP_CFG_ROM_REG_FSBLCTRL0
#define BSP_CFG_ROM_REG_FSBLCTRL0 ( \
                (7 << 0U) | \
                (7 << 3U) | \
                (7 << 6U) | \
                (7 << 9U) | \
                0xFFFFF000)
#endif

            /* FSBL Control Register 1 */
#ifndef BSP_CFG_ROM_REG_FSBLCTRL1
#define BSP_CFG_ROM_REG_FSBLCTRL1 ( \
                (3 << 0U) | \
                0xFFFFFFFC)
#endif

            /* FSBL Control Register 2 */
#ifndef BSP_CFG_ROM_REG_FSBLCTRL2
#define BSP_CFG_ROM_REG_FSBLCTRL2 ( \
                (15 << 0U) | \
                (0x1F << 4U) | \
                0xFFFFFE00)
#endif

            /* Start Address of Code Certificate Register 0 */
#ifndef BSP_CFG_ROM_REG_SACC0
#define BSP_CFG_ROM_REG_SACC0 (0xFFFFFFFF)
#endif

            /* Start Address of Code Certificate Register 1 */
#ifndef BSP_CFG_ROM_REG_SACC1
#define BSP_CFG_ROM_REG_SACC1 (0xFFFFFFFF)
#endif

            /* Start Address of Measurement Report Register */
#ifndef BSP_CFG_ROM_REG_SAMR
#define BSP_CFG_ROM_REG_SAMR (0xFFFFFFFF)
#endif
#if (BSP_CFG_ROM_REG_FSBLCTRL0 != 0xFFFFFFFFU) || (BSP_CFG_ROM_REG_FSBLCTRL1 != 0xFFFFFFFFU) || \
    (BSP_CFG_ROM_REG_FSBLCTRL2 != 0xFFFFFFFFU) || (BSP_CFG_ROM_REG_SACC0 != 0xFFFFFFFFU) || \
    (BSP_CFG_ROM_REG_SACC1 != 0xFFFFFFFFU) || (BSP_CFG_ROM_REG_SAMR != 0xFFFFFFFFU)
#error "RA8P1 FSBL/SACC/SAMR provisioning is unsupported; retain disabled defaults and use an externally qualified provisioning process"
#endif

#ifndef BSP_CFG_DCACHE_ENABLED
#define BSP_CFG_DCACHE_ENABLED (0)
#endif


#ifndef BSP_CFG_SDRAM_ENABLED
 #define BSP_CFG_SDRAM_ENABLED  (0)
#endif

#ifndef BSP_CFG_SDRAM_TRAS
 #define BSP_CFG_SDRAM_TRAS  (6)
#endif

#ifndef BSP_CFG_SDRAM_TRCD
 #define BSP_CFG_SDRAM_TRCD  (3)
#endif

#ifndef BSP_CFG_SDRAM_TRP
 #define BSP_CFG_SDRAM_TRP  (3)
#endif

#ifndef BSP_CFG_SDRAM_TWR
 #define BSP_CFG_SDRAM_TWR  (2)
#endif

#ifndef BSP_CFG_SDRAM_TCL
 #define BSP_CFG_SDRAM_TCL  (3)
#endif

#ifndef BSP_CFG_SDRAM_TRFC
 #define BSP_CFG_SDRAM_TRFC  (937)
#endif

#ifndef BSP_CFG_SDRAM_TREFW
 #define BSP_CFG_SDRAM_TREFW  (8)
#endif

#ifndef BSP_CFG_SDRAM_INIT_ARFI
 #define BSP_CFG_SDRAM_INIT_ARFI  (10)
#endif

#ifndef BSP_CFG_SDRAM_INIT_ARFC
 #define BSP_CFG_SDRAM_INIT_ARFC  (8)
#endif

#ifndef BSP_CFG_SDRAM_INIT_PRC
 #define BSP_CFG_SDRAM_INIT_PRC  (3)
#endif

#ifndef BSP_CFG_SDRAM_MULTIPLEX_ADDR_SHIFT
 #define BSP_CFG_SDRAM_MULTIPLEX_ADDR_SHIFT  (1)
#endif

#ifndef BSP_CFG_SDRAM_ENDIAN_MODE
 #define BSP_CFG_SDRAM_ENDIAN_MODE  (0)
#endif

#ifndef BSP_CFG_SDRAM_ACCESS_MODE
 #define BSP_CFG_SDRAM_ACCESS_MODE  (1)
#endif

#ifndef BSP_CFG_SDRAM_BUS_WIDTH
 #define BSP_CFG_SDRAM_BUS_WIDTH  (0)
#endif
#endif /* BSP_MCU_FAMILY_CFG_H_ */
