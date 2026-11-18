"""OSPI-001..007: independent frame/address, MMIO, UBSan and MDF constraints.

Oracles: RA8P1 HM45.2.1.4 p3001 (ADDSIZE/MSByte), 45.2.2.7 p3009,
Fig5.4 p241 and HM46.1/46.3 pp3058-3060 (DOTF unit/range/page ends).
Original FSP5.9 API and crypto sources establish the compatibility boundary.
Full production translation units are compiled; volatile MMIO alone is redirected,
plus the old nonvolatile 64-bit destination store for the unaligned-load mutation.
Enabled target DOTF must fail compilation/configuration with the explicit binding
qualification diagnostic; no crypto helper is replaced or executed. No live e2/HIL evidence.
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
import xml.etree.ElementTree as ET

from tools.ra8p1.regression import readonly_sections
from tools.test_ra8p1_review_peripheral_capabilities import prepare, instrument, run, stock

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "baseline"
FSP = BASE / "ra/fsp"
SOURCE = FSP / "src/r_ospi_b/r_ospi_b.c"
MDF = BASE / "module_descriptions/Renesas##HAL Drivers##all##r_ospi_b####5.9.0.xml"
FIX = ROOT / "tools/ra8p1/review_ospi"
CRYPTO = FSP / "src/r_rsip_protected/crypto_procedures_protected/src/rsip/common"
CAPABILITY = "interface.mcu.ospi_b.1"
DISABLED = "config.driver.ospi_b.dotf_support.disabled"
ENABLED = "config.driver.ospi_b.dotf_support.protected_enabled"
COMPATIBILITY = "config.driver.ospi_b.dotf_support.enabled"
DOTF_BLOCKED = "OSPI_B DOTF crypto/register binding is not qualified for this variant"


def observe(ir):
    ir = instrument(ir)
    pattern = re.compile(r"^(\s*)store i64 ([%@\w.-]+), ptr (.*?), align \d+.*$", re.M)
    ir, count = pattern.subn(lambda m: f"{m[1]}call void @review_store64(ptr {m[3]}, i64 {m[2]})", ir)
    if count == 0:
        raise AssertionError("64-bit store observation did not run")
    return ir + "\ndeclare void @review_store64(ptr, i64)\n"


def evaluate(requests):
    # Evaluate actual substituted MDF JavaScript, not a Python translation of its rules.
    js = r"""const fs = require('fs');
const testExists = x => x === '1';
const testInteger = x => x.trim() !== '' && Number.isInteger(Number(x));
const req = JSON.parse(fs.readFileSync(0, 'utf8'));
console.log(JSON.stringify(req.map(r => r.expressions.map(e => {
  const substituted = e.replace(/\$\{([^}]+)\}/g, (_, k) => r.values[k] ?? '');
  return Boolean(eval(substituted));
}))));"""
    return json.loads(run(["node", "-e", js], input=json.dumps(requests)))


class OspiReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("clang")
        cls.arm = os.environ.get("RA8P1_ARM_GCC")
        db = ROOT / "validation/ra8p1/projects/wdt/Debug/compile_commands.json"
        if not cls.arm and db.is_file():
            cls.arm = shlex.split(json.loads(db.read_text())[0]["command"])[0]
        cls.arm = cls.arm or shutil.which("arm-none-eabi-gcc")
        if not cls.cc or not cls.arm or not shutil.which("node"):
            raise RuntimeError("Clang, original ARM GNU and Node required")
        cls.temp = tempfile.TemporaryDirectory(prefix="review-ospi-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.tmp = Path(cls.temp.name)
        cls.source = SOURCE.read_text()
        cls.xml = ET.parse(MDF).getroot()
        cls.stock_xml = ET.fromstring(run(["git", "-C", ROOT, "show", "HEAD:" + str(MDF.relative_to(ROOT))]))

    def flags(self, folder, checks, dotf=0, core=0, device="ra8p1"):
        flags = prepare(folder, device)
        cfg = folder / "r_ospi_b_cfg.h"
        cfg.write_text(cfg.read_text().replace("OSPI_B_CFG_DOTF_SUPPORT_ENABLE 0", f"OSPI_B_CFG_DOTF_SUPPORT_ENABLE {dotf}"))
        return flags + [f"-DCHECKS={checks}", "-DPROTECT=0", "-DBYPASS=0", f"-DBSP_CFG_CPU_CORE={core}"]

    def runtime(self, tag, checks=1, core=0, source=None):
        folder = self.tmp / tag
        folder.mkdir()
        flags = self.flags(folder, checks, core=core)
        src = folder / "r_ospi_b.c"
        src.write_text(self.source if source is None else source)
        sanitize = ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
        ir = run([self.cc, *flags, *sanitize, "-O0", "-S", "-emit-llvm", src, "-o", "-"])
        instrumented = folder / "ospi.ll"
        instrumented.write_text(observe(ir))
        binary = folder / "fixture"
        run([self.cc, *flags, *sanitize, "-O1", instrumented, FIX / "fixture.c", "-o", binary])
        return binary

    def test_complete_production_mmio_address_alias_bounds_null_and_unaligned_both_cores(self):
        for core, checks in itertools.product((0, 1), repeat=2):
            with self.subTest(core=core, checks=checks):
                binary = self.runtime(f"runtime-{core}-{checks}", checks, core)
                self.assertIn("OSPI cases passed", run([binary]))

    def test_each_regression_oracle_rejects_the_corresponding_original_defect(self):
        mutations = [
            ("map", "replace_mask = (replace_mask >> (address_size * 8U)) & 0xFFU;",
             "replace_mask = (replace_mask >> 24U) & 0xFFU;", "ADDRPEN erased valid address bits"),
            ("bounds", "uint32_t size = r_ospi_b_device_size_get(p_ctrl);",
             "uint32_t size = BSP_FEATURE_OSPI_B_DEVICE_SIZE(((ospi_b_extended_cfg_t *) p_ctrl->p_cfg->p_extend)->ospi_b_unit);",
             "command address width bound missing"),
            ("null", "        (NULL == p_cfg_extend->p_xspi_command_set) ||\n        (NULL == p_cfg_extend->p_xspi_command_set->p_table) ||\n",
             "", "null pointer"),
            ("unaligned", "memcpy(&data, p_src8, sizeof(data));", "data = *(uint64_t const *) p_src8;", "misaligned address"),
        ]
        for name, old, new, error in mutations:
            with self.subTest(defect=name):
                self.assertEqual(self.source.count(old), 1)
                binary = self.runtime("before-" + name, source=self.source.replace(old, new))
                result = subprocess.run([str(binary), name], capture_output=True, text=True, timeout=15)
                self.assertNotEqual(result.returncode, 0, "Original defect passed the independent runtime oracle")
                self.assertIn(error, result.stderr)

    def test_enabled_target_dotf_builds_are_explicitly_blocked_for_both_crypto_modes_and_cores(self):
        for core, checks, protected in itertools.product((0, 1), repeat=3):
            folder = self.tmp / f"dotf-blocked-{core}-{checks}-{protected}"
            folder.mkdir()
            flags = self.flags(folder, checks, dotf=1, core=core)
            if protected:
                flags += ["-DOSPI_B_CFG_DOTF_PROTECTED_MODE_SUPPORT_ENABLE"]
            flags += ["-mcpu=" + ("cortex-m85+nopacbti" if core == 0 else "cortex-m33"), "-mthumb", "-fsyntax-only"]
            with self.subTest(core=core, checks=checks, protected=protected):
                result = subprocess.run([str(self.arm), *flags, str(SOURCE)], capture_output=True, text=True, timeout=30)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('#error "' + DOTF_BLOCKED + '"', result.stderr)
                self.assertNotIn("fatal error:", result.stderr)
                self.assertNotIn("has no member", result.stderr)
                # Prove the intended diagnostic, not missing private headers/registers, causes rejection.
                diagnostic = ' #error "' + DOTF_BLOCKED + '"\n'
                self.assertEqual(self.source.count(diagnostic), 1)
                without_diagnostic = folder / "without_diagnostic.c"
                without_diagnostic.write_text(self.source.replace(diagnostic, ""))
                run([self.arm, *flags, without_diagnostic])

    def test_original_crypto_api_proves_unit1_binding_is_missing(self):
        private = stock(CRYPTO / "private/r_rsip_private.c")
        unit1 = private.split("[RSIP_OTF_CHANNEL_1] =", 1)[1].split("}", 1)[0]
        self.assertEqual(unit1.count("= NULL"), 3)
        api = stock(CRYPTO / "inc/api/r_rsip_api.h")
        self.assertIn("RSIP_OTF_CHANNEL_1", api)  # Enum existence is NOT an implementation.
        compat = stock(FSP / "src/r_sce/crypto_procedures/src/rsip_e50d/plainkey/private/inc/hw_sce_ra_private.h")
        functions = re.findall(r"fsp_err_t HW_SCE_Aes\d+OutputKeyForDotfSubAdaptor\(([^;]+)\);", compat)
        self.assertEqual(len(functions), 3)
        self.assertTrue(all("channel" not in f and "unit" not in f for f in functions))
        marker = "static fsp_err_t r_ospi_b_dotf_side_channal_seed_init ("
        legacy_helpers = stock(SOURCE).split(marker, 1)[1].rstrip()
        current_helpers = self.source.split(marker, 1)[1].split(
            "\n#if BSP_FEATURE_OSPI_B_HAS_UNIT_ADDRESS_MAP\nstatic uint32_t r_ospi_b_device_base_get", 1)[0].rstrip()
        self.assertEqual(current_helpers, legacy_helpers)

    def test_complete_production_arm_compile_both_cores_checks_and_optional_features(self):
        for core, checks, optional in itertools.product((0, 1), repeat=3):
            folder = self.tmp / f"arm-{core}-{checks}-{optional}"
            folder.mkdir()
            flags = self.flags(folder, checks, core=core)
            cfg = folder / "r_ospi_b_cfg.h"
            cfg.write_text(cfg.read_text().replace("AUTOCALIBRATION_SUPPORT_ENABLE 1", f"AUTOCALIBRATION_SUPPORT_ENABLE {optional}")
                           .replace("XIP_SUPPORT_ENABLE 1", f"XIP_SUPPORT_ENABLE {optional}"))
            with self.subTest(core=core, checks=checks, optional=optional):
                obj = folder / "ospi.o"
                run([self.arm, *flags, "-mcpu=" + ("cortex-m85+nopacbti" if core == 0 else "cortex-m33"),
                     "-mthumb", "-O2", "-c", SOURCE, "-o", obj])
                self.assertTrue(readonly_sections(obj.read_bytes()))

    def test_legacy_preprocessed_source_executable_constants_and_relocations_unchanged(self):
        for checks, optional in itertools.product((0, 1), repeat=2):
            folder = self.tmp / f"legacy-{checks}-{optional}"
            folder.mkdir()
            flags = self.flags(folder, checks, device="ra8m1")
            cfg = folder / "r_ospi_b_cfg.h"
            cfg.write_text(cfg.read_text().replace("AUTOCALIBRATION_SUPPORT_ENABLE 1", f"AUTOCALIBRATION_SUPPORT_ENABLE {optional}")
                           .replace("XIP_SUPPORT_ENABLE 1", f"XIP_SUPPORT_ENABLE {optional}"))
            before = folder / "before.c"
            before.write_text(stock(SOURCE))
            code, binary = [], []
            for src in (before, SOURCE):
                code.append(re.sub(r"\s+", " ", run([self.arm, *flags, "-E", "-P", src])))
                obj = folder / "ospi.o"
                run([self.arm, *flags, "-mcpu=cortex-m85", "-mthumb", "-O2", "-c", src, "-o", obj])
                binary.append(readonly_sections(obj.read_bytes()))
            with self.subTest(checks=checks, optional=optional):
                self.assertEqual(*code)
                self.assertTrue(binary[0])
                self.assertEqual(*binary)

    @staticmethod
    def constraints(xml):
        prefix = "module.driver.ospi_b.dotf."
        return [c.text for suffix in ("start_address", "end_address")
                for c in xml.find(f".//property[@id='{prefix}{suffix}']").findall("constraint")]

    @staticmethod
    def values(target, unit, enabled, start, end):
        return {CAPABILITY: "1" if target else "", "module.driver.ospi_b.unit": f"module.driver.ospi_b.unit.{unit}",
                "config.driver.ospi_b.dotf_support": ENABLED if enabled else DISABLED,
                "module.driver.ospi_b.dotf.start_address": hex(start), "module.driver.ospi_b.dotf.end_address": hex(end)}

    def test_actual_mdf_dotf_unit_ranges_inclusive_ends_disabled_defaults_and_negative_controls(self):
        constraints = self.constraints(self.xml)
        self.assertEqual(len(constraints), 4)
        requests, expected = [], []
        for unit, enabled in itertools.product((0, 1), repeat=2):
            for start, end in ((0x90000000, 0x90001fff), (0x80000000, 0x9fffffff),
                               (0x70000000, 0x7fffffff), (0x78000000, 0x78000fff),
                               (0x68000000, 0x68000fff), (0x6ffff000, 0x70000fff),
                               (0x80000001, 0x80001fff), (0x70000000, 0x70001000),
                               (0x80000000, 0x80001ffe), (0x80000000, 0x80001000)):
                lo, hi = ((0x70000000, 0x7fffffff) if unit else (0x80000000, 0x9fffffff))
                requests.append({"expressions": constraints, "values": self.values(True, unit, enabled, start, end)})
                expected.append([not enabled or lo <= start <= hi, not enabled or start % 4096 == 0,
                                 not enabled or lo <= end <= hi, not enabled or end % 4096 == 4095])
        self.assertEqual(evaluate(requests), expected)
        module = self.xml.find("module")
        guard = module.find(f"constraint[@display='{DOTF_BLOCKED}']")
        self.assertIsNotNone(guard, "Missing explicit DOTF qualification diagnostic")
        records, verdicts = [], []
        for target, unit, mode in itertools.product((False, True), (0, 1), (DISABLED, ENABLED, COMPATIBILITY)):
            values = self.values(target, unit, False, 0x90000000, 0x90001fff)
            values["config.driver.ospi_b.dotf_support"] = mode
            records.append({"expressions": [guard.text], "values": values})
            verdicts.append([not target or mode == DISABLED])
        self.assertEqual(evaluate(records), verdicts)
        # Existing security provider is part of the parent-owned interface contract.
        self.assertIsNotNone(module.find("provides[@interface='interface.peripheral.ospi_b${module.driver.ospi_b.unit}']"))
        for suffix, default in (("start_address", "0x90000000"), ("end_address", "0x90001FFF")):
            self.assertEqual(self.xml.find(f".//property[@id='module.driver.ospi_b.dotf.{suffix}']").get("default"), default)
        # Original metadata demonstrably rejects a valid/default inclusive end and the OSPI1 range.
        old = self.constraints(self.stock_xml)
        observed = evaluate([{"expressions": old, "values": self.values(True, 0, True, 0x90000000, 0x90001fff)},
                             {"expressions": old, "values": self.values(True, 1, True, 0x70000000, 0x70000fff)}])
        self.assertFalse(observed[0][3])
        self.assertFalse(observed[1][0])

    def test_legacy_mdf_constraints_and_all_emitted_templates_defaults_unchanged(self):
        old, new = self.constraints(self.stock_xml), self.constraints(self.xml)
        requests = []
        for unit, enabled in itertools.product((0, 1), repeat=2):
            for start in (0, 0x70000000, 0x80000000, 0x90000000, 0xa0000000):
                for end in (0, 0x70000fff, 0x90001fff, 0x9fffffff, 4095 * 600000):
                    v = self.values(False, unit, enabled, start, end)
                    requests += [{"expressions": old, "values": v}, {"expressions": new, "values": v}]
        outputs = evaluate(requests)
        self.assertEqual(outputs[::2], outputs[1::2])
        for tag in ("content", "header", "includes", "declarations", "functions", "guard", "nsc", "api"):
            self.assertEqual([ET.tostring(e) for e in self.stock_xml.iter(tag)],
                             [ET.tostring(e) for e in self.xml.iter(tag)], tag)
        def defaults(xml):
            return {e.get("id"): e.get("default") for e in xml.iter("property")}
        self.assertEqual(defaults(self.stock_xml), defaults(self.xml))


if __name__ == "__main__":
    unittest.main()
