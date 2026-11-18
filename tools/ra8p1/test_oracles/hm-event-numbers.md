---
doc: RA8P1 Group User's Manual: Hardware (R01UH1064EJ0130, Rev.1.30)
section: 14.3.2 Event Number
pages: 562-576
---

[page 562]

#### 14.3.2 Event Number

The following table lists heading details for Table 14.5, which describes each event number.

| Table 14.4 Heading details for Event List |  |
|---|---|
| Heading | Description |
| Interrupt request source | Name of the source generating the interrupt request |
| Name | Name of the interrupt |
| Connect to NVIC | “ ✓” indicates the interrupt can be used as a CPU interrupt |
| Invoke DTC | “ ✓” indicates the interrupt can be used to request DTC activation |
| Invoke DMAC | “✓” indicates the interrupt can be used to request DMAC activation |
| Canceling CPU Deep Sleep | “✓” indicates the interrupt can be used to request a return from CPU Deep Sleep mode |
| Canceling Software Standby | “ ✓” indicates the interrupt can be used to request a return from Software Standby mode |
| Canceling Deep Software Standby | “✓” indicates the interrupt can be used to request a return from Deep Software Standby mode |

[page 563]

| Table 14.5 Event List (1 of 14) |  |  |  |  |  |  |  |  |
|---|---|---|---|---|---|---|---|---|
| Event number | Interrupt request source | Name | IELSRn |  | DELSRn | Canceling CPU Deep Sleep | Canceling Software Standby | Canceling Deep Software Standby |
|  |  |  | Connect to NVIC | Invoke DTC | Invoke DMAC |  |  |  |
| 0x001 | Port | PORT_IRQ0 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x002 |  | PORT_IRQ1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x003 |  | PORT_IRQ2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x004 |  | PORT_IRQ3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x005 |  | PORT_IRQ4 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x006 |  | PORT_IRQ5 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x007 |  | PORT_IRQ6 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x008 |  | PORT_IRQ7 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x009 |  | PORT_IRQ8 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x00A |  | PORT_IRQ9 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x00B |  | PORT_IRQ10 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x00C |  | PORT_IRQ11 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x00D |  | PORT_IRQ12 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x00E |  | PORT_IRQ13 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x00F |  | PORT_IRQ14 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x010 |  | PORT_IRQ15 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x011 |  | PORT_IRQ16 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x012 |  | PORT_IRQ17 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x013 |  | PORT_IRQ18 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x014 |  | PORT_IRQ19 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x015 |  | PORT_IRQ20 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x016 |  | PORT_IRQ21 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x017 |  | PORT_IRQ22 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x018 |  | PORT_IRQ23 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x019 |  | PORT_IRQ24 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x01A |  | PORT_IRQ25 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x01B |  | PORT_IRQ26 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x01C |  | PORT_IRQ27 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x01D |  | PORT_IRQ28 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x01E |  | PORT_IRQ29 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x01F |  | PORT_IRQ30 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x020 |  | PORT_IRQ31 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0x040 | DMAC00 | DMAC00_INT | ✓ | ✓ | — | ✓ | — | — |
| 0x041 | DMAC01 | DMAC01_INT | ✓ | ✓ | — | ✓ | — | — |
| 0x042 | DMAC02 | DMAC02_INT | ✓ | ✓ | — | ✓ | — | — |
| 0x043 | DMAC03 | DMAC03_INT | ✓ | ✓ | — | ✓ | — | — |
| 0x044 | DMAC04 | DMAC04_INT | ✓ | ✓ | — | ✓ | — | — |
| 0x045 | DMAC05 | DMAC05_INT | ✓ | ✓ | — | ✓ | — | — |
| 0x046 | DMAC06 | DMAC06_INT | ✓ | ✓ | — | ✓ | — | — |
| 0x047 | DMAC07 | DMAC07_INT | ✓ | ✓ | — | ✓ | — | — |

[page 564]

| Table 14.5 Event List (2 of 14) |  |  |  |  |  |  |  |  |
|---|---|---|---|---|---|---|---|---|
| Event number | Interrupt request source | Name | IELSRn |  | DELSRn | Canceling CPU Deep Sleep | Canceling Software Standby | Canceling Deep Software Standby |
|  |  |  | Connect to NVIC | Invoke DTC | Invoke DMAC |  |  |  |
| 0x048 | DMAC10 | DMAC10_INT | ✓ | ✓ | — | ✓ | — | — |
| 0x049 | DMAC11 | DMAC11_INT | ✓ | ✓ | — | ✓ | — | — |
| 0x04A | DMAC12 | DMAC12_INT | ✓ | ✓ | — | ✓ | — | — |
| 0x04B | DMAC13 | DMAC13_INT | ✓ | ✓ | — | ✓ | — | — |
| 0x04C | DMAC14 | DMAC14_INT | ✓ | ✓ | — | ✓ | — | — |
| 0x04D | DMAC15 | DMAC15_INT | ✓ | ✓ | — | ✓ | — | — |
| 0x04E | DMAC16 | DMAC16_INT | ✓ | ✓ | — | ✓ | — | — |
| 0x04F | DMAC17 | DMAC17_INT | ✓ | ✓ | — | ✓ | — | — |
| 0x056 | DMAC/DTC | DMA0_TRANSERR | ✓ | — | — | ✓ | — | — |
| 0x057 | DMAC/DTC | DMA1_TRANSERR | ✓ | — | — | ✓ | — | — |
| 0x058 | DBG | DBG_CTIIRQ0 | ✓ | — | — | — | — | — |
| 0x059 |  | DBG_CTIIRQ1 | ✓ | — | — | — | — | — |
| 0x05A |  | DBG_JBRXI | ✓ | — | — | ✓ | — | — |
| 0x05B | IPC | IPC_IRQ0 | ✓ | — | — | ✓ | — | — |
| 0x05C |  | IPC_IRQ1 | ✓ | — | — | ✓ | — | — |
| 0x05F | Local Memory | LM0_ERR | ✓ | — | — | ✓ | — | — |
| 0x060 |  | LM1_ERR | ✓ | — | — | ✓ | — | — |
| 0x061 | CPU | CPU0_LOCKUP | ✓ | — | — | ✓ | — | — |
| 0x062 |  | CPU1_LOCKUP | ✓ | — | — | ✓ | — | — |
| 0x063 | BUS | BUS_ERR | ✓ | — | — | ✓ | — | — |
| 0x064 | CM | CM_ERR | ✓ | — | — | ✓ | — | — |
| 0x065 | FPU | FPU_EXC | ✓ | — | — | — | — | — |
| 0x067 | NPU | NPU_IRQ | ✓ | — | — | ✓ | — | — |
| 0x068 | MRAM | MRAM_MRCRD | ✓ | — | — | ✓ | — | — |
| 0x069 |  | MRAM_MRERD | ✓ | — | — | ✓ | — | — |
| 0x06B |  | MRAM_MRCPR | ✓ | — | — | ✓ | — | — |
| 0x06C |  | MRAM_MREPR | ✓ | — | — | ✓ | — | — |
| 0x06D |  | MRAM_ENDOFPE | ✓ | — | — | ✓ | — | — |
| 0x070 | PVD1 | PVD_PVD1 | ✓ | — | — | ✓ | ✓ | ✓*4 |
| 0x071 | PVD2 | PVD_PVD2 | ✓ | — | — | ✓ | ✓ | ✓*4 |
| 0x075 | BBF | VBATT_TADI | ✓ | — | — | ✓ | ✓ | ✓ |
| 0x076 | MOSC | MOSC_STOP | ✓ | — | — | ✓ | — | — |
| 0x077 | SOSC | SOSC_STOP | ✓ | — | — | ✓ | ✓ | ✓ |
| 0x080 | ULPT0 | ULPT0_ULPTI | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ *5 |
| 0x081 |  | ULPT0_ULPTCMAI | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| 0x082 |  | ULPT0_ULPTCMBI | ✓ | ✓ | ✓ | ✓ | ✓ | — |

[page 565]

| Table 14.5 Event List (3 of 14) |  |  |  |  |  |  |  |  |
|---|---|---|---|---|---|---|---|---|
| Event number | Interrupt request source | Name | IELSRn |  | DELSRn | Canceling CPU Deep Sleep | Canceling Software Standby | Canceling Deep Software Standby |
|  |  |  | Connect to NVIC | Invoke DTC | Invoke DMAC |  |  |  |
| 0x083 | ULPT1 | ULPT1_ULPTI | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ *5 |
| 0x084 |  | ULPT1_ULPTCMAI | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| 0x085 |  | ULPT1_ULPTCMBI | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| 0x086 | AGT0 | AGT0_AGTI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x087 |  | AGT0_AGTCMAI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x088 |  | AGT0_AGTCMBI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x089 | AGT1 | AGT1_AGTI | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| 0x08A |  | AGT1_AGTCMAI | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| 0x08B |  | AGT1_AGTCMBI | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| 0x092 | IWDT | IWDT_NMIUNDF | ✓ | — | — | ✓ | ✓ | ✓ *5 |
| 0x093 | WDT0 | WDT0_NMIUNDF | ✓ | — | — | ✓ | — | — |
| 0x094 | WDT1 | WDT1_NMIUNDF | ✓ | — | — | ✓ | — | — |
| 0x095 | RTC | RTC_ALM | ✓ | — | — | ✓ | ✓ | ✓ |
| 0x096 |  | RTC_PRD | ✓ | — | — | ✓ | ✓ | ✓ |
| 0x097 |  | RTC_CUP | ✓ | — | — | ✓ | — | — |
| 0x098 | USBFS | USBFS_D0FIFO | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x099 |  | USBFS_D1FIFO | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x09A |  | USBFS_USBI | ✓ | — | — | ✓ | — | — |
| 0x09B |  | USBFS_USBR | ✓ | — | — | ✓ | ✓ | ✓ *5 |
| 0x09C | IIC0 | IIC0_RXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x09D |  | IIC0_TXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x09E |  | IIC0_TEI | ✓ | — | — | ✓ | — | — |
| 0x09F |  | IIC0_EEI | ✓ | — | — | ✓ | — | — |
| 0x0A0 |  | IIC0_WUI | ✓ | — | — | ✓ | ✓ | — |
| 0x0A1 | IIC1 | IIC1_RXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x0A2 |  | IIC1_TXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x0A3 |  | IIC1_TEI | ✓ | — | — | ✓ | — | — |
| 0x0A4 |  | IIC1_EEI | ✓ | — | — | ✓ | — | — |
| 0x0A6 | IIC2 | IIC2_RXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x0A7 |  | IIC2_TXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x0A8 |  | IIC2_TEI | ✓ | — | — | ✓ | — | — |
| 0x0A9 |  | IIC2_EEI | ✓ | — | — | ✓ | — | — |
| 0x0AB | SDHI/MMC0 | SDHI_MMC0_ACCS | ✓ | — | — | ✓ | — | — |
| 0x0AC |  | SDHI_MMC0_SDIO | ✓ | — | — | ✓ | — | — |
| 0x0AD |  | SDHI_MMC0_CARD | ✓ | — | — | ✓ | — | — |
| 0x0AE |  | SDHI_MMC0_ODMSDBREQ | — | ✓ | ✓ | ✓ | — | — |
| 0x0AF | SDHI/MMC1 | SDHI_MMC1_ACCS | ✓ | — | — | ✓ | — | — |
| 0x0B0 |  | SDHI_MMC1_SDIO | ✓ | — | — | ✓ | — | — |
| 0x0B1 |  | SDHI_MMC1_CARD | ✓ | — | — | ✓ | — | — |
| 0x0B2 |  | SDHI_MMC1_ODMSDBREQ | — | ✓ | ✓ | ✓ | — | — |

[page 566]

| Table 14.5 Event List (4 of 14) |  |  |  |  |  |  |  |  |
|---|---|---|---|---|---|---|---|---|
| Event number | Interrupt request source | Name | IELSRn |  | DELSRn | Canceling CPU Deep Sleep | Canceling Software Standby | Canceling Deep Software Standby |
|  |  |  | Connect to NVIC | Invoke DTC | Invoke DMAC |  |  |  |
| 0x0B3 | SSI0 | SSI0_SSITXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x0B4 |  | SSI0_SSIRXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x0B6 |  | SSI0_SSIF | ✓ | — | — | ✓ | — | — |
| 0x0B9 | SSI1 | SSI1_SSIRT | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x0BA |  | SSI1_SSIF | ✓ | — | — | ✓ | — | — |
| 0x0BB | OSPI0 | OSPI0_ERR | ✓ | — | — | ✓ | — | — |
| 0x0BC |  | OSPI0_CMP | ✓ | — | — | ✓ | — | — |
| 0x0BD | OSPI1 | OSPI1_ERR | ✓ | — | — | ✓ | — | — |
| 0x0BE |  | OSPI1_CMP | ✓ | — | — | ✓ | — | — |
| 0x0BF | PDMIF | PDM_DAT0 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x0C0 |  | PDM_DAT1 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x0C1 |  | PDM_DAT2 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x0C2 |  | PDM_SDET | ✓ | — | — | ✓ | ✓ | — |
| 0x0C3 |  | PDM_ERR0 | ✓ | — | — | ✓ | — | — |
| 0x0C4 |  | PDM_ERR1 | ✓ | — | — | ✓ | — | — |
| 0x0C5 |  | PDM_ERR2 | ✓ | — | — | ✓ | — | — |
| 0x0C6 | ACMPHS | ACMP_HS0 | ✓ | — | — | ✓*1 | ✓*1 | — |
| 0x0C7 |  | ACMP_HS1 | ✓ | — | — | ✓ | — | — |
| 0x0C8 |  | ACMP_HS2 | ✓ | — | — | ✓ | — | — |
| 0x0C9 |  | ACMP_HS3 | ✓ | — | — | ✓ | — | — |
| 0x0CC | ELC | ELC_SWEVT0 | ✓*3 | ✓ | — | ✓ | — | — |
| 0x0CD |  | ELC_SWEVT1 | ✓*3 | ✓ | — | ✓ | — | — |
| 0x0CE |  | ELC_SWEVT2 | ✓*3 | ✓ | — | ✓ | — | — |
| 0x0CF |  | ELC_SWEVT3 | ✓*3 | ✓ | — | ✓ | — | — |
| 0x0D0 | PORT | IOPORT_GROUP1 | ✓ | ✓*2 | ✓*2 | ✓ | — | — |
| 0x0D1 |  | IOPORT_GROUP2 | ✓ | ✓*2 | ✓*2 | ✓ | — | — |
| 0x0D2 |  | IOPORT_GROUP3 | ✓ | ✓*2 | ✓*2 | ✓ | — | — |
| 0x0D3 |  | IOPORT_GROUP4 | ✓ | ✓*2 | ✓*2 | ✓ | — | — |
| 0x0D4 | CAC | CAC_FEERI | ✓ | — | — | ✓ | — | — |
| 0x0D5 |  | CAC_MENDI | ✓ | — | — | ✓ | — | — |
| 0x0D6 |  | CAC_OVFI | ✓ | — | — | ✓ | — | — |
| 0x0D7 | POEG | POEG_GROUPA | ✓ | — | — | ✓ | — | — |
| 0x0D8 |  | POEG_GROUPB | ✓ | — | — | ✓ | — | — |
| 0x0D9 |  | POEG_GROUPC | ✓ | — | — | ✓ | — | — |
| 0x0DA |  | POEG_GROUPD | ✓ | — | — | ✓ | — | — |
| 0x180 | GPT | GPT_UVWEDGE | ✓ | — | — | ✓ | — | — |

[page 567]

| Table 14.5 Event List (5 of 14) |  |  |  |  |  |  |  |  |
|---|---|---|---|---|---|---|---|---|
| Event number | Interrupt request source | Name | IELSRn |  | DELSRn | Canceling CPU Deep Sleep | Canceling Software Standby | Canceling Deep Software Standby |
|  |  |  | Connect to NVIC | Invoke DTC | Invoke DMAC |  |  |  |
| 0x181 | GPT0 | GPT0_CCMPA | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x182 |  | GPT0_CCMPB | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x183 |  | GPT0_CMPC | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x184 |  | GPT0_CMPD | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x185 |  | GPT0_CMPE | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x186 |  | GPT0_CMPF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x187 |  | GPT0_OVF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x188 |  | GPT0_UDF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x189 |  | GPT0_PC | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x18A | GPT1 | GPT1_CCMPA | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x18B |  | GPT1_CCMPB | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x18C |  | GPT1_CMPC | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x18D |  | GPT1_CMPD | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x18E |  | GPT1_CMPE | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x18F |  | GPT1_CMPF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x190 |  | GPT1_OVF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x191 |  | GPT1_UDF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x192 |  | GPT1_PC | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x193 | GPT2 | GPT2_CCMPA | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x194 |  | GPT2_CCMPB | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x195 |  | GPT2_CMPC | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x196 |  | GPT2_CMPD | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x197 |  | GPT2_CMPE | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x198 |  | GPT2_CMPF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x199 |  | GPT2_OVF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x19A |  | GPT2_UDF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x19B |  | GPT2_PC | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x19C | GPT3 | GPT3_CCMPA | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x19D |  | GPT3_CCMPB | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x19E |  | GPT3_CMPC | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x19F |  | GPT3_CMPD | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1A0 |  | GPT3_CMPE | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1A1 |  | GPT3_CMPF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1A2 |  | GPT3_OVF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1A3 |  | GPT3_UDF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1A4 |  | GPT3_PC | ✓ | ✓ | ✓ | ✓ | — | — |

[page 568]

| Table 14.5 Event List (6 of 14) |  |  |  |  |  |  |  |  |
|---|---|---|---|---|---|---|---|---|
| Event number | Interrupt request source | Name | IELSRn |  | DELSRn | Canceling CPU Deep Sleep | Canceling Software Standby | Canceling Deep Software Standby |
|  |  |  | Connect to NVIC | Invoke DTC | Invoke DMAC |  |  |  |
| 0x1A5 | GPT4 | GPT4_CCMPA | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1A6 |  | GPT4_CCMPB | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1A7 |  | GPT4_CMPC | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1A8 |  | GPT4_CMPD | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1A9 |  | GPT4_CMPE | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1AA |  | GPT4_CMPF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1AB |  | GPT4_OVF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1AC |  | GPT4_UDF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1AE | GPT5 | GPT5_CCMPA | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1AF |  | GPT5_CCMPB | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1B0 |  | GPT5_CMPC | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1B1 |  | GPT5_CMPD | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1B2 |  | GPT5_CMPE | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1B3 |  | GPT5_CMPF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1B4 |  | GPT5_OVF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1B5 |  | GPT5_UDF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1B7 | GPT6 | GPT6_CCMPA | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1B8 |  | GPT6_CCMPB | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1B9 |  | GPT6_CMPC | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1BA |  | GPT6_CMPD | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1BB |  | GPT6_CMPE | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1BC |  | GPT6_CMPF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1BD |  | GPT6_OVF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1BE |  | GPT6_UDF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1C0 | GPT7 | GPT7_CCMPA | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1C1 |  | GPT7_CCMPB | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1C2 |  | GPT7_CMPC | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1C3 |  | GPT7_CMPD | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1C4 |  | GPT7_CMPE | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1C5 |  | GPT7_CMPF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1C6 |  | GPT7_OVF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1C7 |  | GPT7_UDF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1C9 | GPT8 | GPT8_CCMPA | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1CA |  | GPT8_CCMPB | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1CB |  | GPT8_CMPC | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1CC |  | GPT8_CMPD | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1CD |  | GPT8_CMPE | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1CE |  | GPT8_CMPF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1CF |  | GPT8_OVF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1D0 |  | GPT8_UDF | ✓ | ✓ | ✓ | ✓ | — | — |

[page 569]

| Table 14.5 Event List (7 of 14) |  |  |  |  |  |  |  |  |
|---|---|---|---|---|---|---|---|---|
| Event number | Interrupt request source | Name | IELSRn |  | DELSRn | Canceling CPU Deep Sleep | Canceling Software Standby | Canceling Deep Software Standby |
|  |  |  | Connect to NVIC | Invoke DTC | Invoke DMAC |  |  |  |
| 0x1D2 | GPT9 | GPT9_CCMPA | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1D3 |  | GPT9_CCMPB | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1D4 |  | GPT9_CMPC | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1D5 |  | GPT9_CMPD | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1D6 |  | GPT9_CMPE | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1D7 |  | GPT9_CMPF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1D8 |  | GPT9_OVF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1D9 |  | GPT9_UDF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1DB | GPT10 | GPT10_CCMPA | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1DC |  | GPT10_CCMPB | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1DD |  | GPT10_CMPC | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1DE |  | GPT10_CMPD | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1DF |  | GPT10_CMPE | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1E0 |  | GPT10_CMPF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1E1 |  | GPT10_OVF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1E2 |  | GPT10_UDF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1E3 |  | GPT10_PC | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1E4 | GPT11 | GPT11_CCMPA | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1E5 |  | GPT11_CCMPB | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1E6 |  | GPT11_CMPC | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1E7 |  | GPT11_CMPD | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1E8 |  | GPT11_CMPE | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1E9 |  | GPT11_CMPF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1EA |  | GPT11_OVF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1EB |  | GPT11_UDF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1EC |  | GPT11_PC | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1ED | GPT12 | GPT12_CCMPA | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1EE |  | GPT12_CCMPB | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1EF |  | GPT12_CMPC | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1F0 |  | GPT12_CMPD | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1F1 |  | GPT12_CMPE | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1F2 |  | GPT12_CMPF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1F3 |  | GPT12_OVF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1F4 |  | GPT12_UDF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1F5 |  | GPT12_PC | ✓ | ✓ | ✓ | ✓ | — | — |

[page 570]

| Table 14.5 Event List (8 of 14) |  |  |  |  |  |  |  |  |
|---|---|---|---|---|---|---|---|---|
| Event number | Interrupt request source | Name | IELSRn |  | DELSRn | Canceling CPU Deep Sleep | Canceling Software Standby | Canceling Deep Software Standby |
|  |  |  | Connect to NVIC | Invoke DTC | Invoke DMAC |  |  |  |
| 0x1F6 | GPT13 | GPT13_CCMPA | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1F7 |  | GPT13_CCMPB | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1F8 |  | GPT13_CMPC | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1F9 |  | GPT13_CMPD | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1FA |  | GPT13_CMPE | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1FB |  | GPT13_CMPF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1FC |  | GPT13_OVF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1FD |  | GPT13_UDF | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x1FE |  | GPT13_PC | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x29A | ESWM | ETHER_FWEI | ✓ | — | — | ✓ | — | — |
| 0x29B |  | ETHER_CAEI | ✓ | — | — | ✓ | — | — |
| 0x29C |  | ETHER_GWEI | ✓ | — | — | ✓ | — | — |
| 0x29D |  | ETHER_EAEI0 | ✓ | — | — | ✓ | — | — |
| 0x29E |  | ETHER_EAEI1 | ✓ | — | — | ✓ | — | — |
| 0x29F |  | ETHER_PTPSI0 | ✓ | — | — | ✓ | — | — |
| 0x2A0 |  | ETHER_PTPSI1 | ✓ | — | — | ✓ | — | — |
| 0x2A1 |  | ETHER_FWSI | ✓ | — | — | ✓ | — | — |
| 0x2A3 |  | ETHER_CAMI | ✓ | — | — | ✓ | — | — |
| 0x2A4 |  | ETHER_EASI0 | ✓ | — | — | ✓ | — | — |
| 0x2A5 |  | ETHER_EASI1 | ✓ | — | — | ✓ | — | — |
| 0x2A6 |  | ETHER_GWDI0 | ✓ | — | — | ✓ | — | — |
| 0x2A7 |  | ETHER_GWDI1 | ✓ | — | — | ✓ | — | — |
| 0x2A8 |  | ETHER_GWDI2 | ✓ | — | — | ✓ | — | — |
| 0x2A9 |  | ETHER_GWDI3 | ✓ | — | — | ✓ | — | — |
| 0x2AA |  | ETHER_GWDI4 | ✓ | — | — | ✓ | — | — |
| 0x2AB |  | ETHER_GWDI5 | ✓ | — | — | ✓ | — | — |
| 0x2AC |  | ETHER_GWDI6 | ✓ | — | — | ✓ | — | — |
| 0x2AD |  | ETHER_GWDI7 | ✓ | — | — | ✓ | — | — |
| 0x2AE |  | ETHER_TSDI0 | ✓ | — | — | ✓ | — | — |
| 0x2AF |  | ETHER_TSDI1 | ✓ | — | — | ✓ | — | — |
| 0x2B0 |  | ETHER_MDIO0 | ✓ | — | — | ✓ | — | — |
| 0x2B1 |  | ETHER_MDIO1 | ✓ | — | — | ✓ | — | — |
| 0x2B2 |  | ETHER_RMPI0 | ✓ | — | — | ✓ | — | — |
| 0x2B3 |  | ETHER_RMPI1 | ✓ | — | — | ✓ | — | — |
| 0x2B4 |  | GPTP_PTPOUT0 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2B5 |  | GPTP_PTPOUT1 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2B6 |  | GPTP_PTPOUT2 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2B7 |  | GPTP_PTPOUT3 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2B8 |  | GPTP_MATCH0 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2B9 |  | GPTP_MATCH1 | ✓ | ✓ | ✓ | ✓ | — | — |

[page 571]

| Table 14.5 Event List (9 of 14) |  |  |  |  |  |  |  |  |
|---|---|---|---|---|---|---|---|---|
| Event number | Interrupt request source | Name | IELSRn |  | DELSRn | Canceling CPU Deep Sleep | Canceling Software Standby | Canceling Deep Software Standby |
|  |  |  | Connect to NVIC | Invoke DTC | Invoke DMAC |  |  |  |
| 0x2C1 | USBHS | USBHS_D0FIFO | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2C2 |  | USBHS_D1FIFO | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2C3 |  | USBHS_USBIR | ✓ | — | — | ✓ | ✓ | ✓*5 |
| 0x2C4 | SCI0 | SCI0_RXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2C5 |  | SCI0_TXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2C6 |  | SCI0_TEI | ✓ | — | — | ✓ | — | — |
| 0x2C7 |  | SCI0_ERI | ✓ | — | — | ✓ | — | — |
| 0x2C8 |  | SCI0_AED | ✓ | — | — | ✓ | — | — |
| 0x2C9 |  | SCI0_BFD | ✓ | — | — | ✓ | — | — |
| 0x2CA |  | SCI0_AM | ✓ | — | — | ✓ | — | — |
| 0x2CB | SCI1 | SCI1_RXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2CC |  | SCI1_TXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2CD |  | SCI1_TEI | ✓ | — | — | ✓ | — | — |
| 0x2CE |  | SCI1_ERI | ✓ | — | — | ✓ | — | — |
| 0x2CF |  | SCI1_AED | ✓ | — | — | ✓ | — | — |
| 0x2D0 |  | SCI1_BFD | ✓ | — | — | ✓ | — | — |
| 0x2D1 |  | SCI1_AM | ✓ | — | — | ✓ | — | — |
| 0x2D2 | SCI2 | SCI2_RXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2D3 |  | SCI2_TXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2D4 |  | SCI2_TEI | ✓ | — | — | ✓ | — | — |
| 0x2D5 |  | SCI2_ERI | ✓ | — | — | ✓ | — | — |
| 0x2D6 |  | SCI2_AED | ✓ | — | — | ✓ | — | — |
| 0x2D7 |  | SCI2_BFD | ✓ | — | — | ✓ | — | — |
| 0x2D8 |  | SCI2_AM | ✓ | — | — | ✓ | — | — |
| 0x2D9 | SCI3 | SCI3_RXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2DA |  | SCI3_TXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2DB |  | SCI3_TEI | ✓ | — | — | ✓ | — | — |
| 0x2DC |  | SCI3_ERI | ✓ | — | — | ✓ | — | — |
| 0x2DD |  | SCI3_AED | ✓ | — | — | ✓ | — | — |
| 0x2DE |  | SCI3_BFD | ✓ | — | — | ✓ | — | — |
| 0x2DF |  | SCI3_AM | ✓ | — | — | ✓ | — | — |
| 0x2E0 | SCI4 | SCI4_RXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2E1 |  | SCI4_TXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2E2 |  | SCI4_TEI | ✓ | — | — | ✓ | — | — |
| 0x2E3 |  | SCI4_ERI | ✓ | — | — | ✓ | — | — |
| 0x2E4 |  | SCI4_AED | ✓ | — | — | ✓ | — | — |
| 0x2E5 |  | SCI4_BFD | ✓ | — | — | ✓ | — | — |
| 0x2E6 |  | SCI4_AM | ✓ | — | — | ✓ | — | — |

[page 572]

| Table 14.5 Event List (10 of 14) |  |  |  |  |  |  |  |  |
|---|---|---|---|---|---|---|---|---|
| Event number | Interrupt request source | Name | IELSRn |  | DELSRn | Canceling CPU Deep Sleep | Canceling Software Standby | Canceling Deep Software Standby |
|  |  |  | Connect to NVIC | Invoke DTC | Invoke DMAC |  |  |  |
| 0x2E7 | SCI5 | SCI5_RXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2E8 |  | SCI5_TXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2E9 |  | SCI5_TEI | ✓ | — | — | ✓ | — | — |
| 0x2EA |  | SCI5_ERI | ✓ | — | — | ✓ | — | — |
| 0x2EB |  | SCI5_AED | ✓ | — | — | ✓ | — | — |
| 0x2EC |  | SCI5_BFD | ✓ | — | — | ✓ | — | — |
| 0x2ED |  | SCI5_AM | ✓ | — | — | ✓ | — | — |
| 0x2EE | SCI6 | SCI6_RXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2EF |  | SCI6_TXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2F0 |  | SCI6_TEI | ✓ | — | — | ✓ | — | — |
| 0x2F1 |  | SCI6_ERI | ✓ | — | — | ✓ | — | — |
| 0x2F2 |  | SCI6_AED | ✓ | — | — | ✓ | — | — |
| 0x2F3 |  | SCI6_BFD | ✓ | — | — | ✓ | — | — |
| 0x2F4 |  | SCI6_AM | ✓ | — | — | ✓ | — | — |
| 0x2F5 | SCI7 | SCI7_RXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2F6 |  | SCI7_TXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2F7 |  | SCI7_TEI | ✓ | — | — | ✓ | — | — |
| 0x2F8 |  | SCI7_ERI | ✓ | — | — | ✓ | — | — |
| 0x2F9 |  | SCI7_AED | ✓ | — | — | ✓ | — | — |
| 0x2FA |  | SCI7_BFD | ✓ | — | — | ✓ | — | — |
| 0x2FB |  | SCI7_AM | ✓ | — | — | ✓ | — | — |
| 0x2FC | SCI8 | SCI8_RXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2FD |  | SCI8_TXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x2FE |  | SCI8_TEI | ✓ | — | — | ✓ | — | — |
| 0x2FF |  | SCI8_ERI | ✓ | — | — | ✓ | — | — |
| 0x300 |  | SCI8_AED | ✓ | — | — | ✓ | — | — |
| 0x301 |  | SCI8_BFD | ✓ | — | — | ✓ | — | — |
| 0x302 |  | SCI8_AM | ✓ | — | — | ✓ | — | — |
| 0x303 | SCI9 | SCI9_RXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x304 |  | SCI9_TXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x305 |  | SCI9_TEI | ✓ | — | — | ✓ | — | — |
| 0x306 |  | SCI9_ERI | ✓ | — | — | ✓ | — | — |
| 0x307 |  | SCI9_AED | ✓ | — | — | ✓ | — | — |
| 0x308 |  | SCI9_BFD | ✓ | — | — | ✓ | — | — |
| 0x309 |  | SCI9_AM | ✓ | — | — | ✓ | — | — |

[page 573]

| Table 14.5 Event List (11 of 14) |  |  |  |  |  |  |  |  |
|---|---|---|---|---|---|---|---|---|
| Event number | Interrupt request source | Name | IELSRn |  | DELSRn | Canceling CPU Deep Sleep | Canceling Software Standby | Canceling Deep Software Standby |
|  |  |  | Connect to NVIC | Invoke DTC | Invoke DMAC |  |  |  |
| 0x30A | SCI10 | SCI10_RXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x30B |  | SCI10_TXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x30C |  | SCI10_TEI | ✓ | — | — | ✓ | — | — |
| 0x30D |  | SCI10_ERI | ✓ | — | — | ✓ | — | — |
| 0x30E |  | SCI10_AED | ✓ | — | — | ✓ | — | — |
| 0x30F |  | SCI10_BFD | ✓ | — | — | ✓ | — | — |
| 0x310 |  | SCI10_AM | ✓ | — | — | ✓ | — | — |
| 0x311 | SCI11 | SCI11_RXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x312 |  | SCI11_TXI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x313 |  | SCI11_TEI | ✓ | — | — | ✓ | — | — |
| 0x314 |  | SCI11_ERI | ✓ | — | — | ✓ | — | — |
| 0x315 |  | SCI11_AED | ✓ | — | — | ✓ | — | — |
| 0x316 |  | SCI11_BFD | ✓ | — | — | ✓ | — | — |
| 0x317 |  | SCI11_AM | ✓ | — | — | ✓ | — | — |
| 0x318 | SPI0 | SPI0_SPRI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x319 |  | SPI0_SPTI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x31A |  | SPI0_SPII | ✓ | — | — | ✓ | — | — |
| 0x31B |  | SPI0_SPEI | ✓ | — | — | ✓ | — | — |
| 0x31C |  | SPI0_SPCEND | ✓ | — | — | ✓ | — | — |
| 0x31D | SPI1 | SPI1_SPRI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x31E |  | SPI1_SPTI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x31F |  | SPI1_SPII | ✓ | — | — | ✓ | — | — |
| 0x320 |  | SPI1_SPEI | ✓ | — | — | ✓ | — | — |
| 0x321 |  | SPI1_SPCEND | ✓ | — | — | ✓ | — | — |

[page 574]

| Table 14.5 Event List (12 of 14) |  |  |  |  |  |  |  |  |
|---|---|---|---|---|---|---|---|---|
| Event number | Interrupt request source | Name | IELSRn |  | DELSRn | Canceling CPU Deep Sleep | Canceling Software Standby | Canceling Deep Software Standby |
|  |  |  | Connect to NVIC | Invoke DTC | Invoke DMAC |  |  |  |
| 0x322 | CANFD | CAN_RXF | ✓ | — | — | ✓ | — | — |
| 0x323 |  | CAN_GLERR | ✓ | — | — | ✓ | — | — |
| 0x324 |  | CAN0_RF_DMAREQ0 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x325 |  | CAN0_RF_DMAREQ1 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x328 |  | CAN1_RF_DMAREQ0 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x329 |  | CAN1_RF_DMAREQ1 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x32C |  | CAN0_TX | ✓ | — | — | ✓ | — | — |
| 0x32D |  | CAN0_CHERR | ✓ | — | — | ✓ | — | — |
| 0x32E |  | CAN0_COMFRX | ✓ | — | — | ✓ | — | — |
| 0x32F |  | CAN0_CF_DMAREQ | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x330 |  | CAN0_RXMB | ✓ | — | — | ✓ | — | — |
| 0x331 |  | CAN1_TX | ✓ | — | — | ✓ | — | — |
| 0x332 |  | CAN1_CHERR | ✓ | — | — | ✓ | — | — |
| 0x333 |  | CAN1_COMFRX | ✓ | — | — | ✓ | — | — |
| 0x334 |  | CAN1_CF_DMAREQ | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x335 |  | CAN1_RXMB | ✓ | — | — | ✓ | — | — |
| 0x338 |  | CAN0_MRAM_ERI | ✓ | — | — | ✓ | — | — |
| 0x339 |  | CAN1_MRAM_ERI | ✓ | — | — | ✓ | — | — |
| 0x33A | I3C | I3C_RESP | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x33B |  | I3C_CMD | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x33C |  | I3C_IBI | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x33D |  | I3C_RX | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x33E |  | I3C_TX | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x33F |  | I3C_RCV | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x340 |  | I3C_HRESP | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x341 |  | I3C_HCMD | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x342 |  | I3C_HRX | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x343 |  | I3C_HTX | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x344 |  | I3C_TEND | ✓ | — | — | ✓ | — | — |
| 0x345 |  | I3C_EEI | ✓ | — | — | ✓ | — | — |
| 0x346 |  | I3C_STEV | ✓ | — | — | ✓ | — | — |
| 0x347 |  | I3C_MREFOVF | ✓ | — | — | ✓ | — | — |
| 0x348 |  | I3C_MREFCPT | ✓ | — | — | ✓ | — | — |
| 0x349 |  | I3C_AMEV | ✓ | — | — | ✓ | — | — |
| 0x34A |  | I3C_WU | ✓ | — | — | ✓ | ✓ | — |

[page 575]

| Table 14.5 Event List (13 of 14) |  |  |  |  |  |  |  |  |
|---|---|---|---|---|---|---|---|---|
| Event number | Interrupt request source | Name | IELSRn |  | DELSRn | Canceling CPU Deep Sleep | Canceling Software Standby | Canceling Deep Software Standby |
|  |  |  | Connect to NVIC | Invoke DTC | Invoke DMAC |  |  |  |
| 0x34B | ADC16H | ADC_LIMCLPI | ✓ | — | — | ✓ | — | — |
| 0x34C |  | ADC_FIFOOVF | ✓ | — | — | ✓ | — | — |
| 0x34D |  | ADC_ADI0 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x34E |  | ADC_ADI1 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x34F |  | ADC_ADI2 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x350 |  | ADC_ADI3 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x351 |  | ADC_ADI4 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x352 |  | ADC_ADI5 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x353 |  | ADC_ADI6 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x354 |  | ADC_ADI7 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x355 |  | ADC_ADI8 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x356 |  | ADC_FIFOREQ0 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x357 |  | ADC_FIFOREQ1 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x358 |  | ADC_FIFOREQ2 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x359 |  | ADC_FIFOREQ3 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x35A |  | ADC_FIFOREQ4 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x35B |  | ADC_FIFOREQ5 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x35C |  | ADC_FIFOREQ6 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x35D |  | ADC_FIFOREQ7 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x35E |  | ADC_FIFOREQ8 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x35F |  | ADC_CMPI0 | ✓ | — | — | ✓ | — | — |
| 0x360 |  | ADC_CMPI1 | ✓ | — | — | ✓ | — | — |
| 0x361 |  | ADC_CCMPM0 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x362 |  | ADC_CCMPUM0 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x363 |  | ADC_ERR0 | ✓ | — | — | ✓ | — | — |
| 0x364 |  | ADC_RESOVF0 | ✓ | — | — | ✓ | — | — |
| 0x366 |  | ADC_CALEND0 | ✓ | — | — | ✓ | — | — |
| 0x367 |  | ADC_CMPI2 | ✓ | — | — | ✓ | — | — |
| 0x368 |  | ADC_CMPI3 | ✓ | — | — | ✓ | — | — |
| 0x369 |  | ADC_CCMPM1 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x36A |  | ADC_CCMPUM1 | ✓ | ✓ | ✓ | ✓ | — | — |
| 0x36B |  | ADC_ERR1 | ✓ | — | — | ✓ | — | — |
| 0x36C |  | ADC_RESOVF1 | ✓ | — | — | ✓ | — | — |
| 0x36E |  | ADC_CALEND1 | ✓ | — | — | ✓ | — | — |
| 0x36F | DOC | DOC_DOPCI | ✓ | — | — | ✓ | — | — |
| 0x371 | RSIP-E50D | RSIP_TADI | ✓ | — | — | ✓ | — | — |
| 0x382 | GLCDC | GLCDC_VPOS | ✓ | — | — | ✓ | — | — |
| 0x383 |  | GLCDC_L1UNDF | ✓ | — | — | ✓ | — | — |
| 0x384 |  | GLCDC_L2UNDF | ✓ | — | — | ✓ | — | — |

[page 576]

| Table 14.5 Event List (14 of 14) |  |  |  |  |  |  |  |  |
|---|---|---|---|---|---|---|---|---|
| Event number | Interrupt request source | Name | IELSRn |  | DELSRn | Canceling CPU Deep Sleep | Canceling Software Standby | Canceling Deep Software Standby |
|  |  |  | Connect to NVIC | Invoke DTC | Invoke DMAC |  |  |  |
| 0x385 | DRW | DRW_IRQ | ✓ | — | — | ✓ | — | — |
| 0x388 | MIPI DSI | DSI_SEQ0 | ✓ | — | — | ✓ | — | — |
| 0x389 |  | DSI_SEQ1 | ✓ | — | — | ✓ | — | — |
| 0x38A |  | DSI_VIN1 | ✓ | — | — | ✓ | — | — |
| 0x38B |  | DSI_RCV | ✓ | — | — | ✓ | — | — |
| 0x38C |  | DSI_FERR | ✓ | — | — | ✓ | — | — |
| 0x38D |  | DSI_PPI | ✓ | — | — | ✓ | — | — |
| 0x38F | MIPI CSI | CSI_RX | ✓ | — | — | ✓ | — | — |
| 0x390 |  | CSI_DL | ✓ | — | — | ✓ | — | — |
| 0x391 |  | CSI_VC | ✓ | — | — | ✓ | — | — |
| 0x392 |  | CSI_PM | ✓ | — | — | ✓ | — | — |
| 0x393 |  | CSI_GST | ✓ | — | — | ✓ | — | — |
| 0x394 |  | CSI_DBG | ✓ | — | — | ✓ | — | — |
| 0x395 | VIN | VIN_IRQ | ✓ | — | — | ✓ | — | — |
| 0x396 |  | VIN_ERR | ✓ | — | — | ✓ | — | — |
| 0x397 | CEU | CEU_CEUI | ✓ | — | — | ✓ | — | — |

Note 1. Only supported when CMPCTL0.CSTEN = 1.
Note 2. Only the first edge detection is valid.
Note 3. Support only interrupt after DTC transfer.
Note 4. Only supported in Deep Software Standby mode 1 and Deep Software Standby mode 2.
Note 5. Only supported in Deep Software Standby mode 1.
