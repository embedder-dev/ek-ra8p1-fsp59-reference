/* Independent literal anchors: RA8P1 HM R01UH1064EJ0130 Rev.1.30,
 * 54.2.13.2 pp.3401-3402 and 60.5.41-44 pp.3591-3592.
 * No expected layout, mask or bitfield byte is read from the inventory.
 */
#include <stddef.h>
#include <stdint.h>
#include "bsp_exceptions.h"
#include "R7KA8P1KF.h"

#define OFFSET(type, member, value) _Static_assert(offsetof(type, member) == (value), #member " offset")
#define WIDTH(type, member, value) _Static_assert(sizeof(((type *) 0)->member) == (value), #member " width")
#define CHECK_DIAGNOSTIC(index, offset) \
    OFFSET(R_ADC_B0_Type, ADEXDR##index, offset); \
    WIDTH(R_ADC_B0_Type, ADEXDR##index, 4); \
    _Static_assert(R_ADC_B0_ADEXDR##index##_DIAGSR_Pos == 24U, "DIAGSR position"); \
    _Static_assert(R_ADC_B0_ADEXDR##index##_DIAGSR_Msk == 0x07000000UL, "DIAGSR mask"); \
    _Static_assert(R_ADC_B0_ADEXDR##index##_DATA_Msk == 0x0000FFFFUL, "DATA mask"); \
    _Static_assert(R_ADC_B0_ADEXDR##index##_ERR_Msk == 0x80000000UL, "ERR mask")

/* The common indexed view must remain ABI-compatible, without DIAGSR. */
OFFSET(R_ADC_B0_Type, ADEXDR, 0x2180);
OFFSET(R_ADC_B0_Type, ADEXDR[22], 0x21D8);
OFFSET(R_ADC_B0_Type, ADEXDR_b[22], 0x21D8);
WIDTH(R_ADC_B0_Type, ADEXDR, 92);
WIDTH(R_ADC_B0_Type, ADEXDR_b, 92);
_Static_assert(sizeof(R_ADC_B0_Type) == 0x2224, "ADC extent unchanged");
_Static_assert(R_ADC_B0_ADEXDR_DATA_Msk == 0x0000FFFFUL, "common DATA");
_Static_assert(R_ADC_B0_ADEXDR_ERR_Msk == 0x80000000UL, "common ERR");
CHECK_DIAGNOSTIC(0,  0x2180);
CHECK_DIAGNOSTIC(1,  0x2184);
CHECK_DIAGNOSTIC(16, 0x21C0);
CHECK_DIAGNOSTIC(17, 0x21C4);
CHECK_DIAGNOSTIC(18, 0x21C8);
CHECK_DIAGNOSTIC(20, 0x21D0);
CHECK_DIAGNOSTIC(21, 0x21D4);
CHECK_DIAGNOSTIC(22, 0x21D8);

/* MWMCR is in SYSC, not the MRAM peripheral register window. */
OFFSET(R_SYSTEM_Type, LVOCR, 0xAB0);
OFFSET(R_SYSTEM_Type, MWMCR, 0xAB4);
OFFSET(R_SYSTEM_Type, SYRSTMSK0, 0xAD0);
WIDTH(R_SYSTEM_Type, MWMCR, 1);
_Static_assert(R_SYSTEM_S_BASE == 0x4001E000UL, "SYSC secure base");
_Static_assert(R_SYSTEM_NS_BASE == 0x5001E000UL, "SYSC nonsecure base");
_Static_assert(R_SYSC_BASE == R_SYSTEM_BASE, "FSP SYSTEM / native SYSC spelling");
_Static_assert(R_SYSTEM_MWMCR_MWM_Pos == 0U, "MWM position");
_Static_assert(R_SYSTEM_MWMCR_MWM_Msk == 0x03UL, "MWM mask");
_Static_assert(sizeof(R_SYSTEM_Type) == 0xD80, "SYSC extent unchanged");

/* Absolute read-only identity registers have no invented +0x10000000 alias. */
_Static_assert(R_UIDR_BASE == 0x02F07B00UL, "UIDR absolute base");
_Static_assert(R_PNR_BASE == 0x02C1EC38UL, "PNR absolute base");
_Static_assert(R_MCUVER_BASE == 0x02C1EC48UL, "MCUVER absolute base");
OFFSET(R_UIDR_Type, UIDR0, 0x00);
OFFSET(R_UIDR_Type, UIDR1, 0x04);
OFFSET(R_UIDR_Type, UIDR2, 0x08);
OFFSET(R_UIDR_Type, UIDR3, 0x0C);
OFFSET(R_PNR_Type, PNR0, 0x00);
OFFSET(R_PNR_Type, PNR1, 0x04);
OFFSET(R_PNR_Type, PNR2, 0x08);
OFFSET(R_PNR_Type, PNR3, 0x0C);
OFFSET(R_MCUVER_Type, MCUVER, 0x00);
WIDTH(R_UIDR_Type, UIDR0, 4);
WIDTH(R_UIDR_Type, UIDR1, 4);
WIDTH(R_UIDR_Type, UIDR2, 4);
WIDTH(R_UIDR_Type, UIDR3, 4);
WIDTH(R_PNR_Type, PNR0, 4);
WIDTH(R_PNR_Type, PNR1, 4);
WIDTH(R_PNR_Type, PNR2, 4);
WIDTH(R_PNR_Type, PNR3, 4);
WIDTH(R_MCUVER_Type, MCUVER, 1);
_Static_assert(sizeof(R_UIDR_Type) == 16, "UID size");
_Static_assert(sizeof(R_PNR_Type) == 16, "part number size");
_Static_assert(sizeof(R_MCUVER_Type) == 1, "version size");
_Static_assert(R_UIDR_UIDR_UID_Msk == 0xFFFFFFFFUL, "UID mask");
_Static_assert(R_PNR_PNR_PNR_Msk == 0xFFFFFFFFUL, "PNR mask");
_Static_assert(R_MCUVER_MCUVER_MCUVE_Msk == 0xFFUL, "MCUVE mask");
#define CHECK_ID_MASKS(index) \
    _Static_assert(R_UIDR_UIDR##index##_UID_Pos == 0U, "UID position"); \
    _Static_assert(R_UIDR_UIDR##index##_UID_Msk == 0xFFFFFFFFUL, "UID individual mask"); \
    _Static_assert(R_PNR_PNR##index##_PNR_Pos == 0U, "PNR position"); \
    _Static_assert(R_PNR_PNR##index##_PNR_Msk == 0xFFFFFFFFUL, "PNR individual mask")
CHECK_ID_MASKS(0);
CHECK_ID_MASKS(1);
CHECK_ID_MASKS(2);
CHECK_ID_MASKS(3);

#ifdef __ELF__
#define PROBE_SECTION(name) __attribute__((section(name), used))
#else
#define PROBE_SECTION(name)
#endif

#define DIAGNOSTIC_BYTES(index) \
    PROBE_SECTION(".analog.diag" #index) \
    const __typeof__(((R_ADC_B0_Type *) 0)->ADEXDR##index##_b) diag##index = \
        {.DATA = 0xFFFFU, .DIAGSR = 7U, .ERR = 1U}
DIAGNOSTIC_BYTES(0);
DIAGNOSTIC_BYTES(1);
DIAGNOSTIC_BYTES(16);
DIAGNOSTIC_BYTES(17);
DIAGNOSTIC_BYTES(18);
DIAGNOSTIC_BYTES(20);
DIAGNOSTIC_BYTES(21);
DIAGNOSTIC_BYTES(22);
PROBE_SECTION(".analog.mwm")
const __typeof__(((R_SYSTEM_Type *) 0)->MWMCR_b) mwm = {.MWM = 3U};

#ifndef __ELF__
static uint32_t read_le(const void * memory)
{
    const unsigned char * p = memory;
    return (uint32_t) p[0] | ((uint32_t) p[1] << 8) |
           ((uint32_t) p[2] << 16) | ((uint32_t) p[3] << 24);
}

int main(void)
{
    if (read_le(&diag0) != 0x8700FFFFUL || read_le(&diag1) != 0x8700FFFFUL ||
        read_le(&diag16) != 0x8700FFFFUL || read_le(&diag17) != 0x8700FFFFUL ||
        read_le(&diag18) != 0x8700FFFFUL || read_le(&diag20) != 0x8700FFFFUL ||
        read_le(&diag21) != 0x8700FFFFUL || read_le(&diag22) != 0x8700FFFFUL)
    {
        return 1;
    }
    return (*(const unsigned char *) &mwm == 0x03U) ? 0 : 2;
}
#endif
