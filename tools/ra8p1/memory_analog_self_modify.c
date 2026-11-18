/* Link this executable into the code-MRAM address range: modification must fail
 * before any register or source/destination access. No fixed memory mappings. */
#include "bsp_api.h"
#include "r_mram.h"
#include <assert.h>
#include <stdio.h>

fixture_mram_t fixture_mram;
struct fixture_scb fixture_scb;
static unsigned int accesses;
void fixture_barrier(int barrier) { (void)barrier; accesses++; }
uint32_t __get_PRIMASK(void) { accesses++; return 0; }
void __set_PRIMASK(uint32_t mask) { (void)mask; accesses++; }
void __disable_irq(void) { accesses++; }
void SCB_DisableDCache(void) { accesses++; }
void SCB_EnableDCache(void) { accesses++; }
void SCB_InvalidateICache(void) { accesses++; }

int main(void)
{
    mram_instance_ctrl_t ctrl = {0};
    mram_extended_cfg_t ext = {0x02080000U, 0x02082000U, 8U, true};
    flash_cfg_t cfg = {.p_extend = &ext};
    assert(R_MRAM_Open(&ctrl, &cfg) == FSP_SUCCESS);
    assert(R_MRAM_Write(&ctrl, 0x20000000U, 0x02080000U, 1U) == FSP_ERR_INVALID_LINKED_ADDRESS);
    assert(R_MRAM_Erase(&ctrl, 0x02080000U, 1U) == FSP_ERR_INVALID_LINKED_ADDRESS);
    assert(accesses == 0 && !ctrl.busy);
    puts("production self-modifying safety gate passed");
    return 0;
}
