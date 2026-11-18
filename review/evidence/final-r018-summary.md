# r018 independent review and software qualification

## Result and scope

The custom FSP 5.9-derived RA8P1 candidate has completed the available repair and scoped software-verification work. **It is not an exhaustive support sign-off.** The authoritative [ledger](../findings.md) retains 242 deduplicated IDs: 238 Confirmed, 1 Rejected and 3 Unresolved. Of these, 229 are repaired and verified in their stated software scope, 12 remain open, and 1 is rejected. No hardware operation was performed. Software-verified fixes still require their stated physical checks.

All 228 initial findings were recorded before initial repairs; 14 supplemental findings were recorded before their respective repairs. Original allegations, frozen locations, primary-source citations, adjudications and rejection reasons remain in the ledger. [Coverage](../coverage.md) retains incomplete per-value, optional-mode and primary-source scope; no historical green result supersedes those gaps.

## Findings by area and severity

`U` denotes unrated source/compiler uncertainty, not an invented defect severity. Fixed/Open are remediation counts; Confirmed/Rejected/Unresolved are separate disposition counts.

| Area | Critical | High | Medium | Low | U | Confirmed | Rejected | Unresolved | Fixed | Open |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 Device header | 0 | 12 | 23 | 2 | 1 | 35 | 0 | 3 | 31 | 7 |
| 2 Interrupts/events | 0 | 2 | 1 | 0 | 0 | 3 | 0 | 0 | 2 | 1 |
| 3 BSP | 0 | 13 | 14 | 0 | 0 | 27 | 0 | 0 | 26 | 1 |
| 4 Dual core | 0 | 0 | 2 | 0 | 1 | 2 | 1 | 0 | 2 | 0 |
| 5 Drivers/ports | 0 | 66 | 76 | 3 | 0 | 145 | 0 | 0 | 142 | 3 |
| 6 Board/configurator | 0 | 4 | 8 | 1 | 0 | 13 | 0 | 0 | 13 | 0 |
| 7 Older devices | 0 | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 1 | 0 |
| 8 Tests | 0 | 6 | 6 | 0 | 0 | 12 | 0 | 0 | 12 | 0 |
| **Total** | **0** | **103** | **131** | **6** | **2** | **238** | **1** | **3** | **229** | **12** |

DUAL-003 is rejected only for GNU 13.2.1 and the recorded CPU1 flags: actual owning `system.c` compiled at six optimization levels retains both finite TCM zero-store loops and subsequent initialization. Other compilers, LTO and physical boot are not thereby qualified.

## Software verification

### Frozen inputs and installation

- Final immutable candidate: `validation/ra8p1/packs/r018/manifest.json`, SHA-256 `eb4dd36f99fb67c1692f7b56d5439c312381e8a4897dfbb30711b9ef491d3960`.
- All 37 candidate archive bytes and every manifest entry were independently rehashed. All 33 supplied `pinmapping`/`pinconfig` payload files match their packaged bytes, unchanged. The navigation README is not a pin-model payload. See [freeze identity](final-r018-freeze-identity.json).
- All 4,389 final production/MDF/test input hashes remain equal to the full host-suite snapshot. `final-r018-host-tests-input-proof.json` records the pinned complete GNU 13.2.1 compiler and zero changed inputs.
- Authorized isolated installation journal includes `29bdfa`. `r018-installed-verify.log` reports 126/126 installed packs equal their journalled expectations and tracked support resources current. Its 20 shared-folder version variants and 49 resources e2 does not track remain explicitly excluded from that CLI support check, not an exhaustive installation claim. Project-selected owners are independently checked by the source/ELF verifier and owner layer reports.

### Fresh r018 parent builds and tests

- **889 host tests passed**, zero failures/errors/skips. Command: `python3 -m unittest discover -s tools -p 'test_*.py' -v`, with `PYTHONPATH=tools` and all Arm compiler selectors pinned to GNU 13.2.1. Log: [final-r018-host-tests.log](final-r018-host-tests.log).
- Minimal CPU0 and CPU0-to-CPU1 pair regenerated and clean-built, zero errors and zero warnings. Current full source/ELF verification checks 3,692 owning sources and passes both core/compiler/ABI/debugger/vector/reset/stack/option-owner and physical-allocation contracts. See [minimal source/ELF](r018-minimal-source-elf.json).
- All **24 six-driver core/checking combinations** clean-built freshly at r018: MRAM, DAC_B, PDM, WDT, ADC_B and CGC, each CM85/CM33 and checking disabled/enabled. All 24 corresponding source/ELF cases pass. Each mode has an immutable artifact/configuration archive whose contents were rehashed. See [build proof](final-r018-parent-build-proof.json), [matrix](r018-parent-driver-matrix.json), and [literal artifact evidence](final-r018-parent-artifact-quotes.md).
- A final audit correctly refused to transfer r014 untouched-default proof over changed drivers. This gap was closed with **6 additional fresh r018 clean links**: uncustomized MRAM, DAC_B and PDM stacks on both cores, using only `config set --add`, without property/BSP/spec overrides or application edits. All 3 new pairs pass full source/physical-ELF checks and all 6 project three-layer checks pass. Per-project config/compiler/object/artifact archives are bound in [untouched defaults](final-r018-untouched-defaults.json). Default Open/lifecycle remains a separate production-C host test, not target runtime. The first MRAM project was created at the CLI-resolved exact folder `defaults/r018`; an initial config attempt at a nonexistent child failed and its corrected command/log are retained. No evidence was overwritten or folder moved.
- ADC_B's raw default correctly reports clock/timing prerequisites. Qualified fixtures use the documented configuration-only 48 MHz source/PCLKA/ADCCLK recipe, mirrored in the actual CPU0 predecessor for the CPU1 project. No generated-header patch or application register shim substitutes for that requirement. MRAM default is read-only until an explicitly reserved window is configured.
- `embedder e2 board check validation/ra8p1/packs/r018 --board EK-RA8P1 --fsp 5.9.0 --keep` passes both cores with 0 warnings, 0 configurator problems and 551 pin settings/0 unknown IDs. It used the verified installed candidate in its isolated clone. [Log](r018-board-check.log).
- All 23 changed/new MDF inputs pass schema/reference checks with **canary: reported**. [Validation](final-r018-metadata-validation.log) retains justified component-alternative and supplied-model informational warnings; it is not warning-free. Generic versus external comparator eligibility is distinct; only external channels 0/1 are qualified by the fitted part.

### Expanded HAL, USB/security and RTOS evidence

The [before/after compatibility table](final-compatibility.md) reports each mandatory module and all 16 new/changed driver vtables. Pristine compilation, capability-adapted compilation, generated linking and runtime are not conflated.

- Lane2 regenerated all 42 existing projects at r018 with unchanged actual generated/compiler/dependency/object/ELF bytes. Their links retain 38 r016 and 4 r017 project origins. All 21 existing pairs pass current source/physical-ELF verification. New CRC SCI8 TDR/RDR plus comparator 0/1 controls add **4 fresh r018 clean links** and **8 active pristine/candidate source-TU results**, all zero errors/warnings. Live PVD menus exclude codes 0–2, preserve default 6; CRC retains SCI0 TDR default. See `validation/ra8p1/compatibility/expanded/lane2-r018-status.md` and closure JSON.
- The all-152 source census remains **r017 compilation transferred through actual unchanged-input proof**, not fresh r018 recompilation. Raw candidate classifications: 53 module passes, 0 compile failures, 18 blocked, 33 absent, 48 variant mismatches. These counts are not complete all-TU/all-option qualification. Of 60 present stock rows, 50 have every original TU active, 3 retain conditional/compiler-excluded gaps, 5 zero-source components have separate dependency-TU/link integrations, and BL2/TF-M remain prerequisite-blocked. Fourteen inactive/compiler-excluded TUs per core remain disclosed. Classic SCI/DAC are accepted incompatible legacy variants; SCI_B UART/DAC_B are the correct standard-interface implementations.
- Lane3 completed **38 actual r018 model regenerations**: **4 fresh r018 default clean links**, **34 r016 link transfers**, and **19 passing current source/ELF pair checks**. Fresh default work has 96 actual build TUs plus 8 active pristine/adapted source cases. Six optional USB/PSA units remain inactive/unqualified. See `validation/ra8p1/compatibility/peripheral-gates/r018-final.md`, owner report and closure.
- RTOS closure completed **4 actual r018 model regenerations** and layer checks; **0 fresh links or target TU compiles**. Exact inputs preserve the true r016-via-r017 origins: 24 core links, 204 candidate port TU passes, 204 pristine port TU passes, and 4,560 original-kernel dependency scans. All 12 archived pairs plus 2 current pairs pass fresh r018 source/ELF inspection. See `validation/ra8p1/compatibility/rtos/r018/report.md` and `final-closure.json`. This does not establish scheduler/tick/FP-context runtime.

### Older-device regression

[Canonical r018 regression](../../validation/ra8p1/compatibility/regression/r018-results.json) reports success for all 18 established fixture rows: six MCU/board controls with checking on/off plus six real RTOS controls. **262 TU/configuration comparisons over 38 unique changed shared TUs** retain exact original/current executable, constant and relocation equality and applicable generated-default/MDF invariants. Four rows/74 comparisons originate at r017; fourteen rows/188 comparisons originate at r016. r018 adds **0 links and 0 TU comparisons**: actual inputs, artifacts and current owning metadata were rechecked for unchanged applicability. No historical link or comparison is relabelled as fresh r018 work. There are no uncovered required shared TUs, missing control configurations or missing required RTOS option rows in this bounded regression report. Older-device runtime remains unverified.

### Literal build proof

From `r018-minimal-pair-clean-build.log`:

```text
verified: yes — <repo>/validation/ra8p1/review_r015_cpu1/Debug/review_r015_cpu1.elf (0 errors, 0 warnings, relinked now, Debug)
artifacts (stat from disk): review_r015_cpu1/Debug/review_r015_cpu1.elf 165568 B 14:35:21, .srec 6278 B 14:35:21, .map 130753 B 14:35:21, .sbd 5620 B 14:35:21
review_r015_cpu0: artifacts (stat from disk): review-r015/Debug/review_r015_cpu0.elf 282904 B 14:35:19, .srec 17454 B 14:35:19, .map 134987 B 14:35:19, .sbd 5476 B 14:35:19
packs: FSP 5.9.0 candidate (37 pack(s) from install 433fc5, install 34e7ce, install 54776c, install 29bdfa, the rest stock; journalled)
```

The CLI reports overlap between generic generated memory descriptions. Independent checks of the actual allocated physical ELF ranges pass; the generic warning is retained, not concealed. MRAM RAM-code links retain a disclosed RWX LOAD warning. Retained RTOS/third-party security warnings are classified in their owner reports and `retained-security-warning-classes.json`, not represented as new warning-free links.

## Migration slice matrix

“Pass (scoped)” is the verified configuration/software scope above, not every optional mode, a complete register catalogue, or physical qualification. “Retained parity” means actual original/current comparisons transferred only through unchanged-input proof, not fresh r018 comparisons.

| Slice | source | MDF | generated + clean build | validate mdf / board check | host tests | older-device regression | hardware (not run) |
|---|---|---|---|---|---|---|---|
| CPU0 BSP | Pass (flat scope); catalogue gaps open | Pass (scoped); unsupported provisioning rejected | Fresh minimal and driver owners pass | Live MDF/canary + both-core board pass | 889 suite pass | Retained shared-BSP parity pass | Not run / Unverified |
| CPU1 BSP | Pass (flat); NS routing blocked | Flat selection pass; NS partition blocked | Fresh CM33 chain pass; physical ranges disjoint | Both-core board pass | Core/cache/startup controls pass | Retained core/shared-owner parity pass | Not run / Unverified |
| EK-RA8P1 board | Pass (scoped routing/default template) | Supplied-model IDs unchanged | Both-core board builds pass | 551 settings, 0 unknown, 0 problems | Mapping/template controls pass | Older board/default invariants pass | Not run / Unverified |
| r_mram | Standard flash API; irreversible timing open | Safe read-only defaults | 4 fresh mode links + fresh default pair | Live canary pass | Lifecycle/window/cache/recovery tests pass | New-only selection; shared-owner parity retained | Not run / Unverified |
| r_dac_b | Standard DAC API; calibration boundary repaired | Usable extended/default config | 4 fresh mode links + fresh default pair | Live canary pass | Both-channel/value/state/timing controls pass | Existing DAC/DAC8 paths/selection preserved in scoped gates | Not run / Unverified |
| r_pdm | FSP-style API/extend; ISR races repaired | Board channel2/stereo admission | 4 fresh mode links + fresh default pair | Live canary pass | FIFO/IRQ/state/stereo/settling controls pass | Unsupported-device selection gates pass | Not run / Unverified |
| r_wdt | Standard WDT API; option/NMI fixes | Defaults/autostart retained | 4 fresh mode links | Live canary pass | Refresh/status/options/checking controls pass | Retained legacy TU parity pass | Not run / Unverified |
| r_adc | ADC16H through ADC_B; classic ADC unchanged | Clock prerequisites explicit | 4 fresh mode links with 48 MHz recipe | Live canary/constraint controls pass | Sequence/FIFO/guard/admission tests pass | RA6T2 ADC_B and classic ADC scoped regressions pass | Not run / Unverified |
| r_cgc | Standard CGC API; target limit/sequence fixes | Rational/divider/voltage constraints | 4 fresh mode links + BSP pair | Live canary/valid-invalid controls pass | Frequency/transition/error controls pass | Retained older clock TU parity pass | Not run / Unverified |

## Open findings and remaining limitations

Seven High-severity IDs remain open:

- **HDR-T01:** GPTP known surface added; PTPSCR0/1/2 lack corroborated width/access/field facts.
- **HDR-G09:** MFWD indices 2–15 have conflicting primary dimensions; common 0/1 views only.
- **HDR-G10:** ESWM TPEMIMC0 lacks a matching primary description.
- **HDR-G14:** GWIDC offsets conflict between register list and detailed manual/SVD.
- **EVT-002:** CPU1 Nonsecure event routing is not provisioned; unsafe Nonsecure links are rejected.
- **BSP-002:** Qualified within-core Secure/Nonsecure partitions remain absent; unsafe Nonsecure linking is rejected instead of aliasing Secure memory.
- **OSPI-003:** Target DOTF crypto/private-register binding is unavailable from permitted matching sources; enabled DOTF rejects, normal OSPI remains usable.

Four Medium-severity IDs and one unrated source discrepancy remain open:

- **MRAM-006:** inconsistent primary command maxima prevent qualified irreversible command deadlines. Permanent startup selection/counter increment reject before MMIO; privileged commands default disabled.
- **HDR-C06:** PVD4/5 address conflict unresolved; no guessed addresses emitted.
- **HDR-G15:** matching configured Ethos-U55 register specification unavailable; no fabricated NPU map.
- **THREADX-003:** runtime 24-bit reload admission repaired; selected-core configurator timing constraint still pending.
- **SRC-001:** 26 narrow PFS reset discrepancies retained in immutable supplied SVD; no unverified reset initializer introduced.

BL2/TF-M flash/storage/security prerequisites, optional inactive paths, non-EK parts, other compilers/LTO, Secure/Nonsecure deployment, unresolved full per-capability numeric review, compact-SVD dimensions/reset-mask limits and exhaustive transition/interleaving coverage remain unqualified. Nineteen older custom lane2 CPU1 warm-start callbacks were preserved rather than silently rewritten; regenerated default/new fixtures use the corrected CPU0-only shared pin/SDRAM guard. Existing generated user-owned applications do not automatically migrate to a changed template.

No boot, dual-core synchronization, NMI/reset timing, clock stability, MRAM persistence/endurance, analog accuracy, microphone/audio, USB/Ethernet/display/camera transport, physical routing or target safety measurement was run.

## Intentional corrections and compatibility

- Canonical FSP register types/members/views are added only where primary layout identity is established; incompatible variants are not disguised by aliases.
- Existing flash/DAC/ADC/watchdog/CGC API types remain unchanged. New PDM follows FSP ctrl/cfg/api plus `p_extend`; migration from this candidate's earlier custom direct-field config is documented in the compatibility report.
- Capability-gated target repairs cover clock limits/sequences, protection restoration, cache/NMI/dual-core ownership, ADC sequencing/FIFO/admission, PDM ISR races, DAC calibration boundary, watchdog option authority and other reviewed driver paths. Older-device branches/configuration behavior remain within the verified regression scope.
- Previously accepted but unsafe/unimplemented target provisioning, Nonsecure images, DOTF and irreversible MRAM commands now fail explicitly; safe flat defaults and memory/write-window boundaries are retained.
- Target comparator presence, legal voltage thresholds, CRC SCI5–8 menus, event-link sources and board routing are corrected; supplied pin-model bytes and filenames are not modified.

## Final cross-owner audit

**Cross-owner audit remains incomplete: readiness exit 2; aggregation was not executed.** The parent independently reran the final readiness command and the audit guards: **26 r018 wrapper/binding tests plus 29 strict-transfer guard tests pass**. The audit checks **876 final input identities**, **12 fresh source-fixture records**, all **24 parent mode archives** and **6 untouched-default archives**. It accepts **zero strict typed-transfer proofs**: adapters/bindings are still missing between the audit's strict snapshot contract and four delivered owner schemas (expanded/HAL, USB/security, RTOS, older-device regression).

This is an audit-tool integration gap, not missing owner deliveries or a demonstrated firmware compile failure. The detailed owner proofs are retained/hash-bound and their own scoped checks pass, but the unified audit has **not accepted** those transferred results. The r017 all-census statuses and r016/r017 legacy/RTOS comparison counts above therefore remain **owner-reported historical results with independently scoped transfer evidence**, not a new aggregate r018 qualification verdict. No old compiler records were reconstructed and no generic closure boolean substitutes for strict transfer validation.

See [`r018-final-audit.md`](../../validation/ra8p1/compatibility/r018-final-audit.md), the final readiness JSON and closed input bindings beside it. Parent recheck logs: `final-r018-parent-audit-readiness.log` (exit2), `final-r018-parent-audit-tests.log` and `final-r018-parent-strict-transfer-tests.log` (both exit0). Completing these four adapters, the12 open findings and preserved source/coverage gaps is required before exhaustive support sign-off. All e2 work is stopped; no hardware operation was performed.
