"""Execute owning production startup/cache functions; no e2, packs or hardware.

Cold/re-enable oracles are HM 2.16.3.3 pp165-166; CPU1 ownership is
HM 2.16.5.2 p191. Callback ordering and legacy parity use stock FSP 5.9.
"""
from pathlib import Path
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
BSP = BASELINE / "ra/fsp/src/bsp"
SYSTEM = BSP / "cmsis/Device/RENESAS/Source/system.c"
COMMON = BSP / "mcu/all/bsp_common.h"
FIXTURE = ROOT / "tools/ra8p1/review_dual_cache/fixture.c"


def function(source, name):
    match = re.search(r"(?m)^[^\n;]*\b" + name + r" \([^;]*?\)\n\{", source)
    if match is None:
        raise AssertionError(f"Missing production function {name}")
    end, depth = match.end(), 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


def run(command):
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise AssertionError(f"{' '.join(map(str, command))}\n{result.stdout}{result.stderr}")
    return result.stdout


class DualCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which("cc")
        if cls.compiler is None:
            raise RuntimeError("A native compiler is required")
        cls.fixture = FIXTURE.read_text()
        cls.current_system = SYSTEM.read_text()
        cls.current_common = COMMON.read_text()
        cls.stock_system, cls.stock_common = [run([
            "git", "-C", BASELINE, "show", "HEAD:" + path.relative_to(BASELINE).as_posix(),
        ]) for path in (SYSTEM, COMMON)]
        cls.legacy_devices = sorted(p.parent.name for p in (BSP / "mcu").glob("*/bsp_feature.h")
                                    if p.parent.name != "ra8p1")

    def source(self, stock=False, system=True):
        cache = self.stock_common if stock else self.current_common
        startup = self.stock_system if stock else self.current_system
        cache_functions = "\n".join(function(cache, name) for name in
                                    ("R_BSP_FlashCacheDisable", "R_BSP_FlashCacheEnable"))
        return self.fixture.replace("/* CACHE FUNCTIONS */", cache_functions).replace(
            "/* SYSTEM FUNCTION */", function(startup, "SystemInit") if system else "")

    def command(self, device, core=0, skip=0, tz_skip=0, system=True):
        return [self.compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                "-Wno-unused-function", "-Wno-unused-variable", "-Wno-pointer-to-int-cast",
                "-D__CLANG_TIDY__", "-DBSP_CFG_XTAL_HZ=24000000", f"-DBSP_CFG_CPU_CORE={core}",
                f"-DBSP_CFG_SKIP_INIT={skip}", f"-DBSP_TZ_CFG_SKIP_INIT={tz_skip}",
                f"-DTEST_SYSTEM={int(system)}", "-I", BSP / "mcu" / device]

    def execute(self, core, mode, skip=0, tz_skip=0):
        with tempfile.TemporaryDirectory(prefix="review-dual-cache-") as temp:
            source, binary = Path(temp) / "fixture.c", Path(temp) / "fixture"
            source.write_text(self.source())
            run(self.command("ra8p1", core, skip, tz_skip) + [
                "-fsanitize=undefined", source, "-o", binary])
            trace, values = run([binary, mode]).strip().split("|")
            return trace, dict((key, int(value)) for key, value in
                               (pair.split("=") for pair in values.split(",")))

    def test_callbacks_run_in_stock_order_on_both_cores(self):
        for core in (0, 1):
            with self.subTest(core=core):
                trace, _ = self.execute(core, "startup")
                # C runtime/constructor and IRQ ordering, independently of cache internals.
                ordered = "AR" + ("G" if core == 0 else "L") + "PZDKU"
                if core == 0:
                    ordered += "VH"
                ordered += "CIB" + ("S" if core == 0 else "")
                self.assertEqual("".join(c for c in trace if c not in "TFWE"), ordered)
                for callback in "RPC":
                    self.assertEqual(trace.count(callback), 1)
                if core == 1:
                    for shared in "GVHS":
                        self.assertNotIn(shared, trace)

    def test_cpu1_cold_start_flushes_and_completes_before_enc(self):
        trace, state = self.execute(1, "startup")
        self.assertEqual("".join(c for c in trace if c in "FWE"), "FWE")
        self.assertLess(trace.index("R"), trace.index("F"))
        self.assertLess(trace.index("E"), trace.index("P"))
        self.assertEqual((state["flush"], state["complete"], state["enable"], state["dirty"]), (1, 1, 1, 0))

    def test_cpu0_never_accesses_cm33_cache_including_skip_init(self):
        for skip, tz_skip in ((0, 0), (1, 0), (0, 1)):
            with self.subTest(skip=skip, tz_skip=tz_skip):
                _, state = self.execute(0, "startup", skip=skip, tz_skip=tz_skip)
                self.assertEqual(state["access"], 0)
                self.assertEqual(state["ctl"], 0)
                self.assertEqual(state["dirty"], 1)
        for mode in ("warm", "disable"):
            with self.subTest(mode=mode):
                _, state = self.execute(0, mode)
                self.assertEqual(state["access"], 0)

    def test_cpu1_generic_reenable_preserves_dirty_lines(self):
        trace, state = self.execute(1, "warm")
        self.assertEqual(trace, "E")
        self.assertEqual((state["flush"], state["complete"], state["dirty"]), (0, 0, 1))
        self.assertEqual(state["ctl"], 1)

    def test_cpu1_reenable_waits_for_existing_flush_and_writeback(self):
        trace, state = self.execute(1, "busy")
        self.assertEqual(trace, "EWE")
        self.assertEqual((state["flush"], state["complete"]), (0, 1))

    def test_cpu1_skip_init_reenable_does_not_flush_dirty_lines(self):
        for skip, tz_skip in ((1, 0), (0, 1)):
            with self.subTest(skip=skip, tz_skip=tz_skip):
                trace, state = self.execute(1, "resume", skip=skip, tz_skip=tz_skip)
                self.assertEqual("".join(c for c in trace if c in "FWE"), "E")
                self.assertEqual(state["dirty"], 1)
                self.assertEqual("".join(c for c in trace if c in "RPC"), "RPC")

    def test_cpu1_disable_completes_required_maintenance(self):
        for mode, control in (("disable", 0x100), ("disable_wb", 0x300)):
            with self.subTest(mode=mode):
                trace, state = self.execute(1, mode)
                self.assertEqual(trace, "EFW")
                self.assertEqual((state["complete"], state["dirty"], state["ctl"]), (1, 0, control))

    def test_all_legacy_cache_executable_and_preprocess_parity(self):
        self.assertEqual(len(self.legacy_devices), 32)
        with tempfile.TemporaryDirectory(prefix="review-cache-legacy-") as temp:
            source, binary = Path(temp) / "fixture.c", Path(temp) / "fixture"
            for device in self.legacy_devices:
                with self.subTest(device=device):
                    results = []
                    for stock in (True, False):
                        source.write_text(self.source(stock=stock, system=False))
                        command = self.command(device, system=False)
                        preprocessed = run(command + ["-E", "-P", source])
                        run(command + ["-O2", "-g0", "-c", source, "-o", binary])
                        object_bytes = binary.read_bytes()
                        run(command + ["-fsanitize=undefined", source, "-o", binary])
                        results.append((preprocessed, object_bytes, run([binary, "warm"]), run([binary, "disable"])))
                    self.assertEqual(*results)

    def test_all_legacy_startup_executable_and_preprocess_parity(self):
        with tempfile.TemporaryDirectory(prefix="review-startup-legacy-") as temp:
            source, binary = Path(temp) / "fixture.c", Path(temp) / "fixture"
            for device in self.legacy_devices:
                for skip in (0, 1):
                    with self.subTest(device=device, skip=skip):
                        results = []
                        for stock in (True, False):
                            source.write_text(self.source(stock=stock))
                            command = self.command(device, skip=skip)
                            tokens = run(command + ["-E", "-P", source])
                            run(command + ["-O2", "-g0", "-c", source, "-o", binary])
                            obj = binary.read_bytes()
                            run(command + ["-fsanitize=undefined", source, "-o", binary])
                            # Legacy cache IPs differ on skip-init maintenance timing;
                            # compare their exact instructions, not the CM33-v2 MMIO oracle.
                            behavior = run([binary, "startup"]) if skip == 0 else None
                            results.append((tokens, obj, behavior))
                        self.assertEqual(*results)

    def mpu_source(self, stock=False):
        with zipfile.ZipFile(ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip") as release:
            with zipfile.ZipFile(io.BytesIO(release.read(
                    "internal/projectgen/ra/packs/Arm.CMSIS6.6.1.0+fsp.5.9.0.pack"))) as pack:
                cmsis = pack.read("ra/arm/CMSIS_6/CMSIS/Core/Include/m-profile/armv8m_mpu.h")
        self.assertEqual(hashlib.sha256(cmsis).hexdigest(),
                         "287fcabda261890f568009423ab2beb163bdcc9af591b4ce9e28f4e465f4e202")
        definitions = []
        for name in ("ARM_MPU_AP_", "ARM_MPU_RBAR", "ARM_MPU_RLAR"):
            lines = cmsis.decode().splitlines()
            index = next(i for i, line in enumerate(lines) if line.startswith("#define " + name + "("))
            definition = [lines[index]]
            while definition[-1].endswith("\\"):
                index += 1
                definition.append(lines[index])
            text = "\n".join(definition)
            if name != "ARM_MPU_AP_":
                text = text.replace(name, "STOCK_" + name, 1)
            definitions.append(text)
        return FIXTURE.with_name("mpu.c").read_text().replace(
            "/* CMSIS ENCODINGS */", "\n".join(definitions)).replace(
            "/* MPU FUNCTION */", function(self.stock_system if stock else self.current_system, "bsp_init_mpu"))

    def test_mpu_rejects_invalid_bounds_before_encoding_on_both_cores(self):
        # Inclusive limits must never be computed for empty, reversed, short or unaligned sections.
        invalid = ((0, 0), (0x22000000, 0x22000000), (0x22000020, 0x22000000),
                   (0, 16), (1, 33), (0xFFFFFFE0, 0))
        valid = ((0, 32), (0x22000000, 0x22000020), (0xFFFFFFC0, 0xFFFFFFE0))
        with tempfile.TemporaryDirectory(prefix="review-mpu-bounds-") as temp:
            source, binary = Path(temp) / "fixture.c", Path(temp) / "fixture"
            source.write_text(self.mpu_source())
            for core in (0, 1):
                for sdram in (0, 1):
                    run(self.command("ra8p1", core, system=False) + [
                        f"-DTEST_SDRAM={sdram}", "-fsanitize=undefined", source, "-o", binary])
                    for start, end in invalid + valid:
                        for slot in range(1 + sdram):
                            with self.subTest(core=core, sdram=sdram, slot=slot, start=hex(start), end=hex(end)):
                                bounds = [0, 0, 0, 0]
                                bounds[slot * 2:slot * 2 + 2] = [start, end]
                                result = run([binary, *map(hex, bounds)]).split()
                                encoded = tuple(map(int, result[:3]))
                                expected = int((start, end) in valid)
                                self.assertEqual(encoded, (expected,) * 3)
                                if expected:
                                    base, limit = (int(value, 16) for value in result[3 + slot * 2:5 + slot * 2])
                                    self.assertEqual(base & 0xFFFFFFE0, start)
                                    self.assertEqual(base & 1, 1, "No-cache region must be XN")
                                    self.assertEqual((limit & 0xFFFFFFE0) | 31, end - 1)

    def test_mpu_all_legacy_preprocess_and_object_parity(self):
        with tempfile.TemporaryDirectory(prefix="review-mpu-legacy-") as temp:
            source, obj = Path(temp) / "fixture.c", Path(temp) / "fixture.o"
            for device in self.legacy_devices:
                for sdram in (0, 1):
                    with self.subTest(device=device, sdram=sdram):
                        results = []
                        for stock in (True, False):
                            source.write_text(self.mpu_source(stock=stock))
                            command = self.command(device, system=False) + [f"-DTEST_SDRAM={sdram}"]
                            tokens = run(command + ["-E", "-P", source])
                            run(command + ["-O2", "-g0", "-c", source, "-o", obj])
                            results.append((tokens, obj.read_bytes()))
                        self.assertEqual(*results)

    def test_arm_full_system_source_with_cpu0_mpu_and_cpu1_code_cache(self):
        compiler = os.environ.get("RA8P1_ARM_CC")
        database = ROOT / "validation/stock/Debug/compile_commands.json"
        if not compiler and database.is_file():
            compiler = shlex.split(json.loads(database.read_text())[0]["command"])[0]
        compiler = compiler or shutil.which("arm-none-eabi-gcc")
        self.assertIsNotNone(compiler, "Complete Arm GCC required")
        with tempfile.TemporaryDirectory(prefix="review-dual-arm-") as temp:
            folder = Path(temp)
            (folder / "bsp_api.h").write_bytes((ROOT / "tools/ra8p1/startup_bsp_api.h").read_bytes())
            with zipfile.ZipFile(ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip") as release:
                with zipfile.ZipFile(io.BytesIO(release.read(
                        "internal/projectgen/ra/packs/Arm.CMSIS6.6.1.0+fsp.5.9.0.pack"))) as pack:
                    prefix = "ra/arm/CMSIS_6/CMSIS/Core/Include/"
                    for name in pack.namelist():
                        if name.startswith(prefix) and not name.endswith("/"):
                            relative = Path(name[len(prefix):])
                            self.assertFalse(relative.is_absolute() or ".." in relative.parts)
                            destination = folder / "cmsis" / relative
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            destination.write_bytes(pack.read(name))
            for core in (0, 1):
                for secure, nonsecure in ((0, 0), (1, 0), (0, 1)):
                    with self.subTest(core=core, secure=secure, nonsecure=nonsecure):
                        cpu, fpu = ("cortex-m85", "fpv5-d16") if core == 0 else ("cortex-m33", "fpv5-sp-d16")
                        run([compiler, "-std=c11", "-ffreestanding", "-Wall", "-Wextra", "-Werror", "-O2",
                             f"-mcpu={cpu}", "-mthumb", f"-mfpu={fpu}", "-mfloat-abi=hard",
                             *(["-mcmse"] if secure else []), f"-DBSP_CFG_DCACHE_ENABLED={int(core == 0)}",
                             f"-DBSP_CFG_CPU_CORE={core}", f"-DBSP_TZ_SECURE_BUILD={secure}",
                             f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}", "-I", folder, "-I", folder / "cmsis",
                             "-I", BSP / "mcu/ra8p1", "-I", BSP / "mcu/all",
                             "-I", BSP / "cmsis/Device/RENESAS/Include", "-c", SYSTEM,
                             "-o", folder / f"system-{core}-{secure}-{nonsecure}.o"])

    def test_source_line_endings_preserved(self):
        for path in (SYSTEM, COMMON):
            raw = path.read_bytes()
            self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"), path)


if __name__ == "__main__":
    unittest.main()
