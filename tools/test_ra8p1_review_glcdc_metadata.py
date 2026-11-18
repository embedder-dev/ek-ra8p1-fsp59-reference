"""GLCDC-014: target enum spelling with unchanged legacy selections.

The unchanged FSP5.9 instance header is the primary naming contract.
Serialized property/option IDs must not be renamed.
"""
from pathlib import Path
import json
import re
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MDF = ROOT / "baseline/module_descriptions/Renesas##HAL Drivers##all##r_glcdc####5.9.0.xml"
HEADER = ROOT / "baseline/ra/fsp/inc/instances/r_glcdc.h"
PROP = "module.driver.display.dithering_mode"


class GlcdcDitherMetadataTests(unittest.TestCase):
    def test_actual_export_selects_header_enum_for_target_without_changing_legacy(self):
        prop = ET.parse(MDF).find(f'.//property[@id="{PROP}"]')
        self.assertIsNotNone(prop)
        self.assertEqual(PROP + ".dithering_mode_trancate", prop.get("default"))
        self.assertIsNotNone(prop.find("export"), "Target enum correction must be exported")
        expression = prop.findtext("export").strip()
        enum = re.search(r"typedef enum e_glcdc_dithering_mode\s*\{(.*?)\}\s*glcdc_dithering_mode_t;",
                         HEADER.read_text(), re.S)
        self.assertIsNotNone(enum)
        known = set(re.findall(r"\bGLCDC_DITHERING_MODE_[A-Za-z0-9_]+\b", enum[1]))
        node = shutil.which("node")
        self.assertIsNotNone(node)
        for target in (False, True):
            for option in prop.findall("option"):
                raw = option.get("value")
                expanded = expression.replace("${interface.mcu.glcdc.global_gamma_switch}",
                                              "1" if target else "unavailable")
                expanded = expanded.replace("${" + PROP + "}", raw)
                script = "const testExists = value => value !== 'unavailable'; console.log(JSON.stringify(" + expanded + "));"
                result = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=10)
                self.assertEqual(0, result.returncode, result.stderr)
                emitted = json.loads(result.stdout)
                if target:
                    self.assertIn(emitted, known)
                    expected = "GLCDC_DITHERING_MODE_ROUND_OFF" if raw.endswith("ROUND_off") else raw
                    self.assertEqual(expected, emitted)
                else:
                    self.assertEqual(raw, emitted)
        self.assertEqual({PROP + suffix for suffix in (".dithering_mode_trancate", ".dithering_mode_round_off", ".dithering_mode_2x2pattern")},
                         {o.get("id") for o in prop.findall("option")})


if __name__ == "__main__":
    unittest.main()
