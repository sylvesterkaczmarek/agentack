import argparse
import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from agentack.adapters.base import AdapterStatus
from agentack.cli import build_parser, cmd_doctor, cmd_test


class CliCodexTests(unittest.TestCase):
    def test_parser_keeps_codex_status_command_for_backward_compatibility(self):
        args = build_parser().parse_args(["test", "codex"])
        self.assertEqual(args.agent, "codex")

    def test_doctor_reports_codex_detected_not_ready(self):
        claude = AdapterStatus("claude", "Claude Code", False, False)
        codex = AdapterStatus(
            "codex",
            "Codex CLI",
            True,
            False,
            executable="/fake/codex",
            version="codex-cli 0.148.0",
            detail="Codex live approval boundary is not verified.",
        )
        with mock.patch("agentack.cli.ClaudeCodeAdapter.detect", return_value=claude), mock.patch(
            "agentack.cli.CodexCLIAdapter.detect", return_value=codex
        ), mock.patch("agentack.cli._discovered_without_adapters", return_value=[]), redirect_stdout(io.StringIO()) as out:
            code = cmd_doctor(argparse.Namespace())
        text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("Codex CLI", text)
        self.assertIn("DETECTED", text)
        self.assertNotIn("READY", text)
        self.assertNotIn("agentack test codex", text)

    def test_test_codex_returns_one_concise_incomplete_diagnostic(self):
        with mock.patch("agentack.adapters.codex.shutil.which", return_value="/fake/codex"), mock.patch(
            "agentack.adapters.codex.safe_version", return_value="codex-cli 0.148.0"
        ), redirect_stdout(io.StringIO()) as out:
            code = cmd_test(argparse.Namespace(agent="codex", json_output=None, sarif=None))
        text = out.getvalue()
        self.assertEqual(code, 3)
        self.assertIn("Integration: Codex CLI", text)
        self.assertIn("Codex live approval boundary", text)
        self.assertIn("INCOMPLETE", text)
        self.assertNotIn("Approval replay", text)
        self.assertNotIn("five safe Codex", text)


if __name__ == "__main__":
    unittest.main()
