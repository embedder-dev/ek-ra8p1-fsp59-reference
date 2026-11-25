"""Host-only tests using synthetic ARM ELF32 section and program tables."""

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import unittest

import image_guard as guard

BASE = 0x02000000
SCRATCH = 0x0207F800
CPU1 = 0x02080000
OPTION_ADDRESS = 0x02C9F040
CODE = b"\x00\xbf" * 32
INIT = b"\xff\x11\x22\x33"
WORD = b"\x78\x56\x34\x12"


@dataclass(frozen=True)
class Fragment:
    name: str
    vma: int
    lma: int
    data: bytes
    sflags: int
    pflags: int
    stype: int = 1


TEXT = Fragment(".text", BASE, BASE, CODE, 6, 5)
DATA = Fragment(".data", 0x22000000, BASE + 0x80, INIT, 3, 6, stype=14)
OPTION = Fragment(".option_setting_ofs0", OPTION_ADDRESS, OPTION_ADDRESS, WORD, 2, 4)
NOLOAD = Fragment(".bss", 0x22000100, 0x22000100, b"\0" * 40, 3, 6, stype=8)


def synthetic_elf(*fragments, entry=BASE + 1):
    """Emit one segment and section per fragment, plus shstrtab and an empty PHDR."""
    phnum = len(fragments) + 1
    result = bytearray(52 + phnum * 32)
    sections = [bytes(40)]
    names = bytearray(b"\0.shstrtab\0")
    for index, f in enumerate(fragments):
        offset, nameoff = len(result), len(names)
        size = 0 if f.stype == 8 else len(f.data)
        result.extend(f.data[:size])
        names.extend(f.name.encode() + b"\0")
        struct.pack_into("<8I", result, 52 + index * 32, 1, offset, f.vma, f.lma,
                         size, len(f.data), f.pflags, 1)
        sections.append(struct.pack("<10I", nameoff, f.stype, f.sflags, f.vma, offset,
                                    len(f.data), 0, 0, 1, 0))
    struct.pack_into("<8I", result, 52 + (phnum - 1) * 32, 1, 52, 0, 0, 0, 0, 0, 4096)
    sections.append(struct.pack("<10I", 1, 3, 0, 0, len(result), len(names), 0, 0, 1, 0))
    result.extend(names)
    shoff = len(result)
    result.extend(b"".join(sections))
    struct.pack_into("<16sHHIIIIIHHHHHH", result, 0, b"\x7fELF\x01\x01\x01", 2, 40, 1, entry,
                     52, shoff, 0x5000000, 52, 32, phnum, 40, len(sections), len(sections) - 1)
    return result


def modify(blob, offset, value):
    result = bytearray(blob)
    struct.pack_into("<I", result, offset, value)
    return result


def record(kind, addr, payload=b""):
    raw = struct.pack(">BI", 5 + len(payload), addr) + payload
    return f"S{kind}{raw.hex()}{255 - (sum(raw) % 256):02x}\n".encode()


class ElfAuditTests(unittest.TestCase):
    def test_option_table_matches_r019_gcc_linkers(self):
        scripts = (Path(__file__).resolve().parents[2]
                   / "pack_sources/ra8p1/Renesas.RA_mcu_ra8p1.5.9.0/script")
        link_options = r"^\s+(\.option_setting_\w+)\s+(0x[0-9a-f]+)\s+:"
        options = dict(re.findall(link_options, (scripts / "fsp.ld").read_text(), re.M))
        self.assertEqual({name: int(addr, 16) for name, addr in options.items()}, guard.OPTIONS)
        self.assertFalse(re.findall(link_options, (scripts / "fsp_cpu1.ld").read_text(), re.M))

    def test_sparse_cpu0_includes_ram_initializer_excludes_only_options_and_nobits(self):
        other_option = Fragment(".option_setting_ofs3", 0x12C9F4C4, 0x12C9F4C4, WORD, 2, 4)
        image = guard.audit_elf(synthetic_elf(DATA, OPTION, NOLOAD, other_option, TEXT), "cpu0")
        self.assertEqual([(s.name, s.lma) for s in image.excluded_options],
                         [(OPTION.name, OPTION_ADDRESS), (other_option.name, 0x12C9F4C4)])
        srec = guard.encode_srec(image)
        self.assertEqual(guard.parse_srec(srec, "cpu0"),
                         (BASE + 1, [(BASE, CODE[:32]), (BASE + 32, CODE[32:]), (BASE + 0x80, INIT)]))
        self.assertEqual(guard.verify_srec(srec, image), [(BASE, CODE), (BASE + 0x80, INIT)])

    def test_cpu1_owns_its_mram_sram_and_tcm_mapping(self):
        text = replace(TEXT, lma=CPU1, vma=CPU1)
        sram = replace(DATA, lma=0x02100000 - 4, vma=0x220D0000)
        itcm = Fragment(".itcm_data", 0, CPU1 + 0x44, INIT, 3, 6)
        dtcm = replace(itcm, name=".dtcm_data", vma=0x20000000, lma=CPU1 + 0x48)
        image = guard.audit_elf(synthetic_elf(text, sram, itcm, dtcm, entry=CPU1 + 1), "cpu1")
        self.assertFalse(image.excluded_options)
        self.assertEqual(guard.verify_srec(guard.encode_srec(image), image)[-1], (0x02100000 - 4, INIT))
        for fragment in [replace(sram, vma=0x22000000), replace(itcm, vma=0x10000),
                         replace(dtcm, vma=0x20E00000), replace(sram, lma=0x02100000)]:
            with self.subTest(fragment=fragment), self.assertRaises(guard.GuardError):
                guard.audit_elf(synthetic_elf(text, fragment, entry=CPU1 + 1), "cpu1")
        with self.assertRaisesRegex(guard.GuardError, "invalid option payload"):
            guard.audit_elf(synthetic_elf(text, OPTION, entry=CPU1 + 1), "cpu1")

    def test_cpu0_exclusive_end_and_forbidden_destinations(self):
        guard.audit_elf(synthetic_elf(TEXT, replace(DATA, lma=SCRATCH - 4)), "cpu0")
        for address in (SCRATCH - 2, SCRATCH, CPU1, BASE - 4, 0x12000000, 0x22000000,
                        0x27000000, 0x60000000, OPTION_ADDRESS):
            with self.subTest(address=hex(address)), self.assertRaisesRegex(guard.GuardError, "outside"):
                guard.audit_elf(synthetic_elf(TEXT, replace(DATA, lma=address)), "cpu0")

    def test_option_names_and_addresses_cannot_masquerade(self):
        for fragment in [replace(OPTION, lma=BASE + 0x80, vma=BASE + 0x80),
                         replace(OPTION, lma=OPTION_ADDRESS + 4),
                         replace(OPTION, vma=OPTION_ADDRESS + 4),
                         replace(OPTION, data=WORD[:3]), replace(OPTION, pflags=6),
                         replace(OPTION, sflags=3)]:
            with self.subTest(fragment=fragment), self.assertRaisesRegex(guard.GuardError, "invalid option payload"):
                guard.audit_elf(synthetic_elf(TEXT, fragment), "cpu0")
        for fragment in [replace(OPTION, name=".option_setting_unknown"),
                         replace(OPTION, name=".fake"), replace(DATA, name=".id_code")]:
            with self.subTest(fragment=fragment), self.assertRaisesRegex(guard.GuardError, "unknown allocated"):
                guard.audit_elf(synthetic_elf(TEXT, fragment), "cpu0")

    def test_rejects_uncovered_segment_padding_and_broken_mappings(self):
        elf = synthetic_elf(TEXT, DATA, OPTION)
        shoff = struct.unpack_from("<I", elf, 32)[0]
        data_ph, option_ph = 52 + 32, 52 + 64
        text_sh, data_sh, option_sh = shoff + 40, shoff + 80, shoff + 120
        data_off = struct.unpack_from("<I", elf, data_sh + 16)[0]
        errors = [
            (modify(elf, data_sh + 8, 0), "unaccounted"),  # nonallocated bytes still in PT_LOAD
            (modify(elf, data_sh + 20, 2), "unaccounted"),  # partial segment coverage
            (modify(elf, text_sh + 4, 8), "unaccounted"),  # NOBITS cannot cover file bytes
            (modify(elf, data_sh + 12, DATA.vma + 1), "no unique PT_LOAD"),
            (modify(elf, data_sh + 16, data_off + 1), "no unique PT_LOAD"),
            (modify(elf, data_ph + 12, BASE + 2), "overlapping PT_LOAD physical"),
            (modify(elf, data_ph + 8, BASE + 2), "overlapping PT_LOAD virtual"),
            (modify(elf, data_ph + 4, data_off - 2), "overlapping PT_LOAD/file"),
            (modify(elf, data_ph + 4, len(elf) - 2), "exceeds the ELF file"),
            (modify(elf, data_ph + 16, len(INIT) + 1), "invalid PT_LOAD sizes"),
            (modify(elf, data_ph + 28, 3), "invalid PT_LOAD alignment"),
            (modify(elf, data_ph, 2), "unknown program header"),
            (modify(elf, option_ph + 20, 8), "invalid option payload"),
            (modify(modify(modify(elf, option_ph + 16, 8), option_ph + 20, 8), option_sh + 20, 8),
             "invalid option payload"),
        ]
        for mutated, error in errors:
            with self.subTest(error=error), self.assertRaisesRegex(guard.GuardError, error):
                guard.audit_elf(mutated, "cpu0")

    def test_bad_elf_identity_and_entry(self):
        elf = synthetic_elf(TEXT)
        for bad in (bytes(elf[:12]), b"\x7fELF\x02" + elf[5:], modify(elf, 16, 0x003E0002),
                    modify(elf, 32, len(elf) - 2)):
            with self.assertRaises(guard.GuardError):
                guard.audit_elf(bad, "cpu0")
        for entry in (BASE, BASE + len(CODE) + 1, OPTION_ADDRESS + 1, DATA.vma + 1):
            with self.subTest(entry=hex(entry)), self.assertRaisesRegex(guard.GuardError, "entry"):
                guard.audit_elf(synthetic_elf(TEXT, DATA, OPTION, entry=entry), "cpu0")


class SrecordTests(unittest.TestCase):
    def setUp(self):
        self.elf = synthetic_elf(TEXT, DATA, OPTION)
        self.image = guard.audit_elf(self.elf, "cpu0")
        self.code = record(3, BASE, CODE)
        self.init = record(3, BASE + 0x80, INIT)
        self.termination = record(7, BASE + 1)

    def test_accepts_equivalent_different_record_boundaries(self):
        self.assertEqual(guard.verify_srec(self.init + self.code + self.termination, self.image),
                         [(BASE, CODE), (BASE + 0x80, INIT)])

    def test_rejects_valid_checksum_payload_omission_and_gap_changes(self):
        for init in (b"", record(3, BASE + 0x80, b"\xfe" + INIT[1:]), record(3, BASE + 0x81, INIT),
                     self.init + record(3, BASE + 0x70, b"\x00")):
            with self.subTest(init=init), self.assertRaisesRegex(guard.GuardError, "exactly match"):
                guard.verify_srec(self.code + init + self.termination, self.image)

    def test_rejects_checksums_count_format_and_termination(self):
        invalid = [
            (self.code[:-3] + b"00\n" + self.termination, "count or checksum"),
            (self.code[:2] + b"00" + self.code[4:] + self.termination, "count or checksum"),
            (self.code + record(7, BASE + 3), "does not match ELF entry"),
            (self.code + record(7, BASE + 1, b"x"), "S7 termination has a payload"),
            (self.code, "missing S3 data or S7"),
            (self.termination + self.code, "follows S7"),
            (self.code + b"S1zz\n" + self.termination, "invalid S3/S7"),
            (self.code + self.code + self.termination, "overlapping S3"),
        ]
        for srec, error in invalid:
            with self.subTest(error=error), self.assertRaisesRegex(guard.GuardError, error):
                guard.verify_srec(srec, self.image)

    def test_rejects_scratch_other_core_and_option_records_before_equality(self):
        for address in (SCRATCH - 2, SCRATCH, CPU1, OPTION_ADDRESS):
            with self.subTest(address=hex(address)), self.assertRaisesRegex(guard.GuardError, "outside"):
                guard.verify_srec(self.code + record(3, address, WORD) + self.termination, self.image)

    def test_cli_build_verify_hashes_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            elf = Path(temp) / "fixture.elf"
            elf.write_bytes(self.elf)
            srec = Path(temp) / "app.srec"
            cli = [sys.executable, str(Path(guard.__file__).resolve())]
            args = ["--core", "cpu0", str(elf), str(srec)]

            def invoke(action):
                return subprocess.run(cli + [action] + args, capture_output=True, text=True)

            built = invoke("build")
            self.assertEqual(built.returncode, 0, built.stderr)
            verified = invoke("verify")
            self.assertEqual(verified.returncode, 0, verified.stderr)
            evidence = json.loads(verified.stdout)
            self.assertEqual(json.loads(built.stdout), evidence)
            self.assertEqual(evidence["elf_sha256"], sha256(self.elf).hexdigest())
            self.assertEqual(evidence["srec_sha256"], sha256(srec.read_bytes()).hexdigest())
            self.assertEqual(evidence["ranges"], [["0x02000000", "0x02000040"], ["0x02000080", "0x02000084"]])
            self.assertEqual(evidence["byte_count"], len(CODE) + len(INIT))
            self.assertEqual(evidence["excluded_options"][0]["sha256"], sha256(WORD).hexdigest())
            self.assertEqual(invoke("build").returncode, 1)  # no replacement on rerun
            srec.write_bytes(self.code + self.termination)
            rejected = invoke("verify")
            self.assertEqual(rejected.returncode, 1)
            self.assertIn("exactly match", rejected.stderr)
            self.assertEqual(rejected.stdout, "")


if __name__ == "__main__":
    unittest.main()
