import unittest
from datetime import datetime, timedelta, timezone

from agentack import Action
from agentack.engine import evaluate_events
from agentack.models import TraceEvent

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def event(event_type: str, offset: int, **kwargs) -> TraceEvent:  # type: ignore[no-untyped-def]
    return TraceEvent(event_type, BASE + timedelta(seconds=offset), "s", **kwargs)  # type: ignore[arg-type]


class BlockLifecycleTests(unittest.TestCase):
    def test_policy_covered_block_without_approval_is_incomplete(self):
        action = Action("shell", "run")
        report = evaluate_events([
            event("action_proposed", 0, action_id="a1", action=action),
            event("action_blocked", 1, action_id="a1", reason="blocked"),
            event("session_end", 2),
        ])
        self.assertEqual(report.status, "INCOMPLETE")
        self.assertIn("ACK009", report.rule_counts)

    def test_policy_covered_block_must_link_approval(self):
        action = Action("shell", "run")
        report = evaluate_events([
            event("action_proposed", 0, action_id="a1", action=action),
            event("approval_requested", 1, action_id="a1", approval_id="p1", action=action),
            event("approval_decision", 2, action_id="a1", approval_id="p1", decision="deny"),
            event("action_blocked", 3, action_id="a1", reason="human denied"),
            event("session_end", 4),
        ])
        self.assertEqual(report.status, "INCOMPLETE")
        self.assertIn("ACK009", report.rule_counts)


if __name__ == "__main__":
    unittest.main()
