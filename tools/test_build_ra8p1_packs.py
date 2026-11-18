"""Construction-only tests; no installation, IDE or target operations."""
from contextlib import ExitStack
import io
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch
import warnings
import xml.etree.ElementTree as ET
import zipfile

import build_ra8p1_packs as builder
from fsp_manifest import digest, read_manifest, read_zip


VERSION = "5.9.0"
A = "Renesas.RA_mcu_a.5.9.0.pack"
B = "Renesas.RA_mcu_b.5.9.0.pack"
NEW = "Renesas.RA_mcu_ra8p1.5.9.0.pack"
SHARED = "ra/fsp/src/bsp/cmsis/Device/RENESAS/Source/system.c"
ALIAS = "ra~1/Source/system.c"
FEATURE = "ra/fsp/src/bsp/mcu/ra8p1/bsp_feature.h"
LICENSE = (b"/*\r\n* Copyright (c) 2020 - 2025 Renesas Electronics Corporation and/or its affiliates\r\n"
           b"*\r\n* SPDX-License-Identifier: BSD-3-Clause\r\n*/\r\n")
PLACEHOLDER = b"/* ${REA_DISCLAIMER_PLACEHOLDER} */\r\n"


def zip_bytes(entries, extra=()):
    stream = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in list(entries.items()) + list(extra):
                archive.writestr(name, data)
    return stream.getvalue()


def pack_contents(name, sources, group=None):
    vendor, package, version = name[:-5].split(".", 2)
    group = group or package
    mdf = "##".join((vendor, "BSP", group, "fsp", "", version)) + ".xml"
    pdsc = ET.Element("package", schemaVersion="1.2")
    ET.SubElement(pdsc, "vendor").text = vendor
    ET.SubElement(pdsc, "name").text = package
    releases = ET.SubElement(pdsc, "releases")
    ET.SubElement(releases, "release", version=version)
    components = ET.SubElement(pdsc, "components")
    component = ET.SubElement(components, "component", Cvendor=vendor, Cclass="BSP",
                              Cgroup=group, Csub="fsp", Cversion=version)
    files = ET.SubElement(component, "files")
    ET.SubElement(files, "file", category="include", name="ra/fsp/inc/")
    for source in sources:
        ET.SubElement(files, "file", category="source", name=source)
    support = ET.Element("toolingSupport", family="ra", platform="platform.rafsp")
    ET.SubElement(support, "file", supportType="Modules", version=version).text = ".module_descriptions/" + mdf
    return {vendor + "." + package + ".pdsc": ET.tostring(pdsc),
            "toolingSupport.xml": ET.tostring(support),
            ".module_descriptions/" + mdf: b"<raModuleDescription/>",
            ".mcu/unmodified.bin": b"\x00\xff untouched\r\n",
            **sources}


class PackConstructionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / "baseline"
        self.inputs = self.root / "pack_sources"
        self.inputs.mkdir()
        self.source.mkdir()
        self.put_source(SHARED, b"current shared bytes\n")
        self.stock = {A: pack_contents(A, {SHARED: b"stock\r\n"}),
                      B: pack_contents(B, {ALIAS: b"stock\r\n"})}
        self.archive = self.root / "release.zip"
        self.counter = 0
        self.sha_patch = patch.object(builder, "ARCHIVE_SHA256", "")
        self.sha_patch.start()
        self.addCleanup(self.sha_patch.stop)
        self.write_release()

    def write_release(self, extra=()):
        entries = {builder.PACK_PREFIX + name: zip_bytes({"empty/": b"", **files})
                   for name, files in self.stock.items()}
        # Other release versions must not become 5.9.0 candidates.
        entries[builder.PACK_PREFIX + "Renesas.Ignore.1.2.3.pack"] = b"not a selected pack"
        raw = zip_bytes(entries, extra)
        self.archive.write_bytes(raw)
        builder.ARCHIVE_SHA256 = digest(raw)

    def put_source(self, name, data):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def put_input(self, pack, files):
        root = self.inputs / pack[:-5]
        for name, data in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return root

    def build(self, output=None):
        self.counter += 1
        output = output or self.root / ("revision-" + str(self.counter))
        builder.build(self.archive, self.source, self.inputs, output)
        return output

    def candidate(self, output, pack):
        return read_zip((output / pack).read_bytes())

    def test_deterministic_archives_manifest_and_diffs(self):
        self.put_input(NEW, pack_contents(NEW, {FEATURE: b"feature\n"}))
        self.put_source(FEATURE, b"feature\n")
        before = self.archive.read_bytes()
        first = self.build()
        os.utime(self.source / SHARED, (1600000000, 1600000000))
        os.chmod(self.source / SHARED, 0o600)
        with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "1800000000"}):
            second = self.build()
        self.assertEqual({p.name: p.read_bytes() for p in first.iterdir()},
                         {p.name: p.read_bytes() for p in second.iterdir()})
        self.assertEqual(before, self.archive.read_bytes())
        with zipfile.ZipFile(first / A) as archive:
            for item in archive.infolist():
                self.assertEqual(item.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(item.create_system, 3)
                self.assertEqual(stat.S_IMODE(item.external_attr >> 16), 0o755 if item.is_dir() else 0o644)

    def test_changed_shared_source_reaches_every_original_owner_and_alias(self):
        output = self.build()
        self.assertEqual(self.candidate(output, A)[SHARED], b"current shared bytes\n")
        self.assertEqual(self.candidate(output, B)[ALIAS], b"current shared bytes\n")
        self.assertNotIn(SHARED, self.candidate(output, B))
        for pack, source in ((A, SHARED), (B, ALIAS)):
            contents = self.candidate(output, pack)
            for name, data in self.stock[pack].items():
                if name != source:
                    self.assertEqual(contents[name], data)
            with zipfile.ZipFile(output / pack) as archive:
                self.assertIn("empty/", archive.namelist())
        diffs = json.loads((output / "entry-diffs.json").read_text())["packs"]
        self.assertEqual(set(diffs), {A, B})
        self.assertEqual(set(diffs[A]["entries"]), {SHARED})
        self.assertEqual(diffs[A]["entries"][SHARED]["before_sha256"], digest(b"stock\r\n"))

    def test_manifest_hashes_every_regular_entry_and_whole_archive(self):
        output = self.build()
        _, manifest, contents = read_manifest(output)
        self.assertEqual(manifest["source_archive_sha256"], builder.ARCHIVE_SHA256)
        for name, entries in contents.items():
            record = manifest["packs"][name]
            self.assertEqual(record["sha256"], digest((output / name).read_bytes()))
            self.assertEqual(record["entries"], {n: digest(d) for n, d in entries.items()})
            self.assertNotIn("empty/", record["entries"])

    def test_full_new_pack_can_reuse_stock_copies_and_sync_current_source(self):
        files = pack_contents(NEW, {SHARED: b"stock\r\n", FEATURE: b"new feature"})
        self.put_input(NEW, files)
        self.put_source(FEATURE, b"new feature")
        output = self.build()
        self.assertEqual(self.candidate(output, NEW)[SHARED], b"current shared bytes\n")
        self.assertEqual(self.candidate(output, NEW)[FEATURE], b"new feature")
        diff = json.loads((output / "entry-diffs.json").read_text())["packs"][NEW]
        self.assertEqual(diff["status"], "added")
        self.assertTrue(all(r["before_sha256"] is None for r in diff["entries"].values()))

    def test_current_checkout_wins_stale_full_new_pack_source_copies(self):
        self.put_input(NEW, pack_contents(NEW, {SHARED: b"previous candidate source", FEATURE: b"previous header"}))
        self.put_source(FEATURE, b"current header")
        output = self.build()
        self.assertEqual(self.candidate(output, NEW)[FEATURE], b"current header")
        self.assertEqual(self.candidate(output, NEW)[SHARED], b"current shared bytes\n")

    def test_explicit_existing_pack_addition_requires_pdsc_and_input_file(self):
        self.put_source(FEATURE, b"new feature")
        pdsc = ET.fromstring(self.stock[A]["Renesas.RA_mcu_a.pdsc"])
        ET.SubElement(pdsc.find("./components/component/files"), "file", name=FEATURE, category="header")
        self.put_input(A, {"Renesas.RA_mcu_a.pdsc": ET.tostring(pdsc), FEATURE: b"new feature"})
        output = self.build()
        self.assertIn(FEATURE, self.candidate(output, A))
        self.assertNotIn(FEATURE, self.candidate(output, B))

    def test_current_mdf_is_propagated_from_source_root(self):
        name = next(n for n in self.stock[A] if n.startswith(".module_descriptions/"))
        self.put_source(name[1:], b"<raModuleDescription><config id='new'/></raModuleDescription>")
        output = self.build()
        self.assertEqual(self.candidate(output, A)[name], (self.source / name[1:]).read_bytes())

    def test_explicit_shared_override_without_checkout_copy_reaches_every_owner(self):
        (self.source / SHARED).unlink()
        self.put_input(A, {SHARED: b"explicit current bytes"})
        output = self.build()
        self.assertEqual(self.candidate(output, A)[SHARED], b"explicit current bytes")
        self.assertEqual(self.candidate(output, B)[ALIAS], b"explicit current bytes")

    def test_untouched_byte_distinct_stock_owners_stay_distinct(self):
        distinct = "ra/fsp/src/disclaimer.h"
        self.stock[A] = pack_contents(A, {SHARED: b"stock\r\n", distinct: b"licensed"})
        self.stock[B] = pack_contents(B, {ALIAS: b"stock\r\n", distinct: b"placeholder"})
        self.write_release()
        self.put_source(distinct, b"licensed")
        output = self.build()
        self.assertEqual(self.candidate(output, A)[distinct], b"licensed")
        self.assertEqual(self.candidate(output, B)[distinct], b"placeholder")
        self.put_source(distinct, b"new ambiguous bytes")
        with self.assertRaisesRegex(ValueError, "Conflicting original source ownership"):
            self.build()

    def test_disclaimer_only_variants_propagate_checkout_to_every_owner(self):
        self.stock[A][SHARED] = LICENSE + b"int original;\r\n"
        self.stock[B][ALIAS] = PLACEHOLDER + b"int original;\r\n"
        self.write_release()
        current = LICENSE + b"int current;\n"
        self.put_source(SHARED, current)
        self.put_input(A, {SHARED: self.stock[A][SHARED]})
        self.put_input(NEW, pack_contents(NEW, {SHARED: b"stale candidate copy"}))
        output = self.build()
        diffs = json.loads((output / "entry-diffs.json").read_text())["packs"]
        for pack, entry in ((A, SHARED), (B, ALIAS), (NEW, SHARED)):
            self.assertEqual(self.candidate(output, pack)[entry], current)
            before = self.stock[pack][entry] if pack in self.stock else None
            self.assertEqual(diffs[pack]["entries"][entry], {
                "before_sha256": digest(before) if before is not None else None,
                "after_sha256": digest(current)})

    def test_untouched_disclaimer_variants_are_not_unified(self):
        self.stock[A][SHARED] = LICENSE + b"int original;\r\n"
        self.stock[B][ALIAS] = PLACEHOLDER + b"int original;\r\n"
        self.write_release()
        self.put_source(SHARED, self.stock[A][SHARED])
        self.put_input(A, {".mcu/unmodified.bin": b"unrelated pack edit"})
        self.put_input(B, {".mcu/unmodified.bin": b"unrelated pack edit"})
        output = self.build()
        for pack, entry in ((A, SHARED), (B, ALIAS)):
            self.assertEqual(self.candidate(output, pack)[entry], self.stock[pack][entry])
            diff = json.loads((output / "entry-diffs.json").read_text())["packs"][pack]
            self.assertNotIn(entry, diff["entries"])

    def test_disclaimer_variants_do_not_hide_conflicting_explicit_edits(self):
        self.stock[A][SHARED] = LICENSE + b"int original;\r\n"
        self.stock[B][ALIAS] = PLACEHOLDER + b"int original;\r\n"
        self.write_release()
        for current in (self.stock[A][SHARED], LICENSE + b"int current;\r\n"):
            for pack, entry, banner in ((A, SHARED, LICENSE), (B, ALIAS, PLACEHOLDER)):
                with self.subTest(current=current, pack=pack):
                    self.put_source(SHARED, current)
                    folder = self.put_input(pack, {entry: banner + b"int unknown_edit;\r\n"})
                    output = self.root / "blocked"
                    with self.assertRaisesRegex(ValueError, "Conflicting explicit source override"):
                        self.build(output)
                    self.assertFalse(output.exists())
                    shutil.rmtree(folder)

    def test_only_exact_leading_release_banner_variants_can_be_reconciled(self):
        cases = (
            (LICENSE + b"int a;\r\n", PLACEHOLDER + b"int b;\r\n"),
            (LICENSE + b"int a;\r\n", b"/* other license */\r\nint a;\r\n"),
            (LICENSE + b"int a;\r\n", PLACEHOLDER + b"int a;\n"),
            (b"prefix\r\n" + LICENSE, b"prefix\r\n" + PLACEHOLDER),
            (b"/* first comment */\r\nint a;\r\n", b"/* second comment */\r\nint a;\r\n"),
        )
        for left, right in cases:
            with self.subTest(left=left, right=right):
                self.stock[A][SHARED] = left
                self.stock[B][ALIAS] = right
                self.write_release()
                output = self.root / "blocked"
                with self.assertRaisesRegex(ValueError, "Conflicting original source ownership"):
                    self.build(output)
                self.assertFalse(output.exists())

    def test_disclaimer_variants_without_checkout_do_not_authorize_explicit_edits(self):
        self.stock[A][SHARED] = LICENSE + b"int original;\r\n"
        self.stock[B][ALIAS] = PLACEHOLDER + b"int original;\r\n"
        self.write_release()
        (self.source / SHARED).unlink()
        self.put_input(A, {SHARED: LICENSE + b"int unknown_edit;\r\n"})
        output = self.root / "blocked"
        with self.assertRaisesRegex(ValueError, "Conflicting explicit source ownership"):
            self.build(output)
        self.assertFalse(output.exists())

    def test_checkout_support_index_does_not_override_explicit_pack_metadata(self):
        main = "Renesas.RA.5.9.0.pack"
        self.stock[main] = pack_contents(main, {})
        self.write_release()
        support = self.stock[main]["toolingSupport.xml"]
        self.put_source("module_descriptions/toolingSupport.xml", support)
        output = self.build()
        self.assertFalse((output / main).exists())
        current = support.replace(b"</toolingSupport>", b"<!-- authored support -->\n</toolingSupport>")
        self.put_input(main, {"toolingSupport.xml": current})
        output = self.build()
        self.assertEqual(self.candidate(output, main)["toolingSupport.xml"], current)
        self.assertNotIn(".module_descriptions/toolingSupport.xml", self.candidate(output, main))
        unknown = self.put_source("module_descriptions/unowned.xml", b"<raModuleDescription/>")
        with self.assertRaisesRegex(ValueError, "Unknown source ownership"):
            self.build()
        unknown.unlink()
        self.put_source("module_descriptions/toolingSupport.xml", b"<raModuleDescription/>")
        with self.assertRaisesRegex(ValueError, "Expected toolingSupport metadata, not an MDF"):
            self.build()

    def test_conflicting_explicit_override_is_rejected(self):
        self.put_input(A, {SHARED: b"conflicting authored source"})
        with self.assertRaisesRegex(ValueError, "Conflicting explicit source override"):
            self.build()

    def test_conflicting_new_owners_are_rejected(self):
        self.put_input(NEW, pack_contents(NEW, {FEATURE: b"one"}))
        other = "Renesas.RA_board_ra8p1_ek.5.9.0.pack"
        self.put_input(other, pack_contents(other, {FEATURE: b"two"}))
        with self.assertRaisesRegex(ValueError, "Conflicting explicit source ownership"):
            self.build()

    def test_unknown_checkout_source_is_rejected_without_output(self):
        self.put_source(FEATURE, b"not explicitly owned")
        output = self.root / "blocked"
        with self.assertRaisesRegex(ValueError, "Unknown source ownership"):
            self.build(output)
        self.assertFalse(output.exists())

    def test_undeclared_explicit_source_is_rejected(self):
        self.put_input(A, {FEATURE: b"not declared"})
        with self.assertRaisesRegex(ValueError, "Unknown source ownership"):
            self.build()

    def test_missing_new_pack_pdsc_source_is_not_filled_implicitly(self):
        self.put_source(FEATURE, b"available but not explicit")
        contents = pack_contents(NEW, {FEATURE: b"new"})
        del contents[FEATURE]
        self.put_input(NEW, contents)
        with self.assertRaisesRegex(ValueError, "Missing PDSC file"):
            self.build()

    def test_missing_original_pdsc_source_is_rejected(self):
        del self.stock[A][SHARED]
        self.write_release()
        with self.assertRaisesRegex(ValueError, "Missing PDSC file"):
            self.build()

    def test_missing_or_multiple_pdsc_is_rejected(self):
        for extra in (False, True):
            with self.subTest(extra=extra):
                contents = pack_contents(NEW, {FEATURE: b"new"})
                if extra:
                    contents["additional.pdsc"] = b"<package/>"
                else:
                    del contents["Renesas.RA_mcu_ra8p1.pdsc"]
                root = self.put_input(NEW, contents)
                with self.assertRaisesRegex(ValueError, "Expected one PDSC"):
                    self.build()
                shutil.rmtree(root)

    def test_missing_support_and_component_mdf_are_rejected(self):
        contents = pack_contents(NEW, {FEATURE: b"new"})
        del contents["toolingSupport.xml"]
        root = self.put_input(NEW, contents)
        with self.assertRaisesRegex(ValueError, "Missing toolingSupport"):
            self.build()
        (root / "toolingSupport.xml").write_bytes(b'<toolingSupport family="ra"/>')
        with self.assertRaisesRegex(ValueError, "Missing component MDF/support"):
            self.build()

    def test_pack_identity_and_module_version_are_checked(self):
        contents = pack_contents(NEW, {FEATURE: b"new"})
        contents["Renesas.RA_mcu_ra8p1.pdsc"] = contents["Renesas.RA_mcu_ra8p1.pdsc"].replace(b"RA_mcu_ra8p1", b"wrong")
        root = self.put_input(NEW, contents)
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            self.build()
        (root / "Renesas.RA_mcu_ra8p1.pdsc").write_bytes(pack_contents(NEW, {FEATURE: b"new"})["Renesas.RA_mcu_ra8p1.pdsc"])
        support = root / "toolingSupport.xml"
        support.write_bytes(support.read_bytes().replace(b'version="5.9.0"', b'version="6.0.0"'))
        with self.assertRaisesRegex(ValueError, "version mismatch"):
            self.build()

    def test_cross_pack_component_identity_conflict_is_rejected(self):
        contents = pack_contents(NEW, {FEATURE: b"new"}, group="RA_mcu_a")
        self.put_input(NEW, contents)
        with self.assertRaisesRegex(ValueError, "Conflicting component ownership"):
            self.build()

    def test_unknown_pdsc_condition_is_rejected(self):
        contents = pack_contents(NEW, {FEATURE: b"new"})
        pdsc = ET.fromstring(contents["Renesas.RA_mcu_ra8p1.pdsc"])
        pdsc.find("./components/component/files/file").set("condition", "Missing_Compiler")
        contents["Renesas.RA_mcu_ra8p1.pdsc"] = ET.tostring(pdsc)
        self.put_input(NEW, contents)
        with self.assertRaisesRegex(ValueError, "Unknown PDSC condition"):
            self.build()

    def test_component_version_must_match_pack_release(self):
        contents = pack_contents(NEW, {FEATURE: b"new"})
        pdsc = ET.fromstring(contents["Renesas.RA_mcu_ra8p1.pdsc"])
        pdsc.find("./components/component").set("Cversion", "6.0.0")
        contents["Renesas.RA_mcu_ra8p1.pdsc"] = ET.tostring(pdsc)
        self.put_input(NEW, contents)
        with self.assertRaisesRegex(ValueError, "Component version mismatch"):
            self.build()

    def test_duplicate_new_component_is_rejected(self):
        contents = pack_contents(NEW, {FEATURE: b"new"})
        pdsc = ET.fromstring(contents["Renesas.RA_mcu_ra8p1.pdsc"])
        pdsc.find("components").append(pdsc.find("./components/component"))
        contents["Renesas.RA_mcu_ra8p1.pdsc"] = ET.tostring(pdsc)
        self.put_input(NEW, contents)
        with self.assertRaisesRegex(ValueError, "Duplicate component identity"):
            self.build()

    def test_malformed_or_entity_xml_is_rejected(self):
        path = "Renesas.RA_mcu_a.pdsc"
        for value in (b"<package", b'<!DOCTYPE package [<!ENTITY x "x">]><package/>'):
            with self.subTest(value=value):
                self.put_input(A, {path: value})
                with self.assertRaises(ValueError):
                    self.build()

    def test_unsafe_original_pack_entry_paths_are_rejected(self):
        for path in ("../escape", "/absolute", "a\\b", "a//b", "C:drive", "a/./b", "control\nfile"):
            with self.subTest(path=path):
                self.stock[A][path] = b"bad"
                self.write_release()
                with self.assertRaisesRegex(ValueError, "Unsafe path"):
                    self.build()
                del self.stock[A][path]

    def test_unsafe_pdsc_reference_is_rejected(self):
        contents = pack_contents(NEW, {"../escape": b"bad"})
        del contents["../escape"]
        self.put_input(NEW, contents)
        with self.assertRaisesRegex(ValueError, "Unsafe path"):
            self.build()

    def test_unsafe_outer_archive_entry_is_rejected(self):
        self.write_release(extra=(("../escape", b"bad"),))
        with self.assertRaisesRegex(ValueError, "Unsafe path"):
            self.build()

    def test_zip_symlinks_duplicates_and_file_directory_collisions_are_rejected(self):
        link = zipfile.ZipInfo("symbolic")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        for extras, message in ((((link, b"target"),), "Unsupported archive entry"),
                                ((("same", b"one"), ("same", b"two")), "Duplicate archive path"),
                                ((("parent", b"file"), ("parent/child", b"file")), "collision")):
            with self.subTest(message=message):
                entries = {builder.PACK_PREFIX + A: zip_bytes(self.stock[A], extras)}
                raw = zip_bytes(entries)
                self.archive.write_bytes(raw)
                builder.ARCHIVE_SHA256 = digest(raw)
                with self.assertRaisesRegex(ValueError, message):
                    self.build()

    def test_symlinked_inputs_and_output_are_rejected(self):
        source = self.source / SHARED
        original = source.read_bytes()
        source.unlink()
        source.symlink_to(self.archive)
        with self.assertRaisesRegex(ValueError, "Non-regular input"):
            self.build()
        source.unlink()
        source.write_bytes(original)
        link = self.inputs / "Renesas.RA_mcu_link.5.9.0"
        link.symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symlinked path"):
            self.build()
        link.unlink()
        output = self.root / "output-link"
        output.symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symlinked path"):
            self.build(output)

    def test_input_special_files_and_nested_symlink_directory_are_rejected(self):
        tree = self.put_input(A, {"marker": b"marker"})
        (tree / "linked").symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Non-regular input"):
            self.build()
        (tree / "linked").unlink()
        os.mkfifo(tree / "pipe")
        with self.assertRaisesRegex(ValueError, "Non-regular input"):
            self.build()

    def test_existing_revision_is_never_changed(self):
        output = self.build()
        before = {p.name: p.read_bytes() for p in output.iterdir()}
        self.put_source(SHARED, b"another revision")
        with self.assertRaisesRegex(ValueError, "Immutable output already exists"):
            self.build(output)
        self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})

    def test_output_inside_inputs_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "separate from input trees"):
            self.build(self.source / "output")
        with self.assertRaisesRegex(ValueError, "separate from input trees"):
            self.build(self.inputs / "output")

    def test_release_hash_is_pinned_before_pack_reading(self):
        self.archive.write_bytes(self.archive.read_bytes() + b"corrupt")
        with self.assertRaisesRegex(ValueError, "Release archive hash mismatch"):
            self.build()

    def test_no_changes_does_not_emit_empty_manifest(self):
        self.put_source(SHARED, b"stock\r\n")
        with self.assertRaisesRegex(ValueError, "No candidate changes"):
            self.build()

    def test_failed_serialization_leaves_no_partial_revision(self):
        output = self.root / "failed"
        with patch.object(builder, "write_pack", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.build(output)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.root.glob(".ra8p1-packs-*")))


class OriginalReleaseTests(unittest.TestCase):
    def test_original_disclaimer_variants_and_all_16_threadx_sources_propagate(self):
        archive = builder.ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip"
        if not archive.is_file():
            self.skipTest("Original release archive is not materialized")
        with ExitStack() as stack:
            packs = builder.load_release(archive, stack)
            references = {n: builder.inspect_pack(p) for n, p in packs.items()}
            owners = builder.ownership(packs, references)
            variants = {source for source, targets in owners.items()
                        if len({packs[p].original(e) for p, e in targets}) > 1}
            self.assertEqual(variants, {
                "ra/fsp/src/rm_netx_secure_crypto/inc/crypto_common/nx_crypto.h",
                "ra/fsp/src/rm_netx_secure_crypto/inc/rm_netx_secure_crypto.h",
                "ra/fsp/src/rm_threadx_port/tx_port_vendor.h",
                "ra/fsp/src/rm_threadx_port/tx_port_wait_thread_ready.c"})
            threadx = {source for source in owners
                       if source.startswith("ra/fsp/src/rm_threadx_port/") and source.endswith(".c")}
            self.assertEqual(len(threadx), 16)
            sources, originals = {}, {}
            for source in sorted(variants | threadx):
                # Select a named authoritative fixture, never an arbitrary owner.
                sources[source] = (packs["Renesas.RA.5.9.0.pack"].original(source)
                                   + b"\r\n/* host-only construction fixture */\r\n")
                originals[source] = {(p, e): packs[p].original(e) for p, e in owners[source]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            checkout = root / "baseline"
            inputs = root / "inputs"
            inputs.mkdir()
            for source, data in sources.items():
                path = checkout / source
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            output = root / "revision"
            builder.build(archive, checkout, inputs, output)
            _, manifest, contents = read_manifest(output)
            diffs = json.loads((output / "entry-diffs.json").read_text())["packs"]
            expected_packs = {p for targets in originals.values() for p, e in targets}
            self.assertEqual(set(manifest["packs"]), expected_packs)
            for source, targets in originals.items():
                for (pack, entry), before in targets.items():
                    self.assertEqual(contents[pack][entry], sources[source])
                    self.assertEqual(diffs[pack]["entries"][entry], {
                        "before_sha256": digest(before), "after_sha256": digest(sources[source])})

    def test_original_shared_change_updates_all_32_mcu_packs(self):
        archive = builder.ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip"
        if not archive.is_file():
            self.skipTest("Original release archive is not materialized")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "baseline"
            inputs = root / "inputs"
            inputs.mkdir()
            path = source / SHARED
            path.parent.mkdir(parents=True)
            path.write_bytes(b"/* host-only construction fixture */\n")
            output = root / "revision"
            builder.build(archive, source, inputs, output)
            _, manifest, contents = read_manifest(output)
            self.assertEqual(len(manifest["packs"]), 32)
            self.assertTrue(all(".RA_mcu_" in n for n in manifest["packs"]))
            for files in contents.values():
                entry = SHARED if SHARED in files else ALIAS
                self.assertEqual(files[entry], path.read_bytes())

    def test_verified_original_has_124_accepted_packs(self):
        # Exercise the actual pinned input as well as adversarial tiny fixtures.
        archive = builder.ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip"
        if not archive.is_file():
            self.skipTest("Original release archive is not materialized")
        with ExitStack() as stack:
            packs = builder.load_release(archive, stack)
            self.assertEqual(len(packs), 124)
            references = {n: builder.inspect_pack(p) for n, p in packs.items()}
            owners = builder.ownership(packs, references)
            shared = owners[SHARED]
            self.assertEqual(len(shared), 32)


if __name__ == "__main__":
    unittest.main()
