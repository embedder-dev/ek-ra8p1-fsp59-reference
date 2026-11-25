"""Run a UART-only paired MIC1 soak; profile {"count": N} overrides 300 captures."""

import asyncio
import json
from pathlib import Path
import re
import tempfile
import time

EVIDENCE = Path("validation/ek-ra8p1/evidence")
PORT = "/dev/cu.usbmodem0010808410141"
BAUD = 115200
ACK_TIMEOUT_S = 4.0
DEFAULT_COUNT = 300
CHUNK_SIZE = 50
SAMPLES = 2048
PCM_RAIL = 1 << 19
CPU1_ACTIVE = 0x0080
# RA8P1 PFS ASEL/PMR/PSEL fields: digital peripheral mode, PDM function 0x1b.
PFS_MASK = 0x1F018000
PFS_PDM = 0x1B010000

PREFLIGHT = re.compile(r"PDM preflight PCLKB=([0-9]{1,10}) MCSTP=([01]) P812=([0-9a-f]{8}) P502=([0-9a-f]{8})")
CAPTURE = re.compile(
    r"PDM capture samples=([0-9]{1,10}) complete=([0-9]{1,10}) errors=([0-9]{1,10}) "
    r"overruns=([0-9]{1,10}) flags=0x([0-9a-f]{8}) timeout=([01])"
)
PCM = re.compile(r"PDM PCM min=(-?[0-9]{1,10}) max=(-?[0-9]{1,10}) mean=(-?[0-9]{1,10}) "
                 r"mean_abs=([0-9]{1,10}) clips=([0-9]{1,10})")
CLOCK = re.compile(r"CLOCK SCKSCR=[0-9a-f]{2} SCKDIVCR=[0-9a-f]{8} SCKDIVCR2=[0-9a-f]{8} "
                   r"OSCSF=[0-9a-f]{2} SCICKCR=[0-9a-f]{2} SCI8_CCR2=[0-9a-f]{8} SCI8_CCR3=[0-9a-f]{8}")
GPT0 = re.compile(r"GPT0 GTCR=([0-9a-f]{8}) GTPR=([0-9]{1,10}) CPU1ACTCSR=([0-9a-f]{4})")


def parse_line(pattern, line):
    match = pattern.fullmatch(line)
    if match is None:
        raise ValueError(f"Malformed or out-of-order UART line: {line!r}")
    return match.groups()


def check_pdm(lines):
    if len(lines) != 5 or lines[-2:] != ["PDM PASS", "ACK pdm"]:
        raise ValueError("Expected PDM preflight, capture, PCM, PASS and ACK in order")

    pclkb, mcstp, p812, p502 = parse_line(PREFLIGHT, lines[0])
    if (mcstp != "0" or not 1_000_000 <= int(pclkb) <= 62_500_000 or
            any(int(pin, 16) & PFS_MASK != PFS_PDM for pin in (p812, p502))):
        raise ValueError("PDM preflight clock or MIC1 pin mux is invalid")

    fields = parse_line(CAPTURE, lines[1])
    for key, value, expected in zip(
            ("samples", "complete", "errors", "overruns", "flags", "timeout"), fields, (SAMPLES, 1, 0, 0, 0, 0)):
        if int(value, 16 if key == "flags" else 10) != expected:
            raise ValueError(f"PDM capture {key}={value}, expected {expected}")

    low, high, mean, mean_abs, clips = map(int, parse_line(PCM, lines[2]))
    rails = int(low == -PCM_RAIL) + int(high == PCM_RAIL - 1)
    clip_floor = clips * (PCM_RAIL - 1) // SAMPLES
    if (not -PCM_RAIL <= low < high < PCM_RAIL or not low <= mean <= high or
            not max(abs(mean), low, -high, clip_floor) <= mean_abs <= max(abs(low), abs(high)) or
            not rails <= clips < SAMPLES or (not rails and clips)):
        raise ValueError("PDM PCM statistics are corrupt, constant or fully clipped")
    return {"samples": SAMPLES, "min": low, "max": high, "mean": mean, "mean_abs": mean_abs, "clips": clips}


def check_clocks(lines):
    # The general CLOCK register line is optional; GPT0 carries the active bit.
    if len(lines) == 3:
        parse_line(CLOCK, lines[0])
        lines = lines[1:]
    if len(lines) != 2 or lines[1] != "ACK clocks":
        raise ValueError("Expected one GPT0 status line followed by ACK clocks")
    gtcr, gtpr, cpu1 = parse_line(GPT0, lines[0])
    if int(gtpr) > 0xFFFFFFFF:
        raise ValueError("GPT0 GTPR does not fit in 32 bits")
    if not int(cpu1, 16) & CPU1_ACTIVE:
        raise ValueError(f"CPU1 inactive (CPU1ACTCSR={cpu1})")
    return {"gtcr": int(gtcr, 16), "gtpr": int(gtpr), "cpu1actcsr": int(cpu1, 16)}


def write_record(transcript, record):
    transcript.write(json.dumps(record) + "\n")
    transcript.flush()


def fresh_lines():
    return serial_read_history(PORT, baud_rate=BAUD, only_new=True)


async def exchange(command, transcript, chunk, capture_index):
    start = time.monotonic_ns()
    record = {"type": "response", "command": command, "chunk": chunk, "capture_index": capture_index,
              "start_monotonic_ns": start, "lines": [], "success": False}
    marker = f"ACK {command}"
    try:
        serial_send(PORT, command, baud_rate=BAUD)
        wait_start = time.monotonic_ns()
        # Live reads normalize line endings; history must still contain the exact ACK line.
        await serial_read(PORT, baud_rate=BAUD, timeout_seconds=ACK_TIMEOUT_S, stop_string=marker)
        record["wait_ns"] = time.monotonic_ns() - wait_start
        record["lines"] = lines = fresh_lines()
        if "PDM FAIL" in lines:
            raise ValueError("Firmware reported PDM FAIL")
        if record["wait_ns"] >= ACK_TIMEOUT_S * 1_000_000_000:
            raise TimeoutError(f"No complete {marker!r} within {ACK_TIMEOUT_S:g} s")
        if marker not in lines:
            raise ValueError(f"No fresh {marker!r} after the live read")
        record["values"] = (check_pdm if command == "pdm" else check_clocks)(lines)
        record["success"] = True
    except Exception as error:
        record["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        end = time.monotonic_ns()
        record.update(end_monotonic_ns=end, elapsed_ns=end - start)
        write_record(transcript, record)


async def run(profile, directory=EVIDENCE):
    count = profile.get("count", DEFAULT_COUNT)
    if type(count) is not int or not 1 <= count <= 5000:
        return {"success": False, "summary": "PDM soak profile count must be an integer from 1 to 5000"}

    data = {"requested": count, "captures_passed": 0, "chunks_passed": 0, "clock_checks_passed": 0}
    result = {"success": False, "data": data}
    start = time.monotonic_ns()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False,
                                         prefix=f"pdm-soak-{time.time_ns()}-", suffix=".jsonl") as transcript:
            data["transcript"] = transcript.name
            write_record(transcript, {"type": "start", "requested": count, "chunk_size": CHUNK_SIZE,
                                      "port": PORT, "baud": BAUD, "start_monotonic_ns": start})
            try:
                # Live and history buffers are independent; reset both before the first send.
                await serial_read(PORT, baud_rate=BAUD, timeout_seconds=0.05)
                fresh_lines()
                await exchange("clocks", transcript, chunk=0, capture_index=0)
                data["clock_checks_passed"] += 1
                for chunk, first in enumerate(range(1, count + 1, CHUNK_SIZE), 1):
                    last = min(first + CHUNK_SIZE - 1, count)
                    for index in range(first, last + 1):
                        await exchange("pdm", transcript, chunk, index)
                        data["captures_passed"] += 1
                    await exchange("clocks", transcript, chunk, last)
                    data["clock_checks_passed"] += 1
                    data["chunks_passed"] += 1
                trailing = fresh_lines()
                if trailing:
                    write_record(transcript, {"type": "unsolicited", "lines": trailing,
                                              "monotonic_ns": time.monotonic_ns()})
                    raise ValueError("Unexpected UART output after final ACK clocks")
                result["success"] = True
            except Exception as error:
                result["summary"] = (f"MIC1 soak stopped after {data['captures_passed']}/{count} captures, "
                                     f"{data['chunks_passed']} checked chunks: {error}")
            data["elapsed_ns"] = time.monotonic_ns() - start
            if result["success"]:
                result["summary"] = (f"MIC1: {count}/{count} clean {SAMPLES}-sample captures in "
                                     f"{data['elapsed_ns'] / 1e9:.1f} s; CPU1 was active at all "
                                     f"{data['clock_checks_passed']} UART checkpoints")
            write_record(transcript, {"type": "summary", **result})
    except OSError as error:
        result.update(success=False, summary=f"Could not save PDM soak evidence: {error}")
    return result


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run(globals().get("capture_profile", {})))))
