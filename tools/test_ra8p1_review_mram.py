"""MRAM repair regressions: execute production C; no packs, IDE or target access."""
from pathlib import Path
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
FSP = ROOT / "baseline/ra/fsp"
FIXTURE = ROOT / "tools/ra8p1/review_mram"
DEVICE = FSP / "src/bsp/cmsis/Device/RENESAS/Include"


class ReviewMramTests(unittest.TestCase):
    def native(self, core, checking, nonsecure, scenarios, tcm_helper=False):
        clang = shutil.which("clang")
        self.assertIsNotNone(clang)
        with tempfile.TemporaryDirectory(prefix="review-mram-") as folder:
            folder = Path(folder)
            (folder / "r_mram_cfg.h").write_text(f"#define MRAM_CFG_PARAM_CHECKING_ENABLE {checking}\n")
            exe = folder / "fixture"
            command = [clang, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-Wshadow",
                       "-O1", f"-DBSP_CFG_CPU_CORE={core}", f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}",
                       "-DBSP_TZ_SECURE_BUILD=0", "-I", str(FIXTURE), "-I", str(folder),
                       "-I", str(DEVICE), "-I", str(ROOT / "tools/ra8p1/layout/native"),
                       "-I", str(FSP / "inc"), "-I", str(FSP / "inc/api"), "-I", str(FSP / "inc/instances"),
                       "-I", str(FSP / "src/r_mram"), str(FIXTURE / "fixture.c"), "-o", str(exe)]
            if tcm_helper:
                command += ["-DTEST_TCM_HELPER"]
            if platform.system() == "Darwin":
                base = "0x10000000" if tcm_helper else "0x100000000"
                command += ["-arch", "x86_64", "-Wl,-pagezero_size,0x1000", "-Wl,-no_pie",
                            f"-Wl,-segaddr,__TEXT,{base}"]
            elif tcm_helper:
                command += ["-no-pie", "-Wl,-Ttext-segment=0x10000000"]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for scenario in scenarios:
                with self.subTest(core=core, checking=checking, nonsecure=nonsecure, scenario=scenario,
                                  tcm_helper=tcm_helper):
                    result = subprocess.run([str(exe), scenario], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("review MRAM fixture passed", result.stdout)

    def test_secure_production_matrix(self):
        for core in [0, 1]:
            for checking in [0, 1]:
                self.native(core, checking, 0, ["erase", "tcm", "cache", "startup", "recovery",
                                                "irreversible-rejected"])

    def test_cpu1_cache_failure_stops_before_programming(self):
        for checking in [0, 1]:
            self.native(1, checking, 0, ["cache-refusal"])

    def test_nonsecure_no_register_access(self):
        for core in [0, 1]:
            for checking in [0, 1]:
                self.native(core, checking, 1, ["nonsecure"])

    def test_helper_in_actual_tcm_alias(self):
        for core in [0, 1]:
            for checking in [0, 1]:
                self.native(core, checking, 0, ["tcm", "startup"], tcm_helper=True)

    def test_mdf_safety_defaults_and_standard_api(self):
        mdf = ROOT / "baseline/module_descriptions/Renesas##HAL Drivers##all##r_mram####5.9.0.xml"
        mod = ET.parse(mdf).getroot().find("module")
        for prop in ["write_start", "write_end"]:
            self.assertEqual(mod.find(f"property[@id='module.driver.mram.{prop}']").get("default"), "0")
        self.assertEqual(mod.find("property[@id='module.driver.mram.extra']").get("default"),
                         "module.driver.mram.extra.disabled")
        self.assertIn("never authorizes Forced Stop", mod.find(
            "property[@id='module.driver.mram.timeout']").get("description"))
        for device in ["ra8m1", "ra6t2"]:
            other = ROOT / f"baseline/module_descriptions/Renesas##BSP##{device}##device####5.9.0.xml"
            self.assertNotIn("interface.mcu.mram", [p.get("interface") for p in ET.parse(other).iter("provides")])
        members = re.findall(r"fsp_err_t\s*\(\*\s*(\w+)\)",
                             (FSP / "inc/api/r_flash_api.h").read_text().split("typedef struct st_flash_api", 1)[1])
        self.assertEqual(len(members), 19)
        source = (FSP / "src/r_mram/r_mram.c").read_text()
        self.assertTrue(all(re.search(rf"\.{member}\s*=", source) for member in members))
        self.assertNotIn("0xB3U", source, "No uncalibrated Forced Stop may cancel an irreversible command")

    def test_arm_core_security_checking_and_ram_closure(self):
        recorded = json.loads((ROOT / "validation/stock/Debug/compile_commands.json").read_text())[0]
        arguments = recorded.get("arguments") or shlex.split(recorded["command"])
        gcc = os.environ.get("RA8P1_ARM_CC", arguments[0])
        objdump = str(Path(gcc).with_name("arm-none-eabi-objdump"))
        self.assertTrue(Path(gcc).is_file(), "Recorded ARM GCC or RA8P1_ARM_CC is required")
        cmsis = ROOT / "validation/stock/ra/arm/CMSIS_6/CMSIS/Core/Include"
        self.assertTrue((cmsis / "core_cm85.h").is_file())
        with tempfile.TemporaryDirectory(prefix="review-mram-arm-") as folder:
            folder = Path(folder)
            shutil.copyfile(ROOT / "tools/ra8p1/memory_analog_target_bsp.h", folder / "bsp_api.h")
            (folder / "fixture.ld").write_text('''
ENTRY(R_MRAM_Write)
MEMORY {
 MRAM (rx) : ORIGIN = 0x02000000, LENGTH = 1M
 RAM (rwx) : ORIGIN = 0x22000000, LENGTH = 512K
}
SECTIONS {
 .text : { *(.text*) *(.rodata*) } > MRAM
 .code_in_ram : { *(.code_in_ram*) } > RAM AT > MRAM
 .data : { *(.data*) } > RAM AT > MRAM
 .bss (NOLOAD) : { *(.bss*) *(COMMON) } > RAM
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.eh_frame*) }
}
''')
            for core, cpu in [(0, "cortex-m85"), (1, "cortex-m33")]:
                for checking in [0, 1]:
                    for nonsecure in [0, 1]:
                        for optimization in ["-O0", "-O2", "-Os"]:
                            with self.subTest(core=core, checking=checking, nonsecure=nonsecure,
                                              optimization=optimization):
                                (folder / "r_mram_cfg.h").write_text(
                                    f"#define MRAM_CFG_PARAM_CHECKING_ENABLE {checking}\n")
                                flags = [f"-mcpu={cpu}", "-mthumb", "-mfloat-abi=soft", optimization,
                                         "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-Wshadow",
                                         "-fno-unwind-tables", "-fno-asynchronous-unwind-tables",
                                         f"-DBSP_CFG_CPU_CORE={core}", f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}",
                                         "-DBSP_TZ_SECURE_BUILD=0", "-I", str(folder), "-I", str(DEVICE),
                                         "-isystem", str(cmsis), "-I", str(FSP / "src/bsp/mcu/all"),
                                         "-I", str(FSP / "src/bsp/mcu/ra8p1"), "-I", str(FSP / "inc"),
                                         "-I", str(FSP / "inc/api"), "-I", str(FSP / "inc/instances")]
                                obj = folder / "mram.o"
                                elf = folder / "fixture.elf"
                                for command in [
                                    [gcc, *flags, "-c", str(FSP / "src/r_mram/r_mram.c"), "-o", str(obj)],
                                    [gcc, *flags, "-nostdlib", f"-Wl,-T,{folder / 'fixture.ld'},--emit-relocs",
                                     str(obj), "-lgcc", "-o", str(elf)],
                                ]:
                                    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                                symbols = subprocess.check_output([objdump, "-t", str(elf)], text=True)
                                if not nonsecure:
                                    for helper in ["program", "extra", "read_mode"]:
                                        self.assertRegex(symbols, rf"\.code_in_ram\s+[0-9a-f]+\s+r_mram_{helper}")
                                relocations = subprocess.check_output([objdump, "-r", "-j", ".code_in_ram", str(obj)], text=True)
                                for target in re.findall(r"^\s*[0-9a-f]+\s+R_ARM_\w+\s+(\S+)", relocations, re.MULTILINE):
                                    self.assertRegex(target, r"^(?:\.code_in_ram|r_mram_(?:program|extra|read_mode))(?:\+.*)?$",
                                                     "RAM helper escaped its section: " + relocations)


if __name__ == "__main__":
    unittest.main()
