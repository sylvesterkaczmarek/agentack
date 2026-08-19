import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agentack.adapters.codex import (
    PROBE_ENVIRONMENT_ID,
    _ExperimentalCodexAppServer,
    _register_local_environment,
    _start_probe_thread,
    _wait_environment_ready,
)
from agentack.adapters.codex_protocol import CodexAppServer, CodexAppServerError


class FakeThreadServer:
    def __init__(self, status_results=None):
        self.calls = []
        self.status_results = list(status_results or [])

    def request(self, method, params, timeout=20):
        self.calls.append((method, params, timeout))
        if method == "thread/start":
            return {"thread": {"id": "thread-probe"}}
        if method == "environment/status":
            if not self.status_results:
                return {"status": "ready", "error": None}
            return self.status_results.pop(0)
        return {}


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

    def test_local_exec_server_is_registered_as_probe_environment(self):
        server = FakeThreadServer()
        environment_id = _register_local_environment(server, "ws://127.0.0.1:43210")
        self.assertEqual(environment_id, PROBE_ENVIRONMENT_ID)
        method, params, timeout = server.calls[-1]
        self.assertEqual(method, "environment/add")
        self.assertEqual(params["environmentId"], PROBE_ENVIRONMENT_ID)
        self.assertEqual(params["execServerUrl"], "ws://127.0.0.1:43210")
        self.assertEqual(params["connectTimeoutMs"], 5000)
        self.assertEqual(timeout, 10)

    def test_environment_readiness_waits_through_pending(self):
        server = FakeThreadServer(
            [
                {"status": "pending", "error": None},
                {"status": "pending", "error": None},
                {"status": "ready", "error": None},
            ]
        )
        with mock.patch("agentack.adapters.codex.time.sleep", return_value=None):
            _wait_environment_ready(server, PROBE_ENVIRONMENT_ID, timeout=1)
        status_calls = [call for call in server.calls if call[0] == "environment/status"]
        self.assertEqual(len(status_calls), 3)
        self.assertTrue(all(call[1] == {"environmentId": PROBE_ENVIRONMENT_ID} for call in status_calls))

    def test_environment_readiness_fails_closed_on_disconnect(self):
        server = FakeThreadServer([{"status": "disconnected", "error": "connection closed"}])
        with self.assertRaisesRegex(CodexAppServerError, "disconnected: connection closed"):
            _wait_environment_ready(server, PROBE_ENVIRONMENT_ID, timeout=1)

    def test_probe_thread_selects_registered_environment(self):
        server = FakeThreadServer()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            thread_id = _start_probe_thread(server, root, environment_id=PROBE_ENVIRONMENT_ID)
            resolved_root = str(root.resolve())
        self.assertEqual(thread_id, "thread-probe")
        method, params, _timeout = server.calls[-1]
        self.assertEqual(method, "thread/start")
        self.assertEqual(params["ephemeral"], False)
        self.assertEqual(params["sandbox"], "read-only")
        self.assertEqual(params["approvalPolicy"], "untrusted")
        self.assertEqual(params["approvalsReviewer"], "user")
        self.assertEqual(params["cwd"], resolved_root)
        self.assertEqual(
            params["environments"],
            [{"environmentId": PROBE_ENVIRONMENT_ID, "cwd": resolved_root}],
        )


if __name__ == "__main__":
    unittest.main()
