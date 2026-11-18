"""SEC-005: CPU0 consumes the upper external-IRQ attribution policy.

Primary oracle: RA8P1 HM Rev1.30 11.2.4 p443: DPFSAR1 at SYSC+0x3e8
is a 32-bit register, bits0..15 attribute IRQ16..31, zero=Secure.
The fragment test checks actual owning assignment execution and legacy
preprocessing; physical security faults and the entire startup need integration.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "baseline/ra/fsp/src/bsp/mcu/all/bsp_security.c"


def attribution_fragment(text):
    start = text.index("  #ifdef BSP_TZ_CFG_DPFSAR\n")
    end = text.index("  #ifdef BSP_TZ_CFG_RSCSAR\n", start)
    return text[start:end]


class SecurityAttributionTests(unittest.TestCase):
    def setUp(self):
        self.cc = shutil.which("cc")
        self.assertIsNotNone(self.cc, "A native compiler is required")
        self.fragment = attribution_fragment(SOURCE.read_text())

    def test_upper_irq_policy_is_consumed_for_target_only(self):
        self.assertIn("R_SYSTEM->DPFSAR1 = BSP_TZ_CFG_DPFSAR1", self.fragment)
        template = r'''
#include <stdint.h>
#include <assert.h>
static struct { volatile uint32_t DPFSAR, DPFSAR1; } regs;
#define R_SYSTEM (&regs)
#define BSP_TZ_CFG_DPFSAR 0x00001234U
#define BSP_TZ_CFG_DPFSAR1 POLICY
static void initialize(void) {
FRAGMENT
}
int main(void) {
    regs.DPFSAR1 = 0xA55AU;
    initialize();
    assert(regs.DPFSAR == 0x1234U);
#if BSP_FEATURE_BSP_HAS_SECONDARY_CORE
    assert(regs.DPFSAR1 == POLICY);
#else
    assert(regs.DPFSAR1 == 0xA55AU);
#endif
    return 0;
}
'''.replace("FRAGMENT", self.fragment)
        with tempfile.TemporaryDirectory(prefix="review-security-") as tmp:
            src, exe = Path(tmp) / "check.c", Path(tmp) / "check"
            src.write_text(template)
            for target in (0, 1):
                for policy in (0, 1, 0x8000, 0xFFFF):
                    built = subprocess.run([self.cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                                            f"-DBSP_FEATURE_BSP_HAS_SECONDARY_CORE={target}",
                                            f"-DPOLICY={policy}U", str(src), "-o", str(exe)],
                                           capture_output=True, text=True, timeout=30)
                    self.assertEqual(0, built.returncode, built.stderr)
                    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(0, result.returncode, (target, policy, result.stderr))

    def test_both_dma_banks_consume_authoritative_cpu0_policy(self):
        text = SOURCE.read_text()
        start = text.index("  #ifdef BSP_TZ_CFG_DMACCHSAR\n")
        end = text.index("  #ifdef BSP_TZ_CFG_ICUSARD\n", start)
        fragment = text[start:end]
        self.assertIn("R_CPSCU->DMACCHSAR = BSP_TZ_CFG_DMACCHSAR", fragment)
        # HM16.3.1.1 p698 and17.2.1 pp739-740: two byte-wide banks at0 and16.
        policy = 0x00550081
        program = ('#include <stdint.h>\n#include <assert.h>\n'
                   'static struct { volatile uint32_t DMACCHSAR; } regs;\n'
                   '#define R_CPSCU (&regs)\n'
                   f'#define BSP_TZ_CFG_DMACCHSAR 0x{policy:08X}U\n'
                   '#define DMACX_REGISTER_SHIFT 0\n'
                   'int main(void) { regs.DMACCHSAR = 0x00FF00FFU;\n' + fragment +
                   '\n#if BSP_FEATURE_BSP_HAS_SECONDARY_CORE\n'
                   f'assert(regs.DMACCHSAR == 0x{policy:08X}U);\n'
                   '#else\nassert(regs.DMACCHSAR == 0x00FF00FFU);\n#endif\nreturn 0; }\n')
        with tempfile.TemporaryDirectory(prefix="review-dma-policy-") as tmp:
            src, exe = Path(tmp) / "check.c", Path(tmp) / "check"
            src.write_text(program)
            for target in (0, 1):
                built = subprocess.run([self.cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                                        f"-DBSP_FEATURE_BSP_HAS_SECONDARY_CORE={target}", str(src), "-o", str(exe)],
                                       capture_output=True, text=True, timeout=30)
                self.assertEqual(0, built.returncode, built.stderr)
                result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
                self.assertEqual(0, result.returncode, result.stderr)

    def test_legacy_preprocessed_fragment_is_unchanged(self):
        original = subprocess.run(["git", "-C", str(ROOT / "baseline"), "show",
                                   "HEAD:ra/fsp/src/bsp/mcu/all/bsp_security.c"],
                                  check=True, capture_output=True, text=True).stdout
        before = attribution_fragment(original)
        def preprocess(fragment):
            result = subprocess.run([self.cc, "-E", "-P", "-x", "c", "-",
                                     "-DBSP_FEATURE_BSP_HAS_SECONDARY_CORE=0", "-DBSP_TZ_CFG_DPFSAR=0x1234U"],
                                    input=fragment, capture_output=True, text=True, timeout=20)
            self.assertEqual(0, result.returncode, result.stderr)
            return result.stdout
        self.assertEqual(preprocess(before), preprocess(self.fragment))


class PeripheralAttributionMetadataTests(unittest.TestCase):
    def test_actual_stack_providers_drive_each_coupled_security_bit(self):
        directory = ROOT / "baseline/module_descriptions"
        fsp = ET.parse(directory / "Renesas##BSP##ra8p1##fsp####5.9.0.xml")
        content = "\n".join(n.text or "" for n in fsp.findall(".//content"))
        logical = content.replace("\\\n", " ")
        cc = shutil.which("cc")
        self.assertIsNotNone(cc)
        providers = {}
        for driver, field in (("dac_b", "channel"), ("ospi_b", "unit")):
            mdf = ET.parse(directory / f"Renesas##HAL Drivers##all##r_{driver}####5.9.0.xml")
            providers[driver] = [p.get("interface") for p in mdf.findall(".//module/provides")]
            self.assertIn(f"interface.peripheral.{driver}${{module.driver.{driver}.{field}}}", providers[driver])
        with tempfile.TemporaryDirectory(prefix="review-peripheral-security-") as tmp:
            src, exe = Path(tmp) / "check.c", Path(tmp) / "check"
            for driver, macro, bits, field in (("dac_b", "PSARD", (20, 19), "channel"),
                                               ("ospi_b", "PSARB", (16, 17), "unit")):
                definition = re.search(r"^#define BSP_TZ_CFG_" + macro + r" [^\n]+", logical, re.M)
                self.assertIsNotNone(definition)
                for owned in ((), (0,), (1,), (0, 1)):
                    counts = {}
                    for unit in owned:
                        for provide in providers[driver]:
                            name = provide.replace(f"${{module.driver.{driver}.{field}}}", str(unit))
                            counts[name] = counts.get(name, 0) + 1
                    expanded = re.sub(r"\$\{(interface\.[^}]+)\}",
                                      lambda m: str(counts.get(m[1], 0)), definition[0])
                    self.assertNotIn("${", expanded)
                    expected = sum(1 << bit for unit, bit in enumerate(bits) if unit not in owned)
                    mask = sum(1 << bit for bit in bits)
                    src.write_text('#include <stdint.h>\n' + expanded +
                                   f'\n_Static_assert((BSP_TZ_CFG_{macro} & {mask}U) == {expected}U, "Secure owner must keep access Secure");\nint main(void){{return 0;}}\n')
                    result = subprocess.run([cc, "-std=c11", "-Wall", "-Werror", str(src), "-o", str(exe)],
                                            capture_output=True, text=True, timeout=20)
                    self.assertEqual(0, result.returncode, (driver, owned, result.stderr))


if __name__ == "__main__":
    unittest.main()
