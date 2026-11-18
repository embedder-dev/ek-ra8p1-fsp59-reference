"""EVT-003: HM20.2 Table20.3 p833 DTC-end ELC sources are selectable.

They are eventlink-only, not NVIC or DTC/DMAC activation sources.
"""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MDF = ROOT / "baseline/module_descriptions/Renesas##BSP##ra8p1##events####5.9.0.xml"
ELC = ROOT / "baseline/ra/fsp/src/bsp/mcu/ra8p1/bsp_elc.h"


class DtcEndEventTests(unittest.TestCase):
    def test_both_manual_dtc_end_sources_are_eventlink_only(self):
        events = ET.parse(MDF).findall(".//event")
        header = ELC.read_text()
        for core, number in ((0, 0x052), (1, 0x055)):
            symbol = f"DTC{core}_DTCEND"
            matched = [e for e in events if e.get("value") == symbol]
            self.assertEqual(1, len(matched), symbol)
            self.assertEqual("eventlink", matched[0].get("scope"))
            self.assertEqual(f"event.dtc{core}.dtcend", matched[0].get("id"))
            match = re.search(r"ELC_EVENT_" + symbol + r"\s*=\s*\((0x[\dA-Fa-f]+)\)", header)
            self.assertIsNotNone(match)
            self.assertEqual(number, int(match[1], 16))


if __name__ == "__main__":
    unittest.main()
