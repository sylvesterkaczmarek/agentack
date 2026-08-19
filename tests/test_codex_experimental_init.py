import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agentack.adapters.codex import _ExperimentalCodexAppServer
from agentack.adapters.codex_protocol import CodexAppServer


class CodexExperimentalInitializationTests(unittest.TestCase):
    def test_initialize_opts_into_experimental_api(self):
        with tempfile.TemporaryDirectory() as directory:
            server = _ExperimentalCodexAppServer("/fake/codex", cwd=Path(directory), agentack_version="0.6.2")
            with mock.patch.object(CodexAppServer, "request", return_value={}) as parent_request:
                server.request(
                    "initialize",
                    {"clientInfo": {"name": "agentack", "title": "AgentAck", "version": "0.6.2"}},
                    timeout=10,
                )
        params = parent_request.call_args.args[1]
        self.assertEqual(params["capabilities"]["experimentalApi"], True)
        self.assertEqual(params["clientInfo"]["name"], "agentack")

    def test_non_initialize_requests_are_not_given_capabilities(self):
        with tempfile.TemporaryDirectory() as directory:
            server = _ExperimentalCodexAppServer("/fake/codex", cwd=Path(directory), agentack_version="0.6.2")
            with mock.patch.object(CodexAppServer, "request", return_value={}) as parent_request:
                server.request("turn/interrupt", {"threadId": "t", "turnId": "u"})
        params = parent_request.call_args.args[1]
        self.assertNotIn("capabilities", params)


if __name__ == "__main__":
    unittest.main()
