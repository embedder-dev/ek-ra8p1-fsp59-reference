# Production WDT host fixture

Run `python3 -m unittest tools.test_ra8p1_wdt -v` from the project root.
The test compiles the complete current `baseline/ra/fsp/src/r_wdt/r_wdt.c`
translation unit, not extracted functions or a rewritten driver. The real
FSP 5.9 `r_wdt.h` and `r_wdt_api.h` supply all public types and APIs.
Only BSP/register and generated configuration dependencies are mocked.

The 30 runtime variants cover CPU0, CPU1 and the legacy register path,
parameter checks enabled/disabled, register-start with NMI/reset and NMI
support compiled out, and auto-start with NMI/reset. Unselected registers
contain sentinels. OFS0 and OFS3 disagree, including their start-mode and
reset/NMI bits, to expose selection of the wrong core's option word.
Invalid pointer/enumeration calls and same-control reopen rejection are
exercised only when parameter checking is enabled; unchecked builds exercise
valid calls. There is no Close API or fabricated close operation.

`WDTRR` is a fixture-only member-name macro recording successive volatile
writes into two bytes. The second byte occupies the reserved hardware byte,
so subsequent register offsets and the 0x100-byte WDT stride stay correct.
The tests assert both refresh write values and order, not just final 0xFF.
`WDTSR` is plain mock storage: clear tests assert the actual W0C bus value;
they do not emulate an asynchronously ticking counter or delayed flag clearing.
Only the BSP NMI/group registration hook is provided. No ordinary IRQ hook
is supplied to hide accidental substitution of an IRQ callback path.

Ten additional compile pairs compare every executable section of the current
legacy-only WDT object with an object compiled from pristine nested-baseline
`git show HEAD:ra/fsp/src/r_wdt/r_wdt.c`. Both use identical headers and flags;
only the production translation unit changes. Native 64-bit Mach-O and ELF
objects are understood. This is host-code regression evidence, not target
instruction equivalence or hardware qualification.

Runtime builds use warnings as errors and non-recovering undefined-behavior
sanitization. All build products and the pristine comparison source live in
temporary directories; no production, IDE, pack or device state is written.
