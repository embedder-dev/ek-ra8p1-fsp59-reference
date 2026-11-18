/* Minimal ROM translation-unit inputs; capabilities come from the production MCU. */
#ifndef REVIEW_ROM_BSP_API_H
#define REVIEW_ROM_BSP_API_H

#include <stdint.h>

#define BSP_CFG_XTAL_HZ              (24000000U)
#include "bsp_feature.h"

#define BSP_DONT_REMOVE              __attribute__((used))
#define BSP_PLACE_IN_SECTION(name)   __attribute__((section(name)))
#define BSP_CFG_HOCO_FREQUENCY       (0U)
#define BSP_CFG_ROM_REG_OFS0         (0xFFFFFFFFU)
#define BSP_CFG_ROM_REG_OFS1         (0xFCFFF0D0U)
#define BSP_CFG_ROM_REG_OFS2         (0xFFFFFFFFU)
#define BSP_CFG_ROM_REG_OFS3         (0xFFFFFFFFU)
#define BSP_CFG_ROM_REG_OFS1_SEL     (0x00000000U)
#define BSP_CFG_ROM_REG_OFS3_SEL     (0x00000000U)

#ifndef REVIEW_REDUCED_POLICY
 #include "all_ones_policy.h"
#endif

#endif
