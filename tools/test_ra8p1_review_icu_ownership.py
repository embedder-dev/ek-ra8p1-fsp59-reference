"""ICU-005: one physical IRQ configuration cannot have two generated owners.

HM14.2.12 pp539-540 defines a single IRQCR per external input. The
configurator check is per project only: callers must assign channels to
one core and serialize direct API uses; this is not a cross-core lock.
"""
from pathlib import Path
import json
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MDF = ROOT / "baseline/module_descriptions/Renesas##HAL Drivers##all##r_icu####5.9.0.xml"


class IcuOwnershipTests(unittest.TestCase):
    def test_single_owner_and_duplicate_admission_with_legacy_control(self):
        constraints = ET.parse(MDF).findall(".//module/constraint")
        matches = [c for c in constraints if c.get("display", "").startswith("Physical external IRQ channel")]
        self.assertEqual(1, len(matches))
        expression = matches[0].text.strip()
        self.assertIn("${interface.mcu.icu.common_regs}", expression)
        self.assertIn("${interface.peripheral.irq${module.driver.external_irq.channel}}", expression)
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required to evaluate the actual MDF JavaScript constraint")
        for target in (False, True):
            for channel in (0, 15, 31):
                for owners in (0, 1, 2, 3):
                    expanded = expression.replace("${interface.mcu.icu.common_regs}", "1" if target else "unavailable")
                    expanded = expanded.replace("${module.driver.external_irq.channel}", str(channel))
                    expanded = expanded.replace("${interface.peripheral.irq" + str(channel) + "}", str(owners))
                    script = "const testExists = value => value !== 'unavailable'; console.log(Boolean(" + expanded + "));"
                    result = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=10)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(not target or owners == 1, json.loads(result.stdout),
                                     (target, channel, owners))

    def test_constraint_does_not_change_generated_c_contract(self):
        root = ET.parse(MDF).getroot()
        module = root.find("module")
        self.assertIsNotNone(module)
        self.assertTrue(any(p.get("interface") == "interface.peripheral.irq${module.driver.external_irq.channel}"
                            for p in module.findall("provides")))
        declarations = module.find("declarations")
        self.assertIsNotNone(declarations)
        self.assertIn("external_irq_cfg_t", "".join(declarations.itertext()))
        self.assertNotIn("common_regs", "".join(declarations.itertext()))


if __name__ == "__main__":
    unittest.main()
