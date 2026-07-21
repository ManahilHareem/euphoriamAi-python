"""Tests for feature flag merging."""
import unittest

from app.config import merge_feature_flags, settings


class FeatureFlagTests(unittest.TestCase):
    def test_payload_overrides_env(self):
        merged = merge_feature_flags({"coach_cert_deep_enabled": True})
        self.assertTrue(merged["coach_cert_deep_enabled"])

    def test_defaults_from_settings(self):
        merged = merge_feature_flags(None)
        self.assertIn("brain_prompt_v2_shadow", merged)
        self.assertEqual(
            merged["treatment_plan_enabled"],
            settings.treatment_plan_enabled,
        )


if __name__ == "__main__":
    unittest.main()
