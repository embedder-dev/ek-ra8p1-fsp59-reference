"""Independent FREERTOS-001..008 controls; no IDE, pack installation, project or hardware writes.

Primary anchors: RA8P1 HM 2.7.1/2.12/11.8.10 figures 11.7-8 (pp118,156,496-497),
Arm M85 TRM 101924_0101_07 4.5 p47, original 5.9 release kernel tasks.c4504-4537
and timers.c294-301. Real kernel/CMSIS dependencies are extracted into temporary directories.
"""
from io import BytesIO
import itertools
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from ra8p1 import rtos_compatibility as original
from ra8p1.regression import readonly_sections
from ra8p1.review_freertos.layout import verify as verify_layout

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tools/ra8p1/review_freertos"
PORT = ROOT / "baseline/ra/fsp/src/rm_freertos_port/port.c"
MDF = ROOT / "baseline/module_descriptions/AWS##RTOS##FreeRTOS##all####11.1.0+fsp.5.9.0.xml"
PORT_KEY = "ra/fsp/src/rm_freertos_port/port.c"
MDF_KEY = ".module_descriptions/" + MDF.name
PREFIX = original.KERNEL_PREFIXES["freertos"]


def function(text, name):
    match = re.search(r"(?m)^[ \t]*(?:__attribute__\(\(weak\)\) )?(?:static )?(?:void|StackType_t \*)\s*" + name + r"\s*\([^;]*?\)\s*\{", text)
    if not match:
        raise AssertionError("Missing production definition: " + name)
    brace = text.index("{", match.start())
    depth, end = 1, brace + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[match.start():end] + "\n"


def inline_assembly(preprocessed, name):
    body = function(preprocessed, name)
    start = body.index("__asm")
    # Basic inline-assembly strings; no C escapes other than whitespace are used here.
    return "".join(bytes(s, "ascii").decode("unicode_escape") for s in
                   re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', body[start:]))


class FreeRtosReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("arm-none-eabi-gcc")
        # Prefer the complete compiler recorded by the retained input; PATH can contain GCC without newlib.
        database = ROOT / "validation/ra8p1/compatibility/rtos/rtos_freertos_cm33/Debug/compile_commands.json"
        if database.is_file():
            row = json.loads(database.read_text())[0]
            compiler = (row.get("arguments") or shlex.split(row["command"]))[0]
            if Path(compiler).is_file():
                cls.cc = compiler
        cls.cxx = shutil.which("c++")
        if not cls.cc or not cls.cxx:
            raise RuntimeError("ARM GCC and a native C++ compiler are required")
        cls.packs = original.original_release(ROOT)  # Pins the whole release archive SHA256.
        cls.pristine = cls.packs["port"]["files"][PORT_KEY].decode()
        cls.current = PORT.read_text()
        with ZipFile(ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip") as release:
            with ZipFile(BytesIO(release.read("internal/projectgen/ra/packs/Arm.CMSIS6.6.1.0+fsp.5.9.0.pack"))) as pack:
                cls.cmsis = {n: pack.read(n) for n in pack.namelist() if n.endswith(".h")}
        cls.temporary = tempfile.TemporaryDirectory(prefix="review-freertos-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.kernel = cls.root / "kernel"
        for name, data in cls.packs["freertos"]["files"].items():
            if name.startswith(PREFIX):
                p = cls.kernel / name.removeprefix(PREFIX)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
        cls.cmsis_dir = cls.root / "cmsis"
        cls.cmsis_dir.mkdir()
        for name, data in cls.cmsis.items():
            if "/Core/Include/" in name:
                p = cls.cmsis_dir / name.split("/Core/Include/", 1)[1]
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
        cls.port_headers = cls.root / "port-headers"
        cls.port_headers.mkdir()
        for name, data in cls.packs["port"]["files"].items():
            if name.startswith("ra/fsp/src/rm_freertos_port/") and name.endswith(".h"):
                (cls.port_headers / Path(name).name).write_bytes(data)

    def run_command(self, command, *, cwd=None, success=True):
        result = subprocess.run(list(map(str, command)), cwd=cwd, capture_output=True, text=True, timeout=60)
        if success:
            self.assertEqual(result.returncode, 0, " ".join(map(str, command)) + "\n" + result.stdout + result.stderr)
        return result

    def arm_command(self, directory, *, core=0, fpu=1, ns=0, checks=1, target=1, tickless=1, monitor=0):
        return [self.cc, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-ffunction-sections", "-fdata-sections",
                "-mcpu=" + ("cortex-m85" if core == 0 else "cortex-m33"), "-mthumb",
                "-mfloat-abi=" + ("hard" if fpu else "soft"), *(["-mfpu=fpv5-sp-d16"] if fpu else []),
                f"-DBSP_CFG_CPU_CORE={core}", f"-DTEST_FPU={fpu}", f"-DBSP_TZ_NONSECURE_BUILD={ns}",
                f"-DBSP_CFG_PARAM_CHECKING_ENABLE={checks}", f"-DTEST_TARGET={target}",
                f"-DconfigUSE_TICKLESS_IDLE={tickless}", f"-DRM_FREERTOS_PORT_CFG_HW_STACK_MONITOR_ENABLE={monitor}",
                "-I" + str(directory), "-I" + str(FIX), "-I" + str(self.port_headers),
                "-I" + str(self.kernel / "include"), "-I" + str(self.cmsis_dir)]

    def test_complete_port_real_kernel_matrix_and_custom_tickless(self):
        with tempfile.TemporaryDirectory(dir=self.root) as temp:
            d = Path(temp)
            (d / "port.c").write_text(self.current)
            for core, fpu, ns, checks, tickless in itertools.product((0, 1), (0, 1), (0, 1), (0, 1), (0, 1, 2)):
                with self.subTest(core=core, fpu=fpu, ns=ns, checks=checks, tickless=tickless):
                    cmd = self.arm_command(d, core=core, fpu=fpu, ns=ns, checks=checks, tickless=tickless)
                    self.run_command(cmd + ["-MD", "-MF", "port.d", "-c", "port.c", "-o", "port.o"], cwd=d)
                    deps = (d / "port.d").read_text()
                    for header in ("FreeRTOS.h", "task.h", "portable.h", "projdefs.h", "mpu_wrappers.h"):
                        self.assertIn(str(self.kernel / "include" / header), deps)
                    self.assertIn(str(self.port_headers / "portmacro.h"), deps)
                    pre = self.run_command(cmd + ["-E", "-P", "port.c"], cwd=d).stdout
                    save = inline_assembly(pre, "PendSV_Handler")
                    restore = inline_assembly(pre, "rm_freertos_port_restore_task_stackless")
                    # Mainline integer contexts always save before PSPLIM/security metadata, also with FPU disabled.
                    self.assertLess(save.index("STMDB     R2!, {R4-R11"), save.index("MRS     R3, PSPLIM"))
                    self.assertNotIn("STMIA   R2!, {R4-R7}", save)
                    self.assertIn("LDMIA   R2!, {R4-R11" + ("}" if ns else ", LR}"), restore)
                    self.assertIn("BX     LR", restore)
                    if not fpu:
                        self.assertNotRegex(save + restore, r"VSTM|VLDM")
                    for active_fp, secure_frame in itertools.product((0, 1) if fpu else (0,),
                                                                     (0, 1) if ns else (0,)):
                        verify_layout(save, restore, fpu=fpu, nonsecure=ns,
                                      active_fp=active_fp, secure_frame=secure_frame)
            # Compile the actual original scheduler and timers, not hand-authored task declarations.
            cmd = self.arm_command(d)
            for unit in ("tasks.c", "timers.c", "list.c", "queue.c"):
                # Original static-only tasks.c has an unused prvDeleteTCB parameter; retain the warning.
                self.run_command([arg for arg in cmd if arg != "-Werror"] +
                                 ["-c", self.kernel / unit, "-o", d / (unit + ".o")])

    def test_psplim_reserve_covers_general_register_and_fp_stores(self):
        with tempfile.TemporaryDirectory(dir=self.root) as temp:
            d = Path(temp)
            for core, ns, fpu in itertools.product((0, 1), repeat=3):
                # ABI software stores: R4-R11, optional S16-S31, PSPLIM and per-task EXC_RETURN.
                # Nonsecure additionally stores the secure context id; its unused MPU word is conservative.
                words = 8 + 16 * fpu + 1 + (2 if ns else 1)
                for old, text in ((False, self.current), (True, self.pristine)):
                    with self.subTest(core=core, ns=ns, fpu=fpu, old=old):
                        (d / "port.c").write_text(text + "\n"
                            "typedef char reserve_bounds[(RM_FREERTOS_PORT_PENDSV_PSPLIM_OFFSET_BYTES >= "
                            + str(words * 4) + ") ? 1 : -1];\n"
                            "typedef char reserve_alignment[(RM_FREERTOS_PORT_PENDSV_PSPLIM_OFFSET_BYTES % 8 == 0) ? 1 : -1];\n")
                        cmd = self.arm_command(d, core=core, ns=ns, fpu=fpu)
                        result = self.run_command(cmd + ["-c", "port.c", "-o", "reserve.o"], cwd=d,
                                                  success=False)
                        self.assertEqual(result.returncode == 0, not (old and fpu))
                        if old and fpu:
                            self.assertIn("reserve_bounds", result.stderr)
                        if old and not fpu:
                            pre = self.run_command(cmd + ["-E", "-P", "port.c"], cwd=d).stdout
                            with self.assertRaises((AssertionError, KeyError)):
                                verify_layout(inline_assembly(pre, "PendSV_Handler"),
                                              inline_assembly(pre, "rm_freertos_port_restore_task_stackless"),
                                              fpu=fpu, nonsecure=ns)

    def test_legacy_preprocessed_executable_constant_relocation_parity(self):
        with tempfile.TemporaryDirectory(dir=self.root) as temp:
            d = Path(temp)
            for core, fpu, ns, checks, monitor in itertools.product((0, 1), (0, 1), (0, 1), (0, 1), (0, 1)):
                # Legacy FPU-less nonsecure is itself broken in 5.9; preprocessing is still required.
                with self.subTest(core=core, fpu=fpu, ns=ns, checks=checks, monitor=monitor):
                    pre, objects = [], []
                    for index, text in enumerate((self.pristine, self.current)):
                        (d / "port.c").write_text(text)
                        cmd = self.arm_command(d, target=0, core=core, fpu=fpu, ns=ns, checks=checks, monitor=monitor)
                        pre.append(self.run_command(cmd + ["-E", "-P", "port.c"], cwd=d).stdout.split())
                        self.run_command(cmd + ["-c", "port.c", "-o", f"port{index}.o"], cwd=d)
                        objects.append(readonly_sections((d / f"port{index}.o").read_bytes()))
                    self.assertEqual(pre[0], pre[1])  # Includes __LINE__ values; no masking or #line directives.
                    self.assertEqual(objects[0], objects[1])

    def model_source(self, text):
        prefix = text[:text.index("void SVC_Handler (void)")]
        result = prefix + "\n"
        names = ("rm_freertos_port_reset_systick", "SysTick_Handler", "rm_freertos_port_sleep_preserving_lpm",
                 "vPortSuppressTicksAndSleep", "vPortSetupTimerInterrupt", "rm_freertos_port_setup_timer",
                 "rm_freertos_port_wait", "rm_freertos_port_suppress_ticks")
        for name in names:
            if name == "rm_freertos_port_reset_systick":
                result += "#if !TEST_TARGET\n" + function(text, name) + "#endif\n"
            elif re.search(r"(?m)^(?:static )?void " + name + r" \(", text) or name.startswith("vPort"):
                result += function(text, name)
        return result + (FIX / "model.cpp").read_text()

    def native_model(self, directory, text, *, target=1, core=0, ns=0, checks=1, extra=()):
        (directory / "bsp_api.h").write_text("#pragma once\n" + (FIX / "model_bsp.hpp").read_text())
        (directory / "FreeRTOSConfig.h").write_bytes((FIX / "FreeRTOSConfig.h").read_bytes())
        (directory / "model.cpp").write_text(self.model_source(text))
        self.run_command([self.cxx, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
                          "-Wno-unused-variable", "-Wno-attributes", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                          f"-DTEST_TARGET={target}", f"-DBSP_CFG_CPU_CORE={core}", "-DTEST_FPU=1",
                          f"-DBSP_TZ_NONSECURE_BUILD={ns}", f"-DBSP_CFG_PARAM_CHECKING_ENABLE={checks}", *extra,
                          "-I" + str(directory), "-I" + str(FIX), "-I" + str(self.port_headers),
                          "-I" + str(self.kernel / "include"), directory / "model.cpp", "-o", directory / "model"])
        return directory / "model"

    def test_delayed_systick_model_early_expiry_abort_and_sleep_prerequisites(self):
        with tempfile.TemporaryDirectory(dir=self.root) as temp:
            d = Path(temp)
            for core, ns, checks, external in itertools.product((0, 1), repeat=4):
                with self.subTest(core=core, ns=ns, checks=checks, external=external):
                    binary = self.native_model(d, self.current, core=core, ns=ns, checks=checks,
                                               extra=(["-DconfigSYSTICK_CLOCK_HZ=1000000U"] if external else []))
                    for case in ("early", "zero", "one", "boundary", "crossed", "expiry", "late", "abort", "pending", "sleep"):
                        # x selects expiry; 'early' intentionally selects the default early-wake case.
                        case = "x" if case == "expiry" else case
                        self.run_command([binary, case])

    def test_invalid_reload_and_source_fail_closed_even_without_asserts(self):
        with tempfile.TemporaryDirectory(dir=self.root) as temp:
            d = Path(temp)
            for checks, extra in itertools.product((0, 1), (["-DconfigTICK_RATE_HZ=1"],
                    ["-DconfigTICK_RATE_HZ=0"], ["-DconfigSYSTICK_CLOCK_HZ=2000000U"],
                    ["-DconfigTICK_RATE_HZ=24000000"])):
                with self.subTest(checks=checks, extra=extra):
                    binary = self.native_model(d, self.current, checks=checks, extra=extra)
                    self.run_command([binary, "invalid"])

    def test_independent_failing_before_production_controls(self):
        with tempfile.TemporaryDirectory(dir=self.root) as temp:
            d = Path(temp)
            # The pristine release is the independent production control, not a fixture formula or mutated mock.
            binary = self.native_model(d, self.pristine, target=0)
            for case in ("early", "crossed", "x", "sleep", "abort", "pending"):
                with self.subTest(case=case):
                    self.assertNotEqual(self.run_command([binary, case], success=False).returncode, 0)
            binary = self.native_model(d, self.pristine, target=0, extra=["-DconfigTICK_RATE_HZ=1"])
            self.assertNotEqual(self.run_command([binary, "invalid"], success=False).returncode, 0)
            (d / "port.c").write_text(self.pristine)
            result = self.run_command(self.arm_command(d, tickless=2) + ["-c", "port.c", "-o", "bad.o"], cwd=d,
                                      success=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("g_reset_systick", result.stderr)

    def test_timer_callback_uses_real_kernel_configured_depth_and_legacy_parity(self):
        pristine_mdf = self.packs["freertos"]["files"][MDF_KEY]
        outputs = {}
        with tempfile.TemporaryDirectory(dir=self.root) as temp:
            d = Path(temp)
            (d / "bsp_api.h").write_text("#pragma once\n" + (FIX / "model_bsp.hpp").read_text())
            (d / "FreeRTOSConfig.h").write_bytes((FIX / "FreeRTOSConfig.h").read_bytes())
            for version, data in (("old", pristine_mdf), ("new", MDF.read_bytes())):
                tree = ET.fromstring(data)
                callback = next("".join(n.itertext()) for n in tree.findall(".//start")
                                if "void vApplicationGetTimerTaskMemory(" in "".join(n.itertext()))
                callback = function(callback, "vApplicationGetTimerTaskMemory")
                for target in (0, 1):
                    code = ('#include "FreeRTOS.h"\n#include "task.h"\n#include "timers.h"\n'
                            + callback + "\nint main(void) { StaticTask_t *t; StackType_t *s; uint32_t n; "
                            "vApplicationGetTimerTaskMemory(&t, &s, &n); return !(t && s && "
                            + ("n == configTIMER_TASK_STACK_DEPTH" if target else "n == configMINIMAL_STACK_SIZE")
                            + "); }\n")
                    (d / "callback.cpp").write_text(code)
                    cmd = [self.cxx, f"-DTEST_TARGET={target}", "-DTEST_FPU=1", "-DBSP_TZ_NONSECURE_BUILD=0",
                           "-DBSP_CFG_CPU_CORE=0", "-DBSP_CFG_PARAM_CHECKING_ENABLE=0",
                           "-I" + str(d), "-I" + str(FIX), "-I" + str(self.port_headers),
                           "-I" + str(self.kernel / "include")]
                    outputs[version, target] = self.run_command(cmd + ["-E", "-P", d / "callback.cpp"]).stdout
                    self.run_command(cmd + [d / "callback.cpp", "-o", d / "callback"])
                    result = self.run_command([d / "callback"], success=False)
                    self.assertEqual(result.returncode == 0, not (version == "old" and target))
                    self.assertIn("uxTimerTaskStack[ " + ("384" if version == "new" and target else "128"),
                                  outputs[version, target])
            self.assertEqual(outputs["old", 0].split(), outputs["new", 0].split())

    def test_crlf_eof_gate_and_assertion_locations(self):
        for path in (PORT, MDF):
            raw = path.read_bytes()
            self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"), str(path))
        data = PORT.read_bytes()
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))
        self.assertTrue(data.endswith(b'#if BSP_FEATURE_BSP_HAS_SECONDARY_CORE && RM_FREERTOS_PORT_CFG_HW_STACK_MONITOR_ENABLE && !BSP_FEATURE_BSP_HAS_SP_MON\r\n'
                                     b' #error "Renesas SPMON is unavailable; use the CPU stack limit support on this device"\r\n#endif\r\n'))
        self.assertNotIn(b"#line", data)
        assertion_lines = lambda text: [(i, s.strip()) for i, s in enumerate(text.splitlines(), 1)
                                       if re.search(r"\bconfigASSERT\(", s) and not s.lstrip().startswith("*")]
        self.assertEqual(assertion_lines(self.pristine), assertion_lines(self.current))


if __name__ == "__main__":
    unittest.main()
