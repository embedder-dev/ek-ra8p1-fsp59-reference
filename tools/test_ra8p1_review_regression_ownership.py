"""Independent fail-closed owner and parent-qualified MDF regression controls."""
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from ra8p1 import regression, stock_regression


ROOT = Path(__file__).resolve().parents[1]
CANFD = ".module_descriptions/Renesas##HAL Drivers##all##r_canfd####5.9.0.xml"
RELEASE_SHA256 = "99c4abae6239a68171fcbff86070971f591f0a8945e90a50eb07d87843bee363"


class CurrentOwnerTests(unittest.TestCase):
    def write_owner(self, root, name, data):
        owner = root / "baseline" / name
        owner.parent.mkdir(parents=True, exist_ok=True)
        owner.write_bytes(data)
        return owner

    def test_missing_or_nonfile_original_header_and_sources_fail_closed(self):
        for suffix in (".h", ".c", ".S", ".s"):
            for directory in (False, True):
                with self.subTest(suffix=suffix, directory=directory), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    name = "ra/fsp/src/owner/input" + suffix
                    if directory:
                        (root / "baseline" / name).mkdir(parents=True)
                    with self.assertRaisesRegex(ValueError, "Missing current owning input: " + re.escape(name)):
                        stock_regression.changed_inputs(root, {name: b"original"})

    def test_changed_inputs_preserve_bytes_and_ignore_non_fsp_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = {"ra/fsp/inc/unchanged.h": b"unchanged", "ra/fsp/src/changed.c": b"original",
                        "ra/aws/kernel.h": b"not an FSP owner", "ra/fsp/notes.txt": b"not compiled"}
            self.write_owner(root, "ra/fsp/inc/unchanged.h", b"unchanged")
            self.write_owner(root, "ra/fsp/src/changed.c", b"current")
            self.assertEqual(stock_regression.changed_inputs(root, original),
                             {"ra/fsp/src/changed.c": (b"original", b"current")})

    def fixture_inputs(self, root):
        path = stock_regression.ICU
        original = {path: b"original source"}
        self.write_owner(root, path, b"current source")
        candidate, log, archive = root / "candidate.json", root / "build.log", root / "fixture.tar.gz"
        candidate.write_text('{"packs": {}}')
        log.write_bytes(b"verified: yes\nclean: ok\n")
        archive.write_bytes(b"immutable fixture archive")
        spec = {"group": "RA4M1", "checks": 0, "archive": archive.name,
                "sha256": regression.sha256(archive.read_bytes()), "build_log": log.name,
                "build_log_sha256": regression.sha256(log.read_bytes()),
                "candidate_manifest_sha256": regression.sha256(candidate.read_bytes()),
                "required_translation_units": [path]}
        entry = {"success": True, "current_generated_build_verified": True,
                 "group": spec["group"], "checks": spec["checks"], "archive_sha256": spec["sha256"],
                 "candidate_manifest_sha256": spec["candidate_manifest_sha256"],
                 "owning_source_overlay": {path: {"pristine_sha256": regression.sha256(original[path]),
                     "candidate_sha256": regression.sha256(b"current source"), "owner_matches_generated": True}},
                 "translation_units": {path: {"matches_pristine": True, "matches_candidate_capture": True,
                     "command": [__file__], "compiler_sha256": regression.sha256(Path(__file__).read_bytes())}}}
        manifest = root / "fixtures.json"
        manifest.write_text(json.dumps({"candidate_manifest": candidate.name, "fixtures": {"control": spec}}))
        historical = root / regression.MANIFEST
        historical.parent.mkdir(parents=True, exist_ok=True)
        historical.write_text(json.dumps({"compiler_version": "13.2.1", "final_generated": {"projects": {}}}))
        return original, candidate, manifest, spec, entry

    def test_deleted_unchanged_owner_blocks_fresh_and_reused_reports(self):
        for suffix in (".h", ".c"):
            for reuse in (False, True):
                with self.subTest(suffix=suffix, reuse=reuse), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    original, _, manifest, _, entry = self.fixture_inputs(root)
                    name = "ra/fsp/src/owner/unchanged" + suffix
                    original[name] = b"unchanged original input"
                    owner = self.write_owner(root, name, original[name])
                    with patch.object(stock_regression, "original_files", return_value=original), \
                            patch.object(stock_regression, "check_fixture", return_value=entry), \
                            patch.object(stock_regression, "coverage_gaps", return_value=([], [], [])), \
                            patch.object(stock_regression, "review_metadata", return_value={"success": True}):
                        report = stock_regression.regress(root, manifest)
                        self.assertTrue(report["success"])
                        previous = root / "previous.json"
                        previous.write_text(json.dumps(report))
                        owner.unlink()
                        with self.assertRaisesRegex(ValueError, "Missing current owning input: " + re.escape(name)):
                            stock_regression.regress(root, manifest, reuse_report=previous if reuse else None)

    def test_owner_deleted_during_comparison_fails_final_stability_check(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original, _, manifest, _, entry = self.fixture_inputs(root)
            name = "ra/fsp/inc/unchanged.h"
            original[name] = b"unchanged header"
            owner = self.write_owner(root, name, original[name])

            def compare(*args, **kwargs):
                owner.unlink()
                return entry

            with patch.object(stock_regression, "original_files", return_value=original), \
                    patch.object(stock_regression, "check_fixture", side_effect=compare), \
                    patch.object(stock_regression, "coverage_gaps", return_value=([], [], [])), \
                    patch.object(stock_regression, "review_metadata", return_value={"success": True}):
                with self.assertRaisesRegex(ValueError, "Missing current owning input: " + re.escape(name)):
                    stock_regression.regress(root, manifest)

    def test_reuse_missing_recorded_owner_has_precise_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, candidate, _, spec, entry = self.fixture_inputs(root)
            with self.assertRaisesRegex(ValueError, "Missing reusable owning input: " + re.escape(stock_regression.ICU)):
                stock_regression.reuse_fixture(root, spec, entry, {}, candidate)

    def test_reuse_with_unchanged_owner_snapshot_still_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original, candidate, _, spec, entry = self.fixture_inputs(root)
            result = stock_regression.reuse_fixture(root, spec, entry,
                                                   stock_regression.changed_inputs(root, original), candidate)
            self.assertTrue(result["reused_unchanged_inputs"])


class QualifiedOptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        archive = ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip"
        if regression.sha256(archive.read_bytes()) != RELEASE_SHA256:
            raise AssertionError("Original FSP 5.9 release archive identity drift")
        with zipfile.ZipFile(archive) as release:
            with zipfile.ZipFile(io.BytesIO(release.read("internal/projectgen/ra/packs/Renesas.RA.5.9.0.pack"))) as pack:
                cls.original = pack.read(CANFD)

    def test_original_vendor_repeated_ids_with_distinct_values_are_valid(self):
        tree = ET.fromstring(self.original)
        enabled = tree.findall(".//option[@id='config.driver.canfd.rxfifo.0.enable.enabled']")
        self.assertEqual([element.get("value") for element in enabled], ["(R_CANFD_CFDGCFG_DCE_Msk)", "(1)"])
        self.assertTrue(stock_regression.shared_metadata_invariants(
            CANFD, self.original, self.original)["option_values_unchanged"])

    def test_actual_canfd_cross_property_enabled_values_cannot_be_swapped(self):
        tree = ET.fromstring(self.original)
        enabled = tree.findall(".//option[@id='config.driver.canfd.rxfifo.0.enable.enabled']")
        first, second = [element.get("value") for element in enabled]
        enabled[0].set("value", second)
        enabled[1].set("value", first)
        with self.assertRaisesRegex(ValueError, "shared MDF value drift"):
            stock_regression.shared_metadata_invariants(CANFD, self.original, ET.tostring(tree))

    def test_option_ownership_includes_full_config_module_and_enum_ancestry(self):
        bodies = [
            '<config path="first.h"><property id="p" default="o">{first}</property></config>'
            '<config path="second.h"><property id="p" default="o">{second}</property></config>',
            '<module id="first"><property id="p" default="o">{first}</property></module>'
            '<module id="second"><property id="p" default="o">{second}</property></module>',
            '<module id="m"><enum id="first">{first}</enum><enum id="second">{second}</enum></module>',
        ]
        for body in bodies:
            with self.subTest(body=body):
                first, second = '<option id="o" value="1"/>', '<option id="o" value="2"/>'
                original = ('<root>' + body.format(first=first, second=second) + '</root>').encode()
                swapped = ('<root>' + body.format(first=second, second=first) + '</root>').encode()
                self.assertTrue(stock_regression.shared_metadata_invariants(
                    CANFD, original, original)["option_values_unchanged"])
                with self.assertRaisesRegex(ValueError, "shared MDF value drift"):
                    stock_regression.shared_metadata_invariants(CANFD, original, swapped)

    def test_repeated_identical_options_retain_multiplicity(self):
        option = '<option id="o" value="1"/>'
        template = '<root><property id="p" default="o">{}</property></root>'
        original = template.format(option * 2).encode()
        self.assertTrue(stock_regression.shared_metadata_invariants(
            CANFD, original, original)["option_values_unchanged"])
        with self.assertRaisesRegex(ValueError, "shared MDF value drift"):
            stock_regression.shared_metadata_invariants(CANFD, original, template.format(option).encode())

    def test_additive_options_properties_and_capability_constraints_remain_valid(self):
        tree = ET.fromstring(self.original)
        prop = tree.find(".//property[@id='config.driver.canfd.dlc_check']")
        ET.SubElement(prop, "option", {"id": "new.option", "value": "target-only"})
        config = tree.find(".//config")
        added = ET.SubElement(config, "property", {"id": "new.property", "default": "off"})
        ET.SubElement(added, "option", {"id": "off", "value": "0"})
        module = tree.find(".//module")
        ET.SubElement(module, "constraint", {"display": "Target capability"}).text = (
            '!testExists("${interface.mcu.adc_b.adc16h}") || target_only')
        result = stock_regression.shared_metadata_invariants(
            CANFD, self.original, ET.tostring(tree),
            legacy_proof={"absent_interfaces": ("interface.mcu.adc_b.adc16h",)})
        self.assertTrue(result["defaults_unchanged"])
        self.assertTrue(result["option_values_unchanged"])
        self.assertEqual(result["added_constraints"], 1)


class TargetOnlyMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.historical = json.loads((ROOT / regression.MANIFEST).read_text())
        cls.original = regression.stock_packs(ROOT, cls.historical)["Renesas.RA"][1]
        cls.manifest = ROOT / "validation/ra8p1/packs/r016/manifest.json"
        cls.review = stock_regression.review_metadata(ROOT, cls.historical, cls.manifest)
        cls.proof = cls.review["legacy_selector_proof"]
        cls.rxie = [stock_regression.xml_contract(e) for e in ET.fromstring(
            cls.original[stock_regression.DSI_MDF]).findall(
                ".//property[@id='module.driver.mipi_dsi.rxie']/option")]
        cls.packs = {}
        for basename in json.loads(cls.manifest.read_text())["packs"]:
            if "RA_mcu_" not in basename and basename != "Renesas.RA.5.9.0.pack":
                continue
            with zipfile.ZipFile(cls.manifest.parent / basename) as package:
                cls.packs[basename] = {name: package.read(name) for name in package.namelist()
                                       if name.startswith(".module_descriptions/") or name.endswith(
                                           ("/bsp_feature.h", "/bsp_peripheral.h", "/r_adc_b.h", "/R7FA6T2BD.h"))}

    def mdf(self, driver):
        path = ".module_descriptions/Renesas##HAL Drivers##all##" + driver + "####5.9.0.xml"
        return path, self.original[path], self.packs["Renesas.RA.5.9.0.pack"][path]

    def check(self, driver, current=None, *, proof=True):
        path, original, frozen = self.mdf(driver)
        return stock_regression.shared_metadata_invariants(
            path, original, frozen if current is None else current,
            legacy_proof=self.proof if proof else None,
            rxie_options=self.rxie if driver == "r_mipi_dsi" else None)

    def test_actual_r016_all_405_contracts_and_all_32_legacy_selectors(self):
        self.assertTrue(self.review["success"])
        self.assertEqual(len(self.review["shared_defaults"]) + len(self.review["old_metadata"]), 405)
        self.assertEqual(len(self.proof["devices"]), 32)
        self.assertEqual(tuple(self.proof["zero_macros"]), stock_regression.METADATA_ZERO)
        self.assertEqual(tuple(self.proof["absent_interfaces"]), stock_regression.METADATA_ABSENT)
        self.assertTrue(self.proof["adc_gain_aliases_verified"])
        self.assertTrue(all(row["original_capabilities_preserved"] > 100 for row in self.proof["devices"].values()))

    def test_actual_reviewed_templates_need_the_header_and_interface_proof(self):
        for driver in ("r_adc_b", "r_agt", "r_glcdc", "r_i3c", "r_icu", "r_ioport", "r_mipi_dsi", "r_ospi_b", "r_sci_b_spi"):
            with self.subTest(driver=driver):
                self.assertTrue(self.check(driver)["defaults_unchanged"])
                with self.assertRaises(ValueError):
                    self.check(driver, proof=False)

    def test_actual_legacy_callback_signature_and_dispatch_mutations_fail(self):
        _, _, frozen = self.mdf("r_adc_b")
        for old, new in (("void const *const p_context", "void *p_context"),
                         ("return R_ADC_B_CallbackSet(", "return R_ADC_B_Close("),
                         ("p_callback_checked, p_context, p_callback_memory_checked", "p_callback, p_context, p_callback_memory_checked")):
            tree = ET.fromstring(frozen)
            template = tree.find(".//guard/template")
            self.assertIn(old, template.text)
            template.text = template.text.replace(old, new)
            with self.subTest(mutation=new), self.assertRaisesRegex(ValueError, "shared MDF guard drift"):
                self.check("r_adc_b", ET.tostring(tree))

    def test_legacy_callback_guard_attributes_and_other_emitted_contracts_fail(self):
        _, _, frozen = self.mdf("r_agt")
        for tag in ("guard", "nsc", "signal", "content", "declarations"):
            tree = ET.fromstring(frozen)
            element = tree.find(".//" + tag)
            self.assertIsNotNone(element)
            element.set("hidden_mutation", "1")
            with self.subTest(tag=tag), self.assertRaisesRegex(ValueError, "shared MDF"):
                self.check("r_agt", ET.tostring(tree))

    def test_added_guard_is_not_ignored_even_if_its_body_is_target_only(self):
        _, _, frozen = self.mdf("r_agt")
        tree = ET.fromstring(frozen)
        ET.SubElement(tree.find("module"), "guard").text = (
            "#if BSP_FEATURE_AGT_REGISTER_TYPE == 1\nnew();\n#endif\n")
        with self.assertRaisesRegex(ValueError, "guard drift"):
            self.check("r_agt", ET.tostring(tree))

    def test_unknown_nested_elif_unterminated_and_reversed_target_guards_fail(self):
        old = b'<root><guard><template>old();</template></guard></root>'
        for code in ("#if BSP_FEATURE_AGT_REGISTER_TYPE == 1\nnew();\n#elif UNKNOWN\nold();\n#endif\n",
                     "#if BSP_FEATURE_AGT_REGISTER_TYPE == 1\nnew();\n#else\nold();\n",
                     "#if BSP_FEATURE_AGT_REGISTER_TYPE != 1\nold();\n#else\nnew();\n#endif\n",
                     "#if OTHER\nnew();\n#else\nold();\n#endif\n"):
            tree = ET.fromstring(old)
            tree.find(".//template").text = code
            with self.subTest(code=code), self.assertRaises(ValueError):
                stock_regression.shared_metadata_invariants("RA8P1.xml", old, ET.tostring(tree), legacy_proof=self.proof)

    def test_unknown_legacy_conditions_are_retained_inside_reviewed_branches(self):
        code = "#if OLD\na();\n#else\nb();\n#endif\n"
        gated = "#if BSP_FEATURE_AGT_REGISTER_TYPE == 1\nnew();\n#else\n" + code + "#endif\n"
        self.assertEqual(stock_regression.legacy_template(code, self.proof),
                         stock_regression.legacy_template(gated, self.proof))
        self.assertNotEqual(stock_regression.legacy_template(code, self.proof),
                            stock_regression.legacy_template(gated.replace("#if OLD", "#if DIFFERENT"), self.proof))

    def test_meaningful_c_tokens_strings_and_preprocessor_macro_spacing_remain_strict(self):
        for old, new in (("x + +y;", "x++y;"), ('use("a b");', 'use("ab");'),
                         ("#define F(x) x\n", "#define F (x) x\n"),
                         ("value = 0x10;", "value = 0 x10;")):
            with self.subTest(old=old):
                self.assertNotEqual(stock_regression.legacy_template(old, self.proof),
                                    stock_regression.legacy_template(new, self.proof))

    def test_existing_exports_cannot_be_added_duplicated_weakened_or_hidden(self):
        _, _, frozen = self.mdf("r_canfd")
        for duplicate in (False, True):
            tree = ET.fromstring(frozen)
            prop = tree.find(".//property[@id='config.driver.canfd.dlc_check']")
            ET.SubElement(prop, "export").text = '"wrong"'
            if duplicate:
                ET.SubElement(prop, "export").text = '"${config.driver.canfd.dlc_check}"'
            with self.subTest(duplicate=duplicate), self.assertRaisesRegex(ValueError, "export drift"):
                self.check("r_canfd", ET.tostring(tree))
        _, _, frozen = self.mdf("r_adc_b")
        tree = ET.fromstring(frozen)
        export = tree.find(".//property[@id='module.driver.adc.virtual_channel_0_data_sign_setting']/export")
        export.text = export.text.replace("SELF_DIAGNOSIS", "WRONG_LEGACY_TEST")
        with self.assertRaisesRegex(ValueError, "export drift"):
            self.check("r_adc_b", ET.tostring(tree))

    def test_hidden_legacy_constraint_weakening_and_cross_property_moves_fail(self):
        _, _, frozen = self.mdf("r_i3c")
        tree = ET.fromstring(frozen)
        constraint = tree.find(".//property[@id='module.driver.i3c.ibi_payload_length']/constraint")
        self.assertIn(" > 0", constraint.text)
        constraint.text = constraint.text.replace(" > 0", " >= 0")
        with self.assertRaisesRegex(ValueError, "constraint drift"):
            self.check("r_i3c", ET.tostring(tree))
        tree = ET.fromstring(frozen)
        first = tree.find(".//property[@id='module.driver.i3c.frequency_byte']/constraint")
        second = tree.find(".//property[@id='module.driver.i3c.inaccuracy_byte']/constraint")
        first.text, second.text = second.text, first.text
        with self.assertRaisesRegex(ValueError, "constraint drift"):
            self.check("r_i3c", ET.tostring(tree))

    def test_ungated_added_constraint_and_disguised_side_effects_fail(self):
        _, _, frozen = self.mdf("r_canfd")
        for expression in ('testInteger("${legacy}")',
                           '!testExists("${interface.mcu.adc_b.adc16h}") || good(), bad()',
                           'bad() || !testExists("${interface.mcu.adc_b.adc16h}")',
                           'testExists("${interface.mcu.adc_b.adc16h}") /* !testExists("${interface.mcu.adc_b.adc16h}") */'):
            tree = ET.fromstring(frozen)
            ET.SubElement(tree.find("module"), "constraint", {"display": "Hidden legacy failure"}).text = expression
            with self.subTest(expression=expression), self.assertRaisesRegex(ValueError, "affects legacy"):
                self.check("r_canfd", ET.tostring(tree))

    def test_added_option_selector_and_property_type_change_fail(self):
        _, _, frozen = self.mdf("r_canfd")
        for selector in (False, True):
            tree = ET.fromstring(frozen)
            prop = tree.find(".//property[@id='config.driver.canfd.dlc_check']")
            if selector:
                ET.SubElement(prop, "select", {"enum": "different.options"})
            else:
                prop.set("readonly", "true")
            with self.subTest(selector=selector), self.assertRaisesRegex(ValueError, "shared MDF"):
                self.check("r_canfd", ET.tostring(tree))

    def test_export_return_types_and_unresolved_property_tests_remain_symbolic(self):
        original = b'<root><property id="p" default="off"/></root>'
        for expression in ('"${p}" || testExists("${interface.mcu.adc_b.adc16h}")',
                           '"${p}" === "on"', '"${p}" === "off"'):
            tree = ET.fromstring(original)
            ET.SubElement(tree.find("property"), "export").text = expression
            with self.subTest(expression=expression), self.assertRaisesRegex(ValueError, "export drift"):
                stock_regression.shared_metadata_invariants("fixture.xml", original, ET.tostring(tree), legacy_proof=self.proof)
        self.assertNotEqual(stock_regression.metadata_expression('"${p}" === "on"', self.proof),
                            stock_regression.metadata_expression('"${p}" === "off"', self.proof))

    def test_legacy_capability_exports_and_enum_defaults_are_not_ignored(self):
        original = (b'<root><module id="m"><provides interface="old"/>'
                    b'<enum id="e" default="a"><option id="a" value="1"/></enum></module></root>')
        for changed in (original.replace(b'interface="old"', b'interface="weakened"'),
                        original.replace(b'default="a"', b'default="other"'),
                        original.replace(b'</module>', b'<provides interface="RA8P1_hidden"/></module>')):
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, "shared MDF"):
                stock_regression.shared_metadata_invariants("RA8P1.xml", original, changed, legacy_proof=self.proof)

    def test_javascript_automatic_semicolon_insertion_is_not_normalized_away(self):
        old = "eval('function f() { return result; } f();')"
        new = "eval('function f() { return\\nresult; } f();')"
        self.assertNotEqual(stock_regression.metadata_expression(old, self.proof),
                            stock_regression.metadata_expression(new, self.proof))

    def test_dsi_migration_uses_exact_original_twenty_option_ids_order_and_values(self):
        self.assertEqual(len(self.rxie), 20)
        self.assertTrue(self.check("r_mipi_dsi")["option_values_unchanged"])
        path = ".module_descriptions/Renesas##BSP##ra8d1##fsp####5.9.0.xml"
        current = self.packs["Renesas.RA_mcu_ra8d1.5.9.0.pack"][path]
        original = regression.stock_packs(ROOT, self.historical)["Renesas.RA_mcu_ra8d1"][1][path]
        stock_regression.legacy_rxie_enum(path, original, current, self.rxie)
        for kind in ("value", "order", "extra", "outside"):
            tree = ET.fromstring(current)
            enum = tree.find("./bsp/enum[@id='enum.driver.mipi_dsi.rxie']")
            if kind == "value":
                enum[5].set("value", "0U")
            elif kind == "order":
                enum[0], enum[1] = enum[1], enum[0]
            elif kind == "extra":
                ET.SubElement(enum, "option", {"id": "extra", "value": "1"})
            else:
                tree.find(".//property").set("default", "changed")
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                stock_regression.legacy_rxie_enum(path, original, ET.tostring(tree), self.rxie)

    def test_all_32_proof_fails_if_last_legacy_device_changes_old_or_new_capability(self):
        pack = "Renesas.RA_mcu_ra8t1.5.9.0.pack"
        path = "ra/fsp/src/bsp/mcu/ra8t1/bsp_feature.h"
        source = self.packs[pack][path]
        for macro in ("BSP_FEATURE_AGT_IS_AVAILABLE", *stock_regression.METADATA_ZERO):
            changed, count = re.subn(rb"(#define\s+" + macro.encode() + rb"\s+)\([^)]*\)", rb"\g<1>(99UL)", source)
            self.assertEqual(count, 1)
            def load(name):
                return dict(self.packs[name], **{path: changed}) if name == pack else self.packs.get(name, {})
            with self.subTest(macro=macro), self.assertRaisesRegex(ValueError, "capability.*(drift|zero)"):
                stock_regression.metadata_legacy_proof(ROOT, self.historical, load, check_owning=False)

    def test_zero_proof_rejects_conditionally_disabled_definitions_undefs_and_include_shadowing(self):
        original = b'#ifndef BSP_FEATURE_H\n#define BSP_FEATURE_H\n#define BSP_FEATURE_OLD (1UL)\n#endif\n'
        macro = stock_regression.METADATA_ZERO[0]
        for inserted in ("#if 0\n#define " + macro + " (0UL)\n#endif\n",
                         "#define " + macro + " (0UL)\n#undef " + macro + "\n",
                         "#define " + macro + " (0UL)\n#include \"hidden.h\"\n"):
            current = original.replace(b"#endif", inserted.encode() + b"#endif")
            with self.subTest(inserted=inserted), self.assertRaises(ValueError):
                stock_regression.verify_additive_header("fixture.h", original, current, "BSP_FEATURE_", stock_regression.METADATA_ZERO)

    def test_all_32_proof_rejects_hidden_old_interface_and_adc_alias_changes(self):
        for alias in (False, True):
            pack = "Renesas.RA.5.9.0.pack" if alias else "Renesas.RA_mcu_ra8t1.5.9.0.pack"
            path = "ra/fsp/inc/instances/r_adc_b.h" if alias else ".module_descriptions/Renesas##BSP##ra8t1##device####5.9.0.xml"
            source = self.packs[pack][path]
            if alias:
                changed = source.replace(b"(22)", b"(21)", 1)
            else:
                tree = ET.fromstring(source)
                ET.SubElement(tree.find("bsp"), "provides", {"interface": "interface.mcu.adc_b.adc16h"})
                changed = ET.tostring(tree)
            self.assertTrue(changed != source)
            def load(name):
                return dict(self.packs[name], **{path: changed}) if name == pack else self.packs.get(name, {})
            with self.subTest(alias=alias), self.assertRaises(ValueError):
                stock_regression.metadata_legacy_proof(ROOT, self.historical, load, check_owning=False)

    def test_existing_report_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "red.json"
            path.write_bytes(b'{"success": false}\n')
            with patch.object(stock_regression, "inventory", return_value={"success": True}), self.assertRaisesRegex(
                    ValueError, "Refusing to overwrite retained evidence"):
                stock_regression.main(["--report", str(path)])
            self.assertEqual(path.read_bytes(), b'{"success": false}\n')


if __name__ == "__main__":
    unittest.main()
