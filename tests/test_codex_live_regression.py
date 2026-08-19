import unittest
from unittest import mock

from agentack.adapters.codex import _ProbePolicyServer, _RetryPromptServer, _retry_probe_turn
from agentack.adapters.codex_analysis import (
    APPROVE_COMMAND,
    DENY_COMMAND,
    ROUTE_B_COMMAND,
    STOP_COMMAND,
    CodexProbeEvidence,
    analyze_probes,
)


class RecordingServer:
    def __init__(self):
        self.requests = []

    def request(self, method, params, timeout=20):
        self.requests.append((method, params, timeout))
        return {"turn": {"id": "turn-1"}}

    def next_message(self, timeout=60):
        raise AssertionError(f"unexpected next_message({timeout})")

    def respond(self, request_id, result):
        raise AssertionError((request_id, result))

    def reject_unknown_request(self, request_id):
        raise AssertionError(request_id)


class CodexLiveRegressionTests(unittest.TestCase):
    def test_closed_turns_without_command_or_approval_evidence_are_incomplete(self):
        commands = {
            "approve": APPROVE_COMMAND,
            "replay": APPROVE_COMMAND,
            "route-a": DENY_COMMAND,
            "route-b": ROUTE_B_COMMAND,
            "stop": STOP_COMMAND,
        }
        probes = [
            CodexProbeEvidence(
                name=name,
                expected_command=command,
                thread_id="thr-1",
                turn_id=f"turn-{index}",
                turn_completed=True,
                turn_status="completed",
                marker_exists=False,
            )
            for index, (name, command) in enumerate(commands.items(), start=1)
        ]
        result = analyze_probes(probes, adapter_version="codex-cli 0.148.0")
        statuses = {check.label: check.status for check in result.checks}
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertEqual(statuses["Lifecycle ordering"], "INCOMPLETE")
        self.assertEqual(statuses["Evidence completeness"], "INCOMPLETE")
        self.assertNotEqual(statuses["Evidence completeness"], "PASS")

    def test_probe_retries_when_codex_closes_turn_without_command_item(self):
        first = CodexProbeEvidence(
            name="approve",
            expected_command=APPROVE_COMMAND,
            thread_id="thr-1",
            turn_id="turn-1",
            turn_completed=True,
            turn_status="completed",
            marker_exists=False,
        )
        second = CodexProbeEvidence(
            name="approve",
            expected_command=APPROVE_COMMAND,
            thread_id="thr-1",
            turn_id="turn-2",
            item_id="item-approve",
            started_command=APPROVE_COMMAND,
            presented_command=APPROVE_COMMAND,
            user_decision="accept",
            completed_command=APPROVE_COMMAND,
            completed_status="completed",
            turn_completed=True,
            turn_status="completed",
            marker_exists=True,
        )
        with mock.patch("agentack.adapters.codex.run_probe_turn", side_effect=[first, second]) as run:
            result = _retry_probe_turn(
                mock.MagicMock(),
                thread_id="thr-1",
                root=mock.MagicMock(),
                name="approve",
                expected_command=APPROVE_COMMAND,
                desired_decision="accept",
                marker_name="agentack-approved.txt",
                input_func=lambda _prompt: "approve",
                max_attempts=3,
            )
        self.assertEqual(run.call_count, 2)
        self.assertEqual(result.item_id, "item-approve")
        self.assertIsNone(result.protocol_error)

    def test_probe_stops_incomplete_after_bounded_no_command_retries(self):
        no_command = CodexProbeEvidence(
            name="approve",
            expected_command=APPROVE_COMMAND,
            thread_id="thr-1",
            turn_id="turn-1",
            turn_completed=True,
            turn_status="completed",
            marker_exists=False,
        )
        with mock.patch("agentack.adapters.codex.run_probe_turn", return_value=no_command) as run:
            result = _retry_probe_turn(
                mock.MagicMock(),
                thread_id="thr-1",
                root=mock.MagicMock(),
                name="approve",
                expected_command=APPROVE_COMMAND,
                desired_decision="accept",
                marker_name="agentack-approved.txt",
                input_func=lambda _prompt: "approve",
                max_attempts=3,
            )
        self.assertEqual(run.call_count, 3)
        self.assertIn("without emitting a commandExecution item", result.protocol_error or "")

    def test_retry_wrapper_strengthens_text_prompt(self):
        delegate = RecordingServer()
        wrapped = _RetryPromptServer(delegate, "MUST INVOKE SHELL")
        wrapped.request(
            "turn/start",
            {"threadId": "thr-1", "input": [{"type": "text", "text": "Run the probe"}]},
        )
        _method, params, _timeout = delegate.requests[-1]
        text = params["input"][0]["text"]
        self.assertIn("Run the probe", text)
        self.assertIn("MUST INVOKE SHELL", text)

    def test_probe_policy_pins_turn_cwd_to_disposable_root(self):
        delegate = RecordingServer()
        root = mock.MagicMock()
        root.resolve.return_value = "/private/tmp/agentack-root"
        wrapped = _ProbePolicyServer(delegate, root)
        wrapped.request("turn/start", {"threadId": "thr-1", "input": []})
        _method, params, _timeout = delegate.requests[-1]
        self.assertEqual(params["cwd"], "/private/tmp/agentack-root")
        self.assertEqual(params["approvalPolicy"], "untrusted")
        self.assertEqual(params["approvalsReviewer"], "user")


if __name__ == "__main__":
    unittest.main()
