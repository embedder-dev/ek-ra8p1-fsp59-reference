/* Host-only fixture: widths/offsets derived from HM55.2 and HM60.5, not an SVD. */
#ifndef MEMORY_ANALOG_BSP_H
#define MEMORY_ANALOG_BSP_H
#define BSP_API_H
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#if BSP_TZ_SECURE_BUILD
 #define CMSE_AU_NONSECURE 1U
 #define CMSE_MPU_READWRITE 2U
 void * fixture_cmse_range(void * p, size_t size, unsigned flags);
 #define cmse_check_address_range(p, size, flags) fixture_cmse_range((void *) (p), (size), (flags))
 #define cmse_check_pointed_object(p, flags) cmse_check_address_range((p), sizeof(*(p)), (flags))
 #define cmse_nsfptr_create(p) (p)
#endif
#include "fsp_common_api.h"
typedef int IRQn_Type;
#define FSP_ASSERT(test) FSP_ERROR_RETURN((test), FSP_ERR_ASSERTION)
#define FSP_ERROR_RETURN(test, error) do { if (!(test)) { return (error); } } while (0)
#define BSP_PLACE_IN_SECTION(name)
#define BSP_FEATURE_DAC_B_CHANNEL_MASK 3U
#define BSP_DELAY_UNITS_MICROSECONDS 0
#define FSP_IP_DAC 0
#define R_BSP_MODULE_START(ip, unit) fixture_module_start(unit)
#define R_BSP_MODULE_STOP(ip, unit) fixture_module_stop(unit)
#define FSP_CRITICAL_SECTION_DEFINE uint32_t fixture_saved_mask
#define FSP_CRITICAL_SECTION_ENTER fixture_saved_mask = __get_PRIMASK(); __disable_irq()
#define FSP_CRITICAL_SECTION_EXIT __set_PRIMASK(fixture_saved_mask)
#if defined(MEMORY_ANALOG_REAL_HEADER)
 #include "R7KA8P1KF.h"
 #undef R_MRAM
 #undef R_DAC_B0
 #undef R_DAC_B1
#else
 #define __DCACHE_PRESENT 1U
 #define __ICACHE_PRESENT 1U
#endif
#define SCB_CCR_DC_Msk 0x10000U
#define SCB_CCR_IC_Msk 0x20000U
struct fixture_scb { uint32_t CCR; };
extern struct fixture_scb fixture_scb;
#define SCB (&fixture_scb)
void fixture_barrier(int barrier);
void fixture_module_start(uint8_t unit);
void fixture_module_stop(uint8_t unit);
void R_BSP_SoftwareDelay(uint32_t duration, int units);
uint32_t __get_PRIMASK(void);
void __set_PRIMASK(uint32_t mask);
void __disable_irq(void);
#define __DMB() fixture_barrier(0)
#define __DSB() fixture_barrier(1)
#define __ISB() fixture_barrier(2)
#define __NOP() fixture_barrier(3)
void SCB_DisableDCache(void);
void SCB_EnableDCache(void);
void SCB_InvalidateICache(void);

#if defined(MEMORY_ANALOG_REAL_HEADER)
typedef R_MRAM_Type fixture_mram_t;
#else
typedef struct
{
    volatile uint8_t MRCPFB;
    uint8_t reserved0[0x3FF];
    volatile uint8_t MREZS;
    uint8_t reserved1[0x1C0F];
    volatile uint8_t MASTAT;
    uint8_t reserved2[0x1F];
    volatile uint32_t MSADDR;
    uint8_t reserved_msaddr[0x14];
    volatile uint8_t MCNTSELR;
    uint8_t reserved3[3];
    volatile uint32_t MCNTDTR0;
    volatile uint32_t MCNTDTR1;
    uint8_t reserved4[0xC];
    volatile uint16_t MCTRCNTR;
    uint8_t reserved5[2];
    volatile uint8_t MCTRLSR;
    uint8_t reserved6[7];
    volatile uint8_t MCTRSTATR;
    uint8_t reserved7[0x13];
    volatile uint32_t MSTATR;
    volatile uint16_t MENTRYR;
    uint8_t reserved8[0x56];
    volatile uint32_t MSUASMON;
    uint8_t reserved9[8];
    volatile uint16_t MSUACR;
    uint8_t reserved10[0xF16];
    volatile uint16_t MRCPC0;
    uint8_t reserved11[2];
    volatile uint16_t MRCPC1;
    uint8_t reserved12[0xA];
    volatile uint8_t MRCPS;
    uint8_t reserved13[0x1F];
    volatile uint16_t MRCFLR;
} fixture_mram_t;
#endif
extern fixture_mram_t fixture_mram;
#define R_MRAM (&fixture_mram)

#if !defined(MEMORY_ANALOG_REAL_HEADER)
typedef struct
{
    volatile uint16_t DADR;
    uint16_t reserved;
    volatile uint32_t DACR0;
    volatile uint32_t DACR1;
    volatile uint32_t DACR2;
} R_DAC_B0_Type;
#endif
extern R_DAC_B0_Type fixture_dac[2];
#define R_DAC_B0 (&fixture_dac[0])
#define R_DAC_B1 (&fixture_dac[1])
#endif
