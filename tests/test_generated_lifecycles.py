"""Deterministic generated checks with valid controls; no model or shell action."""

from __future__ import annotations

from dataclasses import replace
from itertools import permutations
import random
import unittest

from agentack import Action, evaluate_events
from agentack.demo import demo_events


class GeneratedLifecycleTests(unittest.TestCase):
    def test_all_five_event_permutations_have_one_valid_order(self):
        baseline = demo_events("secure")
        self.assertEqual(len(baseline), 5)
        for order in permutations(range(5)):
            with self.subTest(order=order):
                report = evaluate_events([baseline[i] for i in order])
                self.assertEqual(report.status == "PASS", order == tuple(range(5)))

    def test_seeded_action_substitutions_and_valid_controls(self):
        generator = random.Random(20261104)
        for number in range(100):
            parameters = {
                "argv": ["synthetic-command", str(generator.randrange(1_000_000))],
                "context_id": f"context-{number}",
            }
            action = Action("shell", "run", resource="synthetic", parameters=parameters)
            events = [replace(e, action=action) if e.action is not None else e for e in demo_events("secure")]
            with self.subTest(case=number, kind="valid"):
                self.assertEqual(evaluate_events(events).status, "PASS")
            changed = replace(action, parameters={**parameters, "context_id": f"changed-{number}"})
            bad = [replace(e, action=changed) if e.type == "action_executed" else e for e in events]
            with self.subTest(case=number, kind="substituted"):
                self.assertEqual(evaluate_events(bad).status, "FAIL")

    def test_dropping_any_required_event_never_passes(self):
        events = demo_events("secure")
        for index in range(len(events)):
            with self.subTest(index=index):
                self.assertNotEqual(evaluate_events(events[:index] + events[index + 1 :]).status, "PASS")
