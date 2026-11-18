"""Independent regression anchors for confirmed HDR-A01/A02/A03.

Primary inputs reviewed directly: RA8P1 HM R01UH1064EJ0130 Rev.1.30
54.2.13.2 pp.3401-3402 (including Note 1), 60.5.41-44 pp.3591-3592.
The literal C fixture is independent of register inventory values. Stock FSP
5.9 R7FA6T2BD.h:19179-19188 supplies DATA/DIAGSR/ERR vocabulary only;
R7FA8M1AH.h supplies SYSTEM naming. Those headers do not describe RA8P1
identity registers: UIDR/PNR/MCUVE spelling comes from the cited manual.
Native CMSIS headers are layout doubles, Arm builds use preserved 5.9 CMSIS.
No register is accessed, and no OTP write or chip-specific reset is assumed.
"""

from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile

from tools import test_ra8p1_device_header as layout

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / "tools/ra8p1"
FIXTURE = HERE / "review_header_analog_fixture.c"
DIAGNOSTIC = (0, 1, 16, 17, 18, 20, 21, 22)
RESERVED = (2, 3, 7, 10, 11, 12, 13, 14, 15, 19)
NON_DIAGNOSTIC = (4, 5, 6, 8, 9)


def inventory(filename):
    return json.loads((HERE / filename).read_text())


@contextmanager
def disposable_header():
    """Render to a temporary include directory; never update the shared header."""
    with tempfile.TemporaryDirectory(prefix="ra8p1-review-analog-") as directory:
        folder = Path(directory)
        (folder / "R7KA8P1KF.h").write_text(layout.GEN.render(layout.GEN.load_inventory()))
        shutil.copyfile(layout.INCLUDE / "system.h", folder / "system.h")
        yield folder


def native_flags(folder, core=0, nonsecure=0):
    return ["-std=c11", "-Wall", "-Wextra", "-Werror", f"-DBSP_CFG_CPU_CORE={core}",
            f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}", "-I", folder,
            "-I", HERE / "layout/native", "-I", layout.BSP]


class AnalogHeaderReviewTests(unittest.TestCase):
    def test_adexdr_exact_diagnostic_indices_and_unchanged_common_span(self):
        block = next(b for b in inventory("registers_adc.json")["types"] if b["name"] == "R_ADC_B0_Type")
        reg = next(r for r in block["members"] if r["name"] == "ADEXDR")
        self.assertEqual(0x2180, int(reg["offset"], 0))
        self.assertEqual(23, reg["count"])
        self.assertEqual(list(RESERVED), reg["reserved_indices"])
        self.assertEqual([("DATA", 0, 16, "R"), ("ERR", 31, 1, "R")],
                         [(f["name"], f["pos"], f["bits"], f["access"]) for f in reg["fields"]])
        views = reg.get("views", [])
        self.assertEqual([f"ADEXDR{n}" for n in DIAGNOSTIC], [v["name"] for v in views])
        for n, view in zip(DIAGNOSTIC, views):
            with self.subTest(index=n):
                self.assertEqual((4 * n, 32, "R"), (view["offset"], view["width"], view["access"]))
                self.assertEqual([("DATA", 0, 16, "R"), ("DIAGSR", 24, 3, "R"), ("ERR", 31, 1, "R")],
                                 [(f["name"], f["pos"], f["bits"], f["access"]) for f in view["fields"]])

    def test_mwmcr_literal_layout_access_and_known_reset(self):
        block = next(b for b in inventory("registers.json")["types"] if b["name"] == "R_SYSTEM_Type")
        reg = next((r for r in block["members"] if r["name"] == "MWMCR"), None)
        self.assertIsNotNone(reg, "HM60.5.44 p3592 requires SYSC.MWMCR")
        self.assertEqual((0xAB4, 8, "R/W", "0x00"),
                         (int(reg["offset"], 0), reg["width"], reg["access"], reg["reset"]))
        self.assertEqual([{"name": "MWM", "pos": 0, "bits": 2, "access": "R/W"}], reg["fields"])

    def test_identity_layout_ro_width_and_chip_specific_reset(self):
        data = inventory("registers_mram.json")
        blocks = {b["name"]: b for b in data["types"]}
        instances = {i["name"]: i for i in data["instances"]}
        for name, address, member, width, field in (
                ("R_UIDR", 0x02F07B00, "UIDR", 32, "UID"),
                ("R_PNR", 0x02C1EC38, "PNR", 32, "PNR"),
                ("R_MCUVER", 0x02C1EC48, "MCUVER", 8, "MCUVE")):
            with self.subTest(register=name):
                self.assertIn(name, instances)
                instance = instances[name]
                self.assertEqual(address, int(instance["secure"], 0))
                self.assertNotIn("nonsecure", instance, "No guessed +0x10000000 identity alias")
                block = blocks[instance["type"]]
                reg, = block["members"]
                self.assertEqual((member, 0, width, "R", "chip-specific"),
                                 (reg["name"], int(reg["offset"], 0), reg["width"], reg["access"], reg["reset"]))
                self.assertEqual([{"name": field, "pos": 0, "bits": width, "access": "R"}], reg["fields"])
                if width == 32:
                    self.assertEqual(4, reg["count"])
                    self.assertEqual([f"{member}{n}" for n in range(4)], reg["individual_names"])
                else:
                    self.assertNotIn("count", reg)

    def test_no_diagnostic_macros_on_common_non_diagnostic_or_reserved_indices(self):
        rendered = layout.GEN.render(layout.GEN.load_inventory())
        actual = set(re.findall(r"^#define R_ADC_B0_ADEXDR(\d*)_DIAGSR_Pos ", rendered, re.MULTILINE))
        self.assertEqual({str(n) for n in DIAGNOSTIC}, actual)
        for forbidden in ("R_UIDR_NS_BASE", "R_PNR_NS_BASE", "R_MCUVER_NS_BASE"):
            self.assertNotIn("#define " + forbidden + " ", rendered)

    def test_native_literal_layout_masks_and_bitfield_bytes_both_cores(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("Native C compiler unavailable")
        with disposable_header() as folder:
            for core in (0, 1):
                for nonsecure in (0, 1):
                    with self.subTest(core=core, nonsecure=nonsecure):
                        executable = folder / "literal-layout"
                        layout.run([compiler, *native_flags(folder, core, nonsecure), FIXTURE, "-o", executable])
                        layout.run([executable])

    def test_arm_cm85_cm33_literal_layout_masks_and_bitfield_bytes_stock_cmsis(self):
        compiler = os.environ.get("RA8P1_ARM_CC") or shutil.which("arm-none-eabi-gcc")
        if not compiler:
            self.skipTest("No Arm GCC (set RA8P1_ARM_CC)")
        archive = ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip"
        if not archive.is_file():
            self.skipTest("Preserved FSP5.9 CMSIS archive unavailable")
        with disposable_header() as folder:
            cmsis = folder / "cmsis"
            prefix = "ra/arm/CMSIS_6/CMSIS/Core/Include/"
            with zipfile.ZipFile(archive) as release:
                with zipfile.ZipFile(io.BytesIO(release.read(
                        "internal/projectgen/ra/packs/Arm.CMSIS6.6.1.0+fsp.5.9.0.pack"))) as pack:
                    for name in pack.namelist():
                        if name.startswith(prefix) and not name.endswith("/"):
                            relative = Path(name[len(prefix):])
                            self.assertFalse(relative.is_absolute() or ".." in relative.parts)
                            target = cmsis / relative
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_bytes(pack.read(name))
            for core, cpu, fpu in ((0, "cortex-m85", "fpv5-d16"), (1, "cortex-m33", "fpv5-sp-d16")):
                for nonsecure in (0, 1):
                    with self.subTest(core=core, nonsecure=nonsecure):
                        obj = folder / "literal-layout.o"
                        layout.run([compiler, "-std=c11", "-ffreestanding", "-Wall", "-Wextra", "-Werror",
                                    f"-mcpu={cpu}", "-mthumb", f"-mfpu={fpu}", "-mfloat-abi=hard",
                                    f"-DBSP_CFG_CPU_CORE={core}", f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}",
                                    "-I", folder, "-I", cmsis, "-I", layout.BSP, "-c", FIXTURE, "-o", obj])
                        sections = layout.elf_sections(obj)
                        for index in DIAGNOSTIC:
                            self.assertEqual(b"\xff\xff\x00\x87", sections[f".analog.diag{index}"])
                        self.assertEqual(b"\x03", sections[".analog.mwm"])

    def test_negative_diagnostic_fields_and_read_only_writes_rejected(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("Native C compiler unavailable")
        cases = [(f"ADEXDR{n}", f"(void) ((R_ADC_B0_Type *) 0)->ADEXDR{n}_b.DIAGSR;")
                 for n in (*RESERVED, *NON_DIAGNOSTIC, 23)]
        cases += [("DIAGSR", "(void) ((R_ADC_B0_Type *) 0)->ADEXDR_b[0].DIAGSR;")]
        for n in range(4):
            cases.extend([(f"UIDR{n}", f"R_UIDR->UIDR{n} = 0U;"),
                          (f"PNR{n}", f"R_PNR->PNR{n} = 0U;")])
        cases.extend([("MCUVER", "R_MCUVER->MCUVER = 0U;"),
                      ("DIAGSR", "((R_ADC_B0_Type *) 0)->ADEXDR0_b.DIAGSR = 0U;")])
        with disposable_header() as folder:
            flags = [str(x) for x in native_flags(folder)]
            for name, statement in cases:
                with self.subTest(rejected=name):
                    source = '#include "R7KA8P1KF.h"\nvoid negative(void) { ' + statement + ' }\n'
                    result = subprocess.run([compiler, *flags, "-fsyntax-only", "-x", "c", "-"],
                                            input=source, capture_output=True, text=True, timeout=30)
                    self.assertNotEqual(0, result.returncode, f"Unexpectedly accepted: {statement}")
                    self.assertIn(name, result.stderr)

    def test_mwmcr_remains_writable(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("Native C compiler unavailable")
        with disposable_header() as folder:
            source = folder / "writable.c"
            source.write_text('#include "R7KA8P1KF.h"\nvoid writable(void) { '
                              'R_SYSTEM->MWMCR = 0U; R_SYSC->MWMCR_b.MWM = 1U; }\n')
            layout.run([compiler, *native_flags(folder), "-fsyntax-only", source])


if __name__ == "__main__":
    unittest.main()
