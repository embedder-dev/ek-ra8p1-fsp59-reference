"""Check one raw EK-RA8P1 CPU0 UART boot-to-READY transcript against the XTAL plan.

Supply the exact BOOT suffix after 'BOOT EK-RA8P1 ' from the audited image
(e.g. 'r020 CPU0 Nov 24 2026 16:17:52'), not from the capture being checked.
The tag checks the reported identity; image auditing is separate. Input is the
UART payload only, with an optional WDT BOOT diagnostic between GPT0 and READY.
"""

import argparse
import json
from pathlib import Path
import re
import sys

_BUILD_TAG = (
    r"r[0-9]+ CPU0 (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r" (?: [1-9]|[12][0-9]|3[01]) [0-9]{4} (?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]"
)
_HEX = r"[0-9A-Fa-f]"
_RECORDS = {
    "BOOT": re.compile(rf"BOOT EK-RA8P1 (?P<build_tag>{_BUILD_TAG})"),
    "CLOCK": re.compile(
        rf"CLOCK SCKSCR=(?P<SCKSCR>{_HEX}{{2}}) SCKDIVCR=(?P<SCKDIVCR>{_HEX}{{8}})"
        rf" SCKDIVCR2=(?P<SCKDIVCR2>{_HEX}{{8}}) OSCSF=(?P<OSCSF>{_HEX}{{2}})"
        rf" SCICKCR=(?P<SCICKCR>{_HEX}{{2}}) SCI8_CCR2=(?P<SCI8_CCR2>{_HEX}{{8}})"
        rf" SCI8_CCR3=(?P<SCI8_CCR3>{_HEX}{{8}})"
    ),
    "GPT0": re.compile(
        rf"GPT0 GTCR=(?P<GTCR>{_HEX}{{8}}) GTPR=(?P<GTPR>0|[1-9][0-9]{{0,9}})"
        rf" CPU1ACTCSR=(?P<CPU1ACTCSR>{_HEX}{{4}})"
    ),
    "WDT": re.compile(rf"WDT BOOT RSTSR1=(?P<RSTSR1>{_HEX}{{8}}) WDT0RF=(?P<WDT0RF>[01])"),
    "READY": re.compile(r"READY"),
}
_REQUIRED_RECORDS = ("BOOT", "CLOCK", "GPT0", "READY")


def check_transcript(transcript: str, *, build_tag: str, cpu1: str) -> dict:
    """Return a JSON-ready snapshot; only a known WDT diagnostic may interleave."""
    if not re.fullmatch(_BUILD_TAG, build_tag):
        raise ValueError("build tag must be the audited BOOT suffix: rNNN CPU0 Mmm dd yyyy hh:mm:ss")
    if cpu1 not in ("active", "inactive"):
        raise ValueError("cpu1 must be 'active' or 'inactive'")

    expected = {
        "build_tag": build_tag,
        "SCKSCR": "03",
        "SCKDIVCR": "00001110",
        "SCKDIVCR2": "00000000",
        "MOSCSF": 1,
        "CST": 1,
        "GTPR": 239999,
        "ACT": int(cpu1 == "active"),
    }
    observed = {}
    errors = []
    records = []
    # splitlines() would also accept control characters as frame separators.
    lines = transcript.replace("\r\n", "\n").removesuffix("\n")
    for number, line in enumerate(lines.split("\n") if transcript else (), 1):
        kind = line.partition(" ")[0]
        pattern = _RECORDS.get(kind)
        match = pattern.fullmatch(line) if pattern else None
        if match is None:
            errors.append(f"line {number}: garbled or unexpected UART record: {line!r}")
            continue
        if kind in records:
            errors.append(f"line {number}: duplicate {kind} record")
        else:
            for field, value in match.groupdict().items():
                if field in ("GTPR", "WDT0RF"):
                    observed[field] = int(value)
                else:
                    observed[field] = value if field == "build_tag" else value.lower()
        records.append(kind)

    for kind in _REQUIRED_RECORDS:
        if kind not in records:
            errors.append(f"missing {kind} record")
    if list(dict.fromkeys(records)) != [kind for kind in _RECORDS if kind in records]:
        errors.append("UART records out of order (expected BOOT, CLOCK, GPT0, optional WDT BOOT, READY)")

    for flag, register, mask in (("MOSCSF", "OSCSF", 0x08), ("CST", "GTCR", 0x01), ("ACT", "CPU1ACTCSR", 0x80)):
        if register in observed:
            observed[flag] = int(bool(int(observed[register], 16) & mask))
    for field, value in expected.items():
        if field in observed and observed[field] != value:
            errors.append(f"{field}: expected {value!r}, observed {observed[field]!r}")

    return {"success": not errors, "expected": expected, "observed": observed, "records": records, "errors": errors}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", help="path to raw UART text (use '-' for stdin)")
    parser.add_argument("--build-tag", required=True, help="exact audited BOOT suffix after 'BOOT EK-RA8P1 '")
    parser.add_argument("--cpu1", required=True, choices=("active", "inactive"))
    args = parser.parse_args(argv)
    try:
        data = sys.stdin.buffer.read() if args.transcript == "-" else Path(args.transcript).read_bytes()
        snapshot = check_transcript(data.decode("utf-8", errors="backslashreplace"),
                                    build_tag=args.build_tag, cpu1=args.cpu1)
    except (OSError, ValueError) as error:
        parser.exit(2, f"reset_oracle: {error}\n")
    print(json.dumps(snapshot, indent=2))
    return 0 if snapshot["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
