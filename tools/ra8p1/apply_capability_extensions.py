#!/usr/bin/env python3
"""Apply the explicitly reviewed extension registry to each MCU's owning headers."""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def apply(root=ROOT, check=False):
    registry = json.loads((root / "tools/ra8p1/capability_extensions.json").read_text())
    stale = []
    for group, filename in (("features", "bsp_feature.h"), ("peripherals", "bsp_peripheral.h")):
        for path in sorted((root / "baseline/ra/fsp/src/bsp/mcu").glob("*/" + filename)):
            original = path.read_bytes()
            newline = "\r\n" if b"\r\n" in original else "\n"
            text = original.decode().replace("\r\n", "\n")
            for name, item in registry[group].items():
                if not item.get("source") or not item.get("target") or not item.get("legacy"):
                    raise ValueError("Incomplete reviewed capability: " + name)
                value = item["target" if path.parent.name == "ra8p1" else "legacy"]
                if not value.startswith("("):
                    value = "(" + value + ")"
                line = "#define " + name.ljust(69) + " " + value
                pattern = r"^#define\s+" + re.escape(name) + r"\s+[^\n]*$"
                matches = list(re.finditer(pattern, text, re.M))
                if len(matches) > 1:
                    raise ValueError("Duplicate capability: " + str(path) + ": " + name)
                if matches:
                    text = re.sub(pattern, lambda _: line, text, flags=re.M)
                else:
                    end = text.rfind("#endif")
                    if end < 0:
                        raise ValueError("Missing header guard: " + str(path))
                    text = text[:end] + line + "\n\n" + text[end:]
            data = text.replace("\n", newline).encode()
            if data != original:
                stale.append(str(path.relative_to(root)))
                if not check:
                    path.write_bytes(data)
    return stale


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = apply(check=args.check)
    print(json.dumps({"changed" if not args.check else "stale": stale}, indent=2))
    raise SystemExit(1 if args.check and stale else 0)
