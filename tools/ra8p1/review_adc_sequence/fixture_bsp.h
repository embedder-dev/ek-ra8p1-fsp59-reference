#ifndef REVIEW_ADC_SEQUENCE_BSP_H
#define REVIEW_ADC_SEQUENCE_BSP_H
#include "../acquisition_adc_fixture_bsp.h"
#undef R_SYSTEM
typedef struct st_review_system
{
    uint16_t PRCR_S;
    struct { uint8_t LOCK; } TEMPRLR_b;
    struct { uint8_t TSNKEEP; } TEMPRCR_b;
    uint8_t ADCCKCR, ADCCKDIVCR, GPTCKCR, GPTCKDIVCR;
} review_system_t;
extern review_system_t g_review_system;
#define R_SYSTEM (&g_review_system)
#define BSP_CFG_CLOCKS_SECURE 0
#define FSP_STYPE3_REG8_READ(reg, secure) (reg)
#define FSP_PRIV_CLOCK_PCLKA 12U
uint32_t R_FSP_SystemClockHzGet(uint32_t clock);
typedef uint32_t fsp_priv_source_clock_t;
uint32_t R_BSP_SourceClockHzGet(fsp_priv_source_clock_t source);
#undef FSP_REGISTER_READ
#define FSP_REGISTER_READ(reg) review_adc_read(&(reg))
void review_adc_read(volatile uint32_t * reg);
#undef FSP_CRITICAL_SECTION_DEFINE
#undef FSP_CRITICAL_SECTION_ENTER
#undef FSP_CRITICAL_SECTION_EXIT
#define FSP_CRITICAL_SECTION_DEFINE
#define FSP_CRITICAL_SECTION_ENTER review_adc_lock()
#define FSP_CRITICAL_SECTION_EXIT review_adc_unlock()
void review_adc_lock(void);
void review_adc_unlock(void);
#endif
