"""Compile-only GLCDC/PHY stock vocabulary and manual-derived layout checks."""

import copy
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import unittest

from ra8p1 import generate_device_header as header
from test_ra8p1_aux_header import ROOT, TOOLS, compile_source, extract_stock_cmsis
from test_ra8p1_aux_peripherals_header import stock_vocabulary
from test_ra8p1_device_header import check_source, elf_sections


# Independent anchors from HM 64.2 (pp.3767–3824), 65.2 (pp.3832–3847).
ANCHORS = r'''
_Static_assert(sizeof(R_GLCDC_Type) == 0x1454, "GLCDC implemented extent");
_Static_assert(sizeof(R_GLCDC_GR_Type) == 0x100, "graphics plane stride");
_Static_assert(sizeof(R_GLCDC_GAM_Type) == 0x40, "gamma color stride");
_Static_assert(offsetof(R_GLCDC_Type, GR1_CLUT0[255]) == 0x3FC, "first palette end");
_Static_assert(offsetof(R_GLCDC_Type, GR2_CLUT1[255]) == 0xFFC, "last palette end");
_Static_assert(offsetof(R_GLCDC_Type, BG.MON) == 0x1018, "background status");
_Static_assert(offsetof(R_GLCDC_Type, GR[0].FLM2) == 0x110C, "first framebuffer base");
_Static_assert(offsetof(R_GLCDC_Type, GR[1].FLM2) == 0x120C, "second framebuffer base");
_Static_assert(offsetof(R_GLCDC_Type, GAM[0].GAM_SW) == 0x1304, "single gamma enable");
_Static_assert(offsetof(R_GLCDC_Type, GAM[1].LUT[0]) == 0x1348, "blue gamma gains");
_Static_assert(offsetof(R_GLCDC_Type, GAM[2].AREA[4]) == 0x13B8, "last red gamma threshold");
_Static_assert(offsetof(R_GLCDC_Type, OUT.CLKPHASE) == 0x13E4, "output phase");
_Static_assert(offsetof(R_GLCDC_Type, TCON.STHB2) == 0x1424, "last horizontal timing");
_Static_assert(offsetof(R_GLCDC_Type, SYSCNT.PANEL_CLK) == 0x1450, "panel clock and version");
_Static_assert(R_GLCDC_BG_EN_VEN_Msk == 0x100UL, "background latch");
_Static_assert(R_GLCDC_GR_FLM6_FORMAT_Msk == 0x70000000UL, "pixel format");
_Static_assert(R_GLCDC_GR_AB6_ARCCOEF_Msk == 0x1FF0000UL, "alpha coefficient");
_Static_assert(R_GLCDC_SYSCNT_PANEL_CLK_CLKSEL_Msk == 0x100UL, "LCD clock source");
_Static_assert(R_GLCDC_SYSCNT_PANEL_CLK_VER_Msk == 0xFFFF0000UL, "read-only version");
_Static_assert(R_GLCDC_S_BASE == 0x40342000UL, "GLCDC secure base");
_Static_assert(R_GLCDC_NS_BASE == 0x50342000UL, "GLCDC nonsecure base");
_Static_assert(sizeof(R_DPHYCNT_Type) == 0x4C, "D-PHY implemented extent");
_Static_assert(offsetof(R_DPHYCNT_Type, DPHYPWRCR) == 0x10, "power control");
_Static_assert(offsetof(R_DPHYCNT_Type, DPHYSFR) == 0x1C, "PHY power and PLL status");
_Static_assert(offsetof(R_DPHYCNT_Type, DPHYTIM1) == 0x24, "initialization timing");
_Static_assert(offsetof(R_DPHYCNT_Type, DPHYTIM6) == 0x38, "LP timing");
_Static_assert(offsetof(R_DPHYCNT_Type, DPHYMDC) == 0x48, "master mode control");
_Static_assert(R_DPHYCNT_DPHYPLFCR_NMUL_Msk == 0x1FF0000UL, "PLL integer multiplier");
_Static_assert(R_DPHYCNT_DPHYTIM1_TINIT_Msk == 0x7FFFFUL, "initialization cycles");
_Static_assert(R_DPHYCNT_DPHYSFR_PLLSF_Msk == 0x100UL, "PLL stable flag");
_Static_assert(R_DPHYCNT_S_BASE == 0x40346C00UL, "PHY secure base");
_Static_assert(R_DPHYCNT_NS_BASE == 0x50346C00UL, "PHY nonsecure base");
'''


class DisplayHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fragments = [json.loads((TOOLS / name).read_text()) for name in
                         ('registers_compat_glcdc.json', 'registers_compat_mipi_phy.json')]
        cls.data = header.load_inventory()
        cls.rendered = header.render(copy.deepcopy(cls.data))
        cls.source, cls.expected = check_source(copy.deepcopy(cls.data))
        cls.source += ANCHORS

    def test_original_vocabulary_and_documented_restrictions(self):
        for fragment in self.fragments:
            for block in fragment['types']:
                stock = stock_vocabulary(block['name'])
                for reg in block['members']:
                    if 'type' in reg:
                        continue
                    self.assertIn(reg['name'], stock)
                    self.assertLessEqual({field['name'] for field in reg['fields']}, stock[reg['name']])
        gamma = next(block for block in self.fragments[0]['types'] if block['name'] == 'R_GLCDC_GAM_Type')
        self.assertIn('only for GAM[0]', next(reg['source'] for reg in gamma['members'] if reg['name'] == 'GAM_SW'))
        for module, instance in (('r_glcdc', 'R_GLCDC'), ('r_mipi_phy', 'R_DPHYCNT')):
            driver = (ROOT / f'baseline/ra/fsp/src/{module}/{module}.c').read_text()
            for macro in re.findall(r'\b' + instance + r'_\w+_(?:Pos|Msk)\b', driver):
                self.assertIn('#define ' + macro + ' ', self.rendered)

    def test_native_layout_and_stock_register_access_expressions(self):
        compiler = shutil.which('cc')
        if not compiler:
            self.skipTest('Native compiler unavailable')
        source = self.source
        for module, instance in (('r_glcdc', 'R_GLCDC'), ('r_mipi_phy', 'R_DPHYCNT')):
            driver = (ROOT / f'baseline/ra/fsp/src/{module}/{module}.c').read_text()
            accesses = set(re.findall(instance + r'->((?:\w+(?:\[[^\]]+\])?\.)*\w+)', driver))
            source += f'\nvoid {module}_vocabulary(void) {{\n'
            for access in sorted(accesses):
                access = re.sub(r'\[[^\]]+\]', '[0]', access)
                source += '    (void) (' + instance + '->' + access + ');\n'
            source += '}\n'
        with tempfile.TemporaryDirectory(prefix='ra8p1-display-native-') as tmp:
            folder = Path(tmp)
            (folder / 'R7KA8P1KF.h').write_text(self.rendered)
            for core in (0, 1):
                for nonsecure in (0, 1):
                    with self.subTest(core=core, nonsecure=nonsecure):
                        result, command, _ = compile_source(compiler, folder, source, core, nonsecure,
                                                            [TOOLS / 'layout/native', TOOLS / 'layout'])
                        self.assertEqual(0, result.returncode, ' '.join(command) + '\n' + result.stderr)

    def test_arm_layout_and_bitfield_bytes_both_cores_and_security_aliases(self):
        compiler = os.environ.get('RA8P1_ARM_CC') or shutil.which('arm-none-eabi-gcc')
        if not compiler:
            self.skipTest('Arm GCC unavailable (set RA8P1_ARM_CC)')
        with tempfile.TemporaryDirectory(prefix='ra8p1-display-arm-') as tmp:
            folder = Path(tmp)
            (folder / 'R7KA8P1KF.h').write_text(self.rendered)
            cmsis = folder / 'cmsis'
            extract_stock_cmsis(cmsis)
            for core in (0, 1):
                cpu, fpu = ('cortex-m85', 'fpv5-d16') if core == 0 else ('cortex-m33', 'fpv5-sp-d16')
                for nonsecure in (0, 1):
                    with self.subTest(core=core, nonsecure=nonsecure):
                        result, command, obj = compile_source(
                            compiler, folder, self.source, core, nonsecure, [cmsis, TOOLS / 'layout'],
                            [f'-mcpu={cpu}', '-mthumb', f'-mfpu={fpu}', '-mfloat-abi=hard'])
                        self.assertEqual(0, result.returncode, ' '.join(command) + '\n' + result.stderr)
                        actual = elf_sections(obj)
                        for section, expected in self.expected.items():
                            self.assertEqual(expected, actual[section], section)

    def test_status_writes_rejected(self):
        compiler = shutil.which('cc')
        if not compiler:
            self.skipTest('Native compiler unavailable')
        with tempfile.TemporaryDirectory(prefix='ra8p1-display-readonly-') as tmp:
            folder = Path(tmp)
            (folder / 'R7KA8P1KF.h').write_text(self.rendered)
            for instance, member in (('R_GLCDC', 'BG.MON'), ('R_GLCDC', 'GR[1].MON_b.UNDFLST'),
                                     ('R_GLCDC', 'SYSCNT.PANEL_CLK_b.VER'), ('R_DPHYCNT', 'DPHYSFR')):
                with self.subTest(instance=instance, member=member):
                    result, _, _ = compile_source(
                        compiler, folder, '#include "R7KA8P1KF.h"\nvoid rejected(void) { '
                        + instance + '->' + member + ' = 0; }\n', includes=[TOOLS / 'layout/native'])
                    self.assertNotEqual(0, result.returncode)
                    self.assertRegex(result.stderr, r'read.only|const.qualified')


if __name__ == '__main__':
    unittest.main()
