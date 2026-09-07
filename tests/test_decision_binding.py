import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from agentack.engine import evaluate_events
from agentack.models import Action, TraceEvent
from agentack.policy import Policy

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
READ = Action("filesystem", "read", resource="notes.txt")


def event(kind: str, offset: int, **kwargs) -> TraceEvent:  # type: ignore[no-untyped-def]
    return TraceEvent(kind, BASE + timedelta(seconds=offset), "s", **kwargs)  # type: ignore[arg-type]


def proposal(action_id="a", offset=0, **kwargs):  # type: ignore[no-untyped-def]
    return event("action_proposed", offset, action_id=action_id, action=READ, **kwargs)


def request(approval_id="p", action_id="a", offset=1, **kwargs):  # type: ignore[no-untyped-def]
    return event("approval_requested", offset, action_id=action_id, approval_id=approval_id, action=READ, **kwargs)


def decision(value="deny", approval_id="p", action_id="a", offset=2, **kwargs):  # type: ignore[no-untyped-def]
    return event("approval_decision", offset, action_id=action_id, approval_id=approval_id, decision=value, **kwargs)


def execution(approval_id=None, action_id="a", offset=3, **kwargs):  # type: ignore[no-untyped-def]
    return event("action_executed", offset, action_id=action_id, approval_id=approval_id, action=READ, **kwargs)


def report(events, **kwargs):  # type: ignore[no-untyped-def]
    return evaluate_events([*events, event("session_end", 1000)], **kwargs)


class DecisionBindingTests(unittest.TestCase):
    def test_uncovered_action_without_approval_lifecycle_passes(self):
        self.assertEqual(report([proposal(), execution()]).status, "PASS")

    def test_denial_cannot_be_omitted_or_replaced_by_unknown_reference(self):
        for approval_id in (None, "unknown", "p"):
            with self.subTest(approval_id=approval_id):
                result = report([proposal(), request(), decision(), execution(approval_id)])
                self.assertEqual(result.status, "FAIL")
                self.assertEqual(result.rule_counts["ACK002"], 1)

    def test_denial_is_enforced_when_policy_requires_no_categories(self):
        result = report([proposal(), request(), decision(), execution()], policy=Policy(require_approval_for=()))
        self.assertEqual(result.status, "FAIL")
        self.assertIn("ACK002", result.rule_counts)
        self.assertNotIn("ACK001", result.rule_counts)

    def test_policy_covered_denial_with_no_reference_reports_both_defects(self):
        result = report(
            [proposal(), request(), decision(), execution()],
            policy=Policy(require_approval_for=("filesystem:read",)),
        )
        self.assertEqual(result.status, "FAIL")
        self.assertIn("ACK001", result.rule_counts)
        self.assertIn("ACK002", result.rule_counts)

    def test_allow_without_execution_link_is_incomplete(self):
        result = report([proposal(), request(), decision("allow"), execution()])
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertEqual(set(result.rule_counts), {"ACK009"})

    def test_pending_request_without_execution_link_is_incomplete(self):
        result = report([proposal(), request(), execution()])
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertEqual(set(result.rule_counts), {"ACK009"})

    def test_linked_allow_passes_for_uncovered_action(self):
        self.assertEqual(report([proposal(), request(), decision("allow"), execution("p")]).status, "PASS")

    def test_unrelated_denial_does_not_require_approval(self):
        result = report([
            proposal("other"), request(action_id="other"), decision(action_id="other"),
            event("action_blocked", 3, action_id="other", approval_id="p"),
            proposal(offset=4), execution(offset=5),
        ])
        self.assertEqual(result.status, "PASS")

    def test_future_denial_cannot_retroactively_deny_execution(self):
        result = report([proposal(), execution(offset=1), request(offset=2), decision(offset=3)])
        self.assertEqual(result.status, "PASS")
        self.assertNotIn("ACK002", result.rule_counts)

    def test_future_denial_after_pending_request_is_incomplete(self):
        result = report([proposal(), request(), execution(offset=2), decision(offset=3)])
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertNotIn("ACK002", result.rule_counts)

    def test_old_allow_does_not_override_newer_denial(self):
        result = report([
            proposal(), request("old"), decision("allow", "old"),
            request("new", offset=3), decision("deny", "new", offset=4), execution("old", offset=5),
        ])
        self.assertEqual(result.status, "FAIL")
        self.assertIn("ACK002", result.rule_counts)

    def test_later_allow_overrides_same_action_denial(self):
        result = report([
            proposal(), request(), decision(), request("new", offset=3),
            decision("allow", "new", offset=4), execution("new", offset=5),
        ])
        self.assertEqual(result.status, "PASS")

    def test_outstanding_request_can_receive_later_reapproval(self):
        result = report([
            proposal(), request(), request("new", offset=2), decision(offset=3),
            decision("allow", "new", offset=4), execution("new", offset=5),
        ])
        self.assertEqual(result.status, "PASS")

    def test_later_allow_requires_correct_execution_reference(self):
        for approval_id in (None, "p", "unknown"):
            with self.subTest(approval_id=approval_id):
                result = report([
                    proposal(), request(), decision(), request("new", offset=3),
                    decision("allow", "new", offset=4), execution(approval_id, offset=5),
                ])
                self.assertEqual(result.status, "FAIL")
                self.assertIn("ACK002", result.rule_counts)

    def test_duplicate_later_denial_is_not_hidden_by_first_allow(self):
        result = report([
            proposal(), request(), decision("allow"), decision("deny", offset=3), execution("p", offset=4),
        ])
        self.assertEqual(result.status, "FAIL")
        self.assertIn("ACK009", result.rule_counts)
        self.assertIn("ACK002", result.rule_counts)

    def test_allow_for_another_action_cannot_override_denial(self):
        result = report([
            proposal(), request(), decision(), proposal("other", 3), request("new", "other", 4),
            decision("allow", "new", "other", 5), execution("new", offset=6),
            event("action_blocked", 7, action_id="other", approval_id="new"),
        ])
        self.assertEqual(result.status, "FAIL")
        self.assertIn("ACK003", result.rule_counts)
        self.assertIn("ACK002", result.rule_counts)

    def test_mismatched_decision_cannot_override_denial(self):
        result = report([
            proposal(), request(), decision(), request("new", offset=3),
            decision("allow", "new", "other", 4), execution("new", offset=5),
        ])
        self.assertEqual(result.status, "FAIL")
        self.assertIn("ACK003", result.rule_counts)
        self.assertIn("ACK002", result.rule_counts)

    def test_changed_action_cannot_override_denial(self):
        changed = replace(READ, resource="private.txt")
        result = report([
            proposal(), request(), decision(), request("new", offset=3),
            decision("allow", "new", offset=4), replace(execution("new", offset=5), action=changed),
        ])
        self.assertEqual(result.status, "FAIL")
        self.assertIn("ACK003", result.rule_counts)
        self.assertIn("ACK002", result.rule_counts)

    def test_expired_allow_cannot_override_denial(self):
        result = report([
            proposal(), request(), decision(), request("new", offset=3),
            decision("allow", "new", offset=4, expires_at=BASE + timedelta(seconds=5)), execution("new", offset=6),
        ])
        self.assertEqual(result.status, "FAIL")
        self.assertIn("ACK005", result.rule_counts)
        self.assertIn("ACK002", result.rule_counts)

    def test_single_use_allow_cannot_be_reused_after_denial(self):
        result = report([
            proposal(), request(), decision(), request("new", offset=3),
            decision("allow", "new", offset=4), execution("new", offset=5), execution("new", offset=6),
        ])
        self.assertEqual(result.status, "FAIL")
        self.assertIn("ACK004", result.rule_counts)
        self.assertEqual(result.rule_counts["ACK002"], 1)

    def test_reusable_allow_policy_is_preserved(self):
        result = report([
            proposal(), request(), decision(), request("new", offset=3),
            decision("allow", "new", offset=4), execution("new", offset=5), execution("new", offset=6),
        ], policy=Policy(approval_single_use=False))
        self.assertEqual(result.status, "PASS")

    def test_block_remains_terminal_despite_later_allow(self):
        result = report([
            proposal(), request(), decision(), event("action_blocked", 3, action_id="a", approval_id="p"),
            request("new", offset=4), decision("allow", "new", offset=5), execution("new", offset=6),
        ])
        self.assertEqual(result.status, "FAIL")
        self.assertIn("ACK006", result.rule_counts)

    def test_future_allow_cannot_override_denial(self):
        result = report([
            proposal(), request(), decision(), request("new", offset=3),
            execution("new", offset=4), decision("allow", "new", offset=5),
        ])
        self.assertEqual(result.status, "FAIL")
        self.assertIn("ACK006", result.rule_counts)
        self.assertIn("ACK002", result.rule_counts)


class IntentBindingTests(unittest.TestCase):
    def denied_action(self, *, approval_id="denied", intent_id="i"):
        return [
            proposal("denied-action", offset=4),
            request(approval_id, "denied-action", 5, intent_id=intent_id),
            decision("deny", approval_id, "denied-action", 6),
            event("action_blocked", 7, action_id="denied-action", approval_id=approval_id),
        ]

    def test_request_only_intent_inherits_to_execution(self):
        result = report([
            proposal(), request(intent_id="i"), decision("allow"),
            *self.denied_action(), execution("p", offset=8),
        ])
        self.assertEqual(result.status, "FAIL")
        self.assertIn("ACK007", result.rule_counts)

    def test_decision_only_intent_inherits_to_execution(self):
        result = report([
            proposal(), request(), decision("allow", intent_id="i"),
            *self.denied_action(), execution("p", offset=8),
        ])
        self.assertEqual(result.status, "FAIL")
        self.assertIn("ACK007", result.rule_counts)

    def test_changed_execution_intent_does_not_hide_request_intent(self):
        result = report([
            proposal(), request(intent_id="i"), decision("allow"),
            *self.denied_action(), execution("p", offset=8, intent_id="other"),
        ])
        self.assertEqual(result.status, "FAIL")
        self.assertIn("ACK009", result.rule_counts)
        self.assertIn("ACK007", result.rule_counts)

    def test_later_allow_with_conflicting_intent_does_not_override_denial(self):
        result = report([
            proposal(intent_id="i"), request(), decision(), request("new", offset=3),
            decision("allow", "new", offset=4, intent_id="other"), execution("new", offset=5),
        ])
        self.assertEqual(result.status, "FAIL")
        self.assertIn("ACK009", result.rule_counts)
        self.assertIn("ACK002", result.rule_counts)

    def test_nonadjacent_conflicting_intent_is_incomplete_when_blocked(self):
        result = report([
            proposal(intent_id="i"), request(), decision(intent_id="other"),
            event("action_blocked", 3, action_id="a", approval_id="p"),
        ])
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("ACK009", result.rule_counts)

    def test_conflicting_intents_across_requests_are_incomplete_when_blocked(self):
        result = report([
            proposal(), request("first", intent_id="i"), decision("allow", "first"),
            request("second", offset=3, intent_id="other"), decision("deny", "second", offset=4),
            event("action_blocked", 5, action_id="a", approval_id="second"),
        ])
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertEqual(set(result.rule_counts), {"ACK009"})

    def test_earlier_approval_intent_survives_new_approval_id(self):
        result = report([
            proposal(), request(intent_id="i"), decision("allow"), request("new", offset=3),
            decision("allow", "new", offset=4), *self.denied_action(), execution("new", offset=8),
        ])
        self.assertEqual(result.status, "FAIL")
        self.assertIn("ACK007", result.rule_counts)

    def test_denial_inherits_intent_from_earlier_approval_id(self):
        result = report([
            proposal(), request(intent_id="i"), decision("allow"), request("new", offset=3),
            decision("deny", "new", offset=4), event("action_blocked", 5, action_id="a", approval_id="new"),
            proposal("other", offset=6, intent_id="i"), execution(action_id="other", offset=7),
        ])
        self.assertEqual(result.status, "FAIL")
        self.assertIn("ACK007", result.rule_counts)

    def test_later_allow_can_authorise_inherited_intent(self):
        result = report([
            proposal(), request(intent_id="i"), *self.denied_action(),
            decision("allow", offset=8), execution("p", offset=9),
        ])
        self.assertEqual(result.status, "PASS")

    def test_unrelated_intent_does_not_inherit_denial(self):
        result = report([
            proposal(), request(intent_id="unrelated"), decision("allow"),
            *self.denied_action(), execution("p", offset=8),
        ])
        self.assertEqual(result.status, "PASS")

    def test_later_intent_evidence_is_not_used_retroactively(self):
        result = report([
            proposal(), request(), decision("allow"), *self.denied_action(), execution("p", offset=8),
            request("later", offset=9, intent_id="i"), decision("allow", "later", offset=10),
        ])
        self.assertEqual(result.status, "PASS")

    def test_later_intent_evidence_does_not_rewrite_prior_denial(self):
        result = report([
            proposal(), request(), decision(), event("action_blocked", 3, action_id="a", approval_id="p"),
            proposal("other", offset=4, intent_id="i"), execution(action_id="other", offset=5),
            request("later", offset=6, intent_id="i"), decision("allow", "later", offset=7),
        ])
        self.assertEqual(result.status, "PASS")


if __name__ == "__main__":
    unittest.main()
