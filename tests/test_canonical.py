import unittest

from agentack import Action, action_hash, canonical_action_key


class CanonicalTests(unittest.TestCase):
    def test_parameter_order_does_not_change_hash(self):
        first = Action("shell", "run", parameters={"b": 2, "a": 1})
        second = Action("shell", "run", parameters={"a": 1, "b": 2})
        self.assertEqual(action_hash(first), action_hash(second))

    def test_security_relevant_change_changes_hash(self):
        first = Action("shell", "run", parameters={"argv": ["git", "status"]})
        second = Action("shell", "run", parameters={"argv": ["git", "push"]})
        self.assertNotEqual(action_hash(first), action_hash(second))

    def test_explicit_tool_aliases_share_identity(self):
        shell = Action("shell", "run", parameters={"argv": ["git", "status"]})
        bash = Action("Bash", "EXEC", parameters={"argv": ["git", "status"]})
        terminal = Action("terminal", "execute", parameters={"argv": ["git", "status"]})
        self.assertEqual(action_hash(shell), action_hash(bash))
        self.assertEqual(action_hash(shell), action_hash(terminal))
        self.assertEqual(canonical_action_key(bash), "shell:run")


if __name__ == "__main__":
    unittest.main()
