import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agentack.adapters.codex import _ExperimentalCodexAppServer, _start_probe_thread
from agentack.adapters.codex_protocol import CodexAppServer


class FakeThreadServer:
    def __init__(self):
        self.calls = []

    def request(self, method, params, timeout=20):
        self.calls.append((method, params, timeout))
        return {"thread": {"id": "thread-probe"}}


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

    def test_probe_thread_is_materialized_only_inside_temporary_home(self):
        server = FakeThreadServer()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            thread_id = _start_probe_thread(server, root)
        self.assertEqual(thread_id, "thread-probe")
        method, params, _timeout = server.calls[-1]
        self.assertEqual(method, "thread/start")
        self.assertEqual(params["ephemeral"], False)
        self.assertEqual(params["sandbox"], "read-only")
        self.assertEqual(params["approvalPolicy"], "untrusted")
        self.assertEqual(params["approvalsReviewer"], "user")
        self.assertEqual(Path(params["cwd"]), root.resolve())


if __name__ == "__main__":
    unittest.main()
