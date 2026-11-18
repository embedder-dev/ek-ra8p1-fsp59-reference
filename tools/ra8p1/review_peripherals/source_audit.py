"""Read-only extraction of the supplied HM register descriptions for review fixtures.

Run with the folder printed by ``embedder docs fetch ra8p1-hm``. This is not
used by the production header generator and never writes a device header.
"""

from pathlib import Path
import re


CHAPTERS = {
    "GPTP": "43-36.", "MIPI_CSI0": "74-67.", "VIN0": "75-68.",
    "ECCMB0": "50-43.", "MFWD": "38-31.", "ESWM": "37-30.",
    "COMA": "39-32.", "ETHA0_NS": "40-33.", "RMAC0": "41-34.",
    "GWCA0": "42-35.", "DOTF0": "53-46.", "PDG": "31-24.",
}
HEADING = re.compile(
    r"(?m)^(?:#{3,} )?(\d+(?:\.\d+)+)\s+([A-Z][A-Za-z0-9_]*(?:\([NM]\))?)\s*:\s*([^\n]+)")


def descriptions(folder):
    """Return original HM symbols, formulas and field rows, with citations."""
    root = Path(folder)
    result = {}
    for chip, prefix in CHAPTERS.items():
        regs = []
        chapter = next(root.glob(prefix + "*"))
        for path in sorted(chapter.rglob("*.md")):
            text = path.read_text()
            headings = list(HEADING.finditer(text))
            for i, heading in enumerate(headings):
                end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
                body = text[heading.end():end]
                if i + 1 == len(headings) and "-part1.md" in path.name:
                    continuation = path.with_name(path.name.replace("-part1.md", "-part2.md"))
                    if continuation.exists():
                        more = continuation.read_text()
                        stop = HEADING.search(more)
                        body += more[:stop.start()] if stop else more
                offset = re.search(r"Offset address:\s*([^\n]+)", body)
                if not offset:
                    continue
                title = text[heading.start():heading.end()] + body[:offset.start()]
                page = list(re.finditer(r"\[page (\d+)\]", text[:heading.start()]))
                fields = []
                in_fields = False
                for line in body.splitlines():
                    cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
                    if cells[:2] == ["Bit", "Symbol"] and cells[-1:] == ["R/W"]:
                        in_fields = True
                        continue
                    if not line.startswith("|"):
                        in_fields = False
                    if not in_fields or len(cells) != 4:
                        continue
                    dynamic = re.fullmatch(r"[a-z] \([a-z] = (\d+) to (\d+)\)", cells[0])
                    if not dynamic and not re.fullmatch(r"\d+(?::\d+)?", cells[0]):
                        continue
                    if cells[1] in ("—", "–", "-"):
                        continue
                    access = re.match(r"R/W|R|W", cells[3])
                    if access is None:
                        continue
                    bits = ([int(dynamic[1]), int(dynamic[2])] if dynamic
                            else [int(v) for v in cells[0].split(":")])
                    lo, hi = min(bits), max(bits)
                    row = {"symbol": cells[1], "pos": lo, "bits": hi - lo + 1,
                           "access": access[0]}
                    if row not in fields:
                        fields.append(row)
                positions = re.findall(r"Bit position:\s*([\d ]+)", body)
                width = max((int(n) + 1 for row in positions for n in row.split()), default=0)
                regs.append({"symbol": heading[2], "section": heading[1],
                             "page": int(page[-1][1]) if page else None,
                             "path": str(path.relative_to(root)), "formula": offset[1],
                             "title": title, "width": width,
                             "fields": sorted(fields, key=lambda f: f["pos"]),
                             "text": body})
        result[chip] = regs
    return result


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(descriptions(sys.argv[1]), indent=2))
