"""OLD-001: retained full-port compilation and independent EOF guard controls.

The retained RA4M1 project supplies real generated configuration, CMSIS, BSP and
original FreeRTOS headers for full-port comparisons. The all-family controls
compile only the production stack-selection block and EOF rejection with each
real feature header: they isolate admission/fallback, not whole-device builds.
"""
import itertools
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from ra8p1 import rtos_compatibility as rtos


PORT = "ra/fsp/src/rm_freertos_port/port.c"
FEATURES = rtos.ROOT / "baseline/ra/fsp/src/bsp/mcu"
DIAGNOSTIC = "Renesas SPMON is unavailable; use the CPU stack limit support on this device"


def selection(source):
    start = source.index(b"/* Determine which stack monitor to use. */")
    end = source.index(b"/* The IAR compiler often", start)
    return source[start:end]


def rejection(source):
    return source[source.rindex(b"\r\n#if ") + 2:]


class StackGuardControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which("arm-none-eabi-gcc")
        if cls.compiler is None:
            raise unittest.SkipTest("arm-none-eabi-gcc is required for stack guard controls")
        cls.current = (rtos.ROOT / "baseline" / PORT).read_bytes()
        cls.original = subprocess.run(
            ["git", "-C", str(rtos.ROOT / "baseline"), "show", "HEAD:" + PORT],
            check=True, capture_output=True).stdout

    def compile_control(self, folder, source):
        command = [self.compiler, "-x", "c", "-Werror", "-c", "-o", str(folder / "control.o"), "-"]
        compiled = subprocess.run(command, input=source, capture_output=True, timeout=30)
        return compiled, (folder / "control.o").read_bytes() if compiled.returncode == 0 else None

    def control_source(self, feature, request, original=False):
        prefix = (f'#include "{feature}"\n'
                  f'#define RM_FREERTOS_PORT_CFG_HW_STACK_MONITOR_ENABLE {request}\n').encode()
        body = selection(self.original if original else self.current)
        checks = (b"\n#if !BSP_FEATURE_BSP_HAS_SP_MON && RM_FREERTOS_PORT_PRV_USE_HW_STACK_MONITOR\n"
                  b'#error "Missing SPMON must retain the original disabled-monitor fallback"\n'
                  b"#endif\n"
                  b"int selected_monitor(void) { return RM_FREERTOS_PORT_PRV_USE_HW_STACK_MONITOR; }\n")
        return prefix + body + checks + (b"" if original else rejection(self.current))

    def test_all_old_feature_headers_keep_requested_and_disabled_fallbacks(self):
        old_headers = sorted(path for path in FEATURES.glob("*/bsp_feature.h")
                             if path.parent.name != "ra8p1")
        self.assertEqual(32, len(old_headers))
        no_monitor = 0
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for feature in old_headers:
                for request in (0, 1):
                    with self.subTest(device=feature.parent.name, request=request):
                        candidate = self.control_source(feature, request)
                        # No invented capability values: each control includes its owning feature header.
                        candidate += (b"\n#if BSP_FEATURE_BSP_HAS_SECONDARY_CORE\n"
                                      b'#error "Old control unexpectedly has a secondary core"\n'
                                      b"#endif\n")
                        original = self.control_source(feature, request, original=True)
                        before, before_object = self.compile_control(folder, original)
                        self.assertEqual(0, before.returncode, before.stderr.decode())
                        after, after_object = self.compile_control(folder, candidate)
                        self.assertEqual(0, after.returncode, after.stderr.decode())
                        self.assertEqual(before_object, after_object)
                        if request == 1:
                            cpp = subprocess.run([self.compiler, "-E", "-P", "-x", "c", "-"],
                                                 input=candidate, capture_output=True, timeout=30)
                            self.assertEqual(0, cpp.returncode, cpp.stderr.decode())
                            no_monitor += b"return (0);" in cpp.stdout
        self.assertEqual(19, no_monitor)

    def test_target_still_rejects_requested_monitor_but_accepts_disabled(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for request in (0, 1):
                with self.subTest(request=request):
                    source = self.control_source(FEATURES / "ra8p1/bsp_feature.h", request)
                    result, _ = self.compile_control(folder, source)
                    if request:
                        self.assertNotEqual(0, result.returncode)
                        self.assertIn(DIAGNOSTIC, result.stderr.decode())
                    else:
                        self.assertEqual(0, result.returncode, result.stderr.decode())

    def test_all_legacy_stack_layout_tokens_constants_and_relocations_match(self):
        old_headers = sorted(path for path in FEATURES.glob("*/bsp_feature.h")
                             if path.parent.name != "ra8p1")
        self.assertEqual(32, len(old_headers))
        observations = (b"\nconst unsigned stack_layout[] = {"
                        b"RM_FREERTOS_PORT_REGS_ON_PSP, RM_FREERTOS_PORT_CONTROL_ON_PSP, "
                        b"RM_FREERTOS_PORT_EXTRA_LR_ON_PSP, RM_FREERTOS_PORT_SECURE_ID_ON_PSP, "
                        b"RM_FREERTOS_PORT_PSPLIM_ON_PSP, RM_FREERTOS_PORT_PENDSV_PSP_WORDS, "
                        b"RM_FREERTOS_PORT_PENDSV_PSPLIM_OFFSET_BYTES, "
                        b"RM_FREERTOS_PORT_PSPLIM_PRESENT, RM_FREERTOS_PORT_SPMON_PRESENT};\n"
                        b"const unsigned *selected_layout(void) { return stack_layout; }\n")
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            # Isolated selection controls exercise both PSPLIM paths and context options;
            # they do not claim every combination is an actual configuration of each MCU.
            for feature, fpu, nonsecure, psplim in itertools.product(old_headers, (0, 1), (0, 1), (0, 1)):
                with self.subTest(device=feature.parent.name, fpu=fpu, nonsecure=nonsecure, psplim=psplim):
                    context = (f"#define __FPU_USED {fpu}\n"
                               f"#define BSP_TZ_NONSECURE_BUILD {nonsecure}\n").encode()
                    if psplim:
                        context += b"#define RENESAS_CORTEX_M33 1\n"
                    results = []
                    for original in (True, False):
                        source = context + self.control_source(feature, 1, original=original) + observations
                        cpp = subprocess.run([self.compiler, "-E", "-P", "-x", "c", "-"],
                                             input=source, capture_output=True, timeout=30)
                        self.assertEqual(0, cpp.returncode, cpp.stderr.decode())
                        compiled, obj = self.compile_control(folder, source)
                        self.assertEqual(0, compiled.returncode, compiled.stderr.decode())
                        sections = rtos.readonly_sections(obj)
                        self.assertTrue(any(s["kind"] == "executable" for s in sections.values()))
                        self.assertTrue(any(s["kind"] == "constant" for s in sections.values()))
                        self.assertTrue(any(s["relocations"] for s in sections.values()))
                        results.append((cpp.stdout.split(), obj, sections))
                    self.assertEqual(results[0], results[1])
        self.assertEqual(self.current.count(b"\n"), self.current.count(b"\r\n"))


class RetainedFreeRTOSPortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = rtos.ROOT / "validation/ra8p1/compatibility/rtos/controls/rtos_freertos_ra4m1"
        database = cls.project / "Debug/compile_commands.json"
        if not database.is_file():
            raise unittest.SkipTest("Retained real-kernel RA4M1 project is unavailable")
        cls.rows = json.loads(database.read_text())
        cls.row = rtos.selected_rows(cls.project, cls.rows, "ra/fsp/src/rm_freertos_port/")[PORT]
        cls.packs = rtos.original_release(rtos.ROOT)
        # Fail, rather than substitute a stub, if any retained kernel input was changed.
        rtos.dependencies(cls.project, cls.packs["freertos"], cls.rows, rtos.KERNEL_PREFIXES["freertos"])

    def test_full_original_and_candidate_port_tokens_and_object_bytes_match(self):
        with tempfile.TemporaryDirectory(prefix="old-stack-port-") as temporary:
            tree = Path(temporary) / "project"
            shutil.copytree(self.project, tree, ignore=shutil.ignore_patterns("Debug", ".git"))
            (tree / "Debug").mkdir()
            # Use the current owning header so SECONDARY_CORE is explicitly 0, not undefined.
            feature = "ra/fsp/src/bsp/mcu/ra4m1/bsp_feature.h"
            (tree / feature).write_bytes((rtos.ROOT / "baseline" / feature).read_bytes())
            output = tree / "Debug/port.o"
            base = rtos.command_for(self.row, self.project, tree, PORT, output)
            # Debug metadata is excluded; all code/data bytes in the ELF object are compared.
            base += ["-g0", "-ffile-prefix-map=" + str(tree) + "=$PROJECT"]
            for request in (0, 1):
                for tickless in (0, 1):
                    with self.subTest(request=request, tickless=tickless):
                        command = base + [f"-DRM_FREERTOS_PORT_CFG_HW_STACK_MONITOR_ENABLE={request}",
                                          f"-DconfigUSE_TICKLESS_IDLE={tickless}"]
                        results = []
                        for source in (self.packs["port"]["files"][PORT],
                                       (rtos.ROOT / "baseline" / PORT).read_bytes()):
                            (tree / PORT).write_bytes(source)
                            preprocessor = command.copy()
                            index = preprocessor.index("-o")
                            del preprocessor[index:index + 2]
                            preprocessor.remove("-c")
                            preprocessor += ["-E", "-P"]
                            cpp = subprocess.run(preprocessor, cwd=tree / "Debug", capture_output=True, timeout=60)
                            self.assertEqual(0, cpp.returncode, cpp.stderr.decode())
                            compiled = subprocess.run(command, cwd=tree / "Debug", capture_output=True, timeout=60)
                            self.assertEqual(0, compiled.returncode, compiled.stderr.decode())
                            results.append((cpp.stdout.split(), output.read_bytes()))
                        self.assertEqual(results[0][0], results[1][0], "Preprocessed legacy tokens changed")
                        self.assertEqual(results[0][1], results[1][1], "Legacy object bytes changed")


if __name__ == "__main__":
    unittest.main()
