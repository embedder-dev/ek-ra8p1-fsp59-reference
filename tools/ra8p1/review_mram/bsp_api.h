/* MRAM-only host fixture; registers use the production device header. */
#ifndef REVIEW_MRAM_BSP_H
#define REVIEW_MRAM_BSP_H
#define BSP_API_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "fsp_common_api.h"
#include "R7KA8P1KF.h"
typedef int IRQn_Type;
#define FSP_ASSERT(test) FSP_ERROR_RETURN((test), FSP_ERR_ASSERTION)
#define FSP_ERROR_RETURN(test, error) do { if (!(test)) { return (error); } } while (0)
#define BSP_PLACE_IN_SECTION(name)
#define SCB_CCR_DC_Msk 0x10000U
struct fixture_scb { uint32_t CCR; };
extern struct fixture_scb fixture_scb;
#define SCB (&fixture_scb)
uint32_t __get_PRIMASK(void);
void __set_PRIMASK(uint32_t mask);
void __disable_irq(void);
void fixture_barrier(int kind);
#define __DMB() fixture_barrier(0)
#define __DSB() fixture_barrier(1)
#define __ISB() fixture_barrier(2)
#define __NOP() fixture_barrier(3)
void SCB_DisableDCache(void);
void SCB_EnableDCache(void);
void SCB_InvalidateICache(void);
#endif
