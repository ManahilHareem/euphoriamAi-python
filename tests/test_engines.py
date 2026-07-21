"""Unit tests for Brain V2 engines."""
import unittest

from app.engines.goal_diagnosis import build_goal_diagnosis
from app.engines.green_rep import select_green_rep, validate_green_rep
from app.engines.onboarding import build_onboarding_output
from app.engines.treatment_plan_30d import generate_treatment_plan_30d


class EngineTests(unittest.TestCase):
    def test_onboarding_output(self):
        out = build_onboarding_output({"active_domain": "income", "specific_goal": "Launch"})
        self.assertTrue(out["onboarding_complete"])
        self.assertEqual(out["specific_goal"], "Launch")

    def test_goal_diagnosis(self):
        d = build_goal_diagnosis(
            {"signature_id": "X", "failure_strategy": "Delay"},
            {"specific_goal": "Goal"},
        )
        self.assertEqual(d["primary_vortex_signature"], "X")
        self.assertIn("Delay", d["failure_strategy"])

    def test_green_rep_blocked_in_intention(self):
        rep = select_green_rep(
            {"daily_rep": {"name": "Send email", "steps": []}},
            {"session_phase": "intention", "assign_green_rep": True},
        )
        self.assertIsNone(rep)

    def test_green_rep_when_assigned(self):
        rep = select_green_rep(
            {"daily_rep": {"name": "Send email", "steps": [], "win_condition": "Sent"}},
            {"session_phase": "explore", "assign_green_rep": True},
        )
        self.assertTrue(validate_green_rep(rep))

    def test_treatment_plan_default(self):
        plan = generate_treatment_plan_30d(
            domain_map={"goal_title": "Income goal", "today_visible_action": "Send pitch"},
            active_goal_context={"specific_goal": "Income goal"},
        )
        self.assertEqual(plan["current_week"], 1)
        self.assertIn("week_1", plan["weekly_focus"])
        self.assertGreaterEqual(len(plan["days"]), 1)


if __name__ == "__main__":
    unittest.main()
