---
doc: RA8P1 Group User's Manual: Hardware (R01UH1064EJ0130, Rev.1.30)
section: 20.2 Register Descriptions
pages: 829-844
---

[page 829]

### 20.2 Register Descriptions

#### 20.2.1 ELCR : Event Link Controller Register

Base address: ELC = 0x4020_1000
ELC_NS = 0x5020_1000
Offset address: 0x000
Bit position: 7 6 5 4 3 2 1 0

| ELCON | — | — | — | — | — | — | — |
|---|---|---|---|---|---|---|---|

Bit field:
Value after reset: 0 0 0 0 0 0 0 0

| Bit | Symbol | Function | R/W |
|---|---|---|---|
| 6:0 | — | These bits are read as 0. The write value should be 0. | R/W |
| 7 | ELCON | All Event Link Enable<br>0: ELC function is disabled.<br>1: ELC function is enabled. | R/W |

Note: S-TYPE-3, P-TYPE-3
The ELCR register controls the ELC operation.

#### 20.2.2 ELSEGRn : Event Link Software Event Generation Register n (n = 0 to 3)

Base address: ELC = 0x4020_1000
ELC_NS = 0x5020_1000
Offset address: 0x004 + 0x004 × n
Bit position: 7 6 5 4 3 2 1 0

| WI | WE | — | — | — | — | — | SEG |
|---|---|---|---|---|---|---|---|

Bit field:
Value after reset: 1 0 0 0 0 0 0 0

| Bit | Symbol | Function | R/W |
|---|---|---|---|
| 0 | SEG | Software Event Generation<br>0: Normal operation<br>1: Software event is generated. | W |
| 5:1 | — | These bits are read as 0. The write value should be 0. | R/W |
| 6 | WE | SEG Bit Write Enable<br>0: Write to SEG bit disabled.<br>1: Write to SEG bit enabled. | R/W |
| 7 | WI | ELSEGR Register Write Disable<br>0: Write to ELSEGR register enabled.<br>1: Write to ELSEGR register disabled. | W |

Note: S-TYPE-3, P-TYPE-3
SEG bit (Software Event Generation)
When 1 is written to the SEG bit while the WE bit is 1, a software event is generated. This bit is read as 0. Even when 1 is
written to this bit, data is not stored. The WE bit must be set to 1 before writing to this bit.
A software event can trigger a linked DTC event.
WE bit (SEG Bit Write Enable)
The SEG bit can only be written to when the WE bit is 1. Clear the WI bit to 0 before writing to this bit.
[Setting condition]
● If 1 is written to this bit while the WI bit is 0, this bit becomes 1.

[page 830]
[Clearing condition]
● If 0 is written to this bit while the WI bit is 0, this bit becomes 0.
WI bit (ELSEGR Register Write Disable)
The ELSEGR register can only be written to when the write value to the WI bit is 0. This bit is read as 1. Before setting the
WE or SEG bit, the WI bit must be set to 0.

#### 20.2.3 ELSRn:Event Link Setting Register n (n = 0 to 52)

Base address: ELC = 0x4020_1000
ELC_NS = 0x5020_1000
Offset address: 0x020 + 0x004 × n
Bit position: 15 14 13 12 11 10 9 8 7 6 5 4 3 2 1 0

| — | — | — | — | — | — | ELS[9:0] |
|---|---|---|---|---|---|---|

Bit field:
Value after reset: 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0

| Bit | Symbol | Function | R/W |
|---|---|---|---|
| 9:0 | ELS[9:0] | Event Link Select<br>0x000: Event output disabled for the associated peripheral module<br>0x001: Number setting for the event signal to be linked ⋮<br>0x1F8: Number setting for the event signal to be linked Others: Settings prohibited | R/W |
| 15:10 | — | These bits are read as 0. The write value should be 0. | R/W |

Note: P-TYPE-3
Note: This register has different secure access permission depending on the setting of Trusted Event Route Control Register (TEVTRCR).
If the security attribution is configured as Secure,
● Secure access is allowed.
● Non-secure write access is ignored and Non-secure read access is read as 0, TrustZone access error is generated.
If the security attribution is configured as Non-secure and the trusted event route is disabled,
● Secure write access is ignored and Secure read access is read as 0, TrustZone access error is generated.
● Non-secure access is allowed.
If the security attribution is configured as Non-secure and the trusted event route is enabled,
● Secure access is allowed.
● Non-secure write access is ignored and Non-secure read access is allowed.
● TrustZone access error is not generated.
The ELSRn register specifies an event signal to be linked to each peripheral module. Table 20.2 shows the association
between the ELSRn register and the peripheral modules. Table 20.3 shows the association between the event signal names
set in the ELSRn register and the signal numbers.

| Table 20.2 Association between the ELSRn registers and peripheral functions (1 of 2) |  |  |
|---|---|---|
| Register name | Peripheral function (module) | Event name |
| ELSR0 | GPT (A) | ELC_GPTA |
| ELSR1 | GPT (B) | ELC_GPTB |
| ELSR2 | GPT (C) | ELC_GPTC |
| ELSR3 | GPT (D) | ELC_GPTD |
| ELSR4 | GPT (E) | ELC_GPTE |
| ELSR5 | GPT (F) | ELC_GPTF |
| ELSR6 | GPT (G) | ELC_GPTG |
| ELSR7 | GPT (H) | ELC_GPTH |

[page 831]

| Table 20.2 Association between the ELSRn registers and peripheral functions (2 of 2) |  |  |
|---|---|---|
| Register name | Peripheral function (module) | Event name |
| ELSR12 | DAC12 channel 0 | ELC_DA0 |
| ELSR13 | DAC12 channel 1 | ELC_DA1 |
| ELSR14 | PORT1 | ELC_PORT1 |
| ELSR15 | PORT2 | ELC_PORT2 |
| ELSR16 | PORT3 | ELC_PORT3 |
| ELSR17 | PORT4 | ELC_PORT4 |
| ELSR19 | ADC16HA0 | ELC_HAD00 |
| ELSR20 | ADC16HB0 | ELC_HAD01 |
| ELSR21 | ADC16HC0 | ELC_HAD02 |
| ELSR22 | ADC16HA1 | ELC_HAD10 |
| ELSR23 | ADC16HB1 | ELC_HAD11 |
| ELSR24 | ADC16HC1 | ELC_HAD12 |
| ELSR25 | ADC16HA2 | ELC_HAD20 |
| ELSR26 | ADC16HB2 | ELC_HAD21 |
| ELSR27 | ADC16HC2 | ELC_HAD22 |
| ELSR30 | I3C | ELC_I3C |
| ELSR31 | ESWM | ELC_GPTP0 |
| ELSR32 | ESWM | ELC_GPTP1 |

[page 832]

| Table 20.3 Association between event signal names set in ELSRn.ELS[9:0] bits and signal numbers (1 of 9) |  |  |  |
|---|---|---|---|
| Event number | Interrupt request source | Name | Description |
| 0x001 | Port | PORT_IRQ0*1 | External pin interrupt 0 |
| 0x002 |  | PORT_IRQ1*1 | External pin interrupt 1 |
| 0x003 |  | PORT_IRQ2*1 | External pin interrupt 2 |
| 0x004 |  | PORT_IRQ3*1 | External pin interrupt 3 |
| 0x005 |  | PORT_IRQ4*1 | External pin interrupt 4 |
| 0x006 |  | PORT_IRQ5*1 | External pin interrupt 5 |
| 0x007 |  | PORT_IRQ6*1 | External pin interrupt 6 |
| 0x008 |  | PORT_IRQ7*1 | External pin interrupt 7 |
| 0x009 |  | PORT_IRQ8*1 | External pin interrupt 8 |
| 0x00A |  | PORT_IRQ9*1 | External pin interrupt 9 |
| 0x00B |  | PORT_IRQ10*1 | External pin interrupt 10 |
| 0x00C |  | PORT_IRQ11*1 | External pin interrupt 11 |
| 0x00D |  | PORT_IRQ12*1 | External pin interrupt 12 |
| 0x00E |  | PORT_IRQ13*1 | External pin interrupt 13 |
| 0x00F |  | PORT_IRQ14*1 | External pin interrupt 14 |
| 0x010 |  | PORT_IRQ15*1 | External pin interrupt 15 |
| 0x011 |  | PORT_IRQ16*1 | External pin interrupt 16 |
| 0x012 |  | PORT_IRQ17*1 | External pin interrupt 17 |
| 0x013 |  | PORT_IRQ18*1 | External pin interrupt 18 |
| 0x014 |  | PORT_IRQ19*1 | External pin interrupt 19 |
| 0x015 |  | PORT_IRQ20*1 | External pin interrupt 20 |
| 0x016 |  | PORT_IRQ21*1 | External pin interrupt 21 |
| 0x017 |  | PORT_IRQ22*1 | External pin interrupt 22 |
| 0x018 |  | PORT_IRQ23*1 | External pin interrupt 23 |
| 0x019 |  | PORT_IRQ24*1 | External pin interrupt 24 |
| 0x01A |  | PORT_IRQ25*1 | External pin interrupt 25 |
| 0x01B |  | PORT_IRQ26*1 | External pin interrupt 26 |
| 0x01C |  | PORT_IRQ27*1 | External pin interrupt 27 |
| 0x01D |  | PORT_IRQ28*1 | External pin interrupt 28 |
| 0x01E |  | PORT_IRQ29*1 | External pin interrupt 29 |
| 0x01F |  | PORT_IRQ30*1 | External pin interrupt 30 |
| 0x020 |  | PORT_IRQ31*1 | External pin interrupt 31 |

[page 833]

| Table 20.3 Association between event signal names set in ELSRn.ELS[9:0] bits and signal numbers (2 of 9) |  |  |  |
|---|---|---|---|
| Event number | Interrupt request source | Name | Description |
| 0x040 | DMAC0 | DMAC00_INT | DMAC0 transfer end 0 |
| 0x041 |  | DMAC01_INT | DMAC0 transfer end 1 |
| 0x042 |  | DMAC02_INT | DMAC0 transfer end 2 |
| 0x043 |  | DMAC03_INT | DMAC0 transfer end 3 |
| 0x044 |  | DMAC04_INT | DMAC0 transfer end 4 |
| 0x045 |  | DMAC05_INT | DMAC0 transfer end 5 |
| 0x046 |  | DMAC06_INT | DMAC0 transfer end 6 |
| 0x047 |  | DMAC07_INT | DMAC0 transfer end 7 |
| 0x048 | DMAC1 | DMAC10_INT | DMAC1 transfer end 0 |
| 0x049 |  | DMAC11_INT | DMAC1 transfer end 1 |
| 0x04A |  | DMAC12_INT | DMAC1 transfer end 2 |
| 0x04B |  | DMAC13_INT | DMAC1 transfer end 3 |
| 0x04C |  | DMAC14_INT | DMAC1 transfer end 4 |
| 0x04D |  | DMAC15_INT | DMAC1 transfer end 5 |
| 0x04E |  | DMAC16_INT | DMAC1 transfer end 6 |
| 0x04F |  | DMAC17_INT | DMAC1 transfer end 7 |
| 0x052 | DTC0 | DTC0_DTCEND | DTC0 transfer end |
| 0x055 | DTC1 | DTC1_DTCEND | DTC1 transfer end |
| 0x070 | PVD | PVD_PVD1 | Voltage monitor 1 interrupt |
| 0x071 |  | PVD_PVD2 | Voltage monitor 2 interrupt |
| 0x076 | MOSC | MOSC_STOP | Mail Clock oscillation stop |
| 0x080 | ULPT0 | ULPT0_ULPTI | Underflow |
| 0x081 |  | ULPT0_ULPTCMAI | Compare match A |
| 0x082 |  | ULPT0_ULPTCMBI | Compare match B |
| 0x083 | ULPT1 | ULPT1_ULPTI | Underflow |
| 0x084 |  | ULPT1_ULPTCMAI | Compare match A |
| 0x085 |  | ULPT1_ULPTCMBI | Compare match B |
| 0x086 | AGT0 | AGT0_AGTI | AGT interrupt |
| 0x087 |  | AGT0_AGTCMAI | Compare match A |
| 0x088 |  | AGT0_AGTCMBI | Compare match B |
| 0x089 | AGT1 | AGT1_AGTI | AGT interrupt |
| 0x08A |  | AGT1_AGTCMAI | Compare match A |
| 0x08B |  | AGT1_AGTCMBI | Compare match B |
| 0x092 | IWDT | IWDT_NMIUNDF | IWDT underflow |
| 0x093 | WDT | WDT0_NMIUNDF | WDT underflow |
| 0x094 |  | WDT1_NMIUNDF | WDT underflow |
| 0x096 | RTC | RTC_PRD | Periodic interrupt |
| 0x09C | IIC0 | IIC0_RXI | Receive data full |
| 0x09D |  | IIC0_TXI | Transmit data empty |
| 0x09E |  | IIC0_TEI | Transmit end |
| 0x09F |  | IIC0_EEI | Transfer error |

[page 834]

| Table 20.3 Association between event signal names set in ELSRn.ELS[9:0] bits and signal numbers (3 of 9) |  |  |  |
|---|---|---|---|
| Event number | Interrupt request source | Name | Description |
| 0x0A1 | IIC1 | IIC1_RXI | Receive data full |
| 0x0A2 |  | IIC1_TXI | Transmit data empty |
| 0x0A3 |  | IIC1_TEI | Transmit end |
| 0x0A4 |  | IIC1_EEI | Transfer error |
| 0x0A6 | IIC2 | IIC2_RXI | Receive data full |
| 0x0A7 |  | IIC2_TXI | Transmit data empty |
| 0x0A8 |  | IIC2_TEI | Transmit end |
| 0x0A9 |  | IIC2_EEI | Transfer error |
| 0x0C6 | ACMPHS | ACMP_HS0*1 | Comparator interrupt 0 |
| 0x0C7 |  | ACMP_HS1*1 | Comparator interrupt 1 |
| 0x0C8 |  | ACMP_HS2*1 | Comparator interrupt 2 |
| 0x0C9 |  | ACMP_HS3*1 | Comparator interrupt 3 |
| 0x0CC | ELC | ELC_SWEVT0 | Software event 0 |
| 0x0CD |  | ELC_SWEVT1 | Software event 1 |
| 0x0CE |  | ELC_SWEVT2 | Software event 2 |
| 0x0CF |  | ELC_SWEVT3 | Software event 3 |
| 0x0D0 | I/O Port | IOPORT_GROUP1 | Port 1 event |
| 0x0D1 |  | IOPORT_GROUP2 | Port 2 event |
| 0x0D2 |  | IOPORT_GROUP3 | Port 3 event |
| 0x0D3 |  | IOPORT_GROUP4 | Port 4 event |
| 0x180 | GPT | GPT_UVWEDGE | UVW edge event |
| 0x181 | GPT0 | GPT0_CCMPA | Compare match A |
| 0x182 |  | GPT0_CCMPB | Compare match B |
| 0x183 |  | GPT0_CMPC | Compare match C |
| 0x184 |  | GPT0_CMPD | Compare match D |
| 0x185 |  | GPT0_CMPE | Compare match E |
| 0x186 |  | GPT0_CMPF | Compare match F |
| 0x187 |  | GPT0_OVF | Overflow |
| 0x188 |  | GPT0_UDF | Underflow |
| 0x189 |  | GPT0_PC | Cycle count function end |
| 0x18A | GPT1 | GPT1_CCMPA | Compare match A |
| 0x18B |  | GPT1_CCMPB | Compare match B |
| 0x18C |  | GPT1_CMPC | Compare match C |
| 0x18D |  | GPT1_CMPD | Compare match D |
| 0x18E |  | GPT1_CMPE | Compare match E |
| 0x18F |  | GPT1_CMPF | Compare match F |
| 0x190 |  | GPT1_OVF | Overflow |
| 0x191 |  | GPT1_UDF | Underflow |
| 0x192 |  | GPT1_PC | Cycle count function end |

[page 835]

| Table 20.3 Association between event signal names set in ELSRn.ELS[9:0] bits and signal numbers (4 of 9) |  |  |  |
|---|---|---|---|
| Event number | Interrupt request source | Name | Description |
| 0x193 | GPT2 | GPT2_CCMPA | Compare match A |
| 0x194 |  | GPT2_CCMPB | Compare match B |
| 0x195 |  | GPT2_CMPC | Compare match C |
| 0x196 |  | GPT2_CMPD | Compare match D |
| 0x197 |  | GPT2_CMPE | Compare match E |
| 0x198 |  | GPT2_CMPF | Compare match F |
| 0x199 |  | GPT2_OVF | Overflow |
| 0x19A |  | GPT2_UDF | Underflow |
| 0x19B |  | GPT2_PC | Cycle count function end |
| 0x19C | GPT3 | GPT3_CCMPA | Compare match A |
| 0x19D |  | GPT3_CCMPB | Compare match B |
| 0x19E |  | GPT3_CMPC | Compare match C |
| 0x19F |  | GPT3_CMPD | Compare match D |
| 0x1A0 |  | GPT3_CMPE | Compare match E |
| 0x1A1 |  | GPT3_CMPF | Compare match F |
| 0x1A2 |  | GPT3_OVF | Overflow |
| 0x1A3 |  | GPT3_UDF | Underflow |
| 0x1A4 |  | GPT3_PC | Cycle count function end |
| 0x1A5 | GPT4 | GPT4_CCMPA | Compare match A |
| 0x1A6 |  | GPT4_CCMPB | Compare match B |
| 0x1A7 |  | GPT4_CMPC | Compare match C |
| 0x1A8 |  | GPT4_CMPD | Compare match D |
| 0x1A9 |  | GPT4_CMPE | Compare match E |
| 0x1AA |  | GPT4_CMPF | Compare match F |
| 0x1AB |  | GPT4_OVF | Overflow |
| 0x1AC |  | GPT4_UDF | Underflow |
| 0x1AE | GPT5 | GPT5_CCMPA | Compare match A |
| 0x1AF |  | GPT5_CCMPB | Compare match B |
| 0x1B0 |  | GPT5_CMPC | Compare match C |
| 0x1B1 |  | GPT5_CMPD | Compare match D |
| 0x1B2 |  | GPT5_CMPE | Compare match E |
| 0x1B3 |  | GPT5_CMPF | Compare match F |
| 0x1B4 |  | GPT5_OVF | Overflow |
| 0x1B5 |  | GPT5_UDF | Underflow |
| 0x1B7 | GPT6 | GPT6_CCMPA | Compare match A |
| 0x1B8 |  | GPT6_CCMPB | Compare match B |
| 0x1B9 |  | GPT6_CMPC | Compare match C |
| 0x1BA |  | GPT6_CMPD | Compare match D |
| 0x1BB |  | GPT6_CMPE | Compare match E |
| 0x1BC |  | GPT6_CMPF | Compare match F |
| 0x1BD |  | GPT6_OVF | Overflow |
| 0x1BE |  | GPT6_UDF | Underflow |

[page 836]

| Table 20.3 Association between event signal names set in ELSRn.ELS[9:0] bits and signal numbers (5 of 9) |  |  |  |
|---|---|---|---|
| Event number | Interrupt request source | Name | Description |
| 0x1C0 | GPT7 | GPT7_CCMPA | Compare match A |
| 0x1C1 |  | GPT7_CCMPB | Compare match B |
| 0x1C2 |  | GPT7_CMPC | Compare match C |
| 0x1C3 |  | GPT7_CMPD | Compare match D |
| 0x1C4 |  | GPT7_CMPE | Compare match E |
| 0x1C5 |  | GPT7_CMPF | Compare match F |
| 0x1C6 |  | GPT7_OVF | Overflow |
| 0x1C7 |  | GPT7_UDF | Underflow |
| 0x1C9 | GPT8 | GPT8_CCMPA | Compare match A |
| 0x1CA |  | GPT8_CCMPB | Compare match B |
| 0x1CB |  | GPT8_CMPC | Compare match C |
| 0x1CC |  | GPT8_CMPD | Compare match D |
| 0x1CD |  | GPT8_CMPE | Compare match E |
| 0x1CE |  | GPT8_CMPF | Compare match F |
| 0x1CF |  | GPT8_OVF | Overflow |
| 0x1D0 |  | GPT8_UDF | Underflow |
| 0x1D2 | GPT9 | GPT9_CCMPA | Compare match A |
| 0x1D3 |  | GPT9_CCMPB | Compare match B |
| 0x1D4 |  | GPT9_CMPC | Compare match C |
| 0x1D5 |  | GPT9_CMPD | Compare match D |
| 0x1D6 |  | GPT9_CMPE | Compare match E |
| 0x1D7 |  | GPT9_CMPF | Compare match F |
| 0x1D8 |  | GPT9_OVF | Overflow |
| 0x1D9 |  | GPT9_UDF | Underflow |
| 0x1DB | GPT10 | GPT10_CCMPA | Compare match A |
| 0x1DC |  | GPT10_CCMPB | Compare match B |
| 0x1DD |  | GPT10_CMPC | Compare match C |
| 0x1DE |  | GPT10_CMPD | Compare match D |
| 0x1DF |  | GPT10_CMPE | Compare match E |
| 0x1E0 |  | GPT10_CMPF | Compare match F |
| 0x1E1 |  | GPT10_OVF | Overflow |
| 0x1E2 |  | GPT10_UDF | Underflow |
| 0x1E3 |  | GPT10_PC | Cycle count function end |
| 0x1E4 | GPT11 | GPT11_CCMPA | Compare match A |
| 0x1E5 |  | GPT11_CCMPB | Compare match B |
| 0x1E6 |  | GPT11_CMPC | Compare match C |
| 0x1E7 |  | GPT11_CMPD | Compare match D |
| 0x1E8 |  | GPT11_CMPE | Compare match E |
| 0x1E9 |  | GPT11_CMPF | Compare match F |
| 0x1EA |  | GPT11_OVF | Overflow |
| 0x1EB |  | GPT11_UDF | Underflow |
| 0x1EC |  | GPT11_PC | Cycle count function end |

[page 837]

| Table 20.3 Association between event signal names set in ELSRn.ELS[9:0] bits and signal numbers (6 of 9) |  |  |  |
|---|---|---|---|
| Event number | Interrupt request source | Name | Description |
| 0x1ED | GPT12 | GPT12_CCMPA | Compare match A |
| 0x1EE |  | GPT12_CCMPB | Compare match B |
| 0x1EF |  | GPT12_CMPC | Compare match C |
| 0x1F0 |  | GPT12_CMPD | Compare match D |
| 0x1F1 |  | GPT12_CMPE | Compare match E |
| 0x1F2 |  | GPT12_CMPF | Compare match F |
| 0x1F3 |  | GPT12_OVF | Overflow |
| 0x1F4 |  | GPT12_UDF | Underflow |
| 0x1F5 |  | GPT12_PC | Cycle count function end |
| 0x1F6 | GPT13 | GPT13_CCMPA | Compare match A |
| 0x1F7 |  | GPT13_CCMPB | Compare match B |
| 0x1F8 |  | GPT13_CMPC | Compare match C |
| 0x1F9 |  | GPT13_CMPD | Compare match D |
| 0x1FA |  | GPT13_CMPE | Compare match E |
| 0x1FB |  | GPT13_CMPF | Compare match F |
| 0x1FC |  | GPT13_OVF | Overflow |
| 0x1FD |  | GPT13_UDF | Underflow |
| 0x1FE |  | GPT13_PC | Cycle count function end |
| 0x2B4 | ESWM | GPTP_PTPOUT0 | PTP Pulse Out 0 |
| 0x2B5 |  | GPTP_PTPOUT1 | PTP Pulse Out 1 |
| 0x2B6 |  | GPTP_PTPOUT2 | PTP Pulse Out 2 |
| 0x2B7 |  | GPTP_PTPOUT3 | PTP Pulse Out 3 |
| 0x2B8 |  | GPTP_MATCH0 | Media Clock Recovery Match 0 |
| 0x2B9 |  | GPTP_MATCH1 | Media Clock Recovery Match 1 |
| 0x2C4 | SCI0 | SCI0_RXI*2 | Receive data full |
| 0x2C5 |  | SCI0_TXI*2 | Transmit data empty |
| 0x2C6 |  | SCI0_TEI*2 | Transmit end |
| 0x2C7 |  | SCI0_ERI | Receive error |
| 0x2C8 |  | SCI0_AED | Effective edge detection |
| 0x2CA |  | SCI0_AM | Address match event |
| 0x2CB | SCI1 | SCI1_RXI*2 | Receive data full |
| 0x2CC |  | SCI1_TXI*2 | Transmit data empty |
| 0x2CD |  | SCI1_TEI*2 | Transmit end |
| 0x2CE |  | SCI1_ERI | Receive error |
| 0x2CF |  | SCI1_AED | Effective edge detection |
| 0x2D1 |  | SCI1_AM | Address match event |

[page 838]

| Table 20.3 Association between event signal names set in ELSRn.ELS[9:0] bits and signal numbers (7 of 9) |  |  |  |
|---|---|---|---|
| Event number | Interrupt request source | Name | Description |
| 0x2D2 | SCI2 | SCI2_RXI*2 | Receive data full |
| 0x2D3 |  | SCI2_TXI*2 | Transmit data empty |
| 0x2D4 |  | SCI2_TEI*2 | Transmit end |
| 0x2D5 |  | SCI2_ERI | Receive error |
| 0x2D6 |  | SCI2_AED | Effective edge detection |
| 0x2D8 |  | SCI2_AM | Address match event |
| 0x2D9 | SCI3 | SCI3_RXI*2 | Receive data full |
| 0x2DA |  | SCI3_TXI*2 | Transmit data empty |
| 0x2DB |  | SCI3_TEI*2 | Transmit end |
| 0x2DC |  | SCI3_ERI | Receive error |
| 0x2DD |  | SCI3_AED | Effective edge detection |
| 0x2DF |  | SCI3_AM | Address match event |
| 0x2E0 | SCI4 | SCI4_RXI*2 | Receive data full |
| 0x2E1 |  | SCI4_TXI*2 | Transmit data empty |
| 0x2E2 |  | SCI4_TEI*2 | Transmit end |
| 0x2E3 |  | SCI4_ERI | Receive error |
| 0x2E4 |  | SCI4_AED | Effective edge detection |
| 0x2E6 |  | SCI4_AM | Address match event |
| 0x2E7 | SCI5 | SCI5_RXI*2 | Receive data full |
| 0x2E8 |  | SCI5_TXI*2 | Transmit data empty |
| 0x2E9 |  | SCI5_TEI*2 | Transmit end |
| 0x2EA |  | SCI5_ERI | Receive error |
| 0x2EB |  | SCI5_AED | Effective edge detection |
| 0x2ED |  | SCI5_AM | Address match event |
| 0x2EE | SCI6 | SCI6_RXI*2 | Receive data full |
| 0x2EF |  | SCI6_TXI*2 | Transmit data empty |
| 0x2F0 |  | SCI6_TEI*2 | Transmit end |
| 0x2F1 |  | SCI6_ERI | Receive error |
| 0x2F2 |  | SCI6_AED | Effective edge detection |
| 0x2F4 |  | SCI6_AM | Address match event |
| 0x2F5 | SCI7 | SCI7_RXI*2 | Receive data full |
| 0x2F6 |  | SCI7_TXI*2 | Transmit data empty |
| 0x2F7 |  | SCI7_TEI*2 | Transmit end |
| 0x2F8 |  | SCI7_ERI | Receive error |
| 0x2F9 |  | SCI7_AED | Effective edge detection |
| 0x2FB |  | SCI7_AM | Address match event |

[page 839]

| Table 20.3 Association between event signal names set in ELSRn.ELS[9:0] bits and signal numbers (8 of 9) |  |  |  |
|---|---|---|---|
| Event number | Interrupt request source | Name | Description |
| 0x2FC | SCI8 | SCI8_RXI*2 | Receive data full |
| 0x2FD |  | SCI8_TXI*2 | Transmit data empty |
| 0x2FE |  | SCI8_TEI*2 | Transmit end |
| 0x2FF |  | SCI8_ERI | Receive error |
| 0x300 |  | SCI8_AED | Effective edge detection |
| 0x302 |  | SCI8_AM | Address match event |
| 0x303 | SCI9 | SCI9_RXI*2 | Receive data full |
| 0x304 |  | SCI9_TXI*2 | Transmit data empty |
| 0x305 |  | SCI9_TEI*2 | Transmit end |
| 0x306 |  | SCI9_ERI | Receive error |
| 0x307 |  | SCI9_AED | Effective edge detection |
| 0x309 |  | SCI9_AM | Address match event |
| 0x318 | SPI0 | SPI0_SPRI | Receive buffer full |
| 0x319 |  | SPI0_SPTI | Transmit buffer empty |
| 0x31A |  | SPI0_SPII | Idle |
| 0x31B |  | SPI0_SPEI | Error |
| 0x31C |  | SPI0_SPCEND | Communication complete event |
| 0x31D | SPI1 | SPI1_SPRI | Receive buffer full |
| 0x31E |  | SPI1_SPTI | Transmit buffer empty |
| 0x31F |  | SPI1_SPII | Idle |
| 0x320 |  | SPI1_SPEI | Error |
| 0x321 |  | SPI1_SPCEND | Transmission complete event |
| 0x33A | I3C | I3C_RESP | Normal Response queue full |
| 0x33B |  | I3C_CMD | Normal Command queue empty |
| 0x33C |  | I3C_IBI | Normal IBI Queue Empty/Full |
| 0x33D |  | I3C_RX | Normal Rx Data buffer full |
| 0x33E |  | I3C_TX | Normal Tx Data buffer empty |
| 0x33F |  | I3C_RCV | Normal Receive Status queue full |
| 0x340 |  | I3C_HRESP | High priority response queue full |
| 0x341 |  | I3C_HCMD | High priority command queue empty |
| 0x342 |  | I3C_HRX | High priority Rx Data buffer full |
| 0x343 |  | I3C_HTX | High priority Tx Data buffer empty |
| 0x344 |  | I3C_TEND | Transmit end |
| 0x345 |  | I3C_EEI | Transfer error or event occurrence |
| 0x346 |  | I3C_STEV | Synchronous Timing |
| 0x347 |  | I3C_MREFOVF | MREF Counter Overflow |
| 0x348 |  | I3C_MREFCPT | MREF Capture |
| 0x349 |  | I3C_AMEV | Additional Master-initiated bus Event |

[page 840]

| Table 20.3 Association between event signal names set in ELSRn.ELS[9:0] bits and signal numbers (9 of 9) |  |  |  |
|---|---|---|---|
| Event number | Interrupt request source | Name | Description |
| 0x34D | ADC16H | ADC_ADI0 | A/D scan end interrupt for group 0 |
| 0x34E |  | ADC_ADI1 | A/D scan end interrupt for group 1 |
| 0x34F |  | ADC_ADI2 | A/D scan end interrupt for group 2 |
| 0x350 |  | ADC_ADI3 | A/D scan end interrupt for group 3 |
| 0x351 |  | ADC_ADI4 | A/D scan end interrupt for group 4 |
| 0x352 |  | ADC_ADI5 | A/D scan end interrupt for group 5 |
| 0x353 |  | ADC_ADI6 | A/D scan end interrupt for group 6 |
| 0x354 |  | ADC_ADI7 | A/D scan end interrupt for group 7 |
| 0x355 |  | ADC_ADI8 | A/D scan end interrupt for group 8 |
| 0x361 |  | ADC_CCMPM0 | Composite condition compare 0 match |
| 0x362 |  | ADC_CCMPUM0 | Composite condition compare 0 mismatch |
| 0x369 |  | ADC_CCMPM1 | Composite condition compare 1 match |
| 0x36A |  | ADC_CCMPUM1 | Composite condition compare 1 mismatch |
| 0x36F | DOC | DOC_DOPCI | Data operation circuit interrupt |

Note 1. Only pulse (edge detection) is supported.
Note 2. This event is not supported in FIFO mode.

#### 20.2.4 ELCSARA : Event Link Controller Security Attribution Register A

Base ELC = 0x4020_1000
address: ELC_NS = 0x5020_1000
Offset
0x100
address:
Bit position: 31 30 29 28 27 26 25 24 23 22 21 20 19 18 17 16

| — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

Bit field:
Value after reset: 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
Bit position: 15 14 13 12 11 10 9 8 7 6 5 4 3 2 1 0

| — | — | — | — | — | — | — | — | — | — | — | ELSEGR3 | ELSEGR2 | ELSEGR1 | ELSEGR0 | ELCR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

Bit field:
Value after reset: 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0

| Bit | Symbol | Function | R/W |
|---|---|---|---|
| 0 | ELCR | Event Link Controller Register Security Attribution Target register: ELCR<br>0: Secure<br>1: Non-secure | R/W |
| 1 | ELSEGR0 | Event Link Software Event Generation Register 0 Security Attribution<br>0: Secure<br>1: Non-secure | R/W |
| 2 | ELSEGR1 | Event Link Software Event Generation Register 1 Security Attribution<br>0: Secure<br>1: Non-secure | R/W |
| 3 | ELSEGR2 | Event Link Software Event Generation Register 2 Security Attribution<br>0: Secure<br>1: Non-secure | R/W |
| 4 | ELSEGR3 | Event Link Software Event Generation Register 3 Security Attribution<br>0: Secure<br>1: Non-secure | R/W |

[page 841]

| Bit | Symbol | Function | R/W |
|---|---|---|---|
| 31:5 | — | These bits are read as 0. The write value should be 0. | R/W |

Note: S-TYPE-1, P-TYPE-1
Note: This register is write-protected by PRCR_S register.
This register specifies the security attribution for the ELCR, ELSEGR0, ELSEGR1, ELSEGR2, and ELSEGR3 registers.

#### 20.2.5 ELCSARB : Event Link Controller Security Attribution Register B

Base address: ELC = 0x4020_1000
ELC_NS = 0x5020_1000
Offset address: 0x104
Bit position: 31 30 29 28 27 26 25 24 23 22 21 20 19 18 17 16

| ELSR[31:30] | — | — | ELSR[27:19] | — | ELSR[17:16] |
|---|---|---|---|---|---|

Bit field:
Value after reset: 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
Bit position: 15 14 13 12 11 10 9 8 7 6 5 4 3 2 1 0

| ELSR[15:12] | — | — | — | — | ELSR[7:0] |
|---|---|---|---|---|---|

Bit field:
Value after reset: 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0

| Bit | Symbol | Function | R/W |
|---|---|---|---|
| 7:0 | ELSR7 to ELSR0 | Event Link Setting Register n Security Attribution Target register: ELSRn (n = 0 to 7)<br>0: Secure<br>1: Non-secure | R/W |
| 11:8 | — | These bits are read as 0. The write value should be 0. | R/W |
| 17:12 | ELSR17 to ELSR12 | Event Link Setting Register n Security Attribution Target register: ELSRn (n = 12 to 17)<br>0: Secure<br>1: Non-secure | R/W |
| 18 | — | This bit is read as 0. The write value should be 0. | R/W |
| 27:19 | ELSR27 to ELSR19 | Event Link Setting Register n Security Attribution Target register: ELSRn (n = 19 to 27)<br>0: Secure<br>1: Non-secure | R/W |
| 29:28 | — | These bits are read as 0. The write value should be 0. | R/W |
| 31:30 | ELSR31 to ELSR30 | Event Link Setting Register n Security Attribution Target register: ELSRn (n = 30, 31)<br>0: Secure<br>1: Non-secure | R/W |

Note: S-TYPE-1, P-TYPE-1
Note: This register is write-protected by PRCR_S register.
This register specifies the security attribution for the Register ELSRn (n = 0 to 7, 12 to 17, 19 to 27, 30, 31).

[page 842]

#### 20.2.6 ELCSARC : Event Link Controller Security Attribution Register C

Base address: ELC = 0x4020_1000
ELC_NS = 0x5020_1000
Offset address: 0x108
Bit position: 31 30 29 28 27 26 25 24 23 22 21 20 19 18 17 16

| — | — | — | — | — | — | — | — | — | — | — | ELSR[52:48] |
|---|---|---|---|---|---|---|---|---|---|---|---|

Bit field:
Value after reset: 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
Bit position: 15 14 13 12 11 10 9 8 7 6 5 4 3 2 1 0
Bit field: ELSR[47:32]
Value after reset: 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0

| Bit | Symbol | Function | R/W |
|---|---|---|---|
| 20:0 | ELSR[52:32] | Event Link Setting Register n Security Attribution Target register: ELSRn (n = 32 to 52)<br>0: Secure<br>1: Non-secure | R/W |
| 31:21 | — | These bits are read as 0. The write value should be 0. | R/W |

Note: S-TYPE-1, P-TYPE-1
Note: This register is write-protected by PRCR_S register.
This register specifies the security attribution for the Register ELSRn (n = 32 to 52).

#### 20.2.7 ELCPARA : Event Link Controller Privilege Attribution Register A

Base address: ELC = 0x4020_1000
ELC_NS = 0x5020_1000
Offset address: 0x110
Bit position: 31 30 29 28 27 26 25 24 23 22 21 20 19 18 17 16

| — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

Bit field:
Value after reset: 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1
Bit position: 15 14 13 12 11 10 9 8 7 6 5 4 3 2 1 0

| — | — | — | — | — | — | — | — | — | — | — | ELSEGR3 | ELSEGR2 | ELSEGR1 | ELSEGR0 | ELCR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

Bit field:
Value after reset: 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1

| Bit | Symbol | Function | R/W |
|---|---|---|---|
| 0 | ELCR | Event Link Controller Register Privilege Attribution Target register: ELCR<br>0: Privileged<br>1: Unprivileged | R/W |
| 1 | ELSEGR0 | Event Link Software Event Generation Register 0 Privilege Attribution Target register: ELSEGR0<br>0: Privileged<br>1: Unprivileged | R/W |
| 2 | ELSEGR1 | Event Link Software Event Generation Register 1 Privilege Attribution Target register: ELSEGR1<br>0: Privileged<br>1: Unprivileged | R/W |

[page 843]

| Bit | Symbol | Function | R/W |
|---|---|---|---|
| 3 | ELSEGR2 | Event Link Software Event Generation Register 2 Privilege Attribution Target register: ELSEGR2<br>0: Privileged<br>1: Unprivileged | R/W |
| 4 | ELSEGR3 | Event Link Software Event Generation Register 3 Privilege Attribution Target register: ELSEGR3<br>0: Privileged<br>1: Unprivileged | R/W |
| 31:5 | — | These bits are read as 1. The write value should be 1. | R/W |

Note: S-TYPE-2, P-TYPE-1
Note: This register is write-protected by PRCR_S and PRCR_NS register.
This register specifies the privilege attribution for the Register ELCR, ELSEGR0, ELSEGR1, ELSEGR2, and ELSEGR3
registers.

#### 20.2.8 ELCPARB : Event Link Controller Privilege Attribution Register B

Base address: ELC = 0x4020_1000
ELC_NS = 0x5020_1000
Offset address: 0x114
Bit position: 31 30 29 28 27 26 25 24 23 22 21 20 19 18 17 16

| ELSR[31:30] | — | — | ELSR[27:19] | — | ELSR[17:16] |
|---|---|---|---|---|---|

Bit field:
Value after reset: 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1
Bit position: 15 14 13 12 11 10 9 8 7 6 5 4 3 2 1 0

| ELSR[15:12] | — | — | — | — | ELSR[7:0] |
|---|---|---|---|---|---|

Bit field:
Value after reset: 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1

| Bit | Symbol | Function | R/W |
|---|---|---|---|
| 7:0 | ELSR7 to ELSR0 | Event Link Setting Register n Privilege Attribution Target register: ELSRn (n = 0 to 7)<br>0: Privileged<br>1: Unprivileged | R/W |
| 11:8 | — | These bits are read as 1. The write value should be 1. | R/W |
| 17:12 | ELSR17 to ELSR12 | Event Link Setting Register n Privilege Attribution Target register: ELSRn (n = 12 to 17)<br>0: Privileged<br>1: Unprivileged | R/W |
| 18 | — | This bit is read as 1. The write value should be 1. | R/W |
| 27:19 | ELSR27 to ELSR19 | Event Link Setting Register n Privilege Attribution Target register: ELSRn (n = 19 to 27)<br>0: Privileged<br>1: Unprivileged | R/W |
| 29:28 | — | These bits are read as 1. The write value should be 1. | R/W |
| 31:30 | ELSR31 to ELSR30 | Event Link Setting Register n Privilege Attribution Target register: ELSRn (n = 30, 31)<br>0: Privileged<br>1: Unprivileged | R/W |

Note: S-TYPE-2, P-TYPE-1
Note: This register is write-protected by PRCR_S and PRCR_NS register.
This register specifies the privilege attribution for the Register ELSRn (n = 0 to 7, 12 to 17, 19 to 27, 30, 31) registers.

[page 844]

#### 20.2.9 ELCPARC : Event Link Controller Privilege Attribution Register C

Base address: ELC = 0x4020_1000
ELC_NS = 0x5020_1000
Offset address: 0x118
Bit position: 31 30 29 28 27 26 25 24 23 22 21 20 19 18 17 16

| — | — | — | — | — | — | — | — | — | — | — | ELSR[52:48] |
|---|---|---|---|---|---|---|---|---|---|---|---|

Bit field:
Value after reset: 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1
Bit position: 15 14 13 12 11 10 9 8 7 6 5 4 3 2 1 0
Bit field: ELSR[47:32]
Value after reset: 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1

| Bit | Symbol | Function | R/W |
|---|---|---|---|
| 20:0 | ELSR[52:32] | Event Link Setting Register n Privilege Attribution Target register: ELSRn (n = 32 to 52)<br>0: Privileged<br>1: Unprivileged | R/W |
| 31:21 | — | These bits are read as 1. The write value should be 1. | R/W |

Note: S-TYPE-2, P-TYPE-1
Note: This register is write-protected by PRCR_S and PRCR_NS register.
This register specifies the privilege attribution for the Register ELSRn (n = 32 to 52) registers.
