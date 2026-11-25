#include "hal_data.h"

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

static const bsp_io_port_pin_t marker_pins[] = {
    BSP_IO_PORT_05_PIN_14, BSP_IO_PORT_01_PIN_11, BSP_IO_PORT_08_PIN_06, BSP_IO_PORT_08_PIN_07,
};
static volatile int marker = -1;
static bool high;
static volatile bool tx_done;
static volatile bool rx_ready;
static char line[16];
static unsigned int rx_len;
static bool rx_overflow;
volatile fsp_err_t bench_error;

void bench_run(void);
void bench_emit(const char * text);
bool bench_cgc(bool divide);

void console_callback(uart_callback_args_t * args)
{
    if (UART_EVENT_TX_COMPLETE == args->event)
    {
        tx_done = true;
    }
    else if ((UART_EVENT_RX_CHAR == args->event) && !rx_ready)
    {
        if ('\n' == args->data)
        {
            line[rx_overflow ? 0U : rx_len] = '\0';
            rx_ready = true;
            rx_len = 0U;
            rx_overflow = false;
        }
        else if ('\r' != args->data)
        {
            if (rx_len < sizeof(line) - 1U)
            {
                line[rx_len++] = (char) args->data;
            }
            else
            {
                rx_overflow = true;
            }
        }
    }
}

void marker_callback(timer_callback_args_t * args)
{
    if ((TIMER_EVENT_CYCLE_END == args->event) && (marker >= 0))
    {
        high = !high;
        bench_error = R_IOPORT_PinWrite(&g_ioport_ctrl, marker_pins[marker], high ? BSP_IO_LEVEL_HIGH : BSP_IO_LEVEL_LOW);
        if (FSP_SUCCESS != bench_error)
        {
            marker = -1;
        }
    }
}

static void put_line(const char * text)
{
    tx_done = false;
    bench_error = g_console.p_api->write(g_console.p_ctrl, (const uint8_t *) text, strlen(text));
    if (FSP_SUCCESS == bench_error)
    {
        for (uint32_t spins = 0; !tx_done && (spins < 1000000U); ++spins)
        {
            __NOP();
        }
    }
}

void bench_emit(const char * text)
{
    put_line(text);
}

static bool check(fsp_err_t err, const char * operation)
{
    if (FSP_SUCCESS == err)
    {
        return true;
    }
    char status[64];
    (void) snprintf(status, sizeof(status), "FAIL %s err=%u\r\n", operation, (unsigned int) err);
    put_line(status);
    bench_error = err;
    return false;
}

static void clocks(void)
{
    char status[180];
    (void) snprintf(status, sizeof(status),
                    "CLOCK SCKSCR=%02x SCKDIVCR=%08" PRIx32 " SCKDIVCR2=%08" PRIx32
                    " OSCSF=%02x SCICKCR=%02x SCI8_CCR2=%08" PRIx32 " SCI8_CCR3=%08" PRIx32 "\r\n",
                    (unsigned int) R_SYSTEM->SCKSCR, R_SYSTEM->SCKDIVCR, (uint32_t) R_SYSTEM->SCKDIVCR2,
                    (unsigned int) R_SYSTEM->OSCSF, (unsigned int) R_SYSTEM->SCICKCR,
                    R_SCI_B8->CCR2, R_SCI_B8->CCR3);
    put_line(status);
    (void) snprintf(status, sizeof(status), "GPT0 GTCR=%08" PRIx32 " GTPR=%" PRIu32 " CPU1ACTCSR=%04x\r\n",
                    R_GPT0->GTCR, R_GPT0->GTPR, R_CPU_CTRL->CPU1ACTCSR);
    put_line(status);
}

static bool select_marker(int next)
{
    int previous = marker;
    marker = -1;
    if (previous >= 0 && !check(R_IOPORT_PinWrite(&g_ioport_ctrl, marker_pins[previous], BSP_IO_LEVEL_LOW), "idle GPIO"))
    {
        return false;
    }
    if (next >= 0 && !check(R_IOPORT_PinCfg(&g_ioport_ctrl, marker_pins[next], IOPORT_CFG_PORT_DIRECTION_OUTPUT), "marker GPIO"))
    {
        return false;
    }
    high = false;
    marker = next;
    return true;
}

void bench_run(void)
{
    bench_error = g_console.p_api->open(g_console.p_ctrl, g_console.p_cfg);
    if (FSP_SUCCESS != bench_error)
    {
        return;
    }
    put_line("BOOT EK-RA8P1 r020 CPU0 " __DATE__ " " __TIME__ "\r\n");
    if (!check(g_marker.p_api->open(g_marker.p_ctrl, g_marker.p_cfg), "GPT open") ||
        !check(g_marker.p_api->start(g_marker.p_ctrl), "GPT start"))
    {
        return;
    }
    clocks();
    put_line("READY\r\n");
    for (;;)
    {
        if (!rx_ready)
        {
            continue;
        }
        bool ok = false;
        if ('m' == line[0] && line[1] >= '0' && line[1] <= '3' && '\0' == line[2])
        {
            ok = select_marker(line[1] - '0');
        }
        else if (0 == strcmp(line, "idle"))
        {
            ok = select_marker(-1);
        }
        else if (0 == strcmp(line, "clocks"))
        {
            clocks();
            ok = true;
        }
        else if ((0 == strcmp(line, "c0")) || (0 == strcmp(line, "c1")))
        {
            ok = bench_cgc('1' == line[1]);
        }
        if (ok)
        {
            char ack[24];
            (void) snprintf(ack, sizeof(ack), "ACK %s\r\n", line);
            put_line(ack);
        }
        rx_ready = false;
    }
}
