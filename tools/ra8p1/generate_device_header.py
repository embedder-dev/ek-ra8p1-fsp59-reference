#!/usr/bin/env python3
"""Generate the reviewed RA8P1 register slice; no SVD or sibling maps are read.

The JSON inventory is the authoring input. Every numeric hardware fact carries
its hardware-manual citation there. Unlisted registers are deliberately absent,
not inferred from another RA device. Run --check to detect a stale header.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DEFAULT_OUTPUT = ROOT / "baseline/ra/fsp/src/bsp/cmsis/Device/RENESAS/Include/R7KA8P1KF.h"
IDENTIFIER = re.compile(r"[A-Za-z_]\w*\Z", re.ASCII)
QUALIFIERS = {"R": "__IM", "W": "__OM", "R/W": "__IOM"}


def number(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError(f"Invalid C identifier: {value!r}")
    return value


def cite(record):
    source = record.get("source")
    if not isinstance(source, str) or not re.search(r"§[\d.]+.*p\.", source):
        raise ValueError(f"Missing manual section/page citation: {record.get('name')}")
    if "*/" in source or "\n" in source:
        raise ValueError("Invalid citation")
    return source


def field_spellings(field):
    return [field["name"], *field.get("aliases", [])]


def macro_fields(reg):
    for field in reg.get("fields", []):
        yield field, field.get("macro_name", field["name"])
        for alias in field.get("aliases", []):
            yield field, alias


def validate_field_aliases(reg):
    names = set()
    for field in reg.get("fields", []):
        for name in field_spellings(field):
            identifier(name)
            if name in names:
                raise ValueError(f"Duplicate field: {reg['name']}.{name}")
            names.add(name)
    macros = set()
    for _, name in macro_fields(reg):
        if name is not None:
            identifier(name)
            if name in macros:
                raise ValueError(f"Duplicate field macro: {reg['name']}.{name}")
            macros.add(name)


def validate(data):
    """Reject ambiguous layouts instead of silently inventing padding or fields."""
    if data.get("schema") != 1 or data.get("device") != "R7KA8P1KF":
        raise ValueError("Unsupported inventory")
    types = {}
    for block in data["types"]:
        name = identifier(block["name"])
        if name in types:
            raise ValueError(f"Duplicate type: {name}")
        types[name] = block
        for alias in block.get("aliases", []):
            identifier(alias)
            if alias in types:
                raise ValueError(f"Duplicate type: {alias}")
            types[alias] = block
        cite(block)
        end, alignment, names, padding = 0, 1, set(), 0

        def admit(member):
            identifier(member)
            if member in names:
                raise ValueError(f"Duplicate member: {name}.{member}")
            names.add(member)

        for reg in block["members"]:
            identifier(reg["name"])
            cite(reg)
            offset, count = number(reg["offset"]), reg.get("count", 1)
            if not isinstance(count, int) or count < 1:
                raise ValueError("Invalid array count")
            individual_names = reg.get("individual_names", [])
            if individual_names and (len(individual_names) != count or "type" in reg):
                raise ValueError("Individual views must cover a scalar array exactly")
            reserved = reg.get("reserved_indices", [])
            if (not isinstance(reserved, list) or any(not isinstance(n, int) or not 0 <= n < count for n in reserved)
                    or reserved != sorted(set(reserved))):
                raise ValueError("Invalid reserved array indices")
            if "type" in reg:
                nested = types.get(reg["type"])
                if nested is None:
                    raise ValueError(f"Type must be defined before use: {reg['type']}")
                size, align = number(nested["size"]), nested["alignment"]
                if number(reg["element_size"]) != size:
                    raise ValueError(f"Cluster stride differs from type size: {reg['name']}")
            else:
                width = reg["width"]
                if width not in (8, 16, 32) or reg["access"] not in QUALIFIERS:
                    raise ValueError(f"Invalid register width/access: {reg['name']}")
                size = align = width // 8
                validate_field_aliases(reg)
                field_end, field_names, macro_names = 0, set(), set()
                for field in reg.get("fields", []):
                    identifier(field["name"])
                    macro_name = field.get("macro_name", field["name"])
                    if macro_name is not None:
                        identifier(macro_name)
                        if macro_name in macro_names:
                            raise ValueError(f"Duplicate field macro: {reg['name']}.{macro_name}")
                        macro_names.add(macro_name)
                    pos, bits = field["pos"], field["bits"]
                    if field["name"] in field_names or pos < field_end or bits < 1 or pos + bits > width:
                        raise ValueError(f"Overlapping/invalid field: {reg['name']}.{field['name']}")
                    if field["access"] not in QUALIFIERS:
                        raise ValueError("Invalid field access")
                    field_names.add(field["name"])
                    field_end = pos + bits
                for view in reg.get("views", []):
                    identifier(view["name"])
                    view_size = view["width"] // 8
                    if view["width"] not in (8, 16, 32) or view["access"] not in QUALIFIERS:
                        raise ValueError("Invalid view")
                    view_count = view.get("count", 1)
                    if (not isinstance(view_count, int) or view_count < 1 or view["offset"] < 0
                            or view["offset"] % view_size or view["offset"] + view_size * view_count > size * count):
                        raise ValueError("View exceeds register")
                    align = max(align, view_size)
                    validate_field_aliases(view)
                    view_end, view_names, macro_names = 0, set(), set()
                    for field in view.get("fields", []):
                        identifier(field["name"])
                        macro_name = field.get("macro_name", field["name"])
                        if macro_name is not None:
                            identifier(macro_name)
                            if macro_name in macro_names:
                                raise ValueError(f"Duplicate field macro: {view['name']}.{macro_name}")
                            macro_names.add(macro_name)
                        pos, bits = field["pos"], field["bits"]
                        if field["name"] in view_names or pos < view_end or bits < 1 or pos + bits > view["width"]:
                            raise ValueError("Overlapping/invalid view field")
                        if field["access"] not in QUALIFIERS:
                            raise ValueError("Invalid view field access")
                        view_names.add(field["name"])
                        view_end = pos + bits
                # render_type pads from the raw span; C must not round the
                # enclosing union beyond that span for a wider aligned view.
                if size * count % align:
                    raise ValueError(f"Invalid union extent: {name}.{reg['name']}")
            if offset < end or offset % align:
                raise ValueError(f"Overlapping/misaligned register: {name}.{reg['name']}")
            if offset > end:
                admit(f"RESERVED{padding}")
                padding += 1
            for index, member in enumerate(individual_names):
                if member is None:
                    admit(f"RESERVED_INDEX_{reg['name']}_{index}")
            for view in reg.get("views", []):
                if view["offset"]:
                    admit(f"RESERVED_{view['name']}")
            for member in [reg["name"], *reg.get("aliases", []), *[n for n in individual_names if n is not None],
                           *[v["name"] for v in reg.get("views", [])]]:
                identifier(member)
                emitted = [member]
                if (reg.get("fields") and member not in [v["name"] for v in reg.get("views", [])]
                        or any(v["name"] == member and v.get("fields") for v in reg.get("views", []))):
                    emitted.append(member + "_b")
                for public in emitted:
                    admit(public)
            end, alignment = offset + size * count, max(alignment, align)
        if number(block["size"]) > end:
            admit(f"RESERVED{padding}")
        if number(block["size"]) < end or number(block["size"]) % alignment:
            raise ValueError(f"Invalid type extent: {name}")
        block["alignment"] = alignment
    instance_names = set()
    for instance in data["instances"]:
        name = identifier(instance["name"])
        if name in instance_names or instance["type"] not in types:
            raise ValueError(f"Duplicate instance or unknown type: {name}")
        instance_names.add(name)
        cite(instance)
        for key in ("secure", "nonsecure"):
            if key in instance:
                base = number(instance[key])
                if not 0 <= base <= 0xFFFFFFFF or base % types[instance["type"]]["alignment"]:
                    raise ValueError("Invalid peripheral base")
        if "secure" in instance and "nonsecure" in instance:
            if number(instance["nonsecure"]) - number(instance["secure"]) != 0x10000000:
                raise ValueError("Invalid secure/non-secure alias separation")
    for selection in data.get("selections", []):
        name = identifier(selection["name"])
        if name in instance_names:
            raise ValueError(f"Duplicate selected instance: {name}")
        instance_names.add(name)
        cite(selection)
        selected = []
        for cpu in ("cpu0", "cpu1"):
            target = next((i for i in data["instances"] if i["name"] == selection[cpu]), None)
            if target is None:
                raise ValueError("Selected instance does not exist")
            selected.append(target["type"])
        if selected[0] != selected[1]:
            raise ValueError("Selected instances have different register types")
    for core in data["cores"]:
        for macro in core["macros"]:
            identifier(macro["name"])
            cite(macro)
            number(macro["value"])
    # Validate final preprocessor tokens, not only their unflattened parts.
    macros = set()

    def admit_macro(name):
        identifier(name)
        if name in macros:
            raise ValueError(f"Duplicate macro: {name}")
        macros.add(name)

    for name in ("R7KA8P1KF_H", "BASE_NS_OFFSET"):
        admit_macro(name)
    # Core branches are mutually exclusive; each branch still needs unique ids.
    core_names = set()
    for core in data["cores"]:
        local = set()
        for macro in core["macros"]:
            if macro["name"] in local:
                raise ValueError(f"Duplicate core macro: {macro['name']}")
            local.add(macro["name"])
        core_names.update(local)
    for name in core_names:
        admit_macro(name)
    for block in data["types"]:
        for typ in [block["name"], *block.get("aliases", [])]:
            prefix = typ.removesuffix("_Type")
            for reg in block["members"]:
                if "width" not in reg:
                    continue
                members = [reg["name"], *reg.get("aliases", []),
                           *[n for n in reg.get("individual_names", []) if n is not None]]
                for member, fields in [(n, reg) for n in members] + [(v["name"], v) for v in reg.get("views", [])]:
                    for _, field in macro_fields(fields):
                        if field is not None:
                            for suffix in ("Pos", "Msk"):
                                admit_macro(f"{prefix}_{member}_{field}_{suffix}")
    for instance in [*data["instances"], *data.get("selections", [])]:
        suffixes = ["_BASE", ""]
        for key, suffix in (("secure", "S"), ("nonsecure", "NS")):
            if key in instance or "cpu0" in instance:
                suffixes.extend((f"_{suffix}_BASE", f"_{suffix}"))
        for suffix in suffixes:
            admit_macro(instance["name"] + suffix)
    if macros.intersection(types):
        raise ValueError(f"Macro collides with type: {sorted(macros.intersection(types))}")
    return data


def bitfields(reg, suffix=""):
    aliases = [(field, alias) for field in reg.get("fields", []) for alias in field.get("aliases", [])]
    if aliases:
        # Full-width anonymous alternatives preserve both spellings at the same
        # bit position without changing the register's access unit or extent.
        out = ["        union", "        {"]
        original = {**reg, "fields": [{k: v for k, v in field.items() if k != "aliases"}
                                      for field in reg["fields"]]}
        for variant in [original, *[{**reg, "fields": [{**field, "name": alias, "aliases": []}]}
                                   for field, alias in aliases]]:
            lines = bitfields(variant)
            lines[-1] = "        };"
            out += ["    " + line for line in lines]
        return out + [f"        }} {reg['name']}_b{suffix};"]
    width = reg["width"]
    out, end = ["        struct", "        {"], 0
    for field in reg.get("fields", []):
        if field["pos"] > end:
            out.append(f"            uint{width}_t : {field['pos'] - end};")
        out.append(f"            {QUALIFIERS[field['access']]} uint{width}_t {field['name']} : {field['bits']};")
        end = field["pos"] + field["bits"]
    # Fill the entire access unit: GCC must not shrink accesses to a byte.
    if end < width:
        out.append(f"            uint{width}_t : {width - end};")
    out += [f"        }} {reg['name']}_b{suffix};"]
    return out


def render_type(block):
    out = [f"/* {cite(block)} */", "typedef struct", "{"]
    end, reserved = 0, 0
    for reg in block["members"]:
        offset, count = number(reg["offset"]), reg.get("count", 1)
        suffix = f"[{count}]" if "count" in reg else ""
        if offset > end:
            out.append(f"    uint8_t RESERVED{reserved}[0x{offset - end:X}];")
            reserved += 1
        out.append(f"    /* +0x{offset:03X}: {cite(reg)} */")
        if reg.get("reserved_indices"):
            indices = ", ".join(str(n) for n in reg["reserved_indices"])
            out.append(f"    /* Raw indexed span; indices {indices} are reserved for this view. */")
            if reg.get("reserved_note"):
                out.append(f"    /* {reg['reserved_note']} */")
        if "type" in reg:
            out.append(f"    {reg['type']} {reg['name']}{suffix};")
            size = number(reg["element_size"])
        else:
            width, size = reg["width"], reg["width"] // 8
            fields, aliases, views = reg.get("fields", []), reg.get("aliases", []), reg.get("views", [])
            individual_names = reg.get("individual_names", [])
            union = bool(fields or aliases or views or individual_names)
            if union:
                out += ["    union", "    {"]
            indent = "        " if union else "    "
            for name in [reg["name"], *aliases]:
                out.append(f"{indent}{QUALIFIERS[reg['access']]} uint{width}_t {name}{suffix};")
            if fields:
                out += bitfields(reg, suffix)
                for alias in aliases:
                    out += bitfields({**reg, "name": alias}, suffix)
            if individual_names:
                out += ["        struct", "        {"]
                for index, name in enumerate(individual_names):
                    if name is None:
                        out.append(f"            uint{width}_t RESERVED_INDEX_{reg['name']}_{index};")
                        continue
                    out += ["            union", "            {", 
                            f"                {QUALIFIERS[reg['access']]} uint{width}_t {name};"]
                    if fields:
                        out += ["        " + line for line in bitfields({**reg, "name": name})]
                    out += ["            };"]
                out += ["        };"]
            # Each narrow view is in an anonymous struct, so it overlaps the
            # raw register without incorrectly overlapping its neighbour view.
            for view in views:
                out += ["        struct", "        {"]
                if view["offset"]:
                    out.append(f"            uint8_t RESERVED_{view['name']}[{view['offset']}];")
                if view.get("fields"):
                    out += ["            union", "            {"]
                view_suffix = f"[{view['count']}]" if "count" in view else ""
                out.append(f"                {QUALIFIERS[view['access']]} uint{view['width']}_t {view['name']}{view_suffix};")
                if view.get("fields"):
                    out += ["        " + line for line in bitfields(view, view_suffix)]
                    out += ["            };"]
                out += ["        };"]
            if union:
                out += ["    };"]
        end = offset + size * count
    if number(block["size"]) > end:
        out.append(f"    uint8_t RESERVED{reserved}[0x{number(block['size']) - end:X}];")
    out += [f"}} {block['name']};"]
    out += [f"typedef {block['name']} {alias};" for alias in block.get("aliases", [])]
    out.append("")
    return out


def render(data):
    validate(data)
    out = ["/* SPDX-License-Identifier: BSD-3-Clause", " * Generated by tools/ra8p1/generate_device_header.py; do not edit.",
           " * Manual-derived RA8P1 slice, not a complete device register catalogue.",
           " * Register sources: tools/ra8p1/registers*.json.",
           f" * {data['manual']}", " */", "#ifndef R7KA8P1KF_H", "#define R7KA8P1KF_H", "", "#include <stdint.h>",
           "#ifndef BSP_CFG_CPU_CORE", '#error "BSP_CFG_CPU_CORE must select CPU0 (0) or CPU1 (1)"', "#endif", ""]
    for i, core in enumerate(data["cores"]):
        out.append(f"{'#if' if i == 0 else '#elif'} BSP_CFG_CPU_CORE == {core['cpu']}")
        for macro in core["macros"]:
            out += [f"/* {cite(macro)} */", f"#define {macro['name']} ({number(macro['value'])}U)"]
        out.append(f'#include "{core["include"]}"')
    out += ["#else", '#error "Unsupported RA8P1 core"', "#endif", '#include "system.h"', "", "#ifdef __cplusplus", 'extern "C" {', "#endif", ""]
    for block in data["types"]:
        out += render_type(block)
    public_blocks = [public for block in data["types"]
                     for public in [block, *[{**block, "name": alias} for alias in block.get("aliases", [])]]]
    for block in public_blocks:
        prefix = block["name"].removesuffix("_Type")
        for reg in block["members"]:
            if "width" not in reg:
                continue
            for member in [reg["name"], *reg.get("aliases", []), *[n for n in reg.get("individual_names", []) if n is not None]]:
                for field, macro_name in macro_fields(reg):
                    if macro_name is None:
                        continue
                    name = f"{prefix}_{member}_{macro_name}"
                    mask = ((1 << field["bits"]) - 1) << field["pos"]
                    out += [f"#define {name}_Pos ({field['pos']}U)", f"#define {name}_Msk (0x{mask:0{reg['width']//4}X}UL)"]
            for view in reg.get("views", []):
                for field, macro_name in macro_fields(view):
                    if macro_name is None:
                        continue
                    name = f"{prefix}_{view['name']}_{macro_name}"
                    mask = ((1 << field["bits"]) - 1) << field["pos"]
                    out += [f"#define {name}_Pos ({field['pos']}U)", f"#define {name}_Msk (0x{mask:X}UL)"]
    out += ["", "/* Secure/non-secure aliases follow HM Appendix 3.1; ICU and DMA banks", " * are CPU-local at identical addresses (HM §§14.2, 17.1, 18.1). */",
            "#if defined(BSP_TZ_NONSECURE_BUILD) && BSP_TZ_NONSECURE_BUILD", "#define BASE_NS_OFFSET (0x10000000UL)", "#else", "#define BASE_NS_OFFSET (0UL)", "#endif", ""]
    for instance in data["instances"]:
        name, typ = instance["name"], instance["type"]
        out.append(f"/* {cite(instance)} */")
        for key, suffix in (("secure", "S"), ("nonsecure", "NS")):
            if key in instance:
                out += [f"#define {name}_{suffix}_BASE (0x{number(instance[key]):08X}UL)", f"#define {name}_{suffix} (({typ} *) {name}_{suffix}_BASE)"]
        if "secure" in instance and "nonsecure" in instance:
            out.append(f"#define {name}_BASE ({name}_S_BASE + BASE_NS_OFFSET)")
        else:
            suffix = "S" if "secure" in instance else "NS"
            out.append(f"#define {name}_BASE {name}_{suffix}_BASE")
        out.append(f"#define {name} (({typ} *) {name}_BASE)")
    for selection in data.get("selections", []):
        name = selection["name"]
        out += [f"/* {cite(selection)} */", "#if BSP_CFG_CPU_CORE == 0"]
        for n, cpu in enumerate(("cpu0", "cpu1")):
            if n:
                out.append("#else")
            target = selection[cpu]
            for suffix in ("_S_BASE", "_NS_BASE", "_S", "_NS", "_BASE", ""):
                out.append(f"#define {name}{suffix} {target}{suffix}")
        out.append("#endif")
    out += ["", "#ifdef __cplusplus", "}", "#endif", "#endif /* R7KA8P1KF_H */", ""]
    return "\n".join(out)


def load_inventory(paths=None):
    paths = paths or sorted(HERE.glob("registers*.json"))
    data, updates = None, []
    for path in paths:
        fragment = json.loads(Path(path).read_text())
        updates.extend(fragment.get("register_updates", []))
        if data is None:
            data = fragment
        else:
            data["types"].extend(fragment["types"])
            data["instances"].extend(fragment["instances"])
    if data is None:
        raise ValueError("No register inventory")
    for update in updates:
        cite(update)
        blocks = [b for b in data["types"] if b["name"] == update["type"]]
        registers = [r for b in blocks for r in b["members"] if r["name"] == update["register"]]
        if len(blocks) != 1 or len(registers) != 1:
            raise ValueError(f"Ambiguous register update: {update['type']}.{update['register']}")
        reg = registers[0]
        expected = update["expected"]
        if any((number(reg[k]) != number(v) if k == "offset" else reg[k] != v)
               for k, v in expected.items()):
            raise ValueError(f"Register update layout changed: {update['register']}")
        if "view" in update:
            views = [v for v in reg.get("views", []) if v["name"] == update["view"]]
            if len(views) != 1:
                raise ValueError(f"Ambiguous register view update: {update['view']}")
            reg = views[0]
        for field, aliases in update.get("field_aliases", {}).items():
            fields = [f for f in reg.get("fields", []) if f["name"] == field]
            if len(fields) != 1:
                raise ValueError(f"Ambiguous field update: {field}")
            fields[0].setdefault("aliases", []).extend(aliases)
        if "add_fields" in update:
            if reg.get("fields"):
                raise ValueError(f"Register update would replace fields: {reg['name']}")
            reg["fields"] = update["add_fields"]
        reg.setdefault("aliases", []).extend(update.get("aliases", []))
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render(load_inventory()).replace("\n", "\r\n").encode("utf-8")
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != expected:
            parser.exit(1, f"stale generated header: {args.output}\n")
    else:
        args.output.write_bytes(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
