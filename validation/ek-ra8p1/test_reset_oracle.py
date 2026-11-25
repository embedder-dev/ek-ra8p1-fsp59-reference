"""Host-only tests for the EK-RA8P1 reset transcript gate."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from reset_oracle import check_transcript


TAG = "r020 CPU0 Nov 24 2026 16:17:52"
HEALTHY = (
    f"BOOT EK-RA8P1 {TAG}\n"
    "CLOCK SCKSCR=03 SCKDIVCR=00001110 SCKDIVCR2=00000000 OSCSF=28 SCICKCR=03 "
    "SCI8_CCR2=80000c10 SCI8_CCR3=00009200\n"
    "GPT0 GTCR=00000001 GTPR=239999 CPU1ACTCSR=0000\n"
    "READY\n"
)
WDT = "WDT BOOT RSTSR1=00000004 WDT0RF=0\n"


class ResetOracleTests(unittest.TestCase):
    def check(self, transcript=HEALTHY, *, cpu1="inactive"):
        return check_transcript(transcript, build_tag=TAG, cpu1=cpu1)

    def test_healthy_transcript_and_snapshot(self):
        result = self.check()
        self.assertTrue(result["success"], result["errors"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["records"], ["BOOT", "CLOCK", "GPT0", "READY"])
        self.assertEqual(result["observed"]["build_tag"], TAG)
        self.assertEqual(result["observed"]["GTPR"], 239999)
        self.assertEqual(result["observed"]["OSCSF"], "28")
        self.assertEqual(result["observed"]["MOSCSF"], 1)

    def test_wdt_diagnostic_and_crlf(self):
        transcript = HEALTHY.replace("READY\n", WDT + "READY\n").replace("\n", "\r\n")
        result = self.check(transcript)
        self.assertTrue(result["success"], result["errors"])
        self.assertEqual(result["records"], ["BOOT", "CLOCK", "GPT0", "WDT", "READY"])
        self.assertEqual(result["observed"]["RSTSR1"], "00000004")

    def test_single_digit_gcc_date_and_ready_without_line_ending(self):
        tag = TAG.replace("Nov 24", "Nov  4")
        result = check_transcript(HEALTHY.replace(TAG, tag).removesuffix("\n"), build_tag=tag, cpu1="inactive")
        self.assertTrue(result["success"], result["errors"])

    def test_reported_pdm_divider_fails_despite_other_matching_fields(self):
        result = self.check(HEALTHY.replace("SCKDIVCR=00001110", "SCKDIVCR=10000000").replace("OSCSF=28", "OSCSF=08"))
        self.assertFalse(result["success"])
        self.assertEqual(result["expected"]["SCKDIVCR"], "00001110")
        self.assertEqual(result["observed"]["SCKDIVCR"], "10000000")
        self.assertEqual(result["errors"], ["SCKDIVCR: expected '00001110', observed '10000000'"])

    def test_other_value_mismatches(self):
        for good, bad, field in (
            ("SCKSCR=03", "SCKSCR=02", "SCKSCR"),
            ("SCKDIVCR2=00000000", "SCKDIVCR2=10000000", "SCKDIVCR2"),
            ("OSCSF=28", "OSCSF=20", "MOSCSF"),
            ("GTCR=00000001", "GTCR=00000002", "CST"),
            ("GTPR=239999", "GTPR=239998", "GTPR"),
            (TAG, TAG.replace("16:17:52", "16:17:53"), "build_tag"),
        ):
            with self.subTest(field=field):
                result = self.check(HEALTHY.replace(good, bad))
                self.assertFalse(result["success"])
                self.assertTrue(any(error.startswith(f"{field}: expected") for error in result["errors"]))

    def test_cpu1_modes_check_only_the_act_bit(self):
        for register, state, act in (("0081", "active", 1), ("0001", "inactive", 0)):
            with self.subTest(register=register):
                transcript = HEALTHY.replace("CPU1ACTCSR=0000", f"CPU1ACTCSR={register}")
                result = self.check(transcript, cpu1=state)
                self.assertTrue(result["success"], result["errors"])
                self.assertEqual(result["observed"]["ACT"], act)
                wrong = self.check(transcript, cpu1="inactive" if act else "active")
                self.assertFalse(wrong["success"])
                self.assertEqual(wrong["errors"], [f"ACT: expected {1 - act}, observed {act}"])

    def test_missing_and_duplicate_required_records(self):
        for line in HEALTHY.splitlines(keepends=True):
            kind = line.split()[0]
            with self.subTest(kind=kind):
                missing = self.check(HEALTHY.replace(line, ""))
                self.assertFalse(missing["success"])
                self.assertIn(f"missing {kind} record", missing["errors"])
                duplicate = self.check(HEALTHY.replace(line, line * 2))
                self.assertFalse(duplicate["success"])
                self.assertTrue(any(f"duplicate {kind} record" in error for error in duplicate["errors"]))

    def test_out_of_order_records(self):
        boot, clock, gpt, ready = HEALTHY.splitlines(keepends=True)
        for lines in ((boot, gpt, clock, ready), (boot, clock, gpt, ready, WDT)):
            with self.subTest(lines=lines):
                result = self.check("".join(lines))
                self.assertFalse(result["success"])
                self.assertTrue(any("out of order" in error for error in result["errors"]))

    def test_corrupt_framing_is_not_ignored(self):
        for transcript in (
            HEALTHY.replace(TAG, "r020 CPU0"),
            HEALTHY.replace("CLOCK ", "\ufffdCLOCK "),
            HEALTHY.replace("SCI8_CCR2=80000c10", "SCI8_CCR2=80000z10"),
            HEALTHY.replace("GTPR=239999", "GTPR=239999x"),
            HEALTHY.replace("READY\n", "READY\x00\n"),
            HEALTHY.replace("READY\n", "RE\rADY\n"),
            HEALTHY.replace("\nCLOCK", "\vCLOCK"),
            HEALTHY + "RE\n",
        ):
            with self.subTest(transcript=transcript):
                result = self.check(transcript)
                self.assertFalse(result["success"])
                self.assertTrue(any("garbled" in error for error in result["errors"]))

    def test_cli_file_and_stdin_status_and_json(self):
        script = Path(__file__).with_name("reset_oracle.py")
        cmd = [sys.executable, str(script), "--build-tag", TAG, "--cpu1", "inactive"]
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "boot.log"
            capture.write_bytes(HEALTHY.replace("\n", "\r\n").encode("ascii"))
            passing = subprocess.run([*cmd, str(capture)], capture_output=True, check=False)
        self.assertEqual(passing.returncode, 0, passing.stderr)
        self.assertTrue(json.loads(passing.stdout)["success"])
        payload = HEALTHY.encode("ascii").replace(b"CLOCK", b"\xffCLOCK")
        failing = subprocess.run([*cmd, "-"], input=payload, capture_output=True, check=False)
        self.assertEqual(failing.returncode, 1, failing.stderr)
        snapshot = json.loads(failing.stdout)
        self.assertFalse(snapshot["success"])
        self.assertIn("missing CLOCK record", snapshot["errors"])


if __name__ == "__main__":
    unittest.main()
