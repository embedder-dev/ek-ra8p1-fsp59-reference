# Stage 3: DAC0 → AN001 loopback

**Setup gate:** EK-RA8P1 v1 manual R20UT5309EG0104 Table 20: J19-5 (A4/P014/DA0) → 1 kΩ series → J19-1 (A0/P001/AN001), with nothing else driving/loading either pin. In the default board links, E1/E2 tie DAC `VREFL/VREFH` to GND/+3.3 V, E5/E6 do the same for ADC0 `VREFL0/VREFH0`, and E3/E4 supply analog power and ground. Confirm those links and the two generated analog pin settings before arming. Per RA8P1 HM §54.11.21, PORT0 must not be used for digital outputs during this fixture. The spec disables the board-default P013 (`IIC_SCL_PULLUP`); do not use I²C/I3C in this stage. The firmware checks PORT0 before opening ADC or DAC and never reconfigures or drives P001.

**Clock gate:** The XTAL boot profile gives PCLKA 12 MHz and leaves ADCCLK disabled. Select the following on the configurator's **Clocks** tab before applying/building `cpu0-analog.json`. e2 `config set --spec` sets stacks/pins/BSP properties, not Clocks-tab nodes:

| Clock node | Option |
|---|---|
| `board.clock.hoco.freq` | `board.clock.hoco.freq.48m` |
| `board.clock.clock.source` | `board.clock.clock.source.hoco` |
| `board.clock.pclka.div` | `board.clock.pclka.div.1` |
| `board.clock.adcclk.source` | `board.clock.adcclk.source.hoco` |
| `board.clock.adcclk.div` | `board.clock.adcclk.div.1` |

Leave SCICLK on XTAL for the console. Verify generated `BSP_CFG_CLOCK_SOURCE`, `BSP_CFG_HOCO_FREQUENCY`, `BSP_CFG_PCLKA_DIV`, `BSP_CFG_ADCCLK_SOURCE`, and `BSP_CFG_ADCCLK_DIV`; confirm `ADCCKCR.ADCCKSREQ=ADCCKSRDY=0` and stable HOCO. HM §§9.2.56, 54.2.1.3, 54.3.1 and Table 70.99: ADCCLK is gated while switching-ready is set, switching requires stable old/new sources and module stop + two ADC clocks when changing from a divided source, and ADC16H requires 25–60 MHz ADCLK with `PCLKA >= ADCLK`. The generated recipe gives PCLKA=ADCCLK=ADCLK=48 MHz and matching 5-cycle (104 ns) approximation times. There is no fixture-side clock change. Restore the stage-2 XTAL/PCLKA defaults and remove/revert the analog stack and pin changes before the separate stage-4 CGC fixture; the ADC stack is not legal on the original clocks.

**Oracle:** For the equal board references, DAC `D/4096 × VREFH` (HM §55.3) maps to ideal ADC unsigned 12-bit code `D` (HM Fig. 54.48). DAC limits at normal VREFH are 0.20 V to VREFH−0.20 V (HM Table 70.114), so use `384,1024,2048,3072,3712` rather than commands at the rails (about 0.309–2.991 V nominal). The ramp commands `384 + 104*i`, `i=0..32`. Dwell at least 30 ms after each command and retain four separately triggered raw ADC0/AN001 readings, their signed errors, min/max, and rounded mean. Every raw sample must be a 12-bit unsigned value and within ±82 codes (~2% full scale), and the ramp means must increase strictly. UART must show all 5 level and 33 ramp rows, summary `non_increasing=0`, and final `ANALOG PASS` after stop/close. Keep the clock line and generated pin/stack/clock evidence with the transcript. This is a functional check, not a voltage, settling-time, or accuracy measurement; the series resistor and concurrent DAC operation differ from the ADC electrical-characterization conditions.
