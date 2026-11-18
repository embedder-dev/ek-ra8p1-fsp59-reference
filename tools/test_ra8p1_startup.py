"""Focused startup checks: production C, manual-derived header, stock 5.9 CMSIS.

These are compile/controlled-register tests, not a generated-project or boot test.
No IDE, newer source, SVD, installed support cache or target is consulted.
"""
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import struct
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BSP = ROOT / "baseline/ra/fsp/src/bsp"
SYSTEM = BSP / "cmsis/Device/RENESAS/Source/system.c"
SECURITY = BSP / "mcu/all/bsp_security.c"
FIXTURES = ROOT / "tools/ra8p1"


def run(command, **kwargs):
    result = subprocess.run([str(x) for x in command], capture_output=True, text=True, timeout=60, **kwargs)
    if result.returncode:
        raise AssertionError(f"{' '.join(map(str, command))}\n{result.stdout}{result.stderr}")
    return result


def function(path, name):
    source = path.read_text()
    start = source.index(name + " (")
    start = source.rfind("\n", 0, start) + 1
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def code_sections(path):
    data = path.read_bytes()
    if data[:6] != b"\x7fELF\x01\x01":
        raise AssertionError("Expected little-endian ELF32 object")
    offset = struct.unpack_from("<I", data, 32)[0]
    size, count, names_index = struct.unpack_from("<HHH", data, 46)
    sections = [struct.unpack_from("<10I", data, offset + n * size) for n in range(count)]
    strings = sections[names_index]
    names = data[strings[4]:strings[4] + strings[5]]
    result = {}
    for section in sections:
        name = names[section[0]:names.find(b"\0", section[0])].decode()
        if name.startswith((".text", ".rodata", ".data")):
            result[name] = data[section[4]:section[4] + section[5]]
    return result


class StartupTests(unittest.TestCase):
    def native(self, fixture, names, defines=()):
        compiler = shutil.which("cc")
        self.assertIsNotNone(compiler, "Native compiler required")
        with tempfile.TemporaryDirectory(prefix="startup-native-") as tmp:
            source, binary = Path(tmp) / "startup.c", Path(tmp) / "startup"
            preamble, checks = (FIXTURES / fixture).read_text().split("/* PRODUCTION */")
            source.write_text(preamble + "\n" + "\n".join(function(SYSTEM, n) for n in names) + checks)
            run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined",
                 *defines, source, "-o", binary])
            run([binary])

    def test_secondary_activation_order_and_already_active(self):
        self.native("startup_secondary.c", ["bsp_start_secondary_core"])

    def test_ctcm_stcm_ecc_initialization_before_checking(self):
        for runtime in (0, 1):
            with self.subTest(runtime=runtime):
                self.native("startup_tcm.c", ["bsp_init_ctcm"], [f"-DBSP_CFG_C_RUNTIME_INIT={runtime}"])

    def test_graphics_power_attribution_transitions_and_idempotence(self):
        for nonsecure in (0, 1):
            with self.subTest(nonsecure=nonsecure):
                self.native("startup_power.c", ["bsp_init_graphics_power_domain"],
                            [f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}"])

    def test_vbatt_layout_and_protection_readbacks(self):
        body = function(SYSTEM, "SystemInit")
        start = body.index("#if BSP_FEATURE_BSP_VBATT_HAS_VBTBPCR1")
        end = body.index("#elif BSP_FEATURE_BSP_VBATT_HAS_VBTCR1_BPWSWSTP", start)
        battery = body[start:end]
        self.assertNotIn("BSP_FEATURE_BSP_HAS_PRCR_S", battery)
        self.assertIn("#if !BSP_TZ_NONSECURE_BUILD", battery)
        operations = [
            "uint16_t prcr = R_SYSTEM->PRCR_S;",
            "R_SYSTEM->PRCR_S = prcr | BSP_PRV_PRCR_PRC1_UNLOCK;",
            "FSP_REGISTER_READ(R_SYSTEM->PRCR_S);",
            "R_SYSTEM->VBTBPCR1 = R_SYSTEM_VBTBPCR1_BPWSWSTP_Msk;",
            "R_SYSTEM->VBTBPCR2_b.VDETE = 0U;",
            "R_SYSTEM->PRCR_S = BSP_PRV_PRCR_KEY | prcr;",
            "FSP_REGISTER_READ(R_SYSTEM->PRCR_S);",
        ]
        offset = 0
        for operation in operations:
            offset = battery.index(operation, offset) + len(operation)

    def test_arm_full_sources_cpu0_dependencies_before_cpu1(self):
        compiler = os.environ.get("RA8P1_ARM_CC")
        database = ROOT / "validation/stock/Debug/compile_commands.json"
        if not compiler and database.is_file():
            compiler = shlex.split(json.loads(database.read_text())[0]["command"])[0]
        compiler = compiler or shutil.which("arm-none-eabi-gcc")
        self.assertIsNotNone(compiler, "Complete Arm GCC required (or set RA8P1_ARM_CC)")
        nm = run([compiler, "-print-prog-name=nm"]).stdout.strip()
        archive = ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip"
        self.assertTrue(archive.is_file(), "Original 5.9 CMSIS release archive required")
        with tempfile.TemporaryDirectory(prefix="startup-arm-") as tmp:
            folder = Path(tmp)
            (folder / "bsp_api.h").write_bytes((FIXTURES / "startup_bsp_api.h").read_bytes())
            prefix = "ra/arm/CMSIS_6/CMSIS/Core/Include/"
            with zipfile.ZipFile(archive) as release:
                pack_name = "internal/projectgen/ra/packs/Arm.CMSIS6.6.1.0+fsp.5.9.0.pack"
                with zipfile.ZipFile(io.BytesIO(release.read(pack_name))) as pack:
                    for name in pack.namelist():
                        if name.startswith(prefix) and not name.endswith("/"):
                            relative = Path(name[len(prefix):])
                            self.assertFalse(relative.is_absolute() or ".." in relative.parts)
                            target = folder / "cmsis" / relative
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_bytes(pack.read(name))
            for core in (0, 1):
                for secure, nonsecure in ((0, 0), (1, 0), (0, 1)):
                    for source in (SYSTEM, SECURITY):
                        with self.subTest(core=core, secure=secure, nonsecure=nonsecure, source=source.name):
                            cpu, fpu = ("cortex-m85", "fpv5-d16") if core == 0 else ("cortex-m33", "fpv5-sp-d16")
                            run([compiler, "-std=c11", "-ffreestanding", "-Wall", "-Wextra", "-Werror", "-O2",
                                 f"-mcpu={cpu}", "-mthumb", f"-mfpu={fpu}", "-mfloat-abi=hard",
                                 *(["-mcmse"] if secure else []),
                                 f"-DBSP_CFG_CPU_CORE={core}", f"-DBSP_TZ_SECURE_BUILD={secure}",
                                 f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}",
                                 "-I", folder, "-I", folder / "cmsis", "-I", BSP / "mcu/ra8p1", "-I", BSP / "mcu/all",
                                 "-I", BSP / "cmsis/Device/RENESAS/Include", "-c", source,
                                  "-o", folder / f"{source.stem}-{core}-{secure}-{nonsecure}.o"])
                            if source == SYSTEM:
                                undefined = run([nm, "-u", folder / f"{source.stem}-{core}-{secure}-{nonsecure}.o"]).stdout
                                self.assertNotIn("bsp_internal_prv_enable_extra_power_domain", undefined)
                                self.assertNotIn("bsp_init_graphics_power_domain", undefined)

    def test_legacy_ra8m1_executable_sections_unchanged(self):

        database = ROOT / "validation/stock/Debug/compile_commands.json"
        if not database.is_file():
            self.skipTest("Pristine generated RA8M1 control unavailable")
        entries = json.loads(database.read_text())
        with tempfile.TemporaryDirectory(prefix="startup-stock-") as tmp:
            for production in (SYSTEM, SECURITY):
                with self.subTest(source=production.name):
                    entry = next(e for e in entries if Path(e["file"]).name == production.name)
                    command = shlex.split(entry["command"])
                    if not Path(command[0]).is_file():
                        self.skipTest("Recorded stock compiler unavailable")
                    original = run(["git", "show", f"HEAD:{production.relative_to(ROOT / 'baseline')}"],
                                   cwd=ROOT / "baseline").stdout
                    stock = Path(tmp) / production.name
                    stock.write_text(original)
                    objects = []
                    for index, source in enumerate((stock, production)):
                        args = command.copy()
                        obj = Path(tmp) / f"{production.stem}-{index}.o"
                        args[args.index("-o") + 1] = str(obj)
                        args[args.index("-x") + 2] = str(source)
                        run(args, cwd=entry["directory"])
                        objects.append(code_sections(obj))
                    if production == SYSTEM:
                        self.assertTrue(any(name.startswith(".text.") for name in objects[0]))
                    self.assertEqual(*objects)

    def test_ownership_and_no_source_churn(self):
        for path in (SYSTEM, SECURITY):
            raw = path.read_bytes()
            self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"), path)
            self.assertNotIn("BSP_MCU_GROUP_RA8P1", raw.decode())
        body = function(SYSTEM, "SystemInit")
        self.assertLess(body.index("bsp_init_ctcm();"), body.index("bsp_init_uninitialized_vars();"))
        self.assertLess(body.index("bsp_init(NULL);"), body.index("bsp_start_secondary_core();"))
        # Compile the CPU1 preprocessor path: shared initialization must not appear.
        compiler = shutil.which("cc")
        with tempfile.TemporaryDirectory(prefix="startup-preprocess-") as tmp:
            folder = Path(tmp)
            (folder / "bsp_api.h").write_text("\n".join([
                "#define BSP_FEATURE_BSP_HAS_SECONDARY_CORE 1", "#define BSP_CFG_CPU_CORE 1",
                "#define BSP_FEATURE_BSP_HAS_CTCM 1", "#define BSP_CFG_C_RUNTIME_INIT 1"]))
            result = run([compiler, "-E", "-P", "-D__CLANG_TIDY__", "-I", folder, SYSTEM]).stdout
            for call in ("bsp_clock_init();", "R_BSP_Init_RTC();",
                         "R_PSCU->PSARB =", "R_PMISC->PMSAR[", "bsp_start_secondary_core();",
                         "bsp_init_graphics_power_domain", "bsp_internal_prv_enable_extra_power_domain"):
                self.assertNotIn(call, result)
            for call in ("bsp_clock_freq_var_init();", "bsp_init_ctcm();", "bsp_irq_cfg();", "bsp_init("):
                self.assertIn(call, result)
            # CPU-local user hooks remain reachable; only default shared setup is CPU0-owned.
            callback_positions = []
            for event in ("RESET", "POST_CLOCK", "POST_C"):
                call = f"R_BSP_WarmStart(BSP_WARM_START_{event});"
                self.assertEqual(1, result.count(call))
                callback_positions.append(result.index(call))
            self.assertEqual(sorted(callback_positions), callback_positions)
            result = run([compiler, "-E", "-P", "-DBSP_FEATURE_TZ_HAS_TRUSTZONE=1",
                          "-DBSP_TZ_SECURE_BUILD=1", "-D__SAUREGION_PRESENT=1", "-I", folder, SECURITY]).stdout
            for register in ("R_CPSCU->", "R_PSCU->", "R_SYSTEM->", "R_MRAM->", "R_BUS->",
                             "R_TZF->", "R_DMA->", "R_DTC->"):
                self.assertNotIn(register, result)
            for operation in ("SAU->RBAR =", "SAU->CTRL = SAU_CTRL_ENABLE_Msk;", "__DSB();", "__ISB();"):
                self.assertIn(operation, result)
            self.assertNotIn("SCB_InvalidateICache();", result)


if __name__ == "__main__":
    unittest.main()
