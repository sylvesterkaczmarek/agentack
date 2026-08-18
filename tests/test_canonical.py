import unittest

from agentack import Action, action_hash


class CanonicalTests(unittest.TestCase):
    def test_parameter_order_does_not_change_hash(self):
        first = Action("shell", "run", parameters={"b": 2, "a": 1})
        second = Action("shell", "run", parameters={"a": 1, "b": 2})
        self.assertEqual(action_hash(first), action_hash(second))

    def test_security_relevant_change_changes_hash(self):
        first = Action("shell", "run", parameters={"argv": ["git", "status"]})
        second = Action("shell", "run", parameters={"argv": ["git", "push"]})
        self.assertNotEqual(action_hash(first), action_hash(second))


if __name__ == "__main__":
    unittest.main()
