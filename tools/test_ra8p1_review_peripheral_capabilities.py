"""CAP-001/002/003: primary numeric windows and PDG execution, original FSP parity.

HM Rev1.30 Fig5.4 image p241 (NOT flattened label order), 24.2-24.4
pp1164-1173, 9.2.52 p368, and 43.2 pp2878-2879 are the oracles.
Full production TUs compile against the owning API and device register types.
Host LLVM instrumentation redirects volatile MMIO only; no firmware functions
are extracted/reimplemented. ARM executable/constants/relocations are compared
with original nested FSP HEAD. This is not hardware or live e2 evidence.
"""
import itertools
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest

from tools.ra8p1.regression import readonly_sections

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "baseline"
FSP = BASE / "ra/fsp"
FIX = ROOT / "tools/ra8p1/review_peripheral_capabilities"
HEADERS = {"ra8p1": "R7KA8P1KF.h", "ra8m1": "R7FA8M1AH.h", "ra6t2": "R7FA6T2BD.h",
           "ra6m3": "R7FA6M3AH.h"}
TYPES = ("R_GPT0", "R_GPT_ODC", "R_GPT_GTCLK", "R_SYSTEM", "R_PDG", "R_XSPI0")


def run(command, **kwargs):
    p = subprocess.run(list(map(str, command)), capture_output=True, text=True, timeout=90, **kwargs)
    if p.returncode:
        raise AssertionError(str(command) + "\n" + p.stdout + p.stderr)
    return p.stdout


def stock(path):
    return run(["git", "-C", BASE, "show", "HEAD:" + str(path.relative_to(BASE))])


def prepare(folder, device):
    text = (FSP / "src/bsp/cmsis/Device/RENESAS/Include" / HEADERS[device]).read_text()
    declarations = []
    for name in re.findall(r"\} (R_(?:XSPI0|GPT_ODC)_\w+)_Type;", text):
        end = text.index("} " + name + "_Type;") + len("} " + name + "_Type;")
        declarations.append(text[text.rfind("typedef struct", 0, end):end])
    for name in TYPES:
        closing = "} " + name + "_Type;"
        if closing not in text:
            continue
        end = text.index(closing) + len(closing)
        start = text.rfind("typedef struct", 0, end)
        declarations.append(text[start:end])
        declarations.extend(re.findall(r"^[ \t]*#define " + name + r"_\w+_(?:Msk|Pos)\b[^\n]*", text, re.M))
        # Fixed addresses are observed by the test model, not dereferenced on macOS.
        address = {"R_GPT0": 0x41000000, "R_GPT_ODC": 0x42000000, "R_GPT_GTCLK": 0x43000000,
                   "R_SYSTEM": 0x44000000, "R_PDG": 0x45000000, "R_XSPI0": 0x46000000}[name]
        declarations.append(f"#define {name} (({name}_Type *) 0x{address:x}U)")
    declarations.append("#define R_XSPI1 ((R_XSPI0_Type *) 0x46001000U)")
    declarations.append("#define R_GPT1 ((R_GPT0_Type *) 0x41001000U)")
    (folder / "registers.h").write_text("\n".join(declarations) + "\n")
    (folder / "r_gpt_cfg.h").write_text(
        "#define GPT_CFG_PARAM_CHECKING_ENABLE CHECKS\n#define GPT_CFG_OUTPUT_SUPPORT_ENABLE 2\n"
        "#define GPT_CFG_WRITE_PROTECT_ENABLE PROTECT\n#define GPT_CFG_GPTCLK_BYPASS BYPASS\n")
    (folder / "r_ospi_b_cfg.h").write_text(
        "#define OSPI_B_CFG_PARAM_CHECKING_ENABLE CHECKS\n#define OSPI_B_CFG_AUTOCALIBRATION_SUPPORT_ENABLE 1\n"
        "#define OSPI_B_CFG_XIP_SUPPORT_ENABLE 1\n#define OSPI_B_CFG_DMAC_SUPPORT_ENABLE 0\n"
        "#define OSPI_B_CFG_DOTF_SUPPORT_ENABLE 0\n#define OSPI_B_CFG_COMBINATION_FUNCTION 0\n"
        "#define OSPI_B_CFG_PREFETCH_FUNCTION 1\n")
    return ["-std=c11", "-Wall", "-Wextra", "-Werror=implicit-function-declaration",
            "-Werror=incompatible-pointer-types", "-Wno-pointer-to-int-cast", "-Wno-int-to-pointer-cast",
            "-I" + str(folder), "-I" + str(FIX), "-I" + str(FSP / "src/bsp/mcu" / device),
            "-I" + str(FSP / "inc"), "-I" + str(FSP / "inc/api"), "-I" + str(FSP / "inc/instances"),
            "-include", str(FIX / "bsp_api.h")]


def instrument(ir):
    reads = re.compile(r"^(\s*)(%[\w.]+) = load volatile (i\d+), ptr (.*?), align \d+.*$", re.M)
    writes = re.compile(r"^(\s*)store volatile (i\d+) ([%@\w.-]+), ptr (.*?), align \d+.*$", re.M)
    ir, nr = reads.subn(lambda m: f"{m[1]}{m[2]} = call {m[3]} @review_read{m[3][1:]}(ptr {m[4]})", ir)
    ir, nw = writes.subn(lambda m: f"{m[1]}call void @review_write{m[2][1:]}(ptr {m[4]}, {m[2]} {m[3]})", ir)
    if "load volatile" in ir or "store volatile" in ir or min(nr, nw) < 5:
        raise AssertionError("Incomplete full-production MMIO instrumentation")
    for width in (8, 16, 32, 64):
        ir += f"\ndeclare i{width} @review_read{width}(ptr)\ndeclare void @review_write{width}(ptr, i{width})\n"
    return ir


class PeripheralCapabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("clang")
        cls.arm = os.environ.get("RA8P1_ARM_GCC")
        db = ROOT / "validation/ra8p1/projects/wdt/Debug/compile_commands.json"
        if not cls.arm and db.is_file():
            cls.arm = shlex.split(json.loads(db.read_text())[0]["command"])[0]
        cls.arm = cls.arm or shutil.which("arm-none-eabi-gcc")
        if not cls.cc or not cls.arm:
            raise RuntimeError("Clang and original ARM GNU toolchain required")
        cls.temp = tempfile.TemporaryDirectory(prefix="review-peripheral-capabilities-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.tmp = Path(cls.temp.name)

    def test_primary_presence_values_and_unit_boundaries(self):
        src = self.tmp / "values.c"
        src.write_text('''#include "bsp_feature.h"
#include "bsp_peripheral.h"
_Static_assert(BSP_PERIPHERAL_ECCMB_PRESENT == 1, "two CANFD ECC units exist");
_Static_assert(BSP_PERIPHERAL_ECCMB_CHANNEL_MASK == 3, "ECCMB0 and ECCMB1");
_Static_assert(BSP_FEATURE_OSPI_B_IS_AVAILABLE == 1, "OSPI_B exists");
_Static_assert(BSP_FEATURE_OSPI_B_DEVICE_0_START_ADDRESS == 0x80000000U, "OSPI0 CS0");
_Static_assert(BSP_FEATURE_OSPI_B_DEVICE_1_START_ADDRESS == 0x90000000U, "OSPI0 CS1");
_Static_assert(BSP_FEATURE_GPT_GPTEH_SUPPORTED == 0, "PDG is not GPTEH");
_Static_assert(BSP_FEATURE_GPT_GPTEH_CHANNEL_MASK == 0, "PDG is not GPTEH");
_Static_assert(BSP_PERIPHERAL_GPT_ODC_CHANNEL_MASK == 15, "PDG channels 0..3");
_Static_assert(BSP_FEATURE_OSPI_B_DEVICE_START_ADDRESS(1,0) == 0x70000000U, "NOT SDRAM");
_Static_assert(BSP_FEATURE_OSPI_B_DEVICE_START_ADDRESS(1,1) == 0x78000000U, "OSPI1 CS1");
_Static_assert(BSP_FEATURE_OSPI_B_DEVICE_SIZE(0) == 0x10000000U, "256MiB");
_Static_assert(BSP_FEATURE_OSPI_B_DEVICE_SIZE(1) == 0x08000000U, "128MiB");
''')
        run([self.cc, "-std=c11", "-I" + str(FSP / "src/bsp/mcu/ra8p1"), "-c", src, "-o", self.tmp / "values.o"])

    def test_full_production_runtime_unit_windows_pdg_ordering_and_boundaries(self):
        for checks, protect, bypass in itertools.product((0, 1), repeat=3):
            with self.subTest(checks=checks, protect=protect, bypass=bypass):
                folder = self.tmp / f"runtime-{checks}-{protect}-{bypass}"
                folder.mkdir()
                flags = prepare(folder, "ra8p1") + [f"-DCHECKS={checks}", f"-DPROTECT={protect}", f"-DBYPASS={bypass}"]
                objects = []
                for name in ("r_gpt", "r_ospi_b"):
                    source = FSP / f"src/{name}/{name}.c"
                    ir = run([self.cc, *flags, "-O0", "-S", "-emit-llvm", source, "-o", "-"])
                    path = folder / (name + ".ll")
                    path.write_text(instrument(ir))
                    objects.append(path)
                binary = folder / "fixture"
                run([self.cc, *flags, "-O1", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                     *objects, FIX / "fixture.c", "-o", binary])
                self.assertIn("peripheral capability cases passed", run([binary]))

    def test_pdg001_missing_post_unprotect_readback_fails_runtime_order_oracle(self):
        source = FSP / "src/r_gpt/r_gpt.c"
        current = source.read_text()
        readback = "        p_instance_ctrl->p_reg->GTWP;\n"
        self.assertEqual(current.count(readback), 1)
        for core, checks in itertools.product((0, 1), repeat=2):
            with self.subTest(core=core, checks=checks):
                folder = self.tmp / f"pdg001-before-{core}-{checks}"
                folder.mkdir()
                flags = prepare(folder, "ra8p1") + [f"-DCHECKS={checks}", "-DPROTECT=1", "-DBYPASS=0",
                                                      f"-DBSP_CFG_CPU_CORE={core}"]
                before = folder / "r_gpt.c"
                before.write_text(current.replace(readback, ""))
                objects = []
                for path in (before, FSP / "src/r_ospi_b/r_ospi_b.c"):
                    ir = run([self.cc, *flags, "-O0", "-S", "-emit-llvm", path, "-o", "-"])
                    output = folder / (path.stem + ".ll")
                    output.write_text(instrument(ir))
                    objects.append(output)
                binary = folder / "fixture"
                run([self.cc, *flags, "-O1", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                     *objects, FIX / "fixture.c", "-o", binary])
                result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
                self.assertNotEqual(result.returncode, 0, "Missing PDG readback passed the ordering oracle")
                self.assertIn("PDG delay write preceded GTWP readback", result.stderr)

    def test_old_device_complete_tu_executable_constant_and_relocation_parity(self):
        for device, name, checks, protect in itertools.product(("ra8m1", "ra6t2", "ra6m3"),
                                                               ("r_gpt", "r_ospi_b"), (0, 1), (0, 1)):
            if name == "r_ospi_b" and device != "ra8m1":
                continue
            with self.subTest(device=device, driver=name, checks=checks, protect=protect):
                folder = self.tmp / f"old-{device}-{name}-{checks}-{protect}"
                folder.mkdir()
                flags = prepare(folder, device) + [f"-DCHECKS={checks}", f"-DPROTECT={protect}", "-DBYPASS=1",
                                                   "-mcpu=cortex-m33", "-mthumb", "-O2"]
                source = FSP / f"src/{name}/{name}.c"
                before = folder / (name + ".c")
                before.write_text(stock(source))
                results = []
                for path in (before, source):
                    obj = folder / "driver.o"
                    run([self.arm, *flags, "-c", path, "-o", obj])
                    results.append(readonly_sections(obj.read_bytes()))
                self.assertTrue(results[0])
                self.assertEqual(*results)

    def test_target_complete_tus_compile_both_cores_and_parameter_variants(self):
        for core, checks, protect, bypass in itertools.product((0, 1), repeat=4):
            folder = self.tmp / f"arm-{core}-{checks}-{protect}-{bypass}"
            folder.mkdir()
            flags = prepare(folder, "ra8p1") + [f"-DCHECKS={checks}", f"-DPROTECT={protect}", f"-DBYPASS={bypass}",
                f"-DBSP_CFG_CPU_CORE={core}", "-mcpu=" + ("cortex-m33" if core else "cortex-m85+nopacbti"),
                "-mthumb", "-O2"]
            for name in ("r_gpt", "r_ospi_b"):
                with self.subTest(core=core, checks=checks, protect=protect, bypass=bypass, driver=name):
                    obj = folder / (name + ".o")
                    run([self.arm, *flags, "-c", FSP / f"src/{name}/{name}.c", "-o", obj])
                    self.assertTrue(readonly_sections(obj.read_bytes()))

    def test_all_new_macro_names_have_all_device_parity(self):
        registry = json.loads((ROOT / "tools/ra8p1/capability_extensions.json").read_text())["features"]
        for path in (FSP / "src/bsp/mcu").glob("*/bsp_feature.h"):
            for name in ("BSP_FEATURE_GPT_ODC_REGISTER_TYPE", "BSP_FEATURE_OSPI_B_HAS_UNIT_ADDRESS_MAP",
                         "BSP_FEATURE_OSPI_B_DEVICE_START_ADDRESS(unit,channel)", "BSP_FEATURE_OSPI_B_DEVICE_SIZE(unit)"):
                value = registry[name]["target" if path.parent.name == "ra8p1" else "legacy"]
                if not value.startswith("("):
                    value = "(" + value + ")"
                self.assertRegex(path.read_text(), r"(?m)^#define\s+" + re.escape(name) + r"\s+" + re.escape(value) + r"$")


if __name__ == "__main__":
    unittest.main()
