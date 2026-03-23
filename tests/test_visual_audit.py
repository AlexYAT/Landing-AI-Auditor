"""Visual audit mode: models, normalization, readable output, pipeline shape."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

try:
    import playwright  # noqa: F401
except ImportError:
    playwright = None

from app.services.analyzer import MAX_VISUAL_ISSUES, validate_and_normalize_visual_audit
from app.services.audit_pipeline import run_visual_audit
from app.services.report_builder import format_visual_audit_readable
from app.core.models import VisualAuditResult, VisualIssue
from app.core.visual_prompts import build_visual_system_prompt


class TestVisualNormalization(unittest.TestCase):
    def test_invalid_severity_normalized(self) -> None:
        data = {
            "overall_visual_assessment": "ok",
            "visual_issues": [
                {
                    "problem": "p",
                    "why_it_matters": "w",
                    "recommendation": "r",
                    "severity": "bogus",
                }
            ],
        }
        r = validate_and_normalize_visual_audit(data, lang="en")
        self.assertEqual(r.visual_issues[0].severity, "medium")

    def test_severity_critical_maps_to_high(self) -> None:
        data = {
            "overall_visual_assessment": "ok",
            "visual_issues": [
                {
                    "problem": "p",
                    "why_it_matters": "w",
                    "recommendation": "r",
                    "severity": "critical",
                }
            ],
        }
        r = validate_and_normalize_visual_audit(data, lang="en")
        self.assertEqual(r.visual_issues[0].severity, "high")

    def test_severity_case_and_spaces(self) -> None:
        data = {
            "overall_visual_assessment": "ok",
            "visual_issues": [
                {
                    "problem": "a",
                    "why_it_matters": "w",
                    "recommendation": "r",
                    "severity": "  H I G H  ",
                },
                {
                    "problem": "b",
                    "why_it_matters": "w",
                    "recommendation": "r",
                    "severity": "low",
                },
            ],
        }
        r = validate_and_normalize_visual_audit(data, lang="en")
        self.assertEqual(r.visual_issues[0].severity, "high")
        self.assertEqual(r.visual_issues[1].severity, "low")

    def test_trim_to_max_five_issues(self) -> None:
        raw = [
            {
                "problem": f"p{i}",
                "why_it_matters": "w",
                "recommendation": "r",
                "severity": "medium",
            }
            for i in range(7)
        ]
        r = validate_and_normalize_visual_audit(
            {"overall_visual_assessment": "ok", "visual_issues": raw},
            lang="en",
        )
        self.assertEqual(len(r.visual_issues), MAX_VISUAL_ISSUES)
        self.assertEqual([x.problem for x in r.visual_issues], [f"p{i}" for i in range(5)])

    def test_sort_high_before_medium_before_low(self) -> None:
        data = {
            "overall_visual_assessment": "ok",
            "visual_issues": [
                {"problem": "low1", "why_it_matters": "w", "recommendation": "r", "severity": "low"},
                {"problem": "high1", "why_it_matters": "w", "recommendation": "r", "severity": "high"},
                {"problem": "med1", "why_it_matters": "w", "recommendation": "r", "severity": "medium"},
            ],
        }
        r = validate_and_normalize_visual_audit(data, lang="en")
        self.assertEqual([x.problem for x in r.visual_issues], ["high1", "med1", "low1"])

    def test_missing_visual_issues_empty_list(self) -> None:
        r = validate_and_normalize_visual_audit({"overall_visual_assessment": "x"}, lang="ru")
        self.assertEqual(r.visual_issues, [])


class TestVisualModeStructure(unittest.TestCase):
    def test_visual_mode_returns_visual_structure(self) -> None:
        result = VisualAuditResult(
            overall_visual_assessment="Balanced layout",
            visual_issues=[
                VisualIssue(
                    problem="CTA blends with body",
                    why_it_matters="Users may miss the action",
                    recommendation="Emphasize the primary action in structure",
                    severity="high",
                )
            ],
        )
        d = result.to_dict()
        self.assertEqual(d["audit_type"], "visual")
        self.assertEqual(len(d["visual_issues"]), 1)
        self.assertEqual(d["visual_issues"][0]["severity"], "high")

    @patch("app.services.audit_pipeline.capture_page_screenshot", return_value=None)
    @patch("app.services.audit_pipeline.OpenAiAuditProvider")
    @patch("app.services.audit_pipeline.analyze_visual_landing")
    @patch("app.services.audit_pipeline.parse_landing")
    def test_visual_mode_does_not_include_content_fields(
        self,
        mock_parse: MagicMock,
        mock_analyze: MagicMock,
        mock_provider_cls: MagicMock,
        _mock_cap: MagicMock,
    ) -> None:
        mock_provider_cls.return_value = MagicMock()
        mock_parse.return_value.to_dict.return_value = {"title": "T"}
        mock_analyze.return_value = VisualAuditResult(
            overall_visual_assessment="ok",
            visual_issues=[],
        )
        from app.core.config import get_settings

        report = run_visual_audit(
            "https://example.com",
            settings=get_settings(),
            effective_lang="ru",
        )
        self.assertEqual(report.get("audit_type"), "visual")
        self.assertIn("overall_visual_assessment", report)
        self.assertIn("visual_issues", report)
        self.assertIn("language", report)
        self.assertNotIn("summary", report)
        self.assertNotIn("recommendations", report)
        self.assertNotIn("issues", report)
        self.assertNotIn("craftum_block_plan", report)
        self.assertIn("visual_screenshot_used", report)
        self.assertFalse(report["visual_screenshot_used"])


class TestVisualScreenshotPipeline(unittest.TestCase):
    @patch("app.services.audit_pipeline.analyze_visual_landing")
    @patch("app.services.audit_pipeline.capture_page_screenshot")
    @patch("app.services.audit_pipeline.parse_landing")
    def test_visual_with_image_passes_path_to_analyzer(
        self,
        mock_parse: MagicMock,
        mock_cap: MagicMock,
        mock_analyze: MagicMock,
    ) -> None:
        mock_parse.return_value.to_dict.return_value = {"title": "T"}
        mock_cap.return_value = "/tmp/fake_visual.png"
        mock_analyze.return_value = VisualAuditResult(overall_visual_assessment="ok", visual_issues=[])
        from app.core.config import get_settings

        run_visual_audit("https://example.com", settings=get_settings(), effective_lang="en")
        mock_analyze.assert_called_once()
        self.assertEqual(mock_analyze.call_args.kwargs.get("image_path"), "/tmp/fake_visual.png")

    @patch("app.services.audit_pipeline.analyze_visual_landing")
    @patch("app.services.audit_pipeline.capture_page_screenshot", return_value=None)
    @patch("app.services.audit_pipeline.parse_landing")
    def test_visual_fallback_without_image(
        self,
        mock_parse: MagicMock,
        _mock_cap: MagicMock,
        mock_analyze: MagicMock,
    ) -> None:
        mock_parse.return_value.to_dict.return_value = {"title": "T"}
        mock_analyze.return_value = VisualAuditResult(overall_visual_assessment="ok", visual_issues=[])
        from app.core.config import get_settings

        report = run_visual_audit("https://example.com", settings=get_settings(), effective_lang="ru")
        self.assertIsNone(mock_analyze.call_args.kwargs.get("image_path"))
        self.assertFalse(report["visual_screenshot_used"])

class TestScreenshotCaptureGraceful(unittest.TestCase):
    @unittest.skipIf(playwright is None, "playwright not installed")
    @patch("playwright.sync_api.sync_playwright", side_effect=RuntimeError("browser failed"))
    def test_capture_returns_none_without_raising(self, _mock_sync: MagicMock) -> None:
        """Playwright/runtime errors must not propagate from ``capture_page_screenshot``."""
        from app.services.screenshot_capture import capture_page_screenshot

        self.assertIsNone(capture_page_screenshot("https://example.com"))


class TestVisualPromptPolish(unittest.TestCase):
    def test_prompt_mentions_max_five_issues(self) -> None:
        ru = build_visual_system_prompt("ru")
        en = build_visual_system_prompt("en")
        self.assertIn("5", ru)
        self.assertIn("5", en)
        self.assertIn("не более", ru)
        self.assertIn("at most", en.lower())

    def test_prompt_multimodal_when_has_image(self) -> None:
        ru = build_visual_system_prompt("ru", has_image=True)
        en = build_visual_system_prompt("en", has_image=True)
        self.assertIn("Мультимодальный", ru)
        self.assertIn("скриншот", ru.lower())
        self.assertIn("Multimodal", en)
        self.assertIn("screenshot", en.lower())


class TestReadableVisualOutput(unittest.TestCase):
    def test_readable_follows_sorted_severity_order(self) -> None:
        data = {
            "overall_visual_assessment": "ok",
            "visual_issues": [
                {"problem": "shown_last", "why_it_matters": "w", "recommendation": "r", "severity": "low"},
                {"problem": "shown_first", "why_it_matters": "w", "recommendation": "r", "severity": "high"},
            ],
        }
        r = validate_and_normalize_visual_audit(data, lang="en")
        rep = {**r.to_dict(), "language": "en"}
        text = format_visual_audit_readable(rep, "en")
        self.assertLess(text.find("shown_first"), text.find("shown_last"))

    def test_readable_visual_output(self) -> None:
        report = {
            "audit_type": "visual",
            "language": "ru",
            "overall_visual_assessment": "Страница перегружена",
            "visual_issues": [
                {
                    "problem": "Нет акцента на CTA",
                    "why_it_matters": "Снижается заметность действия",
                    "recommendation": "Выделить главный призыв",
                    "severity": "medium",
                }
            ],
        }
        text = format_visual_audit_readable(report, "ru")
        self.assertIn("=== VISUAL AUDIT ===", text)
        self.assertIn("Общая оценка", text)
        self.assertIn("Проблемы", text)
        self.assertIn("Проблема:", text)
        self.assertIn("Почему важно:", text)
        self.assertIn("Рекомендация:", text)
        self.assertIn("Страница перегружена", text)


if __name__ == "__main__":
    unittest.main()
