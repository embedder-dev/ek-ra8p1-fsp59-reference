"""Owning-header integration and independent canonical-layout/admission checks.

Numeric anchors are from HM Rev1.30 §§9.2.49–58,13.2,23.2.2,27.2.6/14/33,
29.2.1,41.2.59,48.2.2–9/19,59.2.4 and July2026 TN-RA*-A0176A/E.
Original FSP5.9 supplies vocabulary, never a substitute target register map.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from ra8p1 import generate_device_header as header
from test_ra8p1_aux_header import compile_source, extract_stock_cmsis
from test_ra8p1_device_header import elf_sections

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools/ra8p1"
INCLUDE = ROOT / "baseline/ra/fsp/src/bsp/cmsis/Device/RENESAS/Include"
SOURCE = "RA8P1 HM §1.1, p.1"

# type, register/view, canonical field, offset, access width, position, bits
CANONICAL = [
    ("R_GPT0_Type", "GTSTR", "CSTRT", 0x4, 32, 0, 1),
    ("R_IWDT_Type", "IWDTRR", "IWDTRR", 0, 8, 0, 8),
    ("R_I3C0_Type", "SVST", "SVAFn", 0x214, 32, 16, 3),
    ("R_DBGCFGINF_Type", "DBGCFGINF", "BTCPU", 0, 32, 0, 1),
]
for n in range(4):
    CANONICAL.extend([
        ("R_RTC_Type", f"BCNT{n}", f"BCNT{n}", 2 + n * 2, 8, 0, 8),
        ("R_RTC_Type", f"BCNT{n}AR", f"BCNT{n}AR", 0x10 + n * 2, 8, 0, 8),
        ("R_RTC_CP_Type", f"BCNT{n}", f"BCNT{n}CP", (2, 4, 6, 10)[n], 8, 0, 8),
    ])
for name, offset, bits in (
        ("SD_ARG", 0x8, 32), ("SD_ARG1", 0xC, 16), ("SD_SECCNT", 0x14, 32),
        ("SD_RSP10", 0x18, 32), ("SD_RSP1", 0x1C, 16), ("SD_RSP32", 0x20, 32),
        ("SD_RSP3", 0x24, 16), ("SD_RSP54", 0x28, 32), ("SD_RSP5", 0x2C, 16),
        ("SD_RSP76", 0x30, 24), ("SD_RSP7", 0x34, 8), ("SD_BUF0", 0x60, 32)):
    CANONICAL.append(("R_SDHI0_Type", name, "SD_BUF" if name == "SD_BUF0" else name,
                      offset, 32, 0, bits))
for prefix, offset in (("SCI", 0x54), ("SPI", 0x56), ("ADC", 0x5A), ("GPT", 0x5C), ("LCD", 0x5E)):
    CANONICAL.append(("R_SYSTEM_Type", prefix + "CKDIVCR", "CKDIV", offset, 8, 0, 4))
    for name, pos, bits in (("CKSEL", 0, 4), ("CKSREQ", 6, 1), ("CKSRDY", 7, 1)):
        CANONICAL.append(("R_SYSTEM_Type", prefix + "CKCR", name, offset + 1, 8, pos, bits))


def canonical_source(anchors=CANONICAL):
    lines = ['#include <stddef.h>', '#include "R7KA8P1KF.h"']
    expected = {}
    for index, (typ, reg, field, offset, width, pos, bits) in enumerate(anchors):
        prefix = typ.removesuffix("_Type") + "_" + reg + "_" + field
        mask = ((1 << bits) - 1) << pos
        lines += [f'_Static_assert(offsetof({typ}, {reg}) == {offset}, "HM offset");',
                  f'_Static_assert(sizeof((({typ} *)0)->{reg}) == {width // 8}, "HM access width");',
                  f'_Static_assert(sizeof((({typ} *)0)->{reg}_b) == {width // 8}, "bitfield extent");',
                  f'_Static_assert({prefix}_Pos == {pos}, "HM position");',
                  f'_Static_assert({prefix}_Msk == 0x{mask:X}UL, "HM mask");',
                  '#ifdef __ELF__', f'__attribute__((section(".canonical.{index}"), used))', '#endif',
                  f'const __typeof__((({typ} *)0)->{reg}_b) canonical_{index} = '
                  + '{ .' + field + f' = 0x{(1 << bits) - 1:X}U }};']
        expected[f".canonical.{index}"] = mask.to_bytes(width // 8, "little")
    lines += [
        '_Static_assert(offsetof(R_SYSTEM_Type, PRCR) == 0x3FA, "Secure PRCR view");',
        '_Static_assert(offsetof(R_SYSTEM_Type, PRCR_NS) == 0x3FE, "distinct NS PRCR");',
        '_Static_assert(sizeof(((R_SYSTEM_Type *)0)->PRCR) == 2, "PRCR halfword");',
        '_Static_assert(offsetof(R_SRAM_Type, SRAMPRCR) == 0, "Secure SRAM protection");',
        '_Static_assert(offsetof(R_SRAM_Type, SRAMPRCR_NS) == 4, "distinct NS SRAM protection");',
        '_Static_assert(sizeof(((R_SRAM_Type *)0)->SRAMPRCR) == 2, "SRAM protection halfword");',
        '_Static_assert(R_SYSTEM_PRCR_PRC0_Msk == R_SYSTEM_PRCR_S_PRC0_Msk, "PRCR fields");',
        '_Static_assert(R_SRAM_SRAMPRCR_PR_Msk == R_SRAM_SRAMPRCR_S_PR_Msk, "SRAM fields");',
        '_Static_assert(R_DBGCFGINF_S_BASE == 0x02C9F04CUL, "TU secure address");',
        '_Static_assert(R_DBGCFGINF_NS_BASE == 0x12C9F04CUL, "TU NS address");',
        '_Static_assert(R_DBGCFGINF_BASE == (BSP_TZ_NONSECURE_BUILD ? 0x12C9F04CUL : 0x02C9F04CUL), "TU selection");',
        'void protection_views(R_SYSTEM_Type * sys, R_SRAM_Type * ram)', '{',
        '    sys->PRCR_b.PRC0 = sys->PRCR_S_b.PRC0;',
        '    ram->SRAMPRCR_b.PR = ram->SRAMPRCR_S_b.PR;', '}',
        '#ifndef __ELF__', 'int main(void)', '{',
    ]
    for index, values in enumerate(expected.values()):
        lines += [f'    const unsigned char expected_{index}[] = {{' + ','.join(map(str, values)) + '};',
                  f'    const volatile unsigned char * actual_{index} = (const volatile unsigned char *) &canonical_{index};',
                  f'    for (unsigned int n = 0; n < sizeof(expected_{index}); ++n)',
                  f'        if (actual_{index}[n] != expected_{index}[n]) return 1;']
    lines += ['    return 0;', '}', '#endif']
    return '\n'.join(lines), expected


def scalar(name="VALUE", offset=0, width=32, fields=None, **extra):
    return {"name": name, "offset": offset, "width": width, "access": "R/W",
            "source": SOURCE, "fields": fields or [], **extra}


def field(name="FLAG", pos=0, bits=1, **extra):
    return {"name": name, "pos": pos, "bits": bits, "access": "R/W", **extra}


def inventory(members, size=32):
    return {"schema": 1, "device": "R7KA8P1KF", "manual": SOURCE, "cores": [], "instances": [],
            "types": [{"name": "R_TEST_Type", "source": SOURCE, "size": size, "members": members}]}


class IntegratedReviewHeaderTests(unittest.TestCase):
    def test_owning_loader_contains_exact_delivered_additions_not_staged(self):
        data = header.load_inventory()
        types = {t["name"]: t for t in data["types"]}
        additions = json.loads((TOOLS / "review_system_header/owning_inventory_additions.json").read_text())
        for before, helpers in additions["insert_types_before"].items():
            for helper in helpers:
                self.assertEqual(helper, types[helper["name"]])
                self.assertLess(data["types"].index(types[helper["name"]]), data["types"].index(types[before]))
        for extension in additions["extend_types"]:
            self.assertEqual(extension["size"], types[extension["name"]]["size"])
            members = {m["name"]: m for m in types[extension["name"]]["members"]}
            for reg in extension["members"]:
                self.assertEqual(reg, members[reg["name"]])
        for path in ("registers_review_system.json", "registers_review_peripherals.json"):
            fragment = json.loads((TOOLS / path).read_text())
            for block in fragment["types"]:
                self.assertEqual(block, types[block["name"]])
            for instance in fragment["instances"]:
                self.assertIn(instance, data["instances"])
        self.assertEqual(INCLUDE.joinpath("R7KA8P1KF.h").read_bytes(),
                         header.render(data).replace('\n', '\r\n').encode())

    def test_original_field_spellings_and_programmed_reset_policy_survive(self):
        data = header.load_inventory()
        blocks = {b["name"]: b for b in data["types"]}
        for typ, reg, original in (("R_GPT0_Type", "GTSTR", "CSTRT0"),
                                   ("R_IWDT_Type", "IWDTRR", "REFRESH"),
                                   ("R_I3C0_Type", "SVST", "SVAF")):
            member = next(r for r in blocks[typ]["members"] if r["name"] == reg)
            self.assertIn(original, {f["name"] for f in member["fields"]})
        dbg = blocks["R_DBGCFGINF_Type"]["members"][0]
        self.assertEqual("R", dbg["access"])
        self.assertFalse(any(k in dbg for k in ("reset", "svd_reset", "manual_reset")))
        self.assertIn("blank products only", dbg["reset_note"])
        self.assertFalse(any(i["name"] in ("R_NPU", "R_PVD4", "R_PVD5") for i in data["instances"]))

    def test_native_canonical_layout_and_bitfield_bytes_both_cores_security_aliases(self):
        compiler = shutil.which("cc")
        self.assertIsNotNone(compiler)
        source, _ = canonical_source()
        with tempfile.TemporaryDirectory(prefix="ra8p1-canonical-native-") as tmp:
            folder = Path(tmp)
            for core in (0, 1):
                for nonsecure in (0, 1):
                    result, command, obj = compile_source(compiler, folder, source, core, nonsecure,
                                                         [TOOLS / "layout/native"])
                    self.assertEqual(0, result.returncode, ' '.join(command) + '\n' + result.stderr)
                    exe = folder / "canonical"
                    result = subprocess.run([compiler, str(obj), '-o', str(exe)], capture_output=True, text=True, timeout=60)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
                    self.assertEqual(0, result.returncode, f"core {core}, NS {nonsecure}: canonical byte probe")

    def test_cm85_cm33_canonical_layout_and_object_bytes_stock_cmsis(self):
        compiler = os.environ.get("RA8P1_ARM_CC") or shutil.which("arm-none-eabi-gcc")
        self.assertIsNotNone(compiler)
        source, expected = canonical_source()
        with tempfile.TemporaryDirectory(prefix="ra8p1-canonical-arm-") as tmp:
            folder = Path(tmp)
            cmsis = folder / "cmsis"
            extract_stock_cmsis(cmsis)
            for core in (0, 1):
                cpu, fpu = ("cortex-m85", "fpv5-d16") if core == 0 else ("cortex-m33", "fpv5-sp-d16")
                for nonsecure in (0, 1):
                    result, command, obj = compile_source(compiler, folder, source, core, nonsecure, [cmsis],
                                                         [f'-mcpu={cpu}', '-mthumb', f'-mfpu={fpu}', '-mfloat-abi=hard'])
                    self.assertEqual(0, result.returncode, ' '.join(command) + '\n' + result.stderr)
                    sections = elf_sections(obj)
                    for name, values in expected.items():
                        self.assertEqual(values, sections[name], name)

    def test_dbgcfginf_and_readonly_canonical_fields_reject_writes(self):
        compiler = shutil.which("cc")
        self.assertIsNotNone(compiler)
        expressions = ("R_DBGCFGINF->DBGCFGINF", "R_DBGCFGINF_NS->DBGCFGINF_b.BTCPU",
                       "R_RTC->CP[2].BCNT3_b.BCNT3CP", "R_SDHI0->SD_RSP1_b.SD_RSP1",
                       "R_SYSTEM->SCICKCR_b.CKSRDY")
        with tempfile.TemporaryDirectory(prefix="ra8p1-canonical-ro-") as tmp:
            for expr in expressions:
                result, _, _ = compile_source(compiler, Path(tmp), '#include "R7KA8P1KF.h"\nvoid rejected(void) { '
                                              + expr + ' = 0; }', includes=[TOOLS / "layout/native"])
                self.assertNotEqual(0, result.returncode, expr)
                self.assertRegex(result.stderr, r'read.only|const.qualified', expr)


# HM14.2.22 p558–559 numbers each word's IS fields by absolute event.
# HM64.2.30–42 p3791–3803 uses distinct gain/threshold labels per register.
REMAINING_ANCHORS = [
    ("R_CEU_Type", "CBWER", "BWE", 0xA0, 32, 0, 1),
    ("R_CANFD_CFDC_Type", "CTR", "BFT", 4, 32, 30, 1),
    ("R_CANFD_CFDGAFL_Type", "P1", "GAFLFDP0", 0xC, 32, 0, 1),
    ("R_CANFD_CFDGAFL_Type", "P1", "GAFLFDP1", 0xC, 32, 1, 1),
    ("R_CANFD_CFDGAFL_Type", "P1", "GAFLFDP8", 0xC, 32, 8, 1),
    ("R_CANFD_Type", "CFDRMND0", "RMNSu", 0x34, 16, 0, 16),
    ("R_CANFD_Type", "CFDRMIEC", "RMIE", 0x38, 16, 0, 16),
]
for word in range(32):
    for bit in range(32):
        REMAINING_ANCHORS.append(("R_ICU_COMMON_Type", f"INTSELR{word}", f"IS{32 * word + bit}",
                                  0x40 + 4 * word, 32, bit, 1))
for index, (low, high) in enumerate((("GAIN01", "GAIN00"), ("GAIN03", "GAIN02"),
                                   ("GAIN05", "GAIN04"), ("GAIN07", "GAIN06"),
                                   ("GAIN09", "GAIN08"), ("GAIN11", "GAIN10"),
                                   ("GAIN13", "GAIN012"), ("GAIN15", "GAIN14")), 1):
    for name, pos in ((low, 0), (high, 16)):
        REMAINING_ANCHORS.append(("R_GLCDC_GAM_Type", f"LUT{index}", name, 4 + 4 * index, 32, pos, 11))
for index, names in enumerate((("TH03", "TH02", "TH01"), ("TH06", "TH05", "TH04"),
                                ("TH09", "TH08", "TH07"), ("TH12", "TH11", "TH10"),
                                ("TH15", "TH14", "TH13")), 1):
    for pos, name in zip((0, 10, 20), names):
        REMAINING_ANCHORS.append(("R_GLCDC_GAM_Type", f"AREA{index}", name, 0x24 + 4 * index, 32, pos, 10))


def remaining_assertions():
    lines = [
        '_Static_assert(sizeof(((R_ICU_COMMON_Type *)0)->INTSELR) == 128, "raw routing array retained");',
        '_Static_assert(sizeof(((R_GLCDC_GAM_Type *)0)->LUT) == 32, "raw LUT array retained");',
        '_Static_assert(sizeof(((R_GLCDC_GAM_Type *)0)->AREA) == 20, "raw AREA array retained");',
        '_Static_assert(_Generic(&((R_CANFD_Type *)0)->CFDRMND0, volatile uint16_t *: 1, default: 0), "ND halfword access type");',
        '_Static_assert(_Generic(&((R_CANFD_Type *)0)->CFDRMIEC, volatile uint16_t *: 1, default: 0), "IEC halfword access type");',
    ]
    for word in range(32):
        lines.append(f'_Static_assert(offsetof(R_ICU_COMMON_Type, INTSELR[{word}]) == 0x{0x40 + 4 * word:X}, "raw routing stride");')
    for unit in (0, 1):
        for suffix, delta in (("S", 0), ("NS", 0x10000000)):
            lines.append(f'_Static_assert(R_CANFD{unit}_{suffix}_BASE == 0x{0x40380000 + unit * 0x2000 + delta:X}UL, "CANFD instance base");')
        for rule in range(16):
            lines.append(f'_Static_assert(offsetof(R_CANFD_Type, CFDGAFL[{rule}].P1) == 0x{0x12C + 16 * rule:X}, "filter entry stride");')
    for color in range(3):
        for index in range(8):
            lines.append(f'_Static_assert(offsetof(R_GLCDC_Type, GAM[{color}].LUT{index + 1}) == 0x{0x1308 + 0x40 * color + 4 * index:X}, "all gamma LUT offsets");')
        for index in range(5):
            lines.append(f'_Static_assert(offsetof(R_GLCDC_Type, GAM[{color}].AREA{index + 1}) == 0x{0x1328 + 0x40 * color + 4 * index:X}, "all gamma AREA offsets");')
    return '\n'.join(lines)


class RemainingReviewHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = header.load_inventory()
        cls.blocks = {b["name"]: b for b in cls.data["types"]}

    def test_exact_register_specific_field_names_access_widths_and_masks(self):
        expected = {}
        for typ, reg, name, offset, width, pos, bits in REMAINING_ANCHORS:
            expected.setdefault((typ, reg, offset, width), {})[name] = (pos, bits, "R/W")
        for (typ, name, offset, width), fields in expected.items():
            views = {}
            for reg in self.blocks[typ]["members"]:
                views[reg['name']] = {**reg, 'offset': header.number(reg['offset'])}
                for view in reg.get('views', []):
                    views[view['name']] = {**view, 'offset': header.number(reg['offset']) + view['offset']}
            actual = views[name]
            with self.subTest(typ=typ, reg=name):
                self.assertEqual((offset, width, 'R/W'), (actual['offset'], actual['width'], actual['access']))
                found = {f['name']: (f['pos'], f['bits'], f['access']) for f in actual['fields']}
                if name == 'CTR':
                    self.assertEqual(fields['BFT'], found['BFT'])
                else:
                    self.assertEqual(fields, found)
        icu = next(r for r in self.blocks['R_ICU_COMMON_Type']['members'] if r['name'] == 'INTSELR')
        self.assertEqual([], icu['fields'])  # no false repeated IS0..31 view
        self.assertEqual(32, len(icu['views']))
        self.assertIn('fixed zero', icu['source'])
        self.assertIn('88/89/91/92/101', icu['source'])

    def test_native_all_numbered_fields_and_halfword_writes_preserve_padding(self):
        compiler = shutil.which('cc')
        self.assertIsNotNone(compiler)
        source, _ = canonical_source(REMAINING_ANCHORS)
        source += '\n' + remaining_assertions()
        with tempfile.TemporaryDirectory(prefix='ra8p1-remaining-native-') as tmp:
            folder = Path(tmp)
            for core in (0, 1):
                for nonsecure in (0, 1):
                    result, command, obj = compile_source(compiler, folder, source, core, nonsecure,
                                                         [TOOLS / 'layout/native'])
                    self.assertEqual(0, result.returncode, ' '.join(command) + '\n' + result.stderr)
                    exe = folder / 'remaining'
                    result = subprocess.run([compiler, str(obj), '-o', str(exe)], capture_output=True, text=True, timeout=60)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
                    self.assertEqual(0, result.returncode, f'core {core}, NS {nonsecure}: numbered field byte probe')
            memory = '''#include <string.h>
#include "R7KA8P1KF.h"
int main(void) {
    R_CANFD_Type regs;
    unsigned char expected[sizeof(regs)];
    memset(&regs, 0xA5, sizeof(regs));
    memset(expected, 0xA5, sizeof(expected));
    regs.CFDRMND0 = 0x1234;
    expected[0x34] = 0x34; expected[0x35] = 0x12;
    if (memcmp(&regs, expected, sizeof(regs))) return 1;
    regs.CFDRMND0_b.RMNSu = 0x5678;
    expected[0x34] = 0x78; expected[0x35] = 0x56;
    if (memcmp(&regs, expected, sizeof(regs))) return 2;
    regs.CFDRMIEC = 0x9ABC;
    expected[0x38] = 0xBC; expected[0x39] = 0x9A;
    if (memcmp(&regs, expected, sizeof(regs))) return 3;
    regs.CFDRMIEC_b.RMIE = 0xDEF0;
    expected[0x38] = 0xF0; expected[0x39] = 0xDE;
    return memcmp(&regs, expected, sizeof(regs)) != 0;
}'''
            result, command, obj = compile_source(compiler, folder, memory, includes=[TOOLS / 'layout/native'])
            self.assertEqual(0, result.returncode, ' '.join(command) + '\n' + result.stderr)
            result = subprocess.run([compiler, str(obj), '-o', str(exe)], capture_output=True, text=True, timeout=60)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(0, subprocess.run([str(exe)], timeout=60).returncode)

    def test_cm85_cm33_all_numbered_layouts_and_bitfield_bytes_stock_cmsis(self):
        compiler = os.environ.get('RA8P1_ARM_CC') or shutil.which('arm-none-eabi-gcc')
        self.assertIsNotNone(compiler)
        source, expected = canonical_source(REMAINING_ANCHORS)
        source += '\n' + remaining_assertions()
        with tempfile.TemporaryDirectory(prefix='ra8p1-remaining-arm-') as tmp:
            folder = Path(tmp)
            cmsis = folder / 'cmsis'
            extract_stock_cmsis(cmsis)
            for core in (0, 1):
                cpu, fpu = ('cortex-m85', 'fpv5-d16') if core == 0 else ('cortex-m33', 'fpv5-sp-d16')
                for nonsecure in (0, 1):
                    result, command, obj = compile_source(compiler, folder, source, core, nonsecure, [cmsis],
                                                         [f'-mcpu={cpu}', '-mthumb', f'-mfpu={fpu}', '-mfloat-abi=hard'])
                    self.assertEqual(0, result.returncode, ' '.join(command) + '\n' + result.stderr)
                    sections = elf_sections(obj)
                    for name, values in expected.items():
                        self.assertEqual(values, sections[name], name)

    def test_reserved_and_wrong_numbered_fields_stay_unavailable(self):
        compiler = shutil.which('cc')
        self.assertIsNotNone(compiler)
        expressions = ('R_CANFD0->CFDGAFL[15].P1_b.GAFLFDP2',
                       'R_GLCDC->GAM[2].LUT2_b.GAIN00', 'R_GLCDC->GAM[1].AREA2_b.TH01',
                       'R_ICU_COMMON->INTSELR1_b.IS0', 'R_ICU_COMMON->INTSELR31_b.IS31')
        with tempfile.TemporaryDirectory(prefix='ra8p1-remaining-negative-') as tmp:
            for expr in expressions:
                result, _, _ = compile_source(compiler, Path(tmp), '#include "R7KA8P1KF.h"\nvoid rejected(void) { '
                                              + expr + ' = 0; }', includes=[TOOLS / 'layout/native'])
                self.assertNotEqual(0, result.returncode, expr)
                self.assertIn(expr.rsplit('.', 1)[1], result.stderr)

    def test_source_blocked_omissions_and_reset_disputes_are_unchanged(self):
        blocked = {
            'R_GPTP_Type': {'PTPSCR0', 'PTPSCR1', 'PTPSCR2'},
            'R_MFWD_Type': {f'{stem}{index}' for stem in ('FWRFC', 'FWRFVC') for index in range(2, 16)},
            'R_ESWM_Type': {'TPEMIMC0'},
            'R_GWCA0_Type': {f'GWIDC{index}' for index in range(64)},
        }
        for typ, forbidden in blocked.items():
            actual = {r['name'] for r in self.blocks[typ]['members']}
            actual.update(n for r in self.blocks[typ]['members'] for n in r.get('individual_names', []) if n)
            self.assertFalse(forbidden & actual, typ)
        self.assertNotIn('R_NPU_Type', self.blocks)
        system = {r['name'] for r in self.blocks['R_SYSTEM_Type']['members']}
        self.assertFalse({'PVD4FCR', 'PVD5FCR'} & system)
        for reg in self.blocks['R_DOTF_Type']['members']:
            self.assertFalse(any('reset' in k.lower() for k in reg))


class HeaderAdmissionReviewTests(unittest.TestCase):
    def test_rejects_all_generated_padding_namespace_collisions(self):
        cases = [
            [scalar('RESERVED0', 4)],
            [scalar('RESERVED0', 0)],  # trailing gap
            [scalar('RESERVED_INDEX_A_0', 0), scalar('A', 4, count=2, individual_names=[None, 'A1'])],
            [scalar('RESERVED_BYTE', 0), scalar('A', 4, views=[dict(name='BYTE', offset=1, width=8, access='R')])],
        ]
        for members in cases:
            with self.subTest(members=members), self.assertRaisesRegex(ValueError, 'Duplicate member'):
                header.render(inventory(members))

    def test_rejects_flattened_macros_across_registers_views_types_and_instances(self):
        a = scalar('A_B', 0, fields=[field('C')])
        b = scalar('A', 4, fields=[field('B_C')])
        cases = [inventory([a, b])]
        view = dict(name='A', offset=0, width=32, access='R/W', fields=[field('B_C')])
        cases.append(inventory([{**a, 'views': [view]}]))
        across = inventory([scalar('B_C', fields=[field('D')])])
        across['types'].append(dict(name='R_TEST_B_Type', size=4, source=SOURCE,
                                    members=[scalar('C', fields=[field('D')])]))
        cases.append(across)
        instance = inventory([a])
        instance['instances'] = [dict(name='R_TEST_A_B_C_Msk', type='R_TEST_Type', secure=0, source=SOURCE)]
        cases.append(instance)
        for data in cases:
            with self.subTest(data=data), self.assertRaisesRegex(ValueError, 'Duplicate macro'):
                header.render(data)

    def test_rejects_field_alias_and_macro_alias_collisions(self):
        for aliases in (['FLAG'], ['OTHER']):
            reg = scalar(fields=[field(aliases=aliases), field('OTHER', 1)])
            with self.subTest(aliases=aliases), self.assertRaisesRegex(ValueError, 'Duplicate field'):
                header.validate(inventory([reg]))
        reg = scalar(fields=[field(aliases=['OTHER']), field('SECOND', 1, macro_name='OTHER')])
        with self.assertRaisesRegex(ValueError, 'Duplicate field macro'):
            header.validate(inventory([reg]))

    def test_wider_view_alignment_and_extent_guards_survive(self):
        view = dict(name='WORD', offset=0, width=32, access='R/W')
        for offset, count, message in ((1, 4, 'Overlapping/misaligned'), (0, 5, 'union extent')):
            reg = scalar(offset=offset, width=8, count=count, views=[view])
            with self.subTest(offset=offset, count=count), self.assertRaisesRegex(ValueError, message):
                header.validate(inventory([reg]))
        data = inventory([scalar(width=8, count=4, views=[view])], 4)
        header.validate(data)
        self.assertEqual(4, data['types'][0]['alignment'])

    def test_register_updates_reject_changed_layout_or_existing_fields(self):
        for expected, fields, message in (({'offset': 4}, [], 'layout changed'),
                                          ({'offset': 0}, [field()], 'replace fields')):
            data = inventory([scalar(fields=fields)])
            data['register_updates'] = [dict(type='R_TEST_Type', register='VALUE', expected=expected,
                                             add_fields=[field('NEW')], source=SOURCE)]
            with tempfile.TemporaryDirectory(prefix='ra8p1-update-') as tmp:
                path = Path(tmp) / 'inventory.json'
                path.write_text(json.dumps(data))
                with self.subTest(expected=expected, fields=fields), self.assertRaisesRegex(ValueError, message):
                    header.load_inventory([path])


if __name__ == '__main__':
    unittest.main()
