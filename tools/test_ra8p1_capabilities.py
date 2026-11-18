"""Focused RA8P1 capability, event-map and ABI checks (no IDE or hardware)."""

import copy
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

from tools.ra8p1.test_oracles import primary

ROOT = Path(__file__).resolve().parents[1]
MCUS = ROOT / "baseline/ra/fsp/src/bsp/mcu"
TARGET = MCUS / "ra8p1"
INVENTORY = ROOT / "tools/ra8p1/bsp_capabilities.json"
REGISTRY = ROOT / "tools/ra8p1/capability_extensions.json"


def definitions(path, prefix):
    """Return valued definitions only, excluding the valueless include guard."""
    matches = re.findall(
        r"^[ \t]*#define[ \t]+(" + prefix + r"\w+(?:\([^\n]*?\))?)[ \t]+"
        r"([^\n]+?)(?:[ \t]+//[^\n]*)?$", path.read_text(), re.M)
    result = dict(matches)
    if len(result) != len(matches):
        raise ValueError(f"duplicate capability definitions in {path}")
    return result


def normalized(value):
    value = re.sub(r"\s+", "", value)
    while value.startswith("(") and value.endswith(")"):
        depth = 0
        for index, char in enumerate(value):
            depth += (char == "(") - (char == ")")
            if depth == 0:
                break
        if index != len(value) - 1:
            break
        value = value[1:-1]
    return value


def integer(value):
    return int(re.sub(r"[uUlL]+$", "", value.strip("() ")), 0)


class Capabilities(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(INVENTORY.read_text())
        cls.features = definitions(TARGET / "bsp_feature.h", "BSP_FEATURE_")
        cls.peripherals = definitions(TARGET / "bsp_peripheral.h", "BSP_PERIPHERAL_")

    def test_complete_audited_inventory_matches_headers(self):
        self.assertEqual(self.data["feature_count"], len(self.features))
        self.assertEqual(self.data["peripheral_count"], len(self.peripherals))
        registry = json.loads(REGISTRY.read_text())
        self.assertEqual(len(self.features), 483 + len(registry["features"]))
        self.assertEqual(len(self.peripherals), 186 + len(registry["peripherals"]))
        for field, actual in [("features", self.features), ("peripherals", self.peripherals)]:
            records = self.data[field]
            self.assertEqual(set(records), set(actual))
            for name, record in records.items():
                with self.subTest(name=name):
                    self.assertEqual(normalized(record["value"]), normalized(actual[name]))
                    self.assertRegex(record["source"], r"RA8P1 HM .+p")
                    self.assertIn(record["review"], ["confirmed", "changed", "added"])

    def test_macro_set_parity_with_every_legacy_mcu(self):
        for folder in sorted(MCUS.iterdir()):
            if folder.name == "ra8p1" or not (folder / "bsp_feature.h").exists():
                continue
            for filename, prefix, target in [
                    ("bsp_feature.h", "BSP_FEATURE_", self.features),
                    ("bsp_peripheral.h", "BSP_PERIPHERAL_", self.peripherals)]:
                with self.subTest(mcu=folder.name, header=filename):
                    self.assertEqual(set(target), set(definitions(folder / filename, prefix)))

    def test_parent_registered_extensions_match(self):
        registry = json.loads(REGISTRY.read_text())
        for group, filename in [("features", "bsp_feature.h"), ("peripherals", "bsp_peripheral.h")]:
            prefix = "BSP_FEATURE_" if group == "features" else "BSP_PERIPHERAL_"
            for folder in sorted(MCUS.iterdir()):
                if not (folder / filename).exists():
                    continue
                actual = definitions(folder / filename, prefix)
                for name, record in registry[group].items():
                    with self.subTest(mcu=folder.name, name=name):
                        value = record["target" if folder.name == "ra8p1" else "legacy"]
                        self.assertEqual(normalized(actual[name]), normalized(value))
                        self.assertEqual(normalized(self.data[group][name]["value"]),
                                         normalized(record["target"]))
                        self.assertTrue(self.data[group][name]["source"])

    def test_absent_ip_blocks_have_no_enabled_subfeatures(self):
        absent = ["ACMPLP", "ADC_D", "CAN", "CTSU", "DAC8", "ESC", "FLASH_HP",
                  "FLASH_LP", "KINT", "OPAMP", "OSPI", "QSPI", "SAU", "SLCDC",
                  "TAU", "TFU", "TML", "UARTA"]
        for ip in absent:
            entries = {k: v for k, v in self.features.items() if k.startswith("BSP_FEATURE_" + ip + "_")
                       and not (ip == "OSPI" and k.startswith("BSP_FEATURE_OSPI_B_"))}
            self.assertTrue(entries, ip)
            for name, value in entries.items():
                with self.subTest(name=name):
                    self.assertEqual(integer(value), 0)
        for name, value in self.features.items():
            if name.startswith("BSP_FEATURE_ADC_") and not name.startswith(("BSP_FEATURE_ADC_B_", "BSP_FEATURE_ADC_D_")):
                self.assertEqual(integer(value), 0, name)

    def test_absent_peripheral_channel_masks_are_zero(self):
        for name, value in self.peripherals.items():
            if not name.endswith("_PRESENT"):
                continue
            mask = name.removesuffix("_PRESENT") + "_CHANNEL_MASK"
            if mask in self.peripherals and integer(value) == 0:
                with self.subTest(peripheral=name):
                    self.assertEqual(integer(self.peripherals[mask]), 0)
        for ip in ["ADC_B", "MRAM", "PDM"]:
            self.assertEqual(integer(self.peripherals["BSP_PERIPHERAL_" + ip + "_PRESENT"]), 1)
        for ip, mask in [("PDM", 7), ("DAC_B", 3), ("DAC12", 3)]:
            with self.subTest(peripheral=ip):
                self.assertEqual(integer(self.peripherals["BSP_PERIPHERAL_" + ip + "_CHANNEL_MASK"]), mask)

    def test_present_silicon_is_not_zeroed(self):
        expected = {
            "ADC_B_IS_AVAILABLE": 1, "CGC_HAS_PLL": 1, "CGC_HAS_PLL2": 1,
            "CGC_PLLCCR_TYPE": 6, "CGC_SCKDIVCR2_HAS_EXTRA_CLOCKS": 1,
            "CGC_HAS_SRAMWTSC": 1, "CGC_HAS_FCLK": 0, "CGC_HAS_FLWT": 0,
            "CANFD_NUM_CHANNELS": 1, "CANFD_NUM_INSTANCES": 2,
            "DMAC_HAS_DELSR": 0,
            "DAC_B_UNIT_COUNT": 2, "DAC_B_CHANNELS_PER_UNIT": 1,
            "DAC12_UNIT_COUNT": 2, "DAC12_CHANNELS_PER_UNIT": 1,
            "DAC_B_CHANNEL_MASK": 3, "ADC_B_REGISTER_TYPE": 1,
            "ICU_HAS_COMMON_REGS": 1, "BSP_MSTP_ADC_MSTPD21": 1,
            "BSP_MSTP_PER_CORE_DMAC_DTC": 1, "BSP_HAS_PRCR_S": 1,
            "BSP_POWER_DOMAIN_TYPE": 1,
            "BSP_HAS_BCLKA_CLOCK": 1, "BSP_HAS_ESW_CLOCK": 1,
            "MRAM_IS_AVAILABLE": 1, "PDM_CHANNELS": 7,
            "BSP_VBATT_HAS_VBTCR1_BPWSWSTP": 0, "BSP_VBATT_HAS_VBTBPCR1": 1,
            "GPT_32BIT_CHANNEL_MASK": 0x3FFF, "GPT_ODC_128_RESOLUTION_CHANNEL_MASK": 0xF,
            "SCI_CHANNELS": 0x3FF, "SCI_UART_FIFO_DEPTH": 16,
            "SDRAM_SDTR_HAS_RAI": 1,
            "ICU_IRQ_CHANNELS_MASK": 0xFFFFFFFF, "ICU_NMIER_MAX_INDEX": 20,
            "ICU_WUPEN_MASK": 0xFFFFFF88FF1DFFFF,
            "LPM_DPSIER_MASK": 0xFFFFEF1FFFFF, "LPM_DPSIEGR_MASK": 0xFFFF13FFFF,
            "BSP_UNIQUE_ID_POINTER": 0x02F07B00, "BSP_HAS_OFS3": 1,
            "BSP_SYS_CLOCK_FREQ_NO_RAM_WAITS": 125000000,
            "CGC_PLLCCR_VCO_MIN_HZ": 960000000, "CGC_PLLCCR_VCO_MAX_HZ": 2400000000,
            "TSN_SLOPE": 2700, "TSN_CALIBRATION32_MASK": 0xFFF, "WDT_PER_CORE": 1,
        }
        for suffix, value in expected.items():
            self.assertEqual(integer(self.features["BSP_FEATURE_" + suffix]), value, suffix)

    def test_adc_unit_masks_cover_only_manual_channels(self):
        # HM Tables 54.4-54.5; the mask compression is the original 5.9 ADC_B convention.
        shared = list(range(16, 23))
        for unit, physical, internal in [
                (0, list(range(6)) + [12, 14] + shared, [96, 100, 101, 102, 104, 105, 112, 113, 114]),
                (1, list(range(6, 12)) + [13, 15] + shared, [97, 100, 101, 102, 104, 105, 116, 117, 118])]:
            expected = sum(1 << x for x in physical) | sum(1 << (32 + x - 96) for x in internal)
            self.assertEqual(integer(self.features[f"BSP_FEATURE_ADC_B_UNIT_{unit}_CHANNELS"]), expected)

    def test_elc_contains_all_documented_events_and_aliases(self):
        text = (TARGET / "bsp_elc.h").read_text()
        actual = {name: int(value, 16) for name, value in re.findall(
            r"(ELC_EVENT_\w+)[ \t]*=[ \t]*\((0x[0-9A-Fa-f]+)\)", text)}
        records = self.data["events"]
        self.assertEqual(len(records), 492)
        self.assertEqual(len({r["number"] for r in records}), len(records))
        self.assertEqual(actual.pop("ELC_EVENT_NONE"), 0)
        self.assertEqual(actual, {r["symbol"]: r["number"] for r in records})
        for alias, target in self.data["event_aliases"].items():
            self.assertRegex(text, r"#define[ \t]+" + re.escape(alias) + r"[ \t]+" + re.escape(target) + r"\b")
            self.assertIn(target, actual)
        # Independent anchor values across the whole ICU table, not a sibling's numbering.
        for symbol, value in {"ICU_IRQ31": 0x020, "DMAC8_INT": 0x048, "MRAM_ENDOFPE": 0x06D,
                              "PDM_DAT0": 0x0BF, "GPT13_COUNTER_OVERFLOW": 0x1FC,
                              "SCI8_TXI": 0x2FD, "ADC_ADI8": 0x355, "CEU_CEUI": 0x397,
                              "DTC0_DTCEND": 0x052, "DTC1_DTCEND": 0x055}.items():
            self.assertEqual(actual["ELC_EVENT_" + symbol], value)

    def test_elc_target_mask_includes_bit_32_not_reserved_slots(self):
        targets = self.data["elc_targets"]
        values = set(targets.values())
        self.assertEqual(values, set(range(8)) | set(range(12, 18)) | set(range(19, 28)) | {30, 31, 32})
        mask = sum(1 << x for x in values)
        self.assertEqual(mask, self.data["elc_target_mask"])
        self.assertEqual(mask, 0x1CFFBF0FF)
        self.assertIn("(33U)", (TARGET / "bsp_elc.h").read_text())

    def test_event_mdf_consumer_symbols_exist(self):
        path = ROOT / "baseline/module_descriptions/Renesas##BSP##ra8p1##events####5.9.0.xml"
        symbols = {r["symbol"] for r in self.data["events"]} | set(self.data["event_aliases"])
        for event in ET.parse(path).findall(".//event"):
            self.assertIn("ELC_EVENT_" + event.attrib["value"], symbols)
        target_symbols = set(re.findall(r"\bELC_PERIPHERAL_\w+\b", (TARGET / "bsp_elc.h").read_text()))
        for link in ET.parse(path).findall(".//link"):
            self.assertIn("ELC_PERIPHERAL_" + link.attrib["value"], target_symbols)

    def test_referenced_capability_names_are_defined(self):
        known = {k.split("(")[0] for k in self.features}
        for filename in ["bsp_feature.h", "bsp_peripheral.h", "bsp_override.h", "bsp_elc.h", "bsp_mcu_info.h"]:
            text = (TARGET / filename).read_text()
            references = set(re.findall(r"\bBSP_FEATURE_\w+\b", text)) - {"BSP_FEATURE_H"}
            self.assertFalse(references - known, (filename, references - known))
            self.assertNotIn("FSP_SUCCESS", text)
            self.assertFalse(any(line.rstrip() != line for line in text.splitlines()), filename)

    def test_changed_fsp_files_introduce_no_undefined_capabilities(self):
        known = {k.split("(")[0] for k in self.features} | set(self.peripherals)
        known |= {"BSP_FEATURE_H", "BSP_PERIPHERAL_H"}
        pattern = r"\bBSP_(?:FEATURE|PERIPHERAL)_\w+\b"
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", "-z", "HEAD", "--", "baseline"], cwd=ROOT, text=True)
        untracked = subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard", "-z", "--", "baseline"],
            cwd=ROOT, text=True)
        paths = sorted(set(changed.split("\0") + untracked.split("\0")))
        checked = 0
        for relative in paths:
            path = ROOT / relative
            if path.suffix not in {".c", ".h"} or not path.is_file():
                continue
            if "/bsp/mcu/" in relative and not any(
                    part in relative for part in ["/bsp/mcu/all/", "/bsp/mcu/ra8p1/"]):
                continue
            checked += 1
            text = path.read_text()
            original = subprocess.run(["git", "show", "HEAD:" + relative], cwd=ROOT,
                                      text=True, capture_output=True)
            if original.returncode == 0:
                old_missing = set(re.findall(pattern, original.stdout)) - known
                patch = subprocess.check_output(
                    ["git", "diff", "--unified=0", "HEAD", "--", relative], cwd=ROOT, text=True)
                added = "\n".join(line[1:] for line in patch.splitlines()
                                  if line.startswith("+") and not line.startswith("+++"))
            else:
                old_missing = set()
                added = text
            with self.subTest(path=relative):
                self.assertFalse(set(re.findall(pattern, text)) - known - old_missing,
                                 "new undefined capability in changed file")
                self.assertFalse(set(re.findall(pattern, added)) - known,
                                 "added line references an undefined capability")
        self.assertGreater(checked, 0)

    def test_event_rows_against_allowed_hardware_manual(self):
        # Mandatory offline primary gate: provenance-checked Table14.5 plus Table20.4 DTC rows.
        primary.assert_event_numbers(self.data["events"])

    def test_shared_json_header_irq29_irq30_swap_fails_primary_gate(self):
        records = copy.deepcopy(self.data["events"])
        for row in records:
            if row["manual_name"] in ("PORT_IRQ29", "PORT_IRQ30"):
                row["number"] = 0x01F if row["manual_name"] == "PORT_IRQ29" else 0x01E
        text = (TARGET / "bsp_elc.h").read_text()
        for row in records:
            if row["manual_name"] in ("PORT_IRQ29", "PORT_IRQ30"):
                text, count = re.subn(r"(" + re.escape(row["symbol"]) + r"[ \t]*=[ \t]*\()0x[0-9A-Fa-f]+(\))",
                                      lambda match: match[1] + hex(row["number"]) + match[2], text)
                self.assertEqual(count, 1)
        paired = {name: int(value, 16) for name, value in re.findall(
            r"(ELC_EVENT_\w+)[ \t]*=[ \t]*\((0x[0-9A-Fa-f]+)\)", text)}
        paired.pop("ELC_EVENT_NONE")
        self.assertEqual(paired, {row["symbol"]: row["number"] for row in records},
                         "Mutant preserves shared JSON/header consistency")
        with self.assertRaisesRegex(AssertionError, "Primary HM event-number mismatch"):
            primary.assert_event_numbers(records)

    def compile_source(self, compiler, source, extra=(), run=False):
        with tempfile.TemporaryDirectory(prefix="ra8p1-capabilities-") as temp:
            output = Path(temp) / ("check" if run else "check.o")
            command = [compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-I", str(TARGET), *extra,
                       "-x", "c", "-", "-o", str(output)]
            if not run:
                command.append("-c")
            result = subprocess.run(command, input=source, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            if run:
                result = subprocess.run([str(output)], text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_generated_pdm_and_adc_vector_event_syntax_compiles(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler not installed")
        numbers = {row["symbol"].removeprefix("ELC_EVENT_"): row["number"] for row in self.data["events"]}
        events = ["PDM_DAT2", "PDM_ERR2", "PDM_DAT0", "PDM_ERR0", "PDM_DAT1", "PDM_ERR1"]
        events += [name for name in numbers if name.startswith("ADC_")]
        entries, assertions, checks = [], [], []
        for index, event in enumerate(events):
            # Match e2's vector_data.c syntax; GROUPn deliberately has no definition.
            call = f"BSP_PRV_VECT_ENUM(EVENT_{event},GROUP{index % 8})"
            entries.append(f"    [{index}] = {call},")
            assertions.append(f'_Static_assert({call} == {numbers[event]}, "{event} vector event");')
            checks.append(f"    assert(vector_events[{index}] == {numbers[event]});")
        source = '#include <assert.h>\n#include "bsp_elc.h"\n'
        source += "elc_event_t const vector_events[] = {\n" + "\n".join(entries) + "\n};\n"
        source += "\n".join(assertions) + "\nint main(void) {\n" + "\n".join(checks) + "\nreturn 0;\n}\n"
        for core in [0, 1]:
            with self.subTest(core=core):
                self.compile_source(compiler, f"#define BSP_CFG_CPU_CORE {core}\n" + source,
                                    ["-Wundef"], run=True)

    def ioport_enum_source(self, text):
        enums = re.findall(r"typedef enum e_ioport_peripheral\b.*?\}\s*ioport_peripheral_t;", text, re.S)
        self.assertEqual(len(enums), 1, "extract the complete owning IOPORT enum")
        offset = re.search(r"^#define[ \t]+IOPORT_PRV_PFS_PSEL_OFFSET[^\n]*", text, re.M)
        self.assertIsNotNone(offset)
        return offset.group(0) + "\n" + enums[0] + "\n"

    def test_ioport_enum_values_match_pristine_head_for_both_sci_variants(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler not installed")
        relative = "ra/fsp/inc/instances/r_ioport.h"
        current = self.ioport_enum_source((ROOT / "baseline" / relative).read_text())
        pristine = self.ioport_enum_source(subprocess.check_output(
            ["git", "show", "HEAD:" + relative], cwd=ROOT / "baseline", text=True))
        pattern = r"^[ \t]*(IOPORT_PERIPHERAL_\w+)[ \t]*="
        old_names = set(re.findall(pattern, pristine, re.M))
        names = set(re.findall(pattern, current, re.M))
        self.assertTrue(old_names)
        self.assertEqual(names - old_names, {"IOPORT_PERIPHERAL_ETHER_RGMII", "IOPORT_PERIPHERAL_PDM"})
        self.assertFalse(old_names - names)
        pristine = re.sub(r"\b(?:IOPORT_\w+|e_ioport_peripheral|ioport_peripheral_t)\b",
                          lambda match: "pristine_" + match.group(0), pristine)
        comparisons = "\n".join(
            f'_Static_assert((unsigned long) {name} == (unsigned long) pristine_{name}, "{name} changed");'
            for name in sorted(old_names))
        # HM 21.6, Table 21.10 p.869 and Table 21.12 p.872: PSEL 11000b/11011b.
        assertions = '''
_Static_assert(IOPORT_PRV_PFS_PSEL_OFFSET == 24, "PSEL bit offset");
_Static_assert(IOPORT_PERIPHERAL_ETHER_RGMII == (0x18UL << 24), "RGMII encoding");
_Static_assert(IOPORT_PERIPHERAL_PDM == (0x1BUL << 24), "PDM encoding");
int main(void) { return 0; }
'''
        variants = {}
        for device in ["ra8p1", "ra8m1", "ra6t2"]:
            value = definitions(MCUS / device / "bsp_feature.h", "BSP_FEATURE_")[
                "BSP_FEATURE_SCI_UART_DE_IS_INVERTED"]
            variants[device] = integer(value)
            with self.subTest(device=device, sci_inverted=value):
                source = f"#define BSP_FEATURE_SCI_UART_DE_IS_INVERTED {value}\n"
                self.compile_source(compiler, source + pristine + current + comparisons + assertions,
                                    ["-Wundef"], run=True)
        self.assertEqual(variants, {"ra8p1": 0, "ra8m1": 0, "ra6t2": 1})

    def test_ioport_board_pin_tokens_compile_and_missing_new_members_fail(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler not installed")
        model = ET.parse(ROOT / ".embedder/pin-model/pinmapping/PinCfgR7KA8P1KxxCAC.xml")
        alternatives = {node.get("id"): node for node in model.findall(".//alt")
                        if node.findall("./registerSetting")}
        board = ET.parse(ROOT / "baseline/module_descriptions/"
                         "Renesas##BSP##Board##ra8p1_ek####5.9.0##configuration.xml")
        selected = {}
        for setting in board.findall(".//configSetting"):
            alt_id = setting.get("altId")
            alternative = alternatives.get(alt_id)
            if alternative is not None:
                values = " ".join(node.get("value", "") for node in alternative.findall("./registerSetting"))
                tokens = set(re.findall(r"\bIOPORT_PERIPHERAL_\w+", values))
                if tokens:
                    selected[alt_id] = tokens
        self.assertIn("IOPORT_PERIPHERAL_ETHER_RGMII", selected["p307.eswm_rgmii1.rgmii1_txd0"])
        self.assertIn("IOPORT_PERIPHERAL_PDM", selected["p502.pdm2.pdmdat2"])
        self.assertIn("IOPORT_PERIPHERAL_PDM", selected["p812.pdm2.pdmclk2"])
        tokens = set().union(*selected.values())
        current = self.ioport_enum_source((ROOT / "baseline/ra/fsp/inc/instances/r_ioport.h").read_text())
        consumer = "\nioport_peripheral_t const board_pin_tokens[] = {\n" + ",\n".join(sorted(tokens)) + "\n};\n"
        consumer += 'int main(void) { return sizeof(board_pin_tokens) / sizeof(board_pin_tokens[0]) != ' + str(len(tokens)) + '; }\n'
        for inversion in [0, 1]:
            prefix = f"#define BSP_FEATURE_SCI_UART_DE_IS_INVERTED {inversion}\n"
            with self.subTest(sci_inverted=inversion):
                self.compile_source(compiler, prefix + current + consumer, ["-Wundef"], run=True)
            for missing in ["IOPORT_PERIPHERAL_ETHER_RGMII", "IOPORT_PERIPHERAL_PDM"]:
                with self.subTest(sci_inverted=inversion, missing=missing):
                    mutated, count = re.subn(r"^[ \t]*" + missing + r"[ \t]*=[^\n]*\n", "", current, flags=re.M)
                    self.assertEqual(count, 1)
                    result = subprocess.run([compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-Wundef",
                                             "-fsyntax-only", "-x", "c", "-"],
                                            input=prefix + mutated + consumer, text=True, capture_output=True)
                    self.assertNotEqual(result.returncode, 0, "missing board token must fail compilation")
                    self.assertIn(missing, result.stderr)
                    self.assertRegex(result.stderr, r"undeclared|not declared")

    def test_clock_bitfield_abi_and_nmi_groups_on_host(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler not installed")
        self.compile_source(compiler, r'''
#include <assert.h>
#include <stddef.h>
#include "bsp_override.h"
_Static_assert(sizeof(cgc_divider_cfg_t) == 8, "divider ABI");
_Static_assert(sizeof(((cgc_divider_cfg_t *)0)->sckdivcr2) == 2, "16-bit SCKDIVCR2");
_Static_assert(offsetof(cgc_divider_cfg_t, sckdivcr2) == 4, "register image offset");
_Static_assert(BSP_GRP_IRQ_WDT_ERROR == 1 && BSP_GRP_IRQ_IPC == 20, "local NMI indices");
_Static_assert(BSP_GRP_IRQ_LOCAL_MEMORY == 14 && BSP_GRP_IRQ_FPU_EXCEPTION == 16, "NMI indices");
_Static_assert(BSP_GRP_IRQ_MRAM_CODE_READ == 17 && BSP_GRP_IRQ_MRAM_EXTRA_READ == 18, "MRAM NMI indices");
int main(void) {
    cgc_divider_cfg_t c = {0};
    c.sckdivcr2_b.cpuclk_div = CGC_SYS_CLOCK_DIV_2;
    c.sckdivcr2_b.cpuclk1_div = CGC_SYS_CLOCK_DIV_4;
    c.sckdivcr2_b.npuclk_div = CGC_SYS_CLOCK_DIV_8;
    c.sckdivcr2_b.mriclk_div = CGC_SYS_CLOCK_DIV_16;
    assert(c.sckdivcr2 == 0x4321);
    assert(c.sckdivcr2_b.extraclk1_div == 2 && c.sckdivcr2_b.extraclk2_div == 3 && c.sckdivcr2_b.extraclk3_div == 4);
    c.sckdivcr_b.mrpclk_div = CGC_SYS_CLOCK_DIV_24;
    assert(c.sckdivcr_w == 0xB0000000U && c.sckdivcr_b.fclk_div == CGC_SYS_CLOCK_DIV_24);
    return 0;
}
''', run=True)

    def test_both_arm_core_views_compile(self):
        compiler = shutil.which("arm-none-eabi-gcc")
        if not compiler:
            self.skipTest("Arm GCC not installed")
        for core, cpu in [(0, "cortex-m85"), (1, "cortex-m33")]:
            source = f"#define BSP_CFG_CPU_CORE {core}\n" + r'''
#define BSP_CFG_XTAL_HZ 24000000
#define R_SYSTEM_MOMCR_MODRV0_Msk 0x0EU
#define R_SYSTEM_MOMCR_MODRV0_Pos 1U
#include "bsp_override.h"
#include "bsp_mcu_info.h"
_Static_assert(sizeof(cgc_divider_cfg_t) == 8, "target divider ABI");
_Static_assert(sizeof(((cgc_divider_cfg_t *)0)->sckdivcr2) == 2, "target SCKDIVCR2 width");
_Static_assert(BSP_FEATURE_BSP_HAS_CTCM == (BSP_CFG_CPU_CORE == 1), "C-TCM ownership");
_Static_assert(BSP_FEATURE_BSP_HAS_ITCM == (BSP_CFG_CPU_CORE == 0), "ITCM ownership");
_Static_assert(BSP_FEATURE_BSP_HAS_DTCM == (BSP_CFG_CPU_CORE == 0), "DTCM ownership");
_Static_assert(BSP_FEATURE_BSP_CODE_CACHE_VERSION == (BSP_CFG_CPU_CORE ? 2 : 0), "cache view");
_Static_assert(((CGC_MAINCLOCK_DRIVE << BSP_FEATURE_CGC_MODRV_SHIFT) & BSP_FEATURE_CGC_MODRV_MASK) == 0x1AU, "MOMCR reserved bit 4");
_Static_assert(BSP_FEATURE_ICU_WUPEN_MASK == 0xFFFFFF88FF1DFFFFULL, "all wake bits");
_Static_assert(ELC_PERIPHERAL_GPTP1 == 32 && ELC_PERIPHERAL_NUM == 33, "ELC target range");
_Static_assert(BSP_ELC_PERIPHERAL_MASK & (1ULL << ELC_PERIPHERAL_GPTP1), "upper ELC target");
_Static_assert(ELC_SOFTWARE_EVENT_3 == 3, "four software events");
_Static_assert(ELC_EVENT_SCI8_TXI == 0x2FD, "SCI8 event");
bsp_interrupt_event_t event = ELC_EVENT_IPC_IRQ0;
'''
            with self.subTest(core=core):
                self.compile_source(compiler, source, ["-mthumb", "-mcpu=" + cpu, "-ffreestanding"])


if __name__ == "__main__":
    unittest.main()
