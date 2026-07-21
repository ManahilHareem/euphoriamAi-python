"""Unit tests for certification intake phase behavior in coach response normalization."""
import unittest

from app.services.coach import _normalize_coach_response


class CoachIntakePhaseTests(unittest.TestCase):
    def test_intention_phase_blocks_green_rep(self):
        parsed = {
            "assistant_message": "What would make today worth it?",
            "green_rep": {"name": "Outreach", "steps": ["Send 1 message"], "win_condition": "Sent"},
            "writeback_hints": {"assign_new_green_rep": True},
        }
        checkin = {
            "session_phase": "intention",
            "awaiting_session_intention": True,
            "assign_green_rep": True,
        }
        result = _normalize_coach_response(parsed, {}, checkin)
        self.assertIsNone(result["green_rep"])
        self.assertNotIn("assign_new_green_rep", result["writeback_hints"])

    def test_resistance_probe_blocks_green_rep(self):
        parsed = {
            "assistant_message": "That sounds heavy. What's the smallest inch forward?",
            "green_rep": {"name": "Rep", "steps": [], "win_condition": "Done"},
            "writeback_hints": {"assign_new_green_rep": True},
        }
        checkin = {
            "session_phase": "resistance_probe",
            "assign_green_rep": True,
        }
        result = _normalize_coach_response(parsed, {}, checkin)
        self.assertIsNone(result["green_rep"])

    def test_deep_probe_blocks_green_rep(self):
        parsed = {
            "assistant_message": "Stay with that sensation.",
            "green_rep": {"name": "Rep", "steps": [], "win_condition": "Done"},
            "writeback_hints": {"assign_new_green_rep": True},
        }
        checkin = {
            "session_phase": "deep_probe",
            "assign_green_rep": True,
        }
        result = _normalize_coach_response(parsed, {}, checkin)
        self.assertIsNone(result["green_rep"])

    def test_yes_man_pattern_does_not_force_green_rep(self):
        parsed = {
            "assistant_message": "What would happen if you said no once this week?",
            "green_rep": {"name": "Rep", "steps": [], "win_condition": "Done"},
            "writeback_hints": {"assign_new_green_rep": True},
        }
        checkin = {
            "session_phase": "resistance_probe",
            "yes_man_pattern": True,
            "assign_green_rep": True,
        }
        result = _normalize_coach_response(parsed, {}, checkin)
        self.assertIsNone(result["green_rep"])

    def test_session_intention_in_writeback_hints(self):
        parsed = {
            "assistant_message": "Got it.",
            "writeback_hints": {},
        }
        checkin = {
            "session_phase": "explore",
            "session_intention": "Clarity on next step",
            "assign_green_rep": False,
        }
        result = _normalize_coach_response(parsed, {}, checkin)
        self.assertEqual(result["writeback_hints"].get("session_intention"), "Clarity on next step")


if __name__ == "__main__":
    unittest.main()
