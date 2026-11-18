"""Negative controls for measured legacy variant rejection, not target evidence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ra8p1 import compatibility as gate
from ra8p1 import legacy_negative as legacy


class LegacyNegativeTests(unittest.TestCase):
    def project(self, root, name, cpu, core, driver, factory):
        project = root / name
        (project / "Debug").mkdir(parents=True)
        (project / "ra/fsp").mkdir(parents=True)
        (project / "ra_cfg/fsp_cfg").mkdir(parents=True)
        (project / "ra_gen").mkdir()
        (project / "ra_gen/hal_data.h").write_bytes(b"generated target/control input")
        model = ('<raConfiguration><generalSettings><option key="CPU" value="' + cpu + '"/>'
                 '<option key="Core" value="' + core + '"/><option key="#FSPVersion#" value="5.9.0"/>'
                 '</generalSettings><stack module="' + factory + '.1"/></raConfiguration>')
        (project / "configuration.xml").write_text(model)
        source = project / ("ra/fsp/src/" + driver + "/" + driver + ".c")
        row = {"file": str(source), "directory": str(project / "Debug"),
               "arguments": ["/usr/bin/gcc", "-D_RA_CORE=" + core, "-mcpu=cortex-m85" if core == "CM85" else "-mcpu=cortex-m33",
                             "-c", "-o", str(project / "Debug/a.o"), str(source)]}
        (project / "Debug/compile_commands.json").write_text(json.dumps([row]))
        return project

    def control(self, root, driver="r_sci_uart"):
        project = self.project(root, "control", "RA4M1", "CM4", driver, legacy.DRIVERS[driver]["factory"])
        (project / "ra_cfg/fsp_cfg" / legacy.DRIVERS[driver]["config"]).write_bytes(b"/* generated configuration header file - do not edit */\n")
        return project

    def test_cfg_missing_is_blocked_even_alongside_legacy_type_errors(self):
        diagnostics = "error: unknown type name 'R_SCI0_Type'\nfatal error: r_sci_uart_cfg.h: No such file or directory"
        status, _, errors = legacy.diagnose("r_sci_uart", 1, diagnostics, 1)
        self.assertEqual(status, "blocked")
        self.assertEqual(errors, [])

    def test_unrelated_failure_and_suggested_names_are_not_variant_proof(self):
        for diagnostics in ("error: syntax error", "error: bad member; did you mean 'R_DAC_Type'?"):
            self.assertEqual(legacy.diagnose("r_dac", 1, diagnostics, 0)[0], "unrelated-failure")

    def test_semantic_type_errors_are_explicit_measured_negatives(self):
        for driver, symbol in (("r_sci_uart", "R_SCI0_Type"), ("r_dac", "R_DAC_Type")):
            status, _, errors = legacy.diagnose(driver, 1, "error: unknown type name '" + symbol + "'", 0)
            self.assertEqual(status, "measured-negative")
            self.assertEqual(len(errors), 1)

    def test_successful_compilation_is_not_negative_evidence(self):
        self.assertEqual(legacy.diagnose("r_dac", 0, "", 0)[0], "unexpected-compile")

    def test_unproven_dependencies_block_type_errors(self):
        self.assertEqual(legacy.diagnose("r_dac", 1, "error: unknown type name 'R_DAC_Type'", 0, ["missing owning BSP"])[0], "blocked")

    def test_control_header_bytes_and_model_database_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            control = self.control(Path(folder))
            data, record = legacy.control_config(control, "r_sci_uart")
            self.assertEqual(data, (control / "ra_cfg/fsp_cfg/r_sci_uart_cfg.h").read_bytes())
            self.assertEqual(record["header_sha256"], gate.digest(data))
            self.assertEqual(record["settings"]["CPU"], "RA4M1")

    def test_control_cannot_be_newer_fsp_or_target_variant(self):
        for before, after in (("5.9.0", "6.0.0"), ("RA4M1", "RA8P1")):
            with tempfile.TemporaryDirectory() as folder:
                control = self.control(Path(folder))
                model = control / "configuration.xml"
                model.write_text(model.read_text().replace(before, after))
                with self.assertRaisesRegex(ValueError, "older-device FSP 5.9.0"):
                    legacy.control_config(control, "r_sci_uart")

    def test_control_requires_real_factory_and_selected_source(self):
        for missing in ("factory", "source"):
            with tempfile.TemporaryDirectory() as folder:
                control = self.control(Path(folder))
                if missing == "factory":
                    model = control / "configuration.xml"
                    model.write_text(model.read_text().replace("module.driver.uart_on_sci", "module.driver.uart_on_sci_b_uart"))
                else:
                    (control / "Debug/compile_commands.json").write_text("[]")
                with self.assertRaises(ValueError):
                    legacy.control_config(control, "r_sci_uart")

    def test_absent_control_is_reported_without_running_compiler(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = self.project(root, "target", "RA8P1", "CM33", "r_ioport", "module.driver.ioport_on_ioport")
            with patch.object(legacy.subprocess, "run") as compiler:
                result = legacy.measure(root, target, "r_dac", root / "absent", {}, {})
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(result["compiler_invoked"])
            compiler.assert_not_called()

    def test_disposable_control_copy_and_exact_owning_dependency_checks(self):
        for proven in (False, True):
            with self.subTest(proven=proven), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                target = self.project(root, "target", "RA8P1", "CM85", "r_ioport", "module.driver.ioport_on_ioport")
                control = self.control(root)
                source = "ra/fsp/src/r_sci_uart/r_sci_uart.c"
                instance = "ra/fsp/inc/instances/r_sci_uart.h"
                api = "ra/fsp/inc/api/r_uart_api.h"
                feature = "ra/fsp/src/bsp/mcu/ra8p1/bsp_feature.h"
                candidate = {gate.DEVICE_HEADER: b"owning device header", feature: b"owning BSP"}
                stock = gate.OriginalSources()
                stock.update({source: b"original source", instance: b"original instance", api: b"original API"})
                stock.components["r_sci_uart"] = dict(stock)
                initial_target, initial_control = gate.fixture_inputs(target), gate.fixture_inputs(control)
                def compiler(command, **kwargs):
                    tree = Path(command[command.index("-o") + 1]).parents[1]
                    copied_cfg = tree / "legacy-control-cfg/r_sci_uart_cfg.h"
                    self.assertEqual(copied_cfg.read_bytes(), (control / "ra_cfg/fsp_cfg/r_sci_uart_cfg.h").read_bytes())
                    self.assertIn("-mcpu=cortex-m85", command)
                    self.assertEqual((tree / source).read_bytes(), stock[source])
                    if "-E" not in command:
                        return legacy.subprocess.CompletedProcess(command, 1, "", "error: unknown type name 'R_SCI0_Type'")
                    dependencies = [source, instance, api, "legacy-control-cfg/r_sci_uart_cfg.h", feature]
                    if proven:
                        dependencies.append(gate.DEVICE_HEADER)
                    Path(command[command.index("-MF") + 1]).write_text("object: " + " ".join(str(tree / path) for path in dependencies))
                    return legacy.subprocess.CompletedProcess(command, 0, "", "")
                with patch.object(legacy.subprocess, "run", side_effect=compiler):
                    result = legacy.measure(root, target, "r_sci_uart", control, stock, candidate)
                self.assertEqual(result["status"], "measured-negative" if proven else "blocked")
                self.assertFalse(result["compatible"])
                self.assertEqual(result["compiler_returncode"], 1)
                self.assertEqual(gate.fixture_inputs(target), initial_target)
                self.assertEqual(gate.fixture_inputs(control), initial_control)

    def test_report_never_overwrites_existing_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "evidence.json"
            report.write_text("preserved")
            with patch.object(gate, "original_sources") as original, self.assertRaises(SystemExit):
                legacy.main(["--target", folder, "--control", folder, "--report", str(report)])
            original.assert_not_called()
            self.assertEqual(report.read_text(), "preserved")

    def test_control_factories_match_original_census_ids(self):
        modules = json.loads((legacy.ROOT / "tools/ra8p1/compatibility_census.json").read_text())["modules"]
        for name, expected in legacy.DRIVERS.items():
            row = next(module for module in modules if module["name"] == name)
            self.assertIn(expected["factory"], row["module_ids"])

    def test_preparation_commands_are_parent_only_pinned_original_fsp(self):
        commands = legacy.preparation_commands(Path("validation/legacy control"))
        self.assertEqual(len(commands), 3)
        self.assertTrue(all("--lane 0" in command for command in commands))
        self.assertIn("--fsp 5.9.0", commands[0])
        self.assertIn("r_sci_uart:g_legacy_uart", commands[1])
        self.assertIn("r_dac:g_legacy_dac", commands[2])


if __name__ == "__main__":
    unittest.main()
