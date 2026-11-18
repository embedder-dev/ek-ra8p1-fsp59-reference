/* Compile/link fixture only. Register and processor definitions are the real
 * generated device header and preserved stock CMSIS, never fixture registers.
 */
#ifndef MEMORY_ANALOG_TARGET_BSP_H
#define MEMORY_ANALOG_TARGET_BSP_H
#define BSP_API_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "fsp_common_api.h"
#include "bsp_exceptions.h"
#include "R7KA8P1KF.h"
#include "bsp_feature.h"
#include "bsp_peripheral.h"
#define FSP_ASSERT(test) FSP_ERROR_RETURN((test), FSP_ERR_ASSERTION)
#define FSP_ERROR_RETURN(test, error) do { if (!(test)) { return (error); } } while (0)
#define BSP_PLACE_IN_SECTION(name) __attribute__((section(name)))
#define BSP_DELAY_UNITS_MICROSECONDS 0
#define FSP_IP_DAC 0
#define R_BSP_MODULE_START(ip, unit) fixture_module_start(unit)
#define R_BSP_MODULE_STOP(ip, unit) fixture_module_stop(unit)
#define FSP_CRITICAL_SECTION_DEFINE uint32_t fixture_saved_mask
#define FSP_CRITICAL_SECTION_ENTER fixture_saved_mask = __get_PRIMASK(); __disable_irq()
#define FSP_CRITICAL_SECTION_EXIT __set_PRIMASK(fixture_saved_mask)
void fixture_module_start(uint8_t unit);
void fixture_module_stop(uint8_t unit);
void R_BSP_SoftwareDelay(uint32_t duration, int units);
#endif
