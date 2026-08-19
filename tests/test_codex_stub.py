import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from agentack.adapters.codex_stub import DeterministicCodexProvider, write_codex_probe_config


def post_json(url, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        return response.status, response.read().decode("utf-8")


class CodexStubTests(unittest.TestCase):
    def test_provider_emits_exact_shell_call_then_completion(self):
        commands = ("printf first > marker", "printf second > marker")
        with DeterministicCodexProvider(commands) as provider:
            status, first = post_json(provider.base_url + "/responses", {"input": []})
            self.assertEqual(status, 200)
            self.assertIn('"name":"shell_command"', first)
            self.assertIn(json.dumps({"command": commands[0]}, separators=(",", ":")), first)
            self.assertEqual(provider.requests_started, 1)

            status, completion = post_json(
                provider.base_url + "/responses",
                {"input": [{"type": "function_call_output", "call_id": "agentack-shell-1", "output": "ok"}]},
            )
            self.assertEqual(status, 200)
            self.assertIn('"type":"message"', completion)
            self.assertIn('"text":"done"', completion)
            self.assertEqual(provider.requests_started, 1)

            _status, second = post_json(provider.base_url + "/responses", {"input": []})
            self.assertIn(json.dumps({"command": commands[1]}, separators=(",", ":")), second)
            self.assertEqual(provider.requests_started, 2)
            self.assertIsNone(provider.error)

    def test_provider_fails_closed_on_extra_model_turn(self):
        with DeterministicCodexProvider(("echo one",)) as provider:
            post_json(provider.base_url + "/responses", {"input": []})
            with self.assertRaises(urllib.error.HTTPError) as raised:
                post_json(provider.base_url + "/responses", {"input": []})
            self.assertEqual(raised.exception.code, 409)
            self.assertIn("more model turns", provider.error or "")

    def test_probe_config_uses_only_loopback_custom_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            write_codex_probe_config(home, provider_base_url="http://127.0.0.1:43210/v1")
            config = (home / "config.toml").read_text(encoding="utf-8")
        self.assertIn('model_provider = "agentack_local"', config)
        self.assertIn('base_url = "http://127.0.0.1:43210/v1"', config)
        self.assertIn('wire_api = "responses"', config)
        self.assertIn("requires_openai_auth = false", config)
        self.assertIn('approval_policy = "untrusted"', config)
        self.assertIn('sandbox_mode = "workspace-write"', config)
        self.assertNotIn("api_key", config.lower())
        self.assertNotIn("token", config.lower())


if __name__ == "__main__":
    unittest.main()
