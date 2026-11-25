# How Embedder validated the RA8P1 support on the board

This page describes the Embedder session that ran the on-target validation. It covers how it was set up, what we told the agent, what the agent asked us, and how it worked through the tests. The results are in [`validation/ek-ra8p1/validation-summary.md`](../../validation/ek-ra8p1/validation-summary.md) (overview) and [`results.md`](../../validation/ek-ra8p1/results.md) (the table the brief asked for).

## Starting point

- **Code.** The r019 result in this repository (commit `30448d7`). It built cleanly and passed its host tests, but had never run on a board.
- **e2 studio.** An isolated support area with FSP 5.9.0 only. Before the session we installed the r019 packs and confirmed they matched `packs/r019/manifest.json`. No official FSP 6.x RA8P1 support was visible to the agent.
- **Bench:**
  - one EK-RA8P1 v1 with its on-board J-Link (SWD and virtual COM port);
  - a Digilent Analog Discovery 3 (AD3), with four digital inputs on header pins P514, P111, P806 and P807 and a common ground;
  - a 1 kΩ resistor from A4 (DAC0) to A0 (ADC input AN001).

  Nobody had recorded which AD3 line went to which pin, and no AD3 oscilloscope channel was connected.
- **Embedder.** Version 0.3.225 in VS Code. The main agent ran on gpt-6.2-sol, and some subagents ran on gpt-6-luna.
- **Brief.** [`VALIDATION.md`](../../VALIDATION.md), which replaced the original brief's "no hardware" rule.
  - It listed the tests in order and the boundaries.
  - Boundaries: no option-setting or security writes, MRAM writes only in a scratch range named in the plan, and the AD3 as input only.
  - It also set the report format.

## The session at a glance

| | |
|---|---|
| Duration | 2 h 06 min (24 Nov 2026, 23:40 UTC, to 25 Nov, 01:46 UTC) |
| Messages from us | 8, quoted below |
| Questions from the agent | 13, all asking for a physical action on the bench |
| Subagents | 16, for test fixtures, scripts, independent diagnoses and the host regression |
| Model requests | 1,119 (main agent and subagents) |
| Tool calls | about 1,980: 807 shell, 408 file reads, 134 file edits, 79 hardware script runs (63 passed, 16 failed), 16 flash-and-capture runs |
| Context compactions | 7. The agent carried on after each one without being prompted |
| Pack revisions | r019 → r020 (GPT clock fix) → r021 (Rev. A startup fix) |
| Defects found and fixed | 2 in the BSP, both found only on the board |

## What we told the agent

These are all our messages, word for word.

1. The prompt:
   > Read VALIDATION.md. The RA8P1 and EK-RA8P1 support in this repository is finished but has never run on a board. Validate it on the attached EK-RA8P1 with the J-Link and the Analog Discovery 3, following the tests, boundaries and report format in VALIDATION.md. Start with a plan for review.
2. Plan approval, unchanged, 43 seconds after it was submitted. The plan is in [`plan.md`](plan.md).
3. > why are these tests blocked
4. > u can erase anything and run those optional tests aswell
5. > anything else we should test?
6. > test all those, test everything to make this production ready and bullet proof
7. > great is there anything else we want to test to prove that this new ra8p1 support is production ready?
8. > can you make a validation summary in a md file for all the tests we did, their results, and why the test was needed and what they prove

Message 4 gave broad erase permission. The agent still wrote only to the 2 KiB scratch block named in its plan, and checked the rest of code MRAM with hashes before and after.

## What the agent asked us

The agent asked 13 questions. Each one asked us to do something only a person at the bench can do, and each said why:
- **9 power cycles with no debugger attached.** A debugger connection masks watchdog resets and leaves debug state set. Cold start also had to be compared with a debugger reset.
- **3 presses of the board's RESET button.** The J-Link's "reset pin" mode still issued a software reset on this target.
- **1 reconnect of the debug USB cable.** It dropped after a test firmware faulted.

It asked nothing about the code, the configuration or the scope.

## Sources the agent used

- **RA8P1 hardware manual** (R01UH1064EJ0130). The project's document search returned no RA8P1 results, so the agent read the manual's PDF from e2 studio's local download folder.
- **EK-RA8P1 v1 user's manual and the microphone datasheet,** downloaded from Renesas and the part distributor.
- **Web searches,** 5 in all, for J-Link reset and flash-loader behaviour and EK-RA8P1 pin tables.
- **This repository and the bench.**

No official FSP 6.x source or pack was used. The only part of the e2 studio 6.6 install the agent touched was its GNU Arm compiler, for compile checks.

## How the run went

### 1. Plan (23:40–23:44)

- **A read-only subagent** worked out the safest configuration.
- **The plan** fixed these points before any board access:
  - **The scratch range:** `0x0207F800–0x0207FFFF`. It is one 2 KiB MRAM erase block at the end of CPU0's area, below CPU1.
  - **What may be downloaded:** only application S-records derived from each fresh ELF, with known option payloads removed and every byte range checked before download.
  - **Never** a programmer fed an ELF that carries option bytes.
  - **The test order and pin choices,** taken from the board manual and the board profile: SCI8 on PD02/PD03 for the console, and DAC0 P014 → AN001 P001.

### 2. Test tools (23:44–23:54)

Subagents wrote these in parallel:
- the AD3 capture script ([`ra8p1_capture.py`](../../.embedder/hardware/ra8p1_capture.py));
- the image guard that audits ELFs and S-records ([`image_guard.py`](../../validation/ek-ra8p1/image_guard.py)), with host tests;
- the first CPU0 test firmware.

### 3. First defect: GPT timer clock (23:49–00:03)

- **23:49:** the first r019 image booted and printed `READY`.
- **23:59:** the AD3 measured the 20 ms timer toggle on P514 at **57.25 ms**.
- **Diagnosis.** The agent traced the clock setup at hardware breakpoints, and a subagent made an independent diagnosis. The BSP metadata didn't select PCLKD for GPT when the dedicated GPT clock was off, so the timer ran from the wrong clock.
- **Fix.** The agent fixed the BSP module description, built r020, and installed it into the isolated e2 area using a recorded install plan.
- **00:03:** all four pins measured 20.000 ms, which also established the AD3 line-to-pin mapping.

### 4. One driver at a time (00:05–00:43)

| Driver | Result |
|---|---|
| r_cgc | Passed |
| DAC/ADC loopback | Passed, after a test-firmware stack overflow was fixed in the fixture, not the driver |
| r_wdt | Passed. It needed cold power cycles, so the agent asked for them |
| r_mram | Passed, after two preflight refusals (below) |
| CPU1 start | Passed |
| PDM microphone | Passed |

The MRAM test shows how the agent handles a risky step:
1. It backed up the scratch block first.
2. The firmware refused to write twice, before any write happened:
   - once because debug state was still set;
   - once because it compared reserved status bits.
3. The agent fixed the preflight check to compare only the documented flags.
4. Firmware and J-Link both verified the pattern, and the final erase left the block blank.
5. Hashes of the other 1,046,528 bytes of code MRAM stayed the same throughout.

### 5. Second defect: Rev. A startup (00:46–01:30)

After "test everything", the agent added more tests:
- repeated debugger resets;
- physical RESET presses and cold power-on;
- a 300-capture microphone soak with CPU1 running.

**The problem.** r020 sometimes booted with the wrong clock dividers (`SCKDIVCR=0x10000000` instead of `0x00001110`) or faulted before the application started.

**The cause.** The agent read the silicon revision (Rev. A), and the hardware manual (Table 1.1, §11.7) forbids Cortex-M85 cache access during a voltage-scaling transition. It traced startup at reviewed instruction addresses and found both caches active at that point.

**The fix.** It disabled the caches around the transition in `bsp_clocks.c`, then restored them. It built r021 and reran every test on r021: board timing, clock change, watchdog, CPU1, microphone soak, resets and cold power-on. Two tests were not rerun on r021:
- the DAC/ADC loopback;
- the MRAM write.

### 6. Host regression and report (01:09–01:46)

**Missing inputs.** The broad host test suite needed inputs that this repository leaves out: the original run's `validation/` folder and the FSP 5.9.0 release zip. A subagent restored the original run's inputs from its workspace on the bench machine and downloaded the FSP 5.9.0 release zip from Renesas's GitHub release. It checked each against the hashes recorded in this repository.

**Results:**
- A focused set of 41 tests passed on r021.
- The broad suite, run on a pre-r021 snapshot, still had failures and errors, most of them caused by inputs that couldn't be restored.
- That gate is reported as open.

**Report.** The agent then wrote [`results.md`](../../validation/ek-ra8p1/results.md) and [`validation-summary.md`](../../validation/ek-ra8p1/validation-summary.md).

## How the hardware scripts work

The scripts in [`.embedder/hardware/`](../../.embedder/hardware/) run through Embedder's hardware script tool. Embedder provides these helpers:

| Helper | Purpose |
|---|---|
| `gdb.*` | J-Link GDB server access |
| `serial_*` | The virtual COM port |
| `la_*` and `digilent_*` | The AD3 |

Every script follows the same pattern:
- **It sets its pass criteria up front:** expected periods and tolerances, exact UART lines in order, register values, byte-for-byte readback.
- **It prints one JSON result,** `{"success", "summary", "data"}`, and saves its evidence under `validation/ek-ra8p1/evidence/`.
- **It refuses to act on an unsafe or unclear state.** Examples: CPU1 active during an MRAM write, a protected scratch block, an ELF whose hash doesn't match the audited one, an unreviewed breakpoint address.

| Script | What it checks |
|---|---|
| `ra8p1_capture.py` | AD3 line-to-pin mapping and timer periods, ±1% |
| `ra8p1_clock_trace.py` | Clock registers at hardware breakpoints during startup |
| `ra8p1_readback.py` | Programmed code against the audited ELF, and the live CPU0 state |
| `ra8p1_reset_matrix.py` | Repeated system resets, each checked against the boot and clock profile |
| `ra8p1_analog.py` | DAC → ADC loopback levels and ramp |
| `ra8p1_wdt_preflight.py`, `ra8p1_wdt.py` | Watchdog start mode, then refresh, expiry and reset cause |
| `ra8p1_mram_snapshot.py`, `ra8p1_mram_uart.py` | Code MRAM hashes and scratch readback; the guarded erase/write/clean steps |
| `ra8p1_cpu1.py` | CPU1 identity, vector base and an advancing counter |
| `ra8p1_pdm.py`, `ra8p1_pdm_soak.py` | Microphone captures and the 300-capture soak |

**Bench firmware.** It is in [`validation/ek-ra8p1/`](../../validation/ek-ra8p1/) (`bench*.c`), and the generated CPU0 and CPU1 projects are next to it. The test firmware's UART commands (`analog`, `wdt-arm`, `mram-write` and others) are defined in those files. The J-Link command files (`*.jlink`), result checkers (`reset_oracle.py`, `image_guard.py`) and their host tests are in the same folder.

## Reproducing the run

1. Install `packs/r021/` into an e2 studio support area that has FSP 5.9.0 and no RA8P1 support.
2. Wire the bench as described above.
3. Give Embedder [`VALIDATION.md`](../../VALIDATION.md) and the prompt quoted above.

The generated FSP sources (`ra/`) and build outputs (`Debug/`) of the two test projects are left out. To rerun the scripts as they are, regenerate and rebuild the projects first. The ELFs the scripts audit by hash are in `evidence/*-build/`.

Paths from the bench machine appear in the logs as `<repo>`, `<e2studio>`, `<e2-area>`, `<e2-state>` and `<tmp>`. The ELF files in `evidence/` are kept byte for byte, because the evidence records their hashes, so their debug information still contains the original paths. Snapshots of the MRAM scratch block's pre-test content are left out; see [`evidence/SCRATCH-SNAPSHOTS.md`](../../validation/ek-ra8p1/evidence/SCRATCH-SNAPSHOTS.md).
