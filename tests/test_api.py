"""FastAPI /health and /audit tests (mocked pipeline, no real network or OpenAI)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.interfaces.api import app
from app.providers.llm import LlmProviderError
from app.services.analyzer import AnalyzerError
from app.services.parser import ParsingError

_MINIMAL_REPORT = {
    "summary": {
        "overall_assessment": "ok",
        "primary_conversion_goal_guess": "leads",
        "top_strengths": [],
        "top_risks": [],
    },
    "issues": [],
    "recommendations": [],
    "quick_wins": [],
    "rewrites": [],
    "language": "ru",
}


class TestHealthEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_get_health_success(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class TestAuditEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    @patch("app.interfaces.api.run_landing_audit")
    def test_post_audit_success_without_rewrite(self, mock_run: MagicMock) -> None:
        mock_run.return_value = dict(_MINIMAL_REPORT)
        response = self.client.post("/audit", json={"url": "https://example.com"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["language"], "ru")
        self.assertEqual(data["rewrites"], [])
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["rewrite_targets"], None)
        self.assertEqual(mock_run.call_args.args[0], "https://example.com")

    @patch("app.interfaces.api.run_landing_audit")
    def test_post_audit_success_with_rewrite(self, mock_run: MagicMock) -> None:
        mock_run.return_value = {
            **_MINIMAL_REPORT,
            "rewrites": [
                {
                    "block": "hero",
                    "before": "a",
                    "after": "b",
                    "why": "c",
                }
            ],
        }
        response = self.client.post(
            "/audit",
            json={"url": "https://example.com/path", "rewrite": ["hero", "cta"], "lang": "en"},
        )
        self.assertEqual(response.status_code, 200)
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["rewrite_targets"], ("hero", "cta"))
        self.assertEqual(kwargs["effective_lang"], "en")

    @patch("app.interfaces.api.run_landing_audit")
    def test_post_audit_rewrite_empty_behaves_like_no_rewrite(self, mock_run: MagicMock) -> None:
        mock_run.return_value = dict(_MINIMAL_REPORT)
        response = self.client.post(
            "/audit",
            json={"url": "https://example.com", "rewrite": []},
        )
        self.assertEqual(response.status_code, 200)
        mock_run.assert_called_once()
        self.assertIsNone(mock_run.call_args.kwargs["rewrite_targets"])

    @patch("app.interfaces.api.run_landing_audit")
    def test_parsing_error_direct_json_body(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = ParsingError("bad html")
        response = self.client.post("/audit", json={"url": "https://example.com"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"error": "parsing_failed", "message": "bad html"},
        )
        self.assertNotIn("traceback", response.text.lower())

    @patch("app.interfaces.api.run_landing_audit")
    def test_llm_provider_error_direct_json_body(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = LlmProviderError("upstream timeout")
        response = self.client.post("/audit", json={"url": "https://example.com"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json(),
            {"error": "llm_failed", "message": "upstream timeout"},
        )

    @patch("app.interfaces.api.run_landing_audit")
    def test_analyzer_error_direct_json_body(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = AnalyzerError("invalid model json")
        response = self.client.post("/audit", json={"url": "https://example.com"})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            {"error": "audit_failed", "message": "invalid model json"},
        )

    def test_missing_url_rejected(self) -> None:
        response = self.client.post("/audit", json={})
        self.assertEqual(response.status_code, 422)

    def test_invalid_lang_rejected(self) -> None:
        response = self.client.post(
            "/audit",
            json={"url": "https://example.com", "lang": "fr"},
        )
        self.assertEqual(response.status_code, 422)

    def test_invalid_rewrite_target_rejected(self) -> None:
        response = self.client.post(
            "/audit",
            json={"url": "https://example.com", "rewrite": ["hero", "footer"]},
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
