"""Offline CFG-001/002/003 controls from RA8P1 HM Rev.1.30.

Generic comparator presence is separate from package-specific pin eligibility.
These enum checks do not qualify a PVD/LVD driver or exercise e2 resolution.
"""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MDF = ROOT / "baseline/module_descriptions"
DEVICE = MDF / "Renesas##BSP##ra8p1##device####5.9.0.xml"
PART = MDF / "Renesas##BSP##ra8p1##device##R7KA8P1KFLCAC##5.9.0.xml"
FSP = MDF / "Renesas##BSP##ra8p1##fsp####5.9.0.xml"

# HM 8.2.2 p304: (PVDLVL encoding, unchanged serialized voltage suffix).
PVD_LEVELS = (
    (0x03, "3_86V"), (0x04, "3_14V"), (0x05, "3_10V"),
    (0x06, "3_08V"), (0x07, "2_85V"), (0x08, "2_83V"),
    (0x09, "2_80V"), (0x0A, "2_62V"), (0x0B, "2_33V"),
    (0x0C, "1_90V"), (0x0D, "1_86V"), (0x0E, "1_74V"),
    (0x0F, "1_71V"),
)

# HM 49.2.5 pp3193-3194: explicit (channel, TDR address, RDR address).
# No inference from adjacent channels: both security aliases have these low bits.
SCI_SNOOP_ADDRESSES = (
    (0, 0x40358004, 0x40358000),
    (1, 0x40358104, 0x40358100),
    (2, 0x40358204, 0x40358200),
    (3, 0x40358304, 0x40358300),
    (4, 0x40358404, 0x40358400),
    (5, 0x40358504, 0x40358500),
    (6, 0x40358604, 0x40358600),
    (7, 0x40358704, 0x40358700),
    (8, 0x40358804, 0x40358800),
    (9, 0x40358904, 0x40358900),
)


def enum(root, identifier):
    matches = root.findall(f".//enum[@id='{identifier}']")
    if len(matches) != 1:
        raise AssertionError(f"Expected one {identifier}, got {len(matches)}")
    return matches[0]


def numeric_options(element):
    result = {}
    for option in element.findall("option"):
        identifier = option.get("id")
        if identifier in result:
            raise AssertionError(f"Duplicate option {identifier}")
        # MDF values here are numeric literals, optionally parenthesized.
        result[identifier] = int(option.get("value").strip("()"), 0)
    return result


class TargetConfigurationCompletenessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.device = ET.parse(DEVICE).getroot()
        cls.part = ET.parse(PART).getroot()
        cls.fsp = ET.parse(FSP).getroot()

    def test_generic_comparator_provides_expose_exactly_four_channels(self):
        # HM 57.1 table57.1 p3518 specifies ACMPHSn, n=0..3.
        provides = [x.get("interface") for x in self.device.findall(".//bsp/provides")]
        channels = [x for x in provides if re.fullmatch(r"interface\.mcu\.acmphs\.\d+", x)]
        self.assertEqual(4, len(channels))
        self.assertEqual({f"interface.mcu.acmphs.{n}" for n in (0, 1, 2, 3)}, set(channels))
        self.assertNotIn("interface.mcu.acmphs.4", provides)
        self.assertNotIn("interface.mcu.acmphs.-1", provides)

    def test_comparator_mask_and_enum_are_complete_with_original_default(self):
        mask = enum(self.device, "enum.mcu.acmphs.channel.mask")
        self.assertEqual("enum.mcu.acmphs.channel.bitmask", mask.get("default"))
        self.assertEqual({"enum.mcu.acmphs.channel.bitmask": 0xF}, numeric_options(mask))
        channels = enum(self.device, "enum.mcu.acmphs.channels")
        self.assertEqual("enum.mcu.acmphs.channels.0", channels.get("default"))
        expected = {f"enum.mcu.acmphs.channels.{n}": n for n in (0, 1, 2, 3)}
        self.assertEqual(expected, numeric_options(channels))
        self.assertEqual({f"ACMPHS{n}" for n in (0, 1, 2, 3)},
                         {x.get("display") for x in channels.findall("option")})
        self.assertEqual(0, numeric_options(channels)[channels.get("default")])

    def test_part_external_eligibility_is_not_promoted_from_generic_presence(self):
        # Preserve the existing part model; this is not proof that its mapping is complete.
        provides = [x.get("interface") for x in self.part.findall(".//bsp/provides")]
        external = [x for x in provides if re.fullmatch(r"interface\.mcu\.acmphs\.external\.\d+", x)]
        self.assertEqual(2, len(external))
        self.assertEqual({"interface.mcu.acmphs.external.0", "interface.mcu.acmphs.external.1"}, set(external))
        choices = enum(self.part, "enum.mcu.acmphs.external.channels")
        self.assertEqual("enum.mcu.acmphs.external.channels.0", choices.get("default"))
        self.assertEqual({"enum.mcu.acmphs.external.channels.0": 0,
                          "enum.mcu.acmphs.external.channels.1": 1}, numeric_options(choices))
        self.assertFalse(any("acmphs.external" in x.get("interface", "")
                             for x in self.device.findall(".//bsp/provides")))

    def test_pvd_levels_keep_every_legal_id_and_exact_encoding_for_both_monitors(self):
        thresholds = enum(self.fsp, "enum.mcu.lvd.monitor")
        actual = numeric_options(thresholds)
        expected = {f"module.driver.lvd.voltage_threshold.LVD_THRESHOLD_MONITOR_{monitor}_LEVEL_{suffix}": code
                    for monitor in (1, 2) for code, suffix in PVD_LEVELS}
        self.assertEqual(26, len(thresholds.findall("option")))
        self.assertEqual(expected, actual)
        for option in thresholds.findall("option"):
            monitor = re.search(r"MONITOR_([12])_", option.get("id"))[1]
            suffix = option.get("id").rsplit("_LEVEL_", 1)[1]
            self.assertEqual(f"Monitor {monitor} ({suffix[:-1].replace('_', '.')}V)", option.get("display"))

    def test_prohibited_pvd_codes_and_stale_ids_are_no_longer_selectable(self):
        actual = numeric_options(enum(self.fsp, "enum.mcu.lvd.monitor"))
        for monitor in (1, 2):
            prefix = f"module.driver.lvd.voltage_threshold.LVD_THRESHOLD_MONITOR_{monitor}_LEVEL_"
            for suffix in ("4_29V", "4_16V", "4_03V"):
                self.assertNotIn(prefix + suffix, actual)
        for prohibited in (-1, 0, 1, 2, 16, 31):
            self.assertNotIn(prohibited, actual.values())
        self.assertEqual(set(range(3, 16)), set(actual.values()))

    def test_original_pvd_monitor_and_threshold_defaults_remain_valid(self):
        thresholds = enum(self.fsp, "enum.mcu.lvd.monitor")
        self.assertEqual("module.driver.lvd.voltage_threshold.LVD_THRESHOLD_MONITOR_1_LEVEL_3_08V",
                         thresholds.get("default"))
        self.assertEqual(6, numeric_options(thresholds)[thresholds.get("default")])
        monitor = enum(self.fsp, "enum.mcu.lvd.monitor_number")
        self.assertEqual("module.driver.lvd.monitor_number.MONITOR_1", monitor.get("default"))
        self.assertEqual({"module.driver.lvd.monitor_number.MONITOR_1": 1,
                          "module.driver.lvd.monitor_number.MONITOR_2": 2}, numeric_options(monitor))

    def test_all_twenty_crc_selections_match_explicit_manual_addresses(self):
        snoop = enum(self.fsp, "enum.mcu.crc.snoop_address")
        actual = numeric_options(snoop)
        expected = {}
        for channel, tdr, rdr in SCI_SNOOP_ADDRESSES:
            for register, address in (("tdr", tdr), ("rdr", rdr)):
                identifier = f"module.driver.crc.snoop_address.SCI{channel}_{register}"
                expected[identifier] = address & 0x3FFF
                self.assertEqual(address & 0x3FFF, (address + 0x10000000) & 0x3FFF)
        self.assertEqual(20, len(snoop.findall("option")))
        self.assertEqual(expected, actual)
        self.assertEqual(20, len(set(actual.values())))
        self.assertEqual({f"SCI{channel}_{register}" for channel in range(10) for register in ("TDR", "RDR")},
                         {x.get("display") for x in snoop.findall("option")})

    def test_missing_crc_choices_have_exact_lower_fourteen_bit_codes(self):
        actual = numeric_options(enum(self.fsp, "enum.mcu.crc.snoop_address"))
        expected = {"SCI5_tdr": 0x504, "SCI5_rdr": 0x500,
                    "SCI6_tdr": 0x604, "SCI6_rdr": 0x600,
                    "SCI7_tdr": 0x704, "SCI7_rdr": 0x700,
                    "SCI8_tdr": 0x804, "SCI8_rdr": 0x800}
        for suffix, code in expected.items():
            self.assertEqual(code, actual["module.driver.crc.snoop_address." + suffix])

    def test_crc_existing_legal_ids_and_default_remain_unchanged(self):
        snoop = enum(self.fsp, "enum.mcu.crc.snoop_address")
        actual = numeric_options(snoop)
        # The twelve preexisting legal choices must retain their IDs and encodings.
        expected = {"SCI0_tdr": 0x004, "SCI1_tdr": 0x104, "SCI2_tdr": 0x204,
                    "SCI3_tdr": 0x304, "SCI4_tdr": 0x404, "SCI9_tdr": 0x904,
                    "SCI0_rdr": 0x000, "SCI1_rdr": 0x100, "SCI2_rdr": 0x200,
                    "SCI3_rdr": 0x300, "SCI4_rdr": 0x400, "SCI9_rdr": 0x900}
        for suffix, code in expected.items():
            self.assertEqual(code, actual["module.driver.crc.snoop_address." + suffix])
        self.assertEqual("module.driver.crc.snoop_address.SCI0_tdr", snoop.get("default"))
        self.assertEqual(0x004, actual[snoop.get("default")])
        self.assertNotIn("module.driver.crc.snoop_address.SCI10_tdr", actual)
        self.assertNotIn(0x4000, actual.values())


if __name__ == "__main__":
    unittest.main()
