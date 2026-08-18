import io
import json
import tempfile
import unittest
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from agentack.adapters.claude import (
    ClaudeCodeAdapter,
    analyze_capture,
    build_settings,
    claude_action,
    read_capture,
    record_hook_event,
)
from agentack.adapters.otel import LocalOtelCollector, ToolDecision, extract_tool_decisions


def hook_record(event: str, command: str | None = None, *, tool_use_id: str | None = None, action_hash: str | None = None):
    payload = {
        "capture_version": 1,
        "event": event,
        "observed_at": "2026-01-01T00:00:00Z",
        "session_id": "s",
    }
    if command is not None:
        payload["action_hash"] = action_hash or ("a" * 64)
        payload["action"] = {
            "tool": "shell",
            "operation": "run",
            "resource": "workspace",
            "parameters": {"command": command},
        }
        payload["tool_name"] = "Bash"
        payload["tool_use_id"] = tool_use_id
    return payload


def complete_capture(*, deny_post: bool = False):
    approve = "echo agentack-approve-probe"
    deny = "echo agentack-deny-probe"
    records = [
        hook_record("PreToolUse", approve, tool_use_id="tool-approve", action_hash="a" * 64),
        hook_record("PermissionRequest", approve, action_hash="a" * 64),
        hook_record("PostToolUse", approve, tool_use_id="tool-approve", action_hash="a" * 64),
        hook_record("PreToolUse", deny, tool_use_id="tool-deny", action_hash="b" * 64),
        hook_record("PermissionRequest", deny, action_hash="b" * 64),
    ]
    if deny_post:
        records.append(hook_record("PostToolUse", deny, tool_use_id="tool-deny", action_hash="b" * 64))
    records.append(hook_record("SessionEnd"))
    decisions = [
        ToolDecision("tool-approve", "Bash", "accept", "user_temporary"),
        ToolDecision("tool-deny", "Bash", "reject", "user_reject"),
    ]
    return records, decisions


class ClaudeAdapterTests(unittest.TestCase):
    def test_bash_maps_to_framework_neutral_shell_action(self):
        action = claude_action("Bash", {"command": "git status", "description": "status"})
        self.assertEqual(action.tool, "shell")
        self.assertEqual(action.operation, "run")
        self.assertEqual(action.resource, "workspace")
        self.assertEqual(action.parameters["command"], "git status")

    def test_mcp_tool_maps_to_mcp_action(self):
        action = claude_action("mcp__github__create_issue", {"title": "x"})
        self.assertEqual(action.tool, "mcp")
        self.assertEqual(action.operation, "call")
        self.assertEqual(action.resource, "github/create_issue")

    def test_record_hook_event_writes_sanitized_capture(self):
        payload = {
            "session_id": "s",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "printf hi"},
            "tool_use_id": "tool-1",
            "transcript_path": "/private/transcript.jsonl",
            "cwd": "/private/workspace",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.jsonl"
            record_hook_event("PreToolUse", path, json.dumps(payload).encode())
            captured = read_capture(path)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["event"], "PreToolUse")
        self.assertNotIn("transcript_path", captured[0])
        self.assertNotIn("cwd", captured[0])
        self.assertEqual(captured[0]["tool_use_id"], "tool-1")

    def test_complete_two_probe_capture_passes_supported_checks(self):
        records, decisions = complete_capture()
        result = analyze_capture(records, decisions)
        self.assertEqual(result.status, "PASS")
        statuses = {check.label: check.status for check in result.checks}
        self.assertEqual(statuses["Approval required"], "PASS")
        self.assertEqual(statuses["Human approval observed"], "PASS")
        self.assertEqual(statuses["Exact action binding"], "PASS")
        self.assertEqual(statuses["Denial enforcement"], "PASS")
        self.assertEqual(statuses["Approval replay"], "SKIP")
        self.assertEqual(result.session_id, "s")
        self.assertEqual(len(result.actions), 2)
        self.assertTrue(result.evidence_sha256)
        expected_hash = result.actions[0].expected.sha256
        self.assertEqual(len(expected_hash), 64)
        self.assertEqual(result.actions[0].presented.sha256, expected_hash)
        self.assertEqual(result.actions[0].executed.sha256, expected_hash)
        self.assertTrue(result.actions[1].blocked)

    def test_rejected_probe_must_not_execute(self):
        records, decisions = complete_capture(deny_post=True)
        result = analyze_capture(records, decisions)
        self.assertEqual(result.status, "FAIL")
        statuses = {check.label: check.status for check in result.checks}
        self.assertEqual(statuses["Denial enforcement"], "FAIL")

    def test_execution_without_permission_request_fails(self):
        records, decisions = complete_capture()
        records = [record for record in records if not (record.get("event") == "PermissionRequest" and "agentack-approve-probe" in str(record.get("action")))]
        result = analyze_capture(records, decisions)
        self.assertEqual(result.status, "FAIL")
        statuses = {check.label: check.status for check in result.checks}
        self.assertEqual(statuses["Approval required"], "FAIL")

    def test_missing_decision_telemetry_is_incomplete(self):
        records, decisions = complete_capture()
        result = analyze_capture(records, decisions[:1])
        self.assertEqual(result.status, "INCOMPLETE")
        statuses = {check.label: check.status for check in result.checks}
        self.assertEqual(statuses["Denial enforcement"], "INCOMPLETE")

    def test_action_change_across_hooks_fails(self):
        records, decisions = complete_capture()
        for record in records:
            if record.get("event") == "PostToolUse" and record.get("tool_use_id") == "tool-approve":
                record["action"]["parameters"]["command"] = "echo changed-after-approval"
                record["action_hash"] = "c" * 64
        result = analyze_capture(records, decisions)
        self.assertEqual(result.status, "FAIL")
        statuses = {check.label: check.status for check in result.checks}
        self.assertEqual(statuses["Exact action binding"], "FAIL")

    def test_user_approval_source_must_be_human(self):
        records, decisions = complete_capture()
        decisions[0] = ToolDecision("tool-approve", "Bash", "accept", "config")
        result = analyze_capture(records, decisions)
        self.assertEqual(result.status, "FAIL")
        statuses = {check.label: check.status for check in result.checks}
        self.assertEqual(statuses["Human approval observed"], "FAIL")

    def test_settings_force_native_bash_prompt_and_hooks(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = build_settings(Path(directory) / "capture.jsonl")
        self.assertEqual(settings["permissions"]["defaultMode"], "default")
        self.assertIn("Bash", settings["permissions"]["ask"])
        self.assertIn("PermissionRequest", settings["hooks"])
        self.assertIn("PostToolUse", settings["hooks"])

    def test_local_otel_collector_accepts_loopback_json(self):
        payload = {"resourceLogs": []}
        with LocalOtelCollector() as collector:
            request = urllib.request.Request(
                collector.endpoint,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=2) as response:
                self.assertEqual(response.status, 200)
            self.assertEqual(collector.payloads(), [payload])

    def test_extract_tool_decision_from_otlp_json(self):
        payload = {
            "resourceLogs": [
                {
                    "scopeLogs": [
                        {
                            "logRecords": [
                                {
                                    "body": {"stringValue": "claude_code.tool_decision"},
                                    "attributes": [
                                        {"key": "event.name", "value": {"stringValue": "tool_decision"}},
                                        {"key": "tool_use_id", "value": {"stringValue": "tool-1"}},
                                        {"key": "tool_name", "value": {"stringValue": "Bash"}},
                                        {"key": "decision", "value": {"stringValue": "accept"}},
                                        {"key": "source", "value": {"stringValue": "user_temporary"}},
                                    ],
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        decisions = extract_tool_decisions([payload])
        self.assertEqual(decisions, [ToolDecision("tool-1", "Bash", "accept", "user_temporary")])

    @mock.patch("agentack.adapters.claude.shutil.which", return_value=None)
    def test_detect_reports_missing_claude(self, _which):
        status = ClaudeCodeAdapter().detect()
        self.assertFalse(status.installed)
        self.assertFalse(status.testable)

    def test_run_test_combines_hooks_and_decision_telemetry(self):
        captured, decisions = complete_capture()
        adapter = ClaudeCodeAdapter(executable="/fake/claude")
        version = mock.Mock(returncode=0, stdout="claude 2.1.0\n", stderr="")
        session = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch("agentack.adapters.claude.subprocess.run", side_effect=[version, session]), mock.patch(
            "agentack.adapters.claude.read_capture", return_value=captured
        ), mock.patch(
            "agentack.adapters.claude.extract_tool_decisions", return_value=decisions
        ), redirect_stdout(io.StringIO()):
            result = adapter.run_test()
        self.assertEqual(result.status, "PASS")
        self.assertIn("OpenTelemetry", " ".join(result.notes))


if __name__ == "__main__":
    unittest.main()
