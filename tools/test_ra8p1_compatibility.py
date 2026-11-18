"""Negative controls for the stock-source compatibility evidence gate."""
import json
from io import BytesIO
from zipfile import ZipFile
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ra8p1 import compatibility as gate


class CompatibilityTests(unittest.TestCase):
    def fixture(self, root, sources, core="CM85"):
        project = root / "project"
        (project / "Debug").mkdir(parents=True)
        rows = [{"arguments": ["/usr/bin/gcc", "-D_RA_CORE=" + core, "-c", "-o", str(project / "Debug/a.o"),
                               str(project / source)], "file": str(project / source), "directory": str(project / "Debug")}
                for source in sources]
        (project / "Debug/compile_commands.json").write_text(json.dumps(rows))
        (project / "configuration.xml").write_text("generated model")
        (project / "ra_gen").mkdir()
        (project / "ra_gen/hal_data.h").write_bytes(b"unchanged generated header")
        return project

    def compiler(self, command, **kwargs):
        if "--defined-only" in command:
            return gate.subprocess.CompletedProcess(command, 0, "00000000 T R_Test_Open\n", "")
        source = command[command.index("-x") + 2] if "-x" in command else command[command.index("-o") + 2]
        depfile = Path(command[command.index("-MF") + 1])
        depfile.write_text("object.o: " + source + "\n")
        return gate.subprocess.CompletedProcess(command, 0, "", "")

    def test_unsafe_source_paths_are_rejected(self):
        for path in ("/tmp/a.c", "../a.c", "ra/../a.c", "ra\\a.c"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                gate.safe_path(path)
        self.assertEqual(str(gate.safe_path("ra/fsp/src/r_gpt/r_gpt.c")), "ra/fsp/src/r_gpt/r_gpt.c")

    def test_stock_driver_headers_and_sources_but_not_target_bsp_are_original(self):
        bsp = "ra/fsp/src/bsp/mcu/ra8p1/bsp_feature.h"
        drv = "ra/fsp/src/r_gpt/r_gpt.c"
        api = "ra/fsp/inc/api/r_timer_api.h"
        target = {bsp: b"target", drv: b"adapted", api: b"candidate"}
        stock = {bsp: b"not target", drv: b"original", api: b"original api"}
        overlay = gate.source_overlay(target, stock, "stock")
        self.assertEqual(overlay[bsp], b"target")
        self.assertEqual(overlay[drv], b"original")
        self.assertEqual(overlay[api], b"original api")
        self.assertEqual(gate.source_overlay(target, stock, "candidate"), target)
        self.assertEqual(target[drv], b"adapted")

    def test_recorded_flags_preserved_and_sources_not_injected(self):
        row = {"arguments": ["gcc", "-mcpu=cortex-m85", "-D_RA_CORE=CM85", "-I/old/ra_gen", "-c", "-o", "/old/Debug/a.o", "-x", "c", "/old/ra/a.c"], "file": "/old/ra/a.c"}
        result = gate.command_for(row, Path("/old"), Path("/new"), "ra/b.c", Path("/new/Debug/b.o"))
        self.assertIn("-mcpu=cortex-m85", result)
        self.assertIn("-I/new/ra_gen", result)
        self.assertIn("/new/ra/b.c", result)
        self.assertNotIn("/old/ra/a.c", result)
        self.assertFalse(any("R_GPT" in value for value in result))
        assembly = gate.command_for(row, Path("/old"), Path("/new"), "ra/port.S", Path("/new/Debug/b.o"))
        self.assertIn("assembler-with-cpp", assembly)

    def test_missing_compile_source_is_not_silently_replaced(self):
        row = {"arguments": ["gcc", "-c", "-o", "a.o", "other.c"], "file": "/old/ra/a.c"}
        with self.assertRaisesRegex(ValueError, "source is missing"):
            gate.command_for(row, Path("/old"), Path("/new"), "ra/b.c", Path("b.o"))

    def test_candidate_only_driver_never_reported_as_stock_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = self.fixture(root, ["ra/a.c"])
            candidate = {"ra/fsp/src/r_pdm/r_pdm.c": b"candidate"}
            with patch.object(gate.subprocess, "run") as compiler:
                report = gate.compile_project(root, project, [{"name": "r_pdm"}], "stock", "before", {}, candidate)
            self.assertEqual(report["modules"]["r_pdm"]["status"], "not-applicable")
            compiler.assert_not_called()

    def test_original_component_packs_are_hash_verified_and_conflicts_fail(self):
        def pack_bytes(files):
            result = BytesIO()
            with ZipFile(result, "w") as package:
                for name, data in files.items():
                    package.writestr(name, data)
            return result.getvalue()

        source = "ra/fsp/src/r_crypto/r_crypto.c"
        auxiliary = "internal/projectgen/ra/packs/aux.pack"
        for conflicting in (False, True):
            with self.subTest(conflicting=conflicting), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                archive = root / "reference/vendor/FSP_Packs_v5.9.0.zip"
                archive.parent.mkdir(parents=True)
                main = pack_bytes({source: b"original"})
                extra = pack_bytes({source: b"conflict" if conflicting else b"original"})
                archive.write_bytes(pack_bytes({gate.RELEASE_PACK: main, auxiliary: extra}))
                modules = [{"components": [{"archive_entry": auxiliary, "pack_sha256": gate.digest(extra)}]}]
                with patch.object(gate, "ARCHIVE_SHA256", gate.digest(archive.read_bytes())):
                    if conflicting:
                        with self.assertRaisesRegex(ValueError, "Conflicting original source"):
                            gate.original_sources(root, modules)
                    else:
                        self.assertEqual(gate.original_sources(root, modules)[source], b"original")
                        modules[0]["components"][0]["pack_sha256"] = "0" * 64
                        with self.assertRaisesRegex(ValueError, "pack hash mismatch"):
                            gate.original_sources(root, modules)

    def test_original_banner_variants_use_explicit_common_pack_bytes(self):
        def pack_bytes(files):
            result = BytesIO()
            with ZipFile(result, "w") as package:
                for name, data in files.items():
                    package.writestr(name, data)
            return result.getvalue()

        source = "ra/fsp/src/rm_threadx_port/tx_port_wait_thread_ready.c"
        auxiliary = "internal/projectgen/ra/packs/Aux.ThreadX.pack"
        common = (b"/*\r\n* Copyright (c) 2020 - 2025 Renesas Electronics Corporation and/or its affiliates\r\n"
                  b"*\r\n* SPDX-License-Identifier: BSD-3-Clause\r\n*/\r\nint body;\r\n")
        other = b"/* ${REA_DISCLAIMER_PLACEHOLDER} */\r\nint body;\r\n"
        for content, accepted in ((other, True), (other + b"int unknown;", False)):
            with self.subTest(accepted=accepted), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                archive = root / "reference/vendor/FSP_Packs_v5.9.0.zip"
                archive.parent.mkdir(parents=True)
                main = pack_bytes({source: common})
                extra = pack_bytes({source: content})
                archive.write_bytes(pack_bytes({gate.RELEASE_PACK: main, auxiliary: extra}))
                modules = [{"components": [{"archive_entry": auxiliary, "pack_sha256": gate.digest(extra)}]}]
                with patch.object(gate, "ARCHIVE_SHA256", gate.digest(archive.read_bytes())):
                    if accepted:
                        self.assertEqual(gate.original_sources(root, modules)[source], common)
                    else:
                        with self.assertRaisesRegex(ValueError, "Conflicting original source"):
                            gate.original_sources(root, modules)

    def test_inactive_translation_unit_is_not_an_unchanged_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = "ra/fsp/src/r_crypto/r_crypto.c"
            project = self.fixture(root, [source])
            def inactive(command, **kwargs):
                self.compiler(command, **kwargs)
                return gate.subprocess.CompletedProcess(command, 0, "", "")
            with patch.object(gate.subprocess, "run", side_effect=inactive):
                report = gate.compile_project(root, project, [{"name": "r_crypto"}], "candidate", "after", {},
                                              {source: b"#if 0\\nvoid disabled(void) {}\\n#endif\\n"})
            self.assertEqual(report["modules"]["r_crypto"]["status"], "blocked")
            self.assertIn("inactive/empty", report["modules"]["r_crypto"]["reason"])

    def test_missing_generated_dependency_is_blocked_not_compatible(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = "ra/fsp/src/r_gpt/r_gpt.c"
            project = self.fixture(root, [source])
            candidate = {source: b"production source"}
            completed = gate.subprocess.CompletedProcess([], 1, "", "fatal error: r_gpt_cfg.h: No such file or directory")
            with patch.object(gate.subprocess, "run", return_value=completed):
                report = gate.compile_project(root, project, [{"name": "r_gpt"}], "candidate", "after", {}, candidate)
            self.assertEqual(report["modules"]["r_gpt"]["status"], "blocked")
            self.assertEqual(report["modules"]["r_gpt"]["sources"][source]["source_sha256"], gate.digest(candidate[source]))

    def test_stock_set_removes_candidate_only_api_and_driver(self):
        candidate = {"ra/fsp/inc/api/r_pdm_api.h": b"new api", "ra/fsp/src/r_pdm/r_pdm.c": b"new"}
        self.assertEqual(gate.source_overlay(candidate, {}, "stock"), {})

    def test_current_owning_bsp_not_installed_project_bsp_is_consumed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = "ra/fsp/src/r_gpt/r_gpt.c"
            feature = "ra/fsp/src/bsp/mcu/ra8p1/bsp_feature.h"
            project = self.fixture(root, [source])
            candidate = {source: b"candidate", gate.DEVICE_HEADER: b"owning header", feature: b"owning feature"}
            for name in (gate.DEVICE_HEADER, feature):
                path = project / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"STALE installed")
            def compiler(command, **kwargs):
                result = self.compiler(command, **kwargs)
                if "-MF" in command:
                    tree = Path(command[command.index("-o") + 1]).parents[1]
                    for name in (gate.DEVICE_HEADER, feature):
                        self.assertEqual((tree / name).read_bytes(), candidate[name])
                    depfile = Path(command[command.index("-MF") + 1])
                    with depfile.open("a") as output:
                        output.write(" " + str(tree / gate.DEVICE_HEADER) + " " + str(tree / feature))
                return result
            with patch.object(gate.subprocess, "run", side_effect=compiler):
                report = gate.compile_project(root, project, [{"name": "r_gpt"}], "candidate", "after", {}, candidate)
            self.assertEqual(report["modules"]["r_gpt"]["status"], "pass")
            evidence = report["modules"]["r_gpt"]["sources"][source]
            self.assertEqual(evidence["dependencies_sha256"]["$PROJECT/" + feature], gate.digest(candidate[feature]))
            self.assertEqual((project / feature).read_bytes(), b"STALE installed")
            self.assertEqual((project / "ra_gen/hal_data.h").read_bytes(), b"unchanged generated header")

    def test_stock_attempt_uses_exact_pdsc_owner_not_candidate_or_common_banner(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = "ra/fsp/src/r_gpt/r_gpt.c"
            project = self.fixture(root, [source])
            stock = gate.OriginalSources()
            stock[source] = b"common pack banner"
            stock.components["r_gpt"] = {source: b"exact PDSC owner bytes"}
            def compiler(command, **kwargs):
                if "-MF" in command:
                    self.assertEqual(Path(command[command.index("-o") + 2]).read_bytes(), b"exact PDSC owner bytes")
                return self.compiler(command, **kwargs)
            with patch.object(gate.subprocess, "run", side_effect=compiler):
                report = gate.compile_project(root, project, [{"name": "r_gpt"}], "stock", "after", stock, {source: b"candidate"})
            evidence = report["modules"]["r_gpt"]["sources"][source]
            self.assertEqual(evidence["source_sha256"], gate.digest(b"exact PDSC owner bytes"))
            self.assertEqual(evidence["source_sha256"], evidence["original_pdsc_sha256"])

    def test_missing_owning_bsp_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = "ra/fsp/src/r_gpt/r_gpt.c"
            project = self.fixture(root, [source])
            candidate = {source: b"candidate", gate.DEVICE_HEADER: b"header"}
            with patch.object(gate.subprocess, "run", side_effect=self.compiler):
                with self.assertRaisesRegex(ValueError, "did not consume the owning"):
                    gate.compile_project(root, project, [{"name": "r_gpt"}], "candidate", "after", {}, candidate)

    def test_unselected_sources_are_fixture_gaps_not_arbitrary_compiles(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = self.fixture(root, ["ra/a.c"])
            with patch.object(gate.subprocess, "run") as compiler:
                report = gate.compile_project(root, project, [{"name": "r_gpt"}], "candidate", "after", {},
                                              {"ra/fsp/src/r_gpt/r_gpt.c": b"source"})
            self.assertEqual(report["modules"]["r_gpt"]["status"], "blocked")
            self.assertEqual(report["modules"]["r_gpt"]["selected_sources"], [])
            compiler.assert_not_called()

    def test_gcc_never_compiles_tx_iar_even_if_database_lists_it(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = "ra/fsp/src/rm_threadx_port/tx_iar.c"
            project = self.fixture(root, [source])
            with patch.object(gate.subprocess, "run") as compiler:
                report = gate.compile_project(root, project, [{"name": "rm_threadx_port"}], "candidate", "after", {}, {source: b"iar"})
            self.assertEqual(report["modules"]["rm_threadx_port"]["status"], "blocked")
            self.assertEqual(report["modules"]["rm_threadx_port"]["sources"][source]["status"], "excluded")
            compiler.assert_not_called()

    def test_source_inventory_must_equal_original_pdsc_selected_paths(self):
        module = {"name": "r_gpt", "original_release": True, "source_paths": ["ra/fake.c"],
                  "components": [{"files": [{"category": "source", "name": "ra/real.c"}]}]}
        with self.assertRaisesRegex(ValueError, "differ from original PDSC"):
            gate.source_paths(module, {})

    def test_missing_dependency_names_are_actionable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = "ra/fsp/src/r_gpt/r_gpt.c"
            project = self.fixture(root, [source])
            completed = gate.subprocess.CompletedProcess([], 1, "", "fatal error: r_gpt_cfg.h: No such file or directory")
            with patch.object(gate.subprocess, "run", return_value=completed):
                report = gate.compile_project(root, project, [{"name": "r_gpt"}], "candidate", "after", {}, {source: b"source"})
            self.assertEqual(report["modules"]["r_gpt"]["sources"][source]["missing_dependencies"], ["r_gpt_cfg.h"])

    def test_empty_and_mapping_symbols_are_not_a_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = "ra/fsp/src/r_crypto/r_crypto.c"
            project = self.fixture(root, [source])
            def compiler(command, **kwargs):
                result = self.compiler(command, **kwargs)
                if "--defined-only" in command:
                    return gate.subprocess.CompletedProcess(command, 0, "00000000 a flags\n00000000 t $t\n", "")
                return result
            with patch.object(gate.subprocess, "run", side_effect=compiler):
                report = gate.compile_project(root, project, [{"name": "r_crypto"}], "candidate", "after", {}, {source: b"source"})
            self.assertEqual(report["modules"]["r_crypto"]["sources"][source]["status"], "inactive")
            self.assertEqual(report["modules"]["r_crypto"]["status"], "blocked")

    def test_dependency_escape_back_to_project_is_not_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project, tree = root / "original", root / "overlay"
            project.mkdir()
            tree.mkdir()
            (project / "header.h").write_text("stale")
            depfile = tree / "a.d"
            depfile.write_text("a.o: " + str(project / "header.h"))
            with self.assertRaisesRegex(ValueError, "outside the disposable overlay"):
                gate.dependency_hashes(depfile, tree, project, tree)

    def test_aggregate_covers_each_core_and_does_not_hide_real_failures(self):
        modules = [{"name": "r_gpt", "classification": "present"}, {"name": "r_spi", "classification": "variant-mismatch"},
                   {"name": "r_can", "classification": "absent"}]
        def report(project, core, status):
            return {"project": project, "core": core, "source_set": "candidate", "modules": {
                "r_gpt": {"status": status, "sources": {}},
                "r_spi": {"status": "variant-mismatch", "sources": {}}, "r_can": {"status": "not-applicable", "sources": {}}}}
        reports = [report("main85", "CM85", "pass"), report("extra85", "CM85", "blocked"), report("main33", "CM33", "pass")]
        aggregate = gate.aggregate_reports(reports, modules, ["candidate"], ["CM85", "CM33"])
        self.assertEqual(gate.exit_status(aggregate), 0)
        aggregate = gate.aggregate_reports(reports[:2], modules, ["candidate"], ["CM85", "CM33"])
        self.assertEqual(gate.exit_status(aggregate), 2)
        reports.append(report("bad85", "CM85", "fail"))
        aggregate = gate.aggregate_reports(reports, modules, ["candidate"], ["CM85", "CM33"])
        self.assertEqual(gate.exit_status(aggregate), 1)

    def test_partial_source_reports_aggregate_without_inventing_missing_coverage(self):
        modules = [{"name": "r_gpt", "classification": "present"}, {"name": "r_ioport", "classification": "present"},
                   {"name": "r_missing", "classification": "present"}]
        def report(project, core, module):
            return {"project": project, "core": core, "source_set": "candidate",
                    "modules": {module: {"status": "pass", "sources": {}}}}
        reports = [report("timer85", "CM85", "r_gpt"), report("timer33", "CM33", "r_gpt"),
                   report("port85", "CM85", "r_ioport")]
        aggregate = gate.aggregate_reports(reports, modules, ["candidate"], ["CM85", "CM33"])
        self.assertEqual(aggregate["candidate"]["r_gpt"]["status"], "pass")
        self.assertEqual(aggregate["candidate"]["r_ioport"]["status"], "blocked")
        self.assertEqual(aggregate["candidate"]["r_ioport"]["cores"]["CM33"]["passing_projects"], [])
        self.assertEqual(aggregate["candidate"]["r_missing"]["status"], "blocked")
        self.assertEqual(gate.exit_status(aggregate), 2)

    def test_partial_pristine_failure_does_not_become_candidate_failure(self):
        module = {"name": "r_gpt", "classification": "present"}
        def report(core, source_set, status):
            return {"project": source_set + core, "core": core, "source_set": source_set,
                    "modules": {"r_gpt": {"status": status, "sources": {}}}}
        reports = [report(core, source_set, "pass" if source_set == "candidate" else "fail")
                   for core in ("CM85", "CM33") for source_set in ("stock", "candidate")]
        aggregate = gate.aggregate_reports(reports, [module], ["stock", "candidate"], ["CM85", "CM33"])
        self.assertEqual(gate.exit_status(aggregate), 1)
        self.assertEqual(gate.exit_status({"stock": aggregate["stock"]}), 1)
        self.assertEqual(gate.exit_status({"candidate": aggregate["candidate"]}), 0)
        for cell in aggregate["candidate"]["r_gpt"]["cores"].values():
            self.assertEqual(cell["failed_projects"], [])

    def test_report_records_separate_source_set_exit_verdicts(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "new-report.json"
            def compile_report(root, project, modules, source_set, phase, stock, candidate):
                return {"project": str(project), "core": "CM85" if str(project) == "p85" else "CM33",
                        "source_set": source_set, "modules": {"r_gpt": {
                            "status": "fail" if source_set == "stock" else "pass", "sources": {}}}}
            with patch.object(gate, "original_sources", return_value={}), patch.object(gate, "candidate_sources", return_value={}), \
                    patch.object(gate, "compile_project", side_effect=compile_report):
                status = gate.main(["--project", "p85", "--project", "p33", "--module", "r_gpt",
                                    "--phase", "after", "--report", str(output)])
            result = json.loads(output.read_text())
            self.assertEqual(status, 1)
            self.assertEqual(result["source_set_exit_status"], {"stock": 1, "candidate": 0})

    def test_existing_reports_are_immutable(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "before.json"
            report.write_text("immutable")
            with self.assertRaises(SystemExit), patch.object(gate, "original_sources") as sources:
                gate.main(["--project", folder, "--phase", "after", "--report", str(report)])
            sources.assert_not_called()
            self.assertEqual(report.read_text(), "immutable")

    def test_after_sources_are_from_owning_baseline_not_pack_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            header = root / "baseline" / gate.DEVICE_HEADER
            header.parent.mkdir(parents=True)
            header.write_bytes(b"owning")
            installed = root / "pack_sources" / gate.DEVICE_HEADER
            installed.parent.mkdir(parents=True)
            installed.write_bytes(b"stale")
            self.assertEqual(gate.candidate_sources(root, "after")[gate.DEVICE_HEADER], b"owning")


if __name__ == "__main__":
    unittest.main()
