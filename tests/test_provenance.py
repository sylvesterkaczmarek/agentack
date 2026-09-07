import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agentack.adapters.base import AdapterTestResult, CheckResult
from agentack.demo import demo_events
from agentack.engine import evaluate_events
from agentack.models import Action, ActionIdentity, ActionLifecycleIdentity, TRACE_SCHEMA_VERSION, TraceEvent
from agentack.parser import read_jsonl_with_digest, write_jsonl
from agentack.policy import Policy
from agentack.provenance import action_identity, policy_sha256, trace_action_identities
from agentack.report import (
    adapter_report_payload,
    adapter_sarif_payload,
    trace_report_payload,
    trace_sarif_payload,
)


def event(event_type: str, offset: int, **kwargs) -> TraceEvent:  # type: ignore[no-untyped-def]
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=offset)
    return TraceEvent(event_type, timestamp, "s", **kwargs)  # type: ignore[arg-type]


class ProvenanceTests(unittest.TestCase):
    def test_fresh_approval_is_attributed_to_execution(self):
        action = Action("shell", "run", parameters={"argv": ["git", "status"]})
        events = [
            event("action_proposed", 0, action_id="a1", action=action),
            event("approval_requested", 1, action_id="a1", approval_id="p1", action=action),
            event("approval_decision", 2, action_id="a1", approval_id="p1", decision="deny"),
            event("approval_requested", 3, action_id="a1", approval_id="p2", action=action),
            event("approval_decision", 4, action_id="a1", approval_id="p2", decision="allow"),
            event("action_executed", 5, action_id="a1", approval_id="p2", action=action),
            event("session_end", 6),
        ]
        report = evaluate_events(events)
        self.assertEqual(report.status, "PASS")
        document = trace_report_payload(report, events, Policy(), trace_sha256="a" * 64, trace_source=None)
        self.assertEqual(len(document["actions"]), 1)
        summary = document["actions"][0]
        self.assertEqual(summary["approval_id"], "p2")
        self.assertEqual(summary["decision"], "allow")
        identity = action_identity(action)
        assert identity is not None
        self.assertEqual(summary["expected"], identity.to_dict())
        self.assertEqual(summary["presented"], summary["expected"])
        self.assertEqual(summary["executed"], summary["expected"])

    def test_overlapping_request_does_not_replace_execution_approval(self):
        approved = Action("shell", "run", parameters={"argv": ["git", "status"]})
        changed = Action("shell", "run", parameters={"argv": ["git", "push"]})
        events = [
            event("action_proposed", 0, action_id="a1", action=approved),
            event("approval_requested", 1, action_id="a1", approval_id="p1", action=approved),
            event("approval_decision", 2, action_id="a1", approval_id="p1", decision="allow"),
            event("approval_requested", 3, action_id="a1", approval_id="p2", action=changed),
            event("approval_decision", 4, action_id="a1", approval_id="p2", decision="deny"),
            event("action_executed", 5, action_id="a1", approval_id="p1", action=approved),
        ]
        summary = trace_action_identities(events)[0]
        self.assertEqual(summary.approval_id, "p1")
        self.assertEqual(summary.decision, "allow")
        self.assertEqual(summary.presented, action_identity(approved))
        self.assertEqual(summary.executed, action_identity(approved))

    def test_missing_terminal_approval_id_is_not_inferred(self):
        action = Action("shell", "run")
        for terminal_type in ("action_executed", "action_blocked"):
            with self.subTest(terminal_type=terminal_type):
                events = [
                    event("action_proposed", 0, action_id="a1", action=action),
                    event("approval_requested", 1, action_id="a1", approval_id="p1", action=action),
                    event("approval_decision", 2, action_id="a1", approval_id="p1", decision="allow"),
                    event(terminal_type, 3, action_id="a1", action=action if terminal_type == "action_executed" else None),
                ]
                summary = trace_action_identities(events)[0]
                self.assertIsNone(summary.approval_id)
                self.assertIsNone(summary.decision)
                self.assertIsNone(summary.presented)
                self.assertEqual(summary.expected, action_identity(action))
                self.assertEqual(summary.blocked, terminal_type == "action_blocked")

    def test_block_uses_its_explicit_approval_reference(self):
        action = Action("shell", "run")
        events = [
            event("action_proposed", 0, action_id="a1", action=action),
            event("approval_requested", 1, action_id="a1", approval_id="p1", action=action),
            event("approval_decision", 2, action_id="a1", approval_id="p1", decision="allow"),
            event("approval_requested", 3, action_id="a1", approval_id="p2", action=action),
            event("approval_decision", 4, action_id="a1", approval_id="p2", decision="deny"),
            event("action_blocked", 5, action_id="a1", approval_id="p2"),
            event("action_blocked", 6, action_id="a1", approval_id="p1"),
        ]
        summary = trace_action_identities(events)[0]
        self.assertEqual(summary.approval_id, "p2")
        self.assertEqual(summary.decision, "deny")
        self.assertEqual(summary.presented, action_identity(action))
        self.assertTrue(summary.blocked)
        self.assertIsNone(summary.executed)

    def test_first_execution_takes_precedence_over_blocks_and_later_executions(self):
        action = Action("shell", "run")
        changed = Action("shell", "run", parameters={"argv": ["git", "push"]})
        events = [
            event("action_proposed", 0, action_id="a1", action=action),
            event("approval_requested", 1, action_id="a1", approval_id="p1", action=action),
            event("approval_decision", 2, action_id="a1", approval_id="p1", decision="allow"),
            event("action_blocked", 3, action_id="a1", approval_id="p2"),
            event("action_executed", 4, action_id="a1", approval_id="p1", action=action),
            event("action_executed", 5, action_id="a1", approval_id="p2", action=changed),
            event("action_blocked", 6, action_id="a1", approval_id="p2"),
        ]
        summary = trace_action_identities(events)[0]
        self.assertEqual(summary.approval_id, "p1")
        self.assertEqual(summary.decision, "allow")
        self.assertEqual(summary.executed, action_identity(action))
        self.assertTrue(summary.blocked)

    def test_first_request_and_decision_are_used_for_duplicate_approval_id(self):
        action = Action("shell", "run")
        changed = Action("shell", "run", parameters={"argv": ["git", "push"]})
        events = [
            event("action_proposed", 0, action_id="a1", action=action),
            event("approval_requested", 1, action_id="a1", approval_id="p1", action=action),
            event("approval_decision", 2, action_id="a1", approval_id="p1", decision="deny"),
            event("approval_requested", 3, action_id="a1", approval_id="p1", action=changed),
            event("approval_decision", 4, action_id="a1", approval_id="p1", decision="allow"),
            event("action_executed", 5, action_id="a1", approval_id="p1", action=changed),
        ]
        summary = trace_action_identities(events)[0]
        self.assertEqual(summary.decision, "deny")
        self.assertEqual(summary.presented, action_identity(action))
        self.assertEqual(summary.executed, action_identity(changed))

    def test_duplicate_approval_for_other_action_does_not_supply_evidence(self):
        first = Action("shell", "run")
        second = Action("filesystem", "delete", resource="report.txt")
        events = [
            event("action_proposed", 0, action_id="a1", action=first),
            event("approval_requested", 1, action_id="a1", approval_id="p1", action=first),
            event("approval_decision", 2, action_id="a1", approval_id="p1", decision="deny"),
            event("action_proposed", 3, action_id="a2", action=second),
            event("approval_requested", 4, action_id="a2", approval_id="p1", action=second),
            event("approval_decision", 5, action_id="a2", approval_id="p1", decision="allow"),
            event("action_executed", 6, action_id="a2", approval_id="p1", action=second),
        ]
        summaries = trace_action_identities(iter(events))
        self.assertEqual([summary.action_id for summary in summaries], ["a1", "a2"])
        self.assertEqual(summaries[0].decision, "deny")
        self.assertEqual(summaries[1].approval_id, "p1")
        self.assertIsNone(summaries[1].presented)
        self.assertIsNone(summaries[1].decision)
        self.assertEqual(summaries[1].expected, action_identity(second))
        self.assertEqual(summaries[1].executed, action_identity(second))

    def test_unfinished_lifecycle_uses_first_observed_approval(self):
        action = Action("shell", "run")
        changed = Action("shell", "run", parameters={"argv": ["git", "push"]})
        events = [
            event("action_proposed", 0, action_id="a1", action=action),
            event("approval_requested", 1, action_id="a1", approval_id="p1", action=action),
            event("approval_decision", 2, action_id="a1", approval_id="p1", decision="deny"),
            event("approval_requested", 3, action_id="a1", approval_id="p2", action=changed),
            event("approval_decision", 4, action_id="a1", approval_id="p2", decision="allow"),
        ]
        summary = trace_action_identities(events)[0]
        self.assertEqual(summary.approval_id, "p1")
        self.assertEqual(summary.decision, "deny")
        self.assertEqual(summary.presented, action_identity(action))
        self.assertIsNone(summary.executed)
        self.assertFalse(summary.blocked)

    def test_trace_digest_matches_exact_parsed_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            write_jsonl(path, demo_events("secure"))
            events, digest = read_jsonl_with_digest(path)
            import hashlib

            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(len(events), len(demo_events("secure")))

    def test_policy_hash_is_semantic_and_stable(self):
        left = Policy(require_approval_for=("network:*", "shell:*"))
        right = Policy(require_approval_for=("shell:*", "network:*"))
        self.assertEqual(policy_sha256(left), policy_sha256(right))

    def test_trace_report_contains_platform_ready_provenance_without_raw_parameters(self):
        events = demo_events("secure")
        report = evaluate_events(events, source="/private/user/trace.jsonl")
        document = trace_report_payload(
            report,
            events,
            Policy(),
            trace_sha256="a" * 64,
            trace_source="/private/user/trace.jsonl",
            policy_source="/private/user/policy.toml",
            run_id="run-123",
            evaluated_at="2026-08-18T16:00:00Z",
        )
        self.assertEqual(document["report_schema_version"], 1)
        self.assertEqual(document["producer"]["name"], "AgentAck")
        self.assertEqual(document["run"]["run_id"], "run-123")
        self.assertEqual(document["run"]["session_id"], events[0].session_id)
        self.assertEqual(document["input"]["trace"]["schema_version"], TRACE_SCHEMA_VERSION)
        self.assertEqual(document["input"]["trace"]["source"], "trace.jsonl")
        self.assertEqual(document["input"]["policy"]["source"], "policy.toml")
        self.assertEqual(document["result"]["status"], "PASS")
        first_action = document["actions"][0]
        self.assertIn("sha256", first_action["expected"])
        self.assertIn("sha256", first_action["presented"])
        self.assertIn("sha256", first_action["executed"])
        serialized = json.dumps(document)
        self.assertNotIn("/private/user", serialized)
        self.assertNotIn("argv", serialized)

    def test_trace_sarif_contains_version_provenance_and_action_identities(self):
        events = demo_events("action-swap")
        report = evaluate_events(events, source="trace.jsonl")
        document = trace_report_payload(
            report,
            events,
            Policy(),
            trace_sha256="b" * 64,
            trace_source="trace.jsonl",
            run_id="run-456",
            evaluated_at="2026-08-18T16:00:00Z",
        )
        sarif = trace_sarif_payload(report, document)
        run = sarif["runs"][0]
        self.assertEqual(run["automationDetails"]["id"], "run-456")
        self.assertTrue(run["tool"]["driver"]["version"])
        self.assertEqual(run["properties"]["traceSha256"], "b" * 64)
        self.assertTrue(run["properties"]["actionIdentities"])
        self.assertTrue(run["results"])
        self.assertIn("remediation", run["results"][0]["properties"])

    def test_adapter_report_contains_adapter_and_evidence_provenance(self):
        identity = ActionIdentity(sha256="c" * 64, tool="shell", operation="run")
        result = AdapterTestResult(
            adapter="claude",
            display_name="Claude Code",
            status="PASS",
            checks=(CheckResult("Approval required", "PASS", "Observed."),),
            adapter_version="claude 2.1.0",
            session_id="session-1",
            evidence_sha256="d" * 64,
            actions=(
                ActionLifecycleIdentity(
                    action_id="tool-1",
                    approval_id="tool-1",
                    decision="allow",
                    expected=identity,
                    presented=identity,
                    executed=identity,
                ),
            ),
        )
        document = adapter_report_payload(
            result,
            run_id="run-adapter",
            evaluated_at="2026-08-18T16:00:00Z",
        )
        self.assertEqual(document["adapter"]["name"], "claude")
        self.assertEqual(document["adapter"]["version"], "claude 2.1.0")
        self.assertEqual(document["input"]["evidence"]["sha256"], "d" * 64)
        self.assertEqual(document["run"]["session_id"], "session-1")
        self.assertEqual(document["actions"][0]["presented"]["sha256"], "c" * 64)

        sarif = adapter_sarif_payload(result, document)
        run = sarif["runs"][0]
        self.assertEqual(run["properties"]["adapterName"], "claude")
        self.assertEqual(run["properties"]["evidenceSha256"], "d" * 64)
        self.assertEqual(run["results"], [])


if __name__ == "__main__":
    unittest.main()
