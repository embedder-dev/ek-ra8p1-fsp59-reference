import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / ".embedder/hardware/ra8p1_pdm_soak.py"
SPEC = importlib.util.spec_from_file_location("ra8p1_pdm_soak", SCRIPT)
soak = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(soak)

# UART examples from pdm-uart-1795567397441225000.json and cpu1-live-1795567336466162000.json.
PDM = ["PDM preflight PCLKB=24000000 MCSTP=0 P812=1b010c00 P502=1b010c02",
       "PDM capture samples=2048 complete=1 errors=0 overruns=0 flags=0x00000000 timeout=0",
       "PDM PCM min=-931 max=1062 mean=228 mean_abs=273 clips=0", "PDM PASS", "ACK pdm"]
CLOCKS = ["CLOCK SCKSCR=03 SCKDIVCR=00001110 SCKDIVCR2=00000000 OSCSF=28 SCICKCR=03 "
          "SCI8_CCR2=80000c10 SCI8_CCR3=00009200",
          "GPT0 GTCR=00000001 GTPR=239999 CPU1ACTCSR=0080", "ACK clocks"]


def uart_text(lines):
    return "".join(f"{line}\r\n" for line in lines)


def uart_lines(text):
    return [line.removesuffix("\r") for line in text.split("\n") if line]


class FakeSerial:
    def __init__(self, responses=None, before_send=None, stale_live_at=None):
        self.responses = responses or {}
        self.before_send = before_send
        self.stale_live_at = stale_live_at
        self.sent = []
        self.pending = []
        self.live = self.history = uart_text(PDM + CLOCKS)

    def send(self, port, command, baud_rate):
        assert port == soak.PORT and baud_rate == soak.BAUD
        assert not self.pending and not self.history and not self.live
        if self.before_send is not None:
            self.before_send()
        self.sent.append(command)
        lines = PDM if command == "pdm" else CLOCKS
        self.pending = list(self.responses.get(len(self.sent), [uart_text(lines)]))
        if len(self.sent) == self.stale_live_at:
            self.live = uart_text(lines)

    async def read(self, port, baud_rate, timeout_seconds, stop_string=None):
        assert port == soak.PORT and baud_rate == soak.BAUD
        if stop_string is not None:
            assert stop_string == f"ACK {self.sent[-1]}"
            marker = f"{stop_string}\r\n"
            while self.pending and marker not in self.live:
                part = self.pending.pop(0)
                self.live += part
                self.history += part
            if marker not in self.live:
                await asyncio.sleep(timeout_seconds)
        live, self.live = self.live, ""
        return uart_lines(live)

    def read_history(self, port, baud_rate, only_new):
        assert port == soak.PORT and baud_rate == soak.BAUD and only_new is True
        history, self.history = self.history, ""
        return uart_lines(history)


class SoakTests(unittest.TestCase):
    def run_soak(self, profile, fake=None, timeout=4.0):
        fake = fake or FakeSerial()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.multiple(soak, create=True, serial_send=fake.send, serial_read=fake.read,
                                serial_read_history=fake.read_history, ACK_TIMEOUT_S=timeout):
                result = asyncio.run(soak.run(profile, Path(tmp)))
            files = list(Path(tmp).glob("*.jsonl"))
            if not files:
                return result, []
            self.assertEqual([Path(result["data"]["transcript"])], files)
            records = [json.loads(line) for line in files[0].read_text().splitlines()]
        self.assertEqual(records[0]["type"], "start")
        self.assertEqual(records[-1], {"type": "summary", **result})
        return result, records[1:-1]

    def test_default_run_checks_each_50_capture_boundary(self):
        fake = FakeSerial()
        result, records = self.run_soak({}, fake)
        self.assertTrue(result["success"], result)
        self.assertEqual(fake.sent, ["clocks"] + (["pdm"] * 50 + ["clocks"]) * 6)
        self.assertEqual(result["data"]["captures_passed"], 300)
        self.assertEqual(result["data"]["chunks_passed"], 6)
        self.assertEqual(result["data"]["clock_checks_passed"], 7)
        self.assertEqual([r["capture_index"] for r in records if r["command"] == "clocks"], list(range(0, 301, 50)))
        self.assertEqual([r["capture_index"] for r in records if r["command"] == "pdm"], list(range(1, 301)))
        self.assertEqual(records[1]["lines"], PDM)
        self.assertEqual(records[1]["values"]["min"], -931)
        for record in records:
            self.assertTrue(record["success"])
            self.assertEqual(record["end_monotonic_ns"] - record["start_monotonic_ns"], record["elapsed_ns"])
        self.assertTrue(all(a["end_monotonic_ns"] <= b["start_monotonic_ns"] for a, b in zip(records, records[1:])))

    def test_partial_chunk_and_response_split_across_uart_reads(self):
        pdm = uart_text(PDM)
        fake = FakeSerial({1: [uart_text(CLOCKS[1:])], 2: [pdm[:100], pdm[100:-1], pdm[-1:]]})
        result, records = self.run_soak({"count": 51}, fake)
        self.assertTrue(result["success"], result)
        self.assertEqual(fake.sent, ["clocks"] + ["pdm"] * 50 + ["clocks", "pdm", "clocks"])
        self.assertEqual([r["capture_index"] for r in records if r["command"] == "clocks"], [0, 50, 51])
        self.assertEqual(records[1]["lines"], PDM)

    def test_missing_or_unterminated_ack_times_out_and_logs_partial_response(self):
        for partial in (uart_text(PDM[:-1]), uart_text(PDM)[:-2]):
            with self.subTest(partial=partial):
                fake = FakeSerial({2: [partial]})
                result, records = self.run_soak({"count": 2}, fake, timeout=0.03)
                self.assertFalse(result["success"])
                self.assertEqual(fake.sent, ["clocks", "pdm"])
                self.assertEqual(records[-1]["lines"], uart_lines(partial))
                self.assertIn("TimeoutError", records[-1]["error"])

    def test_stale_live_ack_is_not_counted_as_a_fresh_response(self):
        fake = FakeSerial(stale_live_at=2)
        result, records = self.run_soak({"count": 1}, fake)
        self.assertFalse(result["success"])
        self.assertEqual(fake.sent, ["clocks", "pdm"])
        self.assertEqual(records[-1]["lines"], [])
        self.assertIn("No fresh 'ACK pdm'", records[-1]["error"])

    def test_failed_or_corrupt_capture_stops_without_retry(self):
        failures = [PDM[:1] + ["PDM open err=1", "PDM FAIL"],
                    PDM[:4] + ["ACK clocks"], PDM + ["ACK pdm"],
                    PDM[:2] + PDM[3:], [PDM[1], PDM[0], *PDM[2:]],
                    [PDM[0].replace("MCSTP=0", "MCSTP=1"), *PDM[1:]]]
        for field in ("samples=2048", "complete=1", "errors=0", "overruns=0", "flags=0x00000000", "timeout=0"):
            bad = "1" if field.endswith("0") else "2"
            failures.append([PDM[0], PDM[1].replace(field, field[:-1] + bad), *PDM[2:]])
        for line in (PDM[2].replace("-931", "1062"), PDM[2].replace("1062", "524288"),
                     PDM[2].replace("mean_abs=273", "mean_abs=20"), PDM[2].replace("clips=0", "clips=1"),
                     PDM[2].replace("mean=228", "mean=\ufffd28"),
                     "PDM PCM min=-524288 max=524287 mean=0 mean_abs=524287 clips=2048",
                     "PDM PCM min=-524288 max=524287 mean=0 mean_abs=256 clips=1024"):
            failures.append([*PDM[:2], line, *PDM[3:]])
        for response in failures:
            with self.subTest(response=response):
                fake = FakeSerial({2: [uart_text(response)]})
                result, records = self.run_soak({"count": 2}, fake, timeout=0.03)
                self.assertFalse(result["success"])
                self.assertEqual(fake.sent, ["clocks", "pdm"])
                self.assertFalse(records[-1]["success"])
                self.assertEqual(records[-1]["lines"], response)

    def test_inactive_cpu1_at_initial_or_final_checkpoint_fails(self):
        inactive = [CLOCKS[0], CLOCKS[1].replace("0080", "0001"), CLOCKS[2]]
        for ordinal in (1, 3):
            with self.subTest(ordinal=ordinal):
                fake = FakeSerial({ordinal: [uart_text(inactive)]})
                result, records = self.run_soak({"count": 1}, fake)
                self.assertFalse(result["success"])
                self.assertEqual(fake.sent, ["clocks", "pdm", "clocks"][:ordinal])
                self.assertIn("CPU1 inactive", records[-1]["error"])
                self.assertEqual(result["data"]["chunks_passed"], 0)

    def test_profile_accepts_maximum_count(self):
        result, records = self.run_soak({"count": 5000})
        self.assertTrue(result["success"], result)
        self.assertEqual(result["data"]["captures_passed"], 5000)
        self.assertEqual(result["data"]["chunks_passed"], 100)
        self.assertEqual(len(records), 5101)

    def test_profile_rejects_invalid_counts_without_io(self):
        for value in (0, -1, 5001, "300", 2.0, True, None):
            with self.subTest(value=value):
                fake = FakeSerial()
                result, records = self.run_soak({"count": value}, fake)
                self.assertFalse(result["success"])
                self.assertFalse(fake.sent or records)

    def test_evidence_is_flushed_before_next_send_and_paths_are_unique(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for prior_runs in range(2):
                snapshots = []

                def before_send():
                    logs = list(directory.glob("*.jsonl"))
                    self.assertEqual(len(logs), prior_runs + 1)
                    current = next(path for path in logs if path not in past)
                    snapshots.append([json.loads(line)["type"] for line in current.read_text().splitlines()])

                past = set(directory.glob("*.jsonl"))
                fake = FakeSerial(before_send=before_send)
                with patch.multiple(soak, create=True, serial_send=fake.send, serial_read=fake.read,
                                    serial_read_history=fake.read_history), patch.object(soak.time, "time_ns", return_value=1):
                    result = asyncio.run(soak.run({"count": 1}, directory))
                self.assertTrue(result["success"], result)
                self.assertEqual(snapshots, [["start"], ["start", "response"], ["start", "response", "response"]])
            self.assertEqual(len(list(directory.glob("pdm-soak-1-*.jsonl"))), 2)


if __name__ == "__main__":
    unittest.main()
