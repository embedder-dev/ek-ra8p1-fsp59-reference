"""Production-C register fixtures. Host RAM only: no hardware or IDE operations."""
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
FIXTURE = ROOT / "tools/ra8p1"
FSP = ROOT / "baseline/ra/fsp"
MDF = ROOT / "baseline/module_descriptions"
DEVICE = FSP / "src/bsp/cmsis/Device/RENESAS/Include"


def render_validation_spec(driver):
    spec = json.loads((ROOT / f"validation/ra8p1/specs/{driver}.json").read_text())
    assert set(spec) == {"modules", "bsp"} and spec["bsp"] == {}
    mod = ET.parse(MDF / f"Renesas##HAL Drivers##all##r_{driver}####5.9.0.xml").getroot().find("module")
    properties = {p.get("id"): p for p in mod.findall("property")}
    header = mod.findtext("includes") + "\n"
    declarations = '#include "hal_data.h"\n#define FSP_INVALID_VECTOR (-1)\n#define BSP_IRQ_DISABLED 0xFFU\n'
    names = []
    for instance in spec["modules"]:
        assert set(instance) == {"id", "name", "properties"} and instance["id"] == "r_" + driver
        names.append(instance["name"])
        overrides = dict(instance["properties"])
        overrides[f"module.driver.{driver}.name"] = instance["name"]
        assert set(overrides) <= set(properties), set(overrides) - set(properties)
        values = {"_instance": "0", "_disabled": "0"}
        for key, prop in properties.items():
            value = overrides.get(key, prop.get("default"))
            options = {option.get("id"): option.get("value") for option in prop.findall("option")}
            if options:
                assert value in options, (key, value)
                value = options[value]
            values[key] = values.get(value, value).replace("${_instance}", "0")
        substitute = lambda text: re.sub(r"\$\{([^}]+)\}", lambda m: values[m[1]], text)
        header += substitute(mod.findtext("header"))
        declarations += substitute(mod.findtext("declarations"))
    assert len(names) == len(set(names))
    return header, declarations, spec


def render_default_instance(driver):
    mod = ET.parse(MDF / f"Renesas##HAL Drivers##all##r_{driver}####5.9.0.xml").getroot().find("module")
    values = {"_instance": "0", "_disabled": "0"}
    for prop in mod.findall("property"):
        default = prop.get("default")
        option = next((x for x in prop.findall("option") if x.get("id") == default), None)
        value = option.get("value") if option is not None else values.get(default, default)
        values[prop.get("id")] = value.replace("${_instance}", "0")
    source = mod.findtext("header") + mod.findtext("declarations")
    return re.sub(r"\$\{([^}]+)\}", lambda m: values[m[1]], source)


class MemoryAnalogTests(unittest.TestCase):
    def run_c(self, checking, nonsecure, self_modify=False, real_header=False, scenario=None, secure=0, defaults=False):
        clang = shutil.which("clang")
        self.assertIsNotNone(clang, "clang is required for the production-C fixture")
        with tempfile.TemporaryDirectory(prefix="memory-analog-") as temp:
            temp = Path(temp)
            shutil.copyfile(FIXTURE / "memory_analog_bsp.h", temp / "bsp_api.h")
            for driver in ["mram", "dac_b"]:
                (temp / f"r_{driver}_cfg.h").write_text(
                    f"#define {driver.upper()}_CFG_PARAM_CHECKING_ENABLE {checking}\n")
            exe = temp / "fixture"
            fixture_name = "memory_analog_self_modify.c" if self_modify else "memory_analog_fixture.c"
            command = [clang, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-Wshadow",
                       "-O1", "-g", "-DTEST_DAC_B", f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}",
                       f"-DBSP_TZ_SECURE_BUILD={secure}", "-I", str(temp),
                       "-I", str(FSP / "inc"), "-I", str(FSP / "inc/api"), "-I", str(FSP / "inc/instances"),
                       str(FIXTURE / fixture_name), str(FSP / "src/r_mram/r_mram.c"),
                       "-o", str(exe)]
            if defaults:
                (temp / "defaults.c").write_text(
                    '#include "r_mram.h"\n#include "r_dac_b.h"\n'
                    '#define FSP_INVALID_VECTOR (-1)\n#define BSP_IRQ_DISABLED 0xFFU\n' +
                    render_default_instance("mram") + render_default_instance("dac_b"))
                command += ["-DTEST_MEMORY_ANALOG_DEFAULTS", str(temp / "defaults.c")]
            if real_header:
                command += ["-DMEMORY_ANALOG_REAL_HEADER=1", "-DBSP_CFG_CPU_CORE=0", "-I", str(DEVICE),
                            "-I", str(FIXTURE / "layout/native")]
            if not self_modify:
                command += [str(FSP / "src/r_dac_b/r_dac_b.c")]
            image_base = "0x02000000" if self_modify else "0x100000000"
            if platform.system() == "Darwin":
                # flash_api_t has 32-bit addresses. A native arm64 macOS executable
                # reserves the first 4GB; x86_64 with a small page-zero permits
                # ordinary low-address anonymous host mappings (Rosetta on arm64).
                command += ["-arch", "x86_64", "-Wl,-pagezero_size,0x1000", "-Wl,-no_pie",
                            f"-Wl,-segaddr,__TEXT,{image_base}"]
            elif self_modify:
                command += ["-no-pie", "-Wl,-Ttext-segment=0x02000000"]
            built = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            ran = subprocess.run([str(exe)] + ([scenario] if scenario else []),
                                 capture_output=True, text=True, timeout=30)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
            if scenario:
                self.assertIn("production zeroization safety passed", ran.stdout)
            elif self_modify:
                self.assertIn("production self-modifying safety gate passed", ran.stdout)
            else:
                self.assertIn("production MRAM fixture passed", ran.stdout)
                self.assertIn("production DAC_B fixture passed", ran.stdout)

    def test_self_modifying_helper_rejected_before_register_access(self):
        self.run_c(1, 0, self_modify=True)

    def test_production_checking_enabled_secure(self):
        self.run_c(1, 0)

    def test_production_checking_disabled_secure(self):
        self.run_c(0, 0)

    def test_production_checking_enabled_nonsecure(self):
        self.run_c(1, 1)

    def test_production_checking_disabled_nonsecure(self):
        self.run_c(0, 1)

    def test_default_mdf_lifecycle(self):
        for checking in [0, 1]:
            for nonsecure in [0, 1]:
                with self.subTest(checking=checking, nonsecure=nonsecure):
                    self.run_c(checking, nonsecure, real_header=True, defaults=True)

    def test_mram_secure_callback_memory(self):
        for checking in [0, 1]:
            for real_header in [False, True]:
                with self.subTest(checking=checking, real_header=real_header):
                    self.run_c(checking, 0, real_header=real_header, secure=1)

    def test_mram_zeroization_active(self):
        for scenario in ["zeroization-status", "zeroization-admission"]:
            for checking in [0, 1]:
                for nonsecure in [0, 1]:
                    for real_header in [False, True]:
                        with self.subTest(scenario=scenario, checking=checking, nonsecure=nonsecure,
                                          real_header=real_header):
                            self.run_c(checking, nonsecure, real_header=real_header, scenario=scenario)

    def test_mram_zeroization_interrupted(self):
        for scenario in ["zeroization-interrupted", "zeroization-completed-between-polls"]:
            for checking in [0, 1]:
                for nonsecure in [0, 1]:
                    for real_header in [False, True]:
                        with self.subTest(scenario=scenario, checking=checking, nonsecure=nonsecure,
                                          real_header=real_header):
                            self.run_c(checking, nonsecure, real_header=real_header, scenario=scenario)

    def test_mram_zeroization_extra_commands(self):
        for scenario in ["zeroization-extra-active", "zeroization-extra-completed"]:
            for checking in [0, 1]:
                for real_header in [False, True]:
                    with self.subTest(scenario=scenario, checking=checking, real_header=real_header):
                        self.run_c(checking, 0, real_header=real_header, scenario=scenario)

    def test_production_real_generated_header(self):
        for checking in [0, 1]:
            for nonsecure in [0, 1]:
                with self.subTest(checking=checking, nonsecure=nonsecure):
                    self.run_c(checking, nonsecure, real_header=True)
        self.run_c(1, 0, self_modify=True, real_header=True)

    def test_validation_specs_render_and_compile_applications(self):
        clang = shutil.which("clang")
        with tempfile.TemporaryDirectory(prefix="memory-analog-spec-") as temp:
            temp = Path(temp)
            shutil.copyfile(FIXTURE / "memory_analog_bsp.h", temp / "bsp_api.h")
            for driver in ["mram", "dac_b"]:
                header, declarations, spec = render_validation_spec(driver)
                if driver == "mram":
                    self.assertEqual(spec["modules"][0]["name"], "g_mram0")
                    self.assertIn(".write_window_start = 0,", declarations)
                    self.assertIn(".write_window_end = 0,", declarations)
                    self.assertIn(".enable_extra_commands = false,", declarations)
                else:
                    self.assertEqual([m["name"] for m in spec["modules"]], ["g_dac_b0", "g_dac_b1"])
                    for channel in [0, 1]:
                        self.assertIn(f".channel = {channel},", declarations)
                (temp / "hal_data.h").write_text(header)
                (temp / f"r_{driver}_cfg.h").write_text(f"#define {driver.upper()}_CFG_PARAM_CHECKING_ENABLE 1\n")
                command = [clang, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-Wshadow",
                           "-DMEMORY_ANALOG_REAL_HEADER=1", "-DBSP_CFG_CPU_CORE=0", "-DBSP_TZ_NONSECURE_BUILD=0",
                           "-I", str(temp), "-I", str(DEVICE), "-I", str(FIXTURE / "layout/native"),
                           "-I", str(FSP / "inc"), "-I", str(FSP / "inc/api"), "-I", str(FSP / "inc/instances"),
                           "-x", "c", "-fsyntax-only", "-"]
                for label, source in [("declarations", declarations),
                                      ("application", (ROOT / f"validation/ra8p1/apps/{driver}.c").read_text())]:
                    with self.subTest(driver=driver, source=label):
                        result = subprocess.run(command, input=source, text=True, capture_output=True, timeout=30)
                        self.assertEqual(result.returncode, 0, result.stderr)

    def test_arm_real_header_ram_helper_closure(self):
        recorded = json.loads((ROOT / "validation/stock/Debug/compile_commands.json").read_text())[0]
        arguments = recorded.get("arguments") or shlex.split(recorded["command"])
        gcc = os.environ.get("RA8P1_ARM_CC", arguments[0])
        objdump = str(Path(gcc).with_name("arm-none-eabi-objdump"))
        self.assertTrue(Path(gcc).is_file(), "Recorded complete ARM GCC is required (or RA8P1_ARM_CC)")
        self.assertTrue(Path(objdump).is_file(), "Matching ARM objdump is required")
        cmsis = ROOT / "validation/stock/ra/arm/CMSIS_6/CMSIS/Core/Include"
        self.assertTrue((cmsis / "core_cm85.h").is_file(), "Preserved stock CMSIS headers are required")
        with tempfile.TemporaryDirectory(prefix="memory-analog-arm-") as temp:
            temp = Path(temp)
            shutil.copyfile(FIXTURE / "memory_analog_target_bsp.h", temp / "bsp_api.h")
            (temp / "support.c").write_text(
                '#include "bsp_api.h"\n'
                'void fixture_module_start(uint8_t unit) { (void)unit; }\n'
                'void fixture_module_stop(uint8_t unit) { (void)unit; }\n'
                'void R_BSP_SoftwareDelay(uint32_t count, int units) { (void)count; (void)units; }\n')
            (temp / "fixture.ld").write_text('''
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
                                for driver in ["mram", "dac_b"]:
                                    (temp / f"r_{driver}_cfg.h").write_text(
                                        f"#define {driver.upper()}_CFG_PARAM_CHECKING_ENABLE {checking}\n")
                                flags = [f"-mcpu={cpu}", "-mthumb", "-mfloat-abi=soft", optimization,
                                         "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-Wshadow",
                                         "-fno-unwind-tables", "-fno-asynchronous-unwind-tables",
                                         f"-DBSP_CFG_CPU_CORE={core}", f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}",
                                         "-I", str(temp), "-I", str(DEVICE), "-isystem", str(cmsis),
                                         "-I", str(FSP / "src/bsp/mcu/all"), "-I", str(FSP / "src/bsp/mcu/ra8p1"),
                                         "-I", str(FSP / "inc"), "-I", str(FSP / "inc/api"),
                                         "-I", str(FSP / "inc/instances")]
                                objects = []
                                for name, source in [
                                    ("mram", FSP / "src/r_mram/r_mram.c"),
                                    ("dac_b", FSP / "src/r_dac_b/r_dac_b.c"),
                                    ("support", temp / "support.c"),
                                ]:
                                    obj = temp / f"{name}.o"
                                    result = subprocess.run([gcc, *flags, "-c", str(source), "-o", str(obj)],
                                                            capture_output=True, text=True, timeout=30)
                                    self.assertEqual(result.returncode, 0, result.stderr)
                                    objects.append(str(obj))
                                for driver in ["mram", "dac_b"]:
                                    folder = temp / driver
                                    folder.mkdir(exist_ok=True)
                                    header, declarations, _ = render_validation_spec(driver)
                                    (folder / "hal_data.h").write_text(header)
                                    (folder / "hal_data.c").write_text(declarations)
                                    for source in [folder / "hal_data.c", ROOT / f"validation/ra8p1/apps/{driver}.c"]:
                                        result = subprocess.run(
                                            [gcc, *flags, "-I", str(folder), "-c", str(source),
                                             "-o", str(folder / "application.o")],
                                            capture_output=True, text=True, timeout=30)
                                        self.assertEqual(result.returncode, 0, result.stderr)
                                elf = temp / "fixture.elf"
                                result = subprocess.run(
                                    [gcc, *flags, "-nostdlib", f"-Wl,-T,{temp / 'fixture.ld'},--emit-relocs",
                                     *objects, "-lgcc", "-o", str(elf)], capture_output=True, text=True, timeout=30)
                                self.assertEqual(result.returncode, 0, result.stderr)
                                sections = subprocess.check_output([objdump, "-h", str(elf)], text=True)
                                match = re.search(r"\s\d+\s+\.code_in_ram\s+([0-9a-f]+)\s+([0-9a-f]+)\s+([0-9a-f]+)",
                                                  sections)
                                self.assertIsNotNone(match, sections)
                                size, vma, lma = [int(value, 16) for value in match.groups()]
                                self.assertEqual(vma, 0x22000000)
                                self.assertGreater(size, 0)
                                self.assertTrue(0x02000000 <= lma < 0x02100000)
                                symbols = subprocess.check_output([objdump, "-t", str(elf)], text=True)
                                self.assertRegex(symbols, r"\.code_in_ram\s+[0-9a-f]+\s+r_mram_program")
                                if not nonsecure:
                                    self.assertRegex(symbols, r"\.code_in_ram\s+[0-9a-f]+\s+r_mram_extra")
                                relocations = subprocess.check_output(
                                    [objdump, "-r", "-j", ".code_in_ram", str(temp / "mram.o")], text=True)
                                for target in re.findall(r"^\s*[0-9a-f]+\s+R_ARM_\w+\s+(\S+)",
                                                         relocations, re.MULTILINE):
                                    self.assertRegex(target, r"^(?:\.code_in_ram|r_mram_program|r_mram_extra|r_mram_read_mode)(?:\+.*)?$",
                                                     "RAM helper references an out-of-section symbol: " + relocations)
                                assembly = subprocess.check_output(
                                    [objdump, "-d", "-j", ".code_in_ram", str(elf)], text=True)
                                self.assertNotRegex(assembly, r"\bblx?\s+r\d+\b")
                                for address in re.findall(r"\b(?:blx?|b\.w)\s+([0-9a-f]+)\s+<", assembly):
                                    self.assertTrue(vma <= int(address, 16) < vma + size, assembly)

    def test_dac_b_mdf_device_gate_and_api(self):
        mod = ET.parse(MDF / "Renesas##HAL Drivers##all##r_dac_b####5.9.0.xml").getroot().find("module")
        self.assertIn("interface.mcu.dac_b", [x.get("interface") for x in mod.findall("requires")])
        self.assertEqual(mod.get("id"), "module.driver.dac_on_dac_b")
        self.assertIn('component="dac12${module.driver.dac_b.channel}"', ET.tostring(mod, encoding="unicode"))
        self.assertIn(".ad_da_synchronized = false", mod.findtext("declarations"))
        self.assertIsNotNone(mod.find("guard/template"))
        self.assertIsNotNone(mod.find("nsc/declarations"))

    def test_dac_b_unique_unit_contract(self):
        mod = ET.parse(MDF / "Renesas##HAL Drivers##all##r_dac_b####5.9.0.xml").getroot().find("module")
        unique = mod.find("constraint[@display='Only one control block may own each DAC_B unit']")
        self.assertIsNotNone(unique)
        self.assertEqual(unique.text.strip(),
                         '"${interface.driver.dac_on_dac_b.${module.driver.dac_b.channel}}" === "1"')
        interface = "interface.driver.dac_on_dac_b.${module.driver.dac_b.channel}"
        self.assertIn(interface, [p.get("interface") for p in mod.findall("provides")])
        header = (FSP / "inc/instances/r_dac_b.h").read_text()
        self.assertIn("one control block per unit", header)
        for channels, expected in [([0], True), ([1], True), ([0, 1], True),
                                   ([0, 0], False), ([1, 1], False), ([0, 1, 0], False)]:
            with self.subTest(channels=channels):
                provided = [interface.replace("${module.driver.dac_b.channel}", str(c)) for c in channels]
                self.assertEqual(all(provided.count(key) == 1 for key in provided), expected)

    def test_dac_b_channel_interfaces_positive_and_negative(self):
        mod = ET.parse(MDF / "Renesas##HAL Drivers##all##r_dac_b####5.9.0.xml").getroot().find("module")
        constraint = mod.find("constraint[@display='Channel not available on selected MCU']").text.strip()
        self.assertEqual(constraint, 'testExists("${interface.mcu.dac12.${module.driver.dac_b.channel}}")')
        channel_interface = re.fullmatch(r'testExists\("\$\{(.+)\}"\)', constraint).group(1)
        prerequisite = mod.find("requires[@id='module.driver.dac_on_dac_b.requires.mcu']")
        self.assertEqual(prerequisite.get("interface"), "interface.mcu.dac_b")
        self.assertEqual(prerequisite.get("visible"), "false")
        target = {p.get("interface") for p in ET.parse(
            MDF / "Renesas##BSP##ra8p1##device####5.9.0.xml").iter("provides")}
        sibling = {p.get("interface") for p in ET.parse(
            MDF / "Renesas##BSP##ra8m1##device####5.9.0.xml").iter("provides")}
        cases = [
            ("target channel 0", target, 0, True),
            ("target channel 1", target, 1, True),
            ("absent channel 2", target, 2, False),
            ("missing channel 0", target - {"interface.mcu.dac12.0"}, 0, False),
            ("missing channel 1", target - {"interface.mcu.dac12.1"}, 1, False),
            ("missing DAC_B prerequisite", target - {"interface.mcu.dac_b"}, 0, False),
            ("older device channel 0", sibling, 0, False),
            ("older device channel 1", sibling, 1, False),
        ]
        for label, interfaces, channel, expected in cases:
            with self.subTest(case=label):
                selected = channel_interface.replace("${module.driver.dac_b.channel}", str(channel))
                self.assertEqual(selected in interfaces and prerequisite.get("interface") in interfaces, expected)

    def test_default_mdf_instances_compile_against_public_headers(self):
        clang = shutil.which("clang")
        with tempfile.TemporaryDirectory(prefix="memory-analog-mdf-") as temp:
            temp = Path(temp)
            shutil.copyfile(FIXTURE / "memory_analog_bsp.h", temp / "bsp_api.h")
            for driver in ["mram", "dac_b"]:
                root = ET.parse(MDF / f"Renesas##HAL Drivers##all##r_{driver}####5.9.0.xml").getroot()
                mod = root.find("module")
                values = {"_instance": "0", "_disabled": "0"}
                for prop in mod.findall("property"):
                    default = prop.get("default")
                    option = next((x for x in prop.findall("option") if x.get("id") == default), None)
                    value = option.get("value") if option is not None else values.get(default, default)
                    values[prop.get("id")] = value.replace("${_instance}", "0")
                declarations = mod.findtext("header") + mod.findtext("declarations")
                declarations = re.sub(r"\$\{([^}]+)\}", lambda m: values[m[1]], declarations)
                (temp / f"r_{driver}_cfg.h").write_text(f"#define {driver.upper()}_CFG_PARAM_CHECKING_ENABLE 1\n")
                source = (f'#include "r_{driver}.h"\n#define FSP_INVALID_VECTOR (-1)\n'
                          '#define BSP_IRQ_DISABLED 0xFFU\n' + declarations)
                command = [clang, "-std=c11", "-Werror", "-Wall", "-Wextra", "-Wconversion", "-fsyntax-only",
                           "-x", "c", "-I", str(temp), "-I", str(FSP / "inc"), "-I", str(FSP / "inc/api"),
                           "-I", str(FSP / "inc/instances"), "-"]
                result = subprocess.run(command, input=source, text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                substitute = lambda text: re.sub(r"\$\{([^}]+)\}", lambda m: values[m[1]], text)
                (temp / "guard.h").write_text(
                    f'#include "r_{driver}.h"\n' + substitute(mod.findtext("header")) +
                    '#define BSP_CMSE_NONSECURE_ENTRY\n'
                    '#define CMSE_AU_NONSECURE 1\n#define CMSE_NONSECURE 1\n#define CMSE_MPU_READ 2\n'
                    '#define cmse_check_pointed_object(pointer, flags) (pointer)\n'
                    '#define cmse_check_address_range(pointer, size, flags) (pointer)\n')
                for section, source in [
                    ("guard", substitute(mod.findtext("guard/template"))),
                    ("nsc", '#include "guard.h"\n' + substitute(
                        mod.findtext("nsc/header") + mod.findtext("nsc/declarations"))),
                ]:
                    with self.subTest(driver=driver, section=section):
                        result = subprocess.run(command, input=source, text=True, capture_output=True, timeout=30)
                        self.assertEqual(result.returncode, 0, result.stderr)

    def test_mram_mdf_guards_and_device_gate(self):
        root = ET.parse(MDF / "Renesas##HAL Drivers##all##r_mram####5.9.0.xml").getroot()
        mod = root.find("module")
        self.assertIn("interface.mcu.mram", [x.get("interface") for x in mod.findall("requires")])
        self.assertEqual(mod.get("id"), "module.driver.flash_on_mram")
        guards = "".join(mod.find("guard").itertext())
        self.assertIn("void const *const p_context", guards)
        self.assertIn("cmse_check_address_range((void *)(uintptr_t) src_address", guards)
        self.assertIn(".write_window_start = ${module.driver.mram.write_start}", mod.findtext("declarations"))
        api_text = (FSP / "inc/api/r_flash_api.h").read_text().split("typedef struct st_flash_api", 1)[1]
        api_members = re.findall(r"fsp_err_t\s*\(\*\s*(\w+)\)", api_text)
        self.assertEqual(len(api_members), 19)
        for member in api_members:
            self.assertRegex((FSP / "src/r_mram/r_mram.c").read_text(), rf"\.{member}\s*=")


if __name__ == "__main__":
    unittest.main()
