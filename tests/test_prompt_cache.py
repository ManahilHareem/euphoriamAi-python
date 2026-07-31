import unittest

from app.services.prompt_cache import resolve_prompts


class PromptCacheTests(unittest.TestCase):
    def test_stores_static_and_serves_thin_rag_overlay(self):
        key = "test-cache-key-1"
        full = {
            "coach_brain_prompt": "Goal OS",
            "brain_prompt": "FULL LIBRARY",
            "stage1_daily_coach": "Daily",
            "brain_prompt_rag_chunks": [{"title": "a", "chunk": "chunk-a"}],
        }
        first = resolve_prompts(full, key)
        self.assertEqual(first["coach_brain_prompt"], "Goal OS")
        self.assertEqual(first["brain_prompt_rag_chunks"][0]["chunk"], "chunk-a")
        # Truncated/full brain may remain for cache fallback; compose prefers RAG.
        self.assertEqual(first.get("brain_prompt"), "FULL LIBRARY")

        second = resolve_prompts(
            {"brain_prompt_rag_chunks": [{"title": "b", "chunk": "chunk-b"}]},
            key,
        )
        self.assertEqual(second["coach_brain_prompt"], "Goal OS")
        self.assertEqual(second["brain_prompt_rag_chunks"][0]["chunk"], "chunk-b")
        self.assertEqual(second.get("brain_prompt"), "FULL LIBRARY")

        miss = resolve_prompts({"brain_prompt_rag_chunks": []}, key)
        self.assertEqual(miss["coach_brain_prompt"], "Goal OS")
        self.assertNotIn("brain_prompt_rag_chunks", miss)
        self.assertEqual(miss.get("brain_prompt"), "FULL LIBRARY")

    def test_cache_miss_returns_none(self):
        self.assertIsNone(resolve_prompts(None, "missing-key-xyz"))


if __name__ == "__main__":
    unittest.main()
