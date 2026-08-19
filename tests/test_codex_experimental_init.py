import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agentack.adapters.codex import (
    _CODEX_EXEC_SERVER_URL,
    _CODEX_NOISE_ENV_VARS,
    _ExperimentalCodexAppServer,
    _start_probe_thread,
    _temporary_codex_environment,
)
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

    def test_temporary_environment_selects_native_exec_url_and_clears_noise(self):
        keys = ("CODEX_HOME", _CODEX_EXEC_SERVER_URL, *_CODEX_NOISE_ENV_VARS)
        previous = {key: os.environ.get(key) for key in keys}
        try:
            for key in _CODEX_NOISE_ENV_VARS:
                os.environ[key] = "host-value"
            with tempfile.TemporaryDirectory() as directory:
                with _temporary_codex_environment(Path(directory), "ws://127.0.0.1:43210"):
                    self.assertEqual(os.environ.get("CODEX_HOME"), directory)
                    self.assertEqual(os.environ.get(_CODEX_EXEC_SERVER_URL), "ws://127.0.0.1:43210")
                    for key in _CODEX_NOISE_ENV_VARS:
                        self.assertNotIn(key, os.environ)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_probe_thread_uses_default_environment_without_explicit_selection(self):
        server = FakeThreadServer()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            thread_id = _start_probe_thread(server, root)
            resolved_root = str(root.resolve())
        self.assertEqual(thread_id, "thread-probe")
        method, params, _timeout = server.calls[-1]
        self.assertEqual(method, "thread/start")
        self.assertEqual(params["ephemeral"], False)
        self.assertEqual(params["sandbox"], "read-only")
        self.assertEqual(params["approvalPolicy"], "untrusted")
        self.assertEqual(params["approvalsReviewer"], "user")
        self.assertEqual(params["cwd"], resolved_root)
        self.assertNotIn("environments", params)


if __name__ == "__main__":
    unittest.main()
