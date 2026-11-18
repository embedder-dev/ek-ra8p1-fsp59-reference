# Focused clock-transition remediation fixtures

Scope: CLK-001/003/004/007/008/009 in the shared `bsp_clocks.c/.h` only.
The existing CLK-002/017 and BSP-005 changes are retained. No MDF, capability,
register-header, pack, generator, ledger, generated-project, e2, or device changes
are part of this batch.

## Primary-source anchors

- RA8P1 HM 9.2.2/9.2.3, pp. 327–331: packed system dividers, clock-ratio
  restrictions, and /2 versus /3 families. CPU0, CPU1, NPU and MRI are independent
  nibbles, not one arithmetic number. Both transition endpoints must be legal.
- HM 60.4.3, pp. 3559–3560, Figures 60.5/60.6: notify each divided MRAM clock
  before raising it; do not lower its notification while the old clock still
  runs. HM 60.5.1 prohibits prefetch at MRI <= 100 MHz.
- HM 11.7 and the 2026-02-06 clock-switch procedure correction: set voltage
  scaling for the destination frequencies before switching. Startup uses VSCR_1
  conservatively, waits for VSCMTSF before/after writing, and completes the
  transition before enabling either PLL. CM85 cache/TCM initialization occurs
  after `bsp_clock_init` in the existing startup sequence. External-VDD electrical
  requirements are not configured by VSCR.
- Datasheet Table 2.49, pp. 108–114: independent CPU0/CPU1/NPU/MRI/MRP/ICLK/
  PCLKA/PCLKB frequency maxima used by the runtime fixture.
- Datasheet Table 2.50, p. 115: FLL maximum 1920 us standard, 2150 us SiP.
  The target startup wait is 2150 us, including HOCO feeding either PLL.
- Each module-stop mask below comes from that domain's own switching section,
  not a sibling MCU or a generic list of consumers.

| Clock | HM section | Module-stop register/bits | Independent mask |
| --- | --- | --- | --- |
| USB | 9.2.44 | B11/B12 | 0x00001800 |
| OCTA | 9.2.45 | B16/B17 | 0x00030000 |
| CANFD | 9.2.46 | C26/C27 | 0x0C000000 |
| USB60 | 9.2.47 | B12 | 0x00001000 |
| I3C | 9.2.48 | B4 | 0x00000010 |
| SCI | 9.2.54 | B22–B31 | 0xFFC00000 |
| SPI | 9.2.55 | B18/B19 | 0x000C0000 |
| ADC | 9.2.56 | D21 | 0x00200000 |
| GPT/PDG | 9.2.57 | E18–E21/E27–E31 | 0xF83C0000 |
| LCD | 9.2.58 | C4 | 0x00000010 |

The module-stop/read/wait sequence is required for old division != /1. OCTA
requires read confirmation, not a timed wait. Other domains use a conservative
2200 us bound: two cycles of the slowest allowed source (LOCO minimum
29.4912 kHz) divided by 32 take <2171 us. This avoids trusting a configured source
frequency table before warm-start clocks have been restored. Only bits set by
the helper are cleared after the new clock is ready; pre-existing stops remain.

CANFD MOSC selection uses the normal peripheral handshake even though MOSC is
not a PLL source; the independent target encoding is 3, not reset MOCO=1.

## Executed-production checks

Run from the repository root:

```sh
python3 -m unittest tools.test_ra8p1_review_clock_transitions -v
```

Final focused result: **Ran 7 tests in 98.007 s — OK** (exit 0).

The Python harness extracts actual production functions/conditionals into
throwaway compilation units. It never rewrites checked-in generated projects.
Native cases use `-Wall -Wextra -Werror` and undefined-behavior sanitizer.

- `transition.cpp`: both cores × parameter checks on/off × settling delay
  on/off (8 builds). Every simulated register write checks legal encoding/family,
  CPU/NPU/MRI/ICLK ratios, frequency maxima, and separately sufficient MRI/MRP
  notifications. Cold start, opposing source/divider directions, equal sources,
  /2↔/3 family changes through MOCO, /64 and /24, and the former 0x4321+1
  whole-packed-divider error are exercised. Family crossings retain the prior
  MOCO stop state.
- `peripheral_startup.cpp`: both cores × checks on/off × secure/nonsecure ×
  FLL on/off × opposite HOCO/MOSC PLL inputs × cold/warm startup (64 builds).
  Every domain uses numeric masks above with three unrelated module-stop
  patterns, four initial sources and three old divisors. It checks stop-before-
  request, confirmation, delay, ready handshakes, divider/source writes, module
  restoration, voltage-before-PLL, FLL-before-PLL, and MOSC CANFD startup.
- Frozen keyed-OCTA protection fixture: 8 builds across cores/checks/security;
  every legal saved protection mask and the original source/divider matrix.
  This isolates keyed protection with a no-op stop helper; the real helper and
  its restoration are separately executed by `peripheral_startup.cpp`.
- Complete production ARM translation unit: existing generated RA8P1 CM85 and
  CM33 configurations with checks 0/1 (4 compilations, warnings rejected).
- Complete legacy ARM TU and preprocessed-token parity: existing generated
  RA8M1, RA6T2, RA4M1 and RA0E1 configurations with checks 0/1 (8 pairs). Compares
  executable/read-only constant sections plus their relocations, not debug data.
- 32 legacy capability sets: original/current FLL/PLL/OCTA changed-region token
  and native-object parity in both security modes; header FLL on/off parity.
- RA2A2 IRTC fragment with active error logging: independently requires the
  original `__LINE__` constants 3479 and 3502 and token/native-object parity.
  The production `#line 3465` anchors the unchanged IRTC tail. CRLF is checked
  on both production files.

## Integration blockers found outside the new focused suite

The exploratory combined run of `test_ra8p1_review_clock_transitions`,
`test_ra8p1_review_clock_registers`, `test_ra8p1_review_cgc`,
`test_ra8p1_review_mram`, `test_ra8p1_clocks`, `test_ra8p1_cgc`, and
`test_ra8p1_review_lpm` ran **38 tests in 234.478 s: 67 subtest failures and
1 import error**. This is not an all-green project result:

- Older fragment-only OCTA/startup fixtures omit the newly called private
  module-stop helper. The old startup wait mock also assumes every wait is a
  peripheral request, so the new VSCR waits reach unset mock pointers. Existing
  `test_ra8p1_clocks` additionally has a conflicting `PRCR`→`PRCR_S` fake-header
  alias, yielding duplicate/missing member diagnostics. These old fixtures were
  not edited under this ownership boundary.
- `test_ra8p1_cgc` fails its existing PLL-start, source-stop and CPU1 NMI
  expectations. `r_cgc.c` is outside this batch; the separate
  `test_ra8p1_review_cgc` tests all passed in that run.
- Direct package-style import of `test_ra8p1_review_lpm` fails because it imports
  `test_ra8p1_lpm` without the `tools.` prefix. Use the repository discovery
  invocation or `PYTHONPATH=tools` when running that existing module.
- All five `test_ra8p1_review_mram` tests passed in the same run.

No publication or hardware qualification was attempted; both are excluded by
this assignment.

## ADC clock-getter handoff (read-only observation)

`R_FSP_SystemClockHzGet(FSP_PRIV_CLOCK_PCLKA)` already supplies effective PCLKA.
There is no shared ADCCLK/GPTCLK getter. The existing
`R_FSP_AsyncClockHzGet` is limited to the BCLKA/ESW source set: it rejects target
sources 0, 2, 3 and 4, so it is not directly usable for ADC/GPT. A private ADC-side
helper can read ADCCKCR/GPTCKCR and their dividers, reject request/not-ready or
prohibited fields, and divide `R_BSP_SourceClockHzGet` by the domain's decoded
numeric divider. No shared API was added here.
