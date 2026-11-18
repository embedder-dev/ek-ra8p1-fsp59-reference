#!/usr/bin/env python3
"""Construct custom FSP 5.9-derived packs without touching an IDE installation.

--source-root is the owning FSP checkout (baseline/ by default). Existing
PDSC-owned ra/fsp, ra/board and module_descriptions files are synchronized to
EVERY owner, including unchanged packs. Pack-only resources stay unchanged.
No deletion is inferred from a file absent from the source checkout.

--pack-sources contains <pack-basename-without-.pack>/ trees. A new pack needs
its FULL contents, including its PDSC, toolingSupport.xml and referenced files.
For an existing pack the tree is an explicit overlay; additions and overrides
are never inferred from filenames in the checkout. Current checkout bytes win
over stock copies in a full tree; conflicting authored overrides are rejected.

Only changed/new packs are emitted. --output must not exist: each invocation
publishes a new immutable revision containing packs, manifest.json and
entry-diffs.json. Keep older revision directories with their matching bytes.
Metadata schema/reference validation and installation remain separate steps.
"""
import argparse
from collections import Counter
from contextlib import ExitStack
from dataclasses import dataclass, field
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from fsp_manifest import digest, safe_name, xml


def parse_xml(data):
    try:
        return xml(data)
    except ET.ParseError as error:
        raise ValueError("Malformed pack XML: " + str(error)) from error


ARCHIVE_SHA256 = "99c4abae6239a68171fcbff86070971f591f0a8945e90a50eb07d87843bee363"
VERSION = "5.9.0"
PACK_PREFIX = "internal/projectgen/ra/packs/"
ROOT = Path(__file__).resolve().parents[1]
SOURCE_TREES = ("ra/fsp", "ra/board", "module_descriptions")
COMPONENT_KEYS = ("Cvendor", "Cclass", "Cgroup", "Csub", "Cvariant", "Cversion")


def checked_name(name):
    safe_name(name)
    if name == "." or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise ValueError("Unsafe path: " + name)
    return name


def checked_path(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError("Symlinked path: " + str(part))
    return path


def tree_files(root):
    """Read only regular files, checking directories before descending into them."""
    root = checked_path(root)
    if not root.is_dir():
        raise ValueError("Expected input directory: " + str(root))
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(directory) / name
            relative = checked_name(path.relative_to(root).as_posix())
            kind = stat.S_IFMT(path.lstat().st_mode)
            if kind not in (stat.S_IFREG, stat.S_IFDIR):
                raise ValueError("Non-regular input: " + str(path))
            if kind == stat.S_IFREG:
                result[relative] = path.read_bytes()
    return result


def zip_inventory(archive):
    files, directories, seen = set(), set(), set()
    for item in archive.infolist():
        name = item.filename[:-1] if item.is_dir() else item.filename
        checked_name(name)
        if item.orig_filename != item.filename:
            raise ValueError("Truncated archive path")
        if name in seen:
            raise ValueError("Duplicate archive path: " + name)
        seen.add(name)
        kind = stat.S_IFMT(item.external_attr >> 16)
        allowed = (0, stat.S_IFDIR) if item.is_dir() else (0, stat.S_IFREG)
        if kind not in allowed or item.flag_bits & 1:
            raise ValueError("Unsupported archive entry: " + name)
        (directories if item.is_dir() else files).add(name)
    for name in seen:
        parent = Path(name).parent
        while str(parent) != ".":
            if parent.as_posix() in files:
                raise ValueError("Archive file/directory collision: " + name)
            parent = parent.parent
    return files, directories


@dataclass
class Pack:
    name: str
    archive: object = None
    original_files: set = field(default_factory=set)
    directories: set = field(default_factory=set)
    overrides: dict = field(default_factory=dict)

    @property
    def names(self):
        return self.original_files | self.overrides.keys()

    def read(self, name):
        if name in self.overrides:
            return self.overrides[name]
        return self.archive.read(name)

    def original(self, name):
        return self.archive.read(name) if name in self.original_files else None


def load_release(path, stack):
    path = checked_path(path)
    stream = stack.enter_context(path.open("rb"))
    if hashlib.file_digest(stream, "sha256").hexdigest() != ARCHIVE_SHA256:
        raise ValueError("Release archive hash mismatch")
    stream.seek(0)
    release = stack.enter_context(zipfile.ZipFile(stream))
    names, _ = zip_inventory(release)
    packs = {}
    for name in sorted(names):
        if not name.startswith(PACK_PREFIX) or not name.endswith("." + VERSION + ".pack"):
            continue
        basename = name[len(PACK_PREFIX):]
        if "/" in basename:
            raise ValueError("Nested release pack: " + name)
        archive = stack.enter_context(zipfile.ZipFile(io.BytesIO(release.read(name))))
        files, directories = zip_inventory(archive)
        packs[basename] = Pack(basename, archive, files, directories)
    if not packs:
        raise ValueError("No FSP 5.9.0 release packs")
    return packs


def source_name(name):
    if name.startswith("ra~1/"):
        return "ra/fsp/src/bsp/cmsis/Device/RENESAS/" + name[5:]
    if name.startswith(("ra/fsp/", "ra/board/")):
        return name
    if name.startswith(".module_descriptions/"):
        return name[1:]
    return None


def inspect_pack(pack):
    """Check file/MDF/support closure, not the IDE's XML schema or expressions."""
    descriptors = [n for n in pack.names if n.endswith(".pdsc")]
    if len(descriptors) != 1:
        raise ValueError("Expected one PDSC: " + pack.name)
    pdsc = parse_xml(pack.read(descriptors[0]))
    old_pdsc = pack.original(descriptors[0])
    old_counts = Counter(tuple(c.get(k, "") for k in COMPONENT_KEYS)
                         for c in parse_xml(old_pdsc).findall("./components/component")) if old_pdsc else Counter()
    vendor, name = pdsc.findtext("vendor"), pdsc.findtext("name")
    release = pdsc.find("./releases/release")
    version = release.get("version") if release is not None else None
    if (pdsc.tag != "package" or not vendor or not name or not version
            or pack.name != vendor + "." + name + "." + version + ".pack"
            or descriptors[0] != vendor + "." + name + ".pdsc"):
        raise ValueError("PDSC/pack identity mismatch: " + pack.name)
    conditions = {node.get("id") for node in pdsc.findall("./conditions/condition")}
    for node in pdsc.iter():
        if node.get("condition") and node.get("condition") not in conditions:
            raise ValueError("Unknown PDSC condition in " + pack.name + ": " + node.get("condition"))
    references, modules = set(), set()
    if "toolingSupport.xml" in pack.names:
        support = parse_xml(pack.read("toolingSupport.xml"))
        if support.tag != "toolingSupport" or support.get("family") != "ra":
            raise ValueError("Invalid toolingSupport identity: " + pack.name)
        for item in support.findall("./file"):
            entry = checked_name(item.text or "")
            if entry not in pack.names:
                raise ValueError("Missing support file in " + pack.name + ": " + entry)
            if item.get("supportType") == "Modules":
                modules.add(entry)
                if item.get("version") != version:
                    raise ValueError("Module support version mismatch: " + entry)
    elif not pack.original_files:
        raise ValueError("Missing toolingSupport.xml: " + pack.name)
    component_ids = Counter()
    for component in pdsc.findall("./components/component"):
        key = tuple(component.get(k, "") for k in COMPONENT_KEYS)
        component_ids[key] += 1
        if component.get("Cversion") != version:
            raise ValueError("Component version mismatch: " + pack.name)
        if component_ids[key] > max(1, old_counts[key]):
            raise ValueError("Duplicate component identity: " + pack.name)
        # The three stock blinky source-only packs have Projects, not MDFs.
        if component.get("Cclass") != "Projects":
            mdf = ".module_descriptions/" + "##".join(key) + ".xml"
            if mdf not in pack.names or mdf not in modules:
                raise ValueError("Missing component MDF/support in " + pack.name + ": " + mdf)
        for item in component.findall("./files/file"):
            entry = item.get("name", "")
            checked_name(entry[:-1] if entry.endswith("/") else entry)
            if entry.endswith("/"):
                continue  # Include search paths need not contain any files in this pack.
            if entry not in pack.names:
                raise ValueError("Missing PDSC file in " + pack.name + ": " + entry)
            references.add(entry)
    for entry in pack.names:
        if entry.startswith(".module_descriptions/"):
            if entry not in modules:
                raise ValueError("Unregistered MDF: " + entry)
            parse_xml(pack.read(entry))
            references.add(entry)
    for entry in pack.overrides:
        if source_name(entry) and entry not in references:
            raise ValueError("Unknown source ownership in " + pack.name + ": " + entry)
    return references


def ownership(packs, references):
    owners = {}
    for name, entries in references.items():
        for entry in entries:
            source = source_name(entry)
            if source:
                owners.setdefault(source, set()).add((name, entry))
    return owners


def component_owners(packs):
    result = {}
    for name, pack in packs.items():
        pdsc = parse_xml(pack.read(next(n for n in pack.names if n.endswith(".pdsc"))))
        for node in pdsc.findall("./components/component"):
            key = tuple(node.get(k, "") for k in COMPONENT_KEYS)
            result.setdefault(key, set()).add(name)
    return result


def add_inputs(packs, root):
    root = checked_path(root)
    if not root.is_dir():
        raise ValueError("Expected pack-source directory: " + str(root))
    explicit = set()
    for path in sorted(root.iterdir()):
        checked_path(path)
        if not path.is_dir():
            raise ValueError("Expected a pack input tree: " + str(path))
        name = checked_name(path.name + ".pack")
        if not name.endswith("." + VERSION + ".pack"):
            raise ValueError("Expected a 5.9.0 pack input tree: " + path.name)
        files = tree_files(path)
        if not files:
            raise ValueError("Empty pack input tree: " + path.name)
        pack = packs.setdefault(name, Pack(name))
        for entry, data in files.items():
            if entry in pack.directories or any(entry.startswith(n + "/") for n in pack.names):
                raise ValueError("Pack file/directory collision: " + entry)
            if any(n.startswith(entry + "/") for n in pack.names | pack.directories):
                raise ValueError("Pack file/directory collision: " + entry)
            pack.overrides[entry] = data
            explicit.add((name, entry))
    return explicit


def disclaimer_equivalent(originals):
    """Recognize only the two exact FSP 5.9 release banners, not arbitrary comments."""
    banners = (b"/* ${REA_DISCLAIMER_PLACEHOLDER} */\r\n",
               b"/*\r\n* Copyright (c) 2020 - 2025 Renesas Electronics Corporation and/or its affiliates\r\n"
               b"*\r\n* SPDX-License-Identifier: BSD-3-Clause\r\n*/\r\n")
    bodies = set()
    for data in originals:
        banner = next((b for b in banners if data.startswith(b)), None)
        if banner is None:
            return False
        bodies.add(data[len(banner):])
    return len(bodies) == 1


def synchronize(packs, owners, original_owners, sources, explicit):
    for source in sorted(sources.keys() | owners.keys() | original_owners.keys()):
        targets = owners.get(source, set()) | original_owners.get(source, set())
        if not targets:
            raise ValueError("Unknown source ownership: " + source)
        originals = {packs[p].original(e) for p, e in original_owners.get(source, ())}
        authored = {packs[p].read(e) for p, e in targets if (p, e) in explicit}
        if source in sources:
            data = sources[source]
            if len(originals) > 1:
                # Leave untouched byte-distinct stock owners intact. A checkout
                # edit may replace all owners only if their bodies match exactly
                # after removing the release's two known disclaimer banners.
                if data in originals and not (authored - originals):
                    continue
                if not disclaimer_equivalent(originals):
                    raise ValueError("Conflicting original source ownership: " + source)
            authored_overrides = {packs[p].read(e) for p, e in targets
                                  if (p, e) in explicit and packs[p].original(e) is not None}
            if authored_overrides - originals - {data}:
                raise ValueError("Conflicting explicit source override: " + source)
        else:
            changed = authored - originals
            if not changed:
                continue  # The source checkout intentionally omits some stock content.
            if len(changed) != 1 or len(originals) > 1 or (authored & originals):
                raise ValueError("Conflicting explicit source ownership: " + source)
            data = next(iter(changed))
        for name, entry in targets:
            if packs[name].read(entry) != data:
                packs[name].overrides[entry] = data


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_pack(pack, path):
    """Fixed ordering, timestamps, modes and compression; preserve entry payloads."""
    hashes = {}
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        entries = pack.names | {n + "/" for n in pack.directories}
        for name in sorted(entries):
            directory = name.endswith("/")
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = ((stat.S_IFDIR | 0o755) if directory
                                  else (stat.S_IFREG | 0o644)) << 16
            data = b"" if directory else pack.read(name)
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
            if not directory:
                hashes[name] = digest(data)
    with path.open("rb") as stream:
        archive_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"sha256": archive_hash, "entries": hashes}


def build(archive, source_root, pack_sources, output):
    output = checked_path(output)
    if output.exists():
        raise ValueError("Immutable output already exists; choose a new revision: " + str(output))
    source_root = checked_path(source_root)
    if not source_root.is_dir():
        raise ValueError("Expected source root: " + str(source_root))
    for input_path in (source_root, checked_path(pack_sources)):
        if output == input_path or output in input_path.parents or input_path in output.parents:
            raise ValueError("Output must be separate from input trees")
    with ExitStack() as stack:
        packs = load_release(archive, stack)
        original_refs = {name: inspect_pack(pack) for name, pack in packs.items()}
        original_owners = ownership(packs, original_refs)
        original_components = component_owners(packs)
        explicit = add_inputs(packs, pack_sources)
        references = {name: inspect_pack(pack) for name, pack in packs.items()}
        for key, names in component_owners(packs).items():
            if len(names) > 1 and names != original_components.get(key):
                raise ValueError("Conflicting component ownership: " + "##".join(key))
        owners = ownership(packs, references)
        sources = {}
        for tree in SOURCE_TREES:
            path = source_root / tree
            if path.exists() or path.is_symlink():
                files = tree_files(path)
                if tree == "module_descriptions" and "toolingSupport.xml" in files:
                    support = parse_xml(files.pop("toolingSupport.xml"))
                    if support.tag != "toolingSupport" or support.get("family") != "ra":
                        raise ValueError("Expected toolingSupport metadata, not an MDF: " + tree + "/toolingSupport.xml")
                    # This checkout index is not an MDF; pack metadata is authored
                    # explicitly in pack_sources and must not be overwritten by it.
                sources.update((tree + "/" + n, d) for n, d in files.items())
        synchronize(packs, owners, original_owners, sources, explicit)
        diffs = {}
        for name, pack in sorted(packs.items()):
            changes = {}
            for entry, data in sorted(pack.overrides.items()):
                before = pack.original(entry)
                if before != data:
                    changes[entry] = {"before_sha256": digest(before) if before is not None else None,
                                      "after_sha256": digest(data)}
            if changes:
                inspect_pack(pack)
                diffs[name] = {"status": "modified" if pack.original_files else "added",
                               "entries": changes}
        if not diffs:
            raise ValueError("No candidate changes")
        # Complete validation before creating any output; publish the whole revision.
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".ra8p1-packs-", dir=output.parent))
        try:
            manifest = {"description": "Custom FSP 5.9-derived RA8P1 support candidate; not stock",
                        "fsp_version": VERSION, "source_archive_sha256": ARCHIVE_SHA256, "packs": {}}
            for name in diffs:
                manifest["packs"][name] = write_pack(packs[name], temporary / name)
            (temporary / "manifest.json").write_bytes(json_bytes(manifest))
            (temporary / "entry-diffs.json").write_bytes(json_bytes({"packs": diffs}))
            # mkdir reserves the destination without ever replacing another revision.
            output.mkdir()
            try:
                for path in sorted(temporary.iterdir()):
                    path.rename(output / path.name)
            except BaseException:
                shutil.rmtree(output)
                raise
        finally:
            shutil.rmtree(temporary)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archive", type=Path, default=ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip")
    parser.add_argument("--source-root", type=Path, default=ROOT / "baseline")
    parser.add_argument("--pack-sources", type=Path, default=ROOT / "pack_sources/ra8p1")
    parser.add_argument("--output", type=Path, default=ROOT / "validation/ra8p1/packs/candidate")
    args = parser.parse_args(argv)
    try:
        manifest = build(args.archive, args.source_root, args.pack_sources, args.output)
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        parser.exit(1, "Pack construction failed: " + str(error) + "\n")
    print("Candidate: " + str(args.output))
    print("Packs: " + str(len(manifest["packs"])))
    print("Manifest: " + str(args.output / "manifest.json"))
    print("Entry diffs: " + str(args.output / "entry-diffs.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
