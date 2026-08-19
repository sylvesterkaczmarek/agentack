import argparse
import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from agentack.adapters.base import AdapterStatus, AdapterTestResult, CheckResult
from agentack.cli import build_parser, cmd_doctor, cmd_test


class CliCodexTests(unittest.TestCase):
    def test_parser_exposes_codex_live_adapter(self):
        args = build_parser().parse_args(["test", "codex"])
        self.assertEqual(args.agent, "codex")

    def test_doctor_includes_capability_checked_codex_status(self):
        claude = AdapterStatus("claude", "Claude Code", False, False)
        codex = AdapterStatus(
            "codex",
            "Codex CLI",
            True,
            True,
            executable="/fake/codex",
            version="codex-cli 1.2.3",
            detail="Structured App Server command approval lifecycle is available",
        )
        with mock.patch("agentack.cli.ClaudeCodeAdapter.detect", return_value=claude), mock.patch(
            "agentack.cli.CodexCLIAdapter.detect", return_value=codex
        ), mock.patch("agentack.cli._discovered_without_adapters", return_value=[]), redirect_stdout(io.StringIO()) as out:
            code = cmd_doctor(argparse.Namespace())
        self.assertEqual(code, 0)
        self.assertIn("Codex CLI", out.getvalue())
        self.assertIn("READY", out.getvalue())
        self.assertIn("agentack test codex", out.getvalue())

    def test_test_codex_routes_to_codex_adapter(self):
        result = AdapterTestResult(
            adapter="codex",
            display_name="Codex CLI",
            status="INCOMPLETE",
            checks=(CheckResult("Probe session", "INCOMPLETE", "fixture"),),
        )
        instance = mock.Mock()
        instance.run_test.return_value = result
        with mock.patch("agentack.cli.CodexCLIAdapter", return_value=instance), redirect_stdout(io.StringIO()) as out:
            code = cmd_test(argparse.Namespace(agent="codex", json_output=None, sarif=None))
        self.assertEqual(code, 3)
        self.assertIn("Integration: Codex CLI", out.getvalue())


if __name__ == "__main__":
    unittest.main()
