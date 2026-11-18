/* Host-only byte-write tests for manual-derived register access views. */
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "bsp_exceptions.h"
#include "R7KA8P1KF.h"

static int preserved(const void * object, size_t size, size_t offset, const uint8_t * expected, size_t count)
{
    const uint8_t * bytes = object;
    for (size_t i = 0; i < size; ++i)
    {
        uint8_t value = ((i >= offset) && (i - offset < count)) ? expected[i - offset] : 0xA5U;
        if (bytes[i] != value)
        {
            return 1;
        }
    }
    return 0;
}

int main(void)
{
    R_IIC0_Type iic;
    memset(&iic, 0xA5, sizeof(iic));
    iic.SAR[2].L_b.SVA = 0x66U;
    if (preserved(&iic, sizeof(iic), 0x0E, (uint8_t[]) {0x66}, 1)) return 1;

    R_AGTX0_Type agt;
    memset(&agt, 0xA5, sizeof(agt));
    agt.AGT16.CTRL.AGTCR = 0xF0U;
    if (preserved(&agt, sizeof(agt), 8, (uint8_t[]) {0xF0}, 1)) return 2;

    R_RTC_Type rtc;
    memset(&rtc, 0xA5, sizeof(rtc));
    rtc.BCNT0 = 0x23U;
    if (preserved(&rtc, sizeof(rtc), 2, (uint8_t[]) {0x23}, 1)) return 3;
    memset(&rtc, 0xA5, sizeof(rtc));
    rtc.RYRCNT = 0x2026U;
    if (preserved(&rtc, sizeof(rtc), 0x0E, (uint8_t[]) {0x26, 0x20}, 2)) return 4;

    R_USB_FS0_Type fs;
    memset(&fs, 0xA5, sizeof(fs));
    fs.CFIFOLL = 0x6BU;
    if (preserved(&fs, sizeof(fs), 0x14, (uint8_t[]) {0x6B}, 1)) return 5;
    memset(&fs, 0xA5, sizeof(fs));
    fs.CFIFOL = 0x1234U;
    if (preserved(&fs, sizeof(fs), 0x14, (uint8_t[]) {0x34, 0x12}, 2)) return 9;
    if (fs.CFIFO != 0x1234U || fs.CFIFOLL != 0x34U) return 10;
    memset(&fs, 0xA5, sizeof(fs));
    fs.D0FIFOLL = 0x7CU;
    if (preserved(&fs, sizeof(fs), 0x18, (uint8_t[]) {0x7C}, 1)) return 11;
    memset(&fs, 0xA5, sizeof(fs));
    fs.D0FIFOL = 0x5678U;
    if (preserved(&fs, sizeof(fs), 0x18, (uint8_t[]) {0x78, 0x56}, 2)) return 12;
    if (fs.D0FIFO != 0x5678U || fs.D0FIFOLL != 0x78U) return 13;
    memset(&fs, 0xA5, sizeof(fs));
    fs.D1FIFOLL = 0x8DU;
    if (preserved(&fs, sizeof(fs), 0x1C, (uint8_t[]) {0x8D}, 1)) return 14;
    memset(&fs, 0xA5, sizeof(fs));
    fs.D1FIFOL = 0x9ABCU;
    if (preserved(&fs, sizeof(fs), 0x1C, (uint8_t[]) {0xBC, 0x9A}, 2)) return 15;
    if (fs.D1FIFO != 0x9ABCU || fs.D1FIFOLL != 0xBCU) return 16;

    R_USB_HS0_Type hs;
    memset(&hs, 0xA5, sizeof(hs));
    hs.CFIFOH = 0x1234U;
    if (preserved(&hs, sizeof(hs), 0x16, (uint8_t[]) {0x34, 0x12}, 2)) return 6;

    R_I3C0_Type i3c;
    memset(&i3c, 0xA5, sizeof(i3c));
    i3c.DATBAS7 = 0x11223344U;
    if (preserved(&i3c, sizeof(i3c), 0x25C, (uint8_t[]) {0x44, 0x33, 0x22, 0x11}, 4)) return 7;

    R_SSI0_Type ssi;
    memset(&ssi, 0xA5, sizeof(ssi));
    ssi.SSIFTDR8 = 0x5CU;
    if (preserved(&ssi, sizeof(ssi), 0x18, (uint8_t[]) {0x5C}, 1)) return 8;

    return 0;
}
