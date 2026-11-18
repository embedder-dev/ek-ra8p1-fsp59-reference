"""HDR-R02 admission checks against independent native C layout observations."""

import copy
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "ra8p1_alignment_generator", ROOT / "tools/ra8p1/generate_device_header.py")
GEN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GEN)
SOURCE = "Synthetic layout fixture §1 p. 1"


def raw_member(offset=0, count=4):
    return {"name": "RAW", "offset": offset, "width": 8, "access": "R/W",
            "count": count, "source": SOURCE,
            "views": [{"name": "WORD", "offset": 0, "width": 32, "access": "R/W"}]}


def block(members, size, name="Probe_Type"):
    return {"name": name, "size": size, "source": SOURCE, "members": members}


def inventory(*blocks):
    return {"schema": 1, "device": "R7KA8P1KF", "types": list(blocks),
            "instances": [], "cores": []}


class GeneratorAlignmentTests(unittest.TestCase):
    def native_layout(self, blocks, expressions):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("No native C compiler")
        # render_type deliberately bypasses admission to expose the C layout of
        # invalid inputs, rather than relying on validate's own arithmetic.
        source = "\n".join([
            "#include <stdint.h>", "#include <stddef.h>", "#include <stdio.h>",
            "#define __IM volatile const", "#define __OM volatile", "#define __IOM volatile",
            *["\n".join(GEN.render_type(item)) for item in blocks],
            "int main(void) {",
            *[f'    printf("%zu\\n", (size_t) ({expr}));' for expr in expressions],
            "    return 0;", "}", ""])
        with tempfile.TemporaryDirectory(prefix="ra8p1-alignment-") as tmp:
            src, exe = Path(tmp) / "layout.c", Path(tmp) / "layout"
            src.write_text(source)
            result = subprocess.run(
                [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", str(src), "-o", str(exe)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return tuple(int(value) for value in result.stdout.splitlines())

    def test_reject_byte_array_at_offset_one_with_word_view(self):
        probe = block([raw_member(offset=1)], size=5)
        self.assertEqual((4, 4, 8), self.native_layout([probe], [
            "offsetof(Probe_Type, RAW)", "offsetof(Probe_Type, WORD)", "sizeof(Probe_Type)"]))
        with self.assertRaisesRegex(ValueError, "misaligned"):
            GEN.validate(inventory(probe))

    def test_reject_byte_array_at_odd_offset_with_halfword_view(self):
        reg = raw_member(offset=1, count=2)
        reg["views"][0].update(name="HALF", width=16)
        probe = block([reg], size=3)
        self.assertEqual((2, 2, 4), self.native_layout([probe], [
            "offsetof(Probe_Type, RAW)", "offsetof(Probe_Type, HALF)", "sizeof(Probe_Type)"]))
        with self.assertRaisesRegex(ValueError, "misaligned"):
            GEN.validate(inventory(probe))

    def test_reject_union_tail_padding_even_with_room_in_block(self):
        for width, count in ((16, 3), (32, 5), (32, 6)):
            with self.subTest(width=width, count=count):
                reg = raw_member(count=count)
                reg["views"][0]["width"] = width
                probe = block([reg], size=4 if width == 16 else 8)
                # render_type adds explicit padding after the raw span, but C
                # has already rounded up the union: its sizeof exceeds the spec.
                self.assertEqual((6 if width == 16 else 12,),
                                 self.native_layout([probe], ["sizeof(Probe_Type)"]))
                with self.assertRaisesRegex(ValueError, "extent"):
                    GEN.validate(inventory(probe))

    def test_reject_union_extent_that_would_shift_following_byte(self):
        tail = {"name": "TAIL", "offset": 5, "width": 8, "access": "R/W", "source": SOURCE}
        probe = block([raw_member(count=5), tail], size=8)
        self.assertEqual((8, 12), self.native_layout([probe], [
            "offsetof(Probe_Type, TAIL)", "sizeof(Probe_Type)"]))
        with self.assertRaisesRegex(ValueError, "extent"):
            GEN.validate(inventory(probe))

    def test_reject_trailing_block_extent_not_multiple_of_view_alignment(self):
        probe = block([raw_member()], size=5)
        self.assertEqual((8,), self.native_layout([probe], ["sizeof(Probe_Type)"]))
        with self.assertRaisesRegex(ValueError, "type extent"):
            GEN.validate(inventory(probe))

    def test_reject_misaligned_nested_array_through_type_alias(self):
        child = block([raw_member()], size=4, name="Child_Type")
        child["aliases"] = ["ChildAlias_Type"]
        nested = {"name": "CHILD", "offset": 1, "type": "ChildAlias_Type",
                  "element_size": 4, "count": 2, "source": SOURCE}
        parent = block([nested], size=9)
        self.assertEqual((4, 8, 12), self.native_layout([child, parent], [
            "offsetof(Probe_Type, CHILD[0].WORD)", "offsetof(Probe_Type, CHILD[1].WORD)",
            "sizeof(Probe_Type)"]))
        with self.assertRaisesRegex(ValueError, "misaligned"):
            GEN.validate(inventory(child, parent))

    def test_reject_nested_type_trailing_extent(self):
        child = block([raw_member()], size=4, name="Child_Type")
        nested = {"name": "CHILD", "offset": 0, "type": "Child_Type",
                  "element_size": 4, "count": 2, "source": SOURCE}
        parent = block([nested], size=9)
        self.assertEqual((4, 12), self.native_layout([child, parent], [
            "offsetof(Probe_Type, CHILD[1].WORD)", "sizeof(Probe_Type)"]))
        with self.assertRaisesRegex(ValueError, "type extent"):
            GEN.validate(inventory(child, parent))

    def test_valid_wider_array_views_aliases_fields_and_individuals(self):
        reg = raw_member(offset=4, count=8)
        reg["aliases"] = ["RAW_ALIAS"]
        reg["fields"] = [{"name": "FLAG", "pos": 0, "bits": 1, "access": "R/W"}]
        reg["individual_names"] = [None, "BYTE1", None, None, None, None, None, None]
        reg["views"][0].update(count=2, fields=[
            {"name": "ENABLE", "pos": 31, "bits": 1, "access": "R/W"}])
        reg["views"].extend([
            {"name": "HALF", "offset": 2, "width": 16, "access": "R"},
            {"name": "BYTE", "offset": 7, "width": 8, "access": "R"}])
        tail = {"name": "TAIL", "offset": 12, "width": 8, "access": "R/W", "source": SOURCE}
        probe = block([reg, tail], size=16)
        GEN.validate(inventory(probe))
        self.assertEqual(4, probe["alignment"])
        self.assertEqual((4, 4, 4, 8, 8, 6, 11, 5, 12, 4, 16),
                         self.native_layout([probe], [
                             "offsetof(Probe_Type, RAW)", "offsetof(Probe_Type, RAW_ALIAS)",
                             "offsetof(Probe_Type, WORD)", "offsetof(Probe_Type, WORD[1])",
                             "offsetof(Probe_Type, WORD_b[1])", "offsetof(Probe_Type, HALF)",
                             "offsetof(Probe_Type, BYTE)", "offsetof(Probe_Type, BYTE1)",
                             "offsetof(Probe_Type, TAIL)", "_Alignof(Probe_Type)", "sizeof(Probe_Type)"]))

    def test_valid_nested_alias_array_uses_view_alignment(self):
        child = block([raw_member(offset=4)], size=8, name="Child_Type")
        child["aliases"] = ["ChildAlias_Type"]
        nested = {"name": "CHILD", "offset": 8, "type": "ChildAlias_Type",
                  "element_size": 8, "count": 2, "source": SOURCE}
        tail = {"name": "TAIL", "offset": 24, "width": 8, "access": "R/W", "source": SOURCE}
        parent = block([nested, tail], size=28)
        GEN.validate(inventory(child, parent))
        self.assertEqual((4, 4), (child["alignment"], parent["alignment"]))
        self.assertEqual((8, 12, 20, 24, 28), self.native_layout([child, parent], [
            "sizeof(Child_Type)", "offsetof(Probe_Type, CHILD[0].WORD)",
            "offsetof(Probe_Type, CHILD[1].WORD)", "offsetof(Probe_Type, TAIL)", "sizeof(Probe_Type)"]))

    def test_instance_base_must_follow_wider_view_alignment(self):
        for base in (0x40000004, 0x40000002):
            with self.subTest(base=base):
                data = inventory(block([raw_member()], size=4))
                data["instances"] = [{"name": "R_PROBE", "type": "Probe_Type", "secure": base,
                                      "source": SOURCE}]
                if base % 4:
                    with self.assertRaisesRegex(ValueError, "peripheral base"):
                        GEN.validate(data)
                else:
                    GEN.validate(data)

    def test_invalid_relative_view_offsets_and_spans_still_rejected(self):
        for changes in ({"offset": 1}, {"count": 3}, {"offset": -4}):
            with self.subTest(changes=changes):
                reg = raw_member(count=8)
                reg["views"][0].update(changes)
                with self.assertRaisesRegex(ValueError, "View exceeds register"):
                    GEN.validate(inventory(block([reg], size=8)))

    def test_odd_byte_array_without_wider_view_remains_valid(self):
        reg = raw_member(offset=1, count=5)
        reg.pop("views")
        probe = block([reg], size=7)
        GEN.validate(inventory(probe))
        self.assertEqual(1, probe["alignment"])
        self.assertEqual((1, 7), self.native_layout([probe], [
            "offsetof(Probe_Type, RAW)", "sizeof(Probe_Type)"]))

    def test_full_current_inventory_render_matches_existing_header_bytes(self):
        data = GEN.load_inventory()
        GEN.validate(copy.deepcopy(data))
        rendered = GEN.render(data).replace("\n", "\r\n").encode("utf-8")
        self.assertEqual(GEN.DEFAULT_OUTPUT.read_bytes(), rendered)


if __name__ == "__main__":
    unittest.main()
