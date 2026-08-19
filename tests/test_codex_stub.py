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


def request_payload(*, inputs=None):
    return {
        "model": "gpt-5.5",
        "tools": [{"type": "function", "name": "shell_command"}],
        "input": [] if inputs is None else inputs,
    }


def event_payload(sse, event_type):
    lines = sse.splitlines()
    for index, line in enumerate(lines):
        if line == f"event: {event_type}" and index + 1 < len(lines) and lines[index + 1].startswith("data: "):
            return json.loads(lines[index + 1][6:])
    raise AssertionError(f"missing SSE event {event_type}")


class CodexStubTests(unittest.TestCase):
    def test_provider_emits_exact_shell_call_then_completion(self):
        commands = ("printf first > marker", "printf second > marker")
        with DeterministicCodexProvider(commands) as provider:
            status, first = post_json(provider.base_url + "/responses", request_payload())
            self.assertEqual(status, 200)
            call = event_payload(first, "response.output_item.done")["item"]
            self.assertEqual(call["name"], "shell_command")
            self.assertEqual(json.loads(call["arguments"]), {"command": commands[0], "timeout_ms": 30000})
            self.assertEqual(provider.requests_started, 1)

            status, completion = post_json(
                provider.base_url + "/responses",
                request_payload(
                    inputs=[{"type": "function_call_output", "call_id": "agentack-shell-1", "output": "ok"}]
                ),
            )
            self.assertEqual(status, 200)
            message = event_payload(completion, "response.output_item.done")["item"]
            self.assertEqual(message["type"], "message")
            self.assertEqual(message["content"], [{"type": "output_text", "text": "done"}])
            self.assertEqual(provider.requests_started, 1)

            _status, second = post_json(provider.base_url + "/responses", request_payload())
            call = event_payload(second, "response.output_item.done")["item"]
            self.assertEqual(json.loads(call["arguments"]), {"command": commands[1], "timeout_ms": 30000})
            self.assertEqual(provider.requests_started, 2)
            self.assertIsNone(provider.error)
            self.assertIn("model=gpt-5.5", provider.diagnostic)
            self.assertIn("shell_command", provider.diagnostic)

    def test_provider_fails_closed_if_shell_tool_is_not_advertised(self):
        with DeterministicCodexProvider(("echo one",)) as provider:
            payload = {"model": "gpt-5.5", "tools": [{"type": "function", "name": "other_tool"}], "input": []}
            with self.assertRaises(urllib.error.HTTPError) as raised:
                post_json(provider.base_url + "/responses", payload)
            self.assertEqual(raised.exception.code, 422)
            self.assertIn("did not advertise", provider.error or "")
            self.assertIn("other_tool", provider.diagnostic)

    def test_provider_fails_closed_on_extra_model_turn(self):
        with DeterministicCodexProvider(("echo one",)) as provider:
            post_json(provider.base_url + "/responses", request_payload())
            with self.assertRaises(urllib.error.HTTPError) as raised:
                post_json(provider.base_url + "/responses", request_payload())
            self.assertEqual(raised.exception.code, 409)
            self.assertIn("more model turns", provider.error or "")

    def test_probe_config_uses_known_model_and_loopback_custom_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            write_codex_probe_config(home, provider_base_url="http://127.0.0.1:43210/v1")
            config = (home / "config.toml").read_text(encoding="utf-8")
        self.assertIn('model = "gpt-5.5"', config)
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
