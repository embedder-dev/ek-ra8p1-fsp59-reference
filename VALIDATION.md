# EK-RA8P1 on-target validation

The RA8P1 and EK-RA8P1 support in this repository (candidate r019) is finished: the packs build, generated projects build clean on GCC and LLVM, and the host tests pass. It has never run on a board. This round validates it on real hardware.

This brief replaces the hardware rules in MIGRATION.md and prompt.md. A board and instruments are now attached, and the operations below are authorized.

## Environment (already prepared)

- **e2 support area.** It is isolated: FSP 5.9.0 only, plus the r019 packs from `packs/r019/`, installed and verified. `$E2STUDIO` and the `embedder e2` commands already point at it. To check: `embedder e2 packs verify --fsp 5.9.0 --manifest packs/r019`. Don't reinstall or roll back packs unless a fix needs a new candidate.
- **Out of scope:** baseline verification. `reference/vendor/` and the baseline git archive are not in this repository.
- **Disk.** About 7 GB is free. Keep one project per core, delete build outputs you no longer need, and write scratch files only inside this workspace or `$TMPDIR`.

## Hardware

| Item | Details |
|---|---|
| Board | EK-RA8P1 v1, USB-powered |
| Debug probe | On-board J-Link OB, serial 001080841014, SWD. Devices `R7KA8P1KF_CPU0` (Cortex-M85) and `R7KA8P1KF_CPU1` (Cortex-M33) |
| Serial | J-Link virtual COM port `/dev/cu.usbmodem0010808410141` |
| Analog loopback | A4 / P014 / DAC0 (J19-5) → 1 kΩ → A0 / P001 / AN001 (J19-1) |
| Analog Discovery 3 | Serial 210415BE5124. Digital inputs connected to the J1 header pins below, common ground. Scope inputs are **not** connected to the board |

Pins wired to AD3 digital inputs: P514 (J1-1), P111 (J1-3), P806 (J1-9), P807 (J1-11), GND (J1-39). Which AD3 DIO line goes to which pin is not recorded. Establish it on the board first: toggle each pin from firmware, one at a time, and record which line moves.

AD3 rules:
- Use its digital lines as **inputs only**, for logic capture.
- Keep W1, W2, V+ and V−, and pattern and static-I/O outputs, **off**.
- No AD3 scope channel is on the loopback. ADC readings against DAC commands are a functional check, not an independent voltage measurement. Say so in the report.

## Tests, in order

Stop at the first failure, diagnose it and fix the owning source, then continue. A pass needs evidence: console output, register values, captures. Wiring that is present is not evidence.

1. **Probe and image.**
   - The J-Link sees the RA8P1. Read the device and core identity.
   - Confirm that each image you flash is the one you just built, by hash or build timestamp.
   - Know the reset and halt state before every flash.
2. **CPU0 boot and clocks.**
   - Flash a CPU0 image that prints over the virtual COM port. Choose the SCI channel from the board sources and the EK-RA8P1 skill.
   - Report the configured clocks (ICLK, PCLKs, MRAM clock), read back from the clock registers.
   - Check one timing independently: toggle a pin wired to the AD3 at a set period from a timer, and measure the period on the AD3. Report expected against measured.
3. **r_dac_b → r_adc_b loopback.**
   - Drive DAC0 with at least 5 levels across its range, plus a slow ramp. Sample AN001.
   - Report the commanded value, expected code, read code and error at each level.
   - Before enabling the DAC output, confirm from the board sources and the EK-RA8P1 documentation that A4 is P014 and A0 is P001. If you are unsure, ask.
   - Keep P001 an analog input throughout.
4. **r_cgc.** Exercise a clock change the driver supports, for example switching the system clock source and back. Show that the clocks and the UART stay correct afterwards.
5. **r_wdt.** Only if it is safe to do: show that refresh keeps the device running and that stopping refresh resets it. Then recover the board.
6. **r_mram.**
   - Erase, write, read back and verify in a scratch block that you reserve inside the code MRAM application area, away from the running image.
   - Name the exact address range in your plan; approving the plan approves that range.
   - Nothing outside it.
7. **CPU1 (optional).** Start CPU1 from CPU0 and show one sign of life, such as a shared-memory counter or a UART line.
8. **r_pdm (optional).** Capture from the on-board microphones and show plausible, non-constant data. Microphone signals are not wired to the AD3, so mark the audio content unverified.

## Boundaries

- **Flash only the normal code MRAM application area.** Do not write option-setting memory, OFS, the ID code, security or TrustZone boundaries, DLM state, or anything else that could lock the device.
- **No pin model changes.**
- **Source changes only for real defects found on hardware.** After each fix, re-run the affected host tests and generated builds, and list the fix in the report.
- **Don't push** anything.

## Report

Finish with one table. Rows: CPU0 BSP, CPU1 BSP, EK-RA8P1 board, r_cgc, r_dac_b, r_adc_b, r_wdt, r_mram, r_pdm. Columns: test run, expected, observed, evidence (log or capture path), status (passed, failed, blocked or not run).

Then list:
- the defects found and fixed, with their file and line;
- the defects found and not fixed;
- what remains untested, and why.
