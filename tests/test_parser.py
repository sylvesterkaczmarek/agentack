import json
import tempfile
import unittest
from pathlib import Path

from agentack.demo import demo_events
from agentack.models import TRACE_SCHEMA_VERSION, TraceValidationError
from agentack.parser import read_jsonl, write_jsonl


class ParserTests(unittest.TestCase):
    def _write_line(self, payload: str) -> Path:
        self._temporary = tempfile.TemporaryDirectory()
        path = Path(self._temporary.name) / "trace.jsonl"
        path.write_text(payload + "\n", encoding="utf-8")
        return path

    def tearDown(self):
        temporary = getattr(self, "_temporary", None)
        if temporary is not None:
            temporary.cleanup()
            del self._temporary

    def test_round_trip(self):
        events = demo_events("secure")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            write_jsonl(path, events)
            loaded = read_jsonl(path)
        self.assertEqual([item.to_dict() for item in loaded], [item.to_dict() for item in events])

    def test_rejects_multiple_sessions(self):
        events = demo_events("secure")
        changed = list(events)
        last = events[-1]
        changed[-1] = type(last)(type=last.type, timestamp=last.timestamp, session_id="another-session")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            write_jsonl(path, changed)
            with self.assertRaises(TraceValidationError):
                read_jsonl(path)

    def test_rejects_invalid_json(self):
        path = self._write_line("{not json}")
        with self.assertRaises(TraceValidationError):
            read_jsonl(path)

    def test_rejects_duplicate_json_keys(self):
        path = self._write_line(
            '{"schema_version":2,"type":"session_end","type":"interrupt","timestamp":"2026-01-01T00:00:00Z","session_id":"s"}'
        )
        with self.assertRaisesRegex(TraceValidationError, "duplicate JSON object key"):
            read_jsonl(path)

    def test_rejects_unknown_event_fields(self):
        payload = {
            "schema_version": TRACE_SCHEMA_VERSION,
            "type": "session_end",
            "timestamp": "2026-01-01T00:00:00Z",
            "session_id": "s",
            "unexpected": True,
        }
        path = self._write_line(json.dumps(payload))
        with self.assertRaisesRegex(TraceValidationError, "unknown field"):
            read_jsonl(path)

    def test_rejects_unknown_action_fields(self):
        payload = {
            "schema_version": TRACE_SCHEMA_VERSION,
            "type": "action_proposed",
            "timestamp": "2026-01-01T00:00:00Z",
            "session_id": "s",
            "action_id": "a1",
            "action": {"tool": "shell", "operation": "run", "surprise": "x"},
        }
        path = self._write_line(json.dumps(payload))
        with self.assertRaisesRegex(TraceValidationError, "unknown field"):
            read_jsonl(path)

    def test_requires_current_schema_version(self):
        payload = {
            "type": "session_end",
            "timestamp": "2026-01-01T00:00:00Z",
            "session_id": "s",
        }
        path = self._write_line(json.dumps(payload))
        with self.assertRaisesRegex(TraceValidationError, "schema_version"):
            read_jsonl(path)

    def test_approval_request_requires_presented_action(self):
        payload = {
            "schema_version": TRACE_SCHEMA_VERSION,
            "type": "approval_requested",
            "timestamp": "2026-01-01T00:00:00Z",
            "session_id": "s",
            "action_id": "a1",
            "approval_id": "p1",
        }
        path = self._write_line(json.dumps(payload))
        with self.assertRaisesRegex(TraceValidationError, "requires action_id and action"):
            read_jsonl(path)


if __name__ == "__main__":
    unittest.main()
