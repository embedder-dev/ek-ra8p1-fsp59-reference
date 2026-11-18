/* Controlled host register fixture, independently transcribed from RA8P1 HM ch50.
 * This is not a target header and is never packaged into firmware. */
#ifndef ACQUISITION_FIXTURE_BSP_H
#define ACQUISITION_FIXTURE_BSP_H
#define BSP_API_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <limits.h>
#include "fsp_common_api.h"

typedef int IRQn_Type;
typedef struct st_acquisition_pdm_channel
{
    volatile uint32_t PDSTRTR, PDSTPTR, PDCHGTR, PDICR, PDSDCR, PDSR, PDSCR, reserved1;
    volatile uint32_t PDMDSR, PDSFCR, PDHFCS0R, PDHFCK1R, PDHFCH0R, PDHFCH1R;
    volatile uint32_t PDCFCH00R, PDCFCH01R, PDCFCH02R, PDCFCH03R, PDCFCH04R, PDCFCH05R;
    volatile uint32_t PDCFCH06R, PDCFCH07R, PDCFCH08R, PDCFCH09R, PDCFCH10R;
    volatile uint32_t PDLFCH010R;
    volatile uint32_t PDLFCH100R, PDLFCH101R, PDLFCH102R, PDLFCH103R, PDLFCH104R;
    volatile uint32_t PDLFCH105R, PDLFCH106R, PDLFCH107R, PDLFCH108R, PDLFCH109R;
    volatile uint32_t PDLFCH110R, PDLFCH111R, PDLFCH112R, PDLFCH113R, PDLFCH114R;
    volatile uint32_t PDLFCH115R, PDLFCH116R, PDLFCH117R, PDLFCH118R, PDLFCH119R;
    volatile uint32_t PDSDLTR, PDSDUTR, PDDBCR, PDSCTSR, PDOVLTR, PDOVUTR;
    uint32_t reserved2[4];
    volatile uint32_t PDDRCR, PDDCR, PDDRR, PDDSR;
    uint32_t reserved3[4];
} R_PDM_CH_Type;
typedef struct st_acquisition_pdm
{
    uint32_t reserved[64];
    R_PDM_CH_Type CH[3];
} acquisition_pdm_t;
extern acquisition_pdm_t g_acquisition_pdm;
#define R_PDM (&g_acquisition_pdm)
#define R_PDM_CH_PDICR_IDRE_Msk (1U << 2)
#define R_PDM_CH_PDICR_IEDE_Msk (1U << 16)
#define R_PDM_CH_PDSR_STATE_Msk (1U << 0)
#define R_PDM_CH_PDSDCR_BFOWDE_Msk (1U << 27)
#define R_PDM_CH_PDSDCR_SCDE_Msk (1U << 16)
#define R_PDM_CH_PDSDCR_OVLDE_Msk (1U << 17)
#define R_PDM_CH_PDSDCR_OVUDE_Msk (1U << 18)
#define R_PDM_CH_PDSCR_SDFC_Msk (1U << 1)
#define R_PDM_CH_PDMDSR_SFMD_Pos (4U)
#define R_PDM_CH_PDMDSR_HFIS_Pos (8U)
#define R_PDM_CH_PDMDSR_CFIS_Pos (12U)
#define R_PDM_CH_PDMDSR_LFIS_Pos (16U)
#define R_PDM_CH_PDMDSR_DBIS_Pos (28U)
#define R_PDM_CH_PDSFCR_SINCDEC_Pos (16U)
#define R_PDM_CH_PDSFCR_SINCRNG_Pos (24U)
#define BSP_FEATURE_PDM_CHANNELS (7U)
#define FSP_IP_PDM (0U)
#define FSP_PRIV_CLOCK_PCLKB (0U)
#define BSP_DELAY_UNITS_MICROSECONDS (0U)
#define FSP_INVALID_VECTOR (-1)
#define FSP_ASSERT(condition) do { if (!(condition)) { return FSP_ERR_ASSERTION; } } while (0)
#define FSP_ERROR_RETURN(condition, error) do { if (!(condition)) { return (error); } } while (0)
#define FSP_CONTEXT_SAVE
#define FSP_CONTEXT_RESTORE
#define R_BSP_MODULE_START(ip, channel) acquisition_module_start((ip), (channel))
void acquisition_module_start(uint32_t ip, uint32_t channel);
void * R_FSP_IsrContextGet(IRQn_Type irq);
void R_FSP_IsrContextSet(IRQn_Type irq, void * context);
IRQn_Type R_FSP_CurrentIrqGet(void);
void R_BSP_IrqCfgEnable(IRQn_Type irq, uint32_t ipl, void * context);
void R_BSP_IrqDisable(IRQn_Type irq);
void R_BSP_IrqEnable(IRQn_Type irq);
void R_BSP_IrqStatusClear(IRQn_Type irq);
void NVIC_SetPendingIRQ(IRQn_Type irq);
void R_BSP_SoftwareDelay(uint32_t delay, uint32_t units);
uint32_t R_FSP_SystemClockHzGet(uint32_t clock);

/* The secure build is tested as host C with controlled CMSE address classification. */
#if BSP_TZ_SECURE_BUILD
#define BSP_CMSE_NONSECURE_CALL
#define BSP_CMSE_NONSECURE_ENTRY
#define CMSE_AU_NONSECURE (1U)
#define CMSE_MPU_READWRITE (2U)
extern bool g_acquisition_ns_callback;
extern bool g_acquisition_ns_memory;
extern void * g_acquisition_callback_address;
void * acquisition_cmse_range(void * p, size_t size, unsigned flags);
#define cmse_check_address_range(p, size, flags) acquisition_cmse_range((void *) (p), (size), (flags))
#define cmse_check_pointed_object(p, flags) cmse_check_address_range((p), sizeof(*(p)), (flags))
#define cmse_is_nsfptr(p) (g_acquisition_ns_callback && ((void *) (p) == g_acquisition_callback_address))
#define cmse_nsfptr_create(p) (p)
#endif
#endif
