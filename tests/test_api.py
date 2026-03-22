"""FastAPI /health, /meta/capabilities, /audit tests (mocked pipeline where needed)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

from app.core.lang import SUPPORTED_LANGS_API_ORDER
from app.core.presets import PRESETS_API_ORDER
from app.core.rewrite_targets import REWRITE_TARGETS_API_ORDER
from app.interfaces.api import API_VERSION, app
from app.providers.llm import LlmProviderError
from app.services.analyzer import AnalyzerError
from app.services.parser import ParsingError
from app.services.report_builder import build_human_report

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
    "rewrite_texts": {"hero": "", "cta": "", "trust": ""},
    "action_roadmap": [],
    "block_analysis": {
        "blocks_detected": [],
        "missing_blocks": [],
        "next_block": {
            "type": "",
            "priority": "",
            "reason": "",
            "placement": "",
            "implementation_for_craftum": "",
            "example": "",
            "expected_impact": "",
            "confidence": 0.0,
            "why_now": "",
            "style_fit": {"color_guidance": "", "font_guidance": "", "visual_guidance": ""},
        },
    },
    "language": "ru",
    "preset": "general",
}


class TestUiDemo(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_get_root_returns_html_form(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))
        self.assertIn("Run audit", response.text)
        self.assertIn("История аудитов", response.text)

    @patch("app.interfaces.api.run_landing_audit")
    def test_ui_audit_post_shows_result(self, mock_run: MagicMock) -> None:
        rep = dict(_MINIMAL_REPORT)
        rep["report_readable"] = build_human_report(rep)
        mock_run.return_value = rep
        response = self.client.post(
            "/ui/audit",
            data={
                "url": "https://example.com",
                "task": "",
                "preset": "general",
                "lang": "ru",
                "output_mode": "readable",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Общая оценка", response.text)


class TestAuditsHistory(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_get_audits_empty_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.core.paths.get_audits_dir", return_value=Path(tmp)):
                response = self.client.get("/audits")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), [])

    def test_get_audits_parses_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "my-astro_ru_2026-03-22_12-23.json").write_text("{}", encoding="utf-8")
            with patch("app.core.paths.get_audits_dir", return_value=t):
                response = self.client.get("/audits")
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertEqual(len(data), 1)
                self.assertEqual(data[0]["filename"], "my-astro_ru_2026-03-22_12-23.json")
                self.assertEqual(data[0]["domain"], "my-astro")
                self.assertEqual(data[0]["timestamp"], "2026-03-22 12:23")

    def test_ui_open_saved_audit_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            rep = dict(_MINIMAL_REPORT)
            rep["report_readable"] = build_human_report(rep)
            (t / "my-astro_ru_2026-03-22_12-23.json").write_text(
                json.dumps(rep, ensure_ascii=False),
                encoding="utf-8",
            )
            with patch("app.core.paths.get_audits_dir", return_value=t):
                response = self.client.get(
                    "/ui/audit/file",
                    params={"filename": "my-astro_ru_2026-03-22_12-23.json", "output_mode": "readable"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("Общая оценка", response.text)

    def test_ui_open_saved_rejects_invalid_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.core.paths.get_audits_dir", return_value=Path(tmp)):
                response = self.client.get("/ui/audit/file", params={"filename": "../etc/passwd"})
                self.assertEqual(response.status_code, 404)

    @patch("app.services.diff_service.summarize_diff_with_llm", return_value="")
    def test_get_audits_diff_matches_cli_shape(self, _mock_llm: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            rep_a = {
                "language": "ru",
                "block_analysis": {"missing_blocks": ["faq"], "next_block": {"type": "hero"}},
                "action_roadmap": [{"action": "A", "step": 1}],
            }
            rep_b = {
                "language": "ru",
                "block_analysis": {"missing_blocks": ["faq", "x"], "next_block": {"type": "cta"}},
                "action_roadmap": [{"action": "B", "step": 1}],
            }
            (t / "a_ru_2026-01-01_10-00.json").write_text(
                json.dumps(rep_a, ensure_ascii=False),
                encoding="utf-8",
            )
            (t / "b_ru_2026-01-02_10-00.json").write_text(
                json.dumps(rep_b, ensure_ascii=False),
                encoding="utf-8",
            )
            with patch("app.core.paths.get_audits_dir", return_value=t):
                response = self.client.get(
                    "/audits/diff",
                    params={
                        "file1": "a_ru_2026-01-01_10-00.json",
                        "file2": "b_ru_2026-01-02_10-00.json",
                    },
                )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIn("=== CHANGE SUMMARY ===", data["change_summary"])
            self.assertIn("=== DIFF ===", data["diff"])
            self.assertIn("progress_text", data["progress"])
            # -5 (new missing) +5 (next action) -3 (roadmap removed) +5 (roadmap added) = 2
            self.assertEqual(data["progress"]["score"], 2)


class TestHealthEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_get_health_success(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class TestCapabilitiesEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_get_meta_capabilities_success(self) -> None:
        response = self.client.get("/meta/capabilities")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["supported_languages"], list(SUPPORTED_LANGS_API_ORDER))
        self.assertEqual(data["rewrite_targets"], list(REWRITE_TARGETS_API_ORDER))
        self.assertEqual(data["presets"], list(PRESETS_API_ORDER))
        self.assertTrue(data["debug_supported"])
        self.assertEqual(data["api_version"], API_VERSION)


class TestCorsMiddleware(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_cors_middleware_registered(self) -> None:
        classes = [m.cls for m in app.user_middleware]
        self.assertIn(CORSMiddleware, classes)

    def test_cors_preflight_includes_allow_origin(self) -> None:
        response = self.client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.headers.get("access-control-allow-origin"))


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
        self.assertEqual(kwargs["preset"], "general")
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
        self.assertEqual(kwargs["preset"], "general")

    @patch("app.interfaces.api.run_landing_audit")
    def test_post_audit_preset_services_passed(self, mock_run: MagicMock) -> None:
        mock_run.return_value = {**_MINIMAL_REPORT, "preset": "services"}
        response = self.client.post(
            "/audit",
            json={"url": "https://example.com", "preset": "services"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_run.call_args.kwargs["preset"], "services")

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

    def test_invalid_preset_rejected(self) -> None:
        response = self.client.post(
            "/audit",
            json={"url": "https://example.com", "preset": "unknown"},
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
