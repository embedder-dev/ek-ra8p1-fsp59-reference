#!/usr/bin/env python3
"""Audit r019 EK-RA8P1 GNU FLAT images and emit/check application-only S3/S7.

This checks download bytes, not build provenance, startup, or programmer erase behavior.
Only the app ranges and section mappings of the bench plan are supported. JSON ranges
are half-open; run verify against the exact artifact again just before programming.
"""

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import struct
import tempfile

APP = {"cpu0": (0x02000000, 0x0207F800), "cpu1": (0x02080000, 0x02100000)}
SRAM = {"cpu0": (0x22000000, 0x220D0000), "cpu1": (0x220D0000, 0x221A0000)}
TCM_SIZE = {"cpu0": 0x20000, "cpu1": 0x10000}

# r019 fsp.ld: each word has its own PT_LOAD. fsp_cpu1.ld permits none.
OPTIONS = {
    ".option_setting_ofs0": 0x02C9F040,
    ".option_setting_ofs2": 0x02C9F044,
    ".option_setting_sas": 0x02C9F074,
    ".option_setting_ofs1_sec": 0x02C9F0C0,
    ".option_setting_ofs3_sec": 0x02C9F0C4,
    ".option_setting_ofs1_sel": 0x02C9F120,
    ".option_setting_ofs3_sel": 0x02C9F124,
    ".option_setting_ofs1": 0x12C9F4C0,
    ".option_setting_ofs3": 0x12C9F4C4,
}

ELF_HEADER = struct.Struct("<16sHHIIIIIHHHHHH")
PROGRAM_HEADER = struct.Struct("<8I")
SECTION_HEADER = struct.Struct("<10I")
PT_LOAD, SHT_PROGBITS, SHT_STRTAB, SHT_NOBITS = 1, 1, 3, 8
SHF_ALLOC, SHF_EXECINSTR, PF_X, PF_R = 2, 4, 1, 4


class GuardError(ValueError):
    """Malformed image or a mapping outside the bench policy."""


@dataclass(frozen=True)
class Load:
    offset: int
    vma: int
    lma: int
    size: int
    memsz: int
    flags: int


@dataclass(frozen=True)
class Section:
    name: str
    vma: int
    lma: int
    data: bytes


@dataclass(frozen=True)
class Image:
    core: str
    entry: int
    sections: tuple[Section, ...]
    excluded_options: tuple[Section, ...]


def inside(bounds, address, size):
    return bounds[0] <= address and address + size <= bounds[1]


def disjoint(ranges, label):
    end = 0
    for start, stop in sorted(ranges):
        if start < end:
            raise GuardError(f"overlapping {label} at {start:#x}")
        end = stop


def checked_file_range(data, offset, size, label):
    end = offset + size
    if end > len(data) or end > 1 << 32:
        raise GuardError(f"{label} exceeds the ELF file")
    return offset, end


def audit_elf(data: bytes, core: str) -> Image:
    if core not in APP:
        raise GuardError("unknown core")
    checked_file_range(data, 0, ELF_HEADER.size, "ELF header")
    (ident, kind, machine, version, entry, phoff, shoff, _, ehsize, phsize, phnum,
     shsize, shnum, shstrndx) = ELF_HEADER.unpack_from(data)
    if (ident[:7] != b"\x7fELF\x01\x01\x01" or (kind, machine, version) != (2, 40, 1)
            or (ehsize, phsize, shsize) != (ELF_HEADER.size, PROGRAM_HEADER.size, SECTION_HEADER.size)
            or not 0 < phnum < 0xFFFF or not 0 < shstrndx < shnum < 0xFF00):
        raise GuardError("expected a little-endian ARM ELF32 executable with ordinary header tables")
    elf_tables = [(0, ehsize),
                  checked_file_range(data, phoff, phsize * phnum, "program headers"),
                  checked_file_range(data, shoff, shsize * shnum, "section headers")]
    disjoint(elf_tables, "ELF header tables")

    loads = []
    for index in range(phnum):
        ptype, offset, vma, lma, size, memsz, flags, align = PROGRAM_HEADER.unpack_from(
            data, phoff + index * phsize)
        if ptype == 0:  # PT_NULL has no mapping.
            continue
        if ptype != PT_LOAD:
            raise GuardError(f"unknown program header type {ptype:#x}")
        if size > memsz or vma + memsz > 1 << 32 or lma + size > 1 << 32:
            raise GuardError(f"invalid PT_LOAD sizes at index {index}")
        if not size:  # Explicit GNU PHDRS also emit empty and NOLOAD headers.
            continue
        if (align > 1 and (align & (align - 1) or (offset - vma) % align)
                or flags & ~7 or not flags & PF_R):
            raise GuardError(f"invalid PT_LOAD alignment/flags at index {index}")
        checked_file_range(data, offset, size, "PT_LOAD")
        loads.append(Load(offset, vma, lma, size, memsz, flags))
    disjoint(elf_tables + [(p.offset, p.offset + p.size) for p in loads], "PT_LOAD/file structures")
    disjoint(((p.lma, p.lma + p.size) for p in loads), "PT_LOAD physical ranges")
    disjoint(((p.vma, p.vma + p.size) for p in loads), "PT_LOAD virtual ranges")

    def section_header(index):
        return SECTION_HEADER.unpack_from(data, shoff + index * shsize)

    strings = section_header(shstrndx)
    if strings[1] != SHT_STRTAB or strings[2] != 0 or not strings[5] or any(section_header(0)):
        raise GuardError("invalid section name table or null header")
    start, end = checked_file_range(data, strings[4], strings[5], "section names")
    names = data[start:end]
    if names[:1] != b"\0" or names[-1:] != b"\0":
        raise GuardError("invalid section name table")

    app_sections = []
    options = []
    section_names = set()
    coverage = {p: [] for p in loads}
    file_ranges = elf_tables.copy()
    entry_backed = False
    tcm = TCM_SIZE[core]
    windows = {".text": APP[core], ".data": SRAM[core], ".itcm_data": (0, tcm),
               ".dtcm_data": (0x20000000, 0x20000000 + tcm)}
    for index in range(1, shnum):
        nameoff, stype, flags, vma, offset, size, _, _, _, _ = section_header(index)
        if not size or stype == SHT_NOBITS:
            continue
        file_ranges.append(checked_file_range(data, offset, size, f"section {index}"))
        if not flags & SHF_ALLOC:
            continue
        nameend = names.find(b"\0", nameoff)
        if nameend <= nameoff:
            raise GuardError(f"invalid allocated section name at index {index}")
        name = names[nameoff:nameend].decode("ascii")
        if name in section_names:
            raise GuardError(f"duplicate allocated section {name}")
        section_names.add(name)
        if name not in windows and name not in OPTIONS:
            raise GuardError(f"unknown allocated file-backed section {name}")
        types = (SHT_PROGBITS, 14, 15, 16) if name == ".data" else (SHT_PROGBITS,)
        if stype not in types or flags & ~7:
            raise GuardError(f"invalid type/flags for {name}")
        matches = [p for p in loads if inside((p.offset, p.offset + p.size), offset, size)
                   and vma - p.vma == offset - p.offset]
        if len(matches) != 1:
            raise GuardError(f"no unique PT_LOAD file/VMA mapping for {name}")
        p = matches[0]
        section = Section(name, vma, p.lma + offset - p.offset, data[offset:offset + size])
        coverage[p].append((offset, offset + size))
        if name in OPTIONS:
            if (core != "cpu0" or vma != OPTIONS[name] or section.lma != vma or flags != SHF_ALLOC
                    or (size, p.size, p.memsz, p.flags) != (4, 4, 4, PF_R)):
                raise GuardError(f"invalid option payload mapping for {name}")
            options.append(section)
        else:
            if not inside(APP[core], section.lma, size):
                raise GuardError(f"{name} physical range {section.lma:#010x}..{section.lma + size:#010x} "
                                 f"outside {core} application MRAM")
            if not inside(windows[name], vma, size) or (name == ".text" and vma != section.lma):
                raise GuardError(f"unexpected execution mapping for {name}")
            if name == ".text" and flags & SHF_EXECINSTR and p.flags & PF_X:
                entry_backed = bool(entry & 1) and inside((vma, vma + size), entry & ~1, 2)
            app_sections.append(section)

    disjoint(file_ranges, "ELF section/file structures")
    # Section whitelisting alone would miss padding, hidden bytes, and orphan segments.
    for p, slices in coverage.items():
        cursor = p.offset
        for start, stop in sorted(slices):
            if start != cursor:
                raise GuardError(f"unaccounted PT_LOAD bytes at {p.lma + cursor - p.offset:#010x}")
            cursor = stop
        if cursor != p.offset + p.size:
            raise GuardError(f"unaccounted PT_LOAD bytes at {p.lma + cursor - p.offset:#010x}")
    if not entry_backed:
        raise GuardError("entry is not a Thumb address backed by executable application .text")
    return Image(core, entry, tuple(sorted(app_sections, key=lambda s: s.lma)),
                 tuple(sorted(options, key=lambda s: s.lma)))


def srecord(kind, address, data=b""):
    body = bytes([len(data) + 5]) + address.to_bytes(4, "big") + data
    return b"S" + kind + (body + bytes([~sum(body) & 0xFF])).hex().upper().encode("ascii") + b"\n"


def encode_srec(image: Image) -> bytes:
    records = [srecord(b"3", section.lma + offset, section.data[offset:offset + 32])
               for section in image.sections for offset in range(0, len(section.data), 32)]
    return b"".join(records) + srecord(b"7", image.entry)


def parse_srec(data: bytes, core: str):
    """Decode the guard's S3/S7-only format without relying on the ELF or encoder."""
    records = []
    entry = None
    for number, line in enumerate(data.splitlines(), 1):
        if entry is not None:
            raise GuardError("record follows S7 termination")
        if not re.fullmatch(rb"S[37](?:[0-9a-fA-F]{2}){6,256}", line):
            raise GuardError(f"invalid S3/S7 record at line {number}")
        raw = bytes.fromhex(line[2:].decode("ascii"))
        if raw[0] != len(raw) - 1 or sum(raw) % 256 != 255:
            raise GuardError(f"S-record count or checksum mismatch at line {number}")
        address = int.from_bytes(raw[1:5], "big")
        payload = raw[5:-1]
        if line.startswith(b"S7"):
            if payload:
                raise GuardError("S7 termination has a payload")
            entry = address
        else:
            if not payload or not inside(APP[core], address, len(payload)):
                raise GuardError(f"S3 empty or outside {core} application MRAM at line {number}")
            records.append((address, payload))
    if entry is None or not records:
        raise GuardError("missing S3 data or S7 termination")
    disjoint(((addr, addr + len(payload)) for addr, payload in records), "S3 data records")
    return entry, records


def runs(records):
    """Normalize adjacent byte ranges without filling any holes."""
    merged = []
    for start, payload in sorted(records):
        if merged and merged[-1][0] + len(merged[-1][1]) == start:
            merged[-1][1].extend(payload)
        else:
            merged.append((start, bytearray(payload)))
    return merged


def verify_srec(data: bytes, image: Image):
    entry, records = parse_srec(data, image.core)
    if entry != image.entry:
        raise GuardError(f"S7 entry {entry:#010x} does not match ELF entry {image.entry:#010x}")
    expected = runs((section.lma, section.data) for section in image.sections)
    if runs(records) != expected:
        raise GuardError("S3 addresses or payload bytes do not exactly match the allowed ELF bytes")
    return expected


def metadata(elf, srec, image, verified_runs):
    def address(value):
        return f"0x{value:08x}"

    return {
        "core": image.core,
        "permitted_range": list(map(address, APP[image.core])),
        "entry": address(image.entry),
        "elf_sha256": sha256(elf).hexdigest(),
        "srec_sha256": sha256(srec).hexdigest(),
        "byte_count": sum(len(data) for _, data in verified_runs),
        "ranges": [[address(start), address(start + len(data))] for start, data in verified_runs],
        "sections": [{"name": s.name, "vma": address(s.vma), "lma": address(s.lma), "size": len(s.data)}
                     for s in image.sections],
        "excluded_options": [{"name": s.name, "lma": address(s.lma), "size": len(s.data),
                              "sha256": sha256(s.data).hexdigest()} for s in image.excluded_options],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "verify"), help="build a new S-record or verify an existing one")
    parser.add_argument("--core", required=True, choices=APP)
    parser.add_argument("elf", type=Path)
    parser.add_argument("srec", type=Path, help="app-only S-record; build refuses to overwrite")
    args = parser.parse_args(argv)
    try:
        elf = args.elf.read_bytes()
        image = audit_elf(elf, args.core)
        srec = encode_srec(image) if args.action == "build" else args.srec.read_bytes()
        verified_runs = verify_srec(srec, image)
        if args.action == "build":
            # Publish complete bytes under a new name without replacing an existing artifact.
            with tempfile.NamedTemporaryFile(dir=args.srec.parent) as staging:
                staging.write(srec)
                staging.flush()
                os.link(staging.name, args.srec)
        print(json.dumps(metadata(elf, srec, image, verified_runs), separators=(",", ":")))
    except (OSError, ValueError) as error:
        parser.exit(1, f"image_guard: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
