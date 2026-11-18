/* Host services for production ADC_B. Layout comes from the stock or manual-derived candidate device header. */
#ifndef ACQUISITION_ADC_FIXTURE_BSP_H
#define ACQUISITION_ADC_FIXTURE_BSP_H
#define BSP_API_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <assert.h>
#include "fsp_common_api.h"
typedef int32_t IRQn_Type;
typedef uint32_t elc_event_t;
#define __PACKED_STRUCT struct __attribute__((packed))
#define BSP_CMSE_NONSECURE_CALL
#define BSP_TZ_SECURE_BUILD 0
#define FSP_CONTEXT_SAVE
#define FSP_CONTEXT_RESTORE
#define FSP_ASSERT(condition) do { if (!(condition)) { return FSP_ERR_ASSERTION; } } while (0)
#define FSP_ERROR_RETURN(condition, error) do { if (!(condition)) { return (error); } } while (0)
#define FSP_ERROR_LOG(error) ((void) (error))
#define FSP_REGISTER_READ(reg) ((void) (reg))
#define FSP_HARDWARE_REGISTER_WAIT(reg, expected) acquisition_adc_wait(&(reg), (expected));
#define R_BSP_MODULE_START(ip, channel) acquisition_adc_module(true, (ip), (channel))
#define R_BSP_MODULE_STOP(ip, channel) acquisition_adc_module(false, (ip), (channel))
#define FSP_IP_ADC 0U
#define FSP_IP_GPT 1U
#define FSP_IP_TSN 2U
#define ELC_EVENT_NONE 0U
#define __I volatile const
static inline uint32_t __RBIT(uint32_t value)
{
    uint32_t reversed = 0U;
    for (unsigned bit = 0U; bit < 32U; bit++) { reversed = (reversed << 1) | (value & 1U); value >>= 1; }
    return reversed;
}
static inline uint32_t __CLZ(uint32_t value) { return value ? (uint32_t) __builtin_clz(value) : 32U; }
#define BSP_DELAY_UNITS_MICROSECONDS 0U
#define BSP_FEATURE_ADC_B_PGA_SUPPORTED 0
#define BSP_FEATURE_TSN_CALIBRATION32_MASK UINT32_MAX
#define BSP_FEATURE_TSN_SLOPE 1
#define __IM volatile
#define __OM volatile
#define __IOM volatile
#include "acquisition_adc_registers.h"
extern R_ADC_B0_Type g_acquisition_adc;
#define R_ADC_B (&g_acquisition_adc)
typedef struct st_acquisition_tsn { struct { uint32_t TSEN; uint32_t TSOE; } TSCR_b; } acquisition_tsn_t;
extern acquisition_tsn_t g_acquisition_tsn;
extern struct st_acquisition_cal { uint32_t TSCDR; } g_acquisition_cal;
#define R_TSN_CTRL (&g_acquisition_tsn)
#define R_TSN_CAL (&g_acquisition_cal)
#if BSP_FEATURE_ADC_B_REGISTER_TYPE == 1
typedef struct st_acquisition_system
{
    uint16_t PRCR_S;
    struct { uint8_t LOCK; } TEMPRLR_b;
    struct { uint8_t TSNKEEP; } TEMPRCR_b;
    uint8_t ADCCKCR, ADCCKDIVCR, GPTCKCR, GPTCKDIVCR;
} acquisition_system_t;
extern acquisition_system_t g_acquisition_system;
#define R_SYSTEM (&g_acquisition_system)
#define R_SYSTEM_TEMPRCR_TSNKEEP_Msk (0x08UL)
#define R_SYSTEM_PRCR_S_PRC5_Msk (0x20UL)
#define FSP_CRITICAL_SECTION_DEFINE
#define FSP_CRITICAL_SECTION_ENTER ((void) 0)
#define FSP_CRITICAL_SECTION_EXIT ((void) 0)
#endif
void acquisition_adc_wait(volatile uint32_t * reg, uint32_t expected);
void acquisition_adc_module(bool start, uint32_t ip, uint32_t channel);
void R_BSP_IrqCfgEnable(IRQn_Type irq, uint8_t ipl, void * ctx);
void R_BSP_IrqDisable(IRQn_Type irq);
void R_BSP_IrqStatusClear(IRQn_Type irq);
void * R_FSP_IsrContextGet(IRQn_Type irq);
void R_FSP_IsrContextSet(IRQn_Type irq, void * ctx);
IRQn_Type R_FSP_CurrentIrqGet(void);
void R_BSP_SoftwareDelay(uint32_t delay, uint32_t units);
#endif
