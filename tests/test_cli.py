import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agentack.demo import demo_events
from agentack.parser import write_jsonl


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "agentack", *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_secure_demo_exit_zero(self):
        result = self.run_cli("demo", "secure")
        self.assertEqual(result.returncode, 0)
        self.assertIn("PASS", result.stdout)

    def test_vulnerable_demo_exit_one(self):
        result = self.run_cli("demo", "action-swap")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ACK003", result.stdout)

    def test_incomplete_trace_exit_three(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "trace.jsonl"
            events = demo_events("secure")[:-1]
            write_jsonl(trace, events)
            result = self.run_cli("check", str(trace))
        self.assertEqual(result.returncode, 3)
        self.assertIn("INCOMPLETE", result.stdout)

    def test_default_demo_showcases_secure_and_broken_flow(self):
        result = self.run_cli("demo")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Secure approval flow", result.stdout)
        self.assertIn("DETECTED (ACK003)", result.stdout)
        self.assertIn("agentack doctor", result.stdout)

    def test_doctor_is_safe_without_live_adapter(self):
        result = self.run_cli("doctor")
        self.assertEqual(result.returncode, 0)
        self.assertIn("AgentAck doctor", result.stdout)

    def test_explain_includes_actionable_next_step(self):
        result = self.run_cli("explain", "ACK003")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Why:", result.stdout)
        self.assertIn("Next:", result.stdout)

    def test_internal_hook_error_does_not_use_claude_block_exit_code(self):
        result = subprocess.run(
            [sys.executable, "-m", "agentack", "_hook", "claude", "--event", "PreToolUse", "--capture", "ignored.jsonl"],
            input="not-json",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertNotEqual(result.returncode, 2)

    def test_json_and_sarif_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "trace.jsonl"
            report = Path(directory) / "report.json"
            sarif = Path(directory) / "report.sarif"
            generate = self.run_cli("demo", "secure", "--write", str(trace))
            self.assertEqual(generate.returncode, 0)
            result = self.run_cli("check", str(trace), "--json", str(report), "--sarif", str(sarif))
            self.assertEqual(result.returncode, 0)
            self.assertTrue(report.exists())
            self.assertTrue(sarif.exists())


if __name__ == "__main__":
    unittest.main()
