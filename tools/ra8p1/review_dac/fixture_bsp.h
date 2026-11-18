#ifndef REVIEW_DAC_FIXTURE_BSP_H
#define REVIEW_DAC_FIXTURE_BSP_H
#define BSP_API_H

#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "fsp_common_api.h"

/* Hardware-side hooks need to update the production header's read-only status fields. */
#define __IM volatile
#define __OM volatile
#define __IOM volatile
#include "dac_registers.h"

extern R_MRAM_Type test_mram;
extern R_DAC_B0_Type test_dac[2];
#define R_MRAM (&test_mram)
#define R_DAC_B0 (&test_dac[0])
#define R_DAC_B1 (&test_dac[1])

void test_enter(void);
void test_exit(void);
void test_start(unsigned int channel);
void test_stop(unsigned int channel);
void test_dsb(void);
void test_nop(void);
void test_delay(uint32_t delay, unsigned int units);

#define FSP_ASSERT(condition) FSP_ERROR_RETURN(condition, FSP_ERR_ASSERTION)
#define FSP_ERROR_RETURN(condition, error) do { if (!(condition)) { return (error); } } while (0)
#define FSP_CRITICAL_SECTION_DEFINE
#define FSP_CRITICAL_SECTION_ENTER test_enter()
#define FSP_CRITICAL_SECTION_EXIT test_exit()
#define R_BSP_MODULE_START(ip, channel) test_start(channel)
#define R_BSP_MODULE_STOP(ip, channel) test_stop(channel)
#define R_BSP_SoftwareDelay(delay, units) test_delay(delay, units)
#define BSP_DELAY_UNITS_MICROSECONDS (1U)
#define __DSB() test_dsb()
#define __NOP() test_nop()

#endif
