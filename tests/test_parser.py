import tempfile
import unittest
from pathlib import Path

from agentack.demo import demo_events
from agentack.models import TraceValidationError
from agentack.parser import read_jsonl, write_jsonl


class ParserTests(unittest.TestCase):
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
        changed[-1] = type(events[-1])(
            type=events[-1].type,
            timestamp=events[-1].timestamp,
            session_id="another-session",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            write_jsonl(path, changed)
            with self.assertRaises(TraceValidationError):
                read_jsonl(path)

    def test_rejects_invalid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            path.write_text("{not json}\n", encoding="utf-8")
            with self.assertRaises(TraceValidationError):
                read_jsonl(path)


if __name__ == "__main__":
    unittest.main()
