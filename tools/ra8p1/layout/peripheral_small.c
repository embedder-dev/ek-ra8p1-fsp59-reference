/* Independent manual anchors for the canonical small-peripheral inventory.
 * No target memory is accessed. HM citations refer to R01UH1064EJ0130 Rev.1.30.
 */
#include <stddef.h>
#include "bsp_exceptions.h"
#include "R7KA8P1KF.h"

/* HM40.2 pp.2379–2396: the three slave-address pairs are byte-interleaved. */
_Static_assert(sizeof(R_IIC0_SAR_Type) == 2, "IIC slave-address pair stride");
_Static_assert(offsetof(R_IIC0_SAR_Type, L) == 0, "IIC canonical low byte");
_Static_assert(offsetof(R_IIC0_SAR_Type, U) == 1, "IIC canonical upper byte");
_Static_assert(offsetof(R_IIC0_Type, SAR[2].U) == 0x0F, "IIC last slave-address byte");
_Static_assert(offsetof(R_IIC0_Type, ICWUR) == 0x16, "IIC0 wakeup subblock offset");
_Static_assert(R_IIC0_ICFER_FMPE_Msk == 0x80, "IIC fast mode plus");
_Static_assert(R_IIC2_S_BASE == 0x4025E200, "IIC channel count and stride");

/* HM25.2 pp.1175–1183: actual AGT16 hardware, not a synthetic AGTW overlay. */
_Static_assert(sizeof(R_AGTX0_AGT16_CTRL_Type) == 8, "AGT control extent");
_Static_assert(sizeof(R_AGTX0_Type) == 0x10, "AGT16-only extent");
_Static_assert(offsetof(R_AGTX0_Type, AGT16.AGTCMA) == 2, "AGT compare A");
_Static_assert(offsetof(R_AGTX0_Type, AGT16.AGTCMB) == 4, "AGT compare B");
_Static_assert(offsetof(R_AGTX0_Type, AGT16.CTRL.AGTCR) == 8, "AGT control offset");
_Static_assert(offsetof(R_AGTX0_Type, AGT16.CTRL.AGTIOSEL) == 0x0F, "AGT input select");
_Static_assert(R_AGTX0_AGT16_CTRL_AGTIOSEL_TIES_Msk == 0x10, "AGT standby input enable");
_Static_assert(R_AGT1_S_BASE == 0x40221100, "AGT1 secure base");
_Static_assert(R_AGTX0_BASE == R_AGT0_BASE, "canonical AGTX0 is AGT0");
_Static_assert(R_AGTX1_BASE == R_AGT1_BASE, "canonical AGTX1 is AGT1");
_Static_assert(R_AGTX1_BASE - R_AGTX0_BASE == 0x100, "canonical AGTX stride");

/* HM27.2 pp.1231–1251: calendar/binary mode views and three capture clusters. */
_Static_assert(sizeof(R_RTC_Type) == 0x80, "RTC complete capture extent");
_Static_assert(offsetof(R_RTC_Type, RSECCNT) == 2, "RTC seconds");
_Static_assert(offsetof(R_RTC_Type, BCNT0) == 2, "RTC binary overlay");
_Static_assert(offsetof(R_RTC_Type, RYRCNT) == 0x0E, "RTC year");
_Static_assert(sizeof(((R_RTC_Type *) 0)->RYRCNT) == 2, "RTC year access width");
_Static_assert(offsetof(R_RTC_Type, RFRH) == 0x2A, "RTC frequency high");
_Static_assert(offsetof(R_RTC_Type, RFRL) == 0x2C, "RTC frequency low");
_Static_assert(offsetof(R_RTC_Type, RADJ) == 0x2E, "RTC adjustment");
_Static_assert(sizeof(R_RTC_CP_Type) == 0x10, "RTC capture stride");
_Static_assert(offsetof(R_RTC_Type, CP[0].RSEC) == 0x52, "RTC capture seconds");
_Static_assert(offsetof(R_RTC_Type, CP[1].BCNT3) == 0x6A, "RTC binary capture overlay");
_Static_assert(offsetof(R_RTC_Type, CP[2].RMON) == 0x7C, "RTC final capture month");

/* HM14.2.19 pp.554–556: FSP WUPEN names the first 32-bit wake bank. */
_Static_assert(offsetof(R_ICU_Type, WUPEN) == 0x1A0, "canonical first wake bank");
_Static_assert(offsetof(R_ICU_Type, WUPEN) == offsetof(R_ICU_Type, WUPEN0), "identical wake storage");
_Static_assert(sizeof(((R_ICU_Type *) 0)->WUPEN) == 4, "wake bank access width");
_Static_assert(offsetof(R_ICU_Type, WUPEN1) == 0x1A4, "second wake bank is distinct");
_Static_assert(R_ICU_WUPEN_IRQWUPEN15_Msk == 0x8000, "last low-bank external IRQ");
_Static_assert(R_ICU_WUPEN_PVD1WUPEN_Msk == 0x40000, "target PVD1 wake source");
_Static_assert(R_ICU_WUPEN_RIIC0WUPEN_Msk == 0x80000000, "last low-bank wake source");

/* HM8.2 pp.304–310: canonical stock LVD names for PVD storage. */
_Static_assert(offsetof(R_SYSTEM_Type, LVD1CMPCR) == 0xA58, "PVD1 comparator control");
_Static_assert(offsetof(R_SYSTEM_Type, LVD2CR0) == 0xA74, "PVD2 circuit control");
_Static_assert(offsetof(R_SYSTEM_Type, LVD1CR1) == 0x0E0, "PVD1 interrupt selection");
_Static_assert(offsetof(R_SYSTEM_Type, LVD2SR) == 0x0E3, "PVD2 status");
_Static_assert(R_SYSTEM_LVD1CMPCR_LVDE_Msk == 0x80, "PVD comparator enable");
_Static_assert(R_SYSTEM_LVD1CMPCR_LVDLVL_Msk == 0x1F, "PVD threshold width");
_Static_assert(offsetof(R_SYSTEM_Type, PVD1CMPCR) == offsetof(R_SYSTEM_Type, LVD1CMPCR), "PVD1 same storage");
_Static_assert(offsetof(R_SYSTEM_Type, PVD2CR0) == offsetof(R_SYSTEM_Type, LVD2CR0), "PVD2 same storage");
_Static_assert(R_SYSTEM_PVD1CMPCR_PVDE_Msk == R_SYSTEM_LVD1CMPCR_LVDE_Msk, "identical comparator enable");
_Static_assert(R_SYSTEM_PVD2CMPCR_PVDLVL_Msk == R_SYSTEM_LVD2CMPCR_LVDLVL_Msk, "identical threshold field");
_Static_assert(R_SYSTEM_PVD4CR0_RE_Msk == 1, "PVD4 reset enable is not classic RI");
_Static_assert(offsetof(R_SYSTEM_Type, PVD4CMPCR) == 0xA64, "PVD4 comparator control");
_Static_assert(offsetof(R_SYSTEM_Type, PVD5CMPCR) == 0xA68, "PVD5 comparator control");

/* HM26.3 pp.1203–1217 and HM47.2 pp.3066–3105. */
_Static_assert(sizeof(R_ULPT0_Type) == 0x14, "ULPT extent");
_Static_assert(offsetof(R_ULPT0_Type, ULPTMR3) == 0x0F, "ULPT third mode byte");
_Static_assert(R_ULPT1_S_BASE == 0x40220100, "ULPT1 base");
_Static_assert(sizeof(R_SSI0_Type) == 0x28, "SSI extent");
_Static_assert(offsetof(R_SSI0_Type, SSIFTDR8) == 0x18, "SSI byte FIFO port");
_Static_assert(offsetof(R_SSI0_Type, SSIFRDR16) == 0x1C, "SSI halfword FIFO port");
_Static_assert(R_SSI0_SSICR_CKS_Msk == 0x40000000, "SSI audio clock select");

/* HM48.2 pp.3136–3162: native 32-bit SDHI register interface. */
_Static_assert(offsetof(R_SDHI0_Type, SD_ARG) == 8, "SDHI argument");
_Static_assert(sizeof(((R_SDHI0_Type *) 0)->SD_ARG) == 4, "SDHI native argument width");
_Static_assert(offsetof(R_SDHI0_Type, SD_RSP76) == 0x30, "SDHI final response");
_Static_assert(offsetof(R_SDHI0_Type, SD_BUF0) == 0x60, "SDHI buffer port");
_Static_assert(offsetof(R_SDHI0_Type, EXT_SWAP) == 0x1E0, "SDHI swap control");
_Static_assert(R_SDHI1_S_BASE == 0x40252400, "SDHI instance stride");
