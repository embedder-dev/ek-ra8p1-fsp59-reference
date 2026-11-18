"""Focused acquisition checks: execute production PDM C, never a Python driver model."""
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tools/ra8p1"
FSP = ROOT / "baseline/ra/fsp"
MDF = ROOT / "baseline/module_descriptions/Renesas##HAL Drivers##all##r_pdm####5.9.0.xml"


class PdmProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("cc")
        if not cls.cc:
            raise unittest.SkipTest("native C compiler unavailable")

    def compile(self, tmp, param, secure, extra=()):
        (tmp / "bsp_api.h").write_text('#include "acquisition_fixture_bsp.h"\n')
        (tmp / "r_pdm_cfg.h").write_text(f"#define PDM_CFG_PARAM_CHECKING_ENABLE {param}\n")
        return [self.cc, "-std=c11", "-Wall", "-Wextra", "-Wconversion", "-Wshadow", "-Werror",
                f"-DBSP_TZ_SECURE_BUILD={secure}", "-I" + str(tmp), "-I" + str(FIXTURE),
                "-I" + str(FSP / "inc"), "-I" + str(FSP / "inc/api"), "-I" + str(FSP / "inc/instances"), *extra]

    @staticmethod
    def default_properties():
        props = {}
        bsp = ET.parse(ROOT / "baseline/module_descriptions/Renesas##BSP##ra8p1##fsp####5.9.0.xml")
        for prop in ET.parse(MDF).findall("module/property"):
            value = prop.attrib["default"]
            option = prop.find(f"option[@id='{value}']")
            if option is None and prop.find("select") is not None:
                enum_id = prop.find("select").get("enum")
                enum = bsp.find(f".//enum[@id='{enum_id}']")
                option = enum.find(f"option[@id='{value}']")
            if option is not None:
                value = option.attrib["value"]
            props[prop.attrib["id"]] = value.replace("${_instance}", "0")
        return props

    def run_production(self, param, secure, defaults=False):
        with tempfile.TemporaryDirectory(prefix="acquisition-pdm-") as directory:
            tmp = Path(directory)
            binary = tmp / "pdm_fixture"
            command = self.compile(tmp, param, secure, ("-fsanitize=undefined", "-fno-omit-frame-pointer"))
            command += [str(FSP / "src/r_pdm/r_pdm.c"), str(FIXTURE / "acquisition_pdm_fixture.c"), "-o", str(binary)]
            if defaults:
                props = self.default_properties()
                mod = ET.parse(MDF).find("module")
                declarations = re.sub(r"\$\{([^}]+)\}", lambda m: props[m[1]], mod.findtext("declarations"))
                (tmp / "defaults.c").write_text(
                    '#include "r_pdm.h"\n#define VECTOR_NUMBER_PDM_DAT2 2\n#define VECTOR_NUMBER_PDM_ERR2 3\n' + declarations)
                command += ["-DTEST_PDM_DEFAULTS", str(tmp / "defaults.c")]
            build = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, build.returncode, build.stdout + build.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
            self.assertEqual(0, run.returncode, run.stdout + run.stderr)
            self.assertIn("production r_pdm:", run.stdout)

    def test_production_checks_enabled(self):
        self.run_production(1, 0)

    def test_production_checks_disabled(self):
        self.run_production(0, 0)

    def test_production_secure_checks_enabled(self):
        self.run_production(1, 1)

    def test_production_secure_checks_disabled(self):
        self.run_production(0, 1)

    def test_mdf_default_lifecycle(self):
        for checking in (0, 1):
            for secure in (0, 1):
                with self.subTest(checking=checking, secure=secure):
                    self.run_production(checking, secure, defaults=True)

    def test_mdf_default_declarations_and_nsc_compile(self):
        mod = ET.parse(MDF).find("module")
        props = self.default_properties()

        def resolve(text):
            return re.sub(r"\$\{([^}]+)\}", lambda m: props[m.group(1)], text)

        with tempfile.TemporaryDirectory(prefix="acquisition-mdf-") as directory:
            tmp = Path(directory)
            command = self.compile(tmp, 1, 1)
            code = '#include "r_pdm.h"\n#define VECTOR_NUMBER_PDM_DAT2 2\n#define VECTOR_NUMBER_PDM_ERR2 3\n'
            code += resolve(mod.findtext("header")) + resolve(mod.findtext("declarations"))
            (tmp / "declarations.c").write_text(code)
            build = subprocess.run(command + ["-fsyntax-only", str(tmp / "declarations.c")], capture_output=True, text=True)
            self.assertEqual(0, build.returncode, build.stdout + build.stderr)
            guard = mod.find("guard")
            (tmp / "guard.h").write_text('#include "r_pdm.h"\n' + resolve(mod.findtext("header")) +
                                        resolve(guard.findtext("header")))
            (tmp / "guard.c").write_text(resolve(guard.findtext("template")))
            build = subprocess.run(command + ["-fsyntax-only", str(tmp / "guard.c")], capture_output=True, text=True)
            self.assertEqual(0, build.returncode, build.stdout + build.stderr)
            nsc = mod.find("nsc")
            (tmp / "nsc.c").write_text('#include "r_pdm.h"\n' + resolve(nsc.findtext("header")) +
                                       resolve(nsc.findtext("declarations")))
            build = subprocess.run(command + ["-fsyntax-only", str(tmp / "nsc.c")], capture_output=True, text=True)
            self.assertEqual(0, build.returncode, build.stdout + build.stderr)


class PdmMetadataTests(unittest.TestCase):
    def test_mdf_matches_authoring_source(self):
        spec = importlib.util.spec_from_file_location("acquisition_mdf", FIXTURE / "acquisition_mdf.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.render(), MDF.read_text())

    def test_gate_and_interrupt_contract(self):
        mod = ET.parse(MDF).find("module")
        self.assertEqual("interface.mcu.pdm", mod.find("requires").attrib["interface"])
        irq = mod.find("property[@id='module.driver.pdm.ipl']")
        self.assertEqual("enum.mcu.nvic.priorities.mandatory", irq.find("select").attrib["enum"])
        self.assertEqual({"event.pdm${module.driver.pdm.channel}.dat", "event.pdm${module.driver.pdm.channel}.err"},
                         {item.attrib["event"] for item in irq.findall("interrupt")})
        self.assertIsNotNone(mod.find("guard/template"))
        self.assertIsNotNone(mod.find("nsc/declarations"))
        names = [element.attrib["id"] for element in ET.parse(MDF).iter() if "id" in element.attrib]
        self.assertEqual(len(names), len(set(names)))

    def test_duplicate_processing_channel_constraints(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node unavailable for MDF JavaScript controls")
        mod = ET.parse(MDF).find("module")
        interface = "interface.driver.pdm.channel.${module.driver.pdm.channel}"
        self.assertIsNotNone(mod.find(f"provides[@interface='{interface}']"))
        constraint = mod.find("constraint[@display='Processing channel already in use']").text
        expressions, expected = [], []
        for channels in ((0,), (1,), (2,), (2, 0), (0, 1, 2), (0, 0), (1, 1), (2, 2), (0, 1, 0)):
            for channel in channels:
                provided = interface.replace("${module.driver.pdm.channel}", str(channel))
                expression = constraint.replace("${module.driver.pdm.channel}", str(channel))
                expression = expression.replace("${" + provided + "}", str(channels.count(channel)))
                self.assertNotIn("${", expression)
                expressions.append(expression)
                expected.append(channels.count(channel) == 1)
        script = ('const expressions = JSON.parse(require("fs").readFileSync(0, "utf8")); '
                  'console.log(JSON.stringify(expressions.map(s => eval(s))));')
        result = subprocess.run([node, "-e", script], input=json.dumps(expressions),
                                capture_output=True, text=True, check=True)
        self.assertEqual(expected, json.loads(result.stdout))

    def test_actual_constraint_javascript_positive_negative_controls(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node unavailable for MDF JavaScript controls")
        mod = ET.parse(MDF).find("module")
        checks = {item.attrib["display"]: item.text for item in mod.findall("constraint")}
        physical = checks["Physical input must match channel and edge (falling channel 0 wraps to input 2)"]
        clocks = checks["PDMIF bus clock PCLKB must be 1 to 62.5 MHz"]
        for channel in range(3):
            for edge in ("rising", "falling"):
                physical_input = (channel + (2 if edge == "falling" else 0)) % 3
                for actual in range(3):
                    text = physical.replace("${module.driver.pdm.channel}", str(channel))
                    text = text.replace("${module.driver.pdm.physical_input}", str(actual))
                    text = text.replace("${module.driver.pdm.input}", "module.driver.pdm.input." + edge)
                    result = subprocess.run([node, "-p", text], capture_output=True, text=True, check=True)
                    self.assertEqual(str(actual == physical_input).lower(), result.stdout.strip())
        for clock, expected in ((999999, False), (1000000, True), (62500000, True), (62500001, False)):
            text = clocks.replace("${board.clock.peripheral.pdm}", str(clock))
            result = subprocess.run([node, "-p", text], capture_output=True, text=True, check=True)
            self.assertEqual(str(expected).lower(), result.stdout.strip())


class AdcProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("cc")
        if not cls.cc:
            raise unittest.SkipTest("native C compiler unavailable")

    def prepare(self, tmp, param, variant=1):
        header = "R7KA8P1KF.h" if variant else "R7FA6T2BD.h"
        device = (FSP / "src/bsp/cmsis/Device/RENESAS/Include" / header).read_text()
        end = device.index("} R_ADC_B0_Type;") + len("} R_ADC_B0_Type;")
        start = device.rfind("typedef struct", 0, end)
        registers = device[start:end] + "\n"
        registers += "\n".join(line for line in device.splitlines()
                                  if re.match(r"\s*#define R_ADC_B0_", line))
        family = "ra8p1" if variant else "ra6t2"
        features = (FSP / "src/bsp/mcu" / family / "bsp_feature.h").read_text()
        registers += "\n" + "\n".join(line for line in features.splitlines()
                                        if re.match(r"\s*#define BSP_FEATURE_ADC_B_UNIT_[01]_CHANNELS\s", line))
        (tmp / "acquisition_adc_registers.h").write_text(registers)
        if variant:
            override = (FSP / "src/bsp/mcu/ra8p1/bsp_override.h").read_text()
            types = override[override.index("/** ADC16H clock selectors"):override.rindex("#endif")]
            types = "#define BSP_OVERRIDE_ADC_CHANNEL_T\n#define ADC_B_CHANNEL_MASK_EXT_OFFSET (32U)\n" + types
        else:
            types = (FSP / "src/bsp/mcu/ra6t2/r_adc_device_types.h").read_text()
        (tmp / "r_adc_device_types.h").write_text(types)
        (tmp / "bsp_api.h").write_text('''#include "acquisition_adc_fixture_bsp.h"
#if BSP_FEATURE_ADC_B_REGISTER_TYPE == 1
#define BSP_CFG_CLOCKS_SECURE 0
#define FSP_STYPE3_REG8_READ(reg, secure) (reg)
#define FSP_PRIV_CLOCK_PCLKA 12U
typedef uint32_t fsp_priv_source_clock_t;
uint32_t R_FSP_SystemClockHzGet(uint32_t clock);
uint32_t R_BSP_SourceClockHzGet(fsp_priv_source_clock_t source);
#endif
''')
        (tmp / "r_adc_b_cfg.h").write_text(f"#define ADC_B_CFG_PARAM_CHECKING_ENABLE {param}\n")
        return [self.cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-Wno-pointer-to-int-cast", "-Wno-sign-compare", f"-DBSP_FEATURE_ADC_B_REGISTER_TYPE={variant}",
                "-I" + str(tmp), "-I" + str(FIXTURE), "-I" + str(FSP / "inc"),
                "-I" + str(FSP / "inc/api"), "-I" + str(FSP / "inc/instances")]

    def run_production(self, param):
        with tempfile.TemporaryDirectory(prefix="acquisition-adc-") as directory:
            tmp = Path(directory)
            command = self.prepare(tmp, param)
            binary = tmp / "adc_fixture"
            command += ["-fsanitize=undefined", "-fno-omit-frame-pointer",
                        str(FSP / "src/r_adc_b/r_adc_b.c"), str(FIXTURE / "acquisition_adc_fixture.c"),
                        "-o", str(binary)]
            build = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, build.returncode, build.stdout + build.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20,
                                 env={**os.environ, "UBSAN_OPTIONS": "halt_on_error=1"})
            self.assertEqual(0, run.returncode, run.stdout + run.stderr)
            self.assertIn("production r_adc_b:", run.stdout)

    def test_adc_production_checks_enabled(self):
        self.run_production(1)

    def test_adc_production_checks_disabled(self):
        self.run_production(0)

    def test_generated_adc_target_compilation(self):
        project = Path(os.environ.get("RA8P1_ADC_PROJECT", ROOT / "validation/ra8p1/projects/adc_b")).resolve()
        database = project / "Debug/compile_commands.json"
        if not database.is_file():
            self.skipTest("generated ADC project compile database unavailable")
        entry = next((item for item in json.loads(database.read_text())
                      if item["file"].endswith("/r_adc_b.c")), None)
        if not entry:
            self.fail("generated project compile database has no ADC_B source")
        command = shlex.split(entry["command"])
        if not shutil.which(command[0]):
            self.skipTest("recorded target compiler unavailable")
        with tempfile.TemporaryDirectory(prefix="acquisition-adc-target-") as directory:
            tmp = Path(directory)
            # Preserve generated header bytes, including their relative BSP includes; substitute candidate FSP only.
            for folder in ("ra_cfg", "ra_gen"):
                shutil.copytree(project / folder, tmp / folder)
            (tmp / "ra").mkdir()
            (tmp / "ra/fsp").symlink_to(FSP, target_is_directory=True)
            for index, arg in enumerate(command):
                if arg.startswith("-I" + str(project / "ra/fsp")):
                    command[index] = arg.replace(str(project / "ra/fsp"), str(FSP))
                elif arg.startswith(("-I" + str(project / "ra_cfg"), "-I" + str(project / "ra_gen"))):
                    command[index] = arg.replace(str(project), str(tmp))
            checks = tmp / "checks-on.h"
            checks.write_text('#include "bsp_api.h"\n#undef BSP_CFG_PARAM_CHECKING_ENABLE\n'
                              '#define BSP_CFG_PARAM_CHECKING_ENABLE 1\n')
            for source in (FSP / "src/r_adc_b/r_adc_b.c", ROOT / "validation/ra8p1/apps/adc_b.c"):
                for param in ("generated", "enabled"):
                    with self.subTest(source=source.name, checking=param):
                        args = command.copy()
                        args[args.index("-x") + 2] = str(source)
                        args[args.index("-o") + 1] = str(tmp / (source.stem + "-" + param + ".o"))
                        if param == "enabled":
                            args += ["-include", str(checks)]
                        build = subprocess.run(args + ["-Werror"], cwd=entry["directory"],
                                               capture_output=True, text=True)
                        self.assertEqual(0, build.returncode, build.stdout + build.stderr)

    def test_stock_adc_preprocessed_tokens_unchanged(self):
        for param in (0, 1):
            with self.subTest(param=param), tempfile.TemporaryDirectory(prefix="acquisition-adc-stock-") as directory:
                tmp = Path(directory)
                command = self.prepare(tmp, param, variant=0)
                original = tmp / "original"
                original.mkdir()
                for relative in ("ra/fsp/src/r_adc_b/r_adc_b.c", "ra/fsp/inc/instances/r_adc_b.h"):
                    data = subprocess.run(["git", "-C", str(ROOT / "baseline"), "show", "HEAD:" + relative],
                                          capture_output=True, check=True).stdout
                    (original / Path(relative).name).write_bytes(data)
                before = subprocess.run(command + ["-I" + str(original), "-E", "-P", str(original / "r_adc_b.c")],
                                        capture_output=True, text=True, check=True).stdout
                after = subprocess.run(command + ["-E", "-P", str(FSP / "src/r_adc_b/r_adc_b.c")],
                                       capture_output=True, text=True, check=True).stdout
                # Comments and conditional preprocessing may add whitespace, never tokens.
                self.assertEqual(re.findall(r"\S+", before), re.findall(r"\S+", after))
                for name, source in (("before", original / "r_adc_b.c"),
                                     ("after", FSP / "src/r_adc_b/r_adc_b.c")):
                    build = subprocess.run(command + ["-c", str(source), "-o", str(tmp / (name + ".o"))],
                                           capture_output=True, text=True)
                    self.assertEqual(0, build.returncode, build.stdout + build.stderr)
                self.assertEqual((tmp / "before.o").read_bytes(), (tmp / "after.o").read_bytes())


class AdcMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if not cls.node:
            raise unittest.SkipTest("node unavailable for actual MDF JavaScript")
        cls.path = ROOT / "baseline/module_descriptions/Renesas##HAL Drivers##all##r_adc_b####5.9.0.xml"
        cls.mod = ET.parse(cls.path).find("module")
        with zipfile.ZipFile(ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip") as release:
            pack_data = release.read("internal/projectgen/ra/packs/Renesas.RA.5.9.0.pack")
        with zipfile.ZipFile(io.BytesIO(pack_data)) as pack:
            stock = pack.read(".module_descriptions/" + cls.path.name)
        cls.stock = ET.fromstring(stock).find("module")

    def javascript(self, expressions):
        script = ('const testExists = s => s === "1"; const testInteger = s => Number.isInteger(Number(s)); '
                  'const expressions = JSON.parse(require("fs").readFileSync(0, "utf8")); '
                  'console.log(JSON.stringify(expressions.map(s => eval(s))));')
        result = subprocess.run([self.node, "-e", script], input=json.dumps(expressions),
                                capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    @staticmethod
    def substitute(text, values):
        return re.sub(r"\$\{([^}]+)\}", lambda match: str(values[match.group(1)]), text)

    def test_original_constraints_and_guards_preserved(self):
        for old in self.stock.findall("constraint"):
            self.assertTrue(any(item.attrib == old.attrib and item.text == old.text
                                for item in self.mod.findall("constraint")), old.attrib)
        self.assertEqual(ET.tostring(self.stock.find("nsc")), ET.tostring(self.mod.find("nsc")))
        old_guard = self.stock.find("guard")
        guard = ET.fromstring(ET.tostring(self.mod.find("guard")))
        guard.tail = self.mod.find("guard").tail
        old_template = old_guard.find("template")
        template = guard.find("template")
        self.assertEqual(old_template.attrib, template.attrib)
        cc = shutil.which("cc")
        self.assertIsNotNone(cc, "Native compiler required for whole legacy guard preprocessing")
        with tempfile.TemporaryDirectory(prefix="adc-guard-legacy-") as directory:
            tmp = Path(directory)
            (tmp / "guard.h").write_text("")
            for checking in (0, 1):
                tokens = []
                for text in (old_template.text, template.text):
                    source = text.replace("${module.driver.adc.name}", "g_adc")
                    result = subprocess.run(
                        [cc, "-E", "-P", "-x", "c", "-", "-I" + str(tmp),
                         "-DBSP_FEATURE_ADC_B_REGISTER_TYPE=0",
                         f"-DADC_B_CFG_PARAM_CHECKING_ENABLE={checking}"],
                        input=source, capture_output=True, text=True, timeout=30)
                    self.assertEqual(0, result.returncode, result.stderr)
                    tokens.append(result.stdout.split())
                self.assertEqual(*tokens)
        # All guard metadata and other emitted text still match the pristine pack.
        template.text = old_template.text
        self.assertEqual(ET.tostring(old_guard), ET.tostring(guard))
        old_props = {item.attrib["id"]: item for item in self.stock.findall("property")}
        for prop in self.mod.findall("property"):
            if prop.attrib["id"] in old_props:
                self.assertEqual(old_props[prop.attrib["id"]].attrib, prop.attrib)

    def test_gain_exports_variant_and_stock(self):
        fixture = AdcProductionTests()
        fixture.cc = shutil.which("cc")
        if not fixture.cc:
            self.skipTest("native C compiler unavailable for exported gain expressions")
        expressions, gains = [], []
        for index in range(8):
            key = f"module.driver.adc.user_gain_{index}"
            new = self.mod.find(f"property[@id='{key}']/export").text
            old = self.stock.find(f"property[@id='{key}']/export").text
            for gain in (0, 0.125, 1, 1.75, 3.99999):
                expressions += [self.substitute(new, {key: gain}), self.substitute(old, {key: gain})]
                gains.append(gain)
        results = self.javascript(expressions)
        for variant in (0, 1):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory(prefix="adc-gain-") as directory:
                tmp = Path(directory)
                command = fixture.prepare(tmp, 1, variant)
                code = '#include "r_adc_b.h"\nint main(void)\n{\n'
                for index, gain in enumerate(gains):
                    value = results[index * 2]
                    expected = math.floor(gain * (16384 if variant else 4194304))
                    code += f"    if ((uint32_t) ({value}) != {expected}U) return 1;\n"
                    if not variant:
                        old = results[index * 2 + 1]
                        code += f"    if ((uint32_t) ({value}) != (uint32_t) ({old})) return 2;\n"
                code += "    return 0;\n}\n"
                source, binary = tmp / "gain.c", tmp / "gain"
                source.write_text(code)
                build = subprocess.run(command + [str(source), "-o", str(binary)], capture_output=True, text=True)
                self.assertEqual(0, build.returncode, build.stdout + build.stderr)
                run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
                self.assertEqual(0, run.returncode, run.stdout + run.stderr)

    def test_new_constraint_positive_negative_controls(self):
        constraints = {item.attrib["display"]: item.text for item in self.mod.findall("constraint")}
        cap = "interface.mcu.adc_b.adc16h"
        priority = "module.driver.adc.group_priority_enable"
        strict = "module.driver.adc.single_ended_overflow_strict"
        period = "module.driver.adc.sync_operation_control_period"
        expressions, expected = [], []

        def case(label, values, want):
            expressions.append(self.substitute(constraints[label], values))
            expected.append(want)

        for value, want in ((4, False), (5, True), (255, True), (256, False)):
            case("ADC16H synchronous period must be 5 to 255 cycles.", {cap: "1", period: value}, want)
            case("ADC16H synchronous period must be 5 to 255 cycles.", {cap: "absent", period: value}, True)
        for present in ("1", "absent"):
            for choice in ("none", "unit_0", "unit_1", "both"):
                case("Group priority requires the ADC16H priority capability.",
                     {cap: present, priority: priority + "." + choice}, present == "1" or choice == "none")
            for enabled in (False, True):
                case("Strict single-ended overflow checking requires ADC16H.",
                     {cap: present, strict: strict + (".enabled" if enabled else ".disabled")},
                     present == "1" or not enabled)
        for unit in range(2):
            method = f"module.driver.adc.adc_{unit}_method"
            for selected in ("none", "unit_0", "unit_1", "both"):
                for mode in ("sar_mode", "hybrid_mode"):
                    case(f"ADC{unit} group priority is available only in SAR mode.",
                         {priority: priority + "." + selected, method: method + "." + mode},
                         mode == "sar_mode" or selected not in ("both", f"unit_{unit}"))
        for vc in range(33):
            p = f"module.driver.adc.virtual_channel_{vc}"
            label = f"Virtual channel {vc}: strict below-VREFL overflow requires zero offset and no addition/average (TN-RA-A0172A)."
            values = {strict: strict + ".enabled", p + "_scan_group": p + "_scan_group.scan_group_0",
                      p + "_input_mode_selection": f"enum.mcu.adc_b.virtual_channel_{vc}_input_mode.single_ended",
                      p + "_add_average_mode": p + "_add_average_mode.disabled",
                      p + "_offset_table": p + "_offset_table.disabled"}
            values.update({f"module.driver.adc.user_offset_id_{i}": 0 for i in range(8)})
            case(label, values, True)
            for table in range(8):
                selected = {**values, p + "_offset_table": p + f"_offset_table.offset_entry_{table}"}
                case(label, selected, True)
                case(label, {**selected, f"module.driver.adc.user_offset_id_{table}": -1}, False)
            averaged = {**values, p + "_add_average_mode": p + "_add_average_mode.average"}
            case(label, averaged, False)
            case(label, {**averaged, p + "_input_mode_selection":
                         f"enum.mcu.adc_b.virtual_channel_{vc}_input_mode.differential"}, True)
            case(label, {**averaged, p + "_scan_group": p + "_scan_group.none"}, True)
            case(label, {**averaged, strict: strict + ".disabled"}, True)
        self.assertEqual(expected, self.javascript(expressions))


if __name__ == "__main__":
    unittest.main()
