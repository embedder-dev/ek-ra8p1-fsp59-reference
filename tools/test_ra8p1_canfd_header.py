"""Compile-only RA8P1 CANFD Lite layouts from HM 42.2 and stock 5.9 names."""

import copy
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET

from ra8p1 import generate_device_header as header
from test_ra8p1_aux_header import ROOT, TOOLS, compile_source, extract_stock_cmsis
from test_ra8p1_device_header import check_source, elf_sections


INVENTORY = TOOLS / "registers_compat_canfd.json"
STOCK = ROOT / "baseline/ra/fsp/src/bsp/cmsis/Device/RENESAS/Include/R7FA8M1AH.h"
# Independent anchors: HM 42.2.2–42.2.61, pp.2717–2807.
ANCHORS = r'''
_Static_assert(sizeof(R_CANFD_CFDC_Type) == 0x10, "single-channel control");
_Static_assert(sizeof(R_CANFD_CFDC2_Type) == 0x20, "FD control extent");
_Static_assert(sizeof(R_CANFD_CFDGAFL_Type) == 0x10, "AFL rule stride");
_Static_assert(sizeof(R_CANFD_CFDTHL_Type) == 8, "history access size");
_Static_assert(sizeof(R_CANFD_CFDRM_RM_Type) == 0x4C, "RX message stride");
_Static_assert(sizeof(R_CANFD_CFDRF_Type) == 0x4C, "RX FIFO stride");
_Static_assert(sizeof(R_CANFD_CFDCF_Type) == 0x4C, "common FIFO stride");
_Static_assert(sizeof(R_CANFD_CFDTM_Type) == 0x4C, "TX message stride");
_Static_assert(sizeof(R_CANFD_CFDRM_Type) == 0x400, "RX eight-buffer page stride");
_Static_assert(sizeof(R_CANFD_Type) == 0x1120, "two RX pages only");
_Static_assert(offsetof(R_CANFD_Type, CFDGCFG) == 0x14, "global config");
_Static_assert(offsetof(R_CANFD_Type, CFDGAFLCFG0) == 0x2C, "AFL config");
_Static_assert(offsetof(R_CANFD_Type, CFDRMIEC) == 0x38, "RX message interrupt");
_Static_assert(offsetof(R_CANFD_Type, CFDRFCC[1]) == 0x40, "second RX FIFO config");
_Static_assert(offsetof(R_CANFD_Type, CFDCFCC[0]) == 0x54, "one common FIFO");
_Static_assert(offsetof(R_CANFD_Type, CFDTMC[3]) == 0x73, "four TX request bytes");
_Static_assert(offsetof(R_CANFD_Type, CFDTMSTS[3]) == 0x77, "four TX status bytes");
_Static_assert(sizeof(((R_CANFD_Type *) 0)->CFDTMC[0]) == 1, "TX control byte access");
_Static_assert(sizeof(((R_CANFD_Type *) 0)->CFDTMSTS[0]) == 1, "TX status byte access");
_Static_assert(offsetof(R_CANFD_Type, CFDTMIEC[0]) == 0x88, "TX interrupt enable");
_Static_assert(offsetof(R_CANFD_Type, CFDGTINTSTS0) == 0xA4, "TX interrupt status");
_Static_assert(offsetof(R_CANFD_Type, CFDGRSTC) == 0xD8, "software reset");
_Static_assert(offsetof(R_CANFD_Type, CFDC2[0].DCFG) == 0x100, "data-phase config");
_Static_assert(offsetof(R_CANFD_Type, CFDGAFL[15].P1) == 0x21C, "last of sixteen rules");
_Static_assert(offsetof(R_CANFD_Type, CFDRPGACC[63]) == 0x37C, "RAM-test window");
_Static_assert(offsetof(R_CANFD_Type, CFDRF[1].DF[63]) == 0x5B7, "last RX FIFO byte");
_Static_assert(offsetof(R_CANFD_Type, CFDCF[0].ID) == 0x5B8, "common FIFO message");
_Static_assert(offsetof(R_CANFD_Type, CFDTM[3].DF[63]) == 0x733, "last TX message byte");
_Static_assert(offsetof(R_CANFD_Type, CFDTHL[0].ACC0) == 0x740, "history access");
_Static_assert(offsetof(R_CANFD_Type, CFDRM[0].RM[0].ID) == 0x920, "first RX page");
_Static_assert(offsetof(R_CANFD_Type, CFDRM[1].RM[0].ID) == 0xD20, "second RX page");
_Static_assert(offsetof(R_CANFD_Type, CFDRM[1].RM[7].DF[63]) == 0xF7F, "last RX message byte");
_Static_assert(sizeof(((R_CANFD_Type *) 0)->CFDC) / sizeof(R_CANFD_CFDC_Type) == 1, "one channel per unit");
_Static_assert(sizeof(((R_CANFD_Type *) 0)->CFDTM) / sizeof(R_CANFD_CFDTM_Type) == 4, "four TX buffers");
_Static_assert(sizeof(((R_CANFD_Type *) 0)->CFDRM) / sizeof(R_CANFD_CFDRM_Type) == 2, "sixteen RX buffers");
_Static_assert(R_CANFD_CFDC_NCFG_NBRP_Msk == 0x3FFUL, "nominal prescaler");
_Static_assert(offsetof(R_CANFD_CFDC_Type, CTR) == 4, "HM42.2.3 channel control offset");
_Static_assert(R_CANFD_CFDC_CTR_BFT_Pos == 30, "target bit-flip test position");
_Static_assert(R_CANFD_CFDC_CTR_BFT_Msk == 0x40000000UL, "target bit-flip test mask");
_Static_assert(R_CANFD_CFDC_NCFG_NTSEG2_Msk == 0xFE000000UL, "nominal segment two");
_Static_assert(R_CANFD_CFDC2_DCFG_DBRP_Msk == 0xFFUL, "data-phase prescaler");
_Static_assert(R_CANFD_CFDGAFLCFG0_RNC0_Msk == 0x1F0000UL, "five-bit rule count");
_Static_assert(R_CANFD_CFDRMNB_NRXMB_Msk == 0x1FUL, "sixteen RX capacity");
_Static_assert(R_CANFD_CFDTMIEC_TMIEg_Msk == 0xFUL, "four TX interrupt bits");
_Static_assert(R_CANFD_CFDTM_ID_TMID_Msk == 0x1FFFFFFFUL, "CAN extended identifier");
_Static_assert(R_CANFD_CFDRM_RM_PTR_RMDLC_Msk == 0xF0000000UL, "RX data length");
_Static_assert(R_CANFD0_S_BASE == 0x40380000UL, "unit zero secure base");
_Static_assert(R_CANFD1_NS_BASE == 0x50382000UL, "unit one nonsecure base");
_Static_assert(R_CANFD1_BASE - R_CANFD0_BASE == 0x2000UL, "independent unit stride");
#ifdef R_CANFD
#error "The manual has two independent units, not a shared R_CANFD register bank"
#endif
'''


class CanfdHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fragment = json.loads(INVENTORY.read_text())
        cls.data = header.load_inventory()
        cls.rendered = header.render(copy.deepcopy(cls.data))
        cls.source, cls.expected = check_source(copy.deepcopy(cls.data))
        cls.source += ANCHORS

    def test_inventory_is_unique_and_uses_only_original_vocabulary(self):
        stock = STOCK.read_text()
        names = [block['name'] for block in self.data['types']]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(10, len(self.fragment['types']))
        self.assertEqual({'R_CANFD0', 'R_CANFD1'}, {item['name'] for item in self.fragment['instances']})
        target_only_fields = []
        for block in self.fragment['types']:
            end = stock.index('} ' + block['name'] + ';')
            text = stock[stock.rfind('typedef struct', 0, end):end]
            for reg in block['members']:
                self.assertRegex(text, r'\b' + reg['name'] + r'(?:\[|;)')
                if 'type' in reg:
                    self.assertRegex(text, re.escape(reg['type']) + r'\s+' + reg['name'] + r'\[')
                for field in reg.get('fields', []):
                    identity = (block['name'], reg['name'], field['name'])
                    if identity == ('R_CANFD_CFDC_Type', 'CTR', 'BFT'):
                        # HM42.2.3 adds bit-flip testing at bit 30; never alias it to CRCT.
                        self.assertEqual({'name': 'BFT', 'pos': 30, 'bits': 1, 'access': 'R/W'}, field)
                        target_only_fields.append(identity)
                        continue
                    if (block['name'], reg['name']) == ('R_CANFD_CFDGAFL_Type', 'P1'):
                        # HM42.2.22 p2750 gives separate FIFO destinations at0,1,8.
                        expected = {'GAFLFDP0': 0, 'GAFLFDP1': 1, 'GAFLFDP8': 8}
                        self.assertIn(field['name'], expected)
                        self.assertEqual({'name': field['name'], 'pos': expected[field['name']],
                                          'bits': 1, 'access': 'R/W'}, field)
                        target_only_fields.append(identity)
                        continue
                    self.assertRegex(text, r'\b' + field['name'] + r'\s*:')
                    macro = field.get('macro_name', field['name'])
                    if macro is not None:
                        self.assertRegex(stock, r'#define ' + block['name'].removesuffix('_Type') + '_'
                                         + reg['name'] + '_' + macro + r'_Pos\b')
        self.assertEqual({('R_CANFD_CFDC_Type', 'CTR', 'BFT'),
                          ('R_CANFD_CFDGAFL_Type', 'P1', 'GAFLFDP0'),
                          ('R_CANFD_CFDGAFL_Type', 'P1', 'GAFLFDP1'),
                          ('R_CANFD_CFDGAFL_Type', 'P1', 'GAFLFDP8')}, set(target_only_fields))
        self.assertEqual(4, len(target_only_fields))
        self.assertNotIn('#define R_CANFD_CFDC_CTR_CRCT_', self.rendered)
        self.assertNotIn('#define R_CANFD_CFDTM_PTR_TMTS_', self.rendered)
        self.assertNotIn('#define R_CANFD_CFDGAFLCFG0_RNC1_', self.rendered)
        self.assertNotIn('#define R_CANFD_CFDGAFLECTR_AFLPN_', self.rendered)
        self.assertNotIn('#define R_CANFD_CFDGAFL_P1_GAFLFDP_', self.rendered)

    def test_per_instance_topology_and_mdf_total_channel_count(self):
        feature = (ROOT / 'baseline/ra/fsp/src/bsp/mcu/ra8p1/bsp_feature.h').read_text()
        values = {}
        for name, expected in (('BSP_FEATURE_CANFD_NUM_CHANNELS', 1), ('BSP_FEATURE_CANFD_NUM_INSTANCES', 2)):
            matches = re.findall(r'^#define\s+' + name + r'\s+\((0x[\dA-Fa-f]+|\d+)[UL]*\)', feature, re.M)
            self.assertEqual(1, len(matches), name)
            values[name] = int(matches[0], 0)
            self.assertEqual(expected, values[name], name)
        total = values['BSP_FEATURE_CANFD_NUM_CHANNELS'] * values['BSP_FEATURE_CANFD_NUM_INSTANCES']
        self.assertEqual(2, total)
        for mcu in ('ra8p1', 'ra8m1'):
            mdf = ROOT / f'baseline/module_descriptions/Renesas##BSP##{mcu}##fsp####5.9.0.xml'
            properties = [node for node in ET.parse(mdf).iter('property')
                          if node.get('id') == 'config.bsp.fsp.mcu.canfd.num_channels']
            self.assertEqual(1, len(properties), mcu)
            self.assertEqual(total, int(properties[0].get('default'), 0), mcu)
        bases = {item['name']: (header.number(item['secure']), header.number(item['nonsecure']))
                 for item in self.fragment['instances']}
        self.assertEqual({'R_CANFD0': (0x40380000, 0x50380000),
                          'R_CANFD1': (0x40382000, 0x50382000)}, bases)

    def test_native_offsets_widths_masks_and_security_aliases(self):
        compiler = shutil.which('cc')
        if not compiler:
            self.skipTest('Native compiler unavailable')
        with tempfile.TemporaryDirectory(prefix='ra8p1-canfd-native-') as tmp:
            folder = Path(tmp)
            (folder / 'R7KA8P1KF.h').write_text(self.rendered)
            for core in (0, 1):
                for nonsecure in (0, 1):
                    with self.subTest(core=core, nonsecure=nonsecure):
                        result, command, _ = compile_source(compiler, folder, self.source, core, nonsecure,
                                                            [TOOLS / 'layout/native', TOOLS / 'layout'])
                        self.assertEqual(0, result.returncode, ' '.join(command) + '\n' + result.stderr)

    def test_arm_layout_and_bitfield_object_bytes(self):
        compiler = os.environ.get('RA8P1_ARM_CC') or shutil.which('arm-none-eabi-gcc')
        if not compiler:
            self.skipTest('Arm GCC unavailable (set RA8P1_ARM_CC)')
        with tempfile.TemporaryDirectory(prefix='ra8p1-canfd-arm-') as tmp:
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

    def test_readonly_status_and_receive_message_writes_are_rejected(self):
        compiler = shutil.which('cc')
        if not compiler:
            self.skipTest('Native compiler unavailable')
        with tempfile.TemporaryDirectory(prefix='ra8p1-canfd-readonly-') as tmp:
            folder = Path(tmp)
            (folder / 'R7KA8P1KF.h').write_text(self.rendered)
            for member in ('CFDGSTS', 'CFDGSTS_b.GRAMINIT', 'CFDRF[1].ID', 'CFDRM[1].RM[7].DF[63]',
                           'CFDTMSTS_b[0].TMTRM', 'CFDGTINTSTS0'):
                with self.subTest(member=member):
                    result, _, _ = compile_source(
                        compiler, folder, '#include "R7KA8P1KF.h"\nvoid rejected(void) { R_CANFD0->'
                        + member + ' = 0; }\n', includes=[TOOLS / 'layout/native'])
                    self.assertNotEqual(0, result.returncode)
                    self.assertRegex(result.stderr, r'read.only|const.qualified')


if __name__ == '__main__':
    unittest.main()
