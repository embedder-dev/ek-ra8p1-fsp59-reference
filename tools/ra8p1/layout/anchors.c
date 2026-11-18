/* Independent anchors transcribed from RA8P1 HM R01UH1064EJ0130.
 * These deliberately do not obtain expected values from the generator input.
 */
#include <stddef.h>
#include <stdint.h>
#include "bsp_exceptions.h"
#include "R7KA8P1KF.h"

#define OFFSET(type, member, expected) _Static_assert(offsetof(type, member) == (expected), #type "." #member)
#define WIDTH(type, member, expected) _Static_assert(sizeof(((type *) 0)->member) == (expected), #type "." #member " width")

/* HM §§2.1,2.3 pp.111–117: both cores have FPU, DSP, SAU and 4 priority bits. */
_Static_assert(__NVIC_PRIO_BITS == 4U, "NVIC priorities");
_Static_assert(__FPU_PRESENT == 1U, "FPU");
_Static_assert(__DSP_PRESENT == 1U, "DSP");
_Static_assert(__SAUREGION_PRESENT == 1U, "SAU");
#if BSP_CFG_CPU_CORE == 0
_Static_assert(__CORTEX_M == 85U, "CPU0 CM85");
_Static_assert(__CM85_REV == 0x0101U, "CM85 r1p1");
_Static_assert(__FPU_DP == 1U, "CPU0 double precision");
#else
_Static_assert(__CORTEX_M == 33U, "CPU1 CM33");
_Static_assert(__CM33_REV == 0x0004U, "CM33 r0p4");
_Static_assert(__ICACHE_PRESENT == 0U, "CM33 cache is external, not SCB I-cache");
#endif

/* HM §§9.2.2–9.2.7 pp.327–335. The PLL map differs from RA8M1. */
OFFSET(R_SYSTEM_Type, SCKDIVCR, 0x20);
OFFSET(R_SYSTEM_Type, SCKDIVCR2, 0x24);
OFFSET(R_SYSTEM_Type, SCKSCR, 0x26);
OFFSET(R_SYSTEM_Type, PLLCCR, 0xAC);
OFFSET(R_SYSTEM_Type, PLLCCR2, 0x4C);
WIDTH(R_SYSTEM_Type, SCKDIVCR2, 2);
WIDTH(R_SYSTEM_Type, PLLCCR, 4);
_Static_assert(R_SYSTEM_SCKDIVCR_MRPCK_Msk == 0xF0000000UL, "MRAM peripheral divider");
_Static_assert(R_SYSTEM_SCKDIVCR2_CPUCK0_Msk == 0x000FUL, "CPU0 divider");
_Static_assert(R_SYSTEM_SCKDIVCR2_CPUCK1_Msk == 0x00F0UL, "CPU1 divider");
_Static_assert(R_SYSTEM_SCKDIVCR2_NPUCK_Msk == 0x0F00UL, "NPU divider");
_Static_assert(R_SYSTEM_SCKDIVCR2_MRICK_Msk == 0xF000UL, "MRAM bus divider");

/* HM §§13.2.1–2 pp.525–527; §§14.2.12–22 pp.542–560. */
OFFSET(R_SYSTEM_Type, PRCR_S, 0x3FA);
OFFSET(R_SYSTEM_Type, PRCR_NS, 0x3FE);
WIDTH(R_SYSTEM_Type, PRCR_S, 2);
OFFSET(R_ICU_Type, NMIER, 0x100);
OFFSET(R_ICU_Type, NMICLR, 0x110);
OFFSET(R_ICU_Type, NMISR, 0x120);
WIDTH(R_ICU_Type, NMIER, 4);
OFFSET(R_ICU_Type, DELSR[7], 0x29C);
OFFSET(R_ICU_Type, IELSR[95], 0x47C);
_Static_assert(sizeof(R_ICU_Type) == 0x480U, "ICU slice extent");
_Static_assert(R_ICU_IELSR_IELS_Msk == 0x3FFUL, "10-bit event selector");
_Static_assert(R_ICU_IELSR_IR_Msk == 0x00010000UL, "interrupt status");
_Static_assert(R_ICU_IELSR_DTCE_Msk == 0x01000000UL, "DTC enable");
/* HM §14.2.12 pp.539–540: external IRQ arrays are in the shared block. */
OFFSET(R_ICU_COMMON_Type, IRQCRa[0], 0x00);
OFFSET(R_ICU_COMMON_Type, IRQCRa[15], 0x0F);
OFFSET(R_ICU_COMMON_Type, NMICR, 0x10);
OFFSET(R_ICU_COMMON_Type, IRQCRb[0], 0x14);
OFFSET(R_ICU_COMMON_Type, IRQCRb[15], 0x23);
WIDTH(R_ICU_COMMON_Type, IRQCRa[0], 1);
WIDTH(R_ICU_COMMON_Type, IRQCRb[0], 1);
_Static_assert(R_ICU_COMMON_IRQCRa_IRQMD_Msk == 3UL, "IRQ sense");
_Static_assert(R_ICU_COMMON_IRQCRb_FCLKSEL_Msk == 0x30UL, "IRQ clock");
_Static_assert(R_ICU_COMMON_IRQCRb_FLTEN_Msk == 0x80UL, "IRQ filter");

/* HM §§20.2.1–3 pp.829–831: software event and link register strides. */
OFFSET(R_ELC_Type, ELSEGR[0].BY, 0x04);
OFFSET(R_ELC_Type, ELSEGR[3].BY, 0x10);
OFFSET(R_ELC_Type, ELSR[0].HA, 0x20);
OFFSET(R_ELC_Type, ELSR[12].HA, 0x50);
OFFSET(R_ELC_Type, ELSR[52].HA, 0xF0);
WIDTH(R_ELC_Type, ELSEGR[0].BY, 1);
WIDTH(R_ELC_Type, ELSR[0].HA, 2);
_Static_assert(sizeof(R_ELC_ELSEGR_Type) == 4, "software event stride");
_Static_assert(sizeof(R_ELC_ELSR_Type) == 4, "event selector stride");
_Static_assert(R_ELC_ELSEGR_BY_SEG_Msk == 1UL, "software event generate");
_Static_assert(R_ELC_ELSEGR_BY_WE_Msk == 0x40UL, "software event enable");
_Static_assert(R_ELC_ELSEGR_BY_WI_Msk == 0x80UL, "software event protection");
_Static_assert(R_ELC_ELSR_HA_ELS_Msk == 0x3FFUL, "10-bit ELC event");
OFFSET(R_ICU_COMMON_Type, IRQCR16, 0x14);
OFFSET(R_ICU_COMMON_Type, IRQCR31, 0x23);
OFFSET(R_ICU_COMMON_Type, INTSELR[31], 0xBC);

/* HM §§15.3.11–22 pp.609–617: SDRAMC at BUS+0xC00. */
OFFSET(R_BUS_Type, SDRAM, 0xC00);
OFFSET(R_BUS_Type, SDRAM.SDCCR, 0xC00);
OFFSET(R_BUS_Type, SDRAM.SDCMOD, 0xC01);
OFFSET(R_BUS_Type, SDRAM.SDAMOD, 0xC02);
OFFSET(R_BUS_Type, SDRAM.SDSELF, 0xC10);
OFFSET(R_BUS_Type, SDRAM.SDRFCR, 0xC14);
OFFSET(R_BUS_Type, SDRAM.SDRFEN, 0xC16);
OFFSET(R_BUS_Type, SDRAM.SDICR, 0xC20);
OFFSET(R_BUS_Type, SDRAM.SDIR, 0xC24);
OFFSET(R_BUS_Type, SDRAM.SDADR, 0xC40);
OFFSET(R_BUS_Type, SDRAM.SDTR, 0xC44);
OFFSET(R_BUS_Type, SDRAM.SDMOD, 0xC48);
OFFSET(R_BUS_Type, SDRAM.SDSR, 0xC50);
WIDTH(R_BUS_SDRAM_Type, SDCCR, 1);
WIDTH(R_BUS_SDRAM_Type, SDCMOD, 1);
WIDTH(R_BUS_SDRAM_Type, SDAMOD, 1);
WIDTH(R_BUS_SDRAM_Type, SDSELF, 1);
WIDTH(R_BUS_SDRAM_Type, SDRFCR, 2);
WIDTH(R_BUS_SDRAM_Type, SDRFEN, 1);
WIDTH(R_BUS_SDRAM_Type, SDICR, 1);
WIDTH(R_BUS_SDRAM_Type, SDIR, 2);
WIDTH(R_BUS_SDRAM_Type, SDADR, 1);
WIDTH(R_BUS_SDRAM_Type, SDTR, 4);
WIDTH(R_BUS_SDRAM_Type, SDMOD, 2);
WIDTH(R_BUS_SDRAM_Type, SDSR, 1);
_Static_assert(sizeof(R_BUS_SDRAM_Type) == 0x54U, "SDRAM cluster padded to word alignment");
/* HM15.3.30–31 pp625–626: the expanded BUS includes the final MBWERR block. */
OFFSET(R_BUS_Type, MBWERR.ERRSTAT, 0x1B00);
OFFSET(R_BUS_Type, MBWERR.ERRCLR, 0x1B08);
WIDTH(R_BUS_MBWERR_Type, ERRCLR, 4);
_Static_assert(sizeof(R_BUS_Type) == 0x1B0CU, "BUS extent through MBWERRCLR");
_Static_assert(R_BUS_SDRAM_SDCCR_EXENB_Msk == 1U, "SDRAM access enable");
_Static_assert(R_BUS_SDRAM_SDCCR_BSIZE_Pos == 4U, "SDRAM width position");
_Static_assert(R_BUS_SDRAM_SDCCR_BSIZE_Msk == 0x30U, "SDRAM width mask");
_Static_assert(R_BUS_SDRAM_SDIR_ARFI_Pos == 0U, "initial refresh interval");
_Static_assert(R_BUS_SDRAM_SDIR_ARFC_Pos == 4U, "initial refresh count");
_Static_assert(R_BUS_SDRAM_SDIR_PRC_Pos == 8U, "initial precharge interval");
_Static_assert(R_BUS_SDRAM_SDTR_CL_Msk == 7U, "column latency");
_Static_assert(R_BUS_SDRAM_SDTR_WR_Msk == 0x100U, "write recovery");
_Static_assert(R_BUS_SDRAM_SDTR_RP_Msk == 0xE00U, "row precharge interval");
_Static_assert(R_BUS_SDRAM_SDTR_RCD_Msk == 0x3000U, "row column latency");
_Static_assert(R_BUS_SDRAM_SDTR_RAI_Msk == 0x70000U, "row active interval");
_Static_assert(R_BUS_SDRAM_SDRFCR_RFC_Msk == 0xFFFU, "refresh interval");
_Static_assert(R_BUS_SDRAM_SDRFCR_REFW_Msk == 0xF000U, "refresh cycles");
_Static_assert(R_BUS_SDRAM_SDSR_MRSST_Msk == 1U, "mode-register status");
_Static_assert(R_BUS_SDRAM_SDSR_INIST_Msk == 8U, "initialization status");
_Static_assert(R_BUS_SDRAM_SDSR_SRFST_Msk == 0x10U, "self-refresh status");

/* HM §§15.3.28–29 pp.623–624: halfword bus-error policy and protection. */
OFFSET(R_BUS_Type, BUSOAD, 0x1000);
OFFSET(R_BUS_Type, BUSOADPT, 0x1004);
WIDTH(R_BUS_Type, BUSOAD, 2);
WIDTH(R_BUS_Type, BUSOADPT, 2);
_Static_assert(R_BUS_BUSOAD_ILERROAD_Msk == 0x1UL, "illegal-address error policy");
_Static_assert(R_BUS_BUSOAD_SLERROAD_Pos == 1U, "slave-bus error policy position");
_Static_assert(R_BUS_BUSOAD_SLERROAD_Msk == 0x2UL, "slave-bus error policy");
_Static_assert(R_BUS_BUSOAD_BWERROAD_Msk == 0x4UL, "bufferable-write error policy");
_Static_assert(R_BUS_BUSOADPT_PROTECT_Msk == 0x1UL, "bus policy protection");
_Static_assert(R_BUS_BUSOADPT_KEY_Pos == 8U, "bus policy key position");
_Static_assert(R_BUS_BUSOADPT_KEY_Msk == 0xFF00UL, "bus policy key mask");

/* HM §11.2.6–10 pp.444–450; §21.2 pp.850–858. */
OFFSET(R_MSTP_Type, MSTPCRA, 0);
OFFSET(R_MSTP_Type, MSTPCRE, 0x10);
_Static_assert(sizeof(R_MSTP_Type) == 0x14U, "module stop layout");
OFFSET(R_PORT0_Type, PODR, 2);
OFFSET(R_PORT0_Type, PIDR, 4);
OFFSET(R_PORT0_Type, POSR, 8);
OFFSET(R_PORT0_Type, PORR, 10);
_Static_assert(sizeof(R_PORT0_Type) == 0x10U, "port register extent, not stride");
OFFSET(R_PFS_Type, PORT[13].PIN[15].PmnPFS, 0x37C);
WIDTH(R_PFS_PORT_PIN_Type, PmnPFS, 4);
WIDTH(R_PFS_PORT_PIN_Type, PmnPFS_HA, 2);
WIDTH(R_PFS_PORT_PIN_Type, PmnPFS_BY, 1);
_Static_assert(R_PFS_PORT_PIN_PmnPFS_DSCR_Msk == 0xC00UL, "drive field");
_Static_assert(R_PFS_PORT_PIN_PmnPFS_PSEL_Msk == 0x1F000000UL, "5-bit function");
OFFSET(R_PMISC_Type, PWPR, 0xC);
OFFSET(R_PMISC_Type, PWPRS, 0x14);
OFFSET(R_PMISC_Type, PMSAR[13].PMSAR, 0x64);
WIDTH(R_PMISC_PMSAR_Type, PMSAR, 2);

/* HM §28.2 pp.1267–1273; ICU §14.2 p.530 and §14.2.14 pp.545–547.
 * WDT instances are 0x100 apart; the ICU address is instead CPU-local.
 */
OFFSET(R_WDT0_Type, WDTRR, 0);
OFFSET(R_WDT0_Type, WDTCR, 2);
OFFSET(R_WDT0_Type, WDTSR, 4);
OFFSET(R_WDT0_Type, WDTRCR, 6);
OFFSET(R_WDT0_Type, WDTCSTPR, 8);
WIDTH(R_WDT0_Type, WDTRR, 1);
WIDTH(R_WDT0_Type, WDTCR, 2);
WIDTH(R_WDT0_Type, WDTSR, 2);
WIDTH(R_WDT0_Type, WDTRCR, 1);
WIDTH(R_WDT0_Type, WDTCSTPR, 1);
_Static_assert(R_WDT0_S_BASE == 0x40202600UL, "WDT0 secure base");
_Static_assert(R_WDT1_S_BASE == R_WDT0_S_BASE + 0x100UL, "WDT instance stride");
_Static_assert(R_WDT1_NS_BASE == R_WDT0_NS_BASE + 0x100UL, "NS WDT instance stride");
_Static_assert(R_WDT0_WDTCR_CKS_Msk == 0xF0UL, "WDT clock divider field");
_Static_assert(R_WDT0_WDTSR_CNTVAL_Msk == 0x3FFFUL, "WDT counter width");
_Static_assert(R_ICU_NMIER_WDTEN_Pos == 1U, "WDT NMI enable");
_Static_assert(R_ICU_NMIER_WDTEN_Msk == 2UL, "WDT NMI enable mask");

/* HM §§17.2.4–19 pp.742–753; channel stride is distinct from DMA global. */
_Static_assert(sizeof(R_DMAC0_Type) == 0x34U, "DMAC register extent");
OFFSET(R_DMAC0_Type, DMCRA, 0x08);
OFFSET(R_DMAC0_Type, DMTMD, 0x10);
OFFSET(R_DMAC0_Type, DMINT, 0x13);
OFFSET(R_DMAC0_Type, DMAMD, 0x14);
OFFSET(R_DMAC0_Type, DMSRR, 0x20);
OFFSET(R_DMAC0_Type, DMDRR, 0x24);
OFFSET(R_DMAC0_Type, DMBWR, 0x30);
WIDTH(R_DMAC0_Type, DMTMD, 2);
WIDTH(R_DMAC0_Type, DMINT, 1);
_Static_assert(R_DMAC0_S_BASE == 0x4000A000UL, "CPU-local DMAC channel base");
_Static_assert(R_DMAC7_S_BASE - R_DMAC0_S_BASE == 7 * 0x40UL, "DMAC channels");
_Static_assert(R_DMA_S_BASE == 0x4000A800UL, "global DMA controller retained");
_Static_assert(R_DMAC0_DMTMD_SZ_Msk == 0x300UL, "DMAC transfer width");

/* HM §23.2 pp.894–985: GPT32n n=0..13, not a sibling channel count. */
_Static_assert(sizeof(R_GPT0_Type) == 0xF0U, "GPT extent");
OFFSET(R_GPT0_Type, GTCR, 0x2C);
OFFSET(R_GPT0_Type, GTCCR[0], 0x4C);
OFFSET(R_GPT0_Type, GTCCR[5], 0x60);
OFFSET(R_GPT0_Type, GTCCRE, 0x58);
OFFSET(R_GPT0_Type, GTCCRD, 0x5C);
OFFSET(R_GPT0_Type, GTADTRA, 0x70);
OFFSET(R_GPT0_Type, GTADTRB, 0x7C);
OFFSET(R_GPT0_Type, GTICCR, 0xEC);
_Static_assert(R_GPT0_GTCR_TPCS_Msk == 0x07800000UL, "GPT prescaler");
_Static_assert(R_GPT13_S_BASE == 0x40322D00UL, "last GPT channel");
_Static_assert(R_GPT_OPS_S_BASE == 0x40323F00UL, "GPT output phase switch");
_Static_assert(R_GPT_GTCLK_S_BASE == 0x40323F10UL, "GPT clock control");

/* HM §39.2 pp.2190–2259 and §44.2 pp.2890–2916. */
_Static_assert(sizeof(R_SCI_B0_Type) == 0x7CU, "SCI_B extent");
OFFSET(R_SCI_B0_Type, RDR_BY, 0x00);
OFFSET(R_SCI_B0_Type, TDR_BY, 0x04);
OFFSET(R_SCI_B0_Type, TDRLL, 0x04);
OFFSET(R_SCI_B0_Type, TDRLH, 0x05);
OFFSET(R_SCI_B0_Type, CCR2, 0x10);
OFFSET(R_SCI_B0_Type, CESR, 0x1C);
OFFSET(R_SCI_B0_Type, CFCLR, 0x68);
_Static_assert(R_SCI_B0_CCR2_BRR_Msk == 0xFF00UL, "SCI_B baud divisor");
_Static_assert(R_SCI_B0_RDR_BY_RDAT_Msk == 0xFFUL, "SCI_B byte data");
_Static_assert(R_SCI_B9_S_BASE == 0x40358900UL, "SCI_B final channel");
_Static_assert(sizeof(R_SPI_B0_Type) == 0x70U, "SPI_B extent");
OFFSET(R_SPI_B0_Type, SPCMD[7], 0x30);
OFFSET(R_SPI_B0_Type, SPCMD7, 0x30);
OFFSET(R_SPI_B0_Type, SPSR, 0x50);
OFFSET(R_SPI_B0_Type, SPFCR, 0x6C);
_Static_assert(R_SPI_B0_SPCR_SPE_Msk == 1UL, "SPI_B enable differs from legacy SPI");
_Static_assert(R_SPI_B0_SPCMD0_SPB_Msk == 0x1F0000UL, "SPI_B word length");
_Static_assert(R_SPI_B1_S_BASE == 0x4035C100UL, "SPI_B second channel");

/* HM §28.2 p.1267; selected alias follows this candidate's per-core ownership. */
_Static_assert(sizeof(R_WDT_Type) == sizeof(R_WDT0_Type), "canonical WDT type");
#if BSP_CFG_CPU_CORE == 0
_Static_assert(R_WDT_S_BASE == 0x40202600UL, "CPU0 owns WDT0");
#else
_Static_assert(R_WDT_S_BASE == 0x40202700UL, "CPU1 owns WDT1");
#endif

/* HM §59.2 pp.3537–3548; CM33 TCM §2.17.3 pp.193–201. */
OFFSET(R_SRAM_Type, SRAMPRCR_S, 0);
OFFSET(R_SRAM_Type, SRAMPRCR_NS, 4);
OFFSET(R_SRAM_Type, SRAMWTSC, 8);
OFFSET(R_SRAM_Type, SRAMCR3, 0x1C);
OFFSET(R_CPSCU_Type, SRAMSABAR3, 0x40C);
_Static_assert(R_CPSCU_SRAMSABAR3_SRAMSABAR_Msk == 0x1FE000UL, "SRAM boundary");
OFFSET(R_CPSCU_Type, TCMSABARC, 0x508);
OFFSET(R_CPSCU_Type, TCMSABARS, 0x50C);
OFFSET(R_TCM_Type, TCMCRC, 0x10);
OFFSET(R_TCM_Type, TCMCRS, 0x14);
/* HM2.9.1.9 pp130–131: use the production ACTREQ definition, not a fixture mask. */
_Static_assert(R_CPU_CTRL_CPU1ACTCSR_ACTREQ_Pos == 0U, "CPU1 activation bit");
_Static_assert(R_CPU_CTRL_CPU1ACTCSR_ACTREQ_Msk == 1UL, "CPU1 activation mask");
/* HM42.2.11 pp2736–2738 and HM45.2.1.4 pp3000–3001. */
_Static_assert(R_CANFD_CFDGCFG_DCS_Pos == 4U, "CANFD clock select bit");
_Static_assert(R_CANFD_CFDGCFG_DCS_Msk == 0x10UL, "CANFD clock select mask");
_Static_assert(R_XSPI0_CMCFGCS_CMCFG0_ADDRPEN_Pos == 16U, "OSPI address replacement position");
_Static_assert(R_XSPI0_CMCFGCS_CMCFG0_ADDRPEN_Msk == 0x00FF0000UL, "OSPI address replacement width");

/* HM §60.5.1–3 pp.3561–3563. */
OFFSET(R_MRAM_Type, MRCPFB, 0);
OFFSET(R_MRAM_Type, MRCFREQ, 4);
OFFSET(R_MRAM_Type, MREFREQ, 8);
WIDTH(R_MRAM_Type, MRCPFB, 1);
WIDTH(R_MRAM_Type, MRCFREQ, 4);
_Static_assert(R_MRAM_MRCFREQ_MRCMHZ_Msk == 0x3FFUL, "code MHz width");
_Static_assert(R_MRAM_MREFREQ_MREMHZ_Msk == 0xFFUL, "extra MHz width");
_Static_assert(R_MRAM_MRCFREQ_KEY_Pos == 24U, "code MHz key");
_Static_assert(R_MRAM_MREFREQ_KEY_Pos == 24U, "extra MHz key");

/* HM §§60.5.14–39 pp.3571–3590; MSADDR is explicitly +0x2030. */
OFFSET(R_MRAM_Type, MREZS, 0x400);
OFFSET(R_MRAM_Type, MASTAT, 0x2010);
OFFSET(R_MRAM_Type, MSADDR, 0x2030);
OFFSET(R_MRAM_Type, MCNTSELR, 0x2048);
OFFSET(R_MRAM_Type, MCNTDTR0, 0x204C);
OFFSET(R_MRAM_Type, MCNTDTR1, 0x2050);
OFFSET(R_MRAM_Type, MCTRCNTR, 0x2060);
OFFSET(R_MRAM_Type, MCTRLSR, 0x2064);
OFFSET(R_MRAM_Type, MCTRSTATR, 0x206C);
OFFSET(R_MRAM_Type, MSTATR, 0x2080);
OFFSET(R_MRAM_Type, MENTRYR, 0x2084);
OFFSET(R_MRAM_Type, MSUASMON, 0x20DC);
OFFSET(R_MRAM_Type, MSUACR, 0x20E8);
OFFSET(R_MRAM_Type, MRCPC0, 0x3000);
OFFSET(R_MRAM_Type, MRCPC1, 0x3004);
OFFSET(R_MRAM_Type, MRCPS, 0x3010);
OFFSET(R_MRAM_Type, MRCFLR, 0x3030);
WIDTH(R_MRAM_Type, MASTAT, 1);
WIDTH(R_MRAM_Type, MCTRCNTR, 2);
WIDTH(R_MRAM_Type, MSTATR, 4);
_Static_assert(R_MRAM_MSTATR_MRDY_Msk == 0x8000UL, "MRAM ready");
_Static_assert(R_MRAM_MRCPS_PRGBSYC_Msk == 0x80UL, "code MRAM busy");

/* HM §55.2 pp.3501–3503: independent 16-bit data / 32-bit control units. */
OFFSET(R_DAC_B0_Type, DADR, 0);
OFFSET(R_DAC_B0_Type, DACR0, 4);
OFFSET(R_DAC_B0_Type, DACR1, 8);
OFFSET(R_DAC_B0_Type, DACR2, 12);
WIDTH(R_DAC_B0_Type, DADR, 2);
WIDTH(R_DAC_B0_Type, DACR0, 4);
_Static_assert(sizeof(R_DAC_B0_Type) == 0x10U, "DAC register extent");
_Static_assert(R_DAC_B0_S_BASE == 0x40233000UL, "DAC0 absolute base: HM55.2.1 p3501");
_Static_assert(R_DAC_B0_NS_BASE == 0x50233000UL, "DAC0 NS absolute base: HM55.2.1 p3501");
_Static_assert(R_DAC_B1_S_BASE == 0x40233100UL, "DAC1 absolute base: HM55.2.1 p3501");
_Static_assert(R_DAC_B1_NS_BASE == 0x50233100UL, "DAC1 NS absolute base: HM55.2.1 p3501");
_Static_assert(R_DAC_B1_S_BASE == R_DAC_B0_S_BASE + 0x100UL, "DAC unit stride");
_Static_assert(R_DAC_B0_DACR0_DACEN_Msk == 1UL, "DAC enable");
_Static_assert(R_DAC_B0_DACR0_DAE_Msk == 0x8000UL, "DAC collective enable");
_Static_assert(R_DAC_B0_DACR0_DAOUTDIS_Msk == 0x80000000UL, "DAC internal output");
_Static_assert(R_DAC_B0_DACR1_DPSEL_Msk == 0x10000UL, "DAC data alignment");
_Static_assert(R_DAC_B0_DACR2_OFSSEL_Msk == 0x100UL, "DAC voltage mode");

/* HM §50.2.1 pp.3202–3206 and §§50.2.15–20 pp.3215–3220. */
_Static_assert(R_PDM_S_BASE == 0x40256000UL, "PDM base");
_Static_assert(sizeof(R_PDM_CH_Type) == 0x100U, "PDM channel stride");
OFFSET(R_PDM_Type, CH[0], 0x100);
OFFSET(R_PDM_Type, CH[2], 0x300);
OFFSET(R_PDM_CH_Type, PDICR, 0xC);
OFFSET(R_PDM_CH_Type, PDSR, 0x14);
OFFSET(R_PDM_CH_Type, PDMDSR, 0x20);
OFFSET(R_PDM_CH_Type, PDSFCR, 0x24);
OFFSET(R_PDM_CH_Type, PDDRCR, 0xE0);
OFFSET(R_PDM_CH_Type, PDDRR, 0xE8);
WIDTH(R_PDM_CH_Type, PDDRR, 4);
_Static_assert(R_PDM_CH_PDICR_IDRE_Msk == 4UL, "PDM data IRQ enable");
_Static_assert(R_PDM_CH_PDICR_IEDE_Msk == 0x10000UL, "PDM error IRQ enable");
_Static_assert(R_PDM_CH_PDSR_STATE_Msk == 1UL, "PDM running");
_Static_assert(R_PDM_CH_PDSDCR_BFOWDE_Msk == 0x8000000UL, "PDM overflow detection");
_Static_assert(R_PDM_CH_PDMDSR_DBIS_Pos == 28U, "PDM buffer format");
_Static_assert(R_PDM_CH_PDSFCR_SINCDEC_Pos == 16U, "PDM decimation");

/* HM §54.2 pp.3327–3403: ADC_B, not the classic ADC register map. */
_Static_assert(R_ADC_B_S_BASE == 0x40338000UL, "ADC_B secure base");
OFFSET(R_ADC_B0_Type, ADCLKENR, 0);
OFFSET(R_ADC_B0_Type, ADGSPCR, 0x44);
OFFSET(R_ADC_B0_Type, ADTRGEXT0, 0xC0);
OFFSET(R_ADC_B0_Type, ADTRGEXT8, 0x140);
OFFSET(R_ADC_B0_Type, ADTRGGPT8, 0x148);
OFFSET(R_ADC_B0_Type, ADSSTR7, 0x25C);
OFFSET(R_ADC_B0_Type, ADUGTR7, 0x39C);
OFFSET(R_ADC_B0_Type, ADCHCR0, 0x600);
OFFSET(R_ADC_B0_Type, ADDOPCRA0, 0x604);
OFFSET(R_ADC_B0_Type, ADCHCR32, 0x800);
OFFSET(R_ADC_B0_Type, ADDOPCRC32, 0x80C);
OFFSET(R_ADC_B0_Type, ADCALSTR, 0xC00);
OFFSET(R_ADC_B0_Type, ADOVFCHSCR0, 0xCB8);
OFFSET(R_ADC_B0_Type, ADOVFEXSCR, 0xCC4);
OFFSET(R_ADC_B0_Type, ADFIFODCR, 0xCF0);
OFFSET(R_ADC_B0_Type, ADDR[22], 0x2058);
OFFSET(R_ADC_B0_Type, ADEXDR[22], 0x21D8);
OFFSET(R_ADC_B0_Type, ADFIFODR8, 0x2220);
WIDTH(R_ADC_B0_Type, ADUGTR0, 4);
WIDTH(R_ADC_B0_Type, ADDR[0], 4);
_Static_assert(R_ADC_B0_ADSYCR_ADSYCYC_Msk == 0xFFUL, "8-bit ADC sync period");
_Static_assert(R_ADC_B0_ADUGTR0_UGAIN_Msk == 0xFFFFUL, "Q2.14 gain value");
_Static_assert(R_ADC_B0_ADUOFTR0_UOFSET_Msk == 0xFFFFUL, "16-bit ADC offset");
_Static_assert(R_ADC_B0_ADOVFCHSCR0_OVFCHCn_Msk == 0x7FFFFFUL, "23 physical channels");
_Static_assert(R_ADC_B0_ADFIFODCR_FIFODCn_Msk == 0x1FFUL, "nine FIFO groups");
_Static_assert(R_ADC_B0_ADOVFEXSCR_OVFEXC8_Msk == (1UL << 8), "DAC0 overflow clear");
_Static_assert(R_ADC_B0_ADOVFEXSCR_OVFEXC17_Msk == (1UL << 17), "SH1 overflow clear");
_Static_assert(R_ADC_B0_ADDR_ERR_Msk == 0x80000000UL, "ADC data validity");

/* HM §56.2 pp.3508–3509: TSN control versus factory calibration storage. */
_Static_assert(R_TSN_CTRL_S_BASE == 0x40235000UL, "TSN control base");
_Static_assert(R_TSN_CAL_S_BASE == 0x02C1EDA0UL, "factory calibration base");
OFFSET(R_TSN_CAL_Type, TSCDR2, 4);
WIDTH(R_TSN_CTRL_Type, TSCR, 1);
WIDTH(R_TSN_CAL_Type, TSCDR, 4);
_Static_assert(R_TSN_CTRL_TSCR_TSEN_Msk == 0x80UL, "TSN enable");
_Static_assert(R_TSN_CTRL_TSCR_TSOE_Msk == 0x10UL, "TSN output enable");

/* HM §§27.2.20–23 pp.1241–1246; §27.2.27 pp.1248–1249. */
_Static_assert(R_RTC_S_BASE == 0x40202000UL, "RTC secure base");
_Static_assert(R_RTC_NS_BASE == 0x50202000UL, "RTC non-secure base");
OFFSET(R_RTC_Type, RCR1, 0x22);
OFFSET(R_RTC_Type, RCR2, 0x24);
OFFSET(R_RTC_Type, RCR4, 0x28);
OFFSET(R_RTC_Type, RTCCR[0].RTCCR, 0x40);
OFFSET(R_RTC_Type, RTCCR[1].RTCCR, 0x42);
OFFSET(R_RTC_Type, RTCCR[2].RTCCR, 0x44);
WIDTH(R_RTC_Type, RCR1, 1);
WIDTH(R_RTC_Type, RCR2, 1);
WIDTH(R_RTC_Type, RCR4, 1);
WIDTH(R_RTC_RTCCR_Type, RTCCR, 1);
_Static_assert(sizeof(R_RTC_RTCCR_Type) == 2U, "RTC capture control stride");
/* HM §§27.2.28–33 pp.1249–1251: capture arrays complete the RTC block. */
_Static_assert(sizeof(R_RTC_Type) == 0x80U, "RTC capture extent");
_Static_assert(R_RTC_RTCCR_RTCCR_TCCT_Msk == 0x03UL, "RTC capture edge control");
_Static_assert(R_RTC_RTCCR_RTCCR_TCST_Msk == 0x04UL, "RTC capture status");
_Static_assert(R_RTC_RTCCR_RTCCR_TCNF_Msk == 0x30UL, "RTC capture noise filter");
_Static_assert(R_RTC_RTCCR_RTCCR_TCEN_Msk == 0x80UL, "RTC capture pin enable");
_Static_assert(R_RTC_RCR2_RESET_Msk == 0x02UL, "RTC software reset");
_Static_assert(R_RTC_RCR4_RCKSEL_Pos == 0U, "RTC count source");
#if BSP_TZ_NONSECURE_BUILD
_Static_assert(R_RTC_BASE == 0x50202000UL, "RTC NS view");
#else
_Static_assert(R_RTC_BASE == 0x40202000UL, "RTC secure view");
#endif

/* HM Appendix3 pp.4285–4288: secure aliases precede NS by 0x10000000. */
_Static_assert(R_SYSTEM_S_BASE == 0x4001E000UL, "SYSC secure base");
_Static_assert(R_SYSTEM_NS_BASE == 0x5001E000UL, "SYSC NS base");
_Static_assert(R_ICU_S_BASE == 0x4000C000UL, "CPU-local ICU base");
_Static_assert(R_ICU_COMMON_S_BASE == 0x40006000UL, "common ICU base");
_Static_assert(R_PORTD_S_BASE == 0x404001A0UL, "portD base");
_Static_assert(R_PMISC_NS_BASE == 0x50400D00UL, "NS port protection");
_Static_assert(R_MRAM_S_BASE == 0x4013C000UL, "MRAM base");
#if BSP_TZ_NONSECURE_BUILD
_Static_assert(R_SYSTEM_BASE == 0x5001E000UL, "NS view");
#else
_Static_assert(R_SYSTEM_BASE == 0x4001E000UL, "secure view");
#endif
