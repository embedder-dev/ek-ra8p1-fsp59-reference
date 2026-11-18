"""Header checks, separate from generated FSP builds and physical qualification.

Inventory-derived probes test compiler packing/generator consistency ONLY.
Independent gates compile frozen supplied-SVD facts (with cited applicability and
manual corrections) and handwritten manual anchors against the actual header.
Arm integration uses the original CMSIS pack; RA8P1_ARM_CC selects its compiler.
No IDE, installed pack cache, target or newer FSP implementation is consulted.
"""

import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zipfile

from tools.ra8p1.test_oracles import primary

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools/ra8p1"
INCLUDE = ROOT / "baseline/ra/fsp/src/bsp/cmsis/Device/RENESAS/Include"
BSP = ROOT / "baseline/ra/fsp/src/bsp/mcu/all"
SPEC = importlib.util.spec_from_file_location("ra8p1_header", TOOLS / "generate_device_header.py")
GEN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GEN)


def run(command):
    result = subprocess.run([str(x) for x in command], capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise AssertionError(f"{' '.join(map(str, command))}\n{result.stdout}{result.stderr}")
    return result


def check_source(data):
    """Observe packing consistency only; expected numbers share the generator input."""
    GEN.validate(data)
    lines = ['#include <stddef.h>', '#include <stdint.h>', '#include "bsp_exceptions.h"',
             '#include "R7KA8P1KF.h"', ""]
    for instance in data["instances"]:
        name = instance["name"]
        for key, suffix in (("secure", "S"), ("nonsecure", "NS")):
            if key in instance:
                lines.append(f'_Static_assert({name}_{suffix}_BASE == {GEN.number(instance[key])}UL, "{name} {key}");')
        key = "nonsecure" if "secure" not in instance else "secure"
        base = GEN.number(instance[key])
        delta = " + (BSP_TZ_NONSECURE_BUILD ? 0x10000000UL : 0UL)" if "secure" in instance and "nonsecure" in instance else ""
        lines.append(f'_Static_assert({name}_BASE == ({base}UL{delta}), "{name} selected base");')
    expected, runtime = {}, []
    for selection in data.get("selections", []):
        name = selection["name"]
        for cpu, target in enumerate((selection["cpu0"], selection["cpu1"])):
            lines += [f'#if BSP_CFG_CPU_CORE == {cpu}',
                      f'_Static_assert({name}_BASE == {target}_BASE, "{name} CPU-local selection");', '#endif']
    public_blocks = [public for block in data["types"]
                     for public in [block, *[{**block, "name": alias} for alias in block.get("aliases", [])]]]
    for block in public_blocks:
        typ = block["name"]
        lines.append(f'_Static_assert(sizeof({typ}) == {GEN.number(block["size"])}, "{typ} size");')
        lines.append(f'_Static_assert(_Alignof({typ}) == {block["alignment"]}, "{typ} alignment");')
        public = list(block["members"])
        for reg in block["members"]:
            for alias in reg.get("aliases", []):
                public.append({**reg, "name": alias, "aliases": [], "views": [], "individual_names": []})
            for i, name in enumerate(reg.get("individual_names", [])):
                if name is None:
                    continue
                individual = {**reg, "name": name, "offset": GEN.number(reg["offset"]) + i * reg["width"] // 8,
                              "aliases": [], "views": [], "individual_names": []}
                individual.pop("count", None)
                public.append(individual)
            for view in reg.get("views", []):
                public.append({**view, "offset": GEN.number(reg["offset"]) + view["offset"]})
        for reg in public:
            offset, name = GEN.number(reg["offset"]), reg["name"]
            lines.append(f'_Static_assert(offsetof({typ}, {name}) == {offset}, "{typ}.{name}");')
            if "type" in reg:
                size = reg["element_size"]
            else:
                size = reg["width"] // 8
            if "count" in reg:
                last = reg["count"] - 1
                lines.append(f'_Static_assert(offsetof({typ}, {name}[{last}]) == {offset + size * last}, "{name} stride");')
            for alias in reg.get("aliases", []):
                lines.append(f'_Static_assert(offsetof({typ}, {alias}) == {offset}, "{alias} equivalent view");')
                lines.append(f'_Static_assert(sizeof((({typ} *) 0)->{alias}) == {size * reg.get("count", 1)}, "{alias} width");')
            for i, individual in enumerate(reg.get("individual_names", [])):
                if individual is None:
                    continue
                lines.append(f'_Static_assert(offsetof({typ}, {individual}) == {offset + size * i}, "{individual} array view");')
                lines.append(f'_Static_assert(sizeof((({typ} *) 0)->{individual}) == {size}, "{individual} width");')
            for view in reg.get("views", []):
                lines.append(f'_Static_assert(offsetof({typ}, {view["name"]}) == {offset + view["offset"]}, "{name} view");')
                lines.append(f'_Static_assert(sizeof((({typ} *) 0)->{view["name"]}) == {view["width"] // 8 * view.get("count", 1)}, "{name} view width");')
            if not reg.get("fields"):
                continue
            member = name + "_b" + ("[0]" if "count" in reg else "")
            index = len(expected)
            section = f".ra8p1.{index}"
            lines += ["#ifdef __ELF__", f'__attribute__((section("{section}"), used))', "#endif",
                      f"const __typeof__((({typ} *) 0)->{member}) probe_{index}[] = {{"]
            values = bytearray()
            for field in reg["fields"]:
                maximum = (1 << field["bits"]) - 1
                mask = maximum << field["pos"]
                lines.append(f'    {{ .{field["name"]} = 0x{maximum:X}U }},')
                values += mask.to_bytes(size, "little")
            lines.append("};")
            expected[section] = bytes(values)
            for n, field in enumerate(reg["fields"]):
                macro_name = field.get("macro_name", field["name"])
                mask = ((1 << field["bits"]) - 1) << field["pos"]
                if macro_name is not None:
                    prefix = f'{typ.removesuffix("_Type")}_{name}_{macro_name}'
                    lines.append(f'_Static_assert({prefix}_Pos == {field["pos"]}, "{prefix} position");')
                    lines.append(f'_Static_assert({prefix}_Msk == 0x{mask:X}UL, "{prefix} mask");')
                runtime += [f'    if (probe_{index}[{n}].{field["name"]} != 0x{(1 << field["bits"]) - 1:X}U) return 1;',
                            f'    if (read_le(&probe_{index}[{n}], {size}) != 0x{mask:X}U) return 2;']
    lines += ["#ifndef __ELF__", "static uint32_t read_le(const void * memory, unsigned size)", "{",
              "    const unsigned char * p = memory;", "    uint32_t value = 0;",
              "    for (unsigned i = 0; i < size; ++i) value |= (uint32_t) p[i] << (i * 8);",
              "    return value;", "}", "int main(void)", "{", *runtime, "    return 0;", "}", "#endif", ""]
    return "\n".join(lines), expected


def elf_sections(path):
    """Minimal ELF32 section reader; no external Python ELF package needed."""
    data = path.read_bytes()
    if data[:6] != b"\x7fELF\x01\x01":
        raise AssertionError("Expected little-endian ELF32 target object")
    section_offset = struct.unpack_from("<I", data, 32)[0]
    size, count, names_index = struct.unpack_from("<HHH", data, 46)
    sections = [struct.unpack_from("<10I", data, section_offset + n * size) for n in range(count)]
    names_record = sections[names_index]
    names = data[names_record[4]:names_record[4] + names_record[5]]
    result = {}
    for section in sections:
        end = names.find(b"\0", section[0])
        name = names[section[0]:end].decode()
        result[name] = data[section[4]:section[4] + section[5]]
    return result


class DeviceHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = GEN.load_inventory()

    def compile_primary(self, source, *, header=None, core=0, nonsecure=0):
        compiler = shutil.which("cc")
        self.assertIsNotNone(compiler, "Native compiler required for primary-source gates")
        with tempfile.TemporaryDirectory(prefix="ra8p1-primary-") as temp:
            folder = Path(temp)
            if header is not None:
                (folder / "R7KA8P1KF.h").write_text(header)
            src, exe = folder / "primary.c", folder / "primary"
            src.write_text(source)
            result = subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                                     f"-DBSP_CFG_CPU_CORE={core}", f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}",
                                     "-I", str(folder), "-I", str(TOOLS / "layout/native"),
                                     "-I", str(TOOLS / "layout"), "-I", str(INCLUDE), "-I", str(BSP),
                                     str(src), "-o", str(exe)], capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                return subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
            return result

    def test_independent_frozen_primary_registers_both_cores(self):
        source = primary.register_source()
        for core in (0, 1):
            for nonsecure in (0, 1):
                with self.subTest(core=core, nonsecure=nonsecure):
                    result = self.compile_primary(source, core=core, nonsecure=nonsecure)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_independent_manual_anchors_both_cores(self):
        for core in (0, 1):
            for nonsecure in (0, 1):
                with self.subTest(core=core, nonsecure=nonsecure):
                    result = self.compile_primary('#include "anchors.c"\nint main(void) { return 0; }\n',
                                                  core=core, nonsecure=nonsecure)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_shared_inventory_header_mutants_fail_primary_not_consistency(self):
        def register(data, typ, name):
            return next(r for b in data["types"] if b["name"] == typ
                        for r in b["members"] if r["name"] == name)

        for mutation, diagnostic in (("dac_base", "DAC0 absolute base"),
                                     ("wdt_offset", "primary R_WDT0_Type.WDTRR offset"),
                                     ("dac_width", "primary R_DAC_B0_Type.DADR width"),
                                     ("canfd_bit", "primary R_CANFD_CFDGCFG_DCS position"),
                                     ("ospi_bits", "primary R_XSPI0_CMCFGCS_CMCFG0_ADDRPEN position")):
            data = copy.deepcopy(self.data)
            if mutation == "dac_base":
                for instance in data["instances"]:
                    if instance["name"] in ("R_DAC_B0", "R_DAC_B1"):
                        for key in ("secure", "nonsecure"):
                            instance[key] = hex(GEN.number(instance[key]) + 0x2000)
            elif mutation == "wdt_offset":
                register(data, "R_WDT0_Type", "WDTRR")["offset"] = "0x1"
            elif mutation == "dac_width":
                register(data, "R_DAC_B0_Type", "DADR")["width"] = 8
            else:
                typ, member, field, pos = (("R_CANFD_Type", "CFDGCFG", "DCS", 6) if mutation == "canfd_bit"
                                          else ("R_XSPI0_CMCFGCS_Type", "CMCFG0", "ADDRPEN", 8))
                fields = register(data, typ, member)["fields"]
                next(f for f in fields if f["name"] == field)["pos"] = pos
                fields.sort(key=lambda item: item["pos"])
            with self.subTest(mutation=mutation):
                header = GEN.render(data)
                consistency, _ = check_source(data)
                result = self.compile_primary(consistency, header=header)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                source = ((TOOLS / "layout/anchors.c").read_text() + '\nint main(void) { return 0; }\n'
                          if mutation == "dac_base" else primary.register_source())
                result = self.compile_primary(source, header=header)
                self.assertNotEqual(result.returncode, 0, "Shared wrong expected/actual values escaped primary gate")
                self.assertIn(diagnostic, result.stderr)

    def test_inventory_is_valid_and_cited(self):
        GEN.validate(copy.deepcopy(self.data))
        for block in self.data["types"]:
            for register in block["members"]:
                self.assertIn("RA8P1 HM", register["source"])

    def test_reproducible_checked_in_header(self):
        expected = GEN.render(copy.deepcopy(self.data)).replace("\n", "\r\n").encode("utf-8")
        self.assertEqual(INCLUDE.joinpath("R7KA8P1KF.h").read_bytes(), expected)

    def test_generator_check_command(self):
        run([shutil.which("python3"), TOOLS / "generate_device_header.py", "--check"])

    def test_field_macro_spellings_do_not_rename_bitfields(self):
        data = copy.deepcopy(self.data)
        block = next(b for b in data["types"] if any(len(r.get("fields", [])) >= 2 for r in b["members"]))
        reg = next(r for r in block["members"] if len(r.get("fields", [])) >= 2)
        first, second = reg["fields"][:2]
        first["macro_name"], second["macro_name"] = "CANONICAL", None
        reg["views"] = [{"name": "TEST_VIEW", "offset": 0, "width": reg["width"],
                         "access": reg["access"], "fields": copy.deepcopy(reg["fields"])}]
        rendered = GEN.render(data)
        for name in (reg["name"], "TEST_VIEW"):
            prefix = block["name"].removesuffix("_Type") + "_" + name + "_"
            self.assertIn("#define " + prefix + "CANONICAL_Pos ", rendered)
            self.assertNotIn("#define " + prefix + second["name"] + "_Pos ", rendered)
        self.assertIn(f'{first["name"]} : {first["bits"]};', rendered)
        self.assertIn(f'{second["name"]} : {second["bits"]};', rendered)

    def test_reject_invalid_and_duplicate_field_macro_spellings(self):
        for view in (False, True):
            for spelling in ("not-an-identifier", 4, "DUPLICATE"):
                data = copy.deepcopy(self.data)
                reg = next(r for b in data["types"] for r in b["members"] if len(r.get("fields", [])) >= 2)
                fields = reg["fields"]
                if view:
                    reg["views"] = [{"name": "TEST_VIEW", "offset": 0, "width": reg["width"],
                                     "access": reg["access"], "fields": copy.deepcopy(fields)}]
                    fields = reg["views"][0]["fields"]
                fields[0]["macro_name"], fields[1]["macro_name"] = "DUPLICATE", spelling
                with self.subTest(view=view, spelling=spelling), self.assertRaises(ValueError):
                    GEN.validate(data)

    def test_reject_overlapping_registers(self):
        data = copy.deepcopy(self.data)
        data["types"][0]["members"][1]["offset"] = "0x0"
        with self.assertRaisesRegex(ValueError, "Overlapping/misaligned"):
            GEN.validate(data)

    def test_reject_overlapping_fields(self):
        data = copy.deepcopy(self.data)
        data["types"][0]["members"][0]["fields"][1]["pos"] = 1
        with self.assertRaisesRegex(ValueError, "Overlapping/invalid field"):
            GEN.validate(data)

    def test_reject_missing_citation(self):
        data = copy.deepcopy(self.data)
        del data["types"][0]["members"][0]["source"]
        with self.assertRaisesRegex(ValueError, "citation"):
            GEN.validate(data)

    def test_reject_bad_width_and_count(self):
        for field, value in [("width", 24), ("count", 0)]:
            with self.subTest(field=field):
                data = copy.deepcopy(self.data)
                data["types"][0]["members"][0][field] = value
                with self.assertRaises(ValueError):
                    GEN.validate(data)

    def test_reject_inconsistent_cluster_stride(self):
        data = copy.deepcopy(self.data)
        cluster = next(reg for block in data["types"] for reg in block["members"] if "type" in reg)
        cluster["element_size"] += 4
        with self.assertRaisesRegex(ValueError, "Cluster stride"):
            GEN.validate(data)

    def test_reject_inconsistent_security_alias(self):
        data = copy.deepcopy(self.data)
        data["instances"][0]["nonsecure"] = "0x60008000"
        with self.assertRaisesRegex(ValueError, "alias separation"):
            GEN.validate(data)

    def test_sparse_adc_extended_data_span_documents_reserved_indices(self):
        adc = next(block for block in self.data["types"] if block["name"] == "R_ADC_B0_Type")
        registers = {r["name"]: r for r in adc["members"]}
        self.assertEqual(23, registers["ADDR"]["count"])
        self.assertEqual([2, 3, 7, 10, 11, 12, 13, 14, 15, 19], registers["ADEXDR"]["reserved_indices"])
        self.assertNotIn("DIAGSR", {field["name"] for field in registers["ADEXDR"]["fields"]})
        self.assertIn("ADCHCR32", registers)
        self.assertNotIn("ADCHCR33", registers)
        self.assertNotIn("ADPGACR", registers)
        self.assertIn("Raw indexed span; indices 2, 3, 7", GEN.render(copy.deepcopy(self.data)))
        for invalid in ([23], [-1], [2, 2], [3, 2]):
            with self.subTest(indices=invalid):
                data = copy.deepcopy(self.data)
                reg = next(r for block in data["types"] for r in block["members"] if r["name"] == "ADEXDR")
                reg["reserved_indices"] = invalid
                with self.assertRaisesRegex(ValueError, "reserved array indices"):
                    GEN.validate(data)

    def test_no_fabricated_sibling_register_views(self):
        header = GEN.render(copy.deepcopy(self.data))
        for forbidden in ["R_FCACHE", "R_SYSTEM_SCKDIVCR2_CPUCK_Msk", "R_TZF_BASE", "R_SYSTEM_MEMWAIT",
                          "R_SYSTEM_VBTCR1", "R_SYSTEM_VBTSR"]:
            self.assertNotIn(forbidden, header)
        cpu = next(block for block in self.data["types"] if block["name"] == "R_CPU_CTRL_Type")
        self.assertTrue({"CPU0INITVTOR", "CPU1INITVTOR", "CPU1ACTCSR", "CPU1WAITCR"}.issubset({r["name"] for r in cpu["members"]}))

    def test_native_layout_widths_masks_and_bitfields_both_cores(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("No native C compiler")
        source, _ = check_source(self.data)
        with tempfile.TemporaryDirectory(prefix="ra8p1-native-") as tmp:
            src, exe = Path(tmp) / "layout.c", Path(tmp) / "layout"
            src.write_text(source)
            for core in (0, 1):
                for nonsecure in (0, 1):
                    with self.subTest(core=core, nonsecure=nonsecure):
                        run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", f"-DBSP_CFG_CPU_CORE={core}",
                             f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}", "-I", TOOLS / "layout/native", "-I", TOOLS / "layout",
                             "-I", INCLUDE, "-I", BSP, src, "-o", exe])
                        run([exe])

    def test_indexed_elc_icu_views_preserve_holes_and_nmicr(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("No native C compiler")
        with tempfile.TemporaryDirectory(prefix="ra8p1-indexed-") as tmp:
            for core in (0, 1):
                for nonsecure in (0, 1):
                    with self.subTest(core=core, nonsecure=nonsecure):
                        exe = Path(tmp) / "indexed"
                        run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined,bounds",
                             f"-DBSP_CFG_CPU_CORE={core}", f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}",
                             "-I", TOOLS / "layout/native", "-I", INCLUDE, "-I", BSP,
                             TOOLS / "layout/indexed_views.c", "-o", exe])
                        run([exe])

    def test_rtc_ioport_member_writes_preserve_adjacent_bytes(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("No native C compiler")
        with tempfile.TemporaryDirectory(prefix="ra8p1-rtc-") as tmp:
            exe = Path(tmp) / "rtc"
            for core in (0, 1):
                for nonsecure in (0, 1):
                    with self.subTest(core=core, nonsecure=nonsecure):
                        run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined",
                             f"-DBSP_CFG_CPU_CORE={core}", f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}",
                             "-I", TOOLS / "layout/native", "-I", INCLUDE, "-I", BSP,
                             TOOLS / "layout/rtc.c", "-o", exe])
                        run([exe])

    def test_shared_bsp_consumers_both_cores_security_and_inline(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("No native C compiler")
        sources = [TOOLS / "layout/shared_bsp.c", *[BSP / name for name in
                   ("bsp_irq.c", "bsp_group_irq.c", "bsp_register_protection.c", "bsp_io.c")]]
        with tempfile.TemporaryDirectory(prefix="ra8p1-shared-bsp-") as tmp:
            for core in (0, 1):
                for secure, nonsecure in ((0, 0), (1, 0), (0, 1)):
                    for inline in (0, 1):
                        with self.subTest(core=core, secure=secure, nonsecure=nonsecure, inline=inline):
                            exe = Path(tmp) / "shared"
                            run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined",
                                 f"-DBSP_CFG_CPU_CORE={core}", f"-DBSP_TZ_SECURE_BUILD={secure}",
                                 f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}", f"-DBSP_CFG_INLINE_IRQ_FUNCTIONS={inline}",
                                 "-I", TOOLS / "layout", "-I", TOOLS / "layout/native", "-I", INCLUDE,
                                 "-I", BSP, "-I", BSP.parent / "ra8p1", *sources, "-o", exe])
                            run([exe])

    def test_stock_ra8m1_shared_objects_unchanged(self):
        stock = ROOT / "validation/stock"
        database = stock / "Debug/compile_commands.json"
        if not database.is_file():
            self.skipTest("Pristine generated RA8M1 control unavailable")
        import shlex
        entries = json.loads(database.read_text())
        with tempfile.TemporaryDirectory(prefix="ra8p1-stock-objects-") as tmp:
            for name in ("bsp_irq.c", "bsp_register_protection.c"):
                with self.subTest(source=name):
                    entry = next(e for e in entries if Path(e["file"]).name == name)
                    command = shlex.split(entry["command"])
                    if not Path(command[0]).is_file():
                        self.skipTest("Recorded stock integration compiler unavailable")
                    output_index = command.index("-o") + 1
                    input_index = command.index("-x") + 2
                    results = []
                    for n, source in enumerate((Path(entry["file"]), BSP / name)):
                        obj = Path(tmp) / f"{n}.o"
                        args = command.copy()
                        args[output_index], args[input_index] = str(obj), str(source)
                        result = subprocess.run(args, cwd=entry["directory"], capture_output=True, text=True, timeout=60)
                        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                        sections = elf_sections(obj)
                        results.append({key: value for key, value in sections.items()
                                        if key.startswith((".text", ".rodata", ".data"))})
                    self.assertTrue(any(key.startswith(".text.") for key in results[0]))
                    self.assertEqual(results[0], results[1], f"RA8M1 executable/constant sections changed: {name}")

    def test_invalid_core_rejected_by_compiler(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("No native C compiler")
        result = subprocess.run([compiler, "-x", "c", "-fsyntax-only", "-DBSP_CFG_CPU_CORE=2", "-I", str(INCLUDE), "-"],
                                input='#include "R7KA8P1KF.h"\n', text=True, capture_output=True, timeout=15)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Unsupported RA8P1 core", result.stderr)

    def test_arm_layout_and_actual_bitfield_bytes_with_stock_cmsis(self):
        compiler = os.environ.get("RA8P1_ARM_CC") or shutil.which("arm-none-eabi-gcc")
        if not compiler:
            self.skipTest("No Arm GCC (set RA8P1_ARM_CC)")
        archive = ROOT / "reference/vendor/FSP_Packs_v5.9.0.zip"
        if not archive.is_file():
            self.skipTest("Original CMSIS release archive unavailable")
        source, expected = check_source(self.data)
        prefix = "ra/arm/CMSIS_6/CMSIS/Core/Include/"
        with tempfile.TemporaryDirectory(prefix="ra8p1-arm-") as tmp:
            folder = Path(tmp)
            cmsis = folder / "cmsis"
            with zipfile.ZipFile(archive) as release:
                pack_name = "internal/projectgen/ra/packs/Arm.CMSIS6.6.1.0+fsp.5.9.0.pack"
                with zipfile.ZipFile(io.BytesIO(release.read(pack_name))) as pack:
                    for name in pack.namelist():
                        if not name.startswith(prefix) or name.endswith("/"):
                            continue
                        relative = Path(name[len(prefix):])
                        if relative.is_absolute() or ".." in relative.parts:
                            raise AssertionError("Unsafe stock header path")
                        target = cmsis / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(pack.read(name))
            src, obj = folder / "layout.c", folder / "layout.o"
            src.write_text(source)
            for core in (0, 1):
                for nonsecure in (0, 1):
                    with self.subTest(core=core, nonsecure=nonsecure):
                        cpu, fpu = ("cortex-m85", "fpv5-d16") if core == 0 else ("cortex-m33", "fpv5-sp-d16")
                        run([compiler, "-std=c11", "-ffreestanding", "-Wall", "-Wextra", "-Werror", f"-mcpu={cpu}", "-mthumb",
                             f"-mfpu={fpu}", "-mfloat-abi=hard", f"-DBSP_CFG_CPU_CORE={core}", f"-DBSP_TZ_NONSECURE_BUILD={nonsecure}",
                             "-I", cmsis, "-I", TOOLS / "layout", "-I", INCLUDE, "-I", BSP, "-c", src, "-o", obj])
                        actual = elf_sections(obj)
                        for section, values in expected.items():
                            self.assertEqual(values, actual[section], f"compiler bitfield allocation: {section}")


if __name__ == "__main__":
    unittest.main()
