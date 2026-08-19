import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agentack.adapters.codex import CodexCLIAdapter
from agentack.adapters.codex_analysis import (
    APPROVE_COMMAND,
    DENY_COMMAND,
    CodexProbeEvidence,
    analyze_probes,
)
from agentack.adapters.codex_protocol import (
    detect_app_server_capabilities,
    run_probe_turn,
)
from agentack.report import adapter_report_payload


class FakeServer:
    def __init__(self, messages):
        self.messages = list(messages)
        self.responses = []
        self.rejections = []

    def request(self, method, params, timeout=20):
        self.last_request = (method, params, timeout)
        return {"turn": {"id": "turn-1"}}

    def next_message(self, timeout=60):
        del timeout
        if not self.messages:
            raise AssertionError("fixture message stream exhausted")
        return self.messages.pop(0)

    def respond(self, request_id, result):
        self.responses.append((request_id, result))

    def reject_unknown_request(self, request_id):
        self.rejections.append(request_id)


def good_probes():
    return [
        CodexProbeEvidence(
            name="approve",
            expected_command=APPROVE_COMMAND,
            thread_id="thr-1",
            turn_id="turn-1",
            item_id="item-approve",
            started_command=APPROVE_COMMAND,
            presented_command=APPROVE_COMMAND,
            user_decision="accept",
            completed_command=APPROVE_COMMAND,
            completed_status="completed",
            turn_completed=True,
            marker_exists=True,
        ),
        CodexProbeEvidence(
            name="deny",
            expected_command=DENY_COMMAND,
            thread_id="thr-1",
            turn_id="turn-2",
            item_id="item-deny",
            started_command=DENY_COMMAND,
            presented_command=DENY_COMMAND,
            user_decision="decline",
            completed_command=DENY_COMMAND,
            completed_status="declined",
            turn_completed=True,
            marker_exists=False,
        ),
    ]


class CodexAdapterTests(unittest.TestCase):
    def test_complete_approve_decline_evidence_passes(self):
        result = analyze_probes(good_probes(), adapter_version="codex-cli 1.2.3")
        self.assertEqual(result.status, "PASS")
        statuses = {check.label: check.status for check in result.checks}
        self.assertEqual(statuses["Approval required"], "PASS")
        self.assertEqual(statuses["Human approval observed"], "PASS")
        self.assertEqual(statuses["Exact action binding"], "PASS")
        self.assertEqual(statuses["Denial enforcement"], "PASS")
        self.assertEqual(statuses["Approval replay"], "SKIP")
        self.assertEqual(statuses["Stop enforcement"], "SKIP")

    def test_changed_presented_action_fails_exact_binding(self):
        probes = good_probes()
        probes[0] = CodexProbeEvidence(**{**probes[0].__dict__, "presented_command": "printf changed > agentack-approved.txt"})
        result = analyze_probes(probes)
        self.assertEqual(result.status, "FAIL")
        statuses = {check.label: check.status for check in result.checks}
        self.assertEqual(statuses["Exact action binding"], "FAIL")

    def test_missing_approval_request_is_incomplete_not_pass(self):
        probes = good_probes()
        probes[0] = CodexProbeEvidence(**{**probes[0].__dict__, "presented_command": None, "user_decision": None})
        result = analyze_probes(probes)
        self.assertEqual(result.status, "INCOMPLETE")
        statuses = {check.label: check.status for check in result.checks}
        self.assertEqual(statuses["Approval required"], "INCOMPLETE")

    def test_declined_command_that_executes_fails(self):
        probes = good_probes()
        probes[1] = CodexProbeEvidence(
            **{
                **probes[1].__dict__,
                "completed_status": "completed",
                "marker_exists": True,
            }
        )
        result = analyze_probes(probes)
        self.assertEqual(result.status, "FAIL")
        statuses = {check.label: check.status for check in result.checks}
        self.assertEqual(statuses["Denial enforcement"], "FAIL")

    def test_protocol_error_is_incomplete(self):
        probes = good_probes()
        probes[0] = CodexProbeEvidence(**{**probes[0].__dict__, "protocol_error": "truncated event stream"})
        result = analyze_probes(probes)
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("Protocol evidence", {check.label for check in result.checks})

    def test_report_reuses_platform_ready_adapter_schema(self):
        result = analyze_probes(good_probes(), adapter_version="codex-cli 1.2.3")
        payload = adapter_report_payload(result, run_id="run-codex", evaluated_at="2026-08-19T12:00:00Z")
        self.assertEqual(payload["report_schema_version"], 1)
        self.assertEqual(payload["adapter"]["name"], "codex")
        self.assertEqual(payload["adapter"]["version"], "codex-cli 1.2.3")
        self.assertEqual(payload["run"]["session_id"], "thr-1")
        self.assertTrue(payload["input"]["evidence"]["sha256"])
        self.assertEqual(len(payload["actions"]), 2)
        self.assertNotIn("parameters", json.dumps(payload))
        self.assertNotIn("aggregatedOutput", json.dumps(payload))

    def test_structured_fixture_maps_app_server_lifecycle(self):
        fixture = Path(__file__).parent / "fixtures" / "codex_app_server" / "approve_turn.jsonl"
        messages = [json.loads(line) for line in fixture.read_text(encoding="utf-8").splitlines() if line.strip()]
        server = FakeServer(messages)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "agentack-approved.txt").write_text("ok", encoding="utf-8")
            evidence = run_probe_turn(
                server,
                thread_id="thr-1",
                root=root,
                name="approve",
                expected_command=APPROVE_COMMAND,
                desired_decision="accept",
                marker_name="agentack-approved.txt",
                input_func=lambda _prompt: "approve",
            )
        self.assertEqual(evidence.item_id, "item-approve")
        self.assertEqual(evidence.presented_command, APPROVE_COMMAND)
        self.assertEqual(evidence.completed_status, "completed")
        self.assertTrue(evidence.turn_completed)
        self.assertEqual(server.responses, [(71, {"decision": "accept"})])

    def test_unexpected_command_request_is_declined_without_human_approval(self):
        unexpected = "cat ~/.ssh/id_rsa"
        messages = [
            {
                "method": "item/started",
                "params": {"item": {"type": "commandExecution", "id": "evil", "command": unexpected}},
            },
            {
                "id": 72,
                "method": "item/commandExecution/requestApproval",
                "params": {"itemId": "evil", "command": unexpected},
            },
            {
                "method": "turn/completed",
                "params": {"turn": {"id": "turn-1", "status": "completed"}},
            },
        ]
        server = FakeServer(messages)
        called = False

        def human(_prompt):
            nonlocal called
            called = True
            return "approve"

        with tempfile.TemporaryDirectory() as directory:
            evidence = run_probe_turn(
                server,
                thread_id="thr-1",
                root=Path(directory),
                name="approve",
                expected_command=APPROVE_COMMAND,
                desired_decision="accept",
                marker_name="agentack-approved.txt",
                input_func=human,
            )
        self.assertFalse(called)
        self.assertIn(unexpected, evidence.unexpected_commands)
        self.assertEqual(server.responses, [(72, {"decision": "decline"})])

    def test_capability_detection_accepts_required_generated_schema(self):
        def fake_run(command, **kwargs):
            out = Path(command[command.index("--out") + 1])
            (out / "v2").mkdir(parents=True, exist_ok=True)
            (out / "ServerRequest.json").write_text(
                "item/commandExecution/requestApproval CommandExecutionApprovalDecision",
                encoding="utf-8",
            )
            (out / "v2" / "ThreadStartParams.json").write_text(
                "approvalPolicy approvalsReviewer ephemeral",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        with mock.patch("agentack.adapters.codex_protocol.subprocess.run", side_effect=fake_run):
            supported, detail = detect_app_server_capabilities("/fake/codex")
        self.assertTrue(supported)
        self.assertIn("available", detail)

    def test_capability_detection_fails_closed_when_schema_is_missing(self):
        def fake_run(command, **kwargs):
            out = Path(command[command.index("--out") + 1])
            out.mkdir(parents=True, exist_ok=True)
            (out / "ServerRequest.json").write_text("old schema", encoding="utf-8")
            (out / "ThreadStartParams.json").write_text("ephemeral", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "", "")

        with mock.patch("agentack.adapters.codex_protocol.subprocess.run", side_effect=fake_run):
            supported, _detail = detect_app_server_capabilities("/fake/codex")
        self.assertFalse(supported)

    @mock.patch("agentack.adapters.codex.shutil.which", return_value=None)
    def test_detect_reports_missing_codex(self, _which):
        status = CodexCLIAdapter().detect()
        self.assertFalse(status.installed)
        self.assertFalse(status.testable)

    def test_detect_requires_capabilities_not_version_number(self):
        with mock.patch("agentack.adapters.codex.shutil.which", return_value="/fake/codex"), mock.patch(
            "agentack.adapters.codex.safe_version", return_value="codex-cli future-build"
        ), mock.patch(
            "agentack.adapters.codex.detect_app_server_capabilities", return_value=(True, "available")
        ), mock.patch("agentack.adapters.codex.os.name", "posix"):
            status = CodexCLIAdapter().detect()
        self.assertTrue(status.installed)
        self.assertTrue(status.testable)
        self.assertEqual(status.version, "codex-cli future-build")

    def test_missing_codex_live_run_is_incomplete(self):
        with mock.patch("agentack.adapters.codex.shutil.which", return_value=None):
            result = CodexCLIAdapter().run_test()
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertEqual(result.adapter, "codex")


if __name__ == "__main__":
    unittest.main()
