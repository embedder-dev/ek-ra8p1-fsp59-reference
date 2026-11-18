#ifndef REVIEW_CGC_BSP_API_H
#define REVIEW_CGC_BSP_API_H
#include "../cgc_test/bsp_api.h"
#undef FSP_HARDWARE_REGISTER_WAIT
/* Evaluate after the hook, so a busy register can become ready before its first access. */
#define FSP_HARDWARE_REGISTER_WAIT(reg, value) do { \
    review_wait_before(#reg); \
    cgc_test_wait((uint32_t) (reg), (uint32_t) (value), #reg); \
} while (0)
void review_wait_before(char const * reg);
#endif
