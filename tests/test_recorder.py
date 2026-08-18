import tempfile
import unittest
from pathlib import Path

from agentack import Action, Recorder
from agentack.engine import evaluate_events
from agentack.parser import read_jsonl


class RecorderTests(unittest.TestCase):
    def test_recorder_emits_checkable_secure_trace(self):
        action = Action("shell", "run", parameters={"argv": ["git", "status"]})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            with Recorder(path, "session-1") as recorder:
                recorder.propose("a1", action, intent_id="i1")
                recorder.request_approval("p1", "a1", action, intent_id="i1")
                recorder.decide("p1", "a1", "allow", intent_id="i1")
                recorder.execute("a1", action, approval_id="p1", intent_id="i1")
            events = read_jsonl(path)
            report = evaluate_events(events)
        self.assertEqual(events[-1].type, "session_end")
        self.assertEqual(report.status, "PASS")

    def test_recorder_can_record_denied_and_blocked_action(self):
        action = Action("filesystem", "delete", resource="synthetic.txt")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            with Recorder(path, "session-1") as recorder:
                recorder.propose("a1", action)
                recorder.request_approval("p1", "a1", action)
                recorder.decide("p1", "a1", "deny")
                recorder.block("a1", approval_id="p1", reason="human denied")
            report = evaluate_events(read_jsonl(path))
        self.assertEqual(report.status, "PASS")


if __name__ == "__main__":
    unittest.main()
