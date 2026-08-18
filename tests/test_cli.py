import json
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
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["report_schema_version"], 1)
            self.assertEqual(payload["producer"]["name"], "AgentAck")
            self.assertEqual(payload["run"]["kind"], "trace")
            self.assertEqual(payload["input"]["trace"]["source"], "trace.jsonl")
            self.assertTrue(payload["input"]["trace"]["sha256"])
            self.assertTrue(payload["input"]["policy"]["sha256"])
            self.assertTrue(payload["actions"])
            sarif_payload = json.loads(sarif.read_text(encoding="utf-8"))
            self.assertEqual(sarif_payload["runs"][0]["tool"]["driver"]["name"], "AgentAck")
            self.assertTrue(sarif_payload["runs"][0]["tool"]["driver"]["version"])

    def test_unreadable_or_missing_trace_returns_input_error_without_traceback(self):
        result = self.run_cli("check", "/definitely/missing/trace.jsonl")
        self.assertEqual(result.returncode, 2)
        self.assertIn("input error", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_invalid_policy_returns_input_error_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "trace.jsonl"
            policy = Path(directory) / "policy.toml"
            write_jsonl(trace, demo_events("secure"))
            policy.write_text("not valid = [", encoding="utf-8")
            result = self.run_cli("check", str(trace), "--policy", str(policy))
        self.assertEqual(result.returncode, 2)
        self.assertIn("input error", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_json_and_sarif_cannot_overwrite_the_same_path(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            result = self.run_cli("demo", "secure", "--json", str(output), "--sarif", str(output))
        self.assertEqual(result.returncode, 2)
        self.assertIn("must use different paths", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_report_write_error_returns_two_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "trace.jsonl"
            blocker = Path(directory) / "not-a-directory"
            blocker.write_text("x", encoding="utf-8")
            write_jsonl(trace, demo_events("secure"))
            result = self.run_cli("check", str(trace), "--json", str(blocker / "report.json"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("output error", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_demo_trace_write_error_returns_two_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory) / "not-a-directory"
            blocker.write_text("x", encoding="utf-8")
            result = self.run_cli("demo", "secure", "--write", str(blocker / "trace.jsonl"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("input/output error", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_init_write_error_returns_two_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory) / "not-a-directory"
            blocker.write_text("x", encoding="utf-8")
            result = self.run_cli("init", str(blocker / "agentack.toml"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("output error", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
