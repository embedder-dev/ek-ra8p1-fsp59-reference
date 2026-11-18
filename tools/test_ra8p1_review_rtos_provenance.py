"""Independent TEST006/TEST009 regressions; all mutations stay in disposable fixtures."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from ra8p1 import rtos_compatibility as rtos


FIXTURES = Path(__file__).parent / "ra8p1/review_rtos_provenance"
PORT = "ra/fsp/src/rm_freertos_port/port.c"
BSP = "ra/fsp/inc/bsp_owner.h"
PREFIX = rtos.KERNEL_PREFIXES["freertos"]
HEADER = PREFIX + "include/FreeRTOS.h"
KERNEL = PREFIX + "kernel.c"


class DisposableProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="review rtos ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / "generated"
        self.project.mkdir()
        (self.project / "Debug").mkdir()
        (self.project / "configuration.xml").write_text("<configuration/>")
        compiler = shutil.which("clang") or shutil.which("cc")
        if not compiler:
            self.skipTest("A host C compiler is required")
        files = {PORT: (FIXTURES / "port.c").read_bytes(),
                 BSP: (FIXTURES / "bsp_owner.h").read_bytes(),
                 HEADER: (FIXTURES / "FreeRTOS.h").read_bytes(),
                 KERNEL: (FIXTURES / "kernel.c").read_bytes()}
        for name, data in files.items():
            target = self.project / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        self.candidate = {name: data for name, data in files.items() if name.startswith("ra/fsp/")}
        self.packs = {
            "port": {"name": "fixture-port.pack", "sha256": "1" * 64,
                     "files": self.candidate.copy(),
                     "pdsc": ET.fromstring('<package><component Csub="rm_freertos_port"><files>'
                                           f'<file category="source" name="{PORT}"/>'
                                           '</files></component></package>')},
            "freertos": {"name": "fixture-kernel.pack", "sha256": "2" * 64,
                         "files": {HEADER: files[HEADER], KERNEL: files[KERNEL]},
                         "pdsc": ET.fromstring('<package><component Cclass="RTOS"><files>'
                                               f'<file category="source" name="{KERNEL}"/>'
                                               f'<file category="header" name="{HEADER}"/>'
                                               '</files></component></package>')},
        }
        self.rows = []
        for source in (PORT, KERNEL):
            args = [compiler, "-I" + str(self.project / "ra/fsp/inc"),
                    "-I" + str(self.project / PREFIX / "include"), "-c", str(self.project / source),
                    "-o", str(self.project / "Debug" / (Path(source).stem + ".o"))]
            self.rows.append({"file": str(self.project / source), "directory": str(self.project / "Debug"),
                              "arguments": args})
        self.save_rows()

    def save_rows(self):
        (self.project / "Debug/compile_commands.json").write_text(json.dumps(self.rows))

    def compile(self, source_set="candidate"):
        # Host objects are Mach-O, not ARM ELF; object inspection is unrelated to provenance.
        with patch.object(rtos, "readonly_sections", return_value={}):
            return rtos.compile_fixture(self.root, self.project, "freertos", "after", source_set,
                                        self.packs, self.candidate)

    def test_complete_owners_compile_and_record_consumed_kernel_inputs(self):
        result = self.compile()
        self.assertEqual("pass", result["status"])
        consumed = result["kernel"]["compiler_dependencies"]
        self.assertEqual(rtos.digest(self.packs["freertos"]["files"][HEADER]), consumed[HEADER])
        self.assertEqual(rtos.digest(self.packs["freertos"]["files"][KERNEL]), consumed[KERNEL])
        self.assertIn("$PROJECT/" + HEADER, result["sources"][PORT]["dependencies_sha256"])

    def test_missing_candidate_port_owner_does_not_reuse_copied_source(self):
        del self.candidate[PORT]
        with patch.object(rtos.subprocess, "run", wraps=subprocess.run) as run:
            with self.assertRaisesRegex(ValueError, "[Oo]wner|[Oo]wning"):
                self.compile()
            run.assert_not_called()

    def test_missing_candidate_header_owner_does_not_reuse_copied_header(self):
        del self.candidate[BSP]
        with patch.object(rtos.subprocess, "run", wraps=subprocess.run) as run:
            with self.assertRaisesRegex(ValueError, "[Oo]wner|[Oo]wning"):
                self.compile()
            run.assert_not_called()

    def test_missing_kernel_header_owner_fails_even_without_a_present_file(self):
        (self.project / HEADER).unlink()
        with self.assertRaisesRegex(ValueError, "[Oo]wner|missing"):
            rtos.dependencies(self.project, self.packs["freertos"], self.rows, PREFIX)

    def test_kernel_pdsc_cannot_refer_to_a_missing_archive_owner(self):
        del self.packs["freertos"]["files"][HEADER]
        (self.project / HEADER).unlink()
        with self.assertRaisesRegex(ValueError, "[Oo]wner|missing"):
            self.compile()

    def test_external_kernel_header_substitution_is_rejected(self):
        external = self.root / "external"
        external.mkdir()
        # Identical bytes outside the original owner's path are still a substitution.
        (external / "FreeRTOS.h").write_bytes(self.packs["freertos"]["files"][HEADER])
        for row in self.rows:
            row["arguments"].insert(1, "-I" + str(external))
        self.save_rows()
        with self.assertRaisesRegex(ValueError, "[Kk]ernel.*([Oo]wner|[Ss]ubstitut)|[Oo]wner.*kernel"):
            self.compile()

    def test_port_only_external_kernel_header_substitution_is_rejected(self):
        external = self.root / "port-external"
        external.mkdir()
        (external / "FreeRTOS.h").write_bytes(self.packs["freertos"]["files"][HEADER])
        self.rows[0]["arguments"].insert(1, "-I" + str(external))
        self.save_rows()
        with self.assertRaisesRegex(ValueError, "kernel owner substitution"):
            self.compile()

    def test_success_without_compiler_dependency_evidence_is_rejected(self):
        run = subprocess.run
        def discard_port_evidence(command, **kwargs):
            completed = run(command, **kwargs)
            if "-MD" in command:
                Path(command[command.index("-MF") + 1]).unlink(missing_ok=True)
            return completed
        with patch.object(rtos.subprocess, "run", side_effect=discard_port_evidence):
            with self.assertRaisesRegex(ValueError, "no dependency evidence"):
                self.compile()

    def test_project_local_shadow_kernel_header_is_rejected(self):
        shadow = self.project / "src"
        shadow.mkdir()
        (shadow / "FreeRTOS.h").write_text("#define KERNEL_VALUE 99\n")
        for row in self.rows:
            row["arguments"].insert(1, "-I" + str(shadow))
        self.save_rows()
        with self.assertRaisesRegex(ValueError, "[Kk]ernel.*([Oo]wner|[Ss]ubstitut)|[Oo]wner.*kernel"):
            self.compile()

    def test_kernel_dependency_preprocessing_failure_is_not_a_pass(self):
        # Inventory hashes still match; a recorded flag breaks the real kernel input.
        self.rows[1]["arguments"].insert(1, "-include")
        self.rows[1]["arguments"].insert(2, "missing-required-kernel-header.h")
        self.save_rows()
        with self.assertRaisesRegex(ValueError, "[Kk]ernel.*dependency|dependency.*[Kk]ernel"):
            self.compile()

    def test_generated_project_is_unchanged_by_provenance_checks(self):
        before = {p.relative_to(self.project): p.read_bytes() for p in self.project.rglob("*") if p.is_file()}
        self.compile()
        after = {p.relative_to(self.project): p.read_bytes() for p in self.project.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


class VerifiedReleaseProvenanceTests(unittest.TestCase):
    def test_retained_real_ports_consume_verified_original_kernels(self):
        packs = rtos.original_release(rtos.ROOT)
        candidate = rtos.candidate_sources(rtos.ROOT, "after")
        for name, header in (("freertos", "include/FreeRTOS.h"), ("threadx", "common/inc/tx_api.h")):
            project = rtos.ROOT / "validation/ra8p1/compatibility/rtos/controls" / ("rtos_" + name + "_ra4m1")
            database = project / "Debug/compile_commands.json"
            if not database.is_file():
                self.skipTest("Retained real-kernel projects are unavailable")
            rows = json.loads(database.read_text())
            args = rows[0].get("arguments") or shlex.split(rows[0]["command"])
            if not Path(args[0]).is_file():
                self.skipTest("The recorded ARM compiler is unavailable")
            for source_set in ("stock", "candidate"):
                with self.subTest(rtos=name, source_set=source_set):
                    result = rtos.compile_fixture(rtos.ROOT, project, name, "after", source_set, packs, candidate)
                    self.assertEqual("pass", result["status"])
                    kernel = result["kernel"]
                    self.assertEqual(set(kernel["translation_units"]), set(kernel["dependency_scans"]))
                    self.assertTrue(set(kernel["translation_units"]) <= kernel["compiler_dependencies"].keys())
                    owner = rtos.KERNEL_PREFIXES[name] + header
                    self.assertIn(owner, kernel["compiler_dependencies"])
                    for owner, sha256 in kernel["compiler_dependencies"].items():
                        self.assertEqual(rtos.digest(packs[name]["files"][owner]), sha256)


class ExclusiveReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.report = self.root / "result.json"
        self.args = ["--fixture", "freertos=unused", "--phase", "after", "--source-set", "candidate",
                     "--report", str(self.report)]
        self.result = {"status": "pass", "sources": {}, "kernel": {"translation_units": []}}

    def invoke(self, compile_fixture=None):
        with patch.object(rtos, "original_release", return_value={}) as release, \
                patch.object(rtos, "candidate_sources", return_value={}), \
                patch.object(rtos, "compile_fixture", side_effect=compile_fixture,
                             return_value=self.result) as compile_call, \
                redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            try:
                return rtos.main(self.args)
            finally:
                self.release_called = release.called
                self.compile_called = compile_call.called

    def test_existing_report_is_refused_before_input_loading_or_compilation(self):
        self.report.write_bytes(b"retained evidence\x00\xff")
        with self.assertRaises(SystemExit) as raised:
            self.invoke()
        self.assertEqual(2, raised.exception.code)
        self.assertEqual(b"retained evidence\x00\xff", self.report.read_bytes())
        self.assertFalse(self.release_called)
        self.assertFalse(self.compile_called)

    def test_report_created_during_compilation_is_not_overwritten(self):
        def competing_writer(*_args):
            self.report.write_bytes(b"other publisher")
            return self.result
        with self.assertRaises(FileExistsError):
            self.invoke(competing_writer)
        self.assertEqual(b"other publisher", self.report.read_bytes())

    def test_dangling_report_symlink_is_refused_without_creating_target(self):
        target = self.root / "untouched.json"
        self.report.symlink_to(target)
        with self.assertRaises(SystemExit):
            self.invoke()
        self.assertTrue(self.report.is_symlink())
        self.assertFalse(target.exists())
        self.assertFalse(self.compile_called)

    def test_new_report_is_published(self):
        self.assertEqual(0, self.invoke())
        self.assertEqual([self.result], json.loads(self.report.read_text())["reports"])


if __name__ == "__main__":
    unittest.main()
