---
doc: RA8P1 Group User's Manual: Hardware (R01UH1064EJ0130, Rev.1.30)
section: 1.4 Function Comparison
pages: 79-80
---

[page 79]

### 1.4 Function Comparison

| Table 1.15 Function Comparison (1 of 2) |  |  |  |  |  |  |  |  |  |  |  |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Parts number |  | R7KA8P1AxxCAC | R7KA8P1BxxCAC | R7KA8P1JxxCAC | R7KA8P1KxxCAC | R7KA8P1AxxCAB | R7KA8P1BxxCAB | R7KA8P1JxxCAB | R7KA8P1KxxCAB | R7JA8P1JxxSAJ | R7JA8P1KxxSAJ |
| Pin count |  | 289 |  |  |  | 224 |  |  |  | 303 |  |
| Package |  | BGA |  |  |  |  |  |  |  |  |  |
| I/O Port |  | 208 | 199 | 208 | 199 | 149 | 142 | 149 | 142 | 195 | 186 |
| Code MRAM |  | 1 MB, 512 KB |  |  |  |  |  |  |  | 1 MB |  |
| CPU0 TCM |  | 256 KB |  |  |  |  |  |  |  |  |  |
| CPU1 TCM |  | No |  | 128 KB |  | No |  | 128 KB |  |  |  |
| CPU0 I/D Caches |  | 32 KB |  |  |  |  |  |  |  |  |  |
| CPU1 C/S Caches |  | No |  | 32 KB |  | No |  | 32 KB |  |  |  |
| SRAM |  | 1792 KB |  | 1664 KB |  | 1792 KB |  | 1664 KB |  |  |  |
| Flash |  | No |  |  |  |  |  |  |  | 8 MB, 4 MB |  |
| DMA | DTC | 1 |  | 2 |  | 1 |  | 2 |  |  |  |
|  | DMAC | 8 |  | 16 |  | 8 |  | 16 |  |  |  |
| BUS | External bus | 32-bit bus |  |  |  | 16-bit bus |  |  |  |  |  |
|  | SDRAM | 32-bit bus |  |  |  | 16-bit bus |  |  |  |  |  |
| System | CPU0 clock | 1 GHz (max.) |  |  |  |  |  |  |  |  |  |
|  | CPU1 clock | No |  | 250 MHz (max.) |  | No |  | 250 MHz (max.) |  |  |  |
|  | CPUs clock sources | MOSC, SOSC, HOCO, MOCO, PLL1P |  |  |  |  |  |  |  |  |  |
|  | CAC | Yes |  |  |  |  |  |  |  |  |  |
|  | WDT | 1 |  | 2 |  | 1 |  | 2 |  |  |  |
|  | IWDT | Yes |  |  |  |  |  |  |  |  |  |
|  | Backup register | 128 B |  |  |  |  |  |  |  |  |  |
| Communic ation | SCI | 10 |  |  |  | 9 |  |  |  | 10 |  |
|  | IIC | 3 |  |  |  |  |  |  |  |  |  |
|  | I3C | Yes |  |  |  |  |  |  |  |  |  |
|  | SPI | 2 |  |  |  |  |  |  |  |  |  |
|  | CANFD | 2 |  |  |  |  |  |  |  |  |  |
|  | USBFS | Yes |  |  |  |  |  |  |  |  |  |
|  | USBHS | Yes |  |  |  |  |  |  |  |  |  |
|  | OSPI | 2 |  |  |  | 1 |  |  |  | 2*2 |  |
|  | SSIE | 2 |  |  |  |  |  |  |  |  |  |
|  | SDHI/MMC | 2 |  |  |  |  |  |  |  |  |  |
|  | ESWM | MII, RMII, GMII, RGMII |  |  |  | MII, RMII, RGMII |  |  |  | MII, RMII, GMII, RGMII |  |
|  | PDMIF | Yes |  |  |  |  |  |  |  |  |  |

[page 80]

| Table 1.15 Function Comparison (2 of 2) |  |  |  |  |  |  |  |  |  |  |  |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Parts number |  | R7KA8P1AxxCAC | R7KA8P1BxxCAC | R7KA8P1JxxCAC | R7KA8P1KxxCAC | R7KA8P1AxxCAB | R7KA8P1BxxCAB | R7KA8P1JxxCAB | R7KA8P1KxxCAB | R7JA8P1JxxSAJ | R7JA8P1KxxSAJ |
| Timers | GPT32*1 | 14 |  |  |  |  |  |  |  |  |  |
|  | PDG | 4 |  |  |  |  |  |  |  |  |  |
|  | AGT*1 | 2 |  |  |  |  |  |  |  |  |  |
|  | ULPT*1 | 2 |  |  |  |  |  |  |  |  |  |
|  | RTC | Yes |  |  |  |  |  |  |  |  |  |
| Analog | ADC16H | Unit 0: 15, Unit 1: 15 |  |  |  | Unit 0: 7, Unit 1: 5 |  |  |  | Unit 0: 15, Unit 1: 15 |  |
|  | DAC12 | 2 |  |  |  |  |  |  |  |  |  |
|  | ACMPHS | 4 |  |  |  |  |  |  |  |  |  |
|  | TSN | Yes |  |  |  |  |  |  |  |  |  |
| HMI | GLCDC | RGB888 |  |  |  |  |  |  |  |  |  |
|  | DRW | Yes |  |  |  |  |  |  |  |  |  |
|  | MIPIDSI/CSI | No | Yes | No | Yes | No | Yes | No | Yes | No | Yes |
|  | VIN | No | Yes | No | Yes | No | Yes | No | Yes | No | Yes |
|  | CEU | Yes |  |  |  |  |  |  |  |  |  |
| Neural processin g | NPU | Yes |  |  |  |  |  |  |  |  |  |
| Data processin g | CRC | Yes |  |  |  |  |  |  |  |  |  |
|  | DOC | Yes |  |  |  |  |  |  |  |  |  |
| Event control | ELC | Yes |  |  |  |  |  |  |  |  |  |
| Security |  | RSIP-E50D, Decryption on-the-fly, Secure Debug, OTP, TrustZone, and Lifecycle management |  |  |  |  |  |  |  |  |  |

Note: The product name differs depending on the supported memory size. See section 1.3. Part Numbering.
Note: The maximum frequency varies by product group. See section 70.3.1. Frequency for details.
Note 1. Available pins depend on the Pin count, about details see section 1.7. Pin Lists.
Note 2. OSPI1 is connected to the serial Flash in the SiP product.
