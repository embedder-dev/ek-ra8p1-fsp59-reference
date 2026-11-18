# EK-RA8P1 migration

Implement EK-RA8P1 support following [MIGRATION.md](MIGRATION.md) and [embedder.md](embedder.md). Verify the baseline, respect source boundaries and preserve older-device behavior.

Start with a plan. It is reviewed before you execute it. Cover the slices below, the order you will integrate them in, what you will delegate, how each slice is verified, and the risks you see.

- **Environment:** the e2 support area is an isolated clean clone (FSP 5.9 only, no RA8P1). Verify it; don't restore anything. Installing candidate packs into it is authorized. No target hardware is attached: report hardware criteria as unverified and don't attempt to program, debug or probe a device.
- **Tools:** use `embedder e2` (discover, generate, build, packs, pins, validate mdf, board check) and the bundled renesas-fsp-mdf, e2-studio and EK-RA8P1 skills. The `tools/` EASE scripts are a fallback only.
- **Pin model:** use Renesas's RA8P1 pin model in `.embedder/pin-model/` (pinmapping/, pinconfig/) as given. Pin ids come from it; never edit, rename or extend it. It is the one permitted FSP 6.0.0 input.
- **Integrate immediately:** generate and clean-build the minimum BSP, then each driver as it becomes available. Fix owning sources and metadata, not generated files.
- Use verified host APIs and exported constants. Check core, compiler, debugger and memory settings independently.
- After pack updates, verify installed packs, extracted support resources and project-source hashes; refresh the stale layer.
- Delegate distinct files, report blockers promptly and continue independent work. Keep handoffs short and avoid long blocking waits.
- Test edge cases and shared-code regressions on the host and in generated builds.

Finish with one table. Rows: CPU0 BSP, CPU1 BSP, EK-RA8P1 board, r_mram, r_dac_b, r_pdm, r_wdt, r_adc, r_cgc. Columns: source, MDF, generated + clean build, validate mdf / board check, host tests, older-device regression, hardware (not run). Then list remaining limitations and intentional behavior changes.
