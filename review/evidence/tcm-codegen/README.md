# DUAL-003: GNU 13.2.1 C-TCM scrub emission

**Disposition: rejected for the qualified compiler/configuration.** The actual
owning `system.c` emits a finite 32-bit zero-store loop covering CPU1-local
C-TCM and S-TCM, including address zero, at every optimization level tested.
There is no compiler-inserted trap or terminal scrub loop, and subsequent
initialization is retained. This is emitted-code evidence, not a claim of
portable ISO C behavior, correctness with another compiler, or physical boot.

## Primary sources and scope

- RA8P1 Group User's Manual: Hardware **R01UH1064EJ0130 Rev.1.30**, section
  **2.17.1.1, Table 2.37, pp.191–192**: CPU1 secure C-TCM is
  `0x00000000..0x0000ffff`; CPU1 secure S-TCM is
  `0x20000000..0x2000ffff`. `0x2a000000`/`0x2a010000` are the bus-master
  windows, not substitutions for CPU1-local accesses. Indexed primary text:
  `/embedder-docs/ra8p1-hm/09-2.-cpu/17-2.17-cm33-tcm-tightly-coupled-memory.md`,
  lines 24–40.
- Owning source:
  `baseline/ra/fsp/src/bsp/cmsis/Device/RENESAS/Source/system.c`,
  constants lines 49–52; call at line 313; actual `bsp_init_ctcm` at
  lines 693–745, specifically stores at lines 703–707.
- Compile the **entire owning source directly**, not the stale generated
  `system.c`, a simplified reproducer, or substituted register declarations.
  Reuse the existing CPU1 project's compiler, flags, working directory and
  generated headers. No additional include paths, defines, no-inline flags,
  null-pointer options, register aliases, or source edits are supplied.
- Existing flags come from
  `validation/ra8p1/projects/cpu1/Debug/compile_commands.json`, the unique
  `system.c` entry. They include `-mcpu=cortex-m33 -mthumb -mfloat-abi=hard
  -mfpu=fpv5-sp-d16`, `-D_RA_CORE=CM33 -D_RA_PRIMARY_CORE=CM85 -D_RA_ORDINAL=2`,
  `-std=c99 -fno-strict-aliasing`, the project's warning/debug flags and
  `--param=min-pagesize=0`. The recorded optimization is `-O2`.
- The **recorded original toolchain**, not the compiler on PATH, reports
  `arm-none-eabi-gcc (Arm GNU Toolchain 13.2.rel1 (Build arm-13.7))
  13.2.1 20231009`. Compiler executable SHA-256:
  `fc7c83a32a7c8be08822941f411fe9fe0104508d2982fa9c5a8775c6d33e73d6`.
- `selected-macros.txt` confirms CPU1, C-TCM support, runtime initialization,
  zero C-TCM base and 64-KiB extent. `BSP_TZ_NONSECURE_BUILD` is 0, making
  `BSP_TZ_CFG_SKIP_INIT` false. `BSP_CFG_SKIP_INIT` is **undefined** in this
  generated configuration (therefore evaluates to 0 in `#if`).

## Exact commands and retained artifacts

From `<repo>`:

```sh
RA8P1_TCM_CODEGEN_EVIDENCE=review/evidence/tcm-codegen python3 -m unittest discover -s tools -p 'test_ra8p1_review_tcm_codegen.py' -v
python3 -m unittest discover -s tools -p 'test_ra8p1_review_tcm_codegen.py' -v
```

**Both invocations: 3 tests passed, no skips.** Each invocation compiles all
six objects anew. The evidence-enabled invocation retains each `.o` and its
`arm-none-eabi-objdump -dr` output in the matching `.dis` file.
`commands-and-inputs.json` records **every complete shell-quoted compiler and
objdump command**, exact working directory, original compilation-database
entry, compiler/database/object hashes and SHA-256 of every compiler-reported
input dependency. Only the original input/output filenames change at `-O2`;
other rows additionally replace that single optimization option.

| Optimization | Scrub location | Scrub zero stores / finite exit | Later initialization |
|---|---|---|---|
| `-O0` | Out-of-line `bsp_init_ctcm` | Two word stores; stack-held offset += 4; unsigned compare to 65536; returns | Retained |
| `-Og` | Out-of-line `bsp_init_ctcm` | Two word stores; register offset += 4; unsigned compare to 65536; returns | Retained |
| `-O1` | Inlined in `SystemInit` | Two word stores; offset += 4; compare to 65536; conditional backedge | Retained |
| `-O2` (recorded setting) | Inlined in `SystemInit` | Two word stores; offset += 4; compare to 65536; conditional backedge | Retained |
| `-O3` | Inlined in `SystemInit` | Same scrub instructions as `-O2` | Retained |
| `-Os` | Inlined in `SystemInit` | Same scrub instructions as `-O2` | Retained |

All six compilations return zero with empty compiler diagnostics. The test
compares decoded instructions **and branch destinations**, not source spelling,
and checks later call relocations and out-of-line return instructions. Negative
controls reject a trap, a removed S-TCM store, a self-spinning backedge, and an
elided later initialization call.

## Emitted instructions at the actual `-O2` setting

`O2.dis`, `SystemInit+0x26..0x3a`:

```text
26: 2300       movs   r3, #0
28: 461a       mov    r2, r3
2a: 601a       str    r2, [r3, #0]
2c: f103 5100  add.w  r1, r3, #536870912  ; 0x20000000
30: 3304       adds   r3, #4
32: f5b3 3f80  cmp.w  r3, #65536         ; 0x10000
36: 600a       str    r2, [r1, #0]
38: d1f7       bne.n  2a <SystemInit+0x2a>
3a: f3bf 8f5f  dmb    sy
```

`r2` stays zero. The first `str` writes address **0**, not an alias. Each
iteration writes C-TCM at `offset` and S-TCM at `0x20000000 + offset`, for
`offset = 0, 4, ..., 0xfffc`: **16,384 word writes per 64-KiB window**.
`add.w` calculates the S-TCM address before the increment; `str` does not alter
the comparison flags. The conditional backedge falls through at `0x10000`.

Subsequent emitted instructions remain: error-status clearing at `0x44`, ECC
control writes at `0x48/0x4a`, relock at `0x54`, runtime TCM-copy/clear calls
at `0x6e/0x86/0x9e`, warm callbacks at `0xac/0xd0/0x116`,
`bsp_clock_freq_var_init` at `0xb0`, `SystemCoreClockUpdate` at `0x110`,
`bsp_irq_cfg` at `0x11a`, and tail branch to `bsp_init` at `0x124`.
The raw relocations disambiguate objdump's unresolved `bl 0 <SystemInit>`
placeholders: these are not recursive calls or terminal loops.

## Limits

No production or generated files were edited; no e2 operation, pack action,
hardware access or commit was performed. The test intentionally uses the
existing generated CPU1 header snapshot, with all input hashes recorded;
it is not a refreshed-project or linked-image qualification. Other toolchains,
LTO, different future BSP flags, silicon ECC behavior, and target startup
remain unverified. The theoretical C null-access concern is not a demonstrated
code-generation defect in this qualified GNU13.2.1 configuration.
