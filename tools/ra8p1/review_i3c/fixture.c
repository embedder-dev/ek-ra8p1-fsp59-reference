/* Host tests of complete production C; numeric acceptance oracles are HM41.
 * registers.h is extracted from the owning device header into a temporary tree.
 * Wait hooks model delayed writes, not target timing or electrical behavior. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "production.c"

R_I3C0_Type review_registers;
unsigned review_waits, review_starts, review_stops;
unsigned review_disabled, review_pending, review_context_cleared;
void * review_context;
const char * review_wait_expression;
static unsigned saw_disable_wait, saw_inst_wait, saw_bst_wait;
static unsigned callbacks;
static i3c_event_t last_event;

void review_wait(const char * expression)
{
    review_waits++;
    review_wait_expression = expression;
    if (strstr(expression, "BUSE"))
    {
        saw_disable_wait++;
        assert((review_disabled & (1U << 5)) != 0);
        assert(review_registers.RSTCTL == 0);
    }
    if (strstr(expression, "INST"))
    {
        saw_inst_wait++;
        /* A different pending cause must not be included in this wait. */
        assert((review_registers.INST & 0x80000000U) != 0);
        assert(strstr(expression, "inst_clear_mask") != NULL);
    }
    if (strstr(expression, "BST"))
    {
        saw_bst_wait++;
        assert(strstr(expression, "bst_clear_mask") != NULL);
    }
    review_registers.RSTCTL = 0;
}

void review_stop(void)
{
    review_stops++;
    assert((review_disabled & (1U << 5)) != 0);
    assert((review_pending & (1U << 5)) != 0);
    assert((review_context_cleared & (1U << 5)) != 0);
    assert(saw_disable_wait == 1);
    assert(review_registers.BCTL_b.BUSE == 0);
}

static void callback(i3c_callback_args_t const * const args)
{
    callbacks++;
    last_event = args->event;
}

static i3c_extended_cfg_t extend;
static i3c_cfg_t config;
static i3c_instance_ctrl_t ctrl;

static void setup(void)
{
    memset(&review_registers, 0, sizeof(review_registers));
    memset(&ctrl, 0, sizeof(ctrl));
    memset(&extend, 0, sizeof(extend));
    extend.resp_irq = 0;
    extend.rx_irq = 1;
    extend.tx_irq = 2;
    extend.rcv_irq = 3;
    extend.ibi_irq = 4;
    extend.eei_irq = 5;
    extend.slave_command_response_info.write_length = 8;
    extend.slave_command_response_info.read_length = 16;
    config = (i3c_cfg_t) {.device_type = I3C_DEVICE_TYPE_MAIN_MASTER,
                           .p_extend = &extend, .p_callback = callback};
    ctrl.p_reg = &review_registers;
    ctrl.p_cfg = &config;
    ctrl.open = I3C_OPEN;
    ctrl.internal_state = I3C_INTERNAL_STATE_MASTER_IDLE;
    review_context = &ctrl;
}

int main(int argc, char ** argv)
{
    assert(argc == 2);
    setup();
    switch (atoi(argv[1]))
    {
        case 1:
        {
#if REVIEW_MASTER
            /* HM41.3.1.1.2 BYTE_CNT=0: no payload access, including NULL. */
            i3c_command_descriptor_t c = {.command_code = I3C_CCC_BROADCAST_RSTDAA, .restart = true};
            assert(R_I3C_CommandSend(&ctrl, &c) == FSP_SUCCESS);
            assert(review_registers.NCMDQP == 0);
            assert(ctrl.write_buffer_descriptor.count == 0);
#endif
            break;
        }
        case 2:
        {
#if REVIEW_MASTER
            /* HM41.3.1.2: response TIDs 0..7; public completion events stay 8/9. */
            for (unsigned read = 0; read != 2; read++)
            {
                uint32_t word = i3c_xfer_command_calculate(7, read != 0, 0, false);
                assert(((word >> 3) & 15U) <= 7);
                assert((word & 0x80000000U) != 0);
                ctrl.internal_state = read ? I3C_INTERNAL_STATE_MASTER_READ : I3C_INTERNAL_STATE_MASTER_WRITE;
                i3c_resp_isr();
                assert(last_event == (read ? I3C_EVENT_READ_COMPLETE : I3C_EVENT_WRITE_COMPLETE));
            }
#endif
            break;
        }
        case 3:
        {
#if REVIEW_MASTER && REVIEW_CHECKS
            /* HM41.2.62 has eight entries numbered 0..7. */
            assert(R_I3C_DynamicAddressAssignmentStart(&ctrl, I3C_ADDRESS_ASSIGNMENT_MODE_ENTDAA, 7, 1) == FSP_SUCCESS);
            ctrl.internal_state = I3C_INTERNAL_STATE_MASTER_IDLE;
            assert(R_I3C_DynamicAddressAssignmentStart(&ctrl, I3C_ADDRESS_ASSIGNMENT_MODE_ENTDAA, 0, 8) == FSP_SUCCESS);
            ctrl.internal_state = I3C_INTERNAL_STATE_MASTER_IDLE;
            assert(R_I3C_DynamicAddressAssignmentStart(&ctrl, I3C_ADDRESS_ASSIGNMENT_MODE_ENTDAA, 7, 2) == FSP_ERR_ASSERTION);
            assert(R_I3C_DynamicAddressAssignmentStart(&ctrl, I3C_ADDRESS_ASSIGNMENT_MODE_ENTDAA, 7, UINT32_MAX) == FSP_ERR_ASSERTION);
            assert(R_I3C_DynamicAddressAssignmentStart(&ctrl, I3C_ADDRESS_ASSIGNMENT_MODE_ENTDAA, 0, 0) == FSP_ERR_ASSERTION);
#endif
            break;
        }
        case 4:
        {
            /* HM41.2.2: do not disable with queued commands; confirm BUSE=0. */
            ctrl.internal_state = I3C_INTERNAL_STATE_MASTER_WRITE;
            assert(R_I3C_Close(&ctrl) == FSP_ERR_IN_USE);
            assert(review_disabled == 0 && review_stops == 0);
            ctrl.internal_state = I3C_INTERNAL_STATE_MASTER_IDLE;
            review_registers.BCTL_b.BUSE = 1;
            assert(R_I3C_Close(&ctrl) == FSP_SUCCESS);
            assert(review_stops == 1 && ctrl.open == 0);
            break;
        }
        case 5:
        {
            /* HM41.4.1: read back the flags actually cleared, not unrelated ones. */
            review_registers.INST = R_I3C0_INST_INEF_Msk | 0x80000000U;
            review_registers.BST = R_I3C0_BST_TODF_Msk | R_I3C0_BST_HDREXDF_Msk;
            i3c_eei_isr();
            assert(callbacks == 3);
            assert(saw_inst_wait == 1 && saw_bst_wait == 1);
            assert(review_registers.INST == 0x80000000U);
            break;
        }
        case 6:
        {
            /* UBSan catches integer promotion before shifts into bit 31/24. */
#if REVIEW_UNALIGNED
            uint8_t bytes[4] = {0x12, 0x34, 0x56, 0xFF};
            i3c_write_buffer_descriptor_t b = {.p_buffer = bytes, .buffer_size = 4};
            assert(i3c_next_data_word_calculate(&b) == 0xFF563412U);
#endif
            extend.bitrate_settings.clock_stalling.ack_phase_enable = 1;
            extend.slave_command_response_info.read_turnaround_time_enable = true;
            extend.slave_command_response_info.read_turnaround_time = 16000000;
            ctrl.internal_state = I3C_INTERNAL_STATE_DISABLED;
            assert(R_I3C_Enable(&ctrl) == FSP_SUCCESS);
            assert(review_registers.SCSTLCTL == 0x80000000U);
#if REVIEW_SLAVE
            assert(review_registers.CMDSPT == (0x80000000U | 16000000U));
#endif
#if REVIEW_MASTER
            i3c_command_descriptor_t c = {.command_code = I3C_CCC_BROADCAST_RSTDAA, .restart = false};
            assert(R_I3C_CommandSend(&ctrl, &c) == FSP_SUCCESS);
#endif
#if REVIEW_SLAVE
            i3c_device_cfg_t device = {.slave_info.pid = {0xFF, 0x80, 0x34, 0x12, 0x56, 0x78}};
            config.device_type = I3C_DEVICE_TYPE_SLAVE;
            assert(R_I3C_DeviceCfgSet(&ctrl, &device) == FSP_SUCCESS);
            assert(review_registers.SDCTPIDH == 0xFF803412U);
            assert(review_registers.SDCTPIDL == 0x5678U);
#endif
            break;
        }
        case 7:
        {
#if REVIEW_CHECKS && REVIEW_SLAVE
            /* HM41.2.72/73/78: reject prohibited slave length/turnaround settings. */
            config.device_type = I3C_DEVICE_TYPE_SLAVE;
            extend.slave_command_response_info.write_length = 7;
            assert(R_I3C_Open(&ctrl, &config) == FSP_ERR_ALREADY_OPEN);
            ctrl.open = 0;
            assert(R_I3C_Open(&ctrl, &config) == FSP_ERR_ASSERTION);
            assert(review_starts == 0);
            extend.slave_command_response_info.write_length = 8;
            extend.slave_command_response_info.read_length = 15;
            assert(R_I3C_Open(&ctrl, &config) == FSP_ERR_ASSERTION);
            extend.slave_command_response_info.read_length = 16;
            extend.slave_command_response_info.read_turnaround_time = 16000001;
            assert(R_I3C_Open(&ctrl, &config) == FSP_ERR_ASSERTION);
            extend.slave_command_response_info.read_turnaround_time = 16000000;
            assert(R_I3C_Open(&ctrl, &config) == FSP_SUCCESS);
#endif
            break;
        }
        default: assert(false);
    }
    return 0;
}
