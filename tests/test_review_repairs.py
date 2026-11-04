"""Regression controls from the independent review and adjacent evidence cases.

Every action is synthetic data. No agent or represented command is executed.
"""

from __future__ import annotations

import copy
from dataclasses import replace
import unittest

from agentack.adapters.claude_analysis import APPROVE_COMMAND, ROUTE_B_COMMAND, analyze_capture
from agentack.adapters.otel import _otel_value, extract_tool_decisions
from agentack.models import TraceValidationError
from test_adapters_claude import complete_capture, hook_record


def telemetry(decisions):
    logs = []
    for decision in decisions:
        attributes = {
            "event.name": "tool_decision",
            "tool_use_id": decision.tool_use_id,
            "tool_name": decision.tool_name,
            "decision": decision.decision,
            "source": decision.source,
            "session.id": decision.session_id,
        }
        logs.append(
            {
                "body": {"stringValue": "claude_code.tool_decision"},
                "attributes": [{"key": key, "value": {"stringValue": value}} for key, value in attributes.items()],
            }
        )
    return {"resourceLogs": [{"scopeLogs": [{"logRecords": logs}]}]}


def first_log(payload):
    return payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]


def attribute(payload, name):
    return next(entry for entry in first_log(payload)["attributes"] if entry["key"] == name)


class TelemetryReviewRepairs(unittest.TestCase):
    def setUp(self):
        self.records, self.decisions = complete_capture()
        self.payload = telemetry(self.decisions)

    def assert_rejected(self, payload=None):
        with self.assertRaises(TraceValidationError):
            extract_tool_decisions([self.payload if payload is None else payload])

    def test_standard_otlp_remains_valid(self):
        parsed = extract_tool_decisions([self.payload])
        self.assertEqual(parsed, self.decisions)
        self.assertEqual(analyze_capture(self.records, parsed).status, "PASS")

    def test_conflicting_decision_aliases_are_rejected(self):
        first_log(self.payload)["attributes"].append({"key": "decision_type", "value": {"stringValue": "reject"}})
        self.assert_rejected()

    def test_conflicting_source_aliases_are_rejected(self):
        first_log(self.payload)["attributes"].append({"key": "decision_source", "value": {"stringValue": "config"}})
        self.assert_rejected()

    def test_matching_aliases_remain_valid(self):
        first_log(self.payload)["attributes"].extend(
            [
                {"key": "decision_type", "value": {"stringValue": "accept"}},
                {"key": "decision_source", "value": {"stringValue": "user_temporary"}},
            ]
        )
        self.assertEqual(extract_tool_decisions([self.payload]), self.decisions)

    def test_legacy_aliases_without_primary_remain_valid(self):
        for entry in first_log(self.payload)["attributes"]:
            if entry["key"] == "decision":
                entry["key"] = "decision_type"
            if entry["key"] == "source":
                entry["key"] = "decision_source"
        self.assertEqual(extract_tool_decisions([self.payload]), self.decisions)

    def test_empty_primary_alias_is_not_hidden_by_fallback(self):
        attribute(self.payload, "decision")["value"] = {"stringValue": ""}
        first_log(self.payload)["attributes"].append({"key": "decision_type", "value": {"stringValue": "accept"}})
        self.assert_rejected()

    def test_multi_typed_anyvalue_is_rejected(self):
        attribute(self.payload, "decision")["value"]["boolValue"] = False
        self.assert_rejected()

    def test_raw_anyvalue_is_rejected(self):
        attribute(self.payload, "decision")["value"] = "accept"
        self.assert_rejected()

    def test_wrong_typed_payloads_are_rejected(self):
        malformed = [
            {"stringValue": False},
            {"stringValue": 3},
            {"stringValue": []},
            {"boolValue": "accept"},
            {"intValue": "accept"},
            {"intValue": True},
            {"intValue": str(2**63)},
            {"intValue": -(2**63) - 1},
            {"doubleValue": "accept"},
            {"doubleValue": True},
            {"bytesValue": "!!"},
            {"arrayValue": []},
            {"kvlistValue": []},
        ]
        for value in malformed:
            with self.subTest(value=value), self.assertRaises(TraceValidationError):
                _otel_value(value)

    def test_nonstring_security_fields_are_rejected(self):
        for name in ("tool_use_id", "decision", "source", "session.id", "tool_name"):
            for value in ({"boolValue": True}, {"intValue": "3"}, {}, {"arrayValue": {"values": []}}):
                with self.subTest(name=name, value=value):
                    payload = copy.deepcopy(self.payload)
                    attribute(payload, name)["value"] = value
                    self.assert_rejected(payload)

    def test_known_nonsensitive_typed_values_are_supported(self):
        values = [
            ({}, None),
            ({"futureValue": "opaque"}, None),
            ({"stringValue": "ok", "futureField": 1}, "ok"),
            ({"boolValue": False}, False),
            ({"intValue": "-7"}, -7),
            ({"intValue": 7}, 7),
            ({"doubleValue": 1.25}, 1.25),
            ({"bytesValue": "aGk="}, b"hi"),
            ({"arrayValue": {"values": [{"stringValue": "x"}, {"intValue": "2"}]}}, ["x", 2]),
            ({"kvlistValue": {"values": [{"key": "k", "value": {"boolValue": True}}]}}, {"k": True}),
        ]
        for encoded, expected in values:
            with self.subTest(encoded=encoded):
                self.assertEqual(_otel_value(encoded), expected)

    def test_duplicate_nested_keys_are_rejected(self):
        with self.assertRaises(TraceValidationError):
            _otel_value(
                {
                    "kvlistValue": {
                        "values": [
                            {"key": "k", "value": {"stringValue": "one"}},
                            {"key": "k", "value": {"stringValue": "two"}},
                        ]
                    }
                }
            )

    def test_excessive_anyvalue_depth_is_rejected(self):
        value = {"stringValue": "x"}
        for _ in range(22):
            value = {"arrayValue": {"values": [value]}}
        with self.assertRaises(TraceValidationError):
            _otel_value(value)

    def test_contradictory_event_name_and_body_are_rejected(self):
        first_log(self.payload)["body"] = {"stringValue": "different-event"}
        self.assert_rejected()

    def test_body_only_event_identifier_is_supported(self):
        first_log(self.payload)["attributes"] = [
            a for a in first_log(self.payload)["attributes"] if a["key"] != "event.name"
        ]
        self.assertEqual(extract_tool_decisions([self.payload]), self.decisions)

    def test_attribute_only_event_identifier_is_supported(self):
        first_log(self.payload).pop("body")
        self.assertEqual(extract_tool_decisions([self.payload]), self.decisions)

    def test_identical_exporter_retries_are_deduplicated(self):
        self.assertEqual(extract_tool_decisions([self.payload, copy.deepcopy(self.payload)]), self.decisions)

    def test_unrelated_structured_log_does_not_become_a_decision(self):
        first_log(self.payload)["body"] = {"arrayValue": {"values": [{"stringValue": "other"}]}}
        attribute(self.payload, "event.name")["value"] = {"stringValue": "other"}
        self.assertEqual(extract_tool_decisions([self.payload]), self.decisions[1:])


class CorrelationReviewRepairs(unittest.TestCase):
    def test_wrong_session_reject_cannot_establish_violation(self):
        records, decisions = complete_capture()
        decisions[0] = replace(decisions[0], session_id="foreign", decision="reject", source="user_reject")
        self.assertEqual(analyze_capture(records, decisions).status, "INCOMPLETE")

    def test_wrong_tool_reject_cannot_establish_violation(self):
        records, decisions = complete_capture()
        decisions[0] = replace(decisions[0], tool_name="Write", decision="reject", source="user_reject")
        self.assertEqual(analyze_capture(records, decisions).status, "INCOMPLETE")

    def test_wrong_session_automatic_accept_cannot_establish_violation(self):
        records, decisions = complete_capture()
        decisions[0] = replace(decisions[0], session_id="foreign", source="config")
        self.assertEqual(analyze_capture(records, decisions).status, "INCOMPLETE")

    def test_foreign_terminal_cannot_establish_violation(self):
        for field, value in (("session_id", "foreign"), ("tool_name", "Write")):
            with self.subTest(field=field):
                records, decisions = complete_capture()
                post = hook_record("PostToolUse", ROUTE_B_COMMAND, tool_use_id="tool-route-b")
                post[field] = value
                records.insert(-1, post)
                self.assertEqual(analyze_capture(records, decisions).status, "INCOMPLETE")

    def test_valid_violation_survives_foreign_decision_for_another_invocation(self):
        records, decisions = complete_capture()
        decisions[0] = replace(decisions[0], session_id="foreign", source="config")
        records.insert(-1, hook_record("PostToolUse", ROUTE_B_COMMAND, tool_use_id="tool-route-b"))
        result = analyze_capture(records, decisions)
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any(c.rule_id == "ACK002" and c.status == "FAIL" for c in result.checks))

    def test_valid_violation_survives_foreign_decision_with_same_id(self):
        records, decisions = complete_capture()
        decisions.append(replace(decisions[3], session_id="foreign", decision="accept", source="config"))
        records.insert(-1, hook_record("PostToolUse", ROUTE_B_COMMAND, tool_use_id="tool-route-b"))
        self.assertEqual(analyze_capture(records, decisions).status, "FAIL")

    def test_ambiguous_in_scope_decisions_remain_incomplete(self):
        records, decisions = complete_capture()
        decisions.append(replace(decisions[0], decision="reject", source="user_reject"))
        self.assertEqual(analyze_capture(records, decisions).status, "INCOMPLETE")

    def test_genuine_nonhuman_baseline_still_fails(self):
        records, decisions = complete_capture()
        decisions[0] = replace(decisions[0], source="config")
        self.assertEqual(analyze_capture(records, decisions).status, "FAIL")

    def test_failed_execution_after_denial_fails_ack002(self):
        records, decisions = complete_capture()
        records.insert(-1, hook_record("PostToolUseFailure", ROUTE_B_COMMAND, tool_use_id="tool-route-b"))
        result = analyze_capture(records, decisions)
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any(c.rule_id == "ACK002" and c.status == "FAIL" for c in result.checks))
        route = next(action for action in result.actions if action.action_id == "tool-route-b")
        self.assertIsNotNone(route.executed)
        self.assertFalse(route.blocked)

    def test_failed_baseline_after_denial_fails(self):
        records, decisions = complete_capture()
        records[2]["event"] = "PostToolUseFailure"
        decisions[0] = replace(decisions[0], decision="reject", source="user_reject")
        self.assertEqual(analyze_capture(records, decisions).status, "FAIL")

    def test_accepted_tool_failure_is_not_a_denial_violation(self):
        records, decisions = complete_capture()
        records[2]["event"] = "PostToolUseFailure"
        result = analyze_capture(records, decisions)
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertFalse(any(c.rule_id == "ACK002" and c.status == "FAIL" for c in result.checks))

    def test_failed_foreign_execution_is_not_attributed_to_denial(self):
        records, decisions = complete_capture()
        post = hook_record("PostToolUseFailure", ROUTE_B_COMMAND, tool_use_id="tool-route-b")
        post["session_id"] = "foreign"
        records.insert(-1, post)
        self.assertEqual(analyze_capture(records, decisions).status, "INCOMPLETE")

    def test_persistent_approval_with_fresh_prompts_still_passes(self):
        records, decisions = complete_capture()
        decisions[0] = replace(decisions[0], source="user_permanent")
        result = analyze_capture(records, decisions)
        self.assertEqual(result.status, "PASS")
        self.assertTrue(any(c.rule_id == "ACK004" and c.status == "SKIP" for c in result.checks))

    def test_valid_reapproval_remains_valid(self):
        records, decisions = complete_capture()
        decisions[1] = replace(decisions[1], decision="accept", source="user_temporary")
        records.insert(5, hook_record("PostToolUse", APPROVE_COMMAND, tool_use_id="tool-replay"))
        self.assertEqual(analyze_capture(records, decisions).status, "PASS")


if __name__ == "__main__":
    unittest.main()
