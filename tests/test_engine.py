import unittest
from datetime import datetime, timedelta, timezone

from agentack import Action
from agentack.demo import SCENARIOS, demo_events
from agentack.engine import evaluate_events
from agentack.models import TraceEvent

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def event(event_type: str, offset: int, **kwargs) -> TraceEvent:  # type: ignore[no-untyped-def]
    return TraceEvent(event_type, BASE + timedelta(seconds=offset), "s", **kwargs)  # type: ignore[arg-type]


class EngineTests(unittest.TestCase):
    def test_secure_scenario_passes(self):
        report = evaluate_events(demo_events("secure"))
        self.assertEqual(report.status, "PASS")
        self.assertEqual(report.findings, ())

    def test_each_vulnerable_demo_fails(self):
        for scenario in SCENARIOS:
            if scenario == "secure":
                continue
            with self.subTest(scenario=scenario):
                report = evaluate_events(demo_events(scenario))
                self.assertEqual(report.status, "FAIL")
                self.assertGreater(len(report.findings), 0)

    def test_action_swap_is_detected(self):
        report = evaluate_events(demo_events("action-swap"))
        self.assertIn("ACK003", report.rule_counts)

    def test_denial_bypass_is_detected(self):
        report = evaluate_events(demo_events("denial-bypass"))
        self.assertIn("ACK002", report.rule_counts)

    def test_replay_is_detected(self):
        report = evaluate_events(demo_events("replay"))
        self.assertIn("ACK004", report.rule_counts)

    def test_route_around_is_detected(self):
        report = evaluate_events(demo_events("route-around"))
        self.assertIn("ACK007", report.rule_counts)

    def test_interrupt_bypass_is_detected(self):
        report = evaluate_events(demo_events("interrupt-bypass"))
        self.assertIn("ACK008", report.rule_counts)

    def test_expired_approval_is_detected(self):
        report = evaluate_events(demo_events("expired"))
        self.assertIn("ACK005", report.rule_counts)

    def test_unapproved_action_is_detected(self):
        report = evaluate_events(demo_events("unapproved"))
        self.assertIn("ACK001", report.rule_counts)

    def test_missing_proposal_is_incomplete_not_pass(self):
        action = Action("shell", "run")
        events = [
            event("approval_requested", 0, action_id="a1", approval_id="p1", action=action),
            event("approval_decision", 1, action_id="a1", approval_id="p1", decision="allow"),
            event("action_executed", 2, action_id="a1", approval_id="p1", action=action),
            event("session_end", 3),
        ]
        report = evaluate_events(events)
        self.assertEqual(report.status, "INCOMPLETE")
        self.assertIn("ACK009", report.rule_counts)

    def test_missing_approval_request_is_incomplete_not_pass(self):
        action = Action("shell", "run")
        events = [
            event("action_proposed", 0, action_id="a1", action=action),
            event("approval_decision", 1, action_id="a1", approval_id="p1", decision="allow"),
            event("action_executed", 2, action_id="a1", approval_id="p1", action=action),
            event("session_end", 3),
        ]
        report = evaluate_events(events)
        self.assertEqual(report.status, "INCOMPLETE")
        self.assertIn("ACK009", report.rule_counts)

    def test_orphan_approval_is_incomplete(self):
        events = [
            event("approval_decision", 0, action_id="a1", approval_id="p1", decision="allow"),
            event("session_end", 1),
        ]
        report = evaluate_events(events)
        self.assertEqual(report.status, "INCOMPLETE")
        self.assertIn("ACK009", report.rule_counts)

    def test_missing_session_end_is_incomplete(self):
        action = Action("filesystem", "read")
        events = [
            event("action_proposed", 0, action_id="a1", action=action),
            event("action_executed", 1, action_id="a1", action=action),
        ]
        report = evaluate_events(events)
        self.assertEqual(report.status, "INCOMPLETE")
        self.assertIn("ACK009", report.rule_counts)

    def test_event_after_session_end_fails(self):
        action = Action("filesystem", "read")
        events = [
            event("session_end", 0),
            event("action_proposed", 1, action_id="a1", action=action),
            event("action_executed", 2, action_id="a1", action=action),
        ]
        report = evaluate_events(events)
        self.assertEqual(report.status, "FAIL")
        self.assertIn("ACK006", report.rule_counts)

    def test_presentation_change_before_decision_fails(self):
        proposed = Action("shell", "run", parameters={"argv": ["git", "status"]})
        presented = Action("shell", "run", parameters={"argv": ["git", "push"]})
        events = [
            event("action_proposed", 0, action_id="a1", action=proposed),
            event("approval_requested", 1, action_id="a1", approval_id="p1", action=presented),
            event("approval_decision", 2, action_id="a1", approval_id="p1", decision="allow"),
            event("action_executed", 3, action_id="a1", approval_id="p1", action=presented),
            event("session_end", 4),
        ]
        report = evaluate_events(events)
        self.assertEqual(report.status, "FAIL")
        self.assertIn("ACK003", report.rule_counts)

    def test_execution_change_after_approval_fails(self):
        presented = Action("shell", "run", parameters={"argv": ["git", "status"]})
        executed = Action("shell", "run", parameters={"argv": ["git", "push"]})
        events = [
            event("action_proposed", 0, action_id="a1", action=presented),
            event("approval_requested", 1, action_id="a1", approval_id="p1", action=presented),
            event("approval_decision", 2, action_id="a1", approval_id="p1", decision="allow"),
            event("action_executed", 3, action_id="a1", approval_id="p1", action=executed),
            event("session_end", 4),
        ]
        report = evaluate_events(events)
        self.assertEqual(report.status, "FAIL")
        self.assertIn("ACK003", report.rule_counts)

    def test_approval_applied_to_different_action_fails(self):
        first = Action("shell", "run", parameters={"argv": ["git", "status"]})
        second = Action("shell", "run", parameters={"argv": ["git", "push"]})
        events = [
            event("action_proposed", 0, action_id="a1", action=first),
            event("approval_requested", 1, action_id="a1", approval_id="p1", action=first),
            event("approval_decision", 2, action_id="a2", approval_id="p1", decision="allow"),
            event("action_proposed", 3, action_id="a2", action=second),
            event("action_executed", 4, action_id="a2", approval_id="p1", action=second),
            event("session_end", 5),
        ]
        report = evaluate_events(events)
        self.assertEqual(report.status, "FAIL")
        self.assertIn("ACK003", report.rule_counts)

    def test_decision_before_request_fails(self):
        action = Action("shell", "run")
        events = [
            event("action_proposed", 0, action_id="a1", action=action),
            event("approval_decision", 1, action_id="a1", approval_id="p1", decision="allow"),
            event("approval_requested", 2, action_id="a1", approval_id="p1", action=action),
            event("action_executed", 3, action_id="a1", approval_id="p1", action=action),
            event("session_end", 4),
        ]
        report = evaluate_events(events)
        self.assertEqual(report.status, "FAIL")
        self.assertIn("ACK006", report.rule_counts)

    def test_denied_and_blocked_action_is_complete(self):
        action = Action("filesystem", "delete", resource="x")
        events = [
            event("action_proposed", 0, action_id="a1", action=action),
            event("approval_requested", 1, action_id="a1", approval_id="p1", action=action),
            event("approval_decision", 2, action_id="a1", approval_id="p1", decision="deny"),
            event("action_blocked", 3, action_id="a1", approval_id="p1", reason="human denied"),
            event("session_end", 4),
        ]
        report = evaluate_events(events)
        self.assertEqual(report.status, "PASS")

    def test_execute_after_block_fails(self):
        action = Action("filesystem", "delete", resource="x")
        events = [
            event("action_proposed", 0, action_id="a1", action=action),
            event("approval_requested", 1, action_id="a1", approval_id="p1", action=action),
            event("approval_decision", 2, action_id="a1", approval_id="p1", decision="deny"),
            event("action_blocked", 3, action_id="a1", approval_id="p1"),
            event("action_executed", 4, action_id="a1", approval_id="p1", action=action),
            event("session_end", 5),
        ]
        report = evaluate_events(events)
        self.assertEqual(report.status, "FAIL")
        self.assertIn("ACK006", report.rule_counts)

    def test_denied_intent_can_execute_after_fresh_exact_reapproval(self):
        first = Action("filesystem", "delete", resource="synthetic/a.txt")
        second = Action("mcp", "call", resource="synthetic-files", parameters={"method": "delete", "path": "a.txt"})
        events = [
            event("action_proposed", 0, action_id="a1", intent_id="i", action=first),
            event("approval_requested", 1, action_id="a1", intent_id="i", approval_id="p1", action=first),
            event("approval_decision", 2, action_id="a1", intent_id="i", approval_id="p1", decision="deny"),
            event("action_blocked", 3, action_id="a1", intent_id="i", approval_id="p1"),
            event("action_proposed", 4, action_id="a2", intent_id="i", action=second),
            event("approval_requested", 5, action_id="a2", intent_id="i", approval_id="p2", action=second),
            event("approval_decision", 6, action_id="a2", intent_id="i", approval_id="p2", decision="allow"),
            event("action_executed", 7, action_id="a2", intent_id="i", approval_id="p2", action=second),
            event("session_end", 8),
        ]
        report = evaluate_events(events)
        self.assertEqual(report.status, "PASS")

    def test_alias_tool_cannot_bypass_required_approval(self):
        action = Action("Bash", "EXEC", parameters={"argv": ["git", "push"]})
        events = [
            event("action_proposed", 0, action_id="a1", action=action),
            event("action_executed", 1, action_id="a1", action=action),
            event("session_end", 2),
        ]
        report = evaluate_events(events)
        self.assertEqual(report.status, "FAIL")
        self.assertIn("ACK001", report.rule_counts)


if __name__ == "__main__":
    unittest.main()
