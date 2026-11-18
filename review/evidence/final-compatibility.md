# FSP 5.9 compatibility: measured before/after

The initial `before-census.json` is one CM85 bare-metal context, not valid RTOS/legacy-variant qualification. Blocked means missing context, not a demonstrated hardware failure. The final stock column means pristine 5.9 source compiled against the final RA8P1 header/BSP; it does not establish correct target behavior. Some modules compile unchanged but need capability-gated behavioral repairs. Final source compilation originated at r017; actual r018 regeneration and unchanged-input/source-ELF proofs are in `expanded/lane2-r018-closure.json`.

| Module | Interface | Initial measurement | Pristine source / final header | Candidate | Disposition |
|---|---|---|---|---|---|
| r_ioport | `ioport_api_t` | pass | pass | pass | Header vocabulary/pin enums; production C unchanged |
| r_cgc | `cgc_api_t` | pass | pass | pass | Capability-gated clock limits, dependencies and sequencing repairs |
| r_wdt | `wdt_api_t` | fail | pass | pass | Per-core option authority, NMI enables and autostart contracts |
| r_iwdt | `wdt_api_t` | pass | pass | pass | Unchanged-source compile gate; no full runtime qualification |
| r_dtc | `transfer_api_t` | pass | pass | pass | Canonical target register views |
| r_dmac | `transfer_api_t` | fail | pass | pass | Canonical channels and truthful DELSR-owner capability |
| r_elc | `elc_api_t` | fail | pass | pass | Canonical arrays/views; eventlink metadata repaired |
| r_icu | `external_irq_api_t` | fail | fail | pass | Genuine IRQCR owner difference needs capability-gated C |
| r_gpt | `timer_api_t` | fail | pass | pass | Pristine compiles; target PDG behavior needs adaptation |
| r_sci_uart | `uart_api_t` | blocked | variant-mismatch | variant-mismatch | Accepted legacy-variant mismatch: target SCI_B, not classic SCI |
| r_sci_b_uart | `uart_api_t` | fail | pass | pass | Correct hardware variant; stock C compiles unchanged |
| r_spi_b | `spi_api_t` | fail | pass | pass | Correct hardware variant; stock C compiles unchanged |
| r_adc_b | `adc_api_t` | fail | pass | pass | Pristine compiles; ADC16H semantics/timing/state/guard repairs required |
| r_dac | `dac_api_t` | blocked | variant-mismatch | variant-mismatch | Accepted legacy-variant mismatch: target DAC_B, not classic DAC |
| rm_freertos_port | `Kernel port ABI` | blocked | pass | pass | Real generated kernel/default/optional/FPU/tickless dependency gates |
| rm_threadx_port | `Kernel port ABI` | blocked | pass | pass | Real generated kernel/default/optional/FPU gates; MDF selector limit open |

## Every changed/new driver interface

The declarations below were read from owning production C. Their function-pointer contracts, generated initializers and callable API probes are checked by source/build gates; a type name alone is not the proof. Existing stock shared API structs were not replaced.

| Driver | Actual interface vtable | Source kind |
|---|---|---|
| r_adc_b | `adc_api_t` / `g_adc_on_adc_b` | changed |
| r_agt | `timer_api_t` / `g_timer_on_agt` | changed |
| r_cgc | `cgc_api_t` / `g_cgc_on_cgc` | changed |
| r_dac_b | `dac_api_t` / `g_dac_on_dac_b` | new |
| r_glcdc | `display_api_t` / `g_display_on_glcdc` | changed |
| r_gpt | `timer_api_t` / `g_timer_on_gpt` | changed |
| r_i3c | `i3c_api_t` / `g_i3c_on_i3c` | changed |
| r_icu | `external_irq_api_t` / `g_external_irq_on_icu` | changed |
| r_lpm | `lpm_api_t` / `g_lpm_on_lpm` | changed |
| r_mipi_dsi | `mipi_dsi_api_t` / `g_mipi_dsi` | changed |
| r_mipi_phy | `mipi_phy_api_t` / `g_mipi_phy` | changed |
| r_mram | `flash_api_t` / `g_flash_on_mram` | new |
| r_ospi_b | `spi_flash_api_t` / `g_ospi_b_on_spi_flash` | changed |
| r_pdm | `pdm_api_t` / `g_pdm_on_pdm` | new |
| r_sci_b_spi | `spi_api_t` / `g_spi_on_sci_b` | changed |
| r_wdt | `wdt_api_t` / `g_wdt_on_wdt` | changed |

- MRAM retains `flash_api_t`/`flash_cfg_t`; safe default write window is empty. Privileged operations default disabled. Counter increment/permanent selection remain source-timing blocked, with explicit errors.
- DAC_B retains `dac_api_t`/`dac_cfg_t`. Hardware-specific configuration stays in its extension; both channel and parameter-checking contracts are exercised.
- PDM has no original 5.9 API. It now follows ctrl/cfg/api + `p_extend` and an API/instance-header split. Earlier custom-candidate direct hardware fields moved to `pdm_extended_cfg_t`; property IDs remain stable.
- OSPI_B retains `spi_flash_api_t`; DMA failures retain ownership/buffers until successful `Close` if cleanup cannot prove quiescence. DOTF is explicitly blocked rather than mapped to invented private registers.
- All 24 final six-driver core/checking clean builds and all 24 source/ELF inspections are fresh r018 results, archived per mode in `review/evidence/r018-parent-driver-matrix.json`.
- ADC requires the documented configuration-only 48 MHz clock recipe, mirrored on its actual CPU0 clock-owner predecessor. No application branch or generated-header patch substitutes for that prerequisite.

## Coverage limits

All 152 census rows remain visible. The raw candidate source aggregate has 53 passes, zero compile failures, 18 blocked, 33 absent and 48 variant mismatches. Of the 60 present stock rows: 50 have all original TUs active, three retain conditional/compiler-dependent gaps, five zero-source components have real dependency-TU/link integrations, and BL2/TF-M remain prerequisite-blocked. The three candidate-only new drivers are qualified separately, not counted as pristine 5.9 sources. Eight additional hardware modes have no corresponding original implementation. See the source audit and owner closures; no aggregate is an all-options/runtime pass.

No hardware, scheduler runtime, analog/audio, persistence, clock stability or full secure/nonsecure deployment qualification was performed.
