"""I3C-001..009: HM41-anchored full-production-C and MDF regressions.

The host fixture uses owning production register/public headers, not substitute
I3C implementations. It does not establish bus timing, transport or silicon
behavior. Metadata execution uses Node, not the live e2 configurator.
"""
from io import BytesIO
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
from zipfile import ZipFile

from ra8p1.regression import readonly_sections

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "baseline"
FSP = BASE / "ra/fsp"
SOURCE = FSP / "src/r_i3c/r_i3c.c"
MDF = BASE / "module_descriptions/Renesas##HAL Drivers##all##r_i3c####5.9.0.xml"
FIXTURE = ROOT / "tools/ra8p1/review_i3c"
CAP = "interface.mcu.i3c.restricted_command_set"


def run(command, **kwargs):
    result = subprocess.run(command, capture_output=True, timeout=45, **kwargs)
    if result.returncode:
        raise AssertionError(f"{command}\n{result.stdout!r}\n{result.stderr!r}")
    return result.stdout


def registers(text):
    end = text.index("} R_I3C0_Type;") + len("} R_I3C0_Type;")
    start = text.rfind("typedef struct", 0, end)
    return text[start:end] + "\n" + "\n".join(re.findall(r"^[ \t]*#define R_I3C0_.*$", text, re.M))


class I3cProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("cc")
        candidates = [os.environ.get("ARM_GCC"), shutil.which("arm-none-eabi-gcc")]
        commands = ROOT / "validation/ra8p1/compatibility/extra85/Debug/compile_commands.json"
        if commands.is_file():
            row = json.loads(commands.read_text())[0]
            candidates.append((row.get("arguments") or shlex.split(row["command"]))[0])
        cls.arm = None
        for candidate in dict.fromkeys(candidates):
            if candidate and Path(candidate).is_file():
                probe = subprocess.run([candidate, "-E", "-x", "c", "-"], input=b"#include <stdint.h>\n",
                                       capture_output=True, timeout=15)
                if probe.returncode == 0:
                    cls.arm = candidate
                    break
        if cls.cc is None or cls.arm is None:
            raise RuntimeError("Native C and complete ARM GNU compiler required (set ARM_GCC)")
        cls.temp = tempfile.TemporaryDirectory(prefix="review-i3c-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.tmp = Path(cls.temp.name)
        header = FSP / "src/bsp/cmsis/Device/RENESAS/Include/R7KA8P1KF.h"
        for device, filename in (("ra8p1", header.name), ("ra8m1", "R7FA8M1AH.h"),
                                 ("ra6e2", "R7FA6E2BB.h"), ("ra2e2", "R7FA2E2A7.h")):
            directory = cls.tmp / device
            directory.mkdir()
            content = (header.parent / filename).read_text()
            (directory / "registers.h").write_text(registers(content))
        (cls.tmp / "production.c").write_bytes(SOURCE.read_bytes())
        cls.pristine = cls.tmp / "pristine.c"
        cls.pristine.write_bytes(run(["git", "-C", str(BASE), "show", "HEAD:ra/fsp/src/r_i3c/r_i3c.c"]))
        cls.binaries = {}

    def flags(self, device="ra8p1", core=0, checks=1, unaligned=1, master=1, slave=1, compiler=None):
        return [compiler or self.cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-Wno-pointer-to-int-cast", "-Wno-unused-function",
                "-I" + str(self.tmp / device), "-I" + str(self.tmp), "-I" + str(FIXTURE),
                "-I" + str(FSP / "src/bsp/mcu" / device),
                "-I" + str(FSP / "inc"), "-I" + str(FSP / "inc/api"), "-I" + str(FSP / "inc/instances"),
                "-include", str(FIXTURE / "bsp_api.h"),
                f"-DBSP_CFG_CPU_CORE={core}", f"-DREVIEW_CHECKS={checks}",
                f"-DREVIEW_UNALIGNED={unaligned}", f"-DREVIEW_MASTER={master}", f"-DREVIEW_SLAVE={slave}"]

    def binary(self, core, checks, unaligned, master=1, slave=1):
        key = core, checks, unaligned, master, slave
        if key not in self.binaries:
            binary = self.tmp / ("i3c-" + "-".join(map(str, key)))
            run(self.flags("ra8p1", *key) + ["-O0", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                                            str(FIXTURE / "fixture.c"), "-o", str(binary)])
            self.binaries[key] = binary
        return self.binaries[key]

    def scenario(self, number):
        for core, checks, unaligned in itertools.product((0, 1), repeat=3):
            with self.subTest(core=core, checks=checks, unaligned=unaligned):
                run([str(self.binary(core, checks, unaligned)), str(number)])

    def test_i3c001_zero_payload_ccc_never_reads_null(self):
        self.scenario(1)

    def test_i3c002_valid_private_transfer_tags_public_events_unchanged(self):
        self.scenario(2)

    def test_i3c003_all_eight_entries_without_overflow(self):
        self.scenario(3)

    def test_i3c004_close_idle_and_eei_teardown_before_module_stop(self):
        self.scenario(4)

    def test_i3c005_masked_flag_readback(self):
        self.scenario(5)

    def test_high_bit_payload_and_register_fields_have_unsigned_shifts(self):
        self.scenario(6)

    def test_slave_admission_checks_precede_mmio(self):
        self.scenario(7)

    def test_master_only_and_slave_only_builds_both_cores(self):
        for core, checks, unaligned, modes in itertools.product((0, 1), (0, 1), (0, 1), ((1, 0), (0, 1))):
            with self.subTest(core=core, checks=checks, unaligned=unaligned, modes=modes):
                run([str(self.binary(core, checks, unaligned, *modes)), "6"])

    def test_older_preprocessing_and_arm_object_parity(self):
        for device, checks, unaligned, modes in itertools.product(
                ("ra8m1", "ra6e2", "ra2e2"), (0, 1), (0, 1), ((1, 1), (1, 0), (0, 1))):
            with self.subTest(device=device, checks=checks, unaligned=unaligned, modes=modes):
                flags = self.flags(device, 0, checks, unaligned, *modes, compiler=self.arm)
                flags += ["-mcpu=cortex-m33", "-mthumb", "-O2"]
                before = run(flags + ["-E", "-P", str(self.pristine)])
                after = run(flags + ["-E", "-P", str(SOURCE)])
                # __LINE__ is not used by the test BSP assertions.
                self.assertEqual(before.split(), after.split())
                sections = []
                for path in (self.pristine, SOURCE):
                    obj = self.tmp / "parity.o"
                    run(flags + ["-c", str(path), "-o", str(obj)])
                    sections.append(readonly_sections(obj.read_bytes()))
                self.assertTrue(sections[0])
                self.assertEqual(*sections)

    def test_crlf_is_preserved(self):
        for path in (SOURCE, MDF):
            raw = path.read_bytes()
            self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"), str(path))


class I3cMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if cls.node is None:
            raise RuntimeError("Node required for actual MDF JavaScript tests")
        cls.root = ET.parse(MDF).getroot()
        cls.module = cls.root.find("module")
        with ZipFile(ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip") as release:
            with ZipFile(BytesIO(release.read("internal/projectgen/ra/packs/Renesas.RA.5.9.0.pack"))) as pack:
                cls.stock_root = ET.fromstring(pack.read(".module_descriptions/" + MDF.name))
        cls.stock_module = cls.stock_root.find("module")

    def values(self, target=True):
        values = {e.get("id"): e.get("default") for e in self.module.findall("property")}
        values.update({CAP: "1" if target else "unresolved", "board.clock.peripheral.i3c.tclk": "200000000",
                       "module.driver.i3c.clock_constraints": "unused"})
        return values

    def eval(self, text, values):
        text = re.sub(r"\$\{([^{}]+)\}", lambda m: values.get(m[1], "unresolved"), text)
        code = ('const testInteger = x => /^-?[0-9]+$/.test(String(x)); '
                'const testExists = x => x === "1"; '
                'console.log(JSON.stringify(eval(JSON.parse(process.argv[1]))));')
        return json.loads(run([self.node, "-e", code, json.dumps(text)]))

    def admitted(self, prop, number, target=True):
        values = self.values(target)
        key = "module.driver.i3c." + prop
        values[key] = str(number)
        constraints = self.module.findall(f"property[@id='{key}']/constraint")
        constraints += [e for e in self.module.findall("constraint")
                        if "12.5 MHz on this peripheral" in e.get("display", "") and "${" + key + "}" in e.text]
        return all(self.eval(e.text, values) for e in constraints)

    def test_pristine_public_configuration_defaults_and_templates(self):
        self.assertEqual(ET.tostring(self.root.find("config")), ET.tostring(self.stock_root.find("config")))
        for tag in ("header", "includes", "declarations"):
            self.assertEqual(ET.tostring(self.module.find(tag)), ET.tostring(self.stock_module.find(tag)))
        before = self.stock_module.findall("property")
        after = self.module.findall("property")
        self.assertEqual(len(before), len(after))
        for original, candidate in zip(before, after):
            self.assertEqual(original.attrib, candidate.attrib)
            self.assertEqual([e.attrib for e in original.findall("option")],
                             [e.attrib for e in candidate.findall("option")])

    def test_legacy_clock_validation_and_export_match_pristine(self):
        def validator(module):
            return next(e.text for e in module.findall("constraint") if '"function calculate_period' in (e.text or ""))
        for clock, frequency in itertools.product((96000000, 192000000, 200000000), (4000000, 12500000, 12900000)):
            values = self.values(False)
            values["board.clock.peripheral.i3c.tclk"] = str(clock)
            for mode in ("stdbr", "extbr"):
                values["module.driver.i3c." + mode + ".pushpull.frequency"] = str(frequency)
            with self.subTest(clock=clock, frequency=frequency):
                self.assertEqual(self.eval(validator(self.stock_module), values), self.eval(validator(self.module), values))
                path = "property[@id='module.driver.bitrate_calculation']/export"
                self.assertEqual(self.eval(self.stock_module.find(path).text, values),
                                 self.eval(self.module.find(path).text, values))

    def test_i3c006_zero_unlimited_ibi_payload_target_only(self):
        for target in (False, True):
            for value in (-1, 0, 1, 255, 256):
                with self.subTest(target=target, value=value):
                    self.assertEqual((0 if target else 1) <= value <= 255,
                                     self.admitted("ibi_payload_length", value, target))

    def test_i3c007_absent_hot_join_and_address_stall_constraints(self):
        for prop in ("ack_hot_join", "notify_rejected_hot_join_request", "hotjoin_requests",
                     "clock_stalling_address_assignment_phase"):
            constraints = [e for e in self.module.findall("constraint") if "${module.driver.i3c." + prop + "}" in (e.text or "")]
            self.assertTrue(constraints, prop)
            for target, enabled in itertools.product((False, True), repeat=2):
                values = self.values(target)
                key = "module.driver.i3c." + prop
                values[key] = key + (".enabled" if enabled else ".disabled")
                self.assertEqual(not (target and enabled), all(self.eval(e.text, values) for e in constraints))

    def test_i3c008_requested_rate_limit_target_only(self):
        for mode in ("stdbr", "extbr"):
            for target in (False, True):
                for value in (12500000, 12500001, 12900000, 12900001):
                    with self.subTest(mode=mode, target=target, value=value):
                        self.assertEqual(value <= (12500000 if target else 12900000),
                                         self.admitted(mode + ".pushpull.frequency", value, target))

    def test_i3c008_actual_rate_in_validator_and_export(self):
        validator = next(e.text for e in self.module.findall("constraint") if '"function calculate_period' in (e.text or ""))
        exporter = self.module.find("property[@id='module.driver.bitrate_calculation']/export").text
        # At 192 MHz: counts 7+8 give 12.8 MHz. This is within the old
        # 10% request tolerance but above HM41 table41.2's 12.5 MHz ceiling.
        for target, text, excessive in itertools.product((False, True), (validator, exporter), (False, True)):
            values = self.values(target)
            values.update({"module.driver.i3c.stdbr.pushpull.frequency": "12900000" if excessive else "12500000",
                           "module.driver.i3c.extbr.pushpull.frequency": "12900000" if excessive else "12500000",
                           "module.driver.i3c.stdbr.pushpull.logic_high": "40",
                           "module.driver.i3c.extbr.pushpull.logic_high": "40",
                           "board.clock.peripheral.i3c.tclk": "192000000" if excessive else "200000000"})
            js = self.eval(text, values)
            if text == validator:
                self.assertEqual(not (target and excessive), bool(js))
            else:
                self.assertEqual(target and excessive, "12.5 MHz" in js)

    def test_i3c009_full_legal_turnaround_target_only(self):
        for target in (False, True):
            for value in (-1, 0, 255, 256, 16000000, 16000001, 0xFFFFFF):
                self.assertEqual(0 <= value <= (16000000 if target else 255),
                                 self.admitted("max_read_turnaround_time", value, target))


if __name__ == "__main__":
    unittest.main()
