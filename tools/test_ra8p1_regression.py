"""Real GNU13 stock object regressions and negative controls for the gate."""
import io
import json
from pathlib import Path
import shlex
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from ra8p1 import regression, stock_regression


ROOT = Path(__file__).resolve().parents[1]


def historical_regress(revision="r008", **kwargs):
    """Replay immutable historical pack inputs, not the evolving current owner.

    Object comparisons and complete historical coverage assertions remain active.
    Current ICU/RTOS/LPM adaptations belong to the separate follow-up gate.
    """
    manifest = json.loads((ROOT / regression.MANIFEST).read_text())
    original = stock_regression.original_files(ROOT, manifest)
    path = ROOT / "validation/ra8p1/packs" / revision / "manifest.json"
    candidate = json.loads(path.read_text())
    frozen = {}
    for name, spec in candidate["packs"].items():
        if name != "Renesas.RA.5.9.0.pack" and not name.startswith("Renesas.RA_mcu_"):
            continue
        archive = path.parent / name
        if regression.sha256(archive.read_bytes()) != spec["sha256"]:
            raise ValueError("Historical pack archive drift: " + name)
        with zipfile.ZipFile(archive) as package:
            for entry, digest in spec["entries"].items():
                if entry not in original or not entry.startswith("ra/fsp/"):
                    continue
                if not entry.endswith((".c", ".h", ".S", ".s")):
                    continue
                data = package.read(entry)
                if regression.sha256(data) != digest:
                    raise ValueError("Historical pack entry drift: " + entry)
                if data != original[entry]:
                    frozen[entry] = (original[entry], data)
    if not frozen:
        raise ValueError("Historical candidate has no changed shared inputs")
    review_metadata = regression.review_metadata

    def historical_metadata(root, historical, candidate_path=None):
        packs = regression.stock_packs(root, historical)
        with tempfile.TemporaryDirectory(prefix="fsp-historical-metadata-") as temp:
            frozen_root = Path(temp)
            folder = frozen_root / "baseline/module_descriptions"
            folder.mkdir(parents=True)
            for name, (_, files) in packs.items():
                if name in ("Renesas.RA", "Arm.CMSIS6"):
                    continue
                for entry, data in files.items():
                    if entry.startswith(".module_descriptions/"):
                        (folder / Path(entry).name).write_bytes(data)
            with patch.object(regression, "stock_packs", return_value=packs):
                result = review_metadata(frozen_root, historical, candidate_path)
            result["scope"] = "Immutable historical pack/metadata inputs; NOT current owning freshness"
            return result

    with patch.object(regression, "snapshot", return_value=frozen), \
            patch.object(regression, "review_metadata", side_effect=historical_metadata):
        return regression.regress(**kwargs)


class StockRegressionTests(unittest.TestCase):
    def test_changed_ra8m1_and_ra6t2_objects_match_head_and_capture(self):
        report = regression.regress()
        self.assertTrue(report["success"], json.dumps(report, indent=2))
        required = {
            "ra/fsp/src/bsp/cmsis/Device/RENESAS/Source/system.c",
            "ra/fsp/src/bsp/mcu/all/bsp_clocks.c",
            "ra/fsp/src/bsp/mcu/all/bsp_irq.c",
            "ra/fsp/src/bsp/mcu/all/bsp_register_protection.c",
            "ra/fsp/src/bsp/mcu/all/bsp_rom_registers.c",
            "ra/fsp/src/bsp/mcu/all/bsp_sdram.c",
            "ra/fsp/src/bsp/mcu/all/bsp_security.c",
        }
        for name in ("ra8m1", "ra6t2"):
            fixture = report["fixtures"][name]
            self.assertEqual(fixture["compiler_version"], "13.2.1")
            self.assertTrue(required <= fixture["translation_units"].keys())
            for relative, tu in fixture["translation_units"].items():
                self.assertTrue(tu["matches_head_and_capture"], relative)
                self.assertNotIn("bsp_common.c", relative)
                self.assertNotIn("r_wdt.c", relative)
            self.assertTrue(any(path.endswith("bsp_feature.h") for path in fixture["owning_source_overlay"]))
            self.assertIn("ra/fsp/inc/fsp_features.h", fixture["owning_source_overlay"])
            self.assertIn("ra/fsp/src/bsp/mcu/all/bsp_common.h", fixture["owning_source_overlay"])
        self.assertIn("ra/fsp/src/r_adc_b/r_adc_b.c", report["fixtures"]["ra6t2"]["translation_units"])
        # Missing CGC fixtures are visible coverage debt, never a passed CGC build.
        if not any(path.endswith("/r_cgc.c") for fixture in report["fixtures"].values()
                   for path in fixture["translation_units"]):
            self.assertIn("ra/fsp/src/r_cgc/r_cgc.c", report["uncovered_changed_translation_units"])

    def test_lazy_dependencies_have_executable_parent_commands(self):
        pending = regression.lazy_dependencies(ROOT)
        self.assertEqual(set(pending), {"ra8d1", "ra4m2", "ra4m1", "ra0e1"})
        for name, dependency in pending.items():
            self.assertNotEqual(dependency["status"], "passed")
            commands = dependency["parent_next_commands"]
            self.assertIn("--add r_cgc:g_cgc0 --build", commands[2])
            self.assertIn("--fsp 5.9.0", commands[1])
            self.assertNotIn("--core", commands[1])  # These stock boards are single-core.
            self.assertIn(name, commands[3])

    def test_archive_drift_and_unsafe_members_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "fixture.tar.gz"
            with tarfile.open(archive, "w:gz") as package:
                member = tarfile.TarInfo("stock/../../outside")
                member.size = 3
                package.addfile(member, io.BytesIO(b"bad"))
            spec = {"archive": archive.name, "archive_root": "stock", "sha256": "0" * 64}
            with self.assertRaisesRegex(ValueError, "hash drift"):
                regression.unpack_fixture(root, spec, root / "scratch")
            spec["sha256"] = regression.sha256(archive.read_bytes())
            with self.assertRaisesRegex(ValueError, "Unsafe fixture"):
                regression.unpack_fixture(root, spec, root / "scratch")
            self.assertFalse((root / "outside").exists())


class OriginalPackControlTests(unittest.TestCase):
    def test_native_pack_controls_compare_real_changed_tus(self):
        report = historical_regress(direct=list(regression.LAZY))
        errors = {name: entry.get("error") for name, entry in report["pack_controls"].items() if not entry["success"]}
        self.assertTrue(report["success"], json.dumps(errors, indent=2))
        self.assertEqual(report["uncovered_by_any_object_control"], [])
        self.assertIn("ra/fsp/src/r_cgc/r_cgc.c", report["uncovered_changed_translation_units"])
        for device, entry in report["pack_controls"].items():
            self.assertIn("NOT an e2-generated", entry["scope"])
            self.assertIn("unverified", entry["generated_control"])
            self.assertEqual(entry["compiler_version"], "13.2.1")
            self.assertEqual(set(entry["translation_units"]),
                             set(report["lazy_dependencies"][device]["changed_translation_units"]))
            for relative, unit in entry["translation_units"].items():
                self.assertTrue(unit["matches_pristine_original_release"], relative)
                self.assertNotIn("r_wdt.c", relative)
                self.assertNotIn("r_adc_b.c", relative)
            cgc = entry["translation_units"]["ra/fsp/src/r_cgc/r_cgc.c"]
            self.assertTrue(any(s["kind"] == "executable" for s in cgc["sections"].values()))
            self.assertTrue(entry["configs"]["ra_gen/bsp_clock_cfg.h"]["scratch_overrides"])
        native = report["pack_controls"]["ra0e1"]
        self.assertEqual(native["core"], "cm23")
        self.assertIn("-mcpu=cortex-m23", next(iter(native["translation_units"].values()))["command"])
        sdram = report["pack_controls"]["ra8d1"]["translation_units"]["ra/fsp/src/bsp/mcu/all/bsp_sdram.c"]
        self.assertGreater(sdram["sections"][".text.R_BSP_SdramInit"]["size"], 0)
        for device in ("ra4m2", "ra4m1", "ra0e1"):
            unit = report["pack_controls"][device]["translation_units"]["ra/fsp/src/bsp/mcu/all/bsp_sdram.c"]
            self.assertTrue(unit["conditional_empty"])  # No invented SDRAM on unsupported devices.

    def test_original_mdf_renderer_rejects_unknown_or_executable_templates(self):
        for text in ("${unknown}", "[#if unknown]1[/#if]"):
            element = ET.fromstring(f'<config path="test.h"><content>{text}</content></config>')
            with self.assertRaisesRegex(ValueError, "Unresolved|unsupported"):
                regression.render_config(element, {})
        element = ET.fromstring('<config path="test.h"><property id="value" default="1"><export>eval()</export></property><content>${value}</content></config>')
        with self.assertRaisesRegex(ValueError, "Unsupported original property export"):
            regression.render_config(element, {})

    def test_only_hash_verified_original_release_is_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "reference").mkdir()
            (root / "release.zip").write_bytes(b"not the original release")
            spec = {"archive": "release.zip", "sha256": "0" * 64}
            provenance = {"baseline": {"archive": {"path": spec["archive"], "sha256": spec["sha256"]}}}
            (root / "reference/provenance.json").write_text(json.dumps(provenance))
            with self.assertRaisesRegex(ValueError, "Original release archive hash drift"):
                regression.stock_packs(root, {"stock_release": spec})
            spec["archive"] = "newer.zip"
            with self.assertRaisesRegex(ValueError, "preserved provenance"):
                regression.stock_packs(root, {"stock_release": spec})


class GeneratedControlTests(unittest.TestCase):
    def test_actual_generated_controls_checks_on_off_match_pristine(self):
        report = historical_regress("r006", generated=True)
        errors = {name: entry.get("error") for name, entry in report["generated_fixtures"].items()
                  if not entry["success"]}
        self.assertTrue(report["success"], json.dumps(errors, indent=2))
        self.assertEqual(report["missing_generated_fixtures"], [])
        self.assertEqual(report["uncovered_by_any_object_control"], [])
        self.assertEqual(len(report["generated_fixtures"]), 8)
        for device in regression.LAZY:
            enabled = report["generated_fixtures"][device + "_checks_on"]
            disabled = report["generated_fixtures"][device + "_checks_off"]
            self.assertEqual((enabled["checks"], disabled["checks"]), (1, 0))
            for entry in (enabled, disabled):
                self.assertIn("NOT original generated stock capture", entry["scope"])
                self.assertEqual(entry["compiler_version"], "13.2.1")
                self.assertTrue(entry["generated_inputs"])
                for relative, unit in entry["translation_units"].items():
                    self.assertTrue(unit["matches_pristine_in_generated_config"], relative)
                    self.assertTrue(unit["matches_candidate_capture"], relative)
                    self.assertEqual(unit["current_diagnostics"], "", relative)
                    self.assertEqual(unit["pristine_diagnostics"], "", relative)
            drivers = ("r_cgc",) if device == "ra0e1" else ("r_cgc", "r_wdt")
            for driver in drivers:
                relative = f"ra/fsp/src/{driver}/{driver}.c"
                on, off = (entry["translation_units"][relative]["sections"] for entry in (enabled, disabled))
                self.assertNotEqual(on, off, "Parameter checks must affect real driver code")
                self.assertGreater(sum(s["size"] for s in on.values()), sum(s["size"] for s in off.values()))
        review = report["metadata_review"]
        self.assertGreater(len(review["old_metadata"]), 50)
        for name, item in review["shared_defaults"].items():
            self.assertTrue(item["defaults_unchanged"], name)
            self.assertTrue(item["existing_constraints_unchanged"], name)
            self.assertTrue(item["guards_nsc_signals_unchanged"], name)
            if "##r_adc_b##" not in name:
                self.assertTrue(item["bytes_unchanged"], name)
        self.assertEqual(report["older_module_gates"]["not_creatable"], ["r_mram", "r_dac_b", "r_pdm"])

    def test_final_r008_six_controls_preserve_pristine_and_candidate_bytes(self):
        report = historical_regress("r008", generated="r008")
        errors = {name: entry.get("error") for name, entry in report["generated_fixtures"].items()
                  if not entry["success"]}
        self.assertTrue(report["success"], json.dumps(errors, indent=2))
        self.assertEqual(report["missing_generated_fixtures"], [])
        self.assertEqual(report["uncovered_by_any_object_control"], [])
        self.assertEqual(len(report["generated_fixtures"]), 12)
        for device in ("ra8m1", "ra6t2", *regression.LAZY):
            enabled = report["generated_fixtures"][device + "_checks_on"]
            disabled = report["generated_fixtures"][device + "_checks_off"]
            self.assertEqual((enabled["checks"], disabled["checks"]), (1, 0))
            for entry in (enabled, disabled):
                self.assertEqual(entry["candidate_revision"], "r008")
                self.assertTrue(all(item["current_owner_matches_candidate"]
                                    for item in entry["owning_source_overlay"].values()))
                for relative, unit in entry["translation_units"].items():
                    self.assertTrue(unit["matches_pristine_in_generated_config"], relative)
                    self.assertTrue(unit["matches_candidate_capture"], relative)
                    self.assertEqual(unit["current_diagnostics"], "", relative)
                    self.assertEqual(unit["pristine_diagnostics"], "", relative)
            cgc = "ra/fsp/src/r_cgc/r_cgc.c"
            self.assertNotEqual(enabled["translation_units"][cgc]["sections"],
                                disabled["translation_units"][cgc]["sections"])
            if device == "ra6t2":
                for entry in (enabled, disabled):
                    self.assertTrue(entry["legacy_gain_aliases"]["success"])
                    self.assertEqual(entry["legacy_gain_aliases"]["assertions"], 32)
                    self.assertEqual(entry["legacy_gain_aliases"]["diagnostics"], "")

    def test_stock_archive_evidence_is_independent_of_refreshed_live_project(self):
        manifest = json.loads((ROOT / regression.MANIFEST).read_text())
        spec = dict(manifest["fixtures"]["ra8m1"], project="deliberately-not-a-live-project")
        changed = regression.snapshot(ROOT, manifest)
        result = regression.check_fixture(ROOT, spec, changed, "13.2.1")
        self.assertTrue(result["success"])
        self.assertTrue(all(tu["matches_head_and_capture"] for tu in result["translation_units"].values()))
        self.assertIn("Frozen original-stock archive", result["scope"])

    def test_real_legacy_gain_macro_drift_fails_compile_assertions(self):
        manifest = json.loads((ROOT / regression.MANIFEST).read_text())
        spec = manifest["final_generated"]["fixtures"]["ra6t2_checks_on"]
        with tempfile.TemporaryDirectory() as temp:
            scratch = Path(temp)
            tree = scratch / "project"
            regression.unpack_fixture(ROOT, spec, tree)
            rows = json.loads((tree / "Debug/compile_commands.json").read_text())
            selected = [(Path(row["file"]).relative_to(Path(row["directory"]).parent).as_posix(), row)
                        for row in rows]
            header = tree / "ra/fsp/inc/instances/r_adc_b.h"
            original = header.read_bytes()
            corrupted = original.replace(b"(0x3FFFFF)", b"(0x3FFFFE)")
            self.assertNotEqual(corrupted, original)
            header.write_bytes(corrupted)
            with self.assertRaisesRegex(ValueError, "legacy gain"):
                regression.check_legacy_gain_aliases(tree, scratch, selected)

    def test_generated_label_and_build_evidence_drift_fail(self):
        manifest = json.loads((ROOT / regression.MANIFEST).read_text())
        spec = dict(manifest["generated_fixtures"]["ra8d1_checks_on"])
        candidate = ROOT / manifest["generated_candidate_manifest"]
        spec["checks"] = 0
        with self.assertRaisesRegex(ValueError, "parameter checking"):
            regression.check_generated_fixture(ROOT, spec, {}, "13.2.1", candidate)
        spec["candidate_manifest_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "manifest drift"):
            regression.check_generated_fixture(ROOT, spec, {}, "13.2.1", candidate)
        spec["candidate_manifest_sha256"] = manifest["generated_fixtures"]["ra8d1_checks_on"]["candidate_manifest_sha256"]
        spec["build_log_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "build evidence drift"):
            regression.check_generated_fixture(ROOT, spec, {}, "13.2.1", candidate)

    def test_real_changed_call_target_fails_generated_control(self):
        manifest = json.loads((ROOT / regression.MANIFEST).read_text())
        changed = regression.snapshot(ROOT, manifest)
        relative = "ra/fsp/src/bsp/mcu/all/bsp_clocks.c"
        pristine, current = changed[relative]
        changed[relative] = (pristine, current + b"\nextern void regression_wrong_target(void);\n"
                             b"void regression_drift(void) { regression_wrong_target(); }\n")
        with self.assertRaisesRegex(ValueError, "section drift"):
            regression.check_generated_fixture(ROOT, manifest["generated_fixtures"]["ra8d1_checks_on"],
                                               changed, "13.2.1", ROOT / manifest["generated_candidate_manifest"])

    def test_module_gate_requires_real_absent_listing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = b'embedder e2 config get control --creatable r_mram --lane 2\n1 modules matching "r_mram"\n'
            (root / "gate.log").write_bytes(data)
            spec = {"log": "gate.log", "sha256": regression.sha256(data), "project": "control", "drivers": ["r_mram"]}
            with self.assertRaisesRegex(ValueError, "not proven absent"):
                regression.check_module_gates(root, spec)


class ObjectComparatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Use the recorded compiler, not PATH, Clang, a mock or a newer pack.
        db = json.loads((ROOT / "validation/stock/Debug/compile_commands.json").read_text())
        cls.compiler = shlex.split(db[0]["command"])[0]
        cls.assert_compiler_version = regression.run([cls.compiler, "-dumpfullversion"]).decode().strip()
        if cls.assert_compiler_version != "13.2.1":
            raise AssertionError("Recorded compiler is not GNU13.2.1")

    def compile(self, directory, source, name="test"):
        path = directory / (name + ".c")
        path.write_text(source)
        output = directory / (name + ".o")
        regression.run([self.compiler, "-mcpu=cortex-m85", "-mthumb", "-O2", "-g",
                        "-ffunction-sections", "-fdata-sections", "-c", str(path), "-o", str(output)])
        return output.read_bytes()

    def test_real_code_and_constant_drift_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = self.compile(root, "const int c = 5; int f(void) { return 1; }")
            for source, section in (("const int c = 5; int f(void) { return 2; }", ".text.f"),
                                    ("const int c = 6; int f(void) { return 1; }", ".rodata.c")):
                candidate = self.compile(root, source)
                with self.assertRaisesRegex(ValueError, section):
                    regression.compare(original, candidate, "negative control")

    def test_changed_relocation_target_fails_despite_equal_code_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = self.compile(root, "extern int first(void); int f(void) { return first(); }")
            candidate = self.compile(root, "extern int other(void); int f(void) { return other(); }")
            before = regression.readonly_sections(original)[".text.f"]
            after = regression.readonly_sections(candidate)[".text.f"]
            self.assertEqual(before["sha256"], after["sha256"])
            self.assertNotEqual(before["relocations"], after["relocations"])
            with self.assertRaisesRegex(ValueError, "section drift"):
                regression.compare(original, candidate, "relocation negative control")

    def test_debug_paths_and_writable_data_are_outside_section_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = self.compile(root, "int ram = 1; int f(void) { return 7; }", "before")
            candidate = self.compile(root, "int ram = 2; int f(void) { return 7; }", "after")
            self.assertNotEqual(original, candidate)
            self.assertTrue(regression.compare(original, candidate, "scope check"))

    def test_invalid_object_and_compile_failure_are_not_success(self):
        with self.assertRaisesRegex(ValueError, "ELF32"):
            regression.readonly_sections(b"not an object")
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "Command failed"):
                self.compile(Path(temp), "#error deliberate compile negative control\n")

    def test_relocated_assertion_filename_matches_capture_without_masking_constants(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            captured, scratch = root / "captured", root / "scratch"
            captured.mkdir()
            scratch.mkdir()
            source = 'const char filename[] = __FILE__;\nconst unsigned line = __LINE__;\n'
            for directory in (captured, scratch):
                (directory / "test.c").write_text(source)
                (directory / "Debug").mkdir()
                (directory / "Debug/test.o.in").write_text('-c -o test.o -x c ../test.c')
            flags = [self.compiler, "-mcpu=cortex-m4", "-mthumb", "-O2", "-c"]
            original = captured / "test.o"
            regression.run([*flags, "../test.c", "-o", str(original)], cwd=captured / "Debug")
            output = scratch / "test.o"
            command = [*flags, str(scratch / "test.c"), "-o", str(output)]
            regression.run(command, cwd=scratch / "Debug")
            with self.assertRaisesRegex(ValueError, "section drift"):
                regression.compare(original.read_bytes(), output.read_bytes(), "unmapped path")
            row = {"directory": str(captured / "Debug"), "file": str(captured / "test.c")}
            mapped = stock_regression.preserve_captured_file_macros(command, row, scratch)
            self.assertEqual(len(mapped), len(command))
            self.assertEqual(mapped, [*flags, "../test.c", "-o", str(output)])
            regression.run(mapped, cwd=scratch / "Debug")
            self.assertTrue(regression.compare(original.read_bytes(), output.read_bytes(), "mapped path"))
            (scratch / "test.c").write_text(source.replace("__LINE__", "99"))
            regression.run(mapped, cwd=scratch / "Debug")
            with self.assertRaisesRegex(ValueError, "section drift"):
                regression.compare(original.read_bytes(), output.read_bytes(), "real constant drift")

    def test_compile_relocation_preserves_fixture_flags_and_includes(self):
        rows = json.loads((ROOT / "validation/stock/Debug/compile_commands.json").read_text())
        row = next(row for row in rows if row["file"].endswith("/bsp_clocks.c"))
        command = shlex.split(row["command"])
        with tempfile.TemporaryDirectory() as temp:
            scratch = Path(temp)
            output = scratch / "new.o"
            mapped, cwd, relative = regression.compile_command(row, scratch, output)
            oldroot = str(Path(row["directory"]).parent)
            expected = [arg.replace(oldroot + "/", str(scratch) + "/") for arg in command]
            expected[expected.index("-o") + 1] = str(output)
            self.assertEqual(mapped, expected)
            self.assertEqual(cwd, scratch / "Debug")
            self.assertEqual(relative.as_posix(), "ra/fsp/src/bsp/mcu/all/bsp_clocks.c")


class CompatibilityFollowupRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.historical = json.loads((ROOT / regression.MANIFEST).read_text())
        cls.candidate = ROOT / cls.historical["final_generated"]["candidate_manifest"]

    def fixture(self):
        return dict(self.historical["final_generated"]["fixtures"]["ra4m1_checks_on"],
                    required_translation_units=[stock_regression.ICU])

    def test_read_only_inventory_reports_all_six_actual_command_sets(self):
        report = stock_regression.inventory()
        self.assertFalse(report["success"])
        self.assertEqual(set(report["controls"]), {"ra8m1", "ra6t2", "ra8d1", "ra4m2", "ra4m1", "ra0e1"})
        self.assertIn(stock_regression.ICU, report["changed_translation_units"])
        self.assertEqual(report["controls"]["ra4m1"]["stack_monitor_capability"], 1)
        for control in report["controls"].values():
            database = ROOT / control["project"] / "Debug/compile_commands.json"
            rows = stock_regression.source_rows(json.loads(database.read_text()))
            self.assertEqual(control["icu_command_present"], stock_regression.ICU in rows)
            self.assertEqual(control["rtos_commands"], sorted(path for path in rows
                             if any("/" + port + "/" in path for port in stock_regression.PORTS)))
            self.assertNotEqual(control["status"], "passed")

    def test_historical_controls_cannot_claim_new_icu_comparison(self):
        with self.assertRaisesRegex(ValueError, "Missing real generated commands.*r_icu.c"):
            stock_regression.check_fixture(ROOT, self.fixture(), {}, "13.2.1", self.candidate)

    def test_real_historical_command_exercises_new_comparison_engine(self):
        # Tests the runner, not the new compatibility requirement: r008 has no ICU.
        path = "ra/fsp/src/r_cgc/r_cgc.c"
        pristine = regression.run(["git", "-C", str(ROOT / "baseline"), "show", "HEAD:" + path])
        spec = dict(self.fixture(), required_translation_units=[path],
                    macro_expectations={path: {"BSP_CFG_PARAM_CHECKING_ENABLE": "(1)",
                                               "BSP_FEATURE_BSP_HAS_SP_MON": "(1UL)"}})
        with tarfile.open(ROOT / spec["archive"]) as package:
            current = package.extractfile(spec["archive_root"] + "/" + path).read()
        report = stock_regression.check_fixture(ROOT, spec, {path: (pristine, current)}, "13.2.1", self.candidate)
        self.assertTrue(report["success"])
        unit = report["translation_units"][path]
        self.assertTrue(unit["matches_pristine"])
        self.assertTrue(unit["matches_candidate_capture"])
        self.assertTrue(any(s["kind"] == "executable" for s in unit["sections"].values()))
        self.assertEqual(unit["candidate_diagnostics"], "")
        self.assertNotIn(stock_regression.ICU, report["translation_units"])
        self.assertTrue(report["generated_inputs"])

    def test_working_tree_replay_cannot_qualify_a_current_generated_build(self):
        path = "ra/fsp/src/r_cgc/r_cgc.c"
        spec = dict(self.fixture(), required_translation_units=[path])
        with tarfile.open(ROOT / spec["archive"]) as package:
            captured = package.extractfile(spec["archive_root"] + "/" + path).read()
        # A source-only change must still be rejected by the frozen-build gate,
        # even when the retained flags emit identical executable/constant bytes.
        inputs = {path: (captured, captured + b"\n")}
        with self.assertRaisesRegex(ValueError, "Frozen owner/project/pack mismatch"):
            stock_regression.check_fixture(ROOT, spec, inputs, "13.2.1", self.candidate)
        result = stock_regression.check_fixture(ROOT, spec, inputs, "13.2.1", self.candidate,
                                               working_tree=True)
        self.assertTrue(result["success"])
        self.assertFalse(result["current_generated_build_verified"])
        self.assertIn("NOT a current generated build", result["scope"])
        self.assertFalse(result["owning_source_overlay"][path]["owner_matches_generated"])
        self.assertTrue(result["translation_units"][path]["matches_pristine"])

    def test_working_tree_replay_still_rejects_real_code_drift(self):
        path = "ra/fsp/src/r_cgc/r_cgc.c"
        spec = dict(self.fixture(), required_translation_units=[path])
        with tarfile.open(ROOT / spec["archive"]) as package:
            captured = package.extractfile(spec["archive_root"] + "/" + path).read()
        current = captured + b"\nunsigned regression_wrong_value(void) { return 123; }\n"
        with self.assertRaisesRegex(ValueError, "Original release versus candidate.*section drift"):
            stock_regression.check_fixture(ROOT, spec, {path: (captured, current)}, "13.2.1", self.candidate,
                                           working_tree=True)

    def test_header_only_port_adaptation_requires_all_port_translation_units(self):
        prefix = "ra/fsp/src/rm_freertos_port/"
        original = {prefix + name: b"original" for name in ("port.c", "portasm.S", "portmacro.h")}
        changed = {prefix + "portmacro.h": (b"original", b"candidate")}
        self.assertEqual(stock_regression.affected_units(changed, original),
                         [prefix + "port.c", prefix + "portasm.S"])

    def test_icu_coverage_is_required_per_control_and_parameter_mode(self):
        specs = {"on": {"group": "RA4M1", "checks": 1}, "off": {"group": "RA4M1", "checks": 0}}
        fixtures = {"on": {"success": True, "translation_units": {stock_regression.ICU: {}}},
                    "off": {"success": True, "translation_units": {}}}
        uncovered, missing, _ = stock_regression.coverage_gaps(fixtures, specs, [stock_regression.ICU], ["ra4m1"])
        self.assertEqual(uncovered, [])
        self.assertEqual(missing, ["ra4m1_checks_0 (including changed ICU)"])

    def test_rtos_default_only_objects_do_not_cover_optional_branches(self):
        path = "ra/fsp/src/rm_freertos_port/port.c"
        specs = {"on": {"group": "RA4M1", "checks": 1}, "off": {"group": "RA4M1", "checks": 0}}
        fixtures = {name: {"success": True, "translation_units": {path: {}}, "active_options": {}}
                    for name in specs}
        uncovered, missing, options = stock_regression.coverage_gaps(fixtures, specs, [path], ["ra4m1"])
        self.assertEqual((uncovered, missing), ([], []))
        self.assertTrue(any("HAS_SP_MON" in item for item in options))
        self.assertTrue(any("TICKLESS_IDLE=1" in item for item in options))
        for name, value in (("on", "1"), ("off", "0")):
            fixtures[name]["active_options"][path] = {"BSP_FEATURE_BSP_HAS_SP_MON": "(1UL)",
                                                     "configUSE_TICKLESS_IDLE": value}
        self.assertEqual(stock_regression.coverage_gaps(fixtures, specs, [path], ["ra4m1"]), ([], [], []))

    def test_manifest_build_log_and_required_unit_guards(self):
        spec = dict(self.fixture(), candidate_manifest_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "manifest drift"):
            stock_regression.validate_evidence(ROOT, spec, self.candidate)
        spec = dict(self.fixture(), build_log_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "build evidence drift"):
            stock_regression.validate_evidence(ROOT, spec, self.candidate)
        spec = dict(self.fixture(), required_translation_units=[])
        with self.assertRaisesRegex(ValueError, "required translation units"):
            stock_regression.validate_evidence(ROOT, spec, self.candidate)

    def test_r009_generated_captures_cover_icu_on_all_six_controls(self):
        folder = ROOT / "validation/ra8p1/compatibility/regression"
        manifest = json.loads((folder / "r009-fixtures.json").read_text())
        report = json.loads((folder / "r009-hal-results.json").read_text())
        candidate = ROOT / manifest["candidate_manifest"]
        historical_devices = self.historical["final_generated"]["projects"]
        for device in historical_devices:
            for mode in ("on", "off"):
                name = device + "_checks_" + mode
                spec, result = manifest["fixtures"][name], report["fixtures"][name]
                stock_regression.validate_evidence(ROOT, spec, candidate)
                self.assertEqual(regression.sha256((ROOT / spec["archive"]).read_bytes()), spec["sha256"])
                self.assertTrue(result["success"], result.get("error"))
                icu = result["translation_units"][stock_regression.ICU]
                self.assertTrue(icu["matches_pristine"])
                self.assertTrue(icu["matches_candidate_capture"])
                self.assertEqual(result["candidate_manifest_sha256"], spec["candidate_manifest_sha256"])
                self.assertTrue(any(section["kind"] == "executable" for section in icu["sections"].values()))
        # HAL success is not a false claim that historical/no-RTOS fixtures
        # cover the newly adapted port sources or their optional branches.
        self.assertFalse(report["success"])
        self.assertTrue(any("rm_freertos_port" in path for path in report["uncovered_translation_units"]))
        self.assertTrue(any("rm_threadx_port" in path for path in report["uncovered_translation_units"]))

    def test_kernel_dependencies_must_match_original_release_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            tree = Path(temp)
            name = "ra/aws/FreeRTOS/FreeRTOS/Source/include/FreeRTOS.h"
            header = tree / name
            header.parent.mkdir(parents=True)
            header.write_bytes(b"original kernel header")
            required = ["ra/fsp/src/rm_freertos_port/port.c"]
            original = {name: header.read_bytes()}
            self.assertEqual(stock_regression.kernel_inputs(tree, required, original),
                             {name: regression.sha256(header.read_bytes())})
            header.write_bytes(b"fabricated kernel header")
            with self.assertRaisesRegex(ValueError, "Kernel dependency differs from original"):
                stock_regression.kernel_inputs(tree, required, original)
            with self.assertRaisesRegex(ValueError, "Missing hash-verified original kernel"):
                stock_regression.kernel_inputs(tree, required, None)

    def test_duplicate_generated_commands_are_rejected(self):
        row = {"directory": "/project/Debug", "file": "/project/ra/fsp/src/r_icu/r_icu.c"}
        with self.assertRaisesRegex(ValueError, "Duplicate generated compile command"):
            stock_regression.source_rows([row, row])


class FinalRevisionRegressionTests(unittest.TestCase):
    def test_immutable_metadata_review_does_not_weaken_default_owner_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            candidate = root / "manifest.json"
            candidate.write_text(json.dumps({"packs": {}}))
            path = ".module_descriptions/Renesas##HAL Drivers##all##r_test####5.9.0.xml"
            packed = b"<raModuleDescription/>"
            owner = root / "baseline/module_descriptions" / Path(path).name
            owner.parent.mkdir(parents=True)
            owner.write_bytes(b"<raModuleDescription>changed owner</raModuleDescription>")
            with patch.object(regression, "stock_packs", return_value={"Renesas.RA": (None, {path: packed})}):
                with self.assertRaisesRegex(ValueError, "Owning metadata differs"):
                    stock_regression.review_metadata(root, {}, candidate)
                result = stock_regression.review_metadata(root, {}, candidate, check_owning=False)
                self.assertTrue(result["success"])
                self.assertFalse(result["current_owning_metadata_checked"])
                self.assertIn("NOT current owning freshness", result["scope"])

    def test_reuse_rejects_changed_source_archive_and_failed_comparisons(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive, log, candidate = root / "fixture.tar.gz", root / "build.log", root / "manifest.json"
            archive.write_bytes(b"immutable archive")
            log.write_bytes(b"verified: yes\nclean: ok\n")
            candidate.write_bytes(b"frozen candidate")
            path = "ra/fsp/src/test.c"
            inputs = {path: (b"original", b"current")}
            spec = {"group": "RA4M1", "checks": 0, "archive": archive.name,
                    "sha256": regression.sha256(archive.read_bytes()), "build_log": log.name,
                    "build_log_sha256": regression.sha256(log.read_bytes()),
                    "candidate_manifest_sha256": regression.sha256(candidate.read_bytes()),
                    "required_translation_units": [path]}
            entry = {"success": True, "current_generated_build_verified": True,
                     "group": spec["group"], "checks": 0, "archive_sha256": spec["sha256"],
                     "candidate_manifest_sha256": spec["candidate_manifest_sha256"],
                     "owning_source_overlay": {path: {"pristine_sha256": regression.sha256(b"original"),
                         "candidate_sha256": regression.sha256(b"current"), "owner_matches_generated": True}},
                     "translation_units": {path: {"matches_pristine": True, "matches_candidate_capture": True,
                         "command": [__file__], "compiler_sha256": regression.sha256(Path(__file__).read_bytes())}}}
            result = stock_regression.reuse_fixture(root, spec, entry, inputs, candidate)
            self.assertTrue(result["reused_unchanged_inputs"])
            with self.assertRaisesRegex(ValueError, "owning inputs drift"):
                stock_regression.reuse_fixture(root, spec, entry, {path: (b"original", b"edited")}, candidate)
            entry["translation_units"][path]["matches_pristine"] = False
            with self.assertRaisesRegex(ValueError, "comparison/compiler drift"):
                stock_regression.reuse_fixture(root, spec, entry, inputs, candidate)
            archive.write_bytes(b"edited archive")
            with self.assertRaisesRegex(ValueError, "archive drift"):
                stock_regression.reuse_fixture(root, spec, entry, inputs, candidate)

    def test_target_only_clock_and_agt_capabilities_must_be_defined_legacy_zero(self):
        for path, names in stock_regression.LEGACY_CAPABILITIES.items():
            for name in names:
                with self.subTest(path=path, macro=name):
                    stock_regression.validate_legacy_capabilities(path, {name: "(0UL)"})
                    with self.assertRaisesRegex(ValueError, "Unresolved generated integer"):
                        stock_regression.validate_legacy_capabilities(path, {})
                    with self.assertRaisesRegex(ValueError, "target-only capability"):
                        stock_regression.validate_legacy_capabilities(path, {name: "(1UL)"})

    def test_shared_clock_owner_requires_each_control_in_both_checking_modes(self):
        specs = {device + str(checks): {"group": device.upper(), "checks": checks}
                 for device in stock_regression.CONTROL_DRIVERS for checks in (0, 1)}
        fixtures = {name: {"success": True, "translation_units": {stock_regression.CLOCKS: {}}}
                    for name in specs}
        self.assertEqual(stock_regression.coverage_gaps(
            fixtures, specs, [stock_regression.CLOCKS], stock_regression.CONTROL_DRIVERS), ([], [], []))
        fixtures["ra8d10"]["translation_units"] = {}
        uncovered, missing, rtos = stock_regression.coverage_gaps(
            fixtures, specs, [stock_regression.CLOCKS], stock_regression.CONTROL_DRIVERS)
        self.assertEqual((uncovered, rtos), ([], []))
        self.assertEqual(missing, ["ra8d1_checks_0 (including changed bsp_clocks)"])

    def test_sci_and_dsi_need_each_supported_control_in_both_modes(self):
        sci = "ra/fsp/src/r_sci_b_spi/r_sci_b_spi.c"
        dsi = "ra/fsp/src/r_mipi_dsi/r_mipi_dsi.c"
        specs = {device + str(checks): {"group": device.upper(), "checks": checks}
                 for device in stock_regression.CONTROL_DRIVERS for checks in (0, 1)}
        fixtures = {name: {"success": True, "translation_units": {}} for name in specs}
        fixtures["ra8d11"]["translation_units"] = {sci: {}, dsi: {}}
        uncovered, missing, _ = stock_regression.coverage_gaps(
            fixtures, specs, [sci, dsi], stock_regression.CONTROL_DRIVERS)
        self.assertEqual(uncovered, [])
        self.assertEqual(len(missing), 5)
        self.assertTrue(any("ra8d1_checks_0" in value and "r_mipi_dsi" in value for value in missing))
        self.assertTrue(any("ra6t2_checks_1" in value and "r_sci_b_spi" in value for value in missing))
        self.assertFalse(any("ra4m" in value or "ra0e1" in value for value in missing))
        for device, drivers in stock_regression.CONTROL_DRIVERS.items():
            for checks in (0, 1):
                fixtures[device + str(checks)]["translation_units"] = {
                    path: {} for path in stock_regression.control_units(device, [sci, dsi])}
        self.assertEqual(stock_regression.coverage_gaps(
            fixtures, specs, [sci, dsi], stock_regression.CONTROL_DRIVERS), ([], [], []))

    def test_all_new_capability_units_have_per_device_checking_coverage(self):
        for device, drivers in stock_regression.CONTROL_DRIVERS.items():
            expected = {f"ra/fsp/src/{driver}/{driver}.c" for driver in drivers}
            self.assertEqual(set(stock_regression.control_units(device, stock_regression.CAPABILITY_UNITS)), expected)
            for path in expected:
                self.assertIn(path, stock_regression.CHECK_MACROS)
        self.assertNotIn("r_agt", stock_regression.CONTROL_DRIVERS["ra0e1"])
        self.assertEqual({device for device, drivers in stock_regression.CONTROL_DRIVERS.items()
                          if "r_sci_b_spi" in drivers}, {"ra8m1", "ra6t2", "ra8d1"})

    def test_driver_checking_aliases_resolve_and_cycles_fail_closed(self):
        values = {"DRIVER": "((BSP))", "BSP": "(1UL)"}
        self.assertEqual(stock_regression.integer_macro(values, "DRIVER"), 1)
        values["BSP"] = "(0)"
        self.assertEqual(stock_regression.integer_macro(values, "DRIVER"), 0)
        values["BSP"] = "DRIVER"
        with self.assertRaisesRegex(ValueError, "Unresolved generated integer"):
            stock_regression.integer_macro(values, "DRIVER")

    def test_metadata_default_option_constraint_and_template_changes_fail(self):
        original = (b'<raModuleDescription><config><property id="p" default="o">'
                    b'<option id="o" value="1"/></property><content>unchanged</content></config>'
                    b'<module><constraint display="legacy">old</constraint>'
                    b'<requires id="r" interface="legacy"/></module></raModuleDescription>')
        path = "Renesas##HAL Drivers##all##r_sci_b_spi####5.9.0.xml"
        result = stock_regression.shared_metadata_invariants(path, original, original)
        self.assertTrue(result["defaults_unchanged"])
        for old, new in ((b'default="o"', b'default="other"'), (b'value="1"', b'value="2"'),
                         (b'>old<', b'>new<'), (b'>unchanged<', b'>changed<'),
                         (b'interface="legacy"', b'interface="other"')):
            with self.assertRaisesRegex(ValueError, "shared MDF"):
                stock_regression.shared_metadata_invariants(path, original, original.replace(old, new))

    def test_original_repeated_option_ids_preserve_each_value(self):
        source = (b'<raModuleDescription><config><property id="p" default="o">'
                  b'<option id="o" value="1"/></property><property id="q" default="o">'
                  b'<option id="o" value="2"/></property></config></raModuleDescription>')
        path = "Renesas##HAL Drivers##all##r_canfd####5.9.0.xml"
        self.assertTrue(stock_regression.shared_metadata_invariants(path, source, source)["option_values_unchanged"])
        with self.assertRaisesRegex(ValueError, "value drift"):
            stock_regression.shared_metadata_invariants(path, source, source.replace(b'value="1"', b'value="2"'))

    def test_dsi_rxte_export_is_identity_without_target_capability(self):
        filename = "Renesas##HAL Drivers##all##r_mipi_dsi####5.9.0.xml"
        # This is the retained r013 exporter contract, not the next revision's
        # independently reviewed device-enum implementation.
        with zipfile.ZipFile(ROOT / "validation/ra8p1/packs/r013/Renesas.RA.5.9.0.pack") as package:
            owner = ET.fromstring(package.read(".module_descriptions/" + filename))
        prop = owner.find(".//property[@id='module.driver.mipi_dsi.rxie']")
        export = prop.find("export")
        self.assertIsNotNone(export)
        self.assertIn('"${interface.mcu.mipi_dsi.rxier_no_rxte}" === "1"', export.text)
        current = b"<raModuleDescription>" + ET.tostring(prop) + b"</raModuleDescription>"
        prop.remove(export)
        original = b"<raModuleDescription>" + ET.tostring(prop) + b"</raModuleDescription>"
        result = stock_regression.shared_metadata_invariants(filename, original, current)
        self.assertEqual(result["legacy_neutral_exports"], ["module.driver.mipi_dsi.rxie"])
        with self.assertRaisesRegex(ValueError, "export drift"):
            stock_regression.shared_metadata_invariants(filename, original, current.replace(b'=== "1"', b'!== "1"'))
        with self.assertRaisesRegex(ValueError, "export drift"):
            stock_regression.shared_metadata_invariants(filename, original, current.replace(b"'interrupts')", b"'0')"))

    def test_dsi_capability_extension_keeps_legacy_branch_and_rejects_other_changes(self):
        path = "Renesas##HAL Drivers##all##r_mipi_dsi####5.9.0.xml"
        original = (b'<raModuleDescription><module><constraint display="Requires MIPI DSI peripheral">'
                    b'("${interface.mcu.mipi_dsi.external}" === "1") &amp;&amp; '
                    b'("${interface.mcu.feature_set.b}" === "1")</constraint>'
                    b'<requires id="module.driver.mipi_dsi.requires.mipi_feature_set_hw" '
                    b'interface="interface.mcu.feature_set.b"/></module></raModuleDescription>')
        candidate = (ROOT / "baseline/module_descriptions" / path).read_bytes()
        constraint = next(element for element in ET.fromstring(candidate).iter("constraint")
                          if element.get("display") == "Requires MIPI DSI peripheral")
        current = b'<raModuleDescription><module>' + ET.tostring(constraint) + b'</module></raModuleDescription>'
        result = stock_regression.shared_metadata_invariants(path, original, current)
        self.assertEqual(result["extended_constraints"], ["Requires MIPI DSI peripheral"])
        with self.assertRaisesRegex(ValueError, "constraint drift"):
            stock_regression.shared_metadata_invariants(path, original,
                                                        current.replace(b'feature_set.b', b'feature_set.other'))


class MetadataOnlyTransferTests(unittest.TestCase):
    def rxie_inputs(self):
        self.legacy = ".module_descriptions/Renesas##BSP##ra8d1##fsp####5.9.0.xml"
        self.target = ".module_descriptions/Renesas##BSP##ra8p1##fsp####5.9.0.xml"
        options = (b'<option id="module.driver.mipi_dsi.rxie.rxte" value="RXTE"/>'
                   b'<option id="module.driver.mipi_dsi.rxie.extedet" value="EXTEDET"/>')
        prop = b'<property id="module.driver.mipi_dsi.rxie" default="legacy">'
        before = {"Renesas.RA.5.9.0.pack": {
            stock_regression.DSI_MDF: b'<root>' + prop + options + b'</property></root>',
            self.legacy: b'<root><module id="legacy"/></root>',
            self.target: b'<root><module id="target"/></root>',
            "ra/fsp/src/test.c": b"production bytes\r\n"}}
        after = {pack: dict(entries) for pack, entries in before.items()}
        entries = after["Renesas.RA.5.9.0.pack"]
        entries[stock_regression.DSI_MDF] = (b'<root>' + prop +
            b'<select enum="enum.driver.mipi_dsi.rxie"/></property></root>')
        for path, name in ((self.legacy, b"legacy"), (self.target, b"target")):
            selected = options.replace(b'value="RXTE"', b'value="0U"') if path == self.target else options
            entries[path] = (b'<root><module id="' + name + b'">'
                b'<enum id="enum.driver.mipi_dsi.rxie" default="">' + selected + b'</enum></module></root>')
        return before, after

    def test_rxie_move_preserves_legacy_values_and_only_target_rxte_is_zero(self):
        before, after = self.rxie_inputs()
        result = stock_regression.review_rxie_transfer(before, after)
        self.assertTrue(result["non_metadata_entries_identical"])
        self.assertEqual(result["legacy_rxie_option_count"], 2)
        entries = after["Renesas.RA.5.9.0.pack"]
        entries[self.legacy] = entries[self.legacy].replace(b'value="RXTE"', b'value="0U"')
        with self.assertRaisesRegex(ValueError, "enum IDs/values changed"):
            stock_regression.review_rxie_transfer(before, after)

    def test_transfer_rejects_other_xml_default_source_and_inventory_changes(self):
        for kind in ("default", "xml", "source", "entry", "pack"):
            before, after = self.rxie_inputs()
            entries = after["Renesas.RA.5.9.0.pack"]
            if kind == "default":
                entries[stock_regression.DSI_MDF] = entries[stock_regression.DSI_MDF].replace(
                    b'default="legacy"', b'default="different"')
            elif kind == "xml":
                entries[self.legacy] = entries[self.legacy].replace(b'id="legacy"', b'id="other"')
            elif kind == "source":
                entries["ra/fsp/src/test.c"] = b"edited production bytes"
            elif kind == "entry":
                entries["extra"] = b"new"
            else:
                after["new.pack"] = {}
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                stock_regression.review_rxie_transfer(before, after)

    def test_transfer_enum_order_duplicates_and_select_changes_fail(self):
        for kind in ("duplicate", "select", "other-value"):
            before, after = self.rxie_inputs()
            entries = after["Renesas.RA.5.9.0.pack"]
            if kind == "duplicate":
                entries[self.legacy] = entries[self.legacy].replace(b'</enum>', b'<option id="extra"/></enum>')
            elif kind == "select":
                entries[stock_regression.DSI_MDF] = entries[stock_regression.DSI_MDF].replace(
                    b'enum="enum.driver.mipi_dsi.rxie"', b'enum="unrelated"')
            else:
                entries[self.target] = entries[self.target].replace(b'value="EXTEDET"', b'value="0U"')
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                stock_regression.review_rxie_transfer(before, after)

    def test_only_mdf_line_endings_may_change_without_semantic_review(self):
        before, after = self.rxie_inputs()
        path = ".module_descriptions/unchanged.xml"
        before["Renesas.RA.5.9.0.pack"][path] = b"<root/>\r\n"
        after["Renesas.RA.5.9.0.pack"][path] = b"<root/>\n"
        self.assertTrue(stock_regression.review_rxie_transfer(before, after)["success"])
        after["Renesas.RA.5.9.0.pack"]["ra/fsp/src/test.c"] = b"production bytes\n"
        with self.assertRaisesRegex(ValueError, "non-MDF input changed"):
            stock_regression.review_rxie_transfer(before, after)

    def fixture_tree(self, tree):
        for name, content in {"ra/test.c": b"int test;", "ra_cfg/config.h": b"#define VALUE 1",
                              "ra_gen/data.c": b"int generated;", "src/main.c": b"int main(void);",
                              "script/fsp.ld": b"SECTIONS {}", "configuration.xml": b"<root/>",
                              ".cproject": b"<root/>", "Debug/ra/test.o.in": b"-c ../ra/test.c",
                              "Debug/memory_regions.ld": b"MEMORY {}",
                              "Debug/app.elf.in": b"-T ../script/fsp.ld"}.items():
            path = tree / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        rows = [{"directory": str(tree / "Debug"), "file": str(tree / "ra/test.c"),
                 "arguments": ["/usr/bin/cc", "-c", str(tree / "ra/test.c"), "-O2", "-o", "ra/test.o"]}]
        (tree / "Debug/compile_commands.json").write_text(json.dumps(rows))

    def test_input_fingerprints_are_location_independent_without_normalizing_bytes(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            trees = [Path(first), Path(second)]
            for tree in trees:
                self.fixture_tree(tree)
            before, after = [stock_regression.fixture_transfer_fingerprint(tree) for tree in trees]
            self.assertTrue(stock_regression.compare_transfer_fingerprints(before, after)["success"])
            self.assertEqual(before["commands"]["ra/test.c"]["arguments"][2], "../ra/test.c")
            (trees[1] / "ra_gen/data.c").write_bytes(b"int changed;")
            with self.assertRaisesRegex(ValueError, "files drift: ra_gen/data.c"):
                stock_regression.compare_transfer_fingerprints(
                    before, stock_regression.fixture_transfer_fingerprint(trees[1]))

    def test_editor_linker_rows_do_not_hide_malformed_real_compile_commands(self):
        with tempfile.TemporaryDirectory() as temp:
            tree = Path(temp)
            self.fixture_tree(tree)
            path = tree / "Debug/compile_commands.json"
            rows = json.loads(path.read_text())
            rows.append({"directory": str(tree / "Debug"), "file": str(tree / "script/fsp.ld"),
                         "arguments": ["clang", "-I../script"]})
            path.write_text(json.dumps(rows))
            result = stock_regression.fixture_transfer_fingerprint(tree)
            self.assertEqual(set(result["commands"]), {"ra/test.c"})
            self.assertIn("script/fsp.ld", result["files"])
            rows[0]["arguments"].remove("-c")
            path.write_text(json.dumps(rows))
            with self.assertRaisesRegex(ValueError, "unique compile/output"):
                stock_regression.fixture_transfer_fingerprint(tree)

    def test_generated_configuration_flags_and_native_response_drift_fail(self):
        for name in (".cproject", "configuration.xml", "ra_cfg/config.h", "Debug/ra/test.o.in",
                     "Debug/memory_regions.ld", "Debug/app.elf.in", "Debug/compile_commands.json"):
            with self.subTest(path=name), tempfile.TemporaryDirectory() as temp:
                tree = Path(temp)
                self.fixture_tree(tree)
                before = stock_regression.fixture_transfer_fingerprint(tree)
                path = tree / name
                if name.endswith(".json"):
                    rows = json.loads(path.read_text())
                    rows[0]["arguments"].insert(1, "-DCHANGED=1")
                    path.write_text(json.dumps(rows))
                else:
                    path.write_bytes(path.read_bytes() + b" ")
                with self.assertRaisesRegex(ValueError, "Transfer .* drift"):
                    stock_regression.compare_transfer_fingerprints(
                        before, stock_regression.fixture_transfer_fingerprint(tree))


if __name__ == "__main__":
    unittest.main()
