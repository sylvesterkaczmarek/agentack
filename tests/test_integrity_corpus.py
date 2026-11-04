import unittest

from agentack.adapters.claude_analysis import analyze_capture
from integrity_cases import cases, materialize


class IntegrityCorpusTests(unittest.TestCase):
    """Each named case is an independently reported regression test."""


def _case_test(mutation, expected):
    def test(self):
        records, decisions = materialize(mutation)
        result = analyze_capture(records, decisions)
        self.assertEqual(result.status, expected, [(c.label, c.status, c.detail) for c in result.checks])

    return test


for _name, _mutation, _expected in cases():
    setattr(IntegrityCorpusTests, "test_" + _name, _case_test(_mutation, _expected))
