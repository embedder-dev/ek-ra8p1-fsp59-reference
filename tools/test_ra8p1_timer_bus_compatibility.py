"""Focused AGT/I3C capability gates: pristine tokens, host guards, real BSP compile.

Only temporary trees receive pending register headers or capability overlays.
No generated project, feature header, pack, IDE or target is changed.
"""
import itertools
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.ra8p1 import compatibility as gate
from tools.ra8p1 import generate_device_header as generator
from tools.ra8p1 import regression

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
DRIVERS = ("r_agt", "r_i3c")
HEADER = "ra/fsp/src/bsp/cmsis/Device/RENESAS/Include/R7KA8P1KF.h"
FEATURES = "ra/fsp/src/bsp/mcu/ra8p1/bsp_feature.h"
CAPABILITIES = ("BSP_FEATURE_I3C_HAS_HOT_JOIN", "BSP_FEATURE_I3C_HAS_TRANSITION_STALL",
                "BSP_FEATURE_I3C_HAS_ADDRESS_PHASE_STALL")
PROJECT = ROOT / "validation/ra8p1/compatibility/extra85"


def function(source, name):
    """Extract a complete production function, keeping its preprocessor guards."""
    match = re.search(r"^(?:static )?\w+ " + re.escape(name) + r" \(", source, re.M)
    if match is None:
        raise AssertionError("Missing production function: " + name)
    opening = source.index("{", match.start())
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


def register_header():
    canonical = (BASELINE / HEADER).read_bytes().decode()
    if all("} " + name + ";" in canonical for name in ("R_AGTX0_Type", "R_I3C0_Type")):
        return canonical
    from tools.test_ra8p1_bus_header import pending_inventory
    return generator.render(pending_inventory())


def compatibility_reports(project=PROJECT):
    modules = [{"name": name} for name in DRIVERS]
    stock = gate.original_sources(ROOT, modules)
    candidate = gate.candidate_sources(ROOT, "after")
    candidate[HEADER] = register_header().encode()
    features = candidate[FEATURES].decode()
    if not re.search(r"^#define\s+BSP_FEATURE_AGT_REGISTER_TYPE\b", features, re.M):
        features += "\n#define BSP_FEATURE_AGT_REGISTER_TYPE (1UL)\n"
    for capability in CAPABILITIES:
        if not re.search(r"^#define\s+" + capability + r"\b", features, re.M):
            features += "\n#define " + capability + " (0UL)\n"
    candidate[FEATURES] = features.encode()
    return [gate.compile_project(ROOT, project, modules, selected, "after", stock, candidate)
            for selected in ("stock", "candidate")]


class TimerBusCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("cc")
        if cls.cc is None:
            raise RuntimeError("Native C compiler required")
        cls.stock = gate.original_sources(ROOT)

    def preprocess(self, source, definitions, includes):
        result = subprocess.run([self.cc, "-E", "-P", "-x", "c", "-", "-I" + str(includes),
                                 *[f"-D{k}={v}" for k, v in definitions.items()]],
                                input=source, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_legacy_agt_objects_match_pristine_with_zero_agtw(self):
        """Replay real GNU flags; compare executable/constants and all relocations."""
        manifest_path = ROOT / "validation/ra8p1/compatibility/regression/r011-fixtures.json"
        if not manifest_path.exists():
            self.skipTest("Retained generated legacy regression fixtures are unavailable")
        manifest = json.loads(manifest_path.read_text())
        source = "ra/fsp/src/r_agt/r_agt.c"
        candidate = (BASELINE / source).read_bytes()
        for device, checks in itertools.product(("ra8m1", "ra4m1"), (0, 1)):
            name = f"{device}_checks_{'on' if checks else 'off'}"
            with self.subTest(fixture=name), tempfile.TemporaryDirectory(prefix="agt-object-") as temporary:
                scratch = Path(temporary)
                tree = scratch / "project"
                regression.unpack_fixture(ROOT, manifest["fixtures"][name], tree)
                rows = json.loads((tree / "Debug/compile_commands.json").read_text())
                row = next(item for item in rows if item["file"].endswith("/" + source))
                for path, data in self.stock.items():
                    if path.endswith(".h") and (tree / path).is_file():
                        (tree / path).write_bytes(data)
                wrapper = scratch / "legacy.h"
                wrapper.write_text('#include "bsp_api.h"\n'
                                   '#define BSP_FEATURE_AGT_REGISTER_TYPE (0UL)\n'
                                   '#if BSP_FEATURE_AGT_AGTW_CHANNEL_COUNT != 0\n'
                                   '#error Expected a real zero-AGTW legacy fixture\n#endif\n'
                                   f'#if BSP_CFG_PARAM_CHECKING_ENABLE != {checks}\n'
                                   '#error Incorrect checking fixture\n#endif\n')
                sections = []
                for data in (self.stock[source], candidate):
                    (tree / source).write_bytes(data)
                    output = scratch / "agt.o"
                    command, cwd, _ = regression.compile_command(row, tree, output)
                    command += ["-include", str(wrapper)]
                    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    sections.append(regression.readonly_sections(output.read_bytes()))
                self.assertTrue(any(part["kind"] == "executable" for part in sections[0].values()))
                self.assertEqual(sections[0], sections[1])

    def test_agt_only_tokens_have_no_absent_registers(self):
        source = (BASELINE / "ra/fsp/src/r_agt/r_agt.c").read_text()
        with tempfile.TemporaryDirectory(prefix="agt-only-") as directory:
            include = Path(directory)
            (include / "r_agt.h").write_text("")
            definitions = {"AGT_CFG_PARAM_CHECKING_ENABLE": 1, "AGT_CFG_INPUT_SUPPORT_ENABLE": 1,
                           "AGT_CFG_OUTPUT_SUPPORT_ENABLE": 1, "BSP_FEATURE_AGT_AGTW_CHANNEL_COUNT": 0,
                           "BSP_FEATURE_AGT_REGISTER_TYPE": 1}
            tokens = self.preprocess(source, definitions, include)
            self.assertNotIn("AGT32", tokens)
            self.assertNotIn("AGTIOSEL_ALT", tokens)
            for entry in ("R_AGT_Start", "R_AGT_Reset", "R_AGT_Enable", "R_AGT_DutyCycleSet",
                          "R_AGT_StatusGet", "r_agt_period_register_set", "agt_int_isr"):
                self.assertIn(entry, tokens)

    def test_legacy_i3c_objects_match_pristine(self):
        """Real legacy compiler objects, not raw source/whitespace equivalence."""
        manifest_path = ROOT / "validation/ra8p1/compatibility/regression/r011-fixtures.json"
        if not manifest_path.exists():
            self.skipTest("Retained generated legacy regression fixtures are unavailable")
        manifest = json.loads(manifest_path.read_text())
        source = "ra/fsp/src/r_i3c/r_i3c.c"
        candidate = (BASELINE / source).read_bytes()
        for checks in (0, 1):
            fixture = f"ra8m1_checks_{'on' if checks else 'off'}"
            with self.subTest(fixture=fixture), tempfile.TemporaryDirectory(prefix="i3c-object-") as temporary:
                scratch = Path(temporary)
                tree = scratch / "project"
                regression.unpack_fixture(ROOT, manifest["fixtures"][fixture], tree)
                rows = json.loads((tree / "Debug/compile_commands.json").read_text())
                row = next(item for item in rows if item["file"].endswith("/" + source))
                for path, data in self.stock.items():
                    if path.endswith(".h") and (tree / path).is_file():
                        (tree / path).write_bytes(data)
                wrapper = scratch / "legacy.h"
                wrapper.write_text('#include "bsp_api.h"\n' +
                                   "".join(f"#define {name} (1UL)\n" for name in CAPABILITIES) +
                                   '#if BSP_FEATURE_I3C_IS_AVAILABLE != 1\n#error Expected real legacy I3C\n#endif\n' +
                                   f'#if BSP_CFG_PARAM_CHECKING_ENABLE != {checks}\n#error Incorrect checking fixture\n#endif\n')
                sections = []
                for data in (self.stock[source], candidate):
                    (tree / source).write_bytes(data)
                    output = scratch / "i3c.o"
                    command, cwd, _ = regression.compile_command(row, tree, output)
                    result = subprocess.run([*command, "-include", str(wrapper)], cwd=cwd,
                                            capture_output=True, text=True, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    sections.append(regression.readonly_sections(output.read_bytes()))
                self.assertTrue(any(part["kind"] == "executable" for part in sections[0].values()))
                self.assertEqual(sections[0], sections[1])

    def test_i3c_rejection_is_side_effect_free_with_checks_on_and_off(self):
        """Run unchanged production Open/Enable/IbiWrite bodies with real FSP APIs."""
        source = (BASELINE / "ra/fsp/src/r_i3c/r_i3c.c").read_text()
        header = register_header()
        end = header.index("} R_I3C0_Type;") + len("} R_I3C0_Type;")
        start = header.rfind("typedef struct", 0, end)
        registers = header[start:end] + "\n" + "\n".join(
            re.findall(r"^#define R_I3C0_.*$", header, re.M))
        enum_start = source.index("typedef enum e_i3c_internal_state")
        enum_end = source.index("} i3c_internal_state_t;", enum_start) + len("} i3c_internal_state_t;")
        macros = source[source.index("#define I3C_OPEN"):source.index("/* ISR function prototypes.")]
        # Stop before unrelated function declarations; all numeric driver constants remain original.
        macros = macros[:macros.index("/***********************************************************************************************************************")]
        selected = "\n".join(function(source, name) for name in
                             ("i3c_extended_cfg_check", "R_I3C_Open", "R_I3C_Enable", "R_I3C_IbiWrite"))
        bsp = r'''
#ifndef BSP_API_H
#define BSP_API_H
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "fsp_common_api.h"
typedef int IRQn_Type;
#define BSP_ALIGN_VARIABLE(n) __attribute__((aligned(n)))
#define __IOM volatile
#define __IM volatile const
#define __OM volatile
#define FSP_ERROR_RETURN(c,e) do { if (!(c)) return (e); } while (0)
#define FSP_ASSERT(c) FSP_ERROR_RETURN(c, FSP_ERR_ASSERTION)
#define FSP_HARDWARE_REGISTER_WAIT(a,b) do { (void)(a); (void)(b); } while (0)
''' + registers + r'''
extern R_I3C0_Type test_registers;
extern unsigned module_starts;
extern unsigned irq_enables;
#define R_I3C0 (&test_registers)
#define R_BSP_MODULE_START(ip,ch) do { (void)(ch); module_starts++; } while (0)
#define R_BSP_IrqCfgEnable(irq,ipl,ctx) do { (void)(irq); (void)(ipl); (void)(ctx); irq_enables++; } while (0)
#endif
'''
        harness = r'''
#include <assert.h>
#include "r_i3c.h"
R_I3C0_Type test_registers;
unsigned module_starts, irq_enables;
static uint32_t i3c_next_data_word_calculate(i3c_write_buffer_descriptor_t * p) { (void)p; return 0; }
''' + source[enum_start:enum_end] + "\n" + macros + "\n" + selected + r'''
static void callback(i3c_callback_args_t const * const p) { (void)p; }
int main(void)
{
    for (unsigned option = 0; option < 5; option++)
    {
        i3c_extended_cfg_t ext = {.slave_command_response_info = {.write_length = 8, .read_length = 16}};
        i3c_cfg_t cfg = {.p_extend = &ext, .p_callback = callback,
                     .device_type = I3C_CFG_MASTER_SUPPORT ? I3C_DEVICE_TYPE_MAIN_MASTER : I3C_DEVICE_TYPE_SLAVE};
        if (option == 0) ext.ibi_control.hot_join_acknowledge = 1;
        if (option == 1) ext.ibi_control.notify_rejected_hot_join_requests = 1;
        if (option == 2) ext.slave_command_response_info.hotjoin_request_enable = 1;
        if (option == 3) ext.bitrate_settings.clock_stalling.transition_phase_enable = 1;
        if (option == 4) ext.bitrate_settings.clock_stalling.assigned_address_phase_enable = 1;
        i3c_instance_ctrl_t ctrl = {0}, saved;
        unsigned char registers_before[sizeof(test_registers)];
        memset(&test_registers, 0xa5, sizeof(test_registers));
        memcpy(registers_before, &test_registers, sizeof(test_registers));
        memcpy(&saved, &ctrl, sizeof(ctrl));
        assert(R_I3C_Open(&ctrl, &cfg) == FSP_ERR_UNSUPPORTED);
        assert(memcmp(&ctrl, &saved, sizeof(ctrl)) == 0);
        assert(memcmp(&test_registers, registers_before, sizeof(test_registers)) == 0);
        assert(module_starts == 0 && irq_enables == 0);
        ctrl.open = I3C_OPEN;
        ctrl.p_cfg = &cfg;
        ctrl.p_reg = &test_registers;
        memcpy(&saved, &ctrl, sizeof(ctrl));
        assert(R_I3C_Enable(&ctrl) == FSP_ERR_UNSUPPORTED);
        assert(memcmp(&ctrl, &saved, sizeof(ctrl)) == 0);
        assert(memcmp(&test_registers, registers_before, sizeof(test_registers)) == 0);
        assert(module_starts == 0 && irq_enables == 0);
    }
    i3c_extended_cfg_t ext = {.slave_command_response_info = {.write_length = 8, .read_length = 16}};
    ext.ibi_control.notify_rejected_mastership_requests = 1;
    ext.ibi_control.notify_rejected_interrupt_requests = 1;
    ext.bitrate_settings.clock_stalling.parity_phase_enable = 1;
    ext.bitrate_settings.clock_stalling.ack_phase_enable = 1;
    ext.bitrate_settings.clock_stalling.clock_stalling_time = 30;
    ext.slave_command_response_info.inband_interrupt_enable = 1;
    i3c_cfg_t cfg = {.p_extend = &ext, .p_callback = callback,
                     .device_type = I3C_CFG_MASTER_SUPPORT ? I3C_DEVICE_TYPE_MAIN_MASTER : I3C_DEVICE_TYPE_SLAVE};
    i3c_instance_ctrl_t ctrl = {0};
    memset(&test_registers, 0, sizeof(test_registers));
    assert(R_I3C_Open(&ctrl, &cfg) == FSP_SUCCESS);
    assert(module_starts == 1);
    assert(R_I3C_Enable(&ctrl) == FSP_SUCCESS);
    assert(test_registers.BCTL_b.BUSE == 1);
    assert(test_registers.IBINCTL == (R_I3C0_IBINCTL_NRMRCTL_Msk | R_I3C0_IBINCTL_NRSIRCTL_Msk));
    /* HM41.2.26 pp2485–2486: ACKPE is bit31 and must be computed without signed-shift UB. */
    assert(test_registers.SCSTLCTL == (0x80000000U | R_I3C0_SCSTLCTL_PARPE_Msk | 30U));
    assert(test_registers.CSECMD == (I3C_CFG_SLAVE_SUPPORT ? R_I3C0_CSECMD_SVIRQE_Msk : 0U));
    assert(irq_enables > 0);
#if I3C_CFG_SLAVE_SUPPORT
    ctrl.internal_state = I3C_INTERNAL_STATE_SLAVE_IDLE;
    i3c_instance_ctrl_t saved;
    unsigned char registers_before[sizeof(test_registers)];
    memcpy(&saved, &ctrl, sizeof(ctrl));
    memcpy(registers_before, &test_registers, sizeof(test_registers));
    assert(R_I3C_IbiWrite(&ctrl, I3C_IBI_TYPE_HOT_JOIN, NULL, 0) == FSP_ERR_UNSUPPORTED);
    assert(memcmp(&ctrl, &saved, sizeof(ctrl)) == 0);
    assert(memcmp(&test_registers, registers_before, sizeof(test_registers)) == 0);
    assert(R_I3C_IbiWrite(&ctrl, I3C_IBI_TYPE_INTERRUPT, NULL, 0) == FSP_SUCCESS);
#endif
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix="i3c-guards-") as temporary:
            directory = Path(temporary)
            (directory / "bsp_api.h").write_text(bsp)
            c_file = directory / "guard.c"
            c_file.write_text(harness)
            for checks, (master, slave) in itertools.product((0, 1), ((1, 1), (1, 0), (0, 1))):
                with self.subTest(checks=checks, master=master, slave=slave):
                    definitions = {**dict.fromkeys(CAPABILITIES, 0),
                                   "I3C_CFG_PARAM_CHECKING_ENABLE": checks,
                                   "I3C_CFG_MASTER_SUPPORT": master, "I3C_CFG_SLAVE_SUPPORT": slave,
                                    "BSP_FEATURE_I3C_IS_AVAILABLE": 1,
                                    "BSP_FEATURE_I3C_HAS_HDR_MODE": 1,
                                   "BSP_FEATURE_I3C_NUM_CHANNELS": 1}
                    binary = directory / "guard"
                    result = subprocess.run([self.cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                                             "-Wno-pointer-to-int-cast", "-Wno-unused-function",
                                             "-fsanitize=undefined", "-fno-sanitize-recover=all",
                                             "-I" + str(directory), "-include", str(directory / "bsp_api.h"),
                                             "-I" + str(BASELINE / "ra/fsp/inc"),
                                             "-I" + str(BASELINE / "ra/fsp/inc/instances"),
                                             "-I" + str(BASELINE / "ra/fsp/inc/api"),
                                             *[f"-D{k}={v}" for k, v in definitions.items()],
                                             str(c_file), "-o", str(binary)],
                                            capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_known_legacy_ack_phase_signed_shift_is_identical(self):
        """Record inherited UB explicitly instead of weakening the guard sanitizer."""
        source = "ra/fsp/src/r_i3c/r_i3c.c"
        pattern = r"    scstlctl \|= .*clock_stalling\.ack_phase_enable.*;"
        with tempfile.TemporaryDirectory(prefix="i3c-legacy-preprocess-") as temporary:
            include = Path(temporary)
            for header in ("r_i3c.h", "r_i3c_cfg.h"):
                (include / header).write_text("")
            definitions = {**dict.fromkeys(CAPABILITIES, 1), "BSP_FEATURE_I3C_IS_AVAILABLE": 1}
            before = re.search(pattern, self.preprocess(self.stock[source].decode(), definitions, include)).group()
            after = re.search(pattern, self.preprocess((BASELINE / source).read_text(), definitions, include)).group()
        with tempfile.TemporaryDirectory(prefix="i3c-legacy-shift-") as temporary:
            directory = Path(temporary)
            for revision, statement in (("stock", before), ("candidate", after)):
                with self.subTest(revision=revision):
                    program = ('#include <stdint.h>\n#define R_I3C0_SCSTLCTL_ACKPE_Pos 31U\n'
                               'int main(void) { struct { struct { struct { unsigned ack_phase_enable:1; } '
                               'clock_stalling; } bitrate_settings; } cfg = {0}, *p_extend = &cfg; '
                               'cfg.bitrate_settings.clock_stalling.ack_phase_enable = 1; '
                               'uint32_t scstlctl = 0;\n' + statement + '\n(void)scstlctl; return 0; }\n')
                    source_file, binary = directory / (revision + ".c"), directory / revision
                    source_file.write_text(program)
                    compiled = subprocess.run([self.cc, "-fsanitize=undefined", "-fno-sanitize-recover=all",
                                               str(source_file), "-o", str(binary)],
                                              capture_output=True, text=True, timeout=30)
                    self.assertEqual(compiled.returncode, 0, compiled.stderr)
                    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("left shift of 1 by 31", result.stderr)

    def test_generated_bsp_pristine_failure_adapted_success(self):
        if not (PROJECT / "Debug/compile_commands.json").exists():
            self.skipTest("Generated extra85 integration fixture is unavailable")
        pristine, adapted = compatibility_reports()
        self.assertEqual(pristine["generated_inputs"], adapted["generated_inputs"])
        for name in DRIVERS:
            with self.subTest(driver=name):
                self.assertEqual(pristine["modules"][name]["status"], "fail")
                row = adapted["modules"][name]
                self.assertEqual(row["status"], "pass", json.dumps(row, indent=2))
                self.assertTrue(row["sources"][f"ra/fsp/src/{name}/{name}.c"]["defined_symbols"])
        diagnostics = str(pristine["modules"])
        for absent in ("AGT32", "HJACKCTL", "NRHJCTL", "TRAPE", "HJEVE"):
            self.assertIn(absent, diagnostics)

    def test_generated_bsp_core_and_checking_compiler_variants(self):
        """Compiler variants of extra85, not separately generated CM33 projects."""
        if not (PROJECT / "Debug/compile_commands.json").exists():
            self.skipTest("Generated extra85 integration fixture is unavailable")
        original_command = gate.command_for
        with tempfile.TemporaryDirectory(prefix="timer-bus-variants-") as temporary:
            wrapper = Path(temporary) / "checking.h"
            for core, checks in itertools.product(("CM85", "CM33"), (0, 1)):
                wrapper.write_text('#include "bsp_api.h"\n#undef BSP_CFG_PARAM_CHECKING_ENABLE\n'
                                   f'#define BSP_CFG_PARAM_CHECKING_ENABLE ({checks})\n')

                def command(*args):
                    selected = original_command(*args)
                    selected = [f"-D_RA_CORE={core}" if arg.startswith("-D_RA_CORE=") else
                                ("-mcpu=cortex-m33" if core == "CM33" and arg.startswith("-mcpu=") else arg)
                                for arg in selected]
                    return [*selected, "-include", str(wrapper)]

                with self.subTest(core=core, checks=checks), patch.object(gate, "command_for", command):
                    pristine, adapted = compatibility_reports()
                    for name in DRIVERS:
                        self.assertEqual(pristine["modules"][name]["status"], "fail")
                        row = adapted["modules"][name]
                        self.assertEqual(row["status"], "pass", json.dumps(row, indent=2))

    def test_original_crlf_format_preserved(self):
        # Behavioral preservation is checked by compiled objects and the legacy UB fixture,
        # not by requiring old source lines to survive an intentional target-specific repair.
        for name in DRIVERS:
            candidate = (BASELINE / f"ra/fsp/src/{name}/{name}.c").read_bytes()
            self.assertEqual(candidate.count(b"\n"), candidate.count(b"\r\n"))


if __name__ == "__main__":
    unittest.main()
