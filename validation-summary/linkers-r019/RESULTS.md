# RA8P1 linker toolchains — r019

## Result and scope

One new immutable candidate revision was published: `validation/ra8p1/packs/r019`.
Only `Renesas.RA_mcu_ra8p1.5.9.0.pack` differs from r018; the other 36 candidate archives, existing stock packs, production C/MDF inputs and older-device resources were not changed by this follow-up. The MCU archive SHA-256 is `1d56e7e2d3474bc613074fa944b530ebc7389743b6e2a8d54cc14693e3a5f5e8`.

Both existing GCC scripts are byte-identical to r018. All 33 supplied pin-model files are unchanged. See `pack-delta.json` and `final-integrity.json`.

Added two LLVM scripts, two IAR scripts, two AC6 scripts and the stock-style AC6 companion `script/ac6/fsp_keep.via`. PDSC selection combines the indicated `Tcompiler` with `Dcore=Cortex-M85` or `Dcore=Cortex-M33`.

| Toolchain / core | Script | PDSC condition | Built and linked | Map check |
|---|---|---|---|---|
| GCC / CPU0 CM85 | `script/fsp.ld` (unchanged) | `Only_CM85_and_GCC` | Pass: minimal + MRAM/DAC_B/PDM, clean | Pass; existing CPU0 ELF/SREC also unchanged |
| GCC / CPU1 CM33 | `script/fsp_cpu1.ld` (unchanged) | `Only_CM33_and_GCC` | Pass: minimal + MRAM/DAC_B/PDM, clean, preceding CPU0 | Pass; existing CPU1 ELF/SREC also unchanged |
| LLVM / CPU0 CM85 | `script/fsp.lld` | `Only_CM85_and_CLANG` | Pass: minimal + MRAM/DAC_B/PDM, clean | Pass against corresponding GCC fixture |
| LLVM / CPU1 CM33 | `script/fsp_cpu1.lld` | `Only_CM33_and_CLANG` | Pass: minimal + MRAM/DAC_B/PDM, clean, preceding CPU0 | Pass against corresponding GCC fixture |
| IAR / CPU0 CM85 | `script/fsp.icf` | `Only_CM85_and_IAR` | Not run: compiler unavailable | Static region/section/symbol checks pass; no map |
| IAR / CPU1 CM33 | `script/fsp_cpu1.icf` | `Only_CM33_and_IAR` | Not run: compiler unavailable | Static region/section/symbol checks pass; no map |
| AC6 / CPU0 CM85 | `script/fsp.scat` + `script/ac6/fsp_keep.via` | `Only_CM85_and_ARMCC` | Not run: compiler unavailable | Static region/section/symbol checks pass; no map |
| AC6 / CPU1 CM33 | `script/fsp_cpu1.scat` + `script/ac6/fsp_keep.via` | `Only_CM33_and_ARMCC` | Not run: compiler unavailable | Static region/section/symbol checks pass; no map |

## Construction and LLVM project creation

The new resources are adapted from the preserved ORIGINAL FSP 5.9 RA8M1 scripts for CM85 and RA6M5 scripts for CM33. The CM33 scripts carry the applicable CM85-style no-cache section support into the RA8P1 allocation. `tools/ra8p1/prepare_pack_resources.py` emits the LLVM resources and compiler/core PDSC entries; `tools/ra8p1/linker_commercial.py` emits the IAR/AC6 resources and companion. The GCC adaptation path and emitted bytes remain unchanged.

Because the high-level create command selects GNU, LLVM creation used the same e2 ProjectGen API through `embedder e2 exec .rerun/linkers-r019/create_llvm.py NAME ABSOLUTE_LOCATION CORE [PRECEDING]`. It selected:

- `projectGenerationFor('ra', '5.9.0')`, board `EK-RA8P1`, core `CM85` or `CM33`;
- chosen template `Bare Metal - Minimal`, `No RTOS`, `FLAT`;
- `toolchain('LLVM Embedded Toolchain for Arm', '21.1.1')`;
- `precedingProject(CPU0_NAME)` for CPU1;
- `validate()`, `generate(None)`, the existing `prepare_project()` identity/debugger helper, and `generateProjectContent()`.

No generated XML, copied production source or generated linker output was hand-patched. Clean builds used `embedder e2 build PROJECT --rebuild`, with CPU1 built after CPU0. The driver fixtures reference all three standard API tables from live application code, and the map checker requires their implementations to survive section garbage collection. Fixtures also populate ITCM, DTCM initialized/BSS, noinit and no-cache sections.

## Placement and unchanged-output proof

`check_maps.py` checks every nonempty allocated output section in the actual ELFs, confirms the section appears in its map, verifies expected memory-region membership, compares region/boundary symbols across GCC/LLVM, and checks every file-backed PT_LOAD is inside that core's owned MRAM or CPU0 option words. Nonallocated debug/metadata and empty output sections do not occupy target memory and are not represented as region-placement passes. Toolchain-exclusive allocated sections are checked explicitly, not dropped from the comparison.

All four GCC/LLVM fixture comparisons pass (`map-comparison.json`):

- CPU0 MRAM `0x02000000..0x0207ffff`; CPU1 MRAM `0x02080000..0x020fffff`.
- CPU0 SRAM `0x22000000..0x220cffff`; CPU1 SRAM `0x220d0000..0x2219ffff`.
- Local ITCM `0x00000000` and DTCM `0x20000000`, 128 KiB each for CPU0 and 64 KiB each for CPU1; initializer images remain in the owning core's MRAM.
- Sparse option words stay at their exact existing contract addresses and are CPU0-only.
- The unchanged GCC contract has no dedicated shared section/reservation. The new scripts preserve the same partitioning of shared SRAM; they do not introduce an IPC shared-memory ABI.

Section sizes and intra-region addresses can differ because GCC and LLVM generate different code/libraries. Required region membership and fixed image/TCM/option boundaries match. e2's generic pair summary reads pre-override generated memory descriptions and reports overlaps for GCC (and cannot check LLVM `.lld` memory files); the actual map/ELF check above verifies the pack-owned final allocations instead.

Existing `cpu0`, `cpu1`, `mram`, and `mram_cm33` projects were clean-rebuilt. All eight ELF/SREC SHA-256 values match their before snapshots exactly (`existing-gcc-before.json`, `existing-gcc-after.json`).

## Focused validation and provenance

- Pack-resource suite: 25 tests passed (`resource-tests-final.log`).
- IAR/AC6 static suite: 12 tests passed (`commercial-tests.log`). These check original-input fingerprints, region bounds, startup symbols, TCM aliases, sparse options, section retention, guards and host preprocessing, not commercial linker execution.
- Combined focused run: 37 tests passed (`focused-tests.log`); no full review or full regression suite rerun.
- Live MDF/PDSC validation: `canary: reported`; no new problems in six files (`validate.log`). The 16 missing driver-component warnings belong to the existing target's wider qualification; this revision changes only linker entries/resources, not those components.
- Final project pack checks report all three layers matching in `verify-{gcc,llvm}-{min,drv}{0,1}.log`.

Recorded pack provenance:

```text
packs: FSP 5.9.0 candidate (37 pack(s) from install 433fc5, install 34e7ce, install 54776c, install 5d782d, the rest stock; journalled)
```

Representative final clean-build evidence (full logs are adjacent):

```text
verified: yes — ~1/link_llvm_drv1/Debug/link_llvm_drv1.elf (0 errors, 0 warnings, relinked now, Debug)
artifacts (stat from disk): link_llvm_drv1/Debug/link_llvm_drv1.elf 634120 B 12:23:03, .srec 30028 B 12:23:03, .map 84604 B 12:23:03, .sbd 5625 B 12:23:04
link_llvm_drv0: artifacts (stat from disk): link_llvm_drv0/Debug/link_llvm_drv0.elf 722180 B 12:23:02, .srec 47068 B 12:23:02, .map 95144 B 12:23:02, .sbd 5481 B 12:23:02
verified: yes — ~1/link_gcc_drv1/Debug/link_gcc_drv1.elf (0 errors, 1 warnings, relinked now, Debug)
artifacts (stat from disk): link_gcc_drv1/Debug/link_gcc_drv1.elf 315664 B 12:23:00, .srec 26416 B 12:23:00, .map 143799 B 12:23:00, .sbd 5645 B 12:23:00
link_gcc_drv0: artifacts (stat from disk): link_gcc_drv0/Debug/link_gcc_drv0.elf 432004 B 12:22:58, .srec 37856 B 12:22:58, .map 147814 B 12:22:58, .sbd 5496 B 12:22:58
```

## Open limitations

- IAR and AC6 are statically checked only. Actual syntax/linking, library initialization and output sparsity need those compilers. CPU1 production startup already contains an explicit commercial-compiler C-TCM blocker in `system.c`; this pack-only change does not remove it.
- LLVM e2 creation/builds did not emit `.launch` files on this host. Compiler/core/dependency and linker selection were verified; debugger launch behavior was not qualified.
- GCC driver fixtures retain the existing RWX LOAD-segment warning for RAM-executed code; GCC scripts were intentionally not changed.
- Non-flat security partitions and optional peripherals are not newly qualified by this linker follow-up. No hardware operations or runtime claims.
- New projects, evidence and the new revision total approximately 134 MiB, below the requested 1 GiB limit; existing historical artifacts were preserved.
