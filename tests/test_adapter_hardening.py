import unittest

from agentack.adapters.claude import analyze_capture
from agentack.adapters.otel import LocalOtelCollector, ToolDecision
from agentack.canonical import action_hash
from agentack.models import Action


def hook_record(event, command=None, *, tool_use_id=None, helper_hash=None):
    record = {
        "capture_version": 1,
        "event": event,
        "observed_at": "2026-01-01T00:00:00Z",
        "session_id": "s",
    }
    if command is not None:
        action = Action("shell", "run", resource="workspace", parameters={"command": command})
        record.update({
            "action_hash": helper_hash or action_hash(action),
            "action": action.to_dict(),
            "tool_name": "Bash",
            "tool_use_id": tool_use_id,
        })
    return record


class AdapterHardeningTests(unittest.TestCase):
    def test_analysis_recomputes_action_identity_instead_of_trusting_helper_hash(self):
        approve = "echo agentack-approve-probe"
        deny = "echo agentack-deny-probe"
        records = [
            hook_record("PreToolUse", approve, tool_use_id="a", helper_hash="f" * 64),
            hook_record("PermissionRequest", approve, helper_hash="0" * 64),
            hook_record("PostToolUse", approve, tool_use_id="a", helper_hash="1" * 64),
            hook_record("PreToolUse", deny, tool_use_id="d"),
            hook_record("PermissionRequest", deny),
            hook_record("SessionEnd"),
        ]
        decisions = [
            ToolDecision("a", "Bash", "accept", "user_temporary"),
            ToolDecision("d", "Bash", "reject", "user_reject"),
        ]
        result = analyze_capture(records, decisions)
        statuses = {check.label: check.status for check in result.checks}
        self.assertEqual(statuses["Exact action binding"], "PASS")

    def test_local_otel_collector_uses_unpredictable_path(self):
        with LocalOtelCollector() as first, LocalOtelCollector() as second:
            self.assertNotEqual(first.endpoint, second.endpoint)
            self.assertTrue(first.endpoint.startswith("http://127.0.0.1:"))
            self.assertIn("/v1/logs", first.endpoint)


if __name__ == "__main__":
    unittest.main()
