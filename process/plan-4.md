# RA8P1: independent primary-source review, then fixes

## Outcome and boundaries

Independently review the current custom FSP 5.9-derived RA8P1 candidate before making further correctness claims. Record **every initial finding in `review/findings.md` before any fixes**, independently adjudicate each against primary sources, fix confirmed defects in their owning inputs, and requalify affected target and older-device configurations.

Continue from the existing candidate; do not restart migration, restore stock packs, reset either repository, or overwrite historical evidence. The previous 58/60 compatibility result is historical context, not a review verdict. BL2/TF-M prerequisites remain explicit qualification blockers; resolving them is not a substitute for the requested independent review or an automatic expansion into secure-boot implementation.

Retain the established target and safety boundaries: R7KA8P1KFLCAC, CM85 CPU0/CM33 CPU1, 24 MHz crystal, CPU0-owned shared initialization and option words, physically disjoint images/RAM, checked TCM aliases, exclusive peripheral ownership, reserved MRAM write windows, and privileged-operation opt-in. Preserve existing FSP 5.9 interfaces and older-device behavior. Do not modify supplied pin-model bytes or names.

**No hardware work:** no discovery/probing, serial connection, debug attach, flash, reset, capture, or security-state changes. Hardware-dependent conclusions remain unverified even when host tests and builds pass.

Planning has used readers only; it has not performed this review, run new tests/builds, or verified current Git changes. During planning, only this designated plan file may change. `review/findings.md` and the other proposed review artifacts below will be created after approval.

## 1. Freeze the review scope and establish primary inputs

The parent will first obtain a complete current tracked/untracked file census for the outer and nested repositories, comparing production sources and MDFs with the preserved original FSP 5.9 inputs. Record hashes of reviewed files, candidate archives, supplied pin files and primary reference versions. Include deletions and generated-authoring tools; do not use an earlier report as the changed-file inventory. Preserve unrelated work. Do not run the pristine-baseline verifier as though intentional migration changes were corruption.

The current planning tools expose no command runner. Actual Git diff/hash comparison, script execution and later e2/test commands require a permitted command runner when implementation starts, or equivalent supplied read-only evidence for the census. If still unavailable, report that specific blocker; continue independent primary-source reading where possible, but do not fabricate an exhaustive census, execute through a write-capable workaround, or claim build/regression results.

Primary sources for reviewers:

- `/embedder-docs/ra8p1-hm/TOC.md` and its section files: RA8P1 HM R01UH1064EJ0130 Rev.1.30, with PDF page markers; the datasheet and applicable technical updates under `/embedder-docs/`.
- The supplied RA8P1 SVD, now expressly requested as review evidence. The available read-only representation is `.embedder/svd-cache/R7KA8P1AD.json` (device `R7KA8P1AD`, version `1.10.02`); `registerLookup` can retrieve its definitions without hardware access. Locate the source XML if available and record provenance/representation limitations. **Reconcile AD versus fitted KF applicability rather than assuming all blocks, options or resets match.** This permission does not authorize importing a newer FSP header, driver, MDF or implementation.
- EK-RA8P1 v1 User's Manual R20UT5309EG0104, board errata R20ZZ0244EG0200, relevant expansion-board manuals, and supplied schematics. Retrieve missing documents from authoritative vendor sources; the board skill is a navigation aid, not independent electrical proof.
- Appropriate Arm architecture and CM85/CM33 reference documents. The RA8P1 HM references Arm DDI 0553, CM85 TRM 101924 and User Guide 101927 in §2.15, pp.159–160. Record the actual applicable revision/section for architecture, barriers, cache, vectors and security claims; do not substitute an unrelated processor's optional features.
- `.embedder/pin-model/pinmapping/` and `pinconfig/`, immutable inputs for accepted pin IDs. Review how the candidate uses the model, not how to rewrite it.
- Preserved original FSP 5.9 sources and pack metadata for naming, API, callback, parameter-check and generation conventions. Sibling headers establish vocabulary, not RA8P1 register facts.

Use technical updates and matching-device manual evidence to resolve SVD discrepancies, retaining both citations. Missing/ambiguous or conflicting source facts become explicit review gaps or findings, never silently chosen constants. Do not treat an SVD reset value as complete evidence of reset sequencing, write side effects or timing.

## 2. Run fresh, read-only specialist reviews

Launch **new subagent sessions**, not any implementation author's existing session. Each gets a single bounded review area, concrete code paths and primary-source locations, but no earlier conclusions, pass counts, suspected defects, migration notes, candidate inventories as authority, or prior test results. Every reviewer must explicitly remain read-only: no file edits, notes, generated artifacts, builds, tests, IDE/configuration operations, installs, or hardware access. They return findings and coverage directly to the parent.

Use `renesas-fsp-drivers`, `renesas-fsp-mdf`, board and e2 skills for navigation/conventions where relevant, but direct reviewers to verify claims in original sources, not skill anecdotes or previous agent reports. The parent owns all report writing. Independent assignments can run concurrently; use bounded batches and the fewest specialists that can cover the actual scope without sampling it away.

| Review area | Assignment and evidence requirements |
|---|---|
| **1. Device header** | Review `R7KA8P1KF.h`, its generator and every `registers*.json` input. Partition by disjoint peripheral families if necessary. Start from the complete primary SVD/manual peripheral inventory—not merely emitted types or currently selected drivers. Compare every applicable instance/base, register/address/width/access, array/cluster stride, field/bit/reserved region and documented reset value; include secure/nonsecure aliases and core views. Check FSP type/member/macro naming against original headers. Enumerate missing blocks/registers and source-only entries. If reset constants are not emitted, review the underlying facts and consumers without pretending the C header declares resets. |
| **2. Interrupts/events** | Independently compare every event number, reserved hole, alias, link target and scope with the manual tables. Trace target `bsp_elc.h`, overrides, events MDF, shared `bsp_irq.*`/`bsp_group_irq.*`, ICU/ELC access, vector generation, IELSR clearing, NMI routing and each core's event banks. Check mappings in changed driver MDFs as well as the enum. |
| **3. BSP** | Review startup/system, shared clock/protection/security/ROM/low-power/cache code, target capabilities, device resource descriptions and linker templates. Cover every source/divider/PLL and limit, transition ordering and wait states, MRAM/cache/prefetch and ECC, data/BSS and memory bounds, option/security defaults, protection restoration and low-power entry/exit. Split clock versus memory/security/startup only if needed for complete coverage. |
| **4. Dual core** | Independently trace CPU1 vector setup, activation, parking/release and barriers; primary/secondary roles, shared initialization/ECC, local TCM/cache, physical alias overlap, peripheral/interrupt ownership, and CPU1 generated project/compiler/debug/linker/dependency selection. Review the CPU1 project as evidence, without modifying it or trusting a prior verifier verdict. |
| **5. Drivers** | Assign **one fresh reviewer per driver**, beginning with `r_mram`, `r_dac_b`, `r_pdm`, `r_wdt`, `r_adc_b`, `r_cgc`, then every other changed driver/port discovered by the actual diff. Already visible candidates include AGT, ICU, I3C, LPM, SCI_B SPI, GLCDC, MIPI DSI, FreeRTOS and ThreadX; the census, not this list, controls completeness. Check each entry point/ISR, manual-defined sequence and timing, state/error cleanup, standard API/extension layout, parameter-check modes, callbacks/security, defaults, instance/core ownership and register side effects. Include production header/MDF contracts in that driver's scope. |
| **6. Board/configurator/packs** | Review board sources, board/device/part/FSP MDFs, every changed shared MDF/PDSC/tooling resource, pack construction/publication inputs, accepted pin IDs and actual generated output. Check clock/default constraint effectiveness, chip/package eligibility, pins/attributes/resets and switch-dependent routing against board documents/schematics. Examine schema-valid but behavior-changing metadata and pack ownership/duplication/staleness risks. |
| **7. Older devices** | Review **every change outside RA8P1-only files** against original FSP 5.9 bytes: C/headers, existing MCU capabilities, APIs, RTOS, MDF defaults/constraints/guards/signals, board metadata and relevant generation/pack tools. Establish affected devices and code-generation paths; do not infer preservation from capability names or object sizes alone. |
| **8. Tests** | Review test sources/harnesses and primary specifications independently. Identify which oracles originate from the same candidate table/generator, fake-register behaviors that conceal side effects, ineffective negative tests, missing branches and unsupported skips. Map each area above to independently sourced assertions and concrete mutations a test should detect; distinguish structure/compile coverage from behavioral correctness. Prior green logs are not evidence for this review. |

Reviewers return: scope inspected, exact coverage counts/list and gaps, plus each finding's file and line, severity, observed behavior, expected behavior, primary source document/revision/section/page or precise SVD path, and reasoning/impact. A no-finding report still needs coverage evidence. Broad findings must enumerate affected entries/locations; distinct independently fixable defects receive separate IDs. Record unavailable source evidence separately from a confirmed code error.

## 3. Record all findings, then adjudicate independently

**Review/fix barrier:** no production, metadata, generator or test fixes until every assigned initial review has returned and all initial findings are durably recorded in `review/findings.md`. Production remains frozen throughout initial review. If a reviewer cannot finish a section, record its uncovered scope explicitly and assign a fresh bounded continuation; do not turn partial coverage into an exhaustive pass.

The parent will create these **proposed** artifacts after approval:

- `review/findings.md`: the requested authoritative ledger, one row per finding, with stable IDs.
- `review/coverage.md`: reviewer IDs/independence, snapshot/reference hashes, ownership of every reviewed block/event/changed file, checked counts and unresolved coverage gaps.
- `review/evidence/`: focused source comparisons, adjudication records, tests/build logs and final revision provenance as needed; no duplicate generic automation framework.

Ledger columns:

`ID | Area | Severity | File:line / observed defect | Primary evidence / expected behavior | Reviewer | Disposition and reason | Fix / owning paths | Test and result | Hardware requirement | Status`.

Severity: **Critical** (lock/security breach, destructive corruption or comparably severe unsafe behavior), **High** (boot failure, wrong addressing/timing, corruption or unusable supported function), **Medium** (bounded functional/configuration defect), **Low** (minor correctness/documentation issue). Source uncertainty is not automatically a code-defect severity; label it clearly.

Initially mark findings **Untriaged**, with fix/test cells pending. Preserve the original allegation and snapshot location when later lines move. Deduplicate repeated reports under one ID with all reviewer references; do not discard disagreements.

Only after the complete initial ledger exists, the parent will open each cited primary source and the affected implementation/callers and mark **Confirmed**, **Rejected—with reason and source**, or **Unresolved—evidence needed**. Reviewer consensus or previous tests are insufficient. Confirmed/rejected disposition remains separate from remediation status: Open, Fixed—verification pending, Fixed—software verified, or Open—hardware/source blocked. Rejection must rebut the claim, not merely note that code builds. Preserve every rejected finding in the ledger.

## 4. Fix confirmed defects in owning inputs

Prioritize destructive/security/addressing/boot defects, then dependency-ordered header/events, BSP/core, driver and configurator fixes. Correct the minimal owning layer and its consumers together; do not add aliases for incompatible registers, success stubs or reduced capability flags to hide failures.

Likely owning paths (actual edits depend on confirmed findings):

- `tools/ra8p1/generate_device_header.py`, `tools/ra8p1/registers*.json`, and their generated owning header `baseline/ra/fsp/src/bsp/cmsis/Device/RENESAS/Include/R7KA8P1KF.h`.
- `baseline/ra/fsp/src/bsp/mcu/ra8p1/`, shared `bsp/mcu/all/`, CMSIS device `Source/system.c`/`startup.c`, and corresponding reviewed capability inputs.
- Each confirmed driver's `baseline/ra/fsp/src/<driver>/`, matching `inc/instances/` and existing API contract; `inc/api/r_pdm_api.h` where relevant.
- `baseline/ra/board/ra8p1_ek/`, owning `baseline/module_descriptions/`, `tools/ra8p1/prepare_pack_resources.py`, and `pack_sources/ra8p1/` device/debug/memory/linker authoring assets.
- Relevant `tools/test_*.py` and production-C fixtures, strengthened with independently sourced expectations.

Keep existing API/configuration IDs/defaults stable unless correcting a confirmed target-only defect. Shared changes use capabilities defined consistently for all MCUs, with old branches/defaults preserved. Do not hand-fix validation-project `ra/`, `ra_cfg/`, `ra_gen/`, application `configuration.xml` or linker output. Preserve source formatting and unrelated changes. Pin-model fixes are never a remediation path.

After review, implementation may be delegated to distinct owned files. Original reviewers remain read-only and can re-review the fix against the source; do not make an independent reviewer its own repair author. Serialize shared capability/header contracts and publication; no concurrent writers to an owner.

For each confirmed finding add an independently sourced failing test before the fix where practical, then demonstrate the fix. Address test-oracle findings by using direct SVD/manual-derived expectations, access-order/write-mask checks and edge cases, not by copying the corrected production constant. Mutation checks run only after the initial ledger, in disposable isolated inputs, never by changing canonical primary sources or mutable installed/generated projects.

If a correction requires an externally visible stock-interface change, an older-device behavior change, a new insecure default or relaxed memory protection, stop that finding for a user decision rather than silently adopting it. Do not grow this review into missing peripheral or BL2/TF-M implementation without an explicit scope decision.

## 5. Integrate and verify repaired batches

The parent owns publication/integration. Reuse existing pack, compatibility, ELF and regression tooling, but apply fixes to those tools too if their independent review confirms defects.

1. Run focused host production-C/layout/event/clock/security/API tests for the changed owners. Cover both cores, parameter checks on/off, relevant callback/ISR/NMI/security paths, exact boundaries, invalid input and rollback/error sequences. Deliberately corrupt representative values/paths to demonstrate strengthened independent checks fail. Enumerate residual untested values; mutation samples do not prove every register correct.
2. Produce a **new immutable candidate revision**, preserving r014 and all intervening historical archives/manifests. Include every shared-source owning pack; recheck unchanged supplied pin-model bytes. Validate changed MDF/PDSC/tooling/board files using `embedder e2 validate mdf` with a live canary and justified BSP parity differences. Check valid and violating configuration cases, not schema alone.
3. With all e2 lanes paused, review the `embedder e2 packs install` dry run and apply its exact plan in the authorized isolated support area. Verify installed archives, extracted support resources and affected project source hashes; use reviewed `packs refresh` plans only for stale layers. Preserve edited/unknown files and block rather than overwrite them. Never restore stock or manually repair the installation.
4. Immediately regenerate and clean-build the minimum CPU0 and CPU0→CPU1 pair after coherent header/BSP fixes, then each affected driver's generated projects on both cores. Use `embedder e2 build <cpu1> --rebuild` for paired dependencies; configuration changes go through `config set`. Verify default stacks as well as affected optional/checking-on/off modes. Run both-core `board check` after board/device/header changes and at final freeze.
5. Rerun the **stock-module compatibility check** with pristine original and current candidate source sets against the same current generated RA8P1 BSP on both cores. Cover all applicable original PDSC translation units and supported RTOS default/optional paths. Preserve unchanged versus capability-adapted versus accepted legacy-variant mismatch classifications. Do not count absent dependencies, header-only evidence or BL2/TF-M prerequisites as compile passes. Reuse actual existing fixture configurations where valid; retain before/after diagnostics.
6. Rerun older-device generation and clean builds for affected shared owners using established RA8M1, RA6T2, RA8D1, RA4M2, RA4M1 and RA0E1 controls, adding controls only for newly affected paths. Compare original versus repaired generated defaults/guards/OFS and executable/constant bytes plus relocations of **changed shared translation units only**, with identical flags/configurations. Explain every difference; no whole-project disassembly expansion or aggregate historical count substitutes for affected coverage.
7. Independently verify current source/pack/ELF identity: physical part, actual CM85/CM33 compiler/ABI and debugger selection, vectors/reset/stacks, physical PT_LOAD disjointness including aliases, TCM allocation, CPU0-only option sections and protected MRAM windows. Recheck reviewers' conclusions against actual emitted code/configuration, not only metadata inputs. Run the complete host suite at the final frozen revision and report failures/skips honestly.

Capture exact commands, source/reference hashes, candidate revision and e2 `packs:`, `verified:` and `artifacts (stat from disk):` lines, including preceding CPU0 artifacts. A verified build proves neither correct register values nor hardware timing. Hardware-required finding rows must state the outstanding physical check and remain explicitly hardware-unverified.

## 6. Reporting and completion gates

Post concise progress at: initial review coverage/ledger complete (before fixes), adjudication complete, each repaired integration checkpoint, and final qualification. Continue independent work without waiting for acknowledgments.

The final response will link `review/findings.md` and report:

- Counts **by each of the eight areas and severity**, with Confirmed / Rejected / Unresolved and Fixed / Open totals. Count each deduplicated ID once; distinguish confirmed fixed-in-software items that still need hardware confirmation.
- Every remaining Critical/High/open or source-blocked item, uncovered review scope, rejected finding rationale and hardware-only criteria.
- Target both-core generated/clean-build, stock-source/candidate compile and affected older-device regression results, host-test results and final candidate freshness. Preserve the accepted legacy SCI/DAC variant exceptions and existing BL2/TF-M blockers as separate limitations.
- Intentional target-only behavior corrections, any custom-candidate source/configuration migration, and disclosed warnings. No new stock FSP interface break or older-device behavior change is assumed approved.

Do not call support done merely because reviewers found nothing in sampled areas or all tests passed. Completion requires full recorded review coverage, individual primary-source adjudication, confirmed defects repaired or explicitly open, and current affected software qualification. With no hardware connected, runtime boot/dual-core synchronization, clock stability, persistence/analog/audio/transport behavior and physical safety remain unverified.
