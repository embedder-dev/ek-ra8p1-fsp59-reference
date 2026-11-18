"""Manual-derived DSI layout, ACK bitmap and original FSP5.9 vocabulary checks."""

import copy
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import unittest

from ra8p1 import generate_device_header as header
from ra8p1.compatibility import original_sources
from test_ra8p1_aux_header import ROOT, TOOLS, compile_source, extract_stock_cmsis
from test_ra8p1_aux_peripherals_header import stock_vocabulary
from test_ra8p1_device_header import check_source, elf_sections


INVENTORY = TOOLS / 'registers_compat_mipi_dsi.json'
STOCK = ROOT / 'baseline/ra/fsp/src/bsp/cmsis/Device/RENESAS/Include/R7FA8D1BH.h'
# Independent anchors from HM 66.2 (pp.3849–3924); AVC bitmap from 66.2.21–22.
ANCHORS = r'''
_Static_assert(sizeof(R_DSILINK_Type) == 0x880, "DSI descriptor-bank extent");
_Static_assert(_Alignof(R_DSILINK_Type) == 4, "DSI word access");
_Static_assert(offsetof(R_DSILINK_Type, ISR) == 0x000, "interrupt status");
_Static_assert(offsetof(R_DSILINK_Type, LINKSR) == 0x010, "link status");
_Static_assert(offsetof(R_DSILINK_Type, TXSETR) == 0x100, "TX setting");
_Static_assert(offsetof(R_DSILINK_Type, RSTSR) == 0x114, "reset status");
_Static_assert(offsetof(R_DSILINK_Type, DSISETR) == 0x120, "DSI operation setting");
_Static_assert(offsetof(R_DSILINK_Type, TXPPD3R) == 0x16C, "last transmit payload word");
_Static_assert(offsetof(R_DSILINK_Type, RXSR) == 0x200, "receive status");
_Static_assert(offsetof(R_DSILINK_Type, AKEPLATIR) == 0x220, "latest ACK report");
_Static_assert(offsetof(R_DSILINK_Type, AKEPACMSR) == 0x224, "accumulated ACK report");
_Static_assert(offsetof(R_DSILINK_Type, AKEPSCR) == 0x228, "ACK clear");
_Static_assert(offsetof(R_DSILINK_Type, RXRSS0R) == 0x240, "first result slot");
_Static_assert(offsetof(R_DSILINK_Type, RXRSS3R) == 0x24C, "fourth result slot");
_Static_assert(offsetof(R_DSILINK_Type, RXPPD3R) == 0x2CC, "last receive payload word");
_Static_assert(offsetof(R_DSILINK_Type, HSTXTOSETR) == 0x2E0, "HS transmit timeout");
_Static_assert(offsetof(R_DSILINK_Type, PLIER) == 0x328, "physical-lane interrupt enable");
_Static_assert(offsetof(R_DSILINK_Type, VMSET0R) == 0x400, "video setting");
_Static_assert(offsetof(R_DSILINK_Type, VMHPSETR) == 0x434, "video horizontal porch");
_Static_assert(offsetof(R_DSILINK_Type, SQCH0SET0R) == 0x5C0, "sequence-zero setting");
_Static_assert(offsetof(R_DSILINK_Type, SQCH1IER) == 0x618, "sequence-one interrupt enable");
_Static_assert(offsetof(R_DSILINK_Type, SQCH0DSC0AR) == 0x780, "first descriptor header");
_Static_assert(offsetof(R_DSILINK_Type, SQCH0DSC7DR) == 0x7FC, "last channel-zero descriptor");
_Static_assert(offsetof(R_DSILINK_Type, SQCH1DSC0AR) == 0x800, "first channel-one descriptor");
_Static_assert(offsetof(R_DSILINK_Type, SQCH1DSC7DR) == 0x87C, "last descriptor address");
_Static_assert(R_DSILINK_SQCH0DSC0AR_DT_Msk == 0x3F0000UL, "packet data type");
_Static_assert(R_DSILINK_SQCH0DSC0AR_VC_Msk == 0xC00000UL, "packet virtual-channel ID");
_Static_assert(R_DSILINK_SQCH0DSC0AR_NXACT_Msk == 0x30000000UL, "descriptor next action");
_Static_assert(R_DSILINK_RXRSS3R_INFOOW_Msk == 0x80000000UL, "result overwrite flag");
_Static_assert(R_DSILINK_AKEPACMSR_AEREP_Msk == 0xFFFFUL, "accumulated error report");
_Static_assert(R_DSILINK_AKEPACMSR_AVC_Pos == 16, "AVC0 first flag");
_Static_assert(R_DSILINK_AKEPACMSR_AVC_Msk == 0xF0000UL, "AVC0 through AVC3 bitmap");
_Static_assert(R_DSILINK_AKEPSCR_AVC_Pos == 16, "AVC0 clear flag");
_Static_assert(R_DSILINK_AKEPSCR_AVC_Msk == 0xF0000UL, "AVC0 through AVC3 clear bitmap");
_Static_assert(R_DSILINK_S_BASE == 0x40346000UL, "DSI secure base");
_Static_assert(R_DSILINK_NS_BASE == 0x50346000UL, "DSI nonsecure base");
#ifdef __ELF__
__attribute__((section(".dsi.ack.status"), used))
#endif
const __typeof__(((R_DSILINK_Type *) 0)->AKEPACMSR_b) ack_status_flags[] = {
    { .AVC = 1 }, { .AVC = 2 }, { .AVC = 4 }, { .AVC = 8 }, { .AEREP = 0xFFFF, .AVC = 15 }
};
#ifdef __ELF__
__attribute__((section(".dsi.ack.clear"), used))
#endif
const __typeof__(((R_DSILINK_Type *) 0)->AKEPSCR_b) ack_clear_flags[] = {
    { .AVC = 1 }, { .AVC = 2 }, { .AVC = 4 }, { .AVC = 8 }, { .AEREP = 0xFFFF, .AVC = 15 }
};
'''
ACK_BYTES = b''.join(value.to_bytes(4, 'little') for value in (0x10000, 0x20000, 0x40000, 0x80000, 0xFFFFF))


class MipiDsiHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fragment = json.loads(INVENTORY.read_text())
        cls.data = header.load_inventory()
        cls.rendered = header.render(copy.deepcopy(cls.data))
        cls.source, cls.expected = check_source(copy.deepcopy(cls.data))
        cls.source += ANCHORS
        cls.expected['.dsi.ack.status'] = ACK_BYTES
        cls.expected['.dsi.ack.clear'] = ACK_BYTES

    def test_original_word_register_vocabulary_and_manual_access_widths(self):
        self.assertEqual(['R_DSILINK_Type'], [block['name'] for block in self.fragment['types']])
        self.assertEqual(['R_DSILINK'], [item['name'] for item in self.fragment['instances']])
        block = self.fragment['types'][0]
        self.assertEqual(127, len(block['members']))
        stock = stock_vocabulary(block['name'])
        stock_text = STOCK.read_text()
        for reg in block['members']:
            with self.subTest(register=reg['name']):
                self.assertEqual(32, reg['width'])
                self.assertFalse(reg.get('aliases'))
                self.assertFalse(reg.get('views'))
                self.assertIn(reg['name'], stock)
                self.assertLessEqual({field['name'] for field in reg['fields']}, stock[reg['name']])
                for field in reg['fields']:
                    self.assertRegex(stock_text, r'#define R_DSILINK_' + reg['name'] + '_' + field['name'] + r'_Pos\b')
        for name, access in (('AKEPACMSR', 'R'), ('AKEPSCR', 'W')):
            reg = next(reg for reg in block['members'] if reg['name'] == name)
            self.assertEqual(access, reg['access'])
            self.assertEqual([('AEREP', 0, 16, access), ('AVC', 16, 4, access)],
                             [(f['name'], f['pos'], f['bits'], f['access']) for f in reg['fields']])
            self.assertIn('AVC0', reg['note'])
            self.assertIn('AVC3', reg['note'])

    def test_target_reserved_clear_bits_have_no_legacy_aliases(self):
        members = {reg['name']: reg for reg in self.fragment['types'][0]['members']}
        reserved = {'RXSCR': (13,), 'SQCH0SCR': (16, 19), 'SQCH1SCR': (16,)}
        for name, positions in reserved.items():
            occupied = sum(((1 << field['bits']) - 1) << field['pos'] for field in members[name]['fields'])
            for bit in positions:
                with self.subTest(register=name, bit=bit):
                    self.assertEqual(0, occupied & (1 << bit))
        for name, field in (('RXSCR', 'RXTE'), ('SQCH0SCR', 'DABORT'),
                            ('SQCH0SCR', 'SIZEERR'), ('SQCH1SCR', 'DABORT')):
            self.assertNotIn(field, {item['name'] for item in members[name]['fields']})
            for suffix in ('Pos', 'Msk'):
                self.assertNotIn('#define R_DSILINK_' + name + '_' + field + '_' + suffix + ' ', self.rendered)
        sizeerr = next(field for field in members['SQCH1SCR']['fields'] if field['name'] == 'SIZEERR')
        self.assertEqual((19, 1, 'W'), (sizeerr['pos'], sizeerr['bits'], sizeerr['access']))

    def test_original_hal_mask_and_register_access_vocabulary(self):
        paths = ('ra/fsp/src/r_mipi_dsi/r_mipi_dsi.c',
                 'ra/fsp/inc/instances/r_mipi_dsi.h')
        stock = original_sources(ROOT)
        driver = '\n'.join(stock[path].decode() for path in paths)
        required = set(re.findall(r'\bR_DSILINK_\w+_(?:Pos|Msk)\b', driver))
        self.assertEqual(151, len(required))
        # These stock RA8D1 clear bits are reserved in RA8P1 HM 66.2.15/55/59.
        unsupported = {
            'R_DSILINK_RXSCR_RXTE_Msk',
            'R_DSILINK_SQCH0SCR_DABORT_Msk',
            'R_DSILINK_SQCH0SCR_SIZEERR_Msk',
            'R_DSILINK_SQCH1SCR_DABORT_Msk',
        }
        missing = {macro for macro in required if '#define ' + macro + ' ' not in self.rendered}
        self.assertEqual(unsupported, missing)
        for macro in unsupported:
            self.assertNotIn('#define ' + macro + ' ', self.rendered)
        accesses = sorted(set(re.findall(r'R_DSILINK->(\w+(?:\.\w+)?)', driver)))
        source = self.source + '\nvoid stock_dsi_access_vocabulary(void) {\n'
        source += ''.join('    (void) (R_DSILINK->' + member + ');\n' for member in accesses) + '}\n'
        compiler = shutil.which('cc')
        if not compiler:
            self.skipTest('Native compiler unavailable')
        with tempfile.TemporaryDirectory(prefix='ra8p1-dsi-native-') as tmp:
            folder = Path(tmp)
            (folder / 'R7KA8P1KF.h').write_text(self.rendered)
            for core in (0, 1):
                for nonsecure in (0, 1):
                    with self.subTest(core=core, nonsecure=nonsecure):
                        result, command, _ = compile_source(compiler, folder, source, core, nonsecure,
                                                            [TOOLS / 'layout/native', TOOLS / 'layout'])
                        self.assertEqual(0, result.returncode, ' '.join(command) + '\n' + result.stderr)

    def test_arm_layout_and_ack_flags_both_cores_and_security_aliases(self):
        compiler = os.environ.get('RA8P1_ARM_CC') or shutil.which('arm-none-eabi-gcc')
        if not compiler:
            self.skipTest('Arm GCC unavailable (set RA8P1_ARM_CC)')
        with tempfile.TemporaryDirectory(prefix='ra8p1-dsi-arm-') as tmp:
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

    def test_readonly_status_and_ack_accumulation_reject_writes(self):
        compiler = shutil.which('cc')
        if not compiler:
            self.skipTest('Native compiler unavailable')
        with tempfile.TemporaryDirectory(prefix='ra8p1-dsi-readonly-') as tmp:
            folder = Path(tmp)
            (folder / 'R7KA8P1KF.h').write_text(self.rendered)
            for member in ('ISR', 'LINKSR', 'RSTSR', 'AKEPLATIR', 'AKEPACMSR', 'AKEPACMSR_b.AVC',
                           'RXRSS3R', 'RXPPD3R', 'PLSR'):
                with self.subTest(member=member):
                    result, _, _ = compile_source(
                        compiler, folder, '#include "R7KA8P1KF.h"\nvoid rejected(void) { R_DSILINK->'
                        + member + ' = 0; }\n', includes=[TOOLS / 'layout/native'])
                    self.assertNotEqual(0, result.returncode)
                    self.assertRegex(result.stderr, r'read.only|const.qualified')


if __name__ == '__main__':
    unittest.main()
