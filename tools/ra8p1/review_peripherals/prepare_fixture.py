"""One-time source crosscheck/authoring helper; never writes the owning header."""
import copy
import itertools
import json
import os
from pathlib import Path
import re

from source_audit import descriptions

ROOT = Path(__file__).resolve().parents[3]
DOC = Path(os.environ["EMBEDDER_DOCS_DIR"]) / "ra8p1-hm"
HM = descriptions(DOC)
SVD = {p["name"]: p for p in json.loads((ROOT / ".embedder/svd-cache/R7KA8P1AD.json").read_text())["peripherals"]}
ACCESS = {"read-only": "R", "write-only": "W", "read-write": "R/W"}
INSTANCES = {
    "GPTP": ["GPTP"], "MIPI_CSI0": ["MIPI_CSI0"], "VIN0": ["VIN0"],
    "ECCMB0": ["ECCMB0", "ECCMB1"], "MFWD": ["MFWD"], "ESWM": ["ESWM"],
    "COMA": ["COMA"], "ETHA0_NS": ["ETHA0", "ETHA1"], "RMAC0": ["RMAC0", "RMAC1"],
    "GWCA0": ["GWCA0"], "DOTF0": ["DOTF0", "DOTF1", "DOTF"], "PDG": ["PDG"],
}
SCALARS = {"FWLTHTL80", "FWLTHTSR40", "FWMACTL40", "FWMACTSR20", "FWMACTRR50", "FWVLANTL30", "FWVLANTSR20"}


def citation(reg):
    return f"RA8P1 HM R01UH1064EJ0130 Rev.1.30 §{reg['section']}, p.{reg['page']}"


def evaluate(expression, env):
    for var, value in env.items():
        expression = re.sub(r"\b" + var + r"\b", str(value), expression)
    assert re.fullmatch(r"[\dxa-fA-F+* ()]+", expression), expression
    return eval(expression, {"__builtins__": {}}, {})


def values(reg, chip):
    title = re.sub(r"\s+", " ", reg["title"] + " " + reg["formula"])
    dims = {}
    for variable, items in re.findall(r"\(([a-zA-Z])\s*=\s*(\d+(?:\s*(?:to|,)\s*\d+)*)\)", title):
        vs = [int(v) for v in re.findall(r"\d+", items)]
        dims[variable] = list(range(vs[0], vs[-1] + 1)) if "to" in items else vs
    expression = re.split(r"\s+\([A-Za-z]\s*=", reg["formula"])[0].strip().replace("×", "*")
    if reg["symbol"] in SCALARS:
        expression = re.search(r"0x[0-9A-Fa-f]+", expression)[0]
    variables = set(re.findall(r"(?<![A-Za-z0-9_])([a-zA-Z])\b", re.sub(r"0x[\da-fA-F]+", "", expression)))
    dims = {k: v for k, v in dims.items() if k in variables}
    if chip == "COMA" and reg["symbol"] == "CABPPFLCi":
        dims = {"i": [0, 1]}
    if chip == "RMAC0" and reg["symbol"] == "MTPFC3t":
        dims = {"t": [0, 1]}  # HM §34.6.3: MTPFC30/MTPFC31, priority groups0/1.
    if chip == "MFWD" and reg["symbol"] in ("FWRFCi", "FWRFVCi"):
        dims = {"i": [0, 1]}
    assert variables <= dims.keys(), (chip, reg["symbol"], expression, dims, variables)
    expanded = []
    for nums in itertools.product(*dims.values()):
        env = dict(zip(dims, nums))
        name = reg["symbol"]
        for var, val in env.items():
            name = name.replace("(" + var + ")", str(val)).replace(var, str(val))
        assert re.fullmatch(r"[A-Za-z_]\w*", name), name
        expanded.append((name, evaluate(expression, env), env))
    return dims, expanded


def fields(reg, svd, chip, notes, env=None):
    env = env or {"i": 0}
    result = []
    for field in svd["fields"]:
        covers = [h for h in reg["fields"] if h["pos"] <= field["bitOffset"]
                  and h["pos"] + h["bits"] >= field["bitOffset"] + field["bitWidth"]]
        if not covers:
            notes.append({"register": chip + "." + reg["symbol"],
                          "note": f"SVD field {field['name']} bit{field['bitOffset']} width{field['bitWidth']} is reserved in {citation(reg)}; not emitted."})
            continue
        assert ACCESS[field["access"]] == covers[0]["access"]
        name = field["name"]
        if chip == "DOTF0" and reg["symbol"] == "CONVAREAD":
            name = "CONVAREAD"
        span = re.fullmatch(r"(\w+?)(\d+) to \1(\d+)", name)
        if span:
            stem, hi, lo = span[1], int(span[2]), int(span[3])
            assert hi - lo + 1 == field["bitWidth"]
            result.extend({"name": stem + str(k), "pos": field["bitOffset"] + k - lo,
                           "bits": 1, "access": covers[0]["access"]} for k in range(lo, hi + 1))
        else:
            assert re.fullmatch(r"[A-Za-z_]\w*", name), name
            result.append({"name": name, "pos": field["bitOffset"], "bits": field["bitWidth"], "access": covers[0]["access"]})
    for h in reg["fields"]:
        mask = ((1 << h["bits"]) - 1) << h["pos"]
        covered = sum(((1 << f["bits"]) - 1) << f["pos"] for f in result
                      if h["pos"] <= f["pos"] and f["pos"] + f["bits"] <= h["pos"] + h["bits"])
        if covered == mask:
            continue
        assert covered == 0, (chip, reg["symbol"], h, covered)
        name = re.sub(r"\[.*?\]|\*\d+", "", h["symbol"]).strip()
        if name == "n/a":
            continue
        dynamic = re.fullmatch(r"(\w+)([a-z]) \(\2 = (.+)\)", name)
        if dynamic:
            for bit in range(h["pos"], h["pos"] + h["bits"]):
                index = evaluate(dynamic[3].replace("×", "*"), {**env, "b": bit})
                result.append({"name": dynamic[1] + str(index), "pos": bit, "bits": 1, "access": h["access"]})
            continue
        assert re.fullmatch(r"[A-Za-z_]\w*", name), (chip, reg["symbol"], name)
        result.append({"name": name, "pos": h["pos"], "bits": h["bits"], "access": h["access"]})
    return sorted(result, key=lambda f: f["pos"])


def main():
    types, instances, fixture, notes = [], [], {}, []
    for chip, specs in HM.items():
        typ = "R_DOTF_Type" if chip == "DOTF0" else "R_" + chip.removesuffix("_NS") + "_Type"
        members, expected, dimensions = [], [], []
        for reg in specs:
            sym = reg["symbol"]
            if chip == "GWCA0" and sym == "GWIDCi":
                continue
            first = int(re.search(r"0x[0-9A-Fa-f]+", reg["formula"])[0], 16)
            s = next(s for s in SVD[chip]["registers"] if s["addressOffset"] == first)
            assert reg["width"] == s["size"]
            dims, expanded = values(reg, chip)
            fs = fields(reg, s, chip, notes)
            modes = {h["access"] for h in reg["fields"]}
            assert modes, (chip, sym)
            acc = next(iter(modes)) if len(modes) == 1 else "R/W"
            for name, offset, env in expanded:
                specific = next((v for v in SVD[chip]["registers"] if v["addressOffset"] == offset), s)
                actual_fields = fields(reg, specific, chip, notes, env)
                item = {"name": name, "offset": hex(offset), "width": reg["width"], "access": acc,
                        "source": citation(reg), "manual_path": reg["path"]}
                if actual_fields:
                    item["fields"] = copy.deepcopy(actual_fields)
                members.append(item)
                expected.append({"name": name, "offset": offset, "width": reg["width"], "access": acc,
                                 "source": citation(reg), "fields": reg["fields"]})
            if dims:
                dimensions.append({"symbol": sym, "formula": reg["formula"], "dimensions": dims,
                                   "members": [(n, o) for n, o, _ in expanded], "source": citation(reg)})
            for path in (DOC / reg["path"].split("/")[0]).glob("*register-list.md"):
                text = path.read_text()
                for m in re.finditer(r"(?m)^\| (0x[^|]+)\|([^\n]+)$", text):
                    if " E:" not in m[1] or sym not in [c.strip() for c in m[2].split("|")]:
                        continue
                    ef = m[1].split("E:")[1].strip().replace("×", "*")
                    page = int(list(re.finditer(r"\[page (\d+)\]", text[:m.start()]))[-1][1])
                    for name, _, env in expanded:
                        off = evaluate(ef, env)
                        members.append({"name": name + "_E", "offset": hex(off), "width": reg["width"],
                                        "access": "R", "fields": [{**f, "access": "R"} for f in fs],
                                        "source": f"RA8P1 HM R01UH1064EJ0130 Rev.1.30 §{reg['section'].split('.')[0]}.2, p.{page} (non-clearing emulation view)",
                                        "manual_path": str(path.relative_to(DOC))})
                        expected.append({"name": name + "_E", "offset": off, "width": reg["width"], "access": "R",
                                         "source": citation(reg), "fields": [{**h, "access": "R"} for h in reg["fields"]]})
        members.sort(key=lambda m: int(m["offset"], 0))
        expected.sort(key=lambda m: m["offset"])
        for a, b in zip(members, members[1:]):
            assert int(a["offset"], 0) + a["width"] // 8 <= int(b["offset"], 0), (chip, a["name"], b["name"])
        for d in dimensions:
            ex = d["members"]
            if len(d["dimensions"]) != 1 or len(ex) < 2:
                continue
            start = next(i for i, m in enumerate(members) if m["name"] == ex[0][0])
            original = members[start:start + len(ex)]
            width = original[0]["width"] // 8
            if ([m["name"] for m in original] != [n for n, _ in ex]
                    or any(b[1] - a[1] != width for a, b in zip(ex, ex[1:]))
                    or any(m.get("fields") != original[0].get("fields") for m in original)):
                continue
            var = next(iter(d["dimensions"]))
            array = d["symbol"].replace("(" + var + ")", "").replace(var, "")
            if array in {m["name"] for m in members}:
                continue
            members[start:start + len(ex)] = [{**original[0], "name": array, "count": len(ex),
                                               "individual_names": [n for n, _ in ex], "array_formula": d["formula"]}]
            d["array"] = array
        alignment = max(m["width"] // 8 for m in members)
        end = max(int(m["offset"], 0) + m.get("count", 1) * m["width"] // 8 for m in members)
        size = (end + alignment - 1) // alignment * alignment
        block = {"name": typ, "size": hex(size), "source": citation(specs[0]), "members": members}
        if chip == "DOTF0":
            block["aliases"] = ["R_DOTF0_Type"]
        types.append(block)
        fixture[typ] = {"size": size, "alignment": alignment, "views": expected, "dimensions": dimensions}
        for name in INSTANCES[chip]:
            sn = "DOTF0" if name == "DOTF" else name
            s = SVD.get(sn) or SVD.get(sn + "_NS")
            base = s["baseAddress"] - (0x10000000 if sn not in SVD else 0)
            instances.append({"name": "R_" + name, "type": typ, "secure": hex(base), "nonsecure": hex(base + 0x10000000),
                              "source": "RA8P1 HM R01UH1064EJ0130 Rev.1.30 §3.1 Appendix3 TableA3.1, p.4286–4288"})
    notes = list({json.dumps(note, sort_keys=True): note for note in notes}.values())
    notes.extend([
        {"register": "DOTF0/1.CONVAREAD", "kind": "reset conflict", "svd": 0, "hm": 4095,
         "source": "HM §46.3.2 pp3059–3060", "decision": "Unresolved: no reset constant or initializer emitted. Offset, width and bits31:12 agree; FSP5.9 field vocabulary CONVAREAD retained."},
        {"register": "GWCA0.GWIDCi", "kind": "address conflict", "svd": "0xC000 + 4*i", "hm_description": "0x0C000 + 4*i", "hm_list": "0x0C00 + 4*i",
         "source": "HM Table35.3 p1800 vs §35.3.9.2", "decision": "Unresolved: omit GWIDC0..63 pending address adjudication."},
        {"register": "GPTP.PTPSCR0/1/2", "kind": "missing descriptions", "source": "HM Table36.3 p1936; no matching §36.3 description or SVD records",
         "decision": "Unresolved: offsets0x780/0x784/0x788 known, width/access/fields unknown. No speculative register view emitted."},
        {"register": "ESWM.TPEMIMC0", "kind": "missing description", "svd": "offset0, read-write, 13 fields", "source": "HM §30.2.2 pp1302–1307 begins at TPEMIMC1 offset4",
         "decision": "Unresolved: no matching description; offset0 remains reserved."},
        {"register": "MFWD.FWRFCi/FWRFVCi", "kind": "dimension conflict", "svd": "i=0..15", "hm_description": "i=0..15", "hm_list": "i=0,1",
         "source": "HM Table31.3 p1333 vs §§31.3.1.3.9–10", "decision": "Emit only common indices0,1. Indices2..15 withheld pending adjudication."},
        {"register": "ESWM.TPEMIMC6t/7t", "kind": "dimension correction", "svd": "both t=0..4", "hm": "6t: t=0..1; 7t: t=0..63",
         "source": "HM §§30.2.2.5–6 pp1306–1307", "decision": "Use documented bounds, not compact SVD spelling."},
        {"register": "MFWD scalar CPU-subdestination registers", "kind": "unbound formula variable", "source": "HM Table31.3 pp1334–1335; §§31.3.1.5.11,31.3.1.5.25,31.3.1.6.7,31.3.1.6.16,31.3.1.6.24,31.3.1.6.34,31.3.1.6.42",
         "decision": "List and SVD have only literal *0 registers. Descriptions append +4*i without bound/indexed symbol; emit scalar index0 only."},
    ])
    import hashlib
    out = {"types": types, "instances": instances,
           "primary_svd": {"name": "R7KA8P1AD", "version": "1.10.02", "sha256": hashlib.sha256((ROOT / ".embedder/svd-cache/R7KA8P1AD.json").read_bytes()).hexdigest()},
           "applicability": {"device": "R7KA8P1KFLCAC", "source": "HM §§1.3–1.4 pp77–80; Table1.15 KxxCAC has MIPI CSI, VIN, ESWM, CANFD ECC, four PDG channels and DOTF."},
           "source_discrepancies": notes,
           "source_policy": "Primary supplied R7KA8P1AD.json v1.10.02 checked against HM Rev1.30 descriptions. HM formulas establish counts/strides. Ambiguous views explicitly withheld; NPU excluded without its matching TRM."}
    for block in fixture.values():
        tables = {}
        for view in block["views"]:
            table = view["source"] + (" E" if view["name"].endswith("_E") else "")
            tables[table] = view.pop("fields")
            view["table"] = table
            del view["source"]
        block["field_tables"] = tables
    (ROOT / "tools/ra8p1/registers_review_peripherals.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    (Path(__file__).parent / "hm_layout.json").write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n")
    for t in types:
        print(t["name"], t["size"], len(t["members"]))
    print("types", len(types), "instances", len(instances), "views", sum(len(v["views"]) for v in fixture.values()))


if __name__ == "__main__":
    main()
