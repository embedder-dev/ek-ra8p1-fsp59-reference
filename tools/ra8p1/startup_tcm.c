/* Controlled memory/register fixture: no MCU memory is accessed. */
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#ifndef BSP_TZ_NONSECURE_BUILD
#define BSP_TZ_NONSECURE_BUILD 0
#endif
#define BSP_TZ_CFG_SKIP_INIT 0
#define BSP_CFG_SKIP_INIT 0
#ifndef BSP_CFG_C_RUNTIME_INIT
#define BSP_CFG_C_RUNTIME_INIT 0
#endif
#define BSP_PRV_PRCR_KEY 0xA500U
#define R_TCM_TCMPRCR_S_PR_Msk 1U
#define R_TCM_TCMCRC_ECCMOD_Pos 2U
#define R_TCM_TCMCRS_ECCMOD_Pos 2U
#define R_TCM_TCMCRC_ECCMOD_Msk 0x0cU
#define R_TCM_TCMCRS_ECCMOD_Msk 0x0cU
#define R_TCM_TCMCRC_E1STSEN_Msk 0x10U
#define R_TCM_TCMCRS_E1STSEN_Msk 0x10U
#define R_TCM_TCMESCLR_CLRC0_Msk 1U
#define R_TCM_TCMESCLR_CLRC1_Msk 2U
#define R_TCM_TCMESCLR_CLRS0_Msk 4U
#define R_TCM_TCMESCLR_CLRS1_Msk 8U
static uint32_t ctcm[0x10000U / sizeof(uint32_t)];
static uint32_t stcm[0x10000U / sizeof(uint32_t)];
#define BSP_PRV_CTCM_SIZE sizeof(ctcm)
#define BSP_PRV_CTCM_BASE ((uintptr_t) ctcm)
#define BSP_PRV_STCM_BASE ((uintptr_t) stcm)
static struct { uint16_t TCMPRCR_S, TCMESCLR; uint8_t TCMCRC, TCMCRS; } regs;
#define R_TCM (&regs)
#if BSP_CFG_C_RUNTIME_INIT
static uint32_t image_c[] = {0xc001U, 0xc002U};
static uint32_t image_s[] = {0x5001U, 0x5002U};
#define __itcm_data_init_start image_c[0]
#define __itcm_data_init_end image_c[2]
#define __itcm_data_start ctcm[0]
#define __dtcm_data_init_start image_s[0]
#define __dtcm_data_init_end image_s[2]
#define __dtcm_data_start stcm[0]
#define __dtcm_bss_start stcm[2]
#define __dtcm_bss_end stcm[4]
#endif
static unsigned barriers;
static void barrier(void) {
    if (barriers == 1 || barriers == 2) {
        assert(regs.TCMCRC == 0x08U && regs.TCMCRS == 0x08U);
        assert(regs.TCMPRCR_S == 0xA501U);
    }
    if (barriers >= 2) {
        for (unsigned i = 0; i < sizeof(ctcm) / sizeof(ctcm[0]); i++) {
            assert(ctcm[i] == 0 && stcm[i] == 0);
        }
    }
    if (barriers == 3) {
        assert(regs.TCMCRC == 0x1cU && regs.TCMCRS == 0x1cU);
        assert(regs.TCMESCLR == 0x0fU);
    }
    barriers++;
}
#define __DMB() barrier()
#define __DSB() ((void) 0)
#define __ISB() ((void) 0)
/* PRODUCTION */
int main(void) {
    for (unsigned i = 0; i < sizeof(ctcm) / sizeof(ctcm[0]); i++) {
        ctcm[i] = stcm[i] = 0xdeadbeefU;
    }
    bsp_init_ctcm();
    assert(barriers == 4);
    assert(regs.TCMPRCR_S == 0xA500U);
#if BSP_CFG_C_RUNTIME_INIT
    assert(ctcm[0] == image_c[0] && ctcm[1] == image_c[1]);
    assert(stcm[0] == image_s[0] && stcm[1] == image_s[1]);
    assert(stcm[2] == 0U && stcm[3] == 0U);
#endif
    return 0;
}
