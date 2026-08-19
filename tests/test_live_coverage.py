import io
import unittest
from contextlib import redirect_stdout

from agentack.cli import build_parser, cmd_coverage
from agentack.coverage import LIVE_COVERAGE, render_coverage


class LiveCoverageTests(unittest.TestCase):
    def test_every_ack_rule_has_one_truthful_coverage_row(self):
        ids = [row.rule_id for row in LIVE_COVERAGE]
        self.assertEqual(ids, [f"ACK00{i}" for i in range(1, 10)])

    def test_expected_live_boundaries_are_explicit(self):
        rows = {row.rule_id: row for row in LIVE_COVERAGE}
        self.assertEqual(rows["ACK004"].claude, "TESTED")
        self.assertEqual(rows["ACK004"].codex, "TESTED")
        self.assertEqual(rows["ACK007"].claude, "TESTED")
        self.assertEqual(rows["ACK007"].codex, "TESTED")
        self.assertEqual(rows["ACK008"].claude, "SKIP")
        self.assertEqual(rows["ACK008"].codex, "TESTED")
        self.assertEqual(rows["ACK005"].claude, "TRACE")

    def test_coverage_command_is_public_and_stable(self):
        parser = build_parser()
        args = parser.parse_args(["coverage"])
        with redirect_stdout(io.StringIO()) as stdout:
            code = cmd_coverage(args)
        self.assertEqual(code, 0)
        text = stdout.getvalue()
        self.assertIn("AgentAck live coverage", text)
        self.assertIn("ACK009", text)
        self.assertEqual(text.strip(), render_coverage())


if __name__ == "__main__":
    unittest.main()
