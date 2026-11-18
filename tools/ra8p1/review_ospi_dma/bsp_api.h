#ifndef REVIEW_OSPI_DMA_BSP_H
#define REVIEW_OSPI_DMA_BSP_H
#include "../review_peripheral_capabilities/bsp_api.h"
#undef BSP_TZ_SECURE_BUILD
#undef BSP_TZ_NONSECURE_BUILD
#define BSP_TZ_SECURE_BUILD (!REVIEW_NONSECURE)
#define BSP_TZ_NONSECURE_BUILD REVIEW_NONSECURE
#include "dma_registers.h"
#undef R_BSP_MODULE_STOP
#define R_BSP_MODULE_STOP(ip,ch) review_module_stop(ip,ch)
void review_module_stop(unsigned ip, unsigned channel);
typedef uint32_t elc_event_t;
#define ELC_EVENT_NONE (0U)
#define FSP_IP_DMAC (3U)
#endif
