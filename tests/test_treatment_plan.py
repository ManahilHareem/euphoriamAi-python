"""Treatment plan API tests."""
import unittest

from fastapi.testclient import TestClient

from app.main import app


class TreatmentPlanRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_generate_forbidden_when_flag_off(self):
        res = self.client.post(
            "/v1/treatment-plan/generate",
            json={"domain_map": {"goal_title": "Test"}},
        )
        self.assertEqual(res.status_code, 403)


if __name__ == "__main__":
    unittest.main()
