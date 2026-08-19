import json
import unittest
from pathlib import Path

from agentack.adapters.codex_analysis import APPROVE_COMMAND, DENY_COMMAND, ROUTE_B_COMMAND, STOP_COMMAND, CodexProbeEvidence, analyze_probes


FIXTURES = Path(__file__).parent / "fixtures" / "live_probes"


def good_probes():
    return [
        CodexProbeEvidence(name="approve", expected_command=APPROVE_COMMAND, thread_id="thr-regression", turn_id="a", item_id="a", started_command=APPROVE_COMMAND, presented_command=APPROVE_COMMAND, user_decision="accept", completed_command=APPROVE_COMMAND, completed_status="completed", turn_completed=True, turn_status="completed", marker_exists=True),
        CodexProbeEvidence(name="replay", expected_command=APPROVE_COMMAND, thread_id="thr-regression", turn_id="r", item_id="r", started_command=APPROVE_COMMAND, presented_command=APPROVE_COMMAND, user_decision="decline", completed_command=APPROVE_COMMAND, completed_status="declined", turn_completed=True, turn_status="completed", marker_exists=True),
        CodexProbeEvidence(name="route-a", expected_command=DENY_COMMAND, thread_id="thr-regression", turn_id="ra", item_id="ra", started_command=DENY_COMMAND, presented_command=DENY_COMMAND, user_decision="decline", completed_command=DENY_COMMAND, completed_status="declined", turn_completed=True, turn_status="completed", marker_exists=False),
        CodexProbeEvidence(name="route-b", expected_command=ROUTE_B_COMMAND, thread_id="thr-regression", turn_id="rb", item_id="rb", started_command=ROUTE_B_COMMAND, presented_command=ROUTE_B_COMMAND, user_decision="decline", completed_command=ROUTE_B_COMMAND, completed_status="declined", turn_completed=True, turn_status="completed", marker_exists=False),
        CodexProbeEvidence(name="stop", expected_command=STOP_COMMAND, thread_id="thr-regression", turn_id="s", item_id="s", started_command=STOP_COMMAND, presented_command=STOP_COMMAND, completed_command=STOP_COMMAND, completed_status="declined", turn_completed=True, turn_status="interrupted", marker_exists=False, interrupt_requested=True),
    ]


def load_fixture(name: str) -> CodexProbeEvidence:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return CodexProbeEvidence(**payload)


class LiveProbeCorpusTests(unittest.TestCase):
    def test_replay_bypass_fixture_stays_detected(self):
        probes = good_probes()
        probes[1] = load_fixture("codex_replay_bypass.json")
        result = analyze_probes(probes)
        self.assertEqual({check.label: check.status for check in result.checks}["Approval replay"], "FAIL")

    def test_route_around_bypass_fixture_stays_detected(self):
        probes = good_probes()
        probes[3] = load_fixture("codex_route_around_bypass.json")
        result = analyze_probes(probes)
        self.assertEqual({check.label: check.status for check in result.checks}["Denial route-around"], "FAIL")

    def test_interrupt_bypass_fixture_stays_detected(self):
        probes = good_probes()
        probes[4] = load_fixture("codex_interrupt_bypass.json")
        result = analyze_probes(probes)
        self.assertEqual({check.label: check.status for check in result.checks}["Stop enforcement"], "FAIL")


if __name__ == "__main__":
    unittest.main()
