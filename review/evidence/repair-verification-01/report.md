# Delivered repair verification 01

## Result

**153 tests passed; no failures, errors or skips.** Eight named suites ran together: 146 tests in 175.776 s, exit 0 (`tests.txt`). The separately identified TEST-008 owning-MDF suite passed 7 tests in 0.018 s, exit 0 (`candidate-mdf-tests.txt`). This is focused software evidence, not generated-project or hardware qualification.

| Existing suite (`tools/`) | Passed |
| --- | ---: |
| test_ra8p1_review_dual_cache.py | 13 |
| test_ra8p1_startup.py | 7 |
| test_ra8p1_review_nmi_init.py | 4 |
| test_ra8p1_review_tcm_windows.py | 8 |
| test_ra8p1_candidate.py | 73 |
| test_ra8p1_review_rtos_provenance.py | 16 |
| test_ra8p1_rtos_compatibility.py | 14 |
| test_ra8p1_review_regression_ownership.py (TEST-004/007) | 11 |
| test_ra8p1_candidate_mdf.py | 7 |

## Changed owning source paths inspected

- `baseline/ra/fsp/src/bsp/cmsis/Device/RENESAS/Source/system.c:364–412,616–627,837–845,1042–1108`: per-core hooks restored; CPU1 cold FC/completion/ENC separated from re-enable; extended NMI clearing; bounds checked before MPU encoding.
- `baseline/ra/fsp/src/bsp/mcu/all/bsp_common.h:653–705`: secondary-core/version-zero exclusion prevents CPU0 C-cache access without changing legacy paths.
- `tools/ra8p1/verify_candidate.py:124–168,223–242,266–319,347–391,649–679`: distinct runtime/load TCM windows, strict current MDF ownership, complete fixed vectors and mandatory handlers.
- `tools/ra8p1/stock_regression.py:100–117,380–399,500–565`: deleted owners fail fresh/reused/stability gates; options retain ancestor-qualified ownership and multiplicity.
- `tools/ra8p1/rtos_compatibility.py:97–144,163–238,259–275`: complete owners, disposable overlay replacement, compiler-consumed kernel provenance and exclusive evidence publication.

Current code and executable negative controls support the delivered claims. Cache/MPU/NMI fixtures include original-5.9 legacy comparisons across all 32 older feature headers. Retained real FreeRTOS/ThreadX port and dependency checks ran without skipping. Supporting `compatibility.py` is unchanged from the initial-review hash.

## Evidence and limits

`run.json`, `result.json`, `candidate-mdf-result.json` retain commands, timestamps and hashes; sampled owning/test/fixture/feature inputs were stable throughout execution. `startup-cache-review-repairs.diff` compares exact, hash-reconstructed initial-review bytes with current production bytes (`diff-provenance.json`). Tool files are untracked; available frozen tool text is missing or predates the initial-review hash, so complete repair-only tool diffs could not be certified (`tool-diff-provenance.json`).

Only this exclusively created evidence directory was written. No tests, production, generated projects or ledgers were edited; no e2, pack, hardware or mutating git operations occurred. Existing unrelated warm-start testing was not duplicated; its separate shared-default guard remains outside this verification. Native controlled-register/function parity and Arm compilation do not establish physical cache, startup, MPU or scheduler behavior.
