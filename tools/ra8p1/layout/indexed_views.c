/* Manual layout invariants for indexed views; no hardware is accessed. */
#include <stdint.h>
#include <string.h>
#include "anchors.c"

static int check_icu(void)
{
    R_ICU_COMMON_Type registers;
    unsigned char const * bytes = (unsigned char const *) &registers;
    memset(&registers, 0xA5, sizeof(registers));
    for (unsigned channel = 0; channel < 32; ++channel)
    {
        unsigned const index = channel + ((channel >> 4) << 2);
        registers.IRQCRa[index] = (uint8_t) channel;
        registers.IRQCRa_b[index].FLTEN = 1;
    }
    for (unsigned offset = 0; offset < sizeof(registers); ++offset)
    {
        unsigned char expected = 0xA5;
        if (offset < 16)
        {
            expected = (unsigned char) (offset | 0x80);
        }
        else if (offset >= 20 && offset < 36)
        {
            expected = (unsigned char) ((offset - 4) | 0x80);
        }
        if (bytes[offset] != expected)
        {
            return 1;
        }
    }
    if (registers.NMICR != 0xA5 || registers.IRQCRb[0] != 0x90 || registers.IRQCRb[15] != 0x9F ||
        registers.IRQCR31 != registers.IRQCRa[35] || registers.IRQCRb_b[15].FLTEN != 1)
    {
        return 2;
    }
    return 0;
}

static int elc_index_is_present(unsigned index)
{
    return index < 8 || (index >= 12 && index <= 17) ||
           (index >= 19 && index <= 27) || index == 30 || index == 31 || index == 32;
}

static int check_elc(void)
{
    R_ELC_Type registers;
    unsigned char const * bytes = (unsigned char const *) &registers;
    memset(&registers, 0xA5, sizeof(registers));
    for (unsigned event = 0; event < 4; ++event)
    {
        registers.ELSEGR[event].BY = 0x41;
    }
    for (unsigned index = 0; index < 53; ++index)
    {
        if (elc_index_is_present(index))
        {
            registers.ELSR[index].HA = 0x3FF;
        }
    }
    for (unsigned offset = 0; offset < sizeof(registers); ++offset)
    {
        unsigned char expected = 0xA5;
        if (offset >= 4 && offset <= 16 && offset % 4 == 0)
        {
            expected = 0x41;
        }
        if (offset >= 0x20 && offset < 0xF4 && elc_index_is_present((offset - 0x20) / 4))
        {
            if (offset % 4 == 0)
            {
                expected = 0xFF;
            }
            else if (offset % 4 == 1)
            {
                expected = 3;
            }
        }
        if (bytes[offset] != expected)
        {
            return 3;
        }
    }
    return 0;
}

int main(void)
{
    int result = check_icu();
    return result ? result : check_elc();
}
