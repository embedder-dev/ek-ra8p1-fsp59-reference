# EK-RA8P1 support on FSP 5.9, made by Embedder

This repository holds RA8P1 MCU and EK-RA8P1 board support for Renesas FSP 5.9.0. Embedder produced it in one session, starting from the EK-RA8P1 migration challenge. No code was written or edited by hand. [PROCESS.md](PROCESS.md) records every instruction Embedder was given, word for word.

**Status: reference, validated on one board.**
- Builds and host tests pass, and a review round checked it against the RA8P1 manual and SVD.
- A later Embedder session then validated it on an EK-RA8P1. That session found and fixed two BSP defects, so the current packs are **r021**. See [On-target validation](#on-target-validation-r021).

Use it to see what an automated migration produces, not as production-qualified FSP support. Known issues are listed below.

## What is in it

| Path | Contents |
|---|---|
| `baseline/ra/fsp/src/bsp/` | RA8P1 device header `R7KA8P1KF.h`, BSP (`mcu/ra8p1/`, clocks, startup, dual core) and the shared BSP changes |
| `baseline/ra/fsp/src/r_*` | New and changed drivers: r_mram, r_dac_b, r_pdm, r_wdt, r_adc_b, r_cgc and others the review touched |
| `baseline/ra/board/ra8p1_ek/` | EK-RA8P1 board support |
| `baseline/module_descriptions/` | e2 studio module descriptions (MDFs) for the device, events, board and changed drivers |
| `pack_sources/` | Source of the RA8P1 device pack: PDSC, linker scripts for GCC, LLVM, IAR and Arm Compiler 6, configurator data |
| `packs/r019/` | The built pack set (candidate r019): the RA8P1 and EK-RA8P1 packs and the rebuilt FSP 5.9.0 packs, with `manifest.json` |
| `packs/r021/` | The current pack set (candidate r021): r019 plus the two fixes from the board validation, with `manifest.json` and `entry-diffs.json` |
| `tools/ra8p1/`, `tools/test_ra8p1_*.py` | Embedder's generators (device header, events, packs) and host tests |
| `review/` | The independent review round: `findings.md` (242 findings with evidence and status), `coverage.md` and the final summary in `evidence/final-r018-summary.md` |
| `validation-summary/linkers-r019/` | Results of the linker-script round: per-toolchain build table, map comparison and pack delta |
| `PROCESS.md`, `process/` | The brief, Embedder's plans, our plan feedback, answers and follow-up messages |
| `VALIDATION.md` | The brief for the on-target validation session |
| `validation/ek-ra8p1/` | On-target results (`validation-summary.md`, `results.md`), evidence logs and captures, the bench test firmware and the generated CPU0 and CPU1 test projects |
| `.embedder/hardware/` | The hardware scripts the agent wrote and ran: J-Link, serial and AD3 checks |
| `process/validation/` | The agent's validation plan and a [summary of the validation session](process/validation/session-summary.md) |

The commit history has three commits:
1. the challenge starting point;
2. Embedder's result (r019);
3. the on-target validation: the two fixes, the r021 packs, the results and the hardware scripts.

`git diff HEAD~2 HEAD~1` shows everything Embedder changed in the migration outside `validation/`. `git diff HEAD~1 -- baseline pack_sources` shows the two fixes from the board.

Left out: the migration run's own `validation/` folder (about 6 GB of build logs, candidate archives and evidence; the `validation/ek-ra8p1/` folder here is the later board validation), the FSP 5.9 pack archive under `reference/vendor/`, and the baseline git archive. Links from `review/` into `validation/` therefore don't resolve. Absolute paths from the machine that ran it are replaced by `<repo>`, `<e2studio>`, `<e2-area>`, `<e2-state>`, `<tmp>` and `<home>`. The ELF files in `validation/ek-ra8p1/evidence/` are kept byte for byte, because the evidence records their hashes.

## On-target validation (r021)

An Embedder session validated the support on one EK-RA8P1 v1 (Rev. A silicon) on 24–25 November 2026. The bench had:
- the board's on-board J-Link;
- an Analog Discovery 3 as a logic analyzer on four header pins;
- a 1 kΩ DAC-to-ADC loopback.

The session took about 2 hours. [The session summary](process/validation/session-summary.md) describes how the agent worked.

**Results.** [`validation/ek-ra8p1/validation-summary.md`](validation/ek-ra8p1/validation-summary.md) gives an overview, and [`results.md`](validation/ek-ra8p1/results.md) has the full table.
- CPU0 boot and clocks, resets, cold power-on, the board's GPIO and GPT timing, r_cgc, r_wdt, CPU1 start and r_pdm passed on r021.
- The DAC/ADC loopback and the MRAM erase/write passed on r020 and were not rerun on r021.

**Fixed from the board:**
- **GPT clock (r020).** With the dedicated GPT clock off, the BSP didn't select PCLKD for GPT. A 20 ms timer measured 57.25 ms on the AD3. The fix is in the RA8P1 BSP module description.
- **Rev. A startup (r021).** The board sometimes booted with the wrong clock dividers, or faulted before reaching the application. The hardware manual forbids Cortex-M85 cache access during a voltage-scaling transition on Rev. A. `bsp_clocks.c` now disables the caches around that transition and restores them afterwards.

**Still open:**
- The full host regression suite has not passed against r021.
- The DAC/ADC loopback and the MRAM erase/write need a rerun on r021.
- The board check reports 16 `r_acmphs`/`r_ioport` pin-binding warnings.
- **Not covered:** PLL and high-speed clock profiles, TrustZone, calibrated analog accuracy, more than one board, and the full voltage and temperature range.

## Using the packs

Install the packs in `packs/r021/` into an e2 studio support area that has FSP 5.9.0 and no RA8P1 support (for example with e2 studio's CMSIS pack import, or by copying them into the area's pack folder). Then create an EK-RA8P1 project for CPU0 (Cortex-M85), and optionally a CPU1 project (Cortex-M33) with the CPU0 project as its preceding project. The debugger configuration uses the on-board J-Link (`R7KA8P1KF_CPU0` and `R7KA8P1KF_CPU1`, SWD).

Toolchains:
- **GCC (GNU ARM 13.2) and LLVM (Arm Toolchain for Embedded 21.1.1):** minimal BSP and driver projects build and link on both cores.
- **IAR and Arm Compiler 6:** linker scripts are included and checked against the GCC layout, but were not built, because neither compiler was available.

## Known issues

- **DMAC10–17 event names.** The event enum renames the manual's `DMAC10_INT`…`DMAC15_INT` (0x048–0x04D) to `ELC_EVENT_DMAC8_INT`…`ELC_EVENT_DMAC13_INT` so the channel numbers stay contiguous for the stock DMAC driver, and defines `DMAC16/17` as aliases of `DMAC14/15`. The values match the manual; the names don't. Code using the manual's names gets the wrong event. The events MDF has the same shift.
- **Events MDF gaps.** It lacks ids for DTC end on both cores (it uses different names), DMAC16/17 and the PDM data and error events.
- **CPU1 start.** CPU0 starts CPU1 from `SystemInit` at a fixed address. If a debugger has already activated CPU1, CPU0 skips activation and CPU1 stays parked. The wait for activation has no timeout, and there is no `R_BSP_SecondaryCoreStart`-style API.
- **r_mram:**
  - An erase at an unaligned address rounds down to the containing 2 KiB block instead of being rejected.
  - Anti-rollback counter increment and permanent start-up area select always return unsupported.
  - The default write window is 0/0.
  - Interrupts are masked for the whole operation.
  - The PE-mode entry is checked with a single read-back.
  - The MSUACR write sequence needs checking against the manual.
- **r_pdm.** Uses an FSP-style API, but has no DMA or sound detection, and not every PDM function is there.
- **TrustZone.** Only flat projects are supported. Secure/non-secure partitions and CPU1 non-secure event routing are not provided; such builds are rejected, not silently wrong.
- **Open review findings:**
  - 12 findings remain open: 7 high, 4 medium and one unrated. They cover a few register blocks whose primary sources conflict (GPTP, MFWD, ESWM, GWIDC, PVD4/5), Ethos-U55, OSPI DOTF, MRAM command timing and a ThreadX timing constraint.
  - See `review/findings.md` and the open-findings section of `review/evidence/final-r018-summary.md`.
- **Self-audit.** Embedder's own final cross-check of its evidence did not complete: its readiness check exits 2. The per-area checks pass.
- **LLVM debug configuration.** LLVM projects created headless did not get debugger `.launch` files. Projects created in the e2 studio GUI may behave differently.
- **Behaviour changes.** Several drivers (r_mram, r_wdt, r_cgc) changed behaviour to follow the manual literally where upstream FSP differs, for example a read-modify-write of NMIER and a cap on PLL1P. Each is listed with its reason in `review/findings.md`.

## Licence

The FSP sources are Renesas FSP 5.9.0 under its BSD-3-Clause licence ([`baseline/LICENSE.md`](baseline/LICENSE.md)). The RA8P1 pin model in `.embedder/pin-model/` is Renesas's and was supplied with the challenge.
