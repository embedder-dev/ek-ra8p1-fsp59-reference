/* Reuse host services only; assertions/oracles live in this independent fixture. */
#ifndef REVIEW_ADC_FIXTURE_BSP_H
#define REVIEW_ADC_FIXTURE_BSP_H
#include "../acquisition_adc_fixture_bsp.h"
#if BSP_FEATURE_ADC_B_REGISTER_TYPE == 1
/* Clock services added by the ADC stop-delay repair; not FIFO/calibration oracles. */
#undef R_SYSTEM
typedef struct st_review_mmio_system
{
    uint16_t PRCR_S;
    struct { uint8_t LOCK; } TEMPRLR_b;
    struct { uint8_t TSNKEEP; } TEMPRCR_b;
    uint8_t ADCCKCR, ADCCKDIVCR, GPTCKCR, GPTCKDIVCR;
} review_mmio_system_t;
static review_mmio_system_t g_review_mmio_system __attribute__((unused));
#define R_SYSTEM (&g_review_mmio_system)
#define BSP_CFG_CLOCKS_SECURE 0
#define FSP_STYPE3_REG8_READ(reg, secure) (reg)
#define FSP_PRIV_CLOCK_PCLKA 12U
typedef uint32_t fsp_priv_source_clock_t;
static inline uint32_t R_FSP_SystemClockHzGet(uint32_t clock) { (void) clock; return 120000000U; }
static inline uint32_t R_BSP_SourceClockHzGet(fsp_priv_source_clock_t source) { (void) source; return 60000000U; }
#endif
#if defined(REVIEW_ADC_ARM)
 #undef R_ADC_B
 #define R_ADC_B ((R_ADC_B0_Type *) 0x40338000UL)
#endif
#endif
