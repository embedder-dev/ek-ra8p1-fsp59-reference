"""Frozen primary-source gates, independent of the production inventories/generator.

The Markdown is an unchanged extraction fetched with `embedder docs fetch ra8p1-hm`.
Hashes pin both the extraction and the supplied-SVD projection so a changed candidate
cannot silently update its own expected values. This is a scoped oracle, not a claim
that every register, silicon variant or physical timing has been qualified.
"""
import hashlib
import json
from pathlib import Path
import re

ORACLES = Path(__file__).resolve().parent
HASHES = {
    "hm-event-numbers.md": "19221b9516ac43bdb07ad688d7c2719939b3ee971c44a87de4607d79008ee9d2",
    "hm-elc-registers.md": "00fe65b219ac39a3b1b55860100ac5f7608368a39afd949e7562974a8e86f313",
    "hm-function-comparison.md": "f7fa757c3d15f47bfd0ff8f72800f5c4467ebf15f34f36c8bcea2cf03f420bb8",
    "svd-shared-registers.json": "e8e2732f8249c47b55bf2db586f68c660b5ed02a40a8244971925220a415f434",
}


def frozen_text(name):
    data = (ORACLES / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != HASHES[name]:
        raise AssertionError("Primary oracle provenance changed: " + name)
    return data.decode()


def event_numbers():
    text = frozen_text("hm-event-numbers.md")
    rows = re.findall(r"^\| (0x[0-9A-Fa-f]+) \|[^|]*\| ([A-Z][A-Z0-9_]+) \|", text, re.M)
    expected = {name: int(number, 16) for number, name in rows}
    assert len(rows) == len(expected) == 490, "Incomplete HM Table 14.5 extraction"
    # HM20.2 Table20.4 includes the two DTC transfer-end events absent from Table14.5.
    elc = frozen_text("hm-elc-registers.md")
    for number, name in re.findall(r"^\| (0x[0-9A-Fa-f]+) \| DTC[01] \| (DTC[01]_DTCEND) \|", elc, re.M):
        expected[name] = int(number, 16)
    assert len(expected) == 492, "Missing primary DTC event rows"
    assert expected["PORT_IRQ29"] == 0x01E and expected["PORT_IRQ30"] == 0x01F
    return expected


def assert_event_numbers(records):
    actual = {row["manual_name"]: row["number"] for row in records}
    assert len(actual) == len(records), "Duplicate manual event name"
    expected = event_numbers()
    if actual != expected:
        differences = {name: (actual.get(name), expected.get(name))
                       for name in actual.keys() | expected.keys() if actual.get(name) != expected.get(name)}
        raise AssertionError("Primary HM event-number mismatch (candidate, manual): " + repr(differences))


def shared_registers():
    frozen_text("hm-function-comparison.md")
    oracle = json.loads(frozen_text("svd-shared-registers.json"))
    assert oracle["provenance"]["device"] == "R7KA8P1AD"
    assert oracle["provenance"]["version"] == "1.10.02"
    assert len(oracle["registers"]) == 296
    assert sum(len(row["fields"]) for row in oracle["registers"]) == 876
    return oracle["registers"]


def register_source():
    """Compile/run the real header against SVD numbers, never candidate JSON values."""
    lines = ['#include <assert.h>', '#include <stddef.h>', '#include <stdint.h>',
             '#include <string.h>', '#include "R7KA8P1KF.h"']
    checks = ['    uint32_t raw = 0;']
    for index, row in enumerate(shared_registers()):
        typ, member = row["type"], row["member"]
        lines += [f'_Static_assert(offsetof({typ}, {member}) == {row["offset"]}, "primary {typ}.{member} offset");',
                  f'_Static_assert(sizeof((({typ} *)0)->{member}) * 8 == {row["width"]}, "primary {typ}.{member} width");']
        for field_index, field in enumerate(row["fields"]):
            name, bits, pos = field["name"], field["bits"], field["pos"]
            maximum, mask = (1 << bits) - 1, ((1 << bits) - 1) << pos
            macro = field["macro_name"]
            if macro is not None:
                prefix = typ.removesuffix("_Type") + "_" + member + "_" + macro
                lines += [f'_Static_assert({prefix}_Pos == {pos}, "primary {prefix} position");',
                          f'_Static_assert({prefix}_Msk == 0x{mask:X}UL, "primary {prefix} mask");']
            probe = f'probe_{index}_{field_index}'
            checks += [f'    const __typeof__((({typ} *)0)->{member}_b) {probe} = {{ .{name} = 0x{maximum:X}U }};',
                       '    raw = 0;',
                       f'    memcpy(&raw, (void const *)&{probe}, sizeof({probe}));',
                       f'    assert(raw == 0x{mask:X}U);']
    return "\n".join(lines + ['int main(void) {'] + checks + ['    return 0;', '}', ''])
