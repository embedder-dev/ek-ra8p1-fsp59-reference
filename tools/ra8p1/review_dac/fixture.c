#include <stdio.h>
#include <string.h>
#include "r_dac_b.h"

R_MRAM_Type test_mram;
R_DAC_B0_Type test_dac[2];
static unsigned int critical_depth;
static unsigned int enters;
static unsigned int exits;
static unsigned int starts;
static unsigned int barriers;
static unsigned int polls;
static unsigned int complete_after;
static unsigned int zeroize_after;

void test_enter(void)
{
    assert(0U == critical_depth);
    critical_depth++;
    enters++;
}

void test_exit(void)
{
    assert(1U == critical_depth);
    if ((0U != barriers) && (0U != test_mram.MCTRSTATR_b.TRBUSY))
    {
        /* An unfinished transfer must retain the selected coefficient list. */
        assert(1U == test_mram.MCTRLSR);
        assert(0x4501U == test_mram.MCTRCNTR);
    }
    critical_depth--;
    exits++;
}

void test_start(unsigned int channel)
{
    assert(0U == critical_depth);
    assert(0U == channel);
    starts++;
}

void test_stop(unsigned int channel)
{
    assert(0U == channel);
}

void test_delay(uint32_t delay, unsigned int units)
{
    assert(0U == critical_depth);
    assert(0U != delay);
    assert(BSP_DELAY_UNITS_MICROSECONDS == units);
}

void test_dsb(void)
{
    assert(1U == critical_depth);
    assert(0U == barriers);
    barriers++;
    assert(0U == test_mram.MCTRSTATR_b.TRBUSY);
    assert(1U == test_mram.MCTRLSR);
    assert(0x4501U == test_mram.MCTRCNTR);
    /* The transfer is immediate or becomes busy before polling begins. */
    test_mram.MCTRSTATR_b.TRBUSY = (0U != complete_after);
}

void test_nop(void)
{
    assert(1U == critical_depth);
    assert(1U == test_mram.MCTRSTATR_b.TRBUSY);
    assert(1U == test_mram.MCTRLSR);
    assert(0x4501U == test_mram.MCTRCNTR);
    polls++;
    if (polls == complete_after)
    {
        test_mram.MCTRSTATR_b.TRBUSY = 0U;
    }
    if (polls == zeroize_after)
    {
        test_mram.MREZS_b.WHUKEXE = 1U;
    }
}

static void run_case(char const * name)
{
    uint32_t budget = 3U;
    unsigned int expected_polls = 0U;
    fsp_err_t expected = FSP_SUCCESS;
    bool already_busy = false;
    bool nonsecure = false;
    bool still_busy = false;
    bool preloaded = false;

    if (0 == strcmp(name, "immediate"))
    {
        budget = 1U;
    }
    else if (0 == strcmp(name, "before_deadline"))
    {
        complete_after = expected_polls = 2U;
    }
    else if (0 == strcmp(name, "last_poll"))
    {
        complete_after = expected_polls = 3U;
    }
    else if (0 == strcmp(name, "single_poll"))
    {
        budget = complete_after = expected_polls = 1U;
    }
    else if (0 == strcmp(name, "zeroization"))
    {
        zeroize_after = complete_after = expected_polls = 3U;
        expected = FSP_ERR_INVALID_STATE;
    }
    else if ((0 == strcmp(name, "still_busy")) || (0 == strcmp(name, "busy_zeroization")))
    {
        complete_after = 4U;
        expected_polls = 3U;
        expected = FSP_ERR_TIMEOUT;
        still_busy = true;
        if (0 == strcmp(name, "busy_zeroization"))
        {
            zeroize_after = 3U;
        }
    }
    else if (0 == strcmp(name, "already_busy"))
    {
        already_busy = true;
        expected = FSP_ERR_IN_USE;
    }
    else if (0 == strcmp(name, "nonsecure"))
    {
        nonsecure = true;
        expected = FSP_ERR_UNSUPPORTED;
    }
    else
    {
        assert(0 && "unknown fixture case");
    }

    assert(nonsecure == (0 != BSP_TZ_NONSECURE_BUILD));
    test_mram.MSTATR_b.MRDY = 1U;
    test_mram.MCTRLSR = 6U; /* A non-default saved selection must be preserved exactly. */
    test_mram.MCTRCNTR = 0x4500U;
    test_mram.MCTRSTATR_b.TRBUSY = already_busy;
    R_MRAM_Type original = test_mram;
    dac_b_extended_cfg_t extension =
    {
        .data_format = DAC_DATA_FORMAT_FLUSH_RIGHT,
        .voltage_mode = DAC_B_VOLTAGE_NORMAL,
        .output = DAC_B_OUTPUT_PIN,
        .trigger = DAC_B_TRIGGER_SOFTWARE,
        .timeout = budget,
        .calibration_preloaded = preloaded,
    };
    dac_cfg_t const configuration = {.channel = 0U, .p_extend = &extension};
    dac_b_instance_ctrl_t control = {0};
    dac_b_instance_ctrl_t original_control = control;

    /* Exercise the production public interface and real control/configuration types. */
    fsp_err_t actual = g_dac_on_dac_b.open(&control, &configuration);
    if (expected != actual)
    {
        fprintf(stderr, "%s: expected status %d, got %d; polls=%u, busy=%u, list=%u\n",
                name, (int) expected, (int) actual, polls,
                (unsigned int) test_mram.MCTRSTATR_b.TRBUSY, (unsigned int) test_mram.MCTRLSR);
    }
    assert(expected == actual);
    assert(expected_polls == polls);
    assert(0U == critical_depth);
    assert((nonsecure ? 0U : 1U) == enters);
    assert(enters == exits);

    if (already_busy || nonsecure)
    {
        assert(0U == barriers);
        assert(0 == memcmp(&original, &test_mram, sizeof(original)));
    }
    else
    {
        assert(1U == barriers);
        assert(0x4501U == test_mram.MCTRCNTR);
        assert((still_busy ? 1U : 6U) == test_mram.MCTRLSR);
        assert(still_busy == (0U != test_mram.MCTRSTATR_b.TRBUSY));
    }
    if (FSP_SUCCESS == expected)
    {
        assert(1U == starts);
        assert(0U != control.open);
        assert(&configuration == control.p_cfg);
        assert(R_DAC_B0 == control.p_reg);
        assert(!control.started);
    }
    else
    {
        R_DAC_B0_Type const untouched[2] = {0};
        assert(0U == starts);
        assert(0 == memcmp(&original_control, &control, sizeof(control)));
        assert(0 == memcmp(untouched, test_dac, sizeof(test_dac)));
    }
    if (nonsecure)
    {
        extension.calibration_preloaded = true;
        assert(FSP_SUCCESS == g_dac_on_dac_b.open(&control, &configuration));
        assert(1U == starts);
        assert(0U == barriers);
        assert(0U == enters);
        assert(0 == memcmp(&original, &test_mram, sizeof(original)));
    }
}

int main(int argc, char ** argv)
{
    assert(2 == argc);
    run_case(argv[1]);
    printf("production DAC_B: %s passed\n", argv[1]);
    return 0;
}
