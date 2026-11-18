"""HM65/66-anchored DSI repair tests: complete production C, no live MMIO.

Native tests use real device and public headers with only BSP/CPU services
substituted. Each behavioral test also rejects the original production defect.
Node evaluates actual MDF export scripts; this is not live e2 validation.
"""
import itertools
import json
import math
import os
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from xml.etree import ElementTree as ET

from ra8p1.compatibility import original_sources, RELEASE_PACK
from ra8p1.regression import readonly_sections

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "baseline"
FSP = BASE / "ra/fsp"
FIXTURE = ROOT / "tools/ra8p1/review_dsi"
DSI = "ra/fsp/src/r_mipi_dsi/r_mipi_dsi.c"
PHY = "ra/fsp/src/r_mipi_phy/r_mipi_phy.c"
MDF = BASE / "module_descriptions/Renesas##HAL Drivers##all##r_mipi_dsi####5.9.0.xml"
CAP = "BSP_FEATURE_MIPI_DSI_STATUS_CLEAR_TYPE"
CORE = "#define __IM volatile const\n#define __OM volatile\n#define __IOM volatile\n"


def run(command, **kwargs):
    result = subprocess.run(command, capture_output=True, timeout=45, **kwargs)
    if result.returncode:
        raise AssertionError(f"{command}\n{result.stdout!r}\n{result.stderr!r}")
    return result.stdout


class DsiProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("cc")
        cls.node = shutil.which("node")
        candidates = [os.environ.get("ARM_GCC"), shutil.which("arm-none-eabi-gcc")]
        db = ROOT / "validation/ra8p1/compatibility/extra85/Debug/compile_commands.json"
        if db.is_file():
            row = json.loads(db.read_text())[0]
            candidates.append((row.get("arguments") or shlex.split(row["command"]))[0])
        cls.arm = None
        for candidate in dict.fromkeys(candidates):
            if candidate and Path(candidate).is_file():
                probe = subprocess.run([candidate, "-E", "-x", "c", "-"],
                                       input=b"#include <stdint.h>\n", capture_output=True)
                if probe.returncode == 0:
                    cls.arm = candidate
                    break
        if not cls.cc or not cls.node or not cls.arm:
            raise RuntimeError("Native C, Node and complete ARM GCC required (set ARM_GCC)")
        cls.original = original_sources(ROOT)
        with ZipFile(ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip") as release:
            with ZipFile(BytesIO(release.read(RELEASE_PACK))) as pack:
                cls.original_mdf = pack.read(".module_descriptions/" + MDF.name).decode("utf-8-sig")
        cls.temp = tempfile.TemporaryDirectory(prefix="review-dsi-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.tmp = Path(cls.temp.name)
        for variant in ("current", "before"):
            folder = cls.tmp / variant
            folder.mkdir()
            for name in ("core_cm85.h", "core_cm33.h", "core_cm7.h"):
                (folder / name).write_text(CORE)
            (folder / "r_mipi_dsi_cfg.h").write_text("")
            for path, name in ((DSI, "production_dsi.c"), (PHY, "production_phy.c")):
                source = (BASE / path).read_bytes() if variant == "current" else cls.original[path]
                if variant == "before" and path == DSI:
                    # Preserve the separately confirmed, pre-existing absent-clear-bit
                    # gates so unrelated compile failures do not mask these defects.
                    source = source.decode().replace("\r\n", "\n")
                    for symbol in ("SQCH0SCR_DABORT", "SQCH0SCR_SIZEERR", "SQCH1SCR_DABORT", "RXSCR_RXTE"):
                        source = re.sub(r"^ +R_DSILINK_" + symbol + r"_Msk \|\n", "", source, flags=re.M)
                    source = source.encode()
                (folder / name).write_bytes(source)
            metadata = MDF.read_text() if variant == "current" else cls.original_mdf
            (folder / "generated_config.h").write_text(cls.render_config(metadata))
        cls.binaries = {}

    @classmethod
    def render_config(cls, metadata):
        """Substitute a real MDF initializer; no generated project is modified."""
        root = ET.fromstring(metadata)
        content = root.find("module/declarations").text
        config = re.search(r"const mipi_dsi_cfg_t .*?_cfg =\s*\{.*?\n        \};", content, re.S)[0]
        values = {"module.driver.mipi_dsi.name": "g_generated",
                  "module.driver.mipi_dsi.requires.mipi_phy::module.driver.mipi_phy.name": "g_generated_phy",
                  "module.driver.mipi_dsi.ulps_wakeup_period": 1000,
                  "module.driver.mipi_dsi.requires.mipi_phy::module.driver.mipi_phy.pll_mhz": 1000,
                  "module.driver.mipi_dsi.requires.mipi_phy::module.driver.mipi_phy.lp_divisor": 5,
                  "module.driver.mipi_dsi.num_lanes": 2,
                  "module.driver.mipi_dsi.no_lp": "",
                  "module.driver.mipi_dsi.crc_enable_mask": ""}
        for axis, total, active, back, sync in (("vertical", 900, 854, 26, 4),
                                                ("horizontal", 600, 480, 70, 10)):
            values.update({f"module.driver.mipi_dsi.display.{axis[0]}timing.total_cyc": total,
                           f"module.driver.mipi_dsi.display.{axis[0]}timing.display_cyc": active,
                           f"module.driver.mipi_dsi.display.{axis[0]}timing.back_porch": back,
                           f"module.driver.mipi_dsi.display.{axis}_sync_lines": sync,
                           f"module.driver.mipi_dsi.display.{axis}_active_lines": active})
        # Export evaluation uses input microseconds; the initializer sees counts.
        for name in ("ulps_wakeup_count", "ulps_wakeup_period"):
            prop = root.find(".//property[@id='module.driver.mipi_dsi." + name + "']")
            if prop is not None:
                values["module.driver.mipi_dsi." + name] = cls.evaluate(prop.find("export").text, values)
        config = re.sub(r"\$\{([^}]+)\}", lambda m: str(values.get(m[1], 0)), config)
        return ("static mipi_phy_instance_t const g_generated_phy = {0};\n"
                "static mipi_dsi_timing_t const g_generated_timing = {0};\n"
                "static mipi_dsi_extended_cfg_t const g_generated_extended_cfg = {0};\n" + config + "\n")

    def flags(self, variant="current", target=1, core=0, checks=1, secure=0, ns=0, compiler=None):
        return [compiler or self.cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-Wno-pointer-to-int-cast", "-Wno-unused-parameter",
                "-I" + str(self.tmp / variant), "-I" + str(FIXTURE),
                "-I" + str(FSP / "src/bsp/cmsis/Device/RENESAS/Include"),
                "-I" + str(FSP / "src/bsp/mcu/all"), "-I" + str(FSP / "inc"),
                "-I" + str(FSP / "inc/api"), "-I" + str(FSP / "inc/instances"),
                "-include", str(FIXTURE / "bsp_api.h"), f"-DTEST_TARGET={target}",
                f"-D{CAP}={target}", f"-DBSP_CFG_CPU_CORE={core}",
                f"-DMIPI_DSI_CFG_PARAM_CHECKING_ENABLE={checks}",
                f"-DBSP_TZ_SECURE_BUILD={secure}", f"-DBSP_TZ_NONSECURE_BUILD={ns}"]

    def binary(self, variant="current", core=0, checks=1, secure=0, ns=0):
        key = variant, core, checks, secure, ns
        if key not in self.binaries:
            output = self.tmp / ("run-" + "-".join(map(str, key)))
            run(self.flags(variant, 1, core, checks, secure, ns) +
                ["-O1", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 str(FIXTURE / "fixture.c"), "-o", str(output)])
            self.binaries[key] = output
        return self.binaries[key]

    def scenario(self, number):
        for core, checks, security in itertools.product((0, 1), (0, 1), ((0, 0), (1, 0), (0, 1))):
            with self.subTest(core=core, checks=checks, security=security):
                run([str(self.binary("current", core, checks, *security)), str(number)])
        result = subprocess.run([str(self.binary("before", secure=int(number == 10))), str(number)],
                                capture_output=True, timeout=10)
        self.assertNotEqual(0, result.returncode, "Pre-repair production escaped the independent oracle")

    def test_dsi001_master_mode_precedes_power(self):
        self.scenario(1)

    def test_dsi002_required_ones_not_whole_reset_value(self):
        self.scenario(2)

    def test_dsi003_each_clear_destination_has_own_mask(self):
        self.scenario(3)

    def test_dsi005_both_polarities(self):
        self.scenario(5)

    def test_dsi006_aux_code_not_bta_full_code_and_unsupported_pre_mmio(self):
        self.scenario(6)

    def test_dsi007_bta_write_uses_tx_buffer(self):
        self.scenario(7)

    def test_dsi008_clock_entry_requires_hsclst_zero(self):
        self.scenario(8)

    def test_dsi009_receive_snapshot_and_consumed_slot_release(self):
        self.scenario(9)

    def test_dsi010_secure_rejects_ns_callback_before_mmio(self):
        self.scenario(10)

    def test_crlf_preserved(self):
        for path in (DSI, PHY):
            data = (BASE / path).read_bytes()
            self.assertNotIn(b"\n", data.replace(b"\r\n", b""))

    def test_legacy_whole_driver_tokens_and_arm_objects(self):
        # Exact original bytes, not the negative-control absent-bit adjustment.
        pristine = self.tmp / "pristine.c"
        for path, checks, secure in itertools.product((DSI, PHY), (0, 1), (0, 1)):
            with self.subTest(path=path, checks=checks, secure=secure):
                pristine.write_bytes(self.original[path])
                flags = self.flags(target=0, checks=checks, secure=secure, compiler=self.arm)
                flags += ["-mcpu=cortex-m85", "-mthumb", "-O2"]
                tokens, objects = [], []
                for source in (pristine, BASE / path):
                    tokens.append(run(flags + ["-E", "-P", str(source)]).split())
                    obj = self.tmp / "parity.o"
                    run(flags + ["-c", str(source), "-o", str(obj)])
                    objects.append(readonly_sections(obj.read_bytes()))
                self.assertEqual(*tokens)
                self.assertEqual(*objects)

    def test_target_arm_both_cores_and_receive_word_access(self):
        for core, cpu, checks, secure in itertools.product((0, 1), ("cortex-m85", "cortex-m33"), (0, 1), (0, 1)):
            if (core == 0) != (cpu == "cortex-m85"):
                continue
            with self.subTest(core=core, checks=checks, secure=secure):
                flags = self.flags(core=core, checks=checks, secure=secure, compiler=self.arm)
                flags += ["-mcpu=" + cpu, "-mthumb", "-O2"]
                for source in (DSI, PHY):
                    run(flags + ["-c", str(BASE / source), "-o", str(self.tmp / "target.o")])
                output = self.tmp / "target.s"
                run(flags + ["-S", str(BASE / DSI), "-o", str(output)])
                body = re.search(r"mipi_dsi_rcv_isr:\n(.*?)\.size\s+mipi_dsi_rcv_isr", output.read_text(), re.S)[1]
                # HM66.2: RXRSS0R is offset 0x240, must be read once in 32-bit units.
                self.assertEqual(1, len(re.findall(r"\bldr\s+r\d+, \[r\d+, #576\]", body)))
                self.assertNotRegex(body, r"\bldr[bhs]+\s+.*#57[6-9]")

    def test_legacy_generated_initializer_tokens_unchanged(self):
        tokens = []
        for metadata in (self.original_mdf, MDF.read_text()):
            path = self.tmp / "generated.c"
            path.write_text('#include "r_mipi_dsi.h"\n' + self.render_config(metadata))
            tokens.append(run(self.flags(target=0) + ["-E", "-P", str(path)]).split())
        self.assertEqual(*tokens)

    @classmethod
    def evaluate(cls, text, values):
        def substitute(match):
            key = match.group(1)
            if key not in values:
                raise AssertionError("Missing MDF substitution " + key)
            return str(values[key])
        script = re.sub(r"\$\{([^}]+)\}", substitute, text)
        harness = "var output; function testExists(v){return v !== 'absent';}\n"
        harness += "console.log(JSON.stringify(eval(" + json.dumps(script) + ")));"
        return json.loads(run([cls.node, "-e", harness]))

    def test_dsi004_generated_frontporches_preserve_total(self):
        self.scenario(4)
        text = MDF.read_text()
        for axis, total, active, back, sync in (("vertical", 900, 854, 26, 4),
                                                ("horizontal", 600, 480, 70, 10)):
            letter = axis[0]
            match = re.search(r"#if " + CAP + r" == 1\s+\." + axis +
                              r"_front_porch\s*=\s*(.*),", text)
            self.assertIsNotNone(match, "Missing target-only frontporch initializer")
            values = {f"module.driver.mipi_dsi.display.{letter}timing.total_cyc": total,
                      f"module.driver.mipi_dsi.display.{letter}timing.display_cyc": active,
                      f"module.driver.mipi_dsi.display.{letter}timing.back_porch": back,
                      f"module.driver.mipi_dsi.display.{axis}_sync_lines": sync}
            expression = re.sub(r"\$\{([^}]+)\}", lambda m: str(values[m[1]]), match[1])
            front = int(run([self.node, "-e", "console.log(" + expression + ")"]))
            self.assertEqual(total, sync + (back - sync) + active + front)
            # Prior production initializer is the independent negative control.
            self.assertNotEqual(total, sync + (back - sync) + active + total-active-back-sync)

    def test_dsi011_export_strict_minimum_round_up_and_no_saturation(self):
        root = ET.parse(MDF).getroot()
        prop = root.find(".//property[@id='module.driver.mipi_dsi.ulps_wakeup_count']")
        self.assertIsNotNone(prop)
        script = prop.find("export").text
        for mhz, divisor, requested in itertools.product((160, 720, 1000, 1024, 1440), (1, 4, 5, 16), (0, 999, 1000, 1001, 2611, 2612, 5000)):
            values = {"module.driver.mipi_dsi.ulps_wakeup_period": requested,
                      "module.driver.mipi_dsi.requires.mipi_phy::module.driver.mipi_phy.pll_mhz": mhz,
                      "module.driver.mipi_dsi.requires.mipi_phy::module.driver.mipi_phy.lp_divisor": divisor}
            count = self.evaluate(script, values)
            lp_mhz = mhz / 16 / divisor
            minimum = max(math.ceil(requested * lp_mhz / 128),
                          math.floor(1000 * lp_mhz / 128) + 1)
            if minimum > 255:
                self.assertEqual("MIPI_DSI_ULPS_WAKEUP_OUT_OF_RANGE", count)
            else:
                self.assertEqual(minimum, count)
                self.assertGreater(count * 128 / lp_mhz, 1000)
                self.assertGreaterEqual(count * 128 / lp_mhz, requested)
        constraint = root.find(".//constraint[@display='ULPS wakeup duration must be representable and strictly greater than 1 ms.']")
        self.assertIsNotNone(constraint)
        for capability, count in itertools.product(("absent", 0, 1), (98, "MIPI_DSI_ULPS_WAKEUP_OUT_OF_RANGE")):
            values = {"interface.mcu.mipi_csi": capability,
                      "module.driver.mipi_dsi.ulps_wakeup_count": count}
            self.assertEqual(capability != 1 or count == 98, self.evaluate(constraint.text, values))
        self.assertLess(97 * 128 / 12.5, 1000)  # Original export: parseInt floors.


if __name__ == "__main__":
    unittest.main()
