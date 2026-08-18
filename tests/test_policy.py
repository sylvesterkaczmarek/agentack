import tempfile
import unittest
from pathlib import Path

from agentack import Action, Policy


class PolicyTests(unittest.TestCase):
    def test_default_policy_requires_shell_and_network_approval(self):
        policy = Policy()
        self.assertTrue(policy.requires_approval(Action("shell", "run")))
        self.assertTrue(policy.requires_approval(Action("network", "request")))
        self.assertFalse(policy.requires_approval(Action("filesystem", "read")))

    def test_alias_and_case_cannot_bypass_policy(self):
        policy = Policy()
        self.assertTrue(policy.requires_approval(Action("Shell", "RUN")))
        self.assertTrue(policy.requires_approval(Action("Bash", "exec")))
        self.assertTrue(policy.requires_approval(Action("terminal", "execute")))

    def test_policy_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.toml"
            path.write_text(Policy().to_toml(), encoding="utf-8")
            loaded = Policy.from_toml(path)
        self.assertEqual(loaded, Policy())


if __name__ == "__main__":
    unittest.main()
