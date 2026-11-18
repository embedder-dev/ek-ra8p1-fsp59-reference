"""Focused input-integrity and coverage tests for the real-kernel RTOS gate."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from ra8p1 import rtos_compatibility as rtos


class OriginalPortInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packs = rtos.original_release(rtos.ROOT)

    def test_release_and_pack_identity(self):
        for key, pack in self.packs.items():
            self.assertEqual(rtos.PACKS[key], pack["name"])
            self.assertEqual(64, len(pack["sha256"]))

    def test_complete_original_gcc_port_sources(self):
        self.assertEqual(["ra/fsp/src/rm_freertos_port/port.c"],
                         rtos.port_paths(self.packs["port"], "rm_freertos_port"))
        paths = rtos.port_paths(self.packs["port"], "rm_threadx_port")
        self.assertEqual(16, len(paths))
        self.assertIn("ra/fsp/src/rm_threadx_port/tx_iar.c", paths)
        self.assertIn("ra/fsp/src/rm_threadx_port/tx_thread_schedule.c", paths)
        self.assertIn("ra/fsp/src/rm_threadx_port/tx_port_wait_thread_ready.c", paths)
        self.assertIn("ra/fsp/src/rm_threadx_port/txe_thread_secure_stack_free.c", paths)

    def test_real_kernel_headers_come_from_original_packs(self):
        for key, suffix in (("freertos", "include/FreeRTOS.h"), ("threadx", "common/inc/tx_api.h")):
            prefix = rtos.KERNEL_PREFIXES[key]
            self.assertIn(prefix + suffix, self.packs[key]["files"])
            units = {f.get("name") for c in self.packs[key]["pdsc"].findall(".//component")
                     if c.get("Cclass") == "RTOS" for f in c.findall("files/file")
                     if f.get("category") == "source" and f.get("name", "").startswith(prefix)}
            self.assertEqual(6 if key == "freertos" else 184, len(units))

    def test_unknown_source_condition_is_not_silently_skipped(self):
        pack = {"pdsc": ET.fromstring('<package><component Csub="port"><files>'
                                      '<file category="source" name="port.c" condition="new"/>'
                                      '</files></component></package>')}
        with self.assertRaisesRegex(ValueError, "Unreviewed conditional"):
            rtos.port_paths(pack, "port")

    def test_archive_hash_mismatch_fails_closed(self):
        with patch.object(rtos, "ARCHIVE_SHA256", "0" * 64):
            with self.assertRaisesRegex(ValueError, "archive hash mismatch"):
                rtos.original_release(rtos.ROOT)

    def test_stack_monitor_rejection_follows_all_port_functions(self):
        path = "ra/fsp/src/rm_freertos_port/port.c"
        current = (rtos.ROOT / "baseline" / path).read_bytes()
        guard = (b'#if BSP_FEATURE_BSP_HAS_SECONDARY_CORE && RM_FREERTOS_PORT_CFG_HW_STACK_MONITOR_ENABLE && !BSP_FEATURE_BSP_HAS_SP_MON\r\n'
                 b' #error "Renesas SPMON is unavailable; use the CPU stack limit support on this device"\r\n'
                 b'#endif\r\n')
        self.assertEqual(1, current.count(guard))
        self.assertTrue(current.endswith(guard))
        self.assertGreater(current.index(guard), current.rindex(b"void vResetPrivilege"))
        self.assertEqual(current.count(b"\n"), current.count(b"\r\n"))
        self.assertNotIn(b"#line", current)

    def test_original_assertion_text_and_line_numbers_are_retained(self):
        path = "ra/fsp/src/rm_freertos_port/port.c"
        original = self.packs["port"]["files"][path]
        current = (rtos.ROOT / "baseline" / path).read_bytes()

        def assertion_locations(source):
            return [(number, line.strip()) for number, line in enumerate(source.splitlines(), 1)
                    if re.search(rb"\bconfigASSERT\s*\(", line)
                    and not line.lstrip().startswith((b"*", b"//"))]

        original_assertions = assertion_locations(original)
        self.assertTrue(original_assertions)
        self.assertEqual(original_assertions, assertion_locations(current))


class DependencyGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.prefix = "ra/kernel/"
        (self.project / self.prefix).mkdir(parents=True)
        self.files = {self.prefix + "kernel.c": b"int kernel;\n", self.prefix + "kernel.h": b"extern int kernel;\n"}
        for name, data in self.files.items():
            (self.project / name).write_bytes(data)
        self.pack = {"name": "original.pack", "sha256": "1" * 64, "files": self.files}
        self.rows = [{"file": str(self.project / self.prefix / "kernel.c"), "directory": str(self.project)}]

    def test_exact_original_dependencies_are_accepted(self):
        report = rtos.dependencies(self.project, self.pack, self.rows, self.prefix)
        self.assertEqual(set(self.files), set(report["files"]))
        self.assertEqual([self.prefix + "kernel.c"], report["translation_units"])

    def test_changed_kernel_header_is_rejected(self):
        (self.project / self.prefix / "kernel.h").write_text("/* substituted */")
        with self.assertRaisesRegex(ValueError, "not hash-identical"):
            rtos.dependencies(self.project, self.pack, self.rows, self.prefix)

    def test_missing_selected_kernel_source_is_rejected(self):
        (self.project / self.prefix / "kernel.c").unlink()
        with self.assertRaisesRegex(ValueError, "translation unit is missing"):
            rtos.dependencies(self.project, self.pack, self.rows, self.prefix)

    def test_extra_kernel_input_is_rejected(self):
        (self.project / self.prefix / "fake.h").write_text("/* substitute */")
        with self.assertRaisesRegex(ValueError, "not hash-identical"):
            rtos.dependencies(self.project, self.pack, self.rows, self.prefix)

    def test_duplicate_compile_database_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate compile database"):
            rtos.selected_rows(self.project, self.rows * 2, self.prefix)

    def test_preprocessor_keeps_target_flags_and_finds_effective_macros(self):
        command = ["gcc", "-mcpu=cortex-m33", "-c", "-o", "port.o", "port.c"]
        completed = subprocess.CompletedProcess(command, 0, "#define TX_PORT_PSPLIM_PRESENT\n"
                                                "#define BSP_CFG_RTOS_IDLE_SLEEP (1)\n", "")
        with patch.object(rtos.subprocess, "run", return_value=completed) as run:
            values = rtos.macro_values(command, self.project)
        actual = run.call_args.args[0]
        self.assertIn("-mcpu=cortex-m33", actual)
        self.assertNotIn("-o", actual)
        self.assertEqual(["-dM", "-E"], actual[-2:])
        self.assertEqual("", values["TX_PORT_PSPLIM_PRESENT"])
        self.assertEqual("(1)", values["BSP_CFG_RTOS_IDLE_SLEEP"])

    def test_pristine_and_candidate_source_sets_remain_distinct(self):
        path = "ra/fsp/src/rm_freertos_port/port.c"
        candidate = {path: b"adapted", "ra/fsp/src/bsp/mcu/new/header.h": b"target"}
        stock = {path: b"original"}
        self.assertEqual(b"original", rtos.source_overlay(candidate, stock, "stock")[path])
        self.assertEqual(b"adapted", rtos.source_overlay(candidate, stock, "candidate")[path])


if __name__ == "__main__":
    unittest.main()
