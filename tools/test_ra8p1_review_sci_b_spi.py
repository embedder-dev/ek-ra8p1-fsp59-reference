"""SCISPI-001..004 requirement tests, not implementation-shape snapshots.

Oracles: HM39.6.5 Fig39.69 pp2319-2320; 39.2.29 p2251;
39.19.6 p2373; 39.19.15 p2376; Tables39.7/39.9 pp2201-2202.
The complete production C TU is compiled against owning device/API headers.
Only LLVM volatile load/store instructions are intercepted by a delayed MMIO
model. Node executes the actual MDF expressions, not the live configurator.
No generated project, installed pack, IDE state or hardware is changed.
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
from xml.etree import ElementTree as ET

from tools.ra8p1.regression import readonly_sections

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "baseline"
FSP = BASE / "ra/fsp"
SOURCE = FSP / "src/r_sci_b_spi/r_sci_b_spi.c"
MDF = BASE / "module_descriptions/Renesas##HAL Drivers##all##r_sci_b_spi####5.9.0.xml"
FIXTURE = ROOT / "tools/ra8p1/review_sci_b_spi"
HEADERS = {"ra8p1": "R7KA8P1KF.h", "ra6t2": "R7FA6T2BD.h", "ra8m1": "R7FA8M1AH.h",
           "ra8d1": "R7FA8D1BH.h", "ra8e1": "R7FA8E1AF.h", "ra8e2": "R7FA8E2AF.h",
           "ra8t1": "R7FA8T1AH.h"}
CAP = "interface.mcu.sci_b.no_scksel"


def run(command, **kwargs):
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True, timeout=60, **kwargs)
    if result.returncode:
        raise AssertionError(str(command) + "\n" + result.stdout + result.stderr)
    return result.stdout


def pristine(path):
    repository = ROOT if path == MDF else BASE
    return run(["git", "-C", repository, "show", "HEAD:" + str(path.relative_to(repository))])


def prepare(tmp, device):
    header = (FSP / "src/bsp/cmsis/Device/RENESAS/Include" / HEADERS[device]).read_text()
    end = header.index("} R_SCI_B0_Type;") + len("} R_SCI_B0_Type;")
    start = header.rfind("typedef struct", 0, end)
    (tmp / "registers.h").write_text(header[start:end] + "\n" + "\n".join(
        re.findall(r"^[ \t]*#define R_SCI_B0_.*$", header, re.M)))
    (tmp / "r_sci_b_spi_cfg.h").write_text("/* Checking and DTC selected on the compiler command line. */\n")
    return ["-std=c11", "-Wall", "-Wextra", "-Werror", "-Wundef",
            "-I" + str(tmp), "-I" + str(FIXTURE), "-I" + str(FSP / "src/bsp/mcu" / device),
            "-I" + str(FSP / "inc"), "-I" + str(FSP / "inc/api"), "-I" + str(FSP / "inc/instances"),
            "-include", str(FIXTURE / "bsp_api.h")]


def intercept_volatile(ir):
    """Replace every volatile MMIO load/store, retaining all production C control flow.

    These are LLVM instruction substitutions, not extracted/reimplemented driver
    functions. Count assertions prevent silently losing instrumentation when LLVM
    syntax changes. The model only accepts addresses in the owning SCI register map.
    """
    reads = re.compile(r"^(\s*)(%\w+) = load volatile (i8|i16|i32|ptr), ptr (%\w+), align \d+.*$", re.M)
    writes = re.compile(r"^(\s*)store volatile (i8|i16|i32|ptr) ([%@\w.-]+), ptr (%\w+), align \d+.*$", re.M)
    suffix = lambda kind: kind.removeprefix("i")
    ir, nr = reads.subn(lambda m: f"{m[1]}{m[2]} = call {m[3]} @review_mmio_read{suffix(m[3])}(ptr {m[4]})", ir)
    ir, nw = writes.subn(lambda m: f"{m[1]}call void @review_mmio_write{suffix(m[2])}(ptr {m[4]}, {m[2]} {m[3]})", ir)
    if "load volatile" in ir or "store volatile" in ir or nr < 5 or nw < 5:
        raise AssertionError("Incomplete production MMIO instrumentation")
    for kind in ("i8", "i16", "i32", "ptr"):
        ir += f"\ndeclare {kind} @review_mmio_read{suffix(kind)}(ptr)\n"
        ir += f"declare void @review_mmio_write{suffix(kind)}(ptr, {kind})\n"
    return ir


class SciSpiProductionReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("clang")
        cls.arm = os.environ.get("RA8P1_ARM_GCC")
        database = ROOT / "validation/ra8p1/projects/wdt/Debug/compile_commands.json"
        if not cls.arm and database.is_file():
            cls.arm = shlex.split(json.loads(database.read_text())[0]["command"])[0]
        cls.arm = cls.arm or shutil.which("arm-none-eabi-gcc")
        if not cls.cc or not cls.arm:
            raise RuntimeError("Clang LLVM and ARM GNU compilers are required")
        cls.temp = tempfile.TemporaryDirectory(prefix="review-sci-spi-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.tmp = Path(cls.temp.name)
        cls.before = cls.tmp / "before.c"
        stock = pristine(SOURCE)
        old = ("    /* CCR4.SCKSEL selects the master receive clock used in simple spi mode on supported MCUs. */\n"
               "    uint32_t ccr4  = (BSP_FEATURE_SCI_SPI_SCKSEL_VALUE << R_SCI_B0_CCR4_SCKSEL_Pos);\n")
        if stock.count(old) != 1:
            raise AssertionError("Unexpected stock SCKSEL initialization")
        # The pre-review candidate differed from stock only by this already-approved field-presence gate.
        cls.before.write_text(stock.replace(old, "#if BSP_FEATURE_SCI_SPI_HAS_SCKSEL\n" + old +
                                             "#else\n    uint32_t ccr4  = 0U;\n#endif\n"))
        cls.binaries = {}

    def binary(self, core, checks, dtc, before=False):
        key = core, checks, dtc, before
        if key not in self.binaries:
            tmp = self.tmp / "-".join(map(str, key))
            tmp.mkdir(exist_ok=True)
            flags = prepare(tmp, "ra8p1") + [f"-DBSP_CFG_CPU_CORE={core}",
                f"-DSCI_B_SPI_CFG_PARAM_CHECKING_ENABLE={checks}", f"-DSCI_B_SPI_DTC_SUPPORT_ENABLE={dtc}"]
            source = self.before if before else SOURCE
            ir = run([self.cc, *flags, "-O0", "-S", "-emit-llvm", source, "-o", "-"])
            (tmp / "driver.ll").write_text(intercept_volatile(ir))
            binary = tmp / "fixture"
            run([self.cc, *flags, "-O1", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 tmp / "driver.ll", FIXTURE / "fixture.c", "-o", binary])
            self.binaries[key] = binary
        return self.binaries[key]

    def scenario(self, scenario, parameters=(0, 1)):
        for core, checks, dtc, parameter, channel in itertools.product(
                (0, 1), (0, 1), (0, 1), parameters, (0, 9)):
            with self.subTest(core=core, checks=checks, dtc=dtc, parameter=parameter, channel=channel):
                result = run([self.binary(core, checks, dtc), scenario, parameter, channel])
                self.assertIn("production SCI_B SPI focused case passed", result)

    def test_scispi001_overrun_stops_acknowledges_drains_clears_before_callback_and_restart(self):
        self.scenario(1)

    def test_scispi002_tei_acknowledges_delayed_internal_stop_before_callback_and_restart(self):
        self.scenario(2)

    def test_scispi002_admission_waits_for_internal_stop_before_next_control_write(self):
        self.scenario(4, (0,))

    def test_scispi003_slave_second_preload_waits_for_tdre_including_dummy_receive(self):
        self.scenario(3, (0, 1, 2, 3))

    def test_busy_te_or_re_is_rejected_without_mutating_control_or_hardware(self):
        self.scenario(5)

    def test_pre_review_production_fails_all_four_runtime_oracles(self):
        for scenario, parameter in ((1, 1), (2, 1), (3, 2), (4, 0)):
            with self.subTest(scenario=scenario):
                result = subprocess.run([str(self.binary(0, 1, 0, before=True)), str(scenario), str(parameter), "0"],
                                        capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0, "pre-review source unexpectedly met the requirement")
                expected = {1: "drains == 1U && cesr == 0U", 2: "cesr == 0U && stop_delay == 0U",
                            3: "csr & R_SCI_B0_CSR_TDRE_Msk", 4: "cesr == 0U"}
                self.assertIn(expected[scenario], result.stderr)

    def test_all_legacy_sci_b_families_full_tu_preprocessing_and_arm_objects_match_stock(self):
        for device, checks, dtc in itertools.product(tuple(d for d in HEADERS if d != "ra8p1"), (0, 1), (0, 1)):
            with self.subTest(device=device, checks=checks, dtc=dtc):
                tmp = self.tmp / f"legacy-{device}-{checks}-{dtc}"
                tmp.mkdir()
                flags = prepare(tmp, device) + [f"-DSCI_B_SPI_CFG_PARAM_CHECKING_ENABLE={checks}",
                    f"-DSCI_B_SPI_DTC_SUPPORT_ENABLE={dtc}", "-DBSP_CFG_CPU_CORE=0",
                    "-mcpu=cortex-m33", "-mthumb", "-O2"]
                old = tmp / "stock.c"
                old.write_text(pristine(SOURCE))
                self.assertEqual(run([self.arm, *flags, "-E", "-P", old]).split(),
                                 run([self.arm, *flags, "-E", "-P", SOURCE]).split())
                objects = []
                for path in (old, SOURCE):
                    obj = tmp / "driver.o"
                    run([self.arm, *flags, "-c", path, "-o", obj])
                    objects.append(readonly_sections(obj.read_bytes()))
                self.assertTrue(objects[0])
                self.assertEqual(*objects)

    def test_complete_production_driver_arm_builds_both_cores_checking_and_dtc_on_off(self):
        for core, checks, dtc in itertools.product((0, 1), repeat=3):
            with self.subTest(core=core, checks=checks, dtc=dtc):
                tmp = self.tmp / f"target-arm-{core}-{checks}-{dtc}"
                tmp.mkdir()
                cpu = "cortex-m33" if core else "cortex-m85+nopacbti"
                flags = prepare(tmp, "ra8p1") + [f"-DBSP_CFG_CPU_CORE={core}",
                    f"-DSCI_B_SPI_CFG_PARAM_CHECKING_ENABLE={checks}", f"-DSCI_B_SPI_DTC_SUPPORT_ENABLE={dtc}",
                    f"-mcpu={cpu}", "-mthumb", "-O2"]
                run([self.arm, *flags, "-c", SOURCE, "-o", tmp / "driver.o"])
                self.assertTrue(readonly_sections((tmp / "driver.o").read_bytes()))

    def test_existing_production_files_retain_crlf(self):
        for path in (SOURCE, MDF):
            data = path.read_bytes()
            self.assertGreater(data.count(b"\r\n"), 0)
            self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))


class SciSpiMdfReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if not cls.node:
            raise RuntimeError("Node is required to evaluate the production MDF expressions")
        cls.current = MDF.read_text()
        cls.stock = pristine(MDF)

    def evaluate(self, cases, current=True):
        module = ET.fromstring(self.current if current else self.stock).find("module")
        constraints = [c.text for c in module.findall("constraint") if "${module.driver.spi.bitrate}" in c.text]
        export = module.find("property[@id='module.driver.spi.bitrate']/export").text
        js = r'''
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const testExists = value => !String(value).startsWith('${');
const testInteger = value => Number.isInteger(Number(value));
const substitute = (text, values) => text.replace(/\$\{([^}]+)\}/g,
    (match, key) => Object.hasOwn(values, key) ? String(values[key]) : match);
const output = input.cases.map(c => {
    const values = {
        'module.driver.spi.bitrate': c.rate,
        'module.driver.spi.operating_mode': 'module.driver.spi.operating_mode.mode_' + c.mode,
        'module.driver.spi.clock_source': 'module.driver.spi.clock_source.' + c.source,
        'board.clock.peripheral.sci_b': c.pclk,
        'board.clock.peripheral.sciclk': c.sciclk,
        'config.bsp.fsp.mcu.sci_spi.max_bitrate': 60000000,
    };
    if (c.target) values['interface.mcu.sci_b.no_scksel'] = 1;
    const admitted = input.constraints.every(text => Boolean(eval(substitute(text, values))));
    const result = { admitted };
    if (admitted && c.mode === 'master' && Number(c.rate) > 0) {
        values['module.driver.spi.clock_source'] = Number(c.source === 'pclk');
        result.generated = eval(substitute(input.export, values));
    }
    return result;
});
console.log(JSON.stringify(output));
'''
        return json.loads(run([self.node, "-e", js], input=json.dumps(
            {"constraints": constraints, "export": export, "cases": cases})))

    @staticmethod
    def case(rate, source="pclk", mode="master", target=True, pclk=125000000, sciclk=24000000):
        return dict(rate=rate, source=source, mode=mode, target=target, pclk=pclk, sciclk=sciclk)

    def test_scispi004_numeric_positive_and_negative_boundaries_for_both_clock_sources(self):
        cases = []
        expected = []
        for clock, source in itertools.product((1, 65536, 65537, 24000000, 120000000, 125000000),
                                                ("pclk", "scispiclk")):
            minimum = (clock + 65535) // 65536
            for rate in (0, 1, minimum - 1, minimum, minimum + 1):
                cases.append(self.case(rate, source, pclk=clock, sciclk=clock))
                expected.append(rate >= minimum and rate > 0)
        for case, result, admitted in zip(cases, self.evaluate(cases), expected):
            with self.subTest(**case):
                self.assertEqual(result["admitted"], admitted)
                if admitted:
                    fields = {name: int(value) for name, value in re.findall(r"\.(cks|brr|bgdm) = (\d+)", result["generated"])}
                    self.assertEqual(set(fields), {"cks", "brr", "bgdm"})
                    self.assertLessEqual(fields["brr"], 255)
                    divisor = (1 << (2 * (fields["cks"] + 1) - fields["bgdm"])) * (fields["brr"] + 1)
                    self.assertLessEqual(case["pclk"], int(case["rate"]) * divisor)

    def test_scispi004_pre_review_admits_and_overspeeds_the_125mhz_one_bps_counterexample(self):
        case = self.case(1)
        result = self.evaluate([case], current=False)[0]
        self.assertTrue(result["admitted"])
        self.assertIn(".cks = 3, .brr = 255, .bgdm = 0", result["generated"])
        self.assertGreater(125000000 / 65536, case["rate"])
        self.assertFalse(self.evaluate([case])[0]["admitted"])

    def test_slave_low_bitrate_and_all_legacy_admissions_and_exports_remain_unchanged(self):
        cases = [self.case(rate, source, mode, target) for rate, source, mode, target in itertools.product(
            (-1, 0, 1, 366, 367, 1907, 1908, 8000000, 60000000, 60000001),
            ("pclk", "scispiclk"), ("master", "slave"), (False, True))
            if not target or mode == "slave"]
        self.assertEqual(self.evaluate(cases, current=False), self.evaluate(cases))

    def test_original_mdf_bytes_and_all_generation_templates_are_unchanged(self):
        new = re.findall(r'        <constraint display="Master bitrate[^\n]+\n.*?        </constraint>\n',
                         self.current, re.S)
        self.assertEqual(len(new), 1)
        self.assertEqual(self.current.replace(new[0], ""), self.stock)

    def test_target_capability_is_provided_and_not_advertised_on_stock_sci_layouts(self):
        # This explicit integration gate prevents an otherwise valid but inert constraint.
        for family, expected in (("ra8p1", True), ("ra6t2", False), ("ra8m1", False)):
            path = BASE / f"module_descriptions/Renesas##BSP##{family}##device####5.9.0.xml"
            provided = {p.get("interface") for p in ET.parse(path).iter("provides")}
            self.assertEqual(CAP in provided, expected,
                             f"Parent device-MDF integration required: {family} must provide {CAP}={expected}")


if __name__ == "__main__":
    unittest.main()
