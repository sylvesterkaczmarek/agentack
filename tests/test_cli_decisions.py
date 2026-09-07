import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def decision_trace(decision):
    action = {"tool": "filesystem", "operation": "read", "resource": "synthetic.txt", "parameters": {}}
    records = [
        {"type": "action_proposed", "action_id": "a1", "action": action},
        {"type": "approval_requested", "action_id": "a1", "approval_id": "p1", "action": action},
        {"type": "approval_decision", "action_id": "a1", "approval_id": "p1", "decision": decision},
        {"type": "action_executed", "action_id": "a1", "action": action},
        {"type": "session_end"},
    ]
    return "".join(
        json.dumps({
            "schema_version": 2,
            "session_id": "decision-session",
            "timestamp": f"2026-01-01T00:00:0{index}Z",
            **record,
        }) + "\n"
        for index, record in enumerate(records)
    )


class DecisionCliTests(unittest.TestCase):
    def test_omitted_approval_link_is_reported_in_cli_json_and_sarif(self):
        for decision, status, exit_code, rule_id in [
            ("deny", "FAIL", 1, "ACK002"),
            ("allow", "INCOMPLETE", 3, "ACK009"),
        ]:
            with self.subTest(decision=decision), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                trace = root / "trace.jsonl"
                report_path = root / "report.json"
                sarif_path = root / "report.sarif"
                trace.write_text(decision_trace(decision), encoding="utf-8", newline="\n")
                result = subprocess.run(
                    [sys.executable, "-m", "agentack", "check", str(trace),
                     "--json", str(report_path), "--sarif", str(sarif_path)],
                    text=True, capture_output=True, check=False,
                )
                self.assertEqual(result.returncode, exit_code, result.stdout + result.stderr)
                self.assertIn(status, result.stdout)
                self.assertIn(rule_id, result.stdout)
                report = json.loads(report_path.read_text(encoding="utf-8"))
                self.assertEqual(report["result"]["status"], status)
                self.assertEqual(report["input"]["trace"]["sha256"], hashlib.sha256(trace.read_bytes()).hexdigest())
                finding = next(item for item in report["result"]["findings"] if item["rule_id"] == rule_id)
                self.assertEqual(finding["line"], 4)
                self.assertEqual(finding["action_id"], "a1")
                self.assertIsNone(finding["approval_id"])
                sarif = json.loads(sarif_path.read_text(encoding="utf-8"))["runs"][0]
                self.assertEqual(sarif["properties"]["status"], status)
                sarif_finding = next(item for item in sarif["results"] if item["ruleId"] == rule_id)
                location = sarif_finding["locations"][0]["physicalLocation"]
                self.assertEqual(location["artifactLocation"]["uri"], "trace.jsonl")
                self.assertEqual(location["region"]["startLine"], 4)


if __name__ == "__main__":
    unittest.main()
