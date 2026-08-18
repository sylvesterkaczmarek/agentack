import json
import tempfile
import unittest
from pathlib import Path

from agentack.adapters.base import AdapterTestResult, CheckResult
from agentack.demo import demo_events
from agentack.engine import evaluate_events
from agentack.models import ActionIdentity, ActionLifecycleIdentity, TRACE_SCHEMA_VERSION
from agentack.parser import read_jsonl_with_digest, write_jsonl
from agentack.policy import Policy
from agentack.provenance import policy_sha256
from agentack.report import (
    adapter_report_payload,
    adapter_sarif_payload,
    trace_report_payload,
    trace_sarif_payload,
)


class ProvenanceTests(unittest.TestCase):
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
