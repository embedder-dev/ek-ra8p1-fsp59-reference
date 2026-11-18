/* Only the CPU entry/state preconditions are modeled; allocator/free-list code is original FSP 5.9. */
#include "bsp_api.h"
#undef BSP_TZ_SECURE_BUILD
#define BSP_TZ_SECURE_BUILD 1
#define __get_IPSR() 1U
#define __get_CONTROL() 2U
#define __set_CONTROL(x) ((void) (x))
#define __set_PSPLIM(x) ((void) (x))
#define __set_PSP(x) ((void) (x))
