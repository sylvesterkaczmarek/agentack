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
                recorder.request_approval("p1", "a1", intent_id="i1")
                recorder.decide("p1", "a1", "allow", approved_action=action, intent_id="i1")
                recorder.execute("a1", action, approval_id="p1", intent_id="i1")
            report = evaluate_events(read_jsonl(path))
        self.assertEqual(report.status, "PASS")


if __name__ == "__main__":
    unittest.main()
