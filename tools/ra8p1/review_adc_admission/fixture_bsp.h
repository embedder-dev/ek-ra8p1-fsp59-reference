/* Host services only; the assertions in fixture.c use manual values. */
#ifndef REVIEW_ADC_ADMISSION_BSP_H
#define REVIEW_ADC_ADMISSION_BSP_H
#include "../acquisition_adc_fixture_bsp.h"
#undef R_SYSTEM
typedef struct st_review_admission_system
{
    uint16_t PRCR_S;
    struct { uint8_t LOCK; } TEMPRLR_b;
    struct { uint8_t TSNKEEP; } TEMPRCR_b;
    uint8_t ADCCKCR, ADCCKDIVCR, GPTCKCR, GPTCKDIVCR;
} review_admission_system_t;
extern review_admission_system_t g_admission_system;
#define R_SYSTEM (&g_admission_system)
#define BSP_CFG_CLOCKS_SECURE 0
#define FSP_STYPE3_REG8_READ(reg, secure) (reg)
#define FSP_PRIV_CLOCK_PCLKA 12U
typedef uint32_t fsp_priv_source_clock_t;
uint32_t R_FSP_SystemClockHzGet(uint32_t clock);
uint32_t R_BSP_SourceClockHzGet(fsp_priv_source_clock_t source);
#endif
