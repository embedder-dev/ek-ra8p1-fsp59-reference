#ifndef REVIEW_AGT_BSP_API_H
#define REVIEW_AGT_BSP_API_H
#define BSP_API_H
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "fsp_common_api.h"
#include "bsp_feature.h"
#define __IOM volatile
#define __IM volatile const
#define __OM volatile
/* Use the actual target's AGT16 layout and masks. The unused AGT32 view only
 * lets pristine 5.9 C compile as a negative control; no test selects AGTW. */
#define R_AGTX0_Type review_target_agt_t
#include "R7KA8P1KF.h"
#undef R_AGTX0_Type
#undef R_AGT0
#undef R_AGT1
#undef R_AGTX0_BASE
#undef R_AGTX1_BASE
typedef union st_review_agt
{
    struct
    {
        volatile uint16_t AGT;
        volatile uint16_t AGTCMA;
        volatile uint16_t AGTCMB;
        uint16_t reserved;
        R_AGTX0_AGT16_CTRL_Type CTRL;
    } AGT16;
    struct
    {
        volatile uint32_t AGT;
        volatile uint32_t AGTCMA;
        volatile uint32_t AGTCMB;
        R_AGTX0_AGT16_CTRL_Type CTRL;
    } AGT32;
    uint8_t stride[0x100];
} R_AGTX0_Type;
/* The pristine compile-only AGTW alternate view is never selected. */
#define AGTIOSEL_ALT AGTIOSEL
extern R_AGTX0_Type review_regs[2];
#define R_AGT0 (&review_regs[0])
#define R_AGT1 (&review_regs[1])
#define R_AGTX0_BASE 0x40221000U
#define R_AGTX1_BASE 0x40221100U
#define FSP_PRIV_CLOCK_PCLKB 0
#define FSP_IP_AGT 0
#define BSP_DELAY_UNITS_MICROSECONDS 1
#define BSP_CMSE_NONSECURE_CALL
#define BSP_CMSE_NONSECURE_ENTRY
#define FSP_CONTEXT_SAVE do {} while (0);
#define FSP_CONTEXT_RESTORE do {} while (0);
#define FSP_INVALID_VECTOR (-1)
#define FSP_RETURN(e) return (e)
#define FSP_ERROR_RETURN(c,e) do { if (!(c)) return (e); } while (0)
#define FSP_ASSERT(c) FSP_ERROR_RETURN(c, FSP_ERR_ASSERTION)
#define FSP_HARDWARE_REGISTER_WAIT(expected,field) review_wait((expected), &p_reg_ctrl->AGTCR)
#define FSP_CRITICAL_SECTION_DEFINE unsigned review_saved_mask
#define FSP_CRITICAL_SECTION_ENTER review_saved_mask = review_critical_enter()
#define FSP_CRITICAL_SECTION_EXIT review_critical_exit(review_saved_mask)
#define R_BSP_MODULE_START(ip,ch) review_module_start(ch)
#define CMSE_AU_NONSECURE 1
void * review_cmse_address(void * p);
void * review_cmse_memory(void * p);
int review_cmse_ns(void (*p)(void *));
#define cmse_check_address_range(p,s,f) review_cmse_address(p)
#define cmse_check_pointed_object(p,f) review_cmse_memory(p)
#define cmse_nsfptr_create(p) (p)
#define cmse_is_nsfptr(p) review_cmse_ns((void (*)(void *))(p))
void review_module_start(unsigned channel);
void review_wait(unsigned value, volatile uint8_t * reg);
void review_write8(volatile uint8_t * reg, uint8_t value);
void review_write16(volatile uint16_t * reg, uint16_t value);
void review_write_tck(volatile uint8_t * reg, uint8_t value);
unsigned review_critical_enter(void);
void review_critical_exit(unsigned saved);
void review_publication_point(void * p);
void R_BSP_SoftwareDelay(uint32_t delay, int units);
uint32_t R_FSP_SystemClockHzGet(int clock);
void R_BSP_IrqCfgEnable(IRQn_Type irq, uint32_t ipl, void * context);
void NVIC_DisableIRQ(IRQn_Type irq);
void R_FSP_IsrContextSet(IRQn_Type irq, void * context);
void * R_FSP_IsrContextGet(IRQn_Type irq);
IRQn_Type R_FSP_CurrentIrqGet(void);
void R_BSP_IrqStatusClear(IRQn_Type irq);
#endif
