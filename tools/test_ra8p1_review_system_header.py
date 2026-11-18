"""HDR-C01..05: independent HM/SVD oracles, never the published header.

The ordinary loader cannot extend a type across fragments. Until the parent
applies review_system_header/owning_inventory.patch, tests stage those exact
additions in memory. Only a temporary generated header is compiled. No e2,
pack, production header, production inventory or device is changed here.
"""

import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from ra8p1 import generate_device_header as header
from test_ra8p1_aux_header import compile_source, extract_stock_cmsis
from test_ra8p1_device_header import elf_sections

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tools/ra8p1/review_system_header"
FRAGMENT = ROOT / "tools/ra8p1/registers_review_system.json"
SVD = ROOT / ".embedder/svd-cache/R7KA8P1AD.json"
NATIVE = ROOT / "tools/ra8p1/layout/native"
ACCESS = {"read-only": "R", "write-only": "W", "read-write": "R/W"}

# HM §§16.3.1.3–51 pp.700–730: the compact SVD names encode ranges but
# contain no dim/dimIncrement. Counts and strides must not come from the DUT.
MPU_GROUPS = (
    ("DMAC0", "DMAC000-07", "DMAC0-1", 0x100, 8),
    ("DMAC1", "DMAC100-07", "DMAC0-1", 0x300, 8),
    ("EDMAC", "EDMAC0-4", "EDMAC", 0x500, 5),
    ("GLCDC", "GLCDC0-1", "GLCDC", 0x700, 2),
    ("DRW", "DRW0-2", "DRW", 0x900, 3),
    ("MIPI_DSI", "MIPID", "MIPID", 0xB00, 1),
    ("CEU", "CEU0-1", "CEU", 0xD00, 2),
    ("MIPI_CSI", "MIPIC0-2", "MIPIC", 0xF00, 3),
    ("NPU", "NPU0-4", "NPU", 0x1100, 5),
)
BUS_MASTERS = ("CPU0", "CPU1", "DMAC0", "DMAC1", "NPU", "EDMAC",
               "GLCDC", "TDRW", "MIPI0", "MIPI1", "CEU")


def proposed_inventory():
    """Stage only the explicit owner additions, also accepting parent integration."""
    data = header.load_inventory()
    additions = json.loads((FIXTURE / "owning_inventory_additions.json").read_text())
    for before, helpers in additions["insert_types_before"].items():
        index = next(i for i, t in enumerate(data["types"]) if t["name"] == before)
        for helper in helpers:
            existing = next((t for t in data["types"] if t["name"] == helper["name"]), None)
            if existing is None:
                data["types"].insert(index, copy.deepcopy(helper))
                index += 1
            elif existing != helper:
                raise AssertionError("Integrated helper differs: " + helper["name"])
    for extension in additions["extend_types"]:
        owner = next(t for t in data["types"] if t["name"] == extension["name"])
        owner["size"] = extension["size"]
        for member in extension["members"]:
            existing = next((r for r in owner["members"] if r["name"] == member["name"]), None)
            if existing is None:
                owner["members"].append(copy.deepcopy(member))
            elif existing != member:
                raise AssertionError("Integrated member differs: " + owner["name"] + "." + member["name"])
        owner["members"].sort(key=lambda r: header.number(r["offset"]))
    return data


def expectations():
    """Complete register oracle from the supplied SVD plus explicit manual deltas."""
    peripherals = {p["name"]: p for p in json.loads(SVD.read_text())["peripherals"]}
    records = {p: {r["name"]: r for r in value["registers"]} for p, value in peripherals.items()
               if p in ("RMPU", "RMPU_NS", "BUS", "CPSCU", "IPC", "CPU_OCD", "CPU_DBG", "CACHE")}
    result = []

    def add(peripheral, raw_name, typ, member, offset=None, leaf_type=None, leaf_member=None):
        raw = records[peripheral][raw_name]
        access = ACCESS[raw["access"]]
        fields = {f["name"]: (f["bitOffset"], f["bitWidth"], ACCESS.get(f.get("access"), access))
                  for f in raw.get("fields", [])}
        if peripheral == "RMPU" and leaf_member in ("S", "E"):
            # HM has anonymous 31:0 address fields; FSP5.9 calls them MMPUS/E.
            fields = {"MMPU" + leaf_member: (0, 32, "R/W")}
        if peripheral == "IPC" and re.fullmatch(r"IPC[01](STA|ISET|CLR)[01]", raw_name):
            kind = re.search(r"STA|ISET|CLR", raw_name).group()
            prefix = {"STA": "IRQ", "ISET": "SET", "CLR": "CLR"}[kind]
            fields = {n: v for n, v in fields.items() if v[0] >= 8}
            fields.update({prefix + str(n): (n, 1, access) for n in range(8)})
        if peripheral == "CPU_DBG" and raw_name == "DBGSTOPCR":
            # HM p.142 explicitly reserves bit29 (SVD gives it a control name).
            fields.pop("DBGSTOP_CTERR1")
        result.append({"type": typ, "member": member,
                       "offset": raw["addressOffset"] if offset is None else offset,
                       "width": raw["size"], "access": access, "fields": fields,
                       "leaf_type": leaf_type or typ,
                       "leaf_member": leaf_member or member})

    for name in ("MMPUOAD", "MMPUOADPT"):
        add("RMPU", name, "R_MPU_MMPU_Type", name)
    for group, region_stem, control_stem, base, count in MPU_GROUPS:
        dma = group.startswith("DMAC")
        leaf = "R_MPU_MMPU_GROUP_Type" if dma else f"R_MPU_MMPU_{group}_Type"
        region_type = "R_MPU_MMPU_GROUP_REGION_Type" if dma else f"R_MPU_MMPU_{group}_REGION_Type"
        for name, prefix, rel in (("EN", "MMPUEN", 0), ("ENPT", "MMPUENPT", 4)):
            raw = "MMPUENPDRW" if group == "DRW" and name == "ENPT" else prefix + control_stem
            add("RMPU", raw, "R_MPU_MMPU_Type", group + "." + name, base + rel, leaf, name)
        if dma:
            add("RMPU_NS", "MMPURPTDMAC0-1", "R_MPU_MMPU_Type", group + ".RPT", base + 8, leaf, "RPT")
            add("RMPU", "MMPURPTDMAC_SEC0-1", "R_MPU_MMPU_Type", group + ".RPT_SEC", base + 12, leaf, "RPT_SEC")
        else:
            add("RMPU", "MMPURPT" + control_stem, "R_MPU_MMPU_Type", group + ".RPT", base + 8, leaf, "RPT")
        for index in range(count):
            for name, prefix, rel in (("AC", "MMPUAC", 0), ("S", "MMPUS", 4), ("E", "MMPUE", 8)):
                add("RMPU", prefix + region_stem, "R_MPU_MMPU_Type", f"{group}.REGION[{index}].{name}",
                    base + 0x100 + index * 0x10 + rel, region_type, name)
    for index in range(8):
        for raw, cluster, member, rel, leaf in (
                ("CS0-7MOD", "CSa", "MOD", 2, "R_BUS_CSa_Type"),
                ("CS0-7WCR1", "CSa", "WCR1", 4, "R_BUS_CSa_Type"),
                ("CS0-7WCR2", "CSa", "WCR2", 8, "R_BUS_CSa_Type"),
                ("CS0CR" if index == 0 else "CS1-7CR", "CSb", "CR", 0x802, "R_BUS_CSb_Type"),
                ("CS0-7REC", "CSb", "REC", 0x80A, "R_BUS_CSb_Type")):
            add("BUS", raw, "R_BUS_Type", f"{cluster}[{index}].{member}", rel + index * 0x10, leaf, member)
    add("BUS", "CSRECEN", "R_BUS_Type", "CSRECEN")
    for name in records["BUS"]:
        if name.startswith(("BUSMABT", "BUSSABT")):
            add("BUS", name, "R_BUS_Type", name)
    for index, master in enumerate(BUS_MASTERS):
        for prefix, member, rel in (("BUSERRSTAT", "ERRSTAT", 0), ("BUSERRCLR", "ERRCLR", 4), ("BUSIRQEN", "IRQEN", 8)):
            add("BUS", prefix + master, "R_BUS_Type", f"BUSERRb[{index}].{member}",
                leaf_type="R_BUS_BUSERRb_Type", leaf_member=member)
    for name, member in (("MBWERRSTAT", "ERRSTAT"), ("MBWERRCLR", "ERRCLR")):
        add("BUS", name, "R_BUS_Type", "MBWERR." + member, leaf_type="R_BUS_MBWERR_Type", leaf_member=member)
    for name in ("DEBUGSAR", "IPCSAR", "IPCPAR"):
        add("CPSCU", name, "R_CPSCU_Type", name)
    for peripheral in ("IPC", "CPU_OCD", "CPU_DBG"):
        for name in records[peripheral]:
            if name == "IPCSEM0-15":
                for index in range(16):
                    add("IPC", name, "R_IPC_Type", f"IPCSEM[{index}]", 4 * index, leaf_member="IPCSEM")
            else:
                add(peripheral, name, "R_" + peripheral + "_Type", name)
    for prefix in ("CCA", "SCA"):
        for suffix in ("TAA", "TAD_DATA", "TAD_ECC", "TAD_TAG", "TAD_LRU", "TAD_TAGECC"):
            name = prefix + suffix
            if name == "SCATAD_TAGECC":
                # HM §2.16.3.21 p.181 is missing from the supplied SVD.
                result.append({"type": "R_CACHE_Type", "member": name, "offset": 0x58,
                               "width": 32, "access": "R/W", "fields": {"TAGECC": (0, 7, "R/W")},
                               "leaf_type": "R_CACHE_Type", "leaf_member": name})
            else:
                add("CACHE", name, "R_CACHE_Type", name)
    return result


def flattened(data, typ, base=0, prefix="", members=None):
    """Actual emitted register paths, including every array element and overlap."""
    types = {t["name"]: t for t in data["types"]}
    output = {}
    for reg in types[typ]["members"] if members is None else members:
        offset = base + header.number(reg["offset"])
        for index in range(reg.get("count", 1)):
            suffix = f"[{index}]" if "count" in reg else ""
            name = prefix + reg["name"] + suffix
            if "type" in reg:
                output.update(flattened(data, reg["type"], offset + index * reg["element_size"], name + "."))
                continue
            position = offset + index * reg["width"] // 8
            output[name] = (position, reg)
            for view in reg.get("views", []):
                output[prefix + view["name"]] = (position + view["offset"], view)
    return output


def check_source():
    lines = [(FIXTURE / "fixture.c").read_text()]
    probes = {}
    for e in expectations():
        typ, member, width = e["type"], e["member"], e["width"]
        lines += [f'_Static_assert(offsetof({typ}, {member}) == {e["offset"]}, "SVD {member} offset");',
                  f'_Static_assert(sizeof((({typ} *)0)->{member}) == {width // 8}, "SVD {member} width");']
        prefix = e["leaf_type"].removesuffix("_Type") + "_" + e["leaf_member"]
        key = (e["leaf_type"], e["leaf_member"])
        if key in probes:
            continue
        section = f".system.{len(probes)}"
        expected = bytearray()
        fields = e["fields"]
        bitfield = key[1] + "_b" + ("[0]" if key[1] == "IPCSEM" else "")
        lines += ['#ifdef __ELF__', f'__attribute__((section("{section}"), used))', '#endif',
                  f'const __typeof__((({key[0]} *)0)->{bitfield}) probe_{len(probes)}[] = {{']
        for field, (pos, bits, _) in fields.items():
            value, mask = (1 << bits) - 1, ((1 << bits) - 1) << pos
            lines.append(f'    {{ .{field} = 0x{value:X}U }},')
            expected += mask.to_bytes(width // 8, "little")
        lines.append('};')
        for field, (pos, bits, _) in fields.items():
            mask = ((1 << bits) - 1) << pos
            lines += [f'_Static_assert({prefix}_{field}_Pos == {pos}, "{prefix} {field} position");',
                      f'_Static_assert({prefix}_{field}_Msk == 0x{mask:X}UL, "{prefix} {field} mask");']
        probes[key] = (section, bytes(expected))
    for name, base in (("R_MPU_MMPU", 0x40000000), ("R_RMPU", 0x40000000), ("R_BUS", 0x40003000),
                       ("R_CPSCU", 0x40008000), ("R_IPC", 0x40020000), ("R_CPU_OCD", 0x40011000),
                       ("R_CPU_DBG", 0x4001B000), ("R_CACHE", 0x4001C000)):
        lines += [f'_Static_assert({name}_S_BASE == 0x{base:X}UL, "secure base");',
                  f'_Static_assert({name}_NS_BASE == 0x{base + 0x10000000:X}UL, "nonsecure base");',
                  f'_Static_assert({name}_BASE == (0x{base:X}UL + (BSP_TZ_NONSECURE_BUILD ? 0x10000000UL : 0)), "selected alias");']
    lines += ['#ifdef SYSTEM_NATIVE', 'int main(void)', '{']
    for index, (_, values) in enumerate(probes.values()):
        expected_bytes = ",".join(str(value) for value in values)
        lines += [f'    const unsigned char expected_{index}[] = {{{expected_bytes}}};',
                  f'    const volatile unsigned char * actual_{index} = (const volatile unsigned char *) probe_{index};',
                  f'    for (unsigned int i = 0; i < sizeof(expected_{index}); ++i)',
                  f'        if (actual_{index}[i] != expected_{index}[i]) return {index + 1};']
    lines += ['    return 0;', '}', '#endif']
    return "\n".join(lines), dict(probes.values())


class SystemHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = proposed_inventory()
        cls.rendered = header.render(copy.deepcopy(cls.data))
        cls.oracle = expectations()

    def test_fragment_and_staged_owner_additions_validate_without_duplicate_types(self):
        header.validate(copy.deepcopy(self.data))
        names = [t["name"] for t in self.data["types"]]
        self.assertEqual(len(names), len(set(names)))
        fragment = json.loads(FRAGMENT.read_text())
        self.assertEqual(5, len(fragment["instances"]))
        self.assertFalse(any(i["name"] in ("R_NPU", "R_PVD4", "R_PVD5") for i in fragment["instances"]))
        for typ in fragment["types"]:
            for member in typ["members"]:
                self.assertRegex(member["source"], r"RA8P1 HM.*§[\d.]+, p\.\d+")

    def test_every_new_register_and_field_matches_independent_svd_or_manual_delta(self):
        maps = {}
        for e in self.oracle:
            maps.setdefault(e["type"], flattened(self.data, e["type"]))
            with self.subTest(typ=e["type"], member=e["member"]):
                offset, actual = maps[e["type"]][e["member"]]
                self.assertEqual((e["offset"], e["width"], e["access"]),
                                 (offset, actual["width"], actual["access"]))
                self.assertEqual(e["fields"], {f["name"]: (f["pos"], f["bits"], f["access"])
                                               for f in actual.get("fields", [])})
        # Set equality catches fabricated registers or missing final array members.
        for typ in ("R_MPU_MMPU_Type", "R_IPC_Type", "R_CPU_OCD_Type", "R_CPU_DBG_Type"):
            self.assertEqual({e["member"] for e in self.oracle if e["type"] == typ}, set(maps[typ]))
        additions = json.loads((FIXTURE / "owning_inventory_additions.json").read_text())
        for extension in additions["extend_types"]:
            actual = flattened(self.data, extension["name"], members=extension["members"])
            expected = {e["member"] for e in self.oracle if e["type"] == extension["name"]}
            self.assertEqual(expected, set(actual))

    def test_reset_uncertainties_and_security_alias_restrictions_are_preserved(self):
        types = {t["name"]: t for t in self.data["types"]}
        for typ, granularity in (("GROUP", 32), ("EDMAC", 32), ("GLCDC", 1024), ("DRW", 1024),
                                 ("MIPI_DSI", 4096), ("CEU", 4096), ("MIPI_CSI", 4096), ("NPU", 4096)):
            region = types[f"R_MPU_MMPU_{typ}_REGION_Type"]
            for name in ("S", "E"):
                reg = next(r for r in region["members"] if r["name"] == name)
                self.assertEqual({"value": hex(0 if name == "S" else granularity - 1),
                                  "known_mask": hex(granularity - 1)}, reg["manual_reset"])
                self.assertIn("undefined", reg["reset_note"])
            if typ in ("MIPI_CSI", "NPU"):
                self.assertEqual("0x0", region["members"][2]["svd_reset"])
                self.assertEqual("0xfff", region["members"][2]["manual_reset"]["value"])
        group = {r["name"]: r for r in types["R_MPU_MMPU_GROUP_Type"]["members"]}
        self.assertIn("Non-secure alias only", group["RPT"]["source"])
        self.assertIn("Secure alias only", group["RPT_SEC"]["source"])
        for r in types["R_CPU_OCD_Type"]["members"]:
            self.assertIn("privileged CPU access", r["source"])
            self.assertIn("self-hosted debug", r["source"])
        dbg = {r["name"]: r for r in types["R_CPU_DBG_Type"]["members"]}
        for name, mask in (("DBGSTR", "0xcfffffff"), ("DBGAUTH0", "0x7fffffff"), ("ALCTRL", "0xffffff00")):
            self.assertEqual(mask, dbg[name]["manual_reset"]["known_mask"])
            self.assertIn("SVD records", dbg[name]["reset_note"])
        self.assertNotIn("MCUSTAT", {r["name"] for r in types["R_CPU_OCD_Type"]["members"]})
        cr = next(r for r in types["R_BUS_CSb_Type"]["members"] if r["name"] == "CR")
        self.assertEqual({"value": "0x21", "known_mask": "0xffff"}, cr["manual_reset_by_cs"]["0"])
        self.assertEqual("0x0", cr["svd_reset_by_cs"]["0"])
        ipcpar = next(r for r in types["R_CPSCU_Type"]["members"] if r["name"] == "IPCPAR")
        self.assertEqual({"value": "0xf0303", "known_mask": "0xf0303"}, ipcpar["manual_reset"])
        self.assertIn("write1", ipcpar["reset_note"])

    def test_native_layout_masks_aliases_and_bitfields_both_cores(self):
        compiler = shutil.which("cc")
        self.assertIsNotNone(compiler, "Native C compiler required")
        source, _ = check_source()
        with tempfile.TemporaryDirectory(prefix="ra8p1-system-native-") as tmp:
            folder = Path(tmp)
            (folder / "R7KA8P1KF.h").write_text(self.rendered)
            for core in (0, 1):
                for nonsecure in (0, 1):
                    with self.subTest(core=core, nonsecure=nonsecure):
                        result, command, obj = compile_source(compiler, folder, source, core, nonsecure, [NATIVE],
                                                             ["-DSYSTEM_NATIVE"])
                        self.assertEqual(0, result.returncode, " ".join(command) + "\n" + result.stderr)
                        executable = folder / "system-header"
                        linked = subprocess.run([compiler, str(obj), "-o", str(executable)],
                                                capture_output=True, text=True, timeout=60)
                        self.assertEqual(0, linked.returncode, linked.stderr)
                        ran = subprocess.run([str(executable)], capture_output=True, text=True, timeout=60)
                        self.assertEqual(0, ran.returncode, "Native bitfield byte probe failed: " + ran.stderr)

    def test_cm85_cm33_layout_masks_and_bitfield_bytes_with_stock_cmsis(self):
        compiler = os.environ.get("RA8P1_ARM_CC") or shutil.which("arm-none-eabi-gcc")
        self.assertIsNotNone(compiler, "Arm GCC required (set RA8P1_ARM_CC)")
        source, expected = check_source()
        with tempfile.TemporaryDirectory(prefix="ra8p1-system-arm-") as tmp:
            folder = Path(tmp)
            (folder / "R7KA8P1KF.h").write_text(self.rendered)
            cmsis = folder / "cmsis"
            extract_stock_cmsis(cmsis)
            for core in (0, 1):
                cpu, fpu = ("cortex-m85", "fpv5-d16") if core == 0 else ("cortex-m33", "fpv5-sp-d16")
                for nonsecure in (0, 1):
                    with self.subTest(core=core, nonsecure=nonsecure):
                        result, command, obj = compile_source(compiler, folder, source, core, nonsecure, [cmsis],
                                                             [f"-mcpu={cpu}", "-mthumb", f"-mfpu={fpu}", "-mfloat-abi=hard"])
                        self.assertEqual(0, result.returncode, " ".join(command) + "\n" + result.stderr)
                        sections = elf_sections(obj)
                        for name, values in expected.items():
                            self.assertEqual(values, sections[name], name)

    def test_read_only_registers_and_subfields_reject_writes(self):
        compiler = shutil.which("cc")
        self.assertIsNotNone(compiler, "Native C compiler required")
        expressions = ("R_IPC->IPC0STA0", "R_IPC->IPC1RXD1", "R_IPC->IPC1STA1_b.FULL",
                       "R_CPU_OCD->MCUERRSTAT", "R_CPU_OCD->FSBLSTATM_b.CS", "R_CPU_DBG->DBGSTR",
                       "R_CPU_DBG->DBGAUTH0_b.SWDBG", "R_CPU_DBG->FSBLSTAT_b.FSBLCLK",
                       "R_BUS->BUSERRb[10].ERRSTAT", "R_BUS->MBWERR.ERRSTAT_b.MBWERR21")
        with tempfile.TemporaryDirectory(prefix="ra8p1-system-readonly-") as tmp:
            folder = Path(tmp)
            (folder / "R7KA8P1KF.h").write_text(self.rendered)
            for expression in expressions:
                with self.subTest(expression=expression):
                    result, _, _ = compile_source(compiler, folder, '#include "R7KA8P1KF.h"\nvoid rejected(void) { '
                                                  + expression + ' = 0; }\n', includes=[NATIVE])
                    self.assertNotEqual(0, result.returncode)
                    self.assertRegex(result.stderr, r"read.only|const.qualified")


if __name__ == "__main__":
    unittest.main()
