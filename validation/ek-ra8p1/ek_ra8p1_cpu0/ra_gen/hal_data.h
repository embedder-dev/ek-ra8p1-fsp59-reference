/* generated HAL header file - do not edit */
#ifndef HAL_DATA_H_
#define HAL_DATA_H_
#include <stdint.h>
#include "bsp_api.h"
#include "common_data.h"
#include "r_pdm.h"
#include "r_wdt.h"
#include "r_wdt_api.h"
#include "r_gpt.h"
#include "r_timer_api.h"
#include "r_sci_b_uart.h"
            #include "r_uart_api.h"
FSP_HEADER
extern pdm_instance_t const g_bench_pdm;
extern pdm_instance_ctrl_t g_bench_pdm_ctrl;
extern pdm_cfg_t const g_bench_pdm_cfg;
#ifndef bench_pdm_callback
void bench_pdm_callback(pdm_callback_args_t * p_args);
#endif
#ifndef NULL
extern pdm_coefficients_t const NULL;
#endif
/** WDT on WDT Instance. */
extern const wdt_instance_t g_bench_wdt;

/** Access the WDT instance using these structures when calling API functions directly (::p_api is not used). */
extern wdt_instance_ctrl_t g_bench_wdt_ctrl;
extern const wdt_cfg_t g_bench_wdt_cfg;

#ifndef NULL
void NULL(wdt_callback_args_t * p_args);
#endif
/** Timer on GPT Instance. */
extern const timer_instance_t g_marker;

/** Access the GPT instance using these structures when calling API functions directly (::p_api is not used). */
extern gpt_instance_ctrl_t g_marker_ctrl;
extern const timer_cfg_t g_marker_cfg;

#ifndef marker_callback
void marker_callback(timer_callback_args_t * p_args);
#endif
/** UART on SCI Instance. */
            extern const uart_instance_t      g_console;

            /** Access the UART instance using these structures when calling API functions directly (::p_api is not used). */
            extern sci_b_uart_instance_ctrl_t     g_console_ctrl;
            extern const uart_cfg_t g_console_cfg;
            extern const sci_b_uart_extended_cfg_t g_console_cfg_extend;

            #ifndef console_callback
            void console_callback(uart_callback_args_t * p_args);
            #endif
void hal_entry(void);
void g_hal_init(void);
FSP_FOOTER
#endif /* HAL_DATA_H_ */
