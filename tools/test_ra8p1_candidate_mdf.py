"""Current owning MDF checks, independent of boot and pack-construction fixtures."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from fsp_manifest import digest
from ra8p1 import verify_candidate as verifier


class OwningMdfTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.baseline = self.root / "baseline"
        self.project = self.root / "project"
        self.pack = "Renesas.RA_mcu_ra8p1.5.9.0.pack"
        self.mdf = ".module_descriptions/Renesas##BSP##ra8p1##fsp####5.9.0.xml"
        self.source = "ra/fsp/src/fixture.c"
        self.third_party = "ra/third_party/library.c"
        self.entries = {self.mdf: b"<raModuleDescription version='current'/>",
                        self.source: b"int current;\n", self.third_party: b"int library;\n"}
        pdsc = ET.Element("package")
        component = ET.SubElement(ET.SubElement(pdsc, "components"), "component",
                                  Cclass="BSP", Cgroup="ra8p1", Csub="fsp", Cversion="5.9.0")
        files = ET.SubElement(component, "files")
        for source in (self.source, self.third_party):
            ET.SubElement(files, "file", name=source, category="source")
            self.put(self.project, source, self.entries[source])
        self.entries["Renesas.RA_mcu_ra8p1.pdsc"] = ET.tostring(pdsc)
        configuration = ET.Element("raConfiguration")
        selected = ET.SubElement(ET.SubElement(configuration, "raComponentSelection"), "component",
                                 **{"class": "BSP", "group": "ra8p1", "subgroup": "fsp", "version": "5.9.0"})
        ET.SubElement(selected, "originalPack").text = self.pack
        self.put(self.project, "configuration.xml", ET.tostring(configuration))
        self.put(self.baseline, self.mdf[1:], self.entries[self.mdf])
        self.put(self.baseline, self.source, self.entries[self.source])
        self.manifest = {"packs": {self.pack: {"entries": {entry: digest(data)
                                                        for entry, data in self.entries.items()}}}}
        self.contents = {self.pack: self.entries}

    def put(self, root, relative, data):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def baseline_check(self):
        return verifier.check_baseline(self.baseline, self.manifest, self.contents)

    def project_check(self):
        return verifier.check_project_sources(self.project, self.baseline, self.manifest,
                                              self.contents, {}, {})

    def test_matching_owning_mdf_is_required_without_owning_third_party_inputs(self):
        checked, accepted = self.baseline_check()
        self.assertEqual(checked, {self.source, self.mdf[1:]})
        self.assertEqual(accepted, {})
        self.assertFalse((self.baseline / self.third_party).exists())
        self.assertEqual(self.project_check()["checked_sources"], 2)
        self.assertFalse((self.project / self.mdf[1:]).exists())

    def test_missing_owning_mdf_is_not_silently_skipped(self):
        (self.baseline / self.mdf[1:]).unlink()
        with self.assertRaisesRegex(ValueError, "owning baseline MDF"):
            self.baseline_check()

    def test_directory_cannot_stand_in_for_owning_mdf(self):
        path = self.baseline / self.mdf[1:]
        path.unlink()
        path.mkdir()
        with self.assertRaisesRegex(ValueError, "owning baseline MDF"):
            self.baseline_check()

    def test_symlinked_owning_mdf_is_rejected(self):
        path = self.baseline / self.mdf[1:]
        path.unlink()
        path.symlink_to(self.put(self.root, "outside.xml", self.entries[self.mdf]))
        for check in (self.baseline_check, self.project_check):
            with self.subTest(check=check.__name__), self.assertRaisesRegex(ValueError, "Symlinked"):
                check()

    def test_mdf_must_match_current_owner_even_with_proven_original_variants(self):
        old = b"<raModuleDescription version='old'/>"
        self.put(self.baseline, self.mdf[1:], old)
        originals = {self.mdf[1:]: {(self.pack, self.mdf): digest(self.entries[self.mdf]),
                                   ("Other.Original.5.9.0.pack", self.mdf): digest(old)}}
        with patch.object(verifier, "original_source_hashes", return_value=originals):
            with self.assertRaisesRegex(ValueError, "owning baseline MDF"):
                self.baseline_check()

    def test_selected_pack_mdf_is_rechecked_after_initial_baseline_validation(self):
        path = self.baseline / self.mdf[1:]
        for mutation in ("missing", "stale", "directory"):
            with self.subTest(mutation=mutation):
                self.put(self.baseline, self.mdf[1:], self.entries[self.mdf])
                self.baseline_check()
                path.unlink()
                if mutation == "stale":
                    path.write_bytes(b"<raModuleDescription edited='true'/>")
                elif mutation == "directory":
                    path.mkdir()
                with self.assertRaisesRegex(ValueError, "owning baseline MDF"):
                    self.project_check()
                if path.is_dir():
                    path.rmdir()

    def test_unrelated_pack_resources_need_not_exist_in_checkout(self):
        unrelated = "ThirdParty.Library.5.9.0.pack"
        resources = {"ra/third_party/unused.c": b"int unused;\n", "documentation/library.txt": b"manual"}
        self.contents[unrelated] = resources
        self.manifest["packs"][unrelated] = {"entries": {entry: digest(data) for entry, data in resources.items()}}
        self.assertEqual(self.baseline_check()[0], {self.source, self.mdf[1:]})
        self.assertEqual(self.project_check()["checked_sources"], 2)


if __name__ == "__main__":
    unittest.main()
