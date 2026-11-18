/*
* Copyright (c) 2020 - 2025 Renesas Electronics Corporation and/or its affiliates
*
* SPDX-License-Identifier: BSD-3-Clause
*/

#ifndef BSP_ELC_H
#define BSP_ELC_H

/*******************************************************************************************************************//**
 * @addtogroup BSP_MCU_RA8P1
 * @{
 **********************************************************************************************************************/

/* UNCRUSTIFY-OFF */

/** ICU event numbers: HM Table 14.5, pp.563-576; DTC-only ELC sources: Table 20.3, p.833. */
typedef enum e_elc_event_ra8p1
{
    ELC_EVENT_NONE                           = (0x000),
    ELC_EVENT_ICU_IRQ0                       = (0x001), // PORT_IRQ0
    ELC_EVENT_ICU_IRQ1                       = (0x002), // PORT_IRQ1
    ELC_EVENT_ICU_IRQ2                       = (0x003), // PORT_IRQ2
    ELC_EVENT_ICU_IRQ3                       = (0x004), // PORT_IRQ3
    ELC_EVENT_ICU_IRQ4                       = (0x005), // PORT_IRQ4
    ELC_EVENT_ICU_IRQ5                       = (0x006), // PORT_IRQ5
    ELC_EVENT_ICU_IRQ6                       = (0x007), // PORT_IRQ6
    ELC_EVENT_ICU_IRQ7                       = (0x008), // PORT_IRQ7
    ELC_EVENT_ICU_IRQ8                       = (0x009), // PORT_IRQ8
    ELC_EVENT_ICU_IRQ9                       = (0x00A), // PORT_IRQ9
    ELC_EVENT_ICU_IRQ10                      = (0x00B), // PORT_IRQ10
    ELC_EVENT_ICU_IRQ11                      = (0x00C), // PORT_IRQ11
    ELC_EVENT_ICU_IRQ12                      = (0x00D), // PORT_IRQ12
    ELC_EVENT_ICU_IRQ13                      = (0x00E), // PORT_IRQ13
    ELC_EVENT_ICU_IRQ14                      = (0x00F), // PORT_IRQ14
    ELC_EVENT_ICU_IRQ15                      = (0x010), // PORT_IRQ15
    ELC_EVENT_ICU_IRQ16                      = (0x011), // PORT_IRQ16
    ELC_EVENT_ICU_IRQ17                      = (0x012), // PORT_IRQ17
    ELC_EVENT_ICU_IRQ18                      = (0x013), // PORT_IRQ18
    ELC_EVENT_ICU_IRQ19                      = (0x014), // PORT_IRQ19
    ELC_EVENT_ICU_IRQ20                      = (0x015), // PORT_IRQ20
    ELC_EVENT_ICU_IRQ21                      = (0x016), // PORT_IRQ21
    ELC_EVENT_ICU_IRQ22                      = (0x017), // PORT_IRQ22
    ELC_EVENT_ICU_IRQ23                      = (0x018), // PORT_IRQ23
    ELC_EVENT_ICU_IRQ24                      = (0x019), // PORT_IRQ24
    ELC_EVENT_ICU_IRQ25                      = (0x01A), // PORT_IRQ25
    ELC_EVENT_ICU_IRQ26                      = (0x01B), // PORT_IRQ26
    ELC_EVENT_ICU_IRQ27                      = (0x01C), // PORT_IRQ27
    ELC_EVENT_ICU_IRQ28                      = (0x01D), // PORT_IRQ28
    ELC_EVENT_ICU_IRQ29                      = (0x01E), // PORT_IRQ29
    ELC_EVENT_ICU_IRQ30                      = (0x01F), // PORT_IRQ30
    ELC_EVENT_ICU_IRQ31                      = (0x020), // PORT_IRQ31
    ELC_EVENT_DMAC0_INT                      = (0x040), // DMAC00_INT
    ELC_EVENT_DMAC1_INT                      = (0x041), // DMAC01_INT
    ELC_EVENT_DMAC2_INT                      = (0x042), // DMAC02_INT
    ELC_EVENT_DMAC3_INT                      = (0x043), // DMAC03_INT
    ELC_EVENT_DMAC4_INT                      = (0x044), // DMAC04_INT
    ELC_EVENT_DMAC5_INT                      = (0x045), // DMAC05_INT
    ELC_EVENT_DMAC6_INT                      = (0x046), // DMAC06_INT
    ELC_EVENT_DMAC7_INT                      = (0x047), // DMAC07_INT
    ELC_EVENT_DMAC8_INT                      = (0x048), // DMAC10_INT
    ELC_EVENT_DMAC9_INT                      = (0x049), // DMAC11_INT
    ELC_EVENT_DMAC10_INT                     = (0x04A), // DMAC12_INT
    ELC_EVENT_DMAC11_INT                     = (0x04B), // DMAC13_INT
    ELC_EVENT_DMAC12_INT                     = (0x04C), // DMAC14_INT
    ELC_EVENT_DMAC13_INT                     = (0x04D), // DMAC15_INT
    ELC_EVENT_DMAC14_INT                     = (0x04E), // DMAC16_INT
    ELC_EVENT_DMAC15_INT                     = (0x04F), // DMAC17_INT
    ELC_EVENT_DTC0_DTCEND                    = (0x052), // DTC0_DTCEND
    ELC_EVENT_DTC1_DTCEND                    = (0x055), // DTC1_DTCEND
    ELC_EVENT_DMA_TRANSERR                   = (0x056), // DMA0_TRANSERR
    ELC_EVENT_DMA1_TRANSERR                  = (0x057), // DMA1_TRANSERR
    ELC_EVENT_DBG_CTIIRQ0                    = (0x058), // DBG_CTIIRQ0
    ELC_EVENT_DBG_CTIIRQ1                    = (0x059), // DBG_CTIIRQ1
    ELC_EVENT_DBG_JBRXI                      = (0x05A), // DBG_JBRXI
    ELC_EVENT_IPC_IRQ0                       = (0x05B), // IPC_IRQ0
    ELC_EVENT_IPC_IRQ1                       = (0x05C), // IPC_IRQ1
    ELC_EVENT_LM0_ERR                        = (0x05F), // LM0_ERR
    ELC_EVENT_LM1_ERR                        = (0x060), // LM1_ERR
    ELC_EVENT_CPU0_LOCKUP                    = (0x061), // CPU0_LOCKUP
    ELC_EVENT_CPU1_LOCKUP                    = (0x062), // CPU1_LOCKUP
    ELC_EVENT_BUS_ERR                        = (0x063), // BUS_ERR
    ELC_EVENT_CM_ERR                         = (0x064), // CM_ERR
    ELC_EVENT_FPU_EXC                        = (0x065), // FPU_EXC
    ELC_EVENT_NPU_IRQ                        = (0x067), // NPU_IRQ
    ELC_EVENT_MRAM_MRCRD                     = (0x068), // MRAM_MRCRD
    ELC_EVENT_MRAM_MRERD                     = (0x069), // MRAM_MRERD
    ELC_EVENT_MRAM_MRCPR                     = (0x06B), // MRAM_MRCPR
    ELC_EVENT_MRAM_MREPR                     = (0x06C), // MRAM_MREPR
    ELC_EVENT_MRAM_ENDOFPE                   = (0x06D), // MRAM_ENDOFPE
    ELC_EVENT_LVD_LVD1                       = (0x070), // PVD_PVD1
    ELC_EVENT_LVD_LVD2                       = (0x071), // PVD_PVD2
    ELC_EVENT_VBATT_TADI                     = (0x075), // VBATT_TADI
    ELC_EVENT_CGC_MOSC_STOP                  = (0x076), // MOSC_STOP
    ELC_EVENT_CGC_SOSC_STOP                  = (0x077), // SOSC_STOP
    ELC_EVENT_ULPT0_INT                      = (0x080), // ULPT0_ULPTI
    ELC_EVENT_ULPT0_COMPARE_A                = (0x081), // ULPT0_ULPTCMAI
    ELC_EVENT_ULPT0_COMPARE_B                = (0x082), // ULPT0_ULPTCMBI
    ELC_EVENT_ULPT1_INT                      = (0x083), // ULPT1_ULPTI
    ELC_EVENT_ULPT1_COMPARE_A                = (0x084), // ULPT1_ULPTCMAI
    ELC_EVENT_ULPT1_COMPARE_B                = (0x085), // ULPT1_ULPTCMBI
    ELC_EVENT_AGT0_INT                       = (0x086), // AGT0_AGTI
    ELC_EVENT_AGT0_COMPARE_A                 = (0x087), // AGT0_AGTCMAI
    ELC_EVENT_AGT0_COMPARE_B                 = (0x088), // AGT0_AGTCMBI
    ELC_EVENT_AGT1_INT                       = (0x089), // AGT1_AGTI
    ELC_EVENT_AGT1_COMPARE_A                 = (0x08A), // AGT1_AGTCMAI
    ELC_EVENT_AGT1_COMPARE_B                 = (0x08B), // AGT1_AGTCMBI
    ELC_EVENT_IWDT_UNDERFLOW                 = (0x092), // IWDT_NMIUNDF
    ELC_EVENT_WDT0_UNDERFLOW                 = (0x093), // WDT0_NMIUNDF
    ELC_EVENT_WDT1_UNDERFLOW                 = (0x094), // WDT1_NMIUNDF
    ELC_EVENT_RTC_ALARM                      = (0x095), // RTC_ALM
    ELC_EVENT_RTC_PERIOD                     = (0x096), // RTC_PRD
    ELC_EVENT_RTC_CARRY                      = (0x097), // RTC_CUP
    ELC_EVENT_USBFS_FIFO_0                   = (0x098), // USBFS_D0FIFO
    ELC_EVENT_USBFS_FIFO_1                   = (0x099), // USBFS_D1FIFO
    ELC_EVENT_USBFS_INT                      = (0x09A), // USBFS_USBI
    ELC_EVENT_USBFS_RESUME                   = (0x09B), // USBFS_USBR
    ELC_EVENT_IIC0_RXI                       = (0x09C), // IIC0_RXI
    ELC_EVENT_IIC0_TXI                       = (0x09D), // IIC0_TXI
    ELC_EVENT_IIC0_TEI                       = (0x09E), // IIC0_TEI
    ELC_EVENT_IIC0_ERI                       = (0x09F), // IIC0_EEI
    ELC_EVENT_IIC0_WUI                       = (0x0A0), // IIC0_WUI
    ELC_EVENT_IIC1_RXI                       = (0x0A1), // IIC1_RXI
    ELC_EVENT_IIC1_TXI                       = (0x0A2), // IIC1_TXI
    ELC_EVENT_IIC1_TEI                       = (0x0A3), // IIC1_TEI
    ELC_EVENT_IIC1_ERI                       = (0x0A4), // IIC1_EEI
    ELC_EVENT_IIC2_RXI                       = (0x0A6), // IIC2_RXI
    ELC_EVENT_IIC2_TXI                       = (0x0A7), // IIC2_TXI
    ELC_EVENT_IIC2_TEI                       = (0x0A8), // IIC2_TEI
    ELC_EVENT_IIC2_ERI                       = (0x0A9), // IIC2_EEI
    ELC_EVENT_SDHIMMC0_ACCS                  = (0x0AB), // SDHI_MMC0_ACCS
    ELC_EVENT_SDHIMMC0_SDIO                  = (0x0AC), // SDHI_MMC0_SDIO
    ELC_EVENT_SDHIMMC0_CARD                  = (0x0AD), // SDHI_MMC0_CARD
    ELC_EVENT_SDHIMMC0_DMA_REQ               = (0x0AE), // SDHI_MMC0_ODMSDBREQ
    ELC_EVENT_SDHIMMC1_ACCS                  = (0x0AF), // SDHI_MMC1_ACCS
    ELC_EVENT_SDHIMMC1_SDIO                  = (0x0B0), // SDHI_MMC1_SDIO
    ELC_EVENT_SDHIMMC1_CARD                  = (0x0B1), // SDHI_MMC1_CARD
    ELC_EVENT_SDHIMMC1_DMA_REQ               = (0x0B2), // SDHI_MMC1_ODMSDBREQ
    ELC_EVENT_SSI0_TXI                       = (0x0B3), // SSI0_SSITXI
    ELC_EVENT_SSI0_RXI                       = (0x0B4), // SSI0_SSIRXI
    ELC_EVENT_SSI0_INT                       = (0x0B6), // SSI0_SSIF
    ELC_EVENT_SSI1_TXI_RXI                   = (0x0B9), // SSI1_SSIRT
    ELC_EVENT_SSI1_INT                       = (0x0BA), // SSI1_SSIF
    ELC_EVENT_XSPI_ERR                       = (0x0BB), // OSPI0_ERR
    ELC_EVENT_XSPI_CMP                       = (0x0BC), // OSPI0_CMP
    ELC_EVENT_OSPI1_ERR                      = (0x0BD), // OSPI1_ERR
    ELC_EVENT_OSPI1_CMP                      = (0x0BE), // OSPI1_CMP
    ELC_EVENT_PDM_DAT0                       = (0x0BF), // PDM_DAT0
    ELC_EVENT_PDM_DAT1                       = (0x0C0), // PDM_DAT1
    ELC_EVENT_PDM_DAT2                       = (0x0C1), // PDM_DAT2
    ELC_EVENT_PDM_SDET                       = (0x0C2), // PDM_SDET
    ELC_EVENT_PDM_ERR0                       = (0x0C3), // PDM_ERR0
    ELC_EVENT_PDM_ERR1                       = (0x0C4), // PDM_ERR1
    ELC_EVENT_PDM_ERR2                       = (0x0C5), // PDM_ERR2
    ELC_EVENT_ACMPHS0_INT                    = (0x0C6), // ACMP_HS0
    ELC_EVENT_ACMPHS1_INT                    = (0x0C7), // ACMP_HS1
    ELC_EVENT_ACMPHS2_INT                    = (0x0C8), // ACMP_HS2
    ELC_EVENT_ACMPHS3_INT                    = (0x0C9), // ACMP_HS3
    ELC_EVENT_ELC_SOFTWARE_EVENT_0           = (0x0CC), // ELC_SWEVT0
    ELC_EVENT_ELC_SOFTWARE_EVENT_1           = (0x0CD), // ELC_SWEVT1
    ELC_EVENT_ELC_SOFTWARE_EVENT_2           = (0x0CE), // ELC_SWEVT2
    ELC_EVENT_ELC_SOFTWARE_EVENT_3           = (0x0CF), // ELC_SWEVT3
    ELC_EVENT_IOPORT_EVENT_1                 = (0x0D0), // IOPORT_GROUP1
    ELC_EVENT_IOPORT_EVENT_2                 = (0x0D1), // IOPORT_GROUP2
    ELC_EVENT_IOPORT_EVENT_3                 = (0x0D2), // IOPORT_GROUP3
    ELC_EVENT_IOPORT_EVENT_4                 = (0x0D3), // IOPORT_GROUP4
    ELC_EVENT_CAC_FREQUENCY_ERROR            = (0x0D4), // CAC_FEERI
    ELC_EVENT_CAC_MEASUREMENT_END            = (0x0D5), // CAC_MENDI
    ELC_EVENT_CAC_OVERFLOW                   = (0x0D6), // CAC_OVFI
    ELC_EVENT_POEG0_EVENT                    = (0x0D7), // POEG_GROUPA
    ELC_EVENT_POEG1_EVENT                    = (0x0D8), // POEG_GROUPB
    ELC_EVENT_POEG2_EVENT                    = (0x0D9), // POEG_GROUPC
    ELC_EVENT_POEG3_EVENT                    = (0x0DA), // POEG_GROUPD
    ELC_EVENT_OPS_UVW_EDGE                   = (0x180), // GPT_UVWEDGE
    ELC_EVENT_GPT0_CAPTURE_COMPARE_A         = (0x181), // GPT0_CCMPA
    ELC_EVENT_GPT0_CAPTURE_COMPARE_B         = (0x182), // GPT0_CCMPB
    ELC_EVENT_GPT0_COMPARE_C                 = (0x183), // GPT0_CMPC
    ELC_EVENT_GPT0_COMPARE_D                 = (0x184), // GPT0_CMPD
    ELC_EVENT_GPT0_COMPARE_E                 = (0x185), // GPT0_CMPE
    ELC_EVENT_GPT0_COMPARE_F                 = (0x186), // GPT0_CMPF
    ELC_EVENT_GPT0_COUNTER_OVERFLOW          = (0x187), // GPT0_OVF
    ELC_EVENT_GPT0_COUNTER_UNDERFLOW         = (0x188), // GPT0_UDF
    ELC_EVENT_GPT0_PC                        = (0x189), // GPT0_PC
    ELC_EVENT_GPT1_CAPTURE_COMPARE_A         = (0x18A), // GPT1_CCMPA
    ELC_EVENT_GPT1_CAPTURE_COMPARE_B         = (0x18B), // GPT1_CCMPB
    ELC_EVENT_GPT1_COMPARE_C                 = (0x18C), // GPT1_CMPC
    ELC_EVENT_GPT1_COMPARE_D                 = (0x18D), // GPT1_CMPD
    ELC_EVENT_GPT1_COMPARE_E                 = (0x18E), // GPT1_CMPE
    ELC_EVENT_GPT1_COMPARE_F                 = (0x18F), // GPT1_CMPF
    ELC_EVENT_GPT1_COUNTER_OVERFLOW          = (0x190), // GPT1_OVF
    ELC_EVENT_GPT1_COUNTER_UNDERFLOW         = (0x191), // GPT1_UDF
    ELC_EVENT_GPT1_PC                        = (0x192), // GPT1_PC
    ELC_EVENT_GPT2_CAPTURE_COMPARE_A         = (0x193), // GPT2_CCMPA
    ELC_EVENT_GPT2_CAPTURE_COMPARE_B         = (0x194), // GPT2_CCMPB
    ELC_EVENT_GPT2_COMPARE_C                 = (0x195), // GPT2_CMPC
    ELC_EVENT_GPT2_COMPARE_D                 = (0x196), // GPT2_CMPD
    ELC_EVENT_GPT2_COMPARE_E                 = (0x197), // GPT2_CMPE
    ELC_EVENT_GPT2_COMPARE_F                 = (0x198), // GPT2_CMPF
    ELC_EVENT_GPT2_COUNTER_OVERFLOW          = (0x199), // GPT2_OVF
    ELC_EVENT_GPT2_COUNTER_UNDERFLOW         = (0x19A), // GPT2_UDF
    ELC_EVENT_GPT2_PC                        = (0x19B), // GPT2_PC
    ELC_EVENT_GPT3_CAPTURE_COMPARE_A         = (0x19C), // GPT3_CCMPA
    ELC_EVENT_GPT3_CAPTURE_COMPARE_B         = (0x19D), // GPT3_CCMPB
    ELC_EVENT_GPT3_COMPARE_C                 = (0x19E), // GPT3_CMPC
    ELC_EVENT_GPT3_COMPARE_D                 = (0x19F), // GPT3_CMPD
    ELC_EVENT_GPT3_COMPARE_E                 = (0x1A0), // GPT3_CMPE
    ELC_EVENT_GPT3_COMPARE_F                 = (0x1A1), // GPT3_CMPF
    ELC_EVENT_GPT3_COUNTER_OVERFLOW          = (0x1A2), // GPT3_OVF
    ELC_EVENT_GPT3_COUNTER_UNDERFLOW         = (0x1A3), // GPT3_UDF
    ELC_EVENT_GPT3_PC                        = (0x1A4), // GPT3_PC
    ELC_EVENT_GPT4_CAPTURE_COMPARE_A         = (0x1A5), // GPT4_CCMPA
    ELC_EVENT_GPT4_CAPTURE_COMPARE_B         = (0x1A6), // GPT4_CCMPB
    ELC_EVENT_GPT4_COMPARE_C                 = (0x1A7), // GPT4_CMPC
    ELC_EVENT_GPT4_COMPARE_D                 = (0x1A8), // GPT4_CMPD
    ELC_EVENT_GPT4_COMPARE_E                 = (0x1A9), // GPT4_CMPE
    ELC_EVENT_GPT4_COMPARE_F                 = (0x1AA), // GPT4_CMPF
    ELC_EVENT_GPT4_COUNTER_OVERFLOW          = (0x1AB), // GPT4_OVF
    ELC_EVENT_GPT4_COUNTER_UNDERFLOW         = (0x1AC), // GPT4_UDF
    ELC_EVENT_GPT5_CAPTURE_COMPARE_A         = (0x1AE), // GPT5_CCMPA
    ELC_EVENT_GPT5_CAPTURE_COMPARE_B         = (0x1AF), // GPT5_CCMPB
    ELC_EVENT_GPT5_COMPARE_C                 = (0x1B0), // GPT5_CMPC
    ELC_EVENT_GPT5_COMPARE_D                 = (0x1B1), // GPT5_CMPD
    ELC_EVENT_GPT5_COMPARE_E                 = (0x1B2), // GPT5_CMPE
    ELC_EVENT_GPT5_COMPARE_F                 = (0x1B3), // GPT5_CMPF
    ELC_EVENT_GPT5_COUNTER_OVERFLOW          = (0x1B4), // GPT5_OVF
    ELC_EVENT_GPT5_COUNTER_UNDERFLOW         = (0x1B5), // GPT5_UDF
    ELC_EVENT_GPT6_CAPTURE_COMPARE_A         = (0x1B7), // GPT6_CCMPA
    ELC_EVENT_GPT6_CAPTURE_COMPARE_B         = (0x1B8), // GPT6_CCMPB
    ELC_EVENT_GPT6_COMPARE_C                 = (0x1B9), // GPT6_CMPC
    ELC_EVENT_GPT6_COMPARE_D                 = (0x1BA), // GPT6_CMPD
    ELC_EVENT_GPT6_COMPARE_E                 = (0x1BB), // GPT6_CMPE
    ELC_EVENT_GPT6_COMPARE_F                 = (0x1BC), // GPT6_CMPF
    ELC_EVENT_GPT6_COUNTER_OVERFLOW          = (0x1BD), // GPT6_OVF
    ELC_EVENT_GPT6_COUNTER_UNDERFLOW         = (0x1BE), // GPT6_UDF
    ELC_EVENT_GPT7_CAPTURE_COMPARE_A         = (0x1C0), // GPT7_CCMPA
    ELC_EVENT_GPT7_CAPTURE_COMPARE_B         = (0x1C1), // GPT7_CCMPB
    ELC_EVENT_GPT7_COMPARE_C                 = (0x1C2), // GPT7_CMPC
    ELC_EVENT_GPT7_COMPARE_D                 = (0x1C3), // GPT7_CMPD
    ELC_EVENT_GPT7_COMPARE_E                 = (0x1C4), // GPT7_CMPE
    ELC_EVENT_GPT7_COMPARE_F                 = (0x1C5), // GPT7_CMPF
    ELC_EVENT_GPT7_COUNTER_OVERFLOW          = (0x1C6), // GPT7_OVF
    ELC_EVENT_GPT7_COUNTER_UNDERFLOW         = (0x1C7), // GPT7_UDF
    ELC_EVENT_GPT8_CAPTURE_COMPARE_A         = (0x1C9), // GPT8_CCMPA
    ELC_EVENT_GPT8_CAPTURE_COMPARE_B         = (0x1CA), // GPT8_CCMPB
    ELC_EVENT_GPT8_COMPARE_C                 = (0x1CB), // GPT8_CMPC
    ELC_EVENT_GPT8_COMPARE_D                 = (0x1CC), // GPT8_CMPD
    ELC_EVENT_GPT8_COMPARE_E                 = (0x1CD), // GPT8_CMPE
    ELC_EVENT_GPT8_COMPARE_F                 = (0x1CE), // GPT8_CMPF
    ELC_EVENT_GPT8_COUNTER_OVERFLOW          = (0x1CF), // GPT8_OVF
    ELC_EVENT_GPT8_COUNTER_UNDERFLOW         = (0x1D0), // GPT8_UDF
    ELC_EVENT_GPT9_CAPTURE_COMPARE_A         = (0x1D2), // GPT9_CCMPA
    ELC_EVENT_GPT9_CAPTURE_COMPARE_B         = (0x1D3), // GPT9_CCMPB
    ELC_EVENT_GPT9_COMPARE_C                 = (0x1D4), // GPT9_CMPC
    ELC_EVENT_GPT9_COMPARE_D                 = (0x1D5), // GPT9_CMPD
    ELC_EVENT_GPT9_COMPARE_E                 = (0x1D6), // GPT9_CMPE
    ELC_EVENT_GPT9_COMPARE_F                 = (0x1D7), // GPT9_CMPF
    ELC_EVENT_GPT9_COUNTER_OVERFLOW          = (0x1D8), // GPT9_OVF
    ELC_EVENT_GPT9_COUNTER_UNDERFLOW         = (0x1D9), // GPT9_UDF
    ELC_EVENT_GPT10_CAPTURE_COMPARE_A        = (0x1DB), // GPT10_CCMPA
    ELC_EVENT_GPT10_CAPTURE_COMPARE_B        = (0x1DC), // GPT10_CCMPB
    ELC_EVENT_GPT10_COMPARE_C                = (0x1DD), // GPT10_CMPC
    ELC_EVENT_GPT10_COMPARE_D                = (0x1DE), // GPT10_CMPD
    ELC_EVENT_GPT10_COMPARE_E                = (0x1DF), // GPT10_CMPE
    ELC_EVENT_GPT10_COMPARE_F                = (0x1E0), // GPT10_CMPF
    ELC_EVENT_GPT10_COUNTER_OVERFLOW         = (0x1E1), // GPT10_OVF
    ELC_EVENT_GPT10_COUNTER_UNDERFLOW        = (0x1E2), // GPT10_UDF
    ELC_EVENT_GPT10_PC                       = (0x1E3), // GPT10_PC
    ELC_EVENT_GPT11_CAPTURE_COMPARE_A        = (0x1E4), // GPT11_CCMPA
    ELC_EVENT_GPT11_CAPTURE_COMPARE_B        = (0x1E5), // GPT11_CCMPB
    ELC_EVENT_GPT11_COMPARE_C                = (0x1E6), // GPT11_CMPC
    ELC_EVENT_GPT11_COMPARE_D                = (0x1E7), // GPT11_CMPD
    ELC_EVENT_GPT11_COMPARE_E                = (0x1E8), // GPT11_CMPE
    ELC_EVENT_GPT11_COMPARE_F                = (0x1E9), // GPT11_CMPF
    ELC_EVENT_GPT11_COUNTER_OVERFLOW         = (0x1EA), // GPT11_OVF
    ELC_EVENT_GPT11_COUNTER_UNDERFLOW        = (0x1EB), // GPT11_UDF
    ELC_EVENT_GPT11_PC                       = (0x1EC), // GPT11_PC
    ELC_EVENT_GPT12_CAPTURE_COMPARE_A        = (0x1ED), // GPT12_CCMPA
    ELC_EVENT_GPT12_CAPTURE_COMPARE_B        = (0x1EE), // GPT12_CCMPB
    ELC_EVENT_GPT12_COMPARE_C                = (0x1EF), // GPT12_CMPC
    ELC_EVENT_GPT12_COMPARE_D                = (0x1F0), // GPT12_CMPD
    ELC_EVENT_GPT12_COMPARE_E                = (0x1F1), // GPT12_CMPE
    ELC_EVENT_GPT12_COMPARE_F                = (0x1F2), // GPT12_CMPF
    ELC_EVENT_GPT12_COUNTER_OVERFLOW         = (0x1F3), // GPT12_OVF
    ELC_EVENT_GPT12_COUNTER_UNDERFLOW        = (0x1F4), // GPT12_UDF
    ELC_EVENT_GPT12_PC                       = (0x1F5), // GPT12_PC
    ELC_EVENT_GPT13_CAPTURE_COMPARE_A        = (0x1F6), // GPT13_CCMPA
    ELC_EVENT_GPT13_CAPTURE_COMPARE_B        = (0x1F7), // GPT13_CCMPB
    ELC_EVENT_GPT13_COMPARE_C                = (0x1F8), // GPT13_CMPC
    ELC_EVENT_GPT13_COMPARE_D                = (0x1F9), // GPT13_CMPD
    ELC_EVENT_GPT13_COMPARE_E                = (0x1FA), // GPT13_CMPE
    ELC_EVENT_GPT13_COMPARE_F                = (0x1FB), // GPT13_CMPF
    ELC_EVENT_GPT13_COUNTER_OVERFLOW         = (0x1FC), // GPT13_OVF
    ELC_EVENT_GPT13_COUNTER_UNDERFLOW        = (0x1FD), // GPT13_UDF
    ELC_EVENT_GPT13_PC                       = (0x1FE), // GPT13_PC
    ELC_EVENT_ETHER_FWEI                     = (0x29A), // ETHER_FWEI
    ELC_EVENT_ETHER_CAEI                     = (0x29B), // ETHER_CAEI
    ELC_EVENT_ETHER_GWEI                     = (0x29C), // ETHER_GWEI
    ELC_EVENT_ETHER_EAEI0                    = (0x29D), // ETHER_EAEI0
    ELC_EVENT_ETHER_EAEI1                    = (0x29E), // ETHER_EAEI1
    ELC_EVENT_ETHER_PTPSI0                   = (0x29F), // ETHER_PTPSI0
    ELC_EVENT_ETHER_PTPSI1                   = (0x2A0), // ETHER_PTPSI1
    ELC_EVENT_ETHER_FWSI                     = (0x2A1), // ETHER_FWSI
    ELC_EVENT_ETHER_CAMI                     = (0x2A3), // ETHER_CAMI
    ELC_EVENT_ETHER_EASI0                    = (0x2A4), // ETHER_EASI0
    ELC_EVENT_ETHER_EASI1                    = (0x2A5), // ETHER_EASI1
    ELC_EVENT_ETHER_GWDI0                    = (0x2A6), // ETHER_GWDI0
    ELC_EVENT_ETHER_GWDI1                    = (0x2A7), // ETHER_GWDI1
    ELC_EVENT_ETHER_GWDI2                    = (0x2A8), // ETHER_GWDI2
    ELC_EVENT_ETHER_GWDI3                    = (0x2A9), // ETHER_GWDI3
    ELC_EVENT_ETHER_GWDI4                    = (0x2AA), // ETHER_GWDI4
    ELC_EVENT_ETHER_GWDI5                    = (0x2AB), // ETHER_GWDI5
    ELC_EVENT_ETHER_GWDI6                    = (0x2AC), // ETHER_GWDI6
    ELC_EVENT_ETHER_GWDI7                    = (0x2AD), // ETHER_GWDI7
    ELC_EVENT_ETHER_TSDI0                    = (0x2AE), // ETHER_TSDI0
    ELC_EVENT_ETHER_TSDI1                    = (0x2AF), // ETHER_TSDI1
    ELC_EVENT_ETHER_MDIO0                    = (0x2B0), // ETHER_MDIO0
    ELC_EVENT_ETHER_MDIO1                    = (0x2B1), // ETHER_MDIO1
    ELC_EVENT_ETHER_RMPI0                    = (0x2B2), // ETHER_RMPI0
    ELC_EVENT_ETHER_RMPI1                    = (0x2B3), // ETHER_RMPI1
    ELC_EVENT_GPTP_PTPOUT0                   = (0x2B4), // GPTP_PTPOUT0
    ELC_EVENT_GPTP_PTPOUT1                   = (0x2B5), // GPTP_PTPOUT1
    ELC_EVENT_GPTP_PTPOUT2                   = (0x2B6), // GPTP_PTPOUT2
    ELC_EVENT_GPTP_PTPOUT3                   = (0x2B7), // GPTP_PTPOUT3
    ELC_EVENT_GPTP_MATCH0                    = (0x2B8), // GPTP_MATCH0
    ELC_EVENT_GPTP_MATCH1                    = (0x2B9), // GPTP_MATCH1
    ELC_EVENT_USBHS_FIFO_0                   = (0x2C1), // USBHS_D0FIFO
    ELC_EVENT_USBHS_FIFO_1                   = (0x2C2), // USBHS_D1FIFO
    ELC_EVENT_USBHS_USB_INT_RESUME           = (0x2C3), // USBHS_USBIR
    ELC_EVENT_SCI0_RXI                       = (0x2C4), // SCI0_RXI
    ELC_EVENT_SCI0_TXI                       = (0x2C5), // SCI0_TXI
    ELC_EVENT_SCI0_TEI                       = (0x2C6), // SCI0_TEI
    ELC_EVENT_SCI0_ERI                       = (0x2C7), // SCI0_ERI
    ELC_EVENT_SCI0_AED                       = (0x2C8), // SCI0_AED
    ELC_EVENT_SCI0_BFD                       = (0x2C9), // SCI0_BFD
    ELC_EVENT_SCI0_AM                        = (0x2CA), // SCI0_AM
    ELC_EVENT_SCI1_RXI                       = (0x2CB), // SCI1_RXI
    ELC_EVENT_SCI1_TXI                       = (0x2CC), // SCI1_TXI
    ELC_EVENT_SCI1_TEI                       = (0x2CD), // SCI1_TEI
    ELC_EVENT_SCI1_ERI                       = (0x2CE), // SCI1_ERI
    ELC_EVENT_SCI1_AED                       = (0x2CF), // SCI1_AED
    ELC_EVENT_SCI1_BFD                       = (0x2D0), // SCI1_BFD
    ELC_EVENT_SCI1_AM                        = (0x2D1), // SCI1_AM
    ELC_EVENT_SCI2_RXI                       = (0x2D2), // SCI2_RXI
    ELC_EVENT_SCI2_TXI                       = (0x2D3), // SCI2_TXI
    ELC_EVENT_SCI2_TEI                       = (0x2D4), // SCI2_TEI
    ELC_EVENT_SCI2_ERI                       = (0x2D5), // SCI2_ERI
    ELC_EVENT_SCI2_AED                       = (0x2D6), // SCI2_AED
    ELC_EVENT_SCI2_BFD                       = (0x2D7), // SCI2_BFD
    ELC_EVENT_SCI2_AM                        = (0x2D8), // SCI2_AM
    ELC_EVENT_SCI3_RXI                       = (0x2D9), // SCI3_RXI
    ELC_EVENT_SCI3_TXI                       = (0x2DA), // SCI3_TXI
    ELC_EVENT_SCI3_TEI                       = (0x2DB), // SCI3_TEI
    ELC_EVENT_SCI3_ERI                       = (0x2DC), // SCI3_ERI
    ELC_EVENT_SCI3_AED                       = (0x2DD), // SCI3_AED
    ELC_EVENT_SCI3_BFD                       = (0x2DE), // SCI3_BFD
    ELC_EVENT_SCI3_AM                        = (0x2DF), // SCI3_AM
    ELC_EVENT_SCI4_RXI                       = (0x2E0), // SCI4_RXI
    ELC_EVENT_SCI4_TXI                       = (0x2E1), // SCI4_TXI
    ELC_EVENT_SCI4_TEI                       = (0x2E2), // SCI4_TEI
    ELC_EVENT_SCI4_ERI                       = (0x2E3), // SCI4_ERI
    ELC_EVENT_SCI4_AED                       = (0x2E4), // SCI4_AED
    ELC_EVENT_SCI4_BFD                       = (0x2E5), // SCI4_BFD
    ELC_EVENT_SCI4_AM                        = (0x2E6), // SCI4_AM
    ELC_EVENT_SCI5_RXI                       = (0x2E7), // SCI5_RXI
    ELC_EVENT_SCI5_TXI                       = (0x2E8), // SCI5_TXI
    ELC_EVENT_SCI5_TEI                       = (0x2E9), // SCI5_TEI
    ELC_EVENT_SCI5_ERI                       = (0x2EA), // SCI5_ERI
    ELC_EVENT_SCI5_AED                       = (0x2EB), // SCI5_AED
    ELC_EVENT_SCI5_BFD                       = (0x2EC), // SCI5_BFD
    ELC_EVENT_SCI5_AM                        = (0x2ED), // SCI5_AM
    ELC_EVENT_SCI6_RXI                       = (0x2EE), // SCI6_RXI
    ELC_EVENT_SCI6_TXI                       = (0x2EF), // SCI6_TXI
    ELC_EVENT_SCI6_TEI                       = (0x2F0), // SCI6_TEI
    ELC_EVENT_SCI6_ERI                       = (0x2F1), // SCI6_ERI
    ELC_EVENT_SCI6_AED                       = (0x2F2), // SCI6_AED
    ELC_EVENT_SCI6_BFD                       = (0x2F3), // SCI6_BFD
    ELC_EVENT_SCI6_AM                        = (0x2F4), // SCI6_AM
    ELC_EVENT_SCI7_RXI                       = (0x2F5), // SCI7_RXI
    ELC_EVENT_SCI7_TXI                       = (0x2F6), // SCI7_TXI
    ELC_EVENT_SCI7_TEI                       = (0x2F7), // SCI7_TEI
    ELC_EVENT_SCI7_ERI                       = (0x2F8), // SCI7_ERI
    ELC_EVENT_SCI7_AED                       = (0x2F9), // SCI7_AED
    ELC_EVENT_SCI7_BFD                       = (0x2FA), // SCI7_BFD
    ELC_EVENT_SCI7_AM                        = (0x2FB), // SCI7_AM
    ELC_EVENT_SCI8_RXI                       = (0x2FC), // SCI8_RXI
    ELC_EVENT_SCI8_TXI                       = (0x2FD), // SCI8_TXI
    ELC_EVENT_SCI8_TEI                       = (0x2FE), // SCI8_TEI
    ELC_EVENT_SCI8_ERI                       = (0x2FF), // SCI8_ERI
    ELC_EVENT_SCI8_AED                       = (0x300), // SCI8_AED
    ELC_EVENT_SCI8_BFD                       = (0x301), // SCI8_BFD
    ELC_EVENT_SCI8_AM                        = (0x302), // SCI8_AM
    ELC_EVENT_SCI9_RXI                       = (0x303), // SCI9_RXI
    ELC_EVENT_SCI9_TXI                       = (0x304), // SCI9_TXI
    ELC_EVENT_SCI9_TEI                       = (0x305), // SCI9_TEI
    ELC_EVENT_SCI9_ERI                       = (0x306), // SCI9_ERI
    ELC_EVENT_SCI9_AED                       = (0x307), // SCI9_AED
    ELC_EVENT_SCI9_BFD                       = (0x308), // SCI9_BFD
    ELC_EVENT_SCI9_AM                        = (0x309), // SCI9_AM
    ELC_EVENT_SCI10_RXI                      = (0x30A), // SCI10_RXI
    ELC_EVENT_SCI10_TXI                      = (0x30B), // SCI10_TXI
    ELC_EVENT_SCI10_TEI                      = (0x30C), // SCI10_TEI
    ELC_EVENT_SCI10_ERI                      = (0x30D), // SCI10_ERI
    ELC_EVENT_SCI10_AED                      = (0x30E), // SCI10_AED
    ELC_EVENT_SCI10_BFD                      = (0x30F), // SCI10_BFD
    ELC_EVENT_SCI10_AM                       = (0x310), // SCI10_AM
    ELC_EVENT_SCI11_RXI                      = (0x311), // SCI11_RXI
    ELC_EVENT_SCI11_TXI                      = (0x312), // SCI11_TXI
    ELC_EVENT_SCI11_TEI                      = (0x313), // SCI11_TEI
    ELC_EVENT_SCI11_ERI                      = (0x314), // SCI11_ERI
    ELC_EVENT_SCI11_AED                      = (0x315), // SCI11_AED
    ELC_EVENT_SCI11_BFD                      = (0x316), // SCI11_BFD
    ELC_EVENT_SCI11_AM                       = (0x317), // SCI11_AM
    ELC_EVENT_SPI0_RXI                       = (0x318), // SPI0_SPRI
    ELC_EVENT_SPI0_TXI                       = (0x319), // SPI0_SPTI
    ELC_EVENT_SPI0_IDLE                      = (0x31A), // SPI0_SPII
    ELC_EVENT_SPI0_ERI                       = (0x31B), // SPI0_SPEI
    ELC_EVENT_SPI0_TEI                       = (0x31C), // SPI0_SPCEND
    ELC_EVENT_SPI1_RXI                       = (0x31D), // SPI1_SPRI
    ELC_EVENT_SPI1_TXI                       = (0x31E), // SPI1_SPTI
    ELC_EVENT_SPI1_IDLE                      = (0x31F), // SPI1_SPII
    ELC_EVENT_SPI1_ERI                       = (0x320), // SPI1_SPEI
    ELC_EVENT_SPI1_TEI                       = (0x321), // SPI1_SPCEND
    ELC_EVENT_CAN_RXF                        = (0x322), // CAN_RXF
    ELC_EVENT_CAN_GLERR                      = (0x323), // CAN_GLERR
    ELC_EVENT_CAN0_DMAREQ0                   = (0x324), // CAN0_RF_DMAREQ0
    ELC_EVENT_CAN0_DMAREQ1                   = (0x325), // CAN0_RF_DMAREQ1
    ELC_EVENT_CAN1_DMAREQ0                   = (0x328), // CAN1_RF_DMAREQ0
    ELC_EVENT_CAN1_DMAREQ1                   = (0x329), // CAN1_RF_DMAREQ1
    ELC_EVENT_CAN0_TX                        = (0x32C), // CAN0_TX
    ELC_EVENT_CAN0_CHERR                     = (0x32D), // CAN0_CHERR
    ELC_EVENT_CAN0_COMFRX                    = (0x32E), // CAN0_COMFRX
    ELC_EVENT_CAN0_CF_DMAREQ                 = (0x32F), // CAN0_CF_DMAREQ
    ELC_EVENT_CAN0_RXMB                      = (0x330), // CAN0_RXMB
    ELC_EVENT_CAN1_TX                        = (0x331), // CAN1_TX
    ELC_EVENT_CAN1_CHERR                     = (0x332), // CAN1_CHERR
    ELC_EVENT_CAN1_COMFRX                    = (0x333), // CAN1_COMFRX
    ELC_EVENT_CAN1_CF_DMAREQ                 = (0x334), // CAN1_CF_DMAREQ
    ELC_EVENT_CAN1_RXMB                      = (0x335), // CAN1_RXMB
    ELC_EVENT_CAN0_MRAM_ERI                  = (0x338), // CAN0_MRAM_ERI
    ELC_EVENT_CAN1_MRAM_ERI                  = (0x339), // CAN1_MRAM_ERI
    ELC_EVENT_I3C0_RESPONSE                  = (0x33A), // I3C_RESP
    ELC_EVENT_I3C0_COMMAND                   = (0x33B), // I3C_CMD
    ELC_EVENT_I3C0_IBI                       = (0x33C), // I3C_IBI
    ELC_EVENT_I3C0_RX                        = (0x33D), // I3C_RX
    ELC_EVENT_I3C0_TX                        = (0x33E), // I3C_TX
    ELC_EVENT_I3C0_RCV_STATUS                = (0x33F), // I3C_RCV
    ELC_EVENT_I3C0_HRESP                     = (0x340), // I3C_HRESP
    ELC_EVENT_I3C0_HCMD                      = (0x341), // I3C_HCMD
    ELC_EVENT_I3C0_HRX                       = (0x342), // I3C_HRX
    ELC_EVENT_I3C0_HTX                       = (0x343), // I3C_HTX
    ELC_EVENT_I3C0_TEND                      = (0x344), // I3C_TEND
    ELC_EVENT_I3C0_EEI                       = (0x345), // I3C_EEI
    ELC_EVENT_I3C0_STEV                      = (0x346), // I3C_STEV
    ELC_EVENT_I3C0_MREFOVF                   = (0x347), // I3C_MREFOVF
    ELC_EVENT_I3C0_MREFCPT                   = (0x348), // I3C_MREFCPT
    ELC_EVENT_I3C0_AMEV                      = (0x349), // I3C_AMEV
    ELC_EVENT_I3C0_WU                        = (0x34A), // I3C_WU
    ELC_EVENT_ADC_LIMCLPI                    = (0x34B), // ADC_LIMCLPI
    ELC_EVENT_ADC_FIFOOVF                    = (0x34C), // ADC_FIFOOVF
    ELC_EVENT_ADC_ADI0                       = (0x34D), // ADC_ADI0
    ELC_EVENT_ADC_ADI1                       = (0x34E), // ADC_ADI1
    ELC_EVENT_ADC_ADI2                       = (0x34F), // ADC_ADI2
    ELC_EVENT_ADC_ADI3                       = (0x350), // ADC_ADI3
    ELC_EVENT_ADC_ADI4                       = (0x351), // ADC_ADI4
    ELC_EVENT_ADC_ADI5                       = (0x352), // ADC_ADI5
    ELC_EVENT_ADC_ADI6                       = (0x353), // ADC_ADI6
    ELC_EVENT_ADC_ADI7                       = (0x354), // ADC_ADI7
    ELC_EVENT_ADC_ADI8                       = (0x355), // ADC_ADI8
    ELC_EVENT_ADC_FIFOREQ0                   = (0x356), // ADC_FIFOREQ0
    ELC_EVENT_ADC_FIFOREQ1                   = (0x357), // ADC_FIFOREQ1
    ELC_EVENT_ADC_FIFOREQ2                   = (0x358), // ADC_FIFOREQ2
    ELC_EVENT_ADC_FIFOREQ3                   = (0x359), // ADC_FIFOREQ3
    ELC_EVENT_ADC_FIFOREQ4                   = (0x35A), // ADC_FIFOREQ4
    ELC_EVENT_ADC_FIFOREQ5                   = (0x35B), // ADC_FIFOREQ5
    ELC_EVENT_ADC_FIFOREQ6                   = (0x35C), // ADC_FIFOREQ6
    ELC_EVENT_ADC_FIFOREQ7                   = (0x35D), // ADC_FIFOREQ7
    ELC_EVENT_ADC_FIFOREQ8                   = (0x35E), // ADC_FIFOREQ8
    ELC_EVENT_ADC_CMPI0                      = (0x35F), // ADC_CMPI0
    ELC_EVENT_ADC_CMPI1                      = (0x360), // ADC_CMPI1
    ELC_EVENT_ADC_CCMPM0                     = (0x361), // ADC_CCMPM0
    ELC_EVENT_ADC_CCMPUM0                    = (0x362), // ADC_CCMPUM0
    ELC_EVENT_ADC_ERR0                       = (0x363), // ADC_ERR0
    ELC_EVENT_ADC_RESOVF0                    = (0x364), // ADC_RESOVF0
    ELC_EVENT_ADC_CALEND0                    = (0x366), // ADC_CALEND0
    ELC_EVENT_ADC_CMPI2                      = (0x367), // ADC_CMPI2
    ELC_EVENT_ADC_CMPI3                      = (0x368), // ADC_CMPI3
    ELC_EVENT_ADC_CCMPM1                     = (0x369), // ADC_CCMPM1
    ELC_EVENT_ADC_CCMPUM1                    = (0x36A), // ADC_CCMPUM1
    ELC_EVENT_ADC_ERR1                       = (0x36B), // ADC_ERR1
    ELC_EVENT_ADC_RESOVF1                    = (0x36C), // ADC_RESOVF1
    ELC_EVENT_ADC_CALEND1                    = (0x36E), // ADC_CALEND1
    ELC_EVENT_DOC_INT                        = (0x36F), // DOC_DOPCI
    ELC_EVENT_RSIP_TADI                      = (0x371), // RSIP_TADI
    ELC_EVENT_GLCDC_LINE_DETECT              = (0x382), // GLCDC_VPOS
    ELC_EVENT_GLCDC_UNDERFLOW_1              = (0x383), // GLCDC_L1UNDF
    ELC_EVENT_GLCDC_UNDERFLOW_2              = (0x384), // GLCDC_L2UNDF
    ELC_EVENT_DRW_INT                        = (0x385), // DRW_IRQ
    ELC_EVENT_MIPIDSI_SEQ0                   = (0x388), // DSI_SEQ0
    ELC_EVENT_MIPIDSI_SEQ1                   = (0x389), // DSI_SEQ1
    ELC_EVENT_MIPIDSI_VIN1                   = (0x38A), // DSI_VIN1
    ELC_EVENT_MIPIDSI_RCV                    = (0x38B), // DSI_RCV
    ELC_EVENT_MIPIDSI_FERR                   = (0x38C), // DSI_FERR
    ELC_EVENT_MIPIDSI_PPI                    = (0x38D), // DSI_PPI
    ELC_EVENT_CSI_RX                         = (0x38F), // CSI_RX
    ELC_EVENT_CSI_DL                         = (0x390), // CSI_DL
    ELC_EVENT_CSI_VC                         = (0x391), // CSI_VC
    ELC_EVENT_CSI_PM                         = (0x392), // CSI_PM
    ELC_EVENT_CSI_GST                        = (0x393), // CSI_GST
    ELC_EVENT_CSI_DBG                        = (0x394), // CSI_DBG
    ELC_EVENT_VIN_IRQ                        = (0x395), // VIN_IRQ
    ELC_EVENT_VIN_ERR                        = (0x396), // VIN_ERR
    ELC_EVENT_CEU_CEUI                       = (0x397), // CEU_CEUI
} elc_event_t;

/* Alternate manual and FSP spellings refer to the same physical event. */
#define ELC_EVENT_ACMP_HS0                         ELC_EVENT_ACMPHS0_INT
#define ELC_EVENT_ACMP_HS1                         ELC_EVENT_ACMPHS1_INT
#define ELC_EVENT_ACMP_HS2                         ELC_EVENT_ACMPHS2_INT
#define ELC_EVENT_ACMP_HS3                         ELC_EVENT_ACMPHS3_INT
#define ELC_EVENT_AGT0_AGTCMAI                     ELC_EVENT_AGT0_COMPARE_A
#define ELC_EVENT_AGT0_AGTCMBI                     ELC_EVENT_AGT0_COMPARE_B
#define ELC_EVENT_AGT0_AGTI                        ELC_EVENT_AGT0_INT
#define ELC_EVENT_AGT1_AGTCMAI                     ELC_EVENT_AGT1_COMPARE_A
#define ELC_EVENT_AGT1_AGTCMBI                     ELC_EVENT_AGT1_COMPARE_B
#define ELC_EVENT_AGT1_AGTI                        ELC_EVENT_AGT1_INT
#define ELC_EVENT_CAC_FEERI                        ELC_EVENT_CAC_FREQUENCY_ERROR
#define ELC_EVENT_CAC_MENDI                        ELC_EVENT_CAC_MEASUREMENT_END
#define ELC_EVENT_CAC_OVFI                         ELC_EVENT_CAC_OVERFLOW
#define ELC_EVENT_CAN0_RF_DMAREQ0                  ELC_EVENT_CAN0_DMAREQ0
#define ELC_EVENT_CAN0_RF_DMAREQ1                  ELC_EVENT_CAN0_DMAREQ1
#define ELC_EVENT_CAN1_RF_DMAREQ0                  ELC_EVENT_CAN1_DMAREQ0
#define ELC_EVENT_CAN1_RF_DMAREQ1                  ELC_EVENT_CAN1_DMAREQ1
#define ELC_EVENT_DMA0_TRANSERR                    ELC_EVENT_DMA_TRANSERR
#define ELC_EVENT_DMAC00_INT                       ELC_EVENT_DMAC0_INT
#define ELC_EVENT_DMAC01_INT                       ELC_EVENT_DMAC1_INT
#define ELC_EVENT_DMAC02_INT                       ELC_EVENT_DMAC2_INT
#define ELC_EVENT_DMAC03_INT                       ELC_EVENT_DMAC3_INT
#define ELC_EVENT_DMAC04_INT                       ELC_EVENT_DMAC4_INT
#define ELC_EVENT_DMAC05_INT                       ELC_EVENT_DMAC5_INT
#define ELC_EVENT_DMAC06_INT                       ELC_EVENT_DMAC6_INT
#define ELC_EVENT_DMAC07_INT                       ELC_EVENT_DMAC7_INT
#define ELC_EVENT_DMAC16_INT                       ELC_EVENT_DMAC14_INT
#define ELC_EVENT_DMAC17_INT                       ELC_EVENT_DMAC15_INT
#define ELC_EVENT_DOC_DOPCI                        ELC_EVENT_DOC_INT
#define ELC_EVENT_DRW_IRQ                          ELC_EVENT_DRW_INT
#define ELC_EVENT_DSI_FERR                         ELC_EVENT_MIPIDSI_FERR
#define ELC_EVENT_DSI_PPI                          ELC_EVENT_MIPIDSI_PPI
#define ELC_EVENT_DSI_RCV                          ELC_EVENT_MIPIDSI_RCV
#define ELC_EVENT_DSI_SEQ0                         ELC_EVENT_MIPIDSI_SEQ0
#define ELC_EVENT_DSI_SEQ1                         ELC_EVENT_MIPIDSI_SEQ1
#define ELC_EVENT_DSI_VIN1                         ELC_EVENT_MIPIDSI_VIN1
#define ELC_EVENT_ELC_SWEVT0                       ELC_EVENT_ELC_SOFTWARE_EVENT_0
#define ELC_EVENT_ELC_SWEVT1                       ELC_EVENT_ELC_SOFTWARE_EVENT_1
#define ELC_EVENT_ELC_SWEVT2                       ELC_EVENT_ELC_SOFTWARE_EVENT_2
#define ELC_EVENT_ELC_SWEVT3                       ELC_EVENT_ELC_SOFTWARE_EVENT_3
#define ELC_EVENT_GLCDC_L1UNDF                     ELC_EVENT_GLCDC_UNDERFLOW_1
#define ELC_EVENT_GLCDC_L2UNDF                     ELC_EVENT_GLCDC_UNDERFLOW_2
#define ELC_EVENT_GLCDC_VPOS                       ELC_EVENT_GLCDC_LINE_DETECT
#define ELC_EVENT_GPT0_CCMPA                       ELC_EVENT_GPT0_CAPTURE_COMPARE_A
#define ELC_EVENT_GPT0_CCMPB                       ELC_EVENT_GPT0_CAPTURE_COMPARE_B
#define ELC_EVENT_GPT0_CMPC                        ELC_EVENT_GPT0_COMPARE_C
#define ELC_EVENT_GPT0_CMPD                        ELC_EVENT_GPT0_COMPARE_D
#define ELC_EVENT_GPT0_CMPE                        ELC_EVENT_GPT0_COMPARE_E
#define ELC_EVENT_GPT0_CMPF                        ELC_EVENT_GPT0_COMPARE_F
#define ELC_EVENT_GPT0_OVF                         ELC_EVENT_GPT0_COUNTER_OVERFLOW
#define ELC_EVENT_GPT0_UDF                         ELC_EVENT_GPT0_COUNTER_UNDERFLOW
#define ELC_EVENT_GPT10_CCMPA                      ELC_EVENT_GPT10_CAPTURE_COMPARE_A
#define ELC_EVENT_GPT10_CCMPB                      ELC_EVENT_GPT10_CAPTURE_COMPARE_B
#define ELC_EVENT_GPT10_CMPC                       ELC_EVENT_GPT10_COMPARE_C
#define ELC_EVENT_GPT10_CMPD                       ELC_EVENT_GPT10_COMPARE_D
#define ELC_EVENT_GPT10_CMPE                       ELC_EVENT_GPT10_COMPARE_E
#define ELC_EVENT_GPT10_CMPF                       ELC_EVENT_GPT10_COMPARE_F
#define ELC_EVENT_GPT10_OVF                        ELC_EVENT_GPT10_COUNTER_OVERFLOW
#define ELC_EVENT_GPT10_UDF                        ELC_EVENT_GPT10_COUNTER_UNDERFLOW
#define ELC_EVENT_GPT11_CCMPA                      ELC_EVENT_GPT11_CAPTURE_COMPARE_A
#define ELC_EVENT_GPT11_CCMPB                      ELC_EVENT_GPT11_CAPTURE_COMPARE_B
#define ELC_EVENT_GPT11_CMPC                       ELC_EVENT_GPT11_COMPARE_C
#define ELC_EVENT_GPT11_CMPD                       ELC_EVENT_GPT11_COMPARE_D
#define ELC_EVENT_GPT11_CMPE                       ELC_EVENT_GPT11_COMPARE_E
#define ELC_EVENT_GPT11_CMPF                       ELC_EVENT_GPT11_COMPARE_F
#define ELC_EVENT_GPT11_OVF                        ELC_EVENT_GPT11_COUNTER_OVERFLOW
#define ELC_EVENT_GPT11_UDF                        ELC_EVENT_GPT11_COUNTER_UNDERFLOW
#define ELC_EVENT_GPT12_CCMPA                      ELC_EVENT_GPT12_CAPTURE_COMPARE_A
#define ELC_EVENT_GPT12_CCMPB                      ELC_EVENT_GPT12_CAPTURE_COMPARE_B
#define ELC_EVENT_GPT12_CMPC                       ELC_EVENT_GPT12_COMPARE_C
#define ELC_EVENT_GPT12_CMPD                       ELC_EVENT_GPT12_COMPARE_D
#define ELC_EVENT_GPT12_CMPE                       ELC_EVENT_GPT12_COMPARE_E
#define ELC_EVENT_GPT12_CMPF                       ELC_EVENT_GPT12_COMPARE_F
#define ELC_EVENT_GPT12_OVF                        ELC_EVENT_GPT12_COUNTER_OVERFLOW
#define ELC_EVENT_GPT12_UDF                        ELC_EVENT_GPT12_COUNTER_UNDERFLOW
#define ELC_EVENT_GPT13_CCMPA                      ELC_EVENT_GPT13_CAPTURE_COMPARE_A
#define ELC_EVENT_GPT13_CCMPB                      ELC_EVENT_GPT13_CAPTURE_COMPARE_B
#define ELC_EVENT_GPT13_CMPC                       ELC_EVENT_GPT13_COMPARE_C
#define ELC_EVENT_GPT13_CMPD                       ELC_EVENT_GPT13_COMPARE_D
#define ELC_EVENT_GPT13_CMPE                       ELC_EVENT_GPT13_COMPARE_E
#define ELC_EVENT_GPT13_CMPF                       ELC_EVENT_GPT13_COMPARE_F
#define ELC_EVENT_GPT13_OVF                        ELC_EVENT_GPT13_COUNTER_OVERFLOW
#define ELC_EVENT_GPT13_UDF                        ELC_EVENT_GPT13_COUNTER_UNDERFLOW
#define ELC_EVENT_GPT1_CCMPA                       ELC_EVENT_GPT1_CAPTURE_COMPARE_A
#define ELC_EVENT_GPT1_CCMPB                       ELC_EVENT_GPT1_CAPTURE_COMPARE_B
#define ELC_EVENT_GPT1_CMPC                        ELC_EVENT_GPT1_COMPARE_C
#define ELC_EVENT_GPT1_CMPD                        ELC_EVENT_GPT1_COMPARE_D
#define ELC_EVENT_GPT1_CMPE                        ELC_EVENT_GPT1_COMPARE_E
#define ELC_EVENT_GPT1_CMPF                        ELC_EVENT_GPT1_COMPARE_F
#define ELC_EVENT_GPT1_OVF                         ELC_EVENT_GPT1_COUNTER_OVERFLOW
#define ELC_EVENT_GPT1_UDF                         ELC_EVENT_GPT1_COUNTER_UNDERFLOW
#define ELC_EVENT_GPT2_CCMPA                       ELC_EVENT_GPT2_CAPTURE_COMPARE_A
#define ELC_EVENT_GPT2_CCMPB                       ELC_EVENT_GPT2_CAPTURE_COMPARE_B
#define ELC_EVENT_GPT2_CMPC                        ELC_EVENT_GPT2_COMPARE_C
#define ELC_EVENT_GPT2_CMPD                        ELC_EVENT_GPT2_COMPARE_D
#define ELC_EVENT_GPT2_CMPE                        ELC_EVENT_GPT2_COMPARE_E
#define ELC_EVENT_GPT2_CMPF                        ELC_EVENT_GPT2_COMPARE_F
#define ELC_EVENT_GPT2_OVF                         ELC_EVENT_GPT2_COUNTER_OVERFLOW
#define ELC_EVENT_GPT2_UDF                         ELC_EVENT_GPT2_COUNTER_UNDERFLOW
#define ELC_EVENT_GPT3_CCMPA                       ELC_EVENT_GPT3_CAPTURE_COMPARE_A
#define ELC_EVENT_GPT3_CCMPB                       ELC_EVENT_GPT3_CAPTURE_COMPARE_B
#define ELC_EVENT_GPT3_CMPC                        ELC_EVENT_GPT3_COMPARE_C
#define ELC_EVENT_GPT3_CMPD                        ELC_EVENT_GPT3_COMPARE_D
#define ELC_EVENT_GPT3_CMPE                        ELC_EVENT_GPT3_COMPARE_E
#define ELC_EVENT_GPT3_CMPF                        ELC_EVENT_GPT3_COMPARE_F
#define ELC_EVENT_GPT3_OVF                         ELC_EVENT_GPT3_COUNTER_OVERFLOW
#define ELC_EVENT_GPT3_UDF                         ELC_EVENT_GPT3_COUNTER_UNDERFLOW
#define ELC_EVENT_GPT4_CCMPA                       ELC_EVENT_GPT4_CAPTURE_COMPARE_A
#define ELC_EVENT_GPT4_CCMPB                       ELC_EVENT_GPT4_CAPTURE_COMPARE_B
#define ELC_EVENT_GPT4_CMPC                        ELC_EVENT_GPT4_COMPARE_C
#define ELC_EVENT_GPT4_CMPD                        ELC_EVENT_GPT4_COMPARE_D
#define ELC_EVENT_GPT4_CMPE                        ELC_EVENT_GPT4_COMPARE_E
#define ELC_EVENT_GPT4_CMPF                        ELC_EVENT_GPT4_COMPARE_F
#define ELC_EVENT_GPT4_OVF                         ELC_EVENT_GPT4_COUNTER_OVERFLOW
#define ELC_EVENT_GPT4_UDF                         ELC_EVENT_GPT4_COUNTER_UNDERFLOW
#define ELC_EVENT_GPT5_CCMPA                       ELC_EVENT_GPT5_CAPTURE_COMPARE_A
#define ELC_EVENT_GPT5_CCMPB                       ELC_EVENT_GPT5_CAPTURE_COMPARE_B
#define ELC_EVENT_GPT5_CMPC                        ELC_EVENT_GPT5_COMPARE_C
#define ELC_EVENT_GPT5_CMPD                        ELC_EVENT_GPT5_COMPARE_D
#define ELC_EVENT_GPT5_CMPE                        ELC_EVENT_GPT5_COMPARE_E
#define ELC_EVENT_GPT5_CMPF                        ELC_EVENT_GPT5_COMPARE_F
#define ELC_EVENT_GPT5_OVF                         ELC_EVENT_GPT5_COUNTER_OVERFLOW
#define ELC_EVENT_GPT5_UDF                         ELC_EVENT_GPT5_COUNTER_UNDERFLOW
#define ELC_EVENT_GPT6_CCMPA                       ELC_EVENT_GPT6_CAPTURE_COMPARE_A
#define ELC_EVENT_GPT6_CCMPB                       ELC_EVENT_GPT6_CAPTURE_COMPARE_B
#define ELC_EVENT_GPT6_CMPC                        ELC_EVENT_GPT6_COMPARE_C
#define ELC_EVENT_GPT6_CMPD                        ELC_EVENT_GPT6_COMPARE_D
#define ELC_EVENT_GPT6_CMPE                        ELC_EVENT_GPT6_COMPARE_E
#define ELC_EVENT_GPT6_CMPF                        ELC_EVENT_GPT6_COMPARE_F
#define ELC_EVENT_GPT6_OVF                         ELC_EVENT_GPT6_COUNTER_OVERFLOW
#define ELC_EVENT_GPT6_UDF                         ELC_EVENT_GPT6_COUNTER_UNDERFLOW
#define ELC_EVENT_GPT7_CCMPA                       ELC_EVENT_GPT7_CAPTURE_COMPARE_A
#define ELC_EVENT_GPT7_CCMPB                       ELC_EVENT_GPT7_CAPTURE_COMPARE_B
#define ELC_EVENT_GPT7_CMPC                        ELC_EVENT_GPT7_COMPARE_C
#define ELC_EVENT_GPT7_CMPD                        ELC_EVENT_GPT7_COMPARE_D
#define ELC_EVENT_GPT7_CMPE                        ELC_EVENT_GPT7_COMPARE_E
#define ELC_EVENT_GPT7_CMPF                        ELC_EVENT_GPT7_COMPARE_F
#define ELC_EVENT_GPT7_OVF                         ELC_EVENT_GPT7_COUNTER_OVERFLOW
#define ELC_EVENT_GPT7_UDF                         ELC_EVENT_GPT7_COUNTER_UNDERFLOW
#define ELC_EVENT_GPT8_CCMPA                       ELC_EVENT_GPT8_CAPTURE_COMPARE_A
#define ELC_EVENT_GPT8_CCMPB                       ELC_EVENT_GPT8_CAPTURE_COMPARE_B
#define ELC_EVENT_GPT8_CMPC                        ELC_EVENT_GPT8_COMPARE_C
#define ELC_EVENT_GPT8_CMPD                        ELC_EVENT_GPT8_COMPARE_D
#define ELC_EVENT_GPT8_CMPE                        ELC_EVENT_GPT8_COMPARE_E
#define ELC_EVENT_GPT8_CMPF                        ELC_EVENT_GPT8_COMPARE_F
#define ELC_EVENT_GPT8_OVF                         ELC_EVENT_GPT8_COUNTER_OVERFLOW
#define ELC_EVENT_GPT8_UDF                         ELC_EVENT_GPT8_COUNTER_UNDERFLOW
#define ELC_EVENT_GPT9_CCMPA                       ELC_EVENT_GPT9_CAPTURE_COMPARE_A
#define ELC_EVENT_GPT9_CCMPB                       ELC_EVENT_GPT9_CAPTURE_COMPARE_B
#define ELC_EVENT_GPT9_CMPC                        ELC_EVENT_GPT9_COMPARE_C
#define ELC_EVENT_GPT9_CMPD                        ELC_EVENT_GPT9_COMPARE_D
#define ELC_EVENT_GPT9_CMPE                        ELC_EVENT_GPT9_COMPARE_E
#define ELC_EVENT_GPT9_CMPF                        ELC_EVENT_GPT9_COMPARE_F
#define ELC_EVENT_GPT9_OVF                         ELC_EVENT_GPT9_COUNTER_OVERFLOW
#define ELC_EVENT_GPT9_UDF                         ELC_EVENT_GPT9_COUNTER_UNDERFLOW
#define ELC_EVENT_GPT_UVWEDGE                      ELC_EVENT_OPS_UVW_EDGE
#define ELC_EVENT_I3C_AMEV                         ELC_EVENT_I3C0_AMEV
#define ELC_EVENT_I3C_CMD                          ELC_EVENT_I3C0_COMMAND
#define ELC_EVENT_I3C_EEI                          ELC_EVENT_I3C0_EEI
#define ELC_EVENT_I3C_HCMD                         ELC_EVENT_I3C0_HCMD
#define ELC_EVENT_I3C_HRESP                        ELC_EVENT_I3C0_HRESP
#define ELC_EVENT_I3C_HRX                          ELC_EVENT_I3C0_HRX
#define ELC_EVENT_I3C_HTX                          ELC_EVENT_I3C0_HTX
#define ELC_EVENT_I3C_IBI                          ELC_EVENT_I3C0_IBI
#define ELC_EVENT_I3C_MREFCPT                      ELC_EVENT_I3C0_MREFCPT
#define ELC_EVENT_I3C_MREFOVF                      ELC_EVENT_I3C0_MREFOVF
#define ELC_EVENT_I3C_RCV                          ELC_EVENT_I3C0_RCV_STATUS
#define ELC_EVENT_I3C_RESP                         ELC_EVENT_I3C0_RESPONSE
#define ELC_EVENT_I3C_RX                           ELC_EVENT_I3C0_RX
#define ELC_EVENT_I3C_STEV                         ELC_EVENT_I3C0_STEV
#define ELC_EVENT_I3C_TEND                         ELC_EVENT_I3C0_TEND
#define ELC_EVENT_I3C_TX                           ELC_EVENT_I3C0_TX
#define ELC_EVENT_I3C_WU                           ELC_EVENT_I3C0_WU
#define ELC_EVENT_IIC0_EEI                         ELC_EVENT_IIC0_ERI
#define ELC_EVENT_IIC1_EEI                         ELC_EVENT_IIC1_ERI
#define ELC_EVENT_IIC2_EEI                         ELC_EVENT_IIC2_ERI
#define ELC_EVENT_IOPORT_GROUP1                    ELC_EVENT_IOPORT_EVENT_1
#define ELC_EVENT_IOPORT_GROUP2                    ELC_EVENT_IOPORT_EVENT_2
#define ELC_EVENT_IOPORT_GROUP3                    ELC_EVENT_IOPORT_EVENT_3
#define ELC_EVENT_IOPORT_GROUP4                    ELC_EVENT_IOPORT_EVENT_4
#define ELC_EVENT_IWDT_NMIUNDF                     ELC_EVENT_IWDT_UNDERFLOW
#define ELC_EVENT_MOSC_STOP                        ELC_EVENT_CGC_MOSC_STOP
#define ELC_EVENT_OSPI0_CMP                        ELC_EVENT_XSPI_CMP
#define ELC_EVENT_OSPI0_ERR                        ELC_EVENT_XSPI_ERR
#define ELC_EVENT_POEG_GROUPA                      ELC_EVENT_POEG0_EVENT
#define ELC_EVENT_POEG_GROUPB                      ELC_EVENT_POEG1_EVENT
#define ELC_EVENT_POEG_GROUPC                      ELC_EVENT_POEG2_EVENT
#define ELC_EVENT_POEG_GROUPD                      ELC_EVENT_POEG3_EVENT
#define ELC_EVENT_PORT_IRQ0                        ELC_EVENT_ICU_IRQ0
#define ELC_EVENT_PORT_IRQ1                        ELC_EVENT_ICU_IRQ1
#define ELC_EVENT_PORT_IRQ10                       ELC_EVENT_ICU_IRQ10
#define ELC_EVENT_PORT_IRQ11                       ELC_EVENT_ICU_IRQ11
#define ELC_EVENT_PORT_IRQ12                       ELC_EVENT_ICU_IRQ12
#define ELC_EVENT_PORT_IRQ13                       ELC_EVENT_ICU_IRQ13
#define ELC_EVENT_PORT_IRQ14                       ELC_EVENT_ICU_IRQ14
#define ELC_EVENT_PORT_IRQ15                       ELC_EVENT_ICU_IRQ15
#define ELC_EVENT_PORT_IRQ16                       ELC_EVENT_ICU_IRQ16
#define ELC_EVENT_PORT_IRQ17                       ELC_EVENT_ICU_IRQ17
#define ELC_EVENT_PORT_IRQ18                       ELC_EVENT_ICU_IRQ18
#define ELC_EVENT_PORT_IRQ19                       ELC_EVENT_ICU_IRQ19
#define ELC_EVENT_PORT_IRQ2                        ELC_EVENT_ICU_IRQ2
#define ELC_EVENT_PORT_IRQ20                       ELC_EVENT_ICU_IRQ20
#define ELC_EVENT_PORT_IRQ21                       ELC_EVENT_ICU_IRQ21
#define ELC_EVENT_PORT_IRQ22                       ELC_EVENT_ICU_IRQ22
#define ELC_EVENT_PORT_IRQ23                       ELC_EVENT_ICU_IRQ23
#define ELC_EVENT_PORT_IRQ24                       ELC_EVENT_ICU_IRQ24
#define ELC_EVENT_PORT_IRQ25                       ELC_EVENT_ICU_IRQ25
#define ELC_EVENT_PORT_IRQ26                       ELC_EVENT_ICU_IRQ26
#define ELC_EVENT_PORT_IRQ27                       ELC_EVENT_ICU_IRQ27
#define ELC_EVENT_PORT_IRQ28                       ELC_EVENT_ICU_IRQ28
#define ELC_EVENT_PORT_IRQ29                       ELC_EVENT_ICU_IRQ29
#define ELC_EVENT_PORT_IRQ3                        ELC_EVENT_ICU_IRQ3
#define ELC_EVENT_PORT_IRQ30                       ELC_EVENT_ICU_IRQ30
#define ELC_EVENT_PORT_IRQ31                       ELC_EVENT_ICU_IRQ31
#define ELC_EVENT_PORT_IRQ4                        ELC_EVENT_ICU_IRQ4
#define ELC_EVENT_PORT_IRQ5                        ELC_EVENT_ICU_IRQ5
#define ELC_EVENT_PORT_IRQ6                        ELC_EVENT_ICU_IRQ6
#define ELC_EVENT_PORT_IRQ7                        ELC_EVENT_ICU_IRQ7
#define ELC_EVENT_PORT_IRQ8                        ELC_EVENT_ICU_IRQ8
#define ELC_EVENT_PORT_IRQ9                        ELC_EVENT_ICU_IRQ9
#define ELC_EVENT_PVD_PVD1                         ELC_EVENT_LVD_LVD1
#define ELC_EVENT_PVD_PVD2                         ELC_EVENT_LVD_LVD2
#define ELC_EVENT_RTC_ALM                          ELC_EVENT_RTC_ALARM
#define ELC_EVENT_RTC_CUP                          ELC_EVENT_RTC_CARRY
#define ELC_EVENT_RTC_PRD                          ELC_EVENT_RTC_PERIOD
#define ELC_EVENT_SDHI_MMC0_ACCS                   ELC_EVENT_SDHIMMC0_ACCS
#define ELC_EVENT_SDHI_MMC0_CARD                   ELC_EVENT_SDHIMMC0_CARD
#define ELC_EVENT_SDHI_MMC0_ODMSDBREQ              ELC_EVENT_SDHIMMC0_DMA_REQ
#define ELC_EVENT_SDHI_MMC0_SDIO                   ELC_EVENT_SDHIMMC0_SDIO
#define ELC_EVENT_SDHI_MMC1_ACCS                   ELC_EVENT_SDHIMMC1_ACCS
#define ELC_EVENT_SDHI_MMC1_CARD                   ELC_EVENT_SDHIMMC1_CARD
#define ELC_EVENT_SDHI_MMC1_ODMSDBREQ              ELC_EVENT_SDHIMMC1_DMA_REQ
#define ELC_EVENT_SDHI_MMC1_SDIO                   ELC_EVENT_SDHIMMC1_SDIO
#define ELC_EVENT_SOSC_STOP                        ELC_EVENT_CGC_SOSC_STOP
#define ELC_EVENT_SPI0_SPCEND                      ELC_EVENT_SPI0_TEI
#define ELC_EVENT_SPI0_SPEI                        ELC_EVENT_SPI0_ERI
#define ELC_EVENT_SPI0_SPII                        ELC_EVENT_SPI0_IDLE
#define ELC_EVENT_SPI0_SPRI                        ELC_EVENT_SPI0_RXI
#define ELC_EVENT_SPI0_SPTI                        ELC_EVENT_SPI0_TXI
#define ELC_EVENT_SPI1_SPCEND                      ELC_EVENT_SPI1_TEI
#define ELC_EVENT_SPI1_SPEI                        ELC_EVENT_SPI1_ERI
#define ELC_EVENT_SPI1_SPII                        ELC_EVENT_SPI1_IDLE
#define ELC_EVENT_SPI1_SPRI                        ELC_EVENT_SPI1_RXI
#define ELC_EVENT_SPI1_SPTI                        ELC_EVENT_SPI1_TXI
#define ELC_EVENT_SSI0_SSIF                        ELC_EVENT_SSI0_INT
#define ELC_EVENT_SSI0_SSIRXI                      ELC_EVENT_SSI0_RXI
#define ELC_EVENT_SSI0_SSITXI                      ELC_EVENT_SSI0_TXI
#define ELC_EVENT_SSI1_RXI                         ELC_EVENT_SSI1_TXI_RXI
#define ELC_EVENT_SSI1_SSIF                        ELC_EVENT_SSI1_INT
#define ELC_EVENT_SSI1_SSIRT                       ELC_EVENT_SSI1_TXI_RXI
#define ELC_EVENT_SSI1_TXI                         ELC_EVENT_SSI1_TXI_RXI
#define ELC_EVENT_ULPT0_ULPTCMAI                   ELC_EVENT_ULPT0_COMPARE_A
#define ELC_EVENT_ULPT0_ULPTCMBI                   ELC_EVENT_ULPT0_COMPARE_B
#define ELC_EVENT_ULPT0_ULPTI                      ELC_EVENT_ULPT0_INT
#define ELC_EVENT_ULPT1_ULPTCMAI                   ELC_EVENT_ULPT1_COMPARE_A
#define ELC_EVENT_ULPT1_ULPTCMBI                   ELC_EVENT_ULPT1_COMPARE_B
#define ELC_EVENT_ULPT1_ULPTI                      ELC_EVENT_ULPT1_INT
#define ELC_EVENT_USBFS_D0FIFO                     ELC_EVENT_USBFS_FIFO_0
#define ELC_EVENT_USBFS_D1FIFO                     ELC_EVENT_USBFS_FIFO_1
#define ELC_EVENT_USBFS_USBI                       ELC_EVENT_USBFS_INT
#define ELC_EVENT_USBFS_USBR                       ELC_EVENT_USBFS_RESUME
#define ELC_EVENT_USBHS_D0FIFO                     ELC_EVENT_USBHS_FIFO_0
#define ELC_EVENT_USBHS_D1FIFO                     ELC_EVENT_USBHS_FIFO_1
#define ELC_EVENT_USBHS_USBIR                      ELC_EVENT_USBHS_USB_INT_RESUME
#define ELC_EVENT_WDT0_NMIUNDF                     ELC_EVENT_WDT0_UNDERFLOW
#define ELC_EVENT_WDT1_NMIUNDF                     ELC_EVENT_WDT1_UNDERFLOW

/* DTC transfer-end is local to the selected core. There is no separate DTC COMPLETE source in Table 14.5. */
#if BSP_CFG_CPU_CORE == 1
 #define ELC_EVENT_DTC_END ELC_EVENT_DTC1_DTCEND
#else
 #define ELC_EVENT_DTC_END ELC_EVENT_DTC0_DTCEND
#endif

#define ELC_PERIPHERAL_NUM (33U)
#define BSP_OVERRIDE_ELC_PERIPHERAL_T

/** Implemented ELSR indices, HM Table 20.2, pp.830-831. */
typedef enum e_elc_peripheral
{
    ELC_PERIPHERAL_GPT_A             = (0),
    ELC_PERIPHERAL_GPT_B             = (1),
    ELC_PERIPHERAL_GPT_C             = (2),
    ELC_PERIPHERAL_GPT_D             = (3),
    ELC_PERIPHERAL_GPT_E             = (4),
    ELC_PERIPHERAL_GPT_F             = (5),
    ELC_PERIPHERAL_GPT_G             = (6),
    ELC_PERIPHERAL_GPT_H             = (7),
    ELC_PERIPHERAL_DAC0              = (12),
    ELC_PERIPHERAL_DAC1              = (13),
    ELC_PERIPHERAL_IOPORT1           = (14),
    ELC_PERIPHERAL_IOPORT2           = (15),
    ELC_PERIPHERAL_IOPORT3           = (16),
    ELC_PERIPHERAL_IOPORT4           = (17),
    ELC_PERIPHERAL_ADC0              = (19),
    ELC_PERIPHERAL_ADC0_B            = (20),
    ELC_PERIPHERAL_ADC0_C            = (21),
    ELC_PERIPHERAL_ADC1              = (22),
    ELC_PERIPHERAL_ADC1_B            = (23),
    ELC_PERIPHERAL_ADC1_C            = (24),
    ELC_PERIPHERAL_ADC2              = (25),
    ELC_PERIPHERAL_ADC2_B            = (26),
    ELC_PERIPHERAL_ADC2_C            = (27),
    ELC_PERIPHERAL_I3C               = (30),
    ELC_PERIPHERAL_GPTP0             = (31),
    ELC_PERIPHERAL_GPTP1             = (32),
} elc_peripheral_t;

#define BSP_ELC_PERIPHERAL_MASK (0x00000001CFFBF0FFULL)

#define BSP_PRV_VECT_ENUM(event,group)  (ELC_ ## event)

#define BSP_OVERRIDE_ELC_SOFTWARE_EVENT_T

typedef enum e_elc_software_event
{
    ELC_SOFTWARE_EVENT_0 = 0,
    ELC_SOFTWARE_EVENT_1 = 1,
    ELC_SOFTWARE_EVENT_2 = 2,
    ELC_SOFTWARE_EVENT_3 = 3,
} elc_software_event_t;

/* UNCRUSTIFY-ON */
/** @} (end addtogroup BSP_MCU_RA8P1) */

#endif
