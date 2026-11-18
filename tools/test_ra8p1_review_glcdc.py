"""GLCDC-001..013: HM64 pp3767-3828, 66.3.6.1 p3931 production-C oracles.

The full production TU and real instance/API/device headers execute natively.
Only constant-address static initializers are rebound to fixture storage;
every runtime R_GLCDC access is observed for ordering and monitor fault injection.
No e2, generated projects, pack installation or physical target operations.
"""
import itertools
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "baseline"
FSP = BASE / "ra/fsp"
SOURCE = FSP / "src/r_glcdc/r_glcdc.c"
FIX = ROOT / "tools/ra8p1/review_glcdc"


def observed(text):
    text = text.replace("&(R_GLCDC->TCON.", "&(review_regs.TCON.")
    text = text.replace("{R_GLCDC->GR1_CLUT0, R_GLCDC->GR2_CLUT0}",
                        "{review_regs.GR1_CLUT0, review_regs.GR2_CLUT0}")
    return text


def sections(path):
    """Executable, data/rodata, relocation and symbol sections of native Mach-O/ELF.

    Compare symbol tables too so byte-identical relocations cannot refer to
    different targets. Debug/build-path bookkeeping is deliberately excluded.
    """
    b = path.read_bytes()
    result = {}
    if b[:4] == b"\xcf\xfa\xed\xfe":
        off = 32
        for _ in range(struct.unpack_from("<I", b, 16)[0]):
            kind, length = struct.unpack_from("<II", b, off)
            if kind == 0x19:
                for i in range(struct.unpack_from("<I", b, off + 64)[0]):
                    s = struct.unpack_from("<16s16sQQIIIIIIII", b, off + 72 + 80 * i)
                    name, seg, _, size, start, _, reloc, nreloc = s[:8]
                    if name.rstrip(b"\0") not in (b"__compact_unwind",):
                        result[(seg, name)] = (b[start:start+size], b[reloc:reloc+8*nreloc])
            if kind == 2:
                sym, n, strings, size = struct.unpack_from("<IIII", b, off+8)
                result["symbols"] = b[sym:sym+16*n], b[strings:strings+size]
            off += length
    elif b[:5] == b"\x7fELF\x02":
        h = struct.unpack_from("<HHIQQQIHHHHHH", b, 16)
        ss = [struct.unpack_from("<IIQQQQIIQQ", b, h[5]+i*h[10]) for i in range(h[11])]
        ns = ss[h[12]]
        names = b[ns[4]:ns[4]+ns[5]]
        for s in ss:
            name = names[s[0]:].split(b"\0", 1)[0]
            if s[2] & 2 or s[1] in (2, 4, 9) or name == b".strtab":
                result[name] = b[s[4]:s[4]+s[5]]
    else:
        raise AssertionError("unsupported object format")
    return result


class GlcdcReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("clang")
        if not cls.cc:
            raise RuntimeError("Clang required")
        cls.temp = tempfile.TemporaryDirectory(prefix="review-glcdc-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.tmp = Path(cls.temp.name)
        core = "#define __IM volatile const\n#define __OM volatile\n#define __IOM volatile\n"
        for f in ("core_cm85.h", "core_cm33.h", "core_cm4.h"):
            (cls.tmp / f).write_text(core)
        for f in ("system.h", "r_glcdc_cfg.h", "r_mipi_dsi_cfg.h", "r_mipi_phy_cfg.h"):
            (cls.tmp / f).write_text("")
        cls.original = subprocess.check_output(["git", "-C", str(BASE), "show",
            "5e8fbb10c752e16272790bd3a2587485d0377835:ra/fsp/src/r_glcdc/r_glcdc.c"], text=True)
        cls.binaries = {}

    def command(self, checks, core=0, color=1, legacy=0, object_only=False, dsi=1):
        return [self.cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-pointer-to-int-cast",
            "-Wno-unused-parameter", "-O2", "-I"+str(FIX), "-I"+str(self.tmp),
            "-I"+str(FSP/"inc"), "-I"+str(FSP/"inc/api"), "-I"+str(FSP/"inc/instances"),
            "-I"+str(FSP/"src/bsp/mcu/all"),
            "-I"+str(FSP/"src/bsp/cmsis/Device/RENESAS/Include"),
            f"-DBSP_CFG_CPU_CORE={core}", f"-DTEST_LEGACY={legacy}",
            f"-DTEST_OBJECT={int(object_only)}", f"-DGLCDC_CFG_PARAM_CHECKING_ENABLE={checks}",
            f"-DGLCDC_CFG_COLOR_CORRECTION_ENABLE={color}",
            f"-DBSP_FEATURE_GLCDC_HAS_GLOBAL_GAMMA_SWITCH={int(not legacy)}"] + (
                ["-DGLCDC_CFG_USING_DSI=1"] if dsi else [])

    def run_ok(self, cmd):
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        self.assertEqual(0, p.returncode, p.stdout+p.stderr)
        return p

    def binary(self, checks, core=0, color=1, original=False, dsi=1):
        key = checks, core, color, original, dsi
        if key not in self.binaries:
            path = self.tmp / "driver.c"
            path.write_text(observed(self.original if original else SOURCE.read_text()))
            out = self.tmp / ("glcdc-"+"-".join(map(str, key)))
            self.run_ok(self.command(checks, core, color, dsi=dsi) + ["-fsanitize=undefined",
                "-fno-sanitize-recover=all", str(path), str(FIX/"fixture.c"), "-o", str(out)])
            self.binaries[key] = out
        return self.binaries[key]

    def test_hm_contracts_both_cores_checks_and_color_on_off(self):
        for checks, core, color, dsi in itertools.product((0, 1), repeat=4):
            binary = self.binary(checks, core, color, dsi=dsi)
            for scenario in range(17):
                if (not color and scenario == 0) or (not dsi and scenario == 4):
                    continue
                with self.subTest(checks=checks, core=core, color=color, dsi=dsi, scenario=scenario):
                    self.run_ok([str(binary), str(scenario)])

    def test_pristine_production_fails_independent_oracles(self):
        for scenario in range(17):
            if scenario == 11:
                checks = 1
            else:
                checks = 0
            with self.subTest(scenario=scenario):
                p = subprocess.run([str(self.binary(checks, original=True)), str(scenario)],
                                   capture_output=True, text=True, timeout=10)
                self.assertNotEqual(0, p.returncode, "Pristine unexpectedly passed "+str(scenario))
                self.assertRegex(p.stderr, r"Assertion|runtime error:")

    def test_legacy_full_translation_unit_code_data_relocations_unchanged(self):
        for checks, color, legacy, dsi in itertools.product((0, 1), (0, 1), (1, 2), (0, 1)):
            images = []
            for text in (self.original, SOURCE.read_text()):
                path = self.tmp / "driver.c"
                path.write_text(text)
                out = self.tmp / "driver.o"
                self.run_ok(self.command(checks, color=color, legacy=legacy, object_only=True, dsi=dsi)+
                            ["-c", str(path), "-o", str(out)])
                images.append(sections(out))
            with self.subTest(checks=checks, color=color, legacy=legacy, dsi=dsi):
                self.assertEqual(*images)

    def test_crlf_and_only_existing_target_gate(self):
        b = SOURCE.read_bytes()
        self.assertEqual(b.count(b"\n"), b.count(b"\r\n"))
        self.assertNotIn("BSP_MCU_GROUP_RA8P1", b.decode())


if __name__ == "__main__":
    unittest.main()
