import unittest

from agentack.demo import SCENARIOS, demo_events
from agentack.engine import evaluate_events


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

    def test_denied_intent_can_execute_after_fresh_exact_reapproval(self):
        from agentack import Action, action_hash
        from agentack.models import TraceEvent
        from datetime import datetime, timedelta, timezone

        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        first = Action("filesystem", "delete", resource="synthetic/a.txt")
        second = Action("mcp", "call", resource="synthetic-files", parameters={"method": "delete", "path": "a.txt"})
        events = [
            TraceEvent("action_proposed", base, "s", action_id="a1", intent_id="i", action=first),
            TraceEvent("approval_decision", base + timedelta(seconds=1), "s", action_id="a1", intent_id="i", approval_id="p1", decision="deny"),
            TraceEvent("action_proposed", base + timedelta(seconds=2), "s", action_id="a2", intent_id="i", action=second),
            TraceEvent("approval_decision", base + timedelta(seconds=3), "s", action_id="a2", intent_id="i", approval_id="p2", decision="allow", approved_action_hash=action_hash(second)),
            TraceEvent("action_executed", base + timedelta(seconds=4), "s", action_id="a2", intent_id="i", approval_id="p2", action=second),
        ]
        report = evaluate_events(events)
        self.assertEqual(report.status, "PASS")


if __name__ == "__main__":
    unittest.main()
