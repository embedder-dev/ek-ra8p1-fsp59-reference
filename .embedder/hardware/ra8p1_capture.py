"""Input-only EK-RA8P1 logic checks for hardware_script_run.

Profiles:
  {"action": "mapping"} (default): map P514/P111/P806/P807 at the boot divider.
  {"action": "timing", "expected_dio": 3, "expected_period_ms": 40}:
      Select P514 (m0), then measure after c1 (40 ms) or c0 (20 ms).
      Use the DIO found for P514, not the example value. Run 20, 40, 20
      to measure the divider transition and restoration. c0/c1 must leave
      P514 toggling. Successful runs end with idle, not a divider change.
"""

import asyncio
import json
import math
import time
from pathlib import Path

AD3_ID = "210415BE5124"
UART_PORT = "/dev/cu.usbmodem0010808410141"
BAUD = 115200
ACK_TIMEOUT_S = 3.0
PINS = {"m0": "P514", "m1": "P111", "m2": "P806", "m3": "P807"}
DIO = tuple(range(16))
# 4000 packed samples; 10 periods even at /2, with 0.1 ms resolution.
SAMPLE_RATE = 10_000
DURATION_S = 0.4
MIN_RISES = 8
PERIOD_TOLERANCE = 0.01


async def send_command(command, data):
    marker = f"ACK {command}"
    entry = {"command": command, "ack": None}
    data["uart"].append(entry)
    # The live read buffer can retain older ACKs. Only trust history since send.
    serial_read_history(UART_PORT, baud_rate=BAUD, only_new=True)
    serial_send(UART_PORT, command, baud_rate=BAUD)
    deadline = time.monotonic() + ACK_TIMEOUT_S
    while (remaining := deadline - time.monotonic()) > 0:
        await serial_read(UART_PORT, baud_rate=BAUD, timeout_seconds=remaining,
                          stop_string="\n")
        lines = serial_read_history(UART_PORT, baud_rate=BAUD, only_new=True)
        if any(line.strip() == marker for line in lines):
            entry["ack"] = marker
            return
        if lines:
            entry["last_lines"] = lines[-5:]
    raise RuntimeError(f"No fresh {marker!r} on SCI8 at {BAUD} baud")


def analyze(capture, report, expected_dio, used_dio):
    samples = capture["samples"]
    rate = float(capture["sampleRate"])
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError("Analyzer did not return a valid sample rate")
    if sorted(capture["enabled_channels"]) != list(DIO) or capture.get("sampleFormat", 16) != 16:
        raise ValueError("Analyzer did not capture all 16 DIO inputs in 16-bit words")

    report.update(sample_rate_sps=rate, sample_count=len(samples),
                  duration_s=len(samples) / rate,
                  lost_samples=capture.get("lostSamples"),
                  corrupted_samples=capture.get("corruptedSamples"))
    rising = [[] for _ in DIO]
    falling = [0 for _ in DIO]
    previous = None
    for index, sample in enumerate(samples):
        if not isinstance(sample, int) or not 0 <= sample <= 0xFFFF:
            raise ValueError("Analyzer samples are not packed 16-bit DIO words")
        if previous is not None:
            changed = previous ^ sample
            while changed:
                bit = changed & -changed
                channel = bit.bit_length() - 1
                if sample & bit:
                    rising[channel].append(index)
                else:
                    falling[channel] += 1
                changed ^= bit
        previous = sample

    moving = [ch for ch in DIO if rising[ch] or falling[ch]]
    report.update(moving_dio=moving, rising_edges=[len(edges) for edges in rising],
                  falling_edges=falling)
    errors = report["errors"]
    expected_count = round(DURATION_S * SAMPLE_RATE)
    if len(samples) != expected_count:
        errors.append(f"Incomplete capture: {len(samples)} samples, expected {expected_count}")
    if report["lost_samples"] or report["corrupted_samples"]:
        errors.append("Analyzer reported lost or corrupt samples")
    if len(moving) != 1:
        errors.append(f"Expected exactly one moving DIO; observed {moving}")
    else:
        channel = moving[0]
        report["dio"] = channel
        if expected_dio is not None and channel != expected_dio:
            errors.append(f"Expected DIO{expected_dio}; observed DIO{channel}")
        if channel in used_dio:
            errors.append(f"DIO{channel} already mapped to another pin")
        edges = rising[channel]
        report["rising_sample_indices"] = edges
        if len(edges) < MIN_RISES:
            errors.append(f"DIO{channel}: {len(edges)} rising edges; need {MIN_RISES}")
        if len(edges) >= 2:
            intervals = [(b - a) * 1000 / rate for a, b in zip(edges, edges[1:])]
            mean = sum(intervals) / len(intervals)
            expected = report["expected_period_ms"]
            relative_error = (mean - expected) / expected
            report.update(mean_period_ms=mean, min_period_ms=min(intervals),
                          max_period_ms=max(intervals), period_error_pct=100 * relative_error)
            if abs(relative_error) > PERIOD_TOLERANCE:
                errors.append(f"Mean {mean:.4f} ms outside {expected} ms ±1%")

    # Export unexpected moving lines too, so a crosstalk/wiring failure is inspectable.
    relevant = sorted(set(moving) | ({expected_dio} if expected_dio is not None else set()))
    return relevant


async def measure(command, pin, period_ms, data, expected_dio=None):
    await send_command(command, data)
    report = {"command": command, "pin": pin, "expected_period_ms": period_ms,
              "expected_dio": expected_dio, "raw_csv_paths": [], "errors": []}
    data["captures"].append(report)
    capture = la_start_timed_capture(duration_seconds=DURATION_S,
                                     enabled_digital_channels=list(DIO),
                                     digital_sample_rate=SAMPLE_RATE, device_id=AD3_ID)
    try:
        la_wait(capture)
        relevant = analyze(capture, report, expected_dio, data["mapping"].values())
        if relevant and report["sample_count"]:
            directory = Path(la_export_raw(capture, digital_channels=relevant,
                                           directory_name=f"ra8p1_{command}_{pin}"))
            # WaveForms runner versions emit either digital.csv or digital_<n>.csv.
            report["raw_csv_paths"] = sorted(str(path) for path in directory.glob("digital*.csv"))
            if not report["raw_csv_paths"]:
                report["errors"].append(f"Analyzer exported no CSV in {directory}")
            analysis_path = directory / "analysis.json"
            report["analysis_path"] = str(analysis_path)
            analysis_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if report["errors"]:
            raise RuntimeError(f"{pin} ({command}): " + "; ".join(report["errors"]))
        return report["dio"]
    finally:
        la_stop(capture)


async def run(profile, data):
    action = profile.get("action", "mapping")
    data["action"] = action
    if action == "timing":
        period_ms = profile.get("expected_period_ms", 20)
        expected_dio = profile.get("expected_dio")
        if period_ms not in (20, 40) or type(expected_dio) is not int or expected_dio not in DIO:
            raise ValueError("Timing needs expected_period_ms 20 or 40 and mapped expected_dio 0–15")
    elif action not in ("mapping", "startup"):
        raise ValueError("Action must be 'mapping', 'timing' or 'startup'")
    if not any(device.get("device_id") == AD3_ID for device in la_get_devices()):
        raise RuntimeError(f"Select the Digilent WaveForms backend with AD3 {AD3_ID}")

    if action == "mapping":
        await send_command("idle", data)
        for command, pin in PINS.items():
            data["mapping"][pin] = await measure(command, pin, 20, data)
        summary = "Four distinct DIO mappings passed at 20 ms ±1%"
    elif action == "startup":
        try:
            await measure("m0", PINS["m0"], 20, data, 0)
        finally:
            await send_command("idle", data)
        mean = data["captures"][-1]["mean_period_ms"]
        return f"Unchanged startup clock: P514/DIO0 {mean:.4f} ms (expected 20 ms ±1%)"
    else:
        await send_command("m0", data)
        await measure("c1" if period_ms == 40 else "c0", PINS["m0"], period_ms, data, expected_dio)
        mean = data["captures"][-1]["mean_period_ms"]
        summary = f"P514/DIO{expected_dio}: {mean:.4f} ms (expected {period_ms} ms ±1%)"
    await send_command("idle", data)
    return summary


def main():
    data = {"device_id": AD3_ID, "uart_port": UART_PORT, "uart_baud": BAUD,
            "requested_sample_rate_sps": SAMPLE_RATE, "requested_duration_s": DURATION_S,
            "uart": [], "captures": [], "mapping": {}}
    try:
        summary = asyncio.run(run(globals().get("capture_profile", {}), data))
    except Exception as exc:
        # Assert failures even when an injected helper is missing or raises.
        print(json.dumps({"success": False, "summary": f"{type(exc).__name__}: {exc}", "data": data}))
    else:
        print(json.dumps({"success": True, "summary": summary, "data": data}))


if __name__ == "__main__":
    main()
