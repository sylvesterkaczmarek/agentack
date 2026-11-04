from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from unittest import mock

from agentack import Action, Recorder, action_hash, evaluate_events
from agentack.demo import demo_events
from agentack.models import TraceEvent, TraceValidationError
from agentack.parser import write_jsonl
from agentack.policy import Policy
from agentack.validation import strict_json_loads
from agentack.adapters.claude import ClaudeCodeAdapter, claude_action
from agentack.adapters.claude_analysis import analyze_capture
from agentack.adapters.claude_capture import read_capture, record_hook_event
from agentack.adapters.otel import extract_tool_decisions
from test_adapters_claude import complete_capture


class ValidationContractTests(unittest.TestCase):
    def test_empty_public_input_has_validation_error(self):
        with self.assertRaises(TraceValidationError):
            evaluate_events([])

    def test_public_api_rejects_mixed_sessions(self):
        events = demo_events("secure")
        events[3] = dataclasses.replace(events[3], session_id="another-session")
        with self.assertRaises(TraceValidationError):
            evaluate_events(events)

    def test_public_api_rejects_invalid_objects(self):
        for value in (None, {}, "event", 42):
            with self.subTest(value=value), self.assertRaises(TraceValidationError):
                evaluate_events([value])

    def test_public_api_rejects_naive_datetime(self):
        events = demo_events("secure")
        events[0] = dataclasses.replace(events[0], timestamp=events[0].timestamp.replace(tzinfo=None))
        with self.assertRaises(TraceValidationError):
            evaluate_events(events)

    def test_clock_regression_cannot_pass(self):
        events = demo_events("secure")
        events[3] = dataclasses.replace(events[3], timestamp=events[0].timestamp - timedelta(days=1))
        self.assertEqual(evaluate_events(events).status, "INCOMPLETE")

    def test_identity_keeps_interpreters_distinct(self):
        actions = [
            Action(tool, "run", parameters={"command": "echo $HOME"}) for tool in ("bash", "powershell", "cmd", "shell")
        ]
        self.assertEqual(len({action_hash(a) for a in actions}), len(actions))

    def test_identity_domain_is_versioned(self):
        action = Action("shell", "run")
        old = hashlib.sha256(
            json.dumps(action.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        self.assertNotEqual(action_hash(action), old)

    def test_native_tool_and_cwd_change_identity_without_exposing_path(self):
        first = claude_action("Bash", {"command": "echo ok"}, cwd="/synthetic/one")
        second = claude_action("Bash", {"command": "echo ok"}, cwd="/synthetic/two")
        self.assertNotEqual(action_hash(first), action_hash(second))
        self.assertNotIn("/synthetic/one", json.dumps(first.to_dict()))

    def test_reserved_context_cannot_be_injected_by_tool_input(self):
        with self.assertRaises(ValueError):
            claude_action("Bash", {"_agentack_execution_context": {}})

    def test_parameter_unicode_is_validated_before_hash(self):
        with self.assertRaises(TraceValidationError):
            action_hash(Action("shell", "run", parameters={"command": chr(0xD800)}))

    def test_action_dictionary_key_unicode_is_validated(self):
        with self.assertRaises(TraceValidationError):
            action_hash(Action("shell", "run", parameters={chr(0xD800): "value"}))

    def test_schema_version_is_integer_not_equal_float(self):
        payload = demo_events("secure")[0].to_dict()
        payload["schema_version"] = 2.0
        with self.assertRaises(TraceValidationError):
            TraceEvent.from_dict(payload)

    def test_cli_malformed_inputs_are_input_errors_without_tracebacks(self):
        fixtures = []
        for field, value in (
            ("type", []),
            ("type", {}),
            ("decision", []),
            ("decision", {}),
            ("session_id", chr(0xD800)),
        ):
            payload = demo_events("secure")[2 if field == "decision" else 0].to_dict()
            payload[field] = value
            fixtures.append(json.dumps(payload))
        fixtures.append('{"x":' + "[" * 1000 + "0" + "]" * 1000 + "}")
        for value in fixtures:
            with self.subTest(value=value[:70]), tempfile.TemporaryDirectory() as directory:
                trace = Path(directory) / "bad.jsonl"
                trace.write_text(value + "\n")
                result = subprocess.run(
                    [sys.executable, "-m", "agentack", "check", str(trace)], text=True, capture_output=True, timeout=10
                )
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_cli_invalid_action_unicode_is_input_error(self):
        values = [e.to_dict() for e in demo_events("secure")]
        for value in values:
            if "action" in value:
                value["action"]["parameters"]["command"] = chr(0xD800)
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "bad.jsonl"
            trace.write_text("\n".join(json.dumps(x) for x in values) + "\n")
            result = subprocess.run(
                [sys.executable, "-m", "agentack", "check", str(trace)], text=True, capture_output=True, timeout=10
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_json_decoder_is_bounded_and_strict(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', "[" * 1000 + "0" + "]" * 1000, b"\xff"):
            with self.subTest(raw=str(raw)[:30]), self.assertRaises(TraceValidationError):
                strict_json_loads(raw)

    def test_json_brackets_inside_strings_do_not_count_as_nesting(self):
        self.assertEqual(strict_json_loads(json.dumps({"text": "[" * 100})), {"text": "[" * 100})

    def test_write_rejects_bad_input_before_truncating_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "existing"
            path.write_text("preserve")
            with self.assertRaises(TraceValidationError):
                write_jsonl(path, [])
            self.assertEqual(path.read_text(), "preserve")

    def test_recorder_validates_session_before_opening_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.jsonl"
            with self.assertRaises(TraceValidationError):
                Recorder(path, "")
            self.assertFalse(path.exists())

    def test_recorder_rejects_append_to_ended_or_other_session(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            write_jsonl(path, demo_events("secure"))
            before = path.read_bytes()
            with self.assertRaises(TraceValidationError):
                Recorder(path, "other", append=True)
            self.assertEqual(path.read_bytes(), before)

    def test_capture_reader_rejects_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.jsonl"
            path.write_text('{"capture_version":2,"capture_version":2}\n')
            with self.assertRaises(ValueError):
                read_capture(path)

    def test_hook_session_and_event_are_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.jsonl"
            with self.assertRaises(ValueError):
                record_hook_event("SessionEnd", path, b'{"session_id":"s","hook_event_name":"PreToolUse"}')
            self.assertFalse(path.exists())

    def test_policy_rejects_untyped_or_invalid_values(self):
        for changes in (
            {"max_approval_age_seconds": True},
            {"approval_single_use": 1},
            {"require_approval_for": (" ",)},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                Policy(**changes)

    def test_policy_rejects_unknown_options(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.toml"
            path.write_text("version=1\n[approval]\nmax_age_second=3\n")
            with self.assertRaises(ValueError):
                Policy.from_toml(path)

    def test_malformed_capture_fails_closed(self):
        for value in (None, {}, [{}], [{"event": []}]):
            self.assertEqual(analyze_capture(value).status, "INCOMPLETE")

    def test_otel_shape_confusion_is_validation_error(self):
        for payload in ({"resourceLogs": {}}, {"resourceLogs": [{"scopeLogs": None}]}):
            with self.assertRaises(ValueError):
                extract_tool_decisions([payload])

    def test_claude_unknown_version_is_not_testable(self):
        with mock.patch("agentack.adapters.claude_live._safe_version", return_value="unknown"):
            status = ClaudeCodeAdapter(executable="/fake/claude").detect()
        self.assertTrue(status.installed)
        self.assertFalse(status.testable)

    def test_claude_missing_capability_is_not_testable(self):
        with (
            mock.patch("agentack.adapters.claude_live._safe_version", return_value="2.1.0"),
            mock.patch(
                "agentack.adapters.claude_live.subprocess.run",
                return_value=mock.Mock(returncode=0, stdout="--tools", stderr=""),
            ),
        ):
            self.assertFalse(ClaudeCodeAdapter(executable="/fake/claude").detect().testable)

    def test_noninteractive_live_run_never_starts_session(self):
        adapter = ClaudeCodeAdapter(executable="/fake/claude")
        from agentack.adapters.base import AdapterStatus

        with (
            mock.patch.object(
                adapter, "detect", return_value=AdapterStatus("claude", "Claude Code", True, True, "/fake/claude")
            ),
            mock.patch("agentack.adapters.claude_live._interactive_terminal", return_value=False),
            mock.patch("agentack.adapters.claude_live.subprocess.run") as run,
        ):
            self.assertEqual(adapter.run_test().status, "INCOMPLETE")
            run.assert_not_called()

    def test_all_valid_fixture_actions_have_context(self):
        records, _ = complete_capture()
        for record in records:
            if "action" in record:
                self.assertIn("_agentack_execution_context", record["action"]["parameters"])

    def test_opaque_session_identifiers_are_not_silently_trimmed(self):
        events = demo_events("secure")
        events[3] = dataclasses.replace(events[3], session_id=" " + events[3].session_id)
        with self.assertRaises(TraceValidationError):
            evaluate_events(events)

    def test_exact_tool_identifiers_are_not_silently_trimmed(self):
        self.assertNotEqual(action_hash(Action("Bash", "run")), action_hash(Action("Bash ", "run")))

    def test_missing_outcome_marks_completeness_incomplete(self):
        records, decisions = complete_capture()
        records = [r for r in records if r["event"] != "PostToolUse"]
        result = analyze_capture(records, decisions)
        self.assertEqual({c.label: c.status for c in result.checks}["Evidence completeness"], "INCOMPLETE")
