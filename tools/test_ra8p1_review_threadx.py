"""THREADX-001..004: real 5.9 kernel/CMSIS inputs, ARM execution and legacy object parity.

QEMU is a CPU simulator with modeled LPM MMIO, not RA8P1 hardware evidence.
The original release archive is mandatory; absent dependencies fail, never skip.
"""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import itertools
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from zipfile import ZipFile

from ra8p1.regression import readonly_sections

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tools/ra8p1/review_threadx"
PORT = ROOT / "baseline/ra/fsp/src/rm_threadx_port"
BSP = ROOT / "baseline/ra/fsp/src/bsp/mcu"
PREFIX = "ra/fsp/src/rm_threadx_port/"
KERNEL = "ra/microsoft/azure-rtos/threadx/"
CMSIS = "ra/arm/CMSIS_6/CMSIS/Core/Include/"
ARCHIVE_SHA = "99c4abae6239a68171fcbff86070971f591f0a8945e90a50eb07d87843bee363"
SOURCES = ("tx_thread_schedule.c", "tx_port_wait_thread_ready.c", "tx_initialize_low_level.c",
           "tx_thread_secure_stack_free.c", "tx_thread_stack_build.c")
KERNEL_SOURCES = ("common/src/tx_thread_delete.c", "common/src/tx_initialize_kernel_enter.c")


def checked(command, timeout=60):
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise AssertionError(" ".join(map(str, command)) + "\n" + result.stdout + result.stderr)
    return result.stdout


def release_inputs():
    data = (ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip").read_bytes()
    if sha256(data).hexdigest() != ARCHIVE_SHA:
        raise ValueError("Original FSP 5.9 dependency archive hash mismatch")
    result = {}
    with ZipFile(BytesIO(data)) as release:
        for pack in ("Renesas.RA.5.9.0.pack", "Microsoft.ThreadX.6.4.0+fsp.5.9.0.pack",
                     "Arm.CMSIS6.6.1.0+fsp.5.9.0.pack"):
            prefixes = ((PREFIX, "ra/fsp/src/rm_tz_context/") if pack.startswith("Renesas.") else
                        (KERNEL,) if pack.startswith("Microsoft.") else (CMSIS,))
            with ZipFile(BytesIO(release.read("internal/projectgen/ra/packs/" + pack))) as archive:
                for name in archive.namelist():
                    if name.startswith(prefixes) and not name.endswith("/"):
                        content = archive.read(name)
                        if name in result and result[name] != content:
                            raise ValueError("Ambiguous original source owner: " + name)
                        result[name] = content
    required = [PREFIX + name for name in SOURCES] + [KERNEL + name for name in KERNEL_SOURCES]
    required += [KERNEL + "common/inc/tx_api.h", CMSIS + "core_cm85.h", CMSIS + "core_cm33.h",
                 CMSIS + "tz_context.h", "ra/fsp/src/rm_tz_context/tz_context.c"]
    for name in required:
        if name not in result:
            raise ValueError("Missing original source/kernel owner: " + name)
    return result


class ThreadXReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = os.environ.get("ARM_NONE_EABI_GCC") or shutil.which("arm-none-eabi-gcc")
        cls.qemu = shutil.which("qemu-system-arm")
        if not cls.cc or not cls.qemu:
            raise RuntimeError("ARM GNU compiler and qemu-system-arm are required; coverage may not silently skip")
        probe = subprocess.run([cls.cc, "-E", "-x", "c", "-"], input="#include <stdint.h>\n",
                               capture_output=True, text=True, timeout=15)
        if probe.returncode:
            raise RuntimeError("Compiler lacks libc headers; set ARM_NONE_EABI_GCC to a complete toolchain:\n"
                               + probe.stderr)
        cls.original = release_inputs()
        cls.temp = tempfile.TemporaryDirectory(prefix="review-threadx-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.tree = Path(cls.temp.name)
        for name, data in cls.original.items():
            path = cls.tree / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        cls.includes = cls.tree / "candidate"
        shutil.copytree(PORT, cls.includes)
        (cls.tree / "rm_tz_context_cfg.h").write_text("#define TZ_PROCESS_STACK_SLOTS 2U\n")
        cls.counter = itertools.count()

    def flags(self, *, core=0, ns=0, nsc=0, optional=0, fpu=1, idle=1, no_timer=0,
              tick=-1, case=0, device="ra8p1", spmon=0, offset=0, original=False):
        cpu = "cortex-m85" if core == 0 else "cortex-m33"
        flags = [self.cc, "-std=c11", "-O2", "-g0", "-Wall", "-Wextra", "-Werror",
                 "-ffunction-sections", "-fdata-sections", "-fno-unwind-tables", "-mcpu=" + cpu, "-mthumb",
                 "-mfloat-abi=softfp" if fpu else "-mfloat-abi=soft", "-mfpu=fpv5-sp-d16",
                 f"-DTEST_CORE={core}", f"-DTEST_NS={ns}", f"-DTEST_NSC={nsc}",
                 f"-DTEST_OPTIONAL={optional}", f"-DTEST_MAX_IPL={2 if optional else 0}",
                 f"-DTEST_NO_TIMER={no_timer}", f"-DTEST_TICK_RATE={tick}", f"-DTEST_CASE={case}",
                 f"-DTEST_SPMON={spmon}", f"-DTEST_STACK_OFFSET={offset}", f"-DBSP_CFG_RTOS_IDLE_SLEEP={idle}",
                 "-I" + str(FIX), "-I" + str(self.tree / PREFIX if original else self.includes),
                 "-I" + str(BSP / device),
                 "-I" + str(self.tree / (KERNEL + "common/inc")),
                 "-I" + str(self.tree / CMSIS), "-I" + str(self.tree)]
        return flags

    def compile(self, source, *, original=False, options=None, extra=()):
        options = options or {}
        obj = self.tree / ("object%d.o" % next(self.counter))
        dep = obj.with_suffix(".d")
        command = self.flags(**options, original=original) + list(extra) + ["-MD", "-MF", dep, "-c", source, "-o", obj]
        checked(command)
        dependencies = dep.read_text().replace("\\\n", " ").split(":", 1)[1].split()
        consumed = set()
        for name in dependencies:
            path = Path(name)
            if path.is_relative_to(self.tree):
                relative = path.relative_to(self.tree).as_posix()
                if relative.startswith((KERNEL, CMSIS)):
                    if self.original.get(relative) != path.read_bytes():
                        raise ValueError("Compiler consumed a substituted original kernel/CMSIS owner: " + relative)
                    consumed.add(relative)
            if path.name == "tx_api.h" and path != self.tree / (KERNEL + "common/inc/tx_api.h"):
                raise ValueError("Compiler consumed a shadow kernel header")
        if source.suffix == ".c" and source.name != "tz_context.c":
            self.assertIn(KERNEL + "common/inc/tx_api.h", consumed)
            self.assertIn(CMSIS + ("core_cm85.h" if options.get("core", 0) == 0 else "core_cm33.h"), consumed)
        return obj

    def binary(self, *, before=False, options=None):
        options = options or {}
        objects = []
        for name in SOURCES:
            source = self.tree / (PREFIX + name) if before else self.includes / name
            if not source.is_file():
                raise ValueError("Required real production port source is missing: " + name)
            objects.append(self.compile(source, options=options))
        for name in KERNEL_SOURCES:
            objects.append(self.compile(self.tree / (KERNEL + name), options=options))
        objects.append(self.compile(FIX / "fixture.c", options=options))
        if options.get("nsc"):
            objects.append(self.compile(self.tree / "ra/fsp/src/rm_tz_context/tz_context.c", options=options,
                                        extra=("-include", str(FIX / "context_model.h"))))
        binary = self.tree / ("fixture%d.elf" % next(self.counter))
        checked(self.flags(**options) + objects + ["-nostartfiles", "--specs=nosys.specs", "-T", FIX / "sim.ld",
                                                  "-Wl,--gc-sections", "-o", binary])
        return binary

    def execute(self, binary, success=True):
        result = subprocess.run([self.qemu, "-M", "mps2-an505", "-nographic", "-monitor", "none",
                                 "-serial", "none", "-semihosting-config", "enable=on,target=native",
                                 "-kernel", str(binary)], capture_output=True, text=True, timeout=10)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS", result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("FAIL", result.stdout + result.stderr)
        return result.stdout + result.stderr

    def test_idle_attribution_and_real_allocator_free_both_cores_optional_security(self):
        for core, ns, optional, idle in itertools.product((0, 1), repeat=4):
            with self.subTest(core=core, ns=ns, optional=optional, idle=idle):
                self.execute(self.binary(options=dict(core=core, ns=ns, nsc=1, optional=optional, idle=idle)))

    def test_tick_default_and_boundaries_both_cores(self):
        for core, optional, no_timer in itertools.product((0, 1), repeat=3):
            for case, tick in ((1, -1), (2, 14 if core else 59), (3, 100), (4, 100), (5, 100)):
                with self.subTest(core=core, optional=optional, no_timer=no_timer, case=case, tick=tick):
                    self.execute(self.binary(options=dict(core=core, optional=optional, no_timer=no_timer,
                                                          case=case, tick=tick)))

    def test_zero_tick_rejected_only_when_timer_enabled(self):
        for core in (0, 1):
            with self.subTest(core=core):
                run = subprocess.run(self.flags(core=core, tick=0) + ["-c", str(self.includes / SOURCES[2]),
                                     "-o", str(self.tree / "zero.o")], capture_output=True, text=True)
                self.assertNotEqual(run.returncode, 0)
                self.assertIn("must be greater than zero", run.stderr)
                self.execute(self.binary(options=dict(core=core, tick=0, no_timer=1, case=5)))

    def test_fp_psplim_covers_independent_maximum_context_and_alignment(self):
        for core, fpu, optional, nsc in itertools.product((0, 1), repeat=4):
            with self.subTest(core=core, fpu=fpu, optional=optional, nsc=nsc):
                source = self.includes / SOURCES[0]
                command = self.flags(core=core, fpu=fpu, optional=optional, nsc=nsc)
                text = checked(command + ["-E", "-P", source])
                reservation = int(re.search(r'"ADD     r1,  r1, #"\s*"(\d+)"', text)[1])
                # Arm M85 TRM 4.5: r3 is not SP and is not limited by PSPLIM.
                # Production stores 8 integer registers, 16 FP registers and EXC_RETURN.
                required = 8 * 4 + (16 * 4 + 4 if fpu else 0)
                self.assertEqual(reservation, required)
                # The public API need not supply an 8-byte-aligned stack start. Round the whole limit up.
                self.assertIn('"ADD     r1,  r1, #7', text)
                self.assertIn('"BIC     r1,  r1, #7', text)
                for offset in range(8):
                    stack_start = 0x20000000 + offset
                    effective_limit = (stack_start + reservation + 7) & ~7
                    self.assertGreaterEqual(effective_limit - required, stack_start)
                obj = self.compile(source, options=dict(core=core, fpu=fpu, optional=optional, nsc=nsc))
                self.assertTrue(readonly_sections(obj.read_bytes()))

    def test_actual_pendsv_programs_aligned_limit_with_fp_and_integer_contexts(self):
        for core, fpu, offset in itertools.product((0, 1), (0, 1), range(8)):
            with self.subTest(core=core, fpu=fpu, offset=offset):
                self.execute(self.binary(options=dict(core=core, fpu=fpu, offset=offset, case=7)))

    def test_original_controls_fail_independent_runtime_requirements(self):
        # Unmodified 5.9 C ports reproduce the confirmed defects under the same capabilities.
        self.execute(self.binary(before=True, options=dict(nsc=1)), success=False)
        self.execute(self.binary(before=True, options=dict(case=2, tick=59)), success=False)
        before = checked(self.flags() + ["-E", "-P", self.tree / (PREFIX + SOURCES[0])])
        reservation = int(re.search(r'"ADD     r1,  r1, #"\s*"(\d+)"', before)[1])
        self.assertLess(reservation, 8 * 4 + 16 * 4 + 4)
        # Isolate stale-id failure from idle attribution with the same complete source and allocator.
        self.execute(self.binary(before=True, options=dict(nsc=1, case=6)), success=False)

    def test_legacy_preprocessing_executable_constants_and_relocations_unchanged(self):
        for core, device, ns, optional, nsc, idle, no_timer in itertools.product(
                (0, 1), ("ra8m1", "ra6t2"), (0, 1), (0, 1), (0, 1), (0, 1), (0, 1)):
            options = dict(core=core, device=device, ns=ns, optional=optional, nsc=nsc, idle=idle, no_timer=no_timer)
            with self.subTest(**options):
                for name in SOURCES[:3]:
                    before = self.tree / (PREFIX + name)
                    after = self.includes / name
                    self.assertEqual(checked(self.flags(**options, original=True) + ["-E", "-P", before]).split(),
                                     checked(self.flags(**options) + ["-E", "-P", after]).split())
                    objects = [self.compile(before, options=options, original=True).read_bytes(),
                               self.compile(after, options=options).read_bytes()]
                    self.assertEqual(readonly_sections(objects[0]), readonly_sections(objects[1]))

    def test_required_dependency_owners_are_real_and_spmon_rejection_preserved(self):
        for core in (0, 1):
            run = subprocess.run(self.flags(core=core, spmon=1) + ["-E", str(self.includes / SOURCES[0])],
                                 capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("SPMON is unavailable", run.stderr)
        # Missing and substituted real headers must fail this suite, not fall through to a mock.
        owner = self.tree / (KERNEL + "common/inc/tx_api.h")
        data = owner.read_bytes()
        try:
            owner.write_bytes(data + b"\n/* substitution */\n")
            with self.assertRaisesRegex(ValueError, "substituted"):
                self.compile(self.includes / SOURCES[0])
        finally:
            owner.write_bytes(data)
        self.assertEqual((self.tree / (CMSIS + "tz_context.h")).read_bytes(), self.original[CMSIS + "tz_context.h"])


if __name__ == "__main__":
    unittest.main()
