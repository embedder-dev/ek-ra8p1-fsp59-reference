/* Linker bounds are inputs; encoding calls are observable before MPU writes. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "bsp_feature.h"

#undef BSP_FEATURE_SDRAM_START_ADDRESS
#define BSP_FEATURE_SDRAM_START_ADDRESS TEST_SDRAM
#define ARMV8_MPU_REGION_MIN_SIZE 32U
#define MPU_RBAR_BASE_Msk 0xFFFFFFE0U
#define MPU_RBAR_BASE_Pos 5U
#define MPU_RBAR_SH_Pos 3U
#define MPU_RBAR_SH_Msk 0x18U
#define MPU_RBAR_AP_Pos 1U
#define MPU_RBAR_AP_Msk 6U
#define MPU_RBAR_XN_Pos 0U
#define MPU_RBAR_XN_Msk 1U
#define MPU_RLAR_LIMIT_Msk 0xFFFFFFE0U
#define MPU_RLAR_LIMIT_Pos 5U
#define MPU_RLAR_AttrIndx_Pos 1U
#define MPU_RLAR_AttrIndx_Msk 0xEU
#define MPU_RLAR_EN_Msk 1U
#define MPU_CTRL_PRIVDEFENA_Msk 4U
#define ARM_MPU_SH_NON 0U
#define ARM_MPU_ATTR_NON_CACHEABLE 4U
#define ARM_MPU_ATTR(outer, inner) (((outer) << 4U) | (inner))
typedef struct { uint32_t RBAR, RLAR; } ARM_MPU_Region_t;

/* CMSIS ENCODINGS */

static uint32_t bounds[4];
#define __nocache_start (*(uint32_t *) (uintptr_t) bounds[0])
#define __nocache_end (*(uint32_t *) (uintptr_t) bounds[1])
#define __nocache_sdram_start (*(uint32_t *) (uintptr_t) bounds[2])
#define __nocache_sdram_end (*(uint32_t *) (uintptr_t) bounds[3])
static unsigned encoded_bases, encoded_limits, regions;
static uint32_t emitted_bases[2], emitted_limits[2];
static uint32_t encode_base(uint32_t base, uint32_t sh, uint32_t ro, uint32_t np, uint32_t xn)
{
    encoded_bases++;
    return STOCK_ARM_MPU_RBAR(base, sh, ro, np, xn);
}
static uint32_t encode_limit(uint32_t limit, uint32_t index)
{
    encoded_limits++;
    return STOCK_ARM_MPU_RLAR(limit, index);
}
#define ARM_MPU_RBAR(base, sh, ro, np, xn) encode_base(base, sh, ro, np, xn)
#define ARM_MPU_RLAR(limit, index) encode_limit(limit, index)
static void ARM_MPU_SetMemAttr(unsigned index, uint32_t attribute)
{
    assert(index == 0U && attribute == 0x44U);
}
static void ARM_MPU_SetRegion(unsigned index, uint32_t base, uint32_t limit)
{
    assert(index < 2U);
    emitted_bases[index] = base;
    emitted_limits[index] = limit;
    regions++;
}
static void ARM_MPU_Enable(uint32_t control)
{
    assert(control == 4U);
}

/* MPU FUNCTION */
#line 2000 "fixture.c"

int main(int argc, char ** argv)
{
    assert(argc == 5);
    for (unsigned i = 0; i < 4U; i++)
    {
        bounds[i] = (uint32_t) strtoul(argv[i + 1U], NULL, 0);
    }
    bsp_init_mpu();
    printf("%u %u %u %08x %08x %08x %08x\n", encoded_bases, encoded_limits, regions,
           emitted_bases[0], emitted_limits[0], emitted_bases[1], emitted_limits[1]);
    return 0;
}
