/* Host-memory checks for the exact RTC member expressions used by r_ioport.c.
 * Register positions are independently anchored in anchors.c; no target is accessed.
 */
#include <assert.h>
#include <string.h>
#include "anchors.c"

int main(void)
{
    R_RTC_Type rtc;
    R_RTC_Type * p_rtc = &rtc;
    unsigned char expected[sizeof(rtc)];
    memset(&rtc, 0xAA, sizeof(rtc));
    memset(expected, 0xAA, sizeof(expected));

    for (unsigned vbatt_index = 0; vbatt_index < 3; ++vbatt_index)
    {
        if (p_rtc->RTCCR[vbatt_index].RTCCR_b.TCEN > 0)
        {
            p_rtc->RTCCR[vbatt_index].RTCCR_b.TCEN = 0;
        }
        expected[0x40 + 2 * vbatt_index] &= 0x7F;
        assert(memcmp(&rtc, expected, sizeof(rtc)) == 0);

        if (0 == p_rtc->RTCCR[vbatt_index].RTCCR_b.TCEN)
        {
            p_rtc->RTCCR[vbatt_index].RTCCR_b.TCEN = 1;
        }
        expected[0x40 + 2 * vbatt_index] |= 0x80;
        assert(memcmp(&rtc, expected, sizeof(rtc)) == 0);
    }

    p_rtc->RCR4 = 0;
    expected[0x28] = 0;
    p_rtc->RCR2 = 0;
    p_rtc->RCR2_b.RESET = 1;
    expected[0x24] = 2;
    p_rtc->RCR1 = 0;
    expected[0x22] = 0;
    assert(memcmp(&rtc, expected, sizeof(rtc)) == 0);
    return 0;
}
