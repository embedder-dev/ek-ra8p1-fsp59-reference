"""Compile-only checks of manual-derived CRC/CAC/DOC_B inventory fragments.

The generated header lives only in a temporary directory. Native checks use the
existing labelled CMSIS doubles; Arm checks use CMSIS from the original 5.9 ZIP.
No installed packs, checked-in generated header, SVD or hardware are used.
"""

import copy
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

from ra8p1 import generate_device_header as header
from test_ra8p1_device_header import elf_sections


ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools/ra8p1"
INCLUDE = ROOT / "baseline/ra/fsp/src/bsp/cmsis/Device/RENESAS/Include"
INVENTORY = TOOLS / "registers_compat_aux.json"

# Independent anchors: HM §§49.2 (pp.3191–3194), 10.2 (pp.422–427),
# 58.2 (pp.3529–3532). Names/types follow the original FSP 5.9 header.
LAYOUTS = {
    "R_CRC_Type": (0x10, 4, {
        "CRCCR0": (0x00, 1), "CRCCR1": (0x01, 1),
        "CRCDIR": (0x04, 4), "CRCDIR_BY": (0x04, 1),
        "CRCDOR": (0x08, 4), "CRCDOR_HA": (0x08, 2),
        "CRCDOR_BY": (0x08, 1), "CRCSAR": (0x0C, 2),
    }),
    "R_CAC_Type": (0x0C, 2, {
        "CACR0": (0x00, 1), "CACR1": (0x01, 1), "CACR2": (0x02, 1),
        "CAICR": (0x03, 1), "CASTR": (0x04, 1), "CAULVR": (0x06, 2),
        "CALLVR": (0x08, 2), "CACNTBR": (0x0A, 2),
    }),
    "R_DOC_B_Type": (0x18, 4, {
        "DOCR": (0x00, 1), "DOSR": (0x04, 1), "DOSCR": (0x08, 1),
        "DODIR": (0x0C, 4), "DODSR0": (0x10, 4), "DODSR1": (0x14, 4),
    }),
}

# Field (position, mask), independent of the inventory under test. Full-width
# data fields retain the baseline header's register-name bitfield vocabulary.
FIELDS = {
    "R_CRC_CRCCR0": {"GPS": (0, 0x07), "LMS": (6, 0x40), "DORCLR": (7, 0x80)},
    "R_CRC_CRCCR1": {"CRCSWR": (6, 0x40), "CRCSEN": (7, 0x80)},
    "R_CRC_CRCDIR": {"CRCDIR": (0, 0xFFFFFFFF)},
    "R_CRC_CRCDIR_BY": {"CRCDIR_BY": (0, 0xFF)},
    "R_CRC_CRCDOR": {"CRCDOR": (0, 0xFFFFFFFF)},
    "R_CRC_CRCDOR_HA": {"CRCDOR_HA": (0, 0xFFFF)},
    "R_CRC_CRCDOR_BY": {"CRCDOR_BY": (0, 0xFF)},
    "R_CRC_CRCSAR": {"CRCSA": (0, 0x3FFF)},
    "R_CAC_CACR0": {"CFME": (0, 0x01)},
    "R_CAC_CACR1": {"CACREFE": (0, 0x01), "FMCS": (1, 0x0E),
                     "TCSS": (4, 0x30), "EDGES": (6, 0xC0)},
    "R_CAC_CACR2": {"RPS": (0, 0x01), "RSCS": (1, 0x0E),
                     "RCDS": (4, 0x30), "DFS": (6, 0xC0)},
    "R_CAC_CAICR": {"FERRIE": (0, 0x01), "MENDIE": (1, 0x02), "OVFIE": (2, 0x04),
                     "FERRFCL": (4, 0x10), "MENDFCL": (5, 0x20), "OVFFCL": (6, 0x40)},
    "R_CAC_CASTR": {"FERRF": (0, 0x01), "MENDF": (1, 0x02), "OVFF": (2, 0x04)},
    "R_CAC_CAULVR": {"CAULVR": (0, 0xFFFF)},
    "R_CAC_CALLVR": {"CALLVR": (0, 0xFFFF)},
    "R_CAC_CACNTBR": {"CACNTBR": (0, 0xFFFF)},
    "R_DOC_B_DOCR": {"OMS": (0, 0x03), "DOBW": (3, 0x08), "DCSEL": (4, 0x70)},
    "R_DOC_B_DOSR": {"DOPCF": (0, 0x01)},
    "R_DOC_B_DOSCR": {"DOPCFCL": (0, 0x01)},
}

BASES = {"R_CRC": 0x40310000, "R_CAC": 0x40202400, "R_DOC_B": 0x40311000}


def check_source():
    """Independent C anchors plus object-data probes; never execute MMIO."""
    lines = ['#include <stddef.h>', '#include "R7KA8P1KF.h"']
    for typ, (size, alignment, members) in LAYOUTS.items():
        lines += [f'_Static_assert(sizeof({typ}) == {size}, "{typ} size");',
                  f'_Static_assert(_Alignof({typ}) == {alignment}, "{typ} alignment");']
        for member, (offset, width) in members.items():
            lines += [f'_Static_assert(offsetof({typ}, {member}) == {offset}, "{member} offset");',
                      f'_Static_assert(sizeof((({typ} *) 0)->{member}) == {width}, "{member} width");']
    for name, base in BASES.items():
        lines += [f'_Static_assert({name}_S_BASE == 0x{base:X}UL, "{name} secure base");',
                  f'_Static_assert({name}_NS_BASE == 0x{base + 0x10000000:X}UL, "{name} nonsecure base");',
                  f'_Static_assert({name}_BASE == (0x{base:X}UL + '
                  f'(BSP_TZ_NONSECURE_BUILD ? 0x10000000UL : 0)), "{name} selected base");',
                  f'_Static_assert(_Generic({name}, {name}_Type *: 1, default: 0), "{name} type");']
    sections = {}
    for prefix, fields in FIELDS.items():
        instance = next(name for name in BASES if prefix.startswith(name + "_"))
        member = prefix[len(instance) + 1:]
        width = LAYOUTS[instance + "_Type"][2][member][1]
        section = f".aux.{len(sections)}"
        lines += ['#ifdef __ELF__', f'__attribute__((section("{section}"), used))', '#endif',
                  f'const __typeof__((({instance}_Type *) 0)->{member}_b) probe_{len(sections)}[] = {{']
        expected = bytearray()
        for field, (pos, mask) in fields.items():
            lines.append(f'    {{ .{field} = 0x{mask >> pos:X}U }},')
            expected += mask.to_bytes(width, "little")
        lines.append('};')
        sections[section] = bytes(expected)
        for field, (pos, mask) in fields.items():
            lines += [f'_Static_assert({prefix}_{field}_Pos == {pos}, "{prefix}_{field} position");',
                      f'_Static_assert({prefix}_{field}_Msk == 0x{mask:X}UL, "{prefix}_{field} mask");']
    return "\n".join(lines) + "\n", sections


def compile_source(compiler, folder, source, core=0, nonsecure=0, includes=(), flags=()):
    src, obj = folder / "aux.c", folder / "aux.o"
    src.write_text('#include "bsp_exceptions.h"\n' + source)
    command = [str(compiler), "-std=c11", "-Wall", "-Wextra", "-Werror", "-ffreestanding",
               f"-DBSP_CFG_CPU_CORE={core}", f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}", *flags,
               "-I", str(folder), *[arg for path in includes for arg in ("-I", str(path))],
               "-I", str(INCLUDE), "-I", str(ROOT / "baseline/ra/fsp/src/bsp/mcu/all"),
               "-c", str(src), "-o", str(obj)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    return result, command, obj


def extract_stock_cmsis(folder):
    archive = ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip"
    prefix = "ra/arm/CMSIS_6/CMSIS/Core/Include/"
    pack_name = "internal/projectgen/ra/packs/Arm.CMSIS6.6.1.0+fsp.5.9.0.pack"
    with zipfile.ZipFile(archive) as release:
        with zipfile.ZipFile(io.BytesIO(release.read(pack_name))) as pack:
            for name in pack.namelist():
                if name.startswith(prefix) and not name.endswith("/"):
                    relative = Path(name[len(prefix):])
                    if relative.is_absolute() or ".." in relative.parts:
                        raise AssertionError("Unsafe stock CMSIS path")
                    target = folder / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(pack.read(name))


class AuxHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fragment = json.loads(INVENTORY.read_text())
        cls.data = header.load_inventory()
        cls.rendered = header.render(copy.deepcopy(cls.data))

    def test_sorted_inventory_merge_is_valid_and_unique(self):
        self.assertEqual(set(LAYOUTS), {block["name"] for block in self.fragment["types"]})
        self.assertEqual(set(BASES), {instance["name"] for instance in self.fragment["instances"]})
        names = [name for block in self.data["types"] for name in [block["name"], *block.get("aliases", [])]]
        for typ in LAYOUTS:
            self.assertEqual(1, names.count(typ))
        for block in self.fragment["types"]:
            self.assertNotIn("aliases", block)
            for member in block["members"]:
                self.assertIn("RA8P1 HM", member["source"])
                self.assertNotIn("count", member)
        for fabricated in ("R_DOC_Type", "#define R_DOC_BASE", "R_DOC_B_DOCR_DOPCFCL", "DODIR_HA"):
            self.assertNotIn(fabricated, self.rendered)

    def test_stock_hal_register_and_mask_vocabulary(self):
        references = []
        for driver in ("r_crc", "r_cac", "r_doc"):
            text = (ROOT / f"baseline/ra/fsp/src/{driver}/{driver}.c").read_text()
            for macro in re.findall(r"\bR_(?:CRC|CAC|DOC_B)_\w+_(?:Pos|Msk)\b", text):
                self.assertIn(f"#define {macro} ", self.rendered)
            references.extend(re.findall(r"\b(R_CRC|R_CAC|R_DOC_B)->(\w+(?:\.\w+)?)", text))
        lines = ['#include "R7KA8P1KF.h"', 'void stock_register_vocabulary(void)', '{']
        lines += [f'    (void) ({instance}->{member});' for instance, member in sorted(set(references))]
        lines.append('}')
        self.compile_native("\n".join(lines))

    def compile_native(self, source):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("Native compiler unavailable")
        with tempfile.TemporaryDirectory(prefix="ra8p1-aux-native-") as tmp:
            folder = Path(tmp)
            (folder / "R7KA8P1KF.h").write_text(self.rendered)
            for core in (0, 1):
                for nonsecure in (0, 1):
                    with self.subTest(core=core, nonsecure=nonsecure):
                        result, command, _ = compile_source(
                            compiler, folder, source, core, nonsecure, [TOOLS / "layout/native"])
                        self.assertEqual(0, result.returncode, " ".join(command) + "\n" + result.stderr)

    def test_native_size_offset_width_mask_and_instance_anchors(self):
        source, _ = check_source()
        self.compile_native(source)

    def test_read_only_status_registers_reject_writes(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("Native compiler unavailable")
        with tempfile.TemporaryDirectory(prefix="ra8p1-aux-readonly-") as tmp:
            folder = Path(tmp)
            (folder / "R7KA8P1KF.h").write_text(self.rendered)
            for expression in ("R_CAC->CASTR", "R_CAC->CASTR_b.FERRF", "R_CAC->CACNTBR",
                               "R_CAC->CACNTBR_b.CACNTBR", "R_DOC_B->DOSR", "R_DOC_B->DOSR_b.DOPCF"):
                with self.subTest(expression=expression):
                    result, _, _ = compile_source(
                        compiler, folder, '#include "R7KA8P1KF.h"\nvoid rejected(void) { '
                        + expression + ' = 0; }\n', includes=[TOOLS / "layout/native"])
                    self.assertNotEqual(0, result.returncode)
                    self.assertRegex(result.stderr, r"read.only|const.qualified")

    def test_cm85_cm33_layout_and_bitfield_object_bytes_stock_cmsis(self):
        compiler = os.environ.get("RA8P1_ARM_CC") or shutil.which("arm-none-eabi-gcc")
        if not compiler:
            self.skipTest("Arm GCC unavailable (set RA8P1_ARM_CC)")
        source, expected = check_source()
        with tempfile.TemporaryDirectory(prefix="ra8p1-aux-arm-") as tmp:
            folder = Path(tmp)
            (folder / "R7KA8P1KF.h").write_text(self.rendered)
            cmsis = folder / "cmsis"
            extract_stock_cmsis(cmsis)
            for core in (0, 1):
                cpu, fpu = ("cortex-m85", "fpv5-d16") if core == 0 else ("cortex-m33", "fpv5-sp-d16")
                for nonsecure in (0, 1):
                    with self.subTest(core=core, nonsecure=nonsecure):
                        result, command, obj = compile_source(
                            compiler, folder, source, core, nonsecure, [cmsis],
                            [f"-mcpu={cpu}", "-mthumb", f"-mfpu={fpu}", "-mfloat-abi=hard"])
                        self.assertEqual(0, result.returncode, " ".join(command) + "\n" + result.stderr)
                        actual = elf_sections(obj)
                        for section, values in expected.items():
                            self.assertEqual(values, actual[section], section)


if __name__ == "__main__":
    unittest.main()
