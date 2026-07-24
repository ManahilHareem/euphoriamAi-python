"""Tests for coach prompt composition with Brain RAG chunks."""
import unittest

from app.services.prompt_compose import compose_coach_system


class CoachPromptComposeRagTests(unittest.TestCase):
    def test_rag_chunks_replace_full_brain_prompt(self):
        system = compose_coach_system(
            {
                "coach_brain_prompt": "Goal OS content",
                "brain_prompt": "FULL LIBRARY SHOULD NOT APPEAR",
                "brain_prompt_rag_chunks": [
                    {"title": "NE+S+R block", "chunk": "Signature-specific guidance"},
                ],
            },
            feature_flags={"brain_prompt_rag_enabled": True},
        )
        self.assertIn("BRAIN LIBRARY (retrieved", system)
        self.assertIn("Signature-specific guidance", system)
        self.assertNotIn("FULL LIBRARY SHOULD NOT APPEAR", system)
        self.assertIn("Goal OS content", system)

    def test_full_brain_prompt_when_no_rag_chunks(self):
        system = compose_coach_system(
            {
                "coach_brain_prompt": "Goal OS",
                "brain_prompt": "Full canonical library",
            },
        )
        self.assertIn("BRAIN PROMPT (Canonical library", system)
        self.assertIn("Full canonical library", system)

    def test_nathan_structural_coaching_rules_present(self):
        system = compose_coach_system(
            {
                "coach_brain_prompt": "Goal OS",
                "brain_prompt": "Library",
            },
        )
        self.assertIn("NATHAN STRUCTURAL COACHING LOOP", system)
        self.assertIn("EMOTIONAL DISCOVERY", system)
        self.assertIn("CONTRADICTION STEP", system)
        self.assertIn("TODAYS_EDGE", system)
        self.assertIn("exactly ONE resource", system)
        self.assertIn("ANTI-CHATBOT", system)
        self.assertIn("Do NOT paraphrase", system)
        self.assertIn("exactly ONE discovery question", system)
        self.assertIn("DISCOVERY PROGRESSION", system)
        self.assertIn("BREAKTHROUGH / CORE BELIEF", system)
        self.assertIn("Never return to an earlier layer", system)


if __name__ == "__main__":
    unittest.main()
