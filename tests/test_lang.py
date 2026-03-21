"""Unit tests for language normalization and prompt wiring."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.core.lang import (
    DEFAULT_LANG,
    SUPPORTED_LANGS,
    get_analyzer_messages,
    normalize_lang,
    resolve_effective_lang,
    used_language_fallback,
)
from app.core.prompts import LANG_RULES, build_system_prompt, build_user_prompt
from app.services.assignment_formatter import format_assignment_output


class TestNormalizeLang(unittest.TestCase):
    """Tests for normalize_lang and fallback detection."""

    def test_default_ru_for_none(self) -> None:
        self.assertEqual(normalize_lang(None), "ru")

    def test_en_case_insensitive(self) -> None:
        self.assertEqual(normalize_lang("EN"), "en")
        self.assertEqual(normalize_lang(" En "), "en")

    def test_ru_explicit(self) -> None:
        self.assertEqual(normalize_lang("ru"), "ru")

    def test_unsupported_fallback_ru(self) -> None:
        self.assertEqual(normalize_lang("xxx"), "ru")
        self.assertEqual(normalize_lang("de"), "ru")

    def test_used_language_fallback(self) -> None:
        self.assertFalse(used_language_fallback("ru"))
        self.assertFalse(used_language_fallback("en"))
        self.assertTrue(used_language_fallback("xxx"))
        self.assertTrue(used_language_fallback("  fr  "))

    def test_supported_set(self) -> None:
        self.assertEqual(SUPPORTED_LANGS, frozenset({"ru", "en"}))
        self.assertEqual(DEFAULT_LANG, "ru")


class TestResolveEffectiveLang(unittest.TestCase):
    """resolve_effective_lang: CLI > env > ru."""

    def test_cli_over_env(self) -> None:
        self.assertEqual(resolve_effective_lang("en", "ru"), "en")
        self.assertEqual(resolve_effective_lang("ru", "en"), "ru")

    def test_env_when_cli_none(self) -> None:
        self.assertEqual(resolve_effective_lang(None, "en"), "en")
        self.assertEqual(resolve_effective_lang(None, "ru"), "ru")

    def test_invalid_env_fallback_ru(self) -> None:
        self.assertEqual(resolve_effective_lang(None, "xxx"), "ru")
        self.assertEqual(resolve_effective_lang(None, "de"), "ru")

    def test_empty_cli_uses_env(self) -> None:
        self.assertEqual(resolve_effective_lang("", "en"), "en")
        self.assertEqual(resolve_effective_lang("  ", "ru"), "ru")


class TestConfigDefaultLang(unittest.TestCase):
    """Settings.default_lang from env DEFAULT_LANG."""

    def test_default_lang_from_env_en(self) -> None:
        with patch.dict(os.environ, {"DEFAULT_LANG": "en"}, clear=False):
            from app.core.config import get_settings

            s = get_settings()
            self.assertEqual(s.default_lang, "en")

    def test_invalid_default_lang_fallback_ru(self) -> None:
        with patch.dict(os.environ, {"DEFAULT_LANG": "xxx"}, clear=False):
            from app.core.config import get_settings

            s = get_settings()
            self.assertEqual(s.default_lang, "ru")


class TestPrompts(unittest.TestCase):
    """System prompt includes language policy from LANG_RULES."""

    def test_system_prompt_ru_contains_russian_policy(self) -> None:
        text = build_system_prompt("ru")
        self.assertIn("русском", text)
        self.assertIn(LANG_RULES["ru"][:40], text)

    def test_system_prompt_en_contains_english_policy(self) -> None:
        text = build_system_prompt("en")
        self.assertIn("English", text)
        self.assertIn("strictly in English", text)

    def test_anti_mixed_language_in_rules(self) -> None:
        text = build_system_prompt("ru")
        self.assertIn("ошибка", text)
        text_en = build_system_prompt("en")
        self.assertIn("error", text_en)

    def test_user_prompt_ru_labels(self) -> None:
        body = build_user_prompt({"a": 1}, "task", lang="ru")
        self.assertIn("Задача пользователя", body)
        self.assertIn("task", body)

    def test_user_prompt_en_labels(self) -> None:
        body = build_user_prompt({"a": 1}, "task", lang="en")
        self.assertIn("User task:", body)


class TestAssignmentFormatterLang(unittest.TestCase):
    """Assignment fallbacks respect language."""

    def test_empty_report_ru_fallbacks(self) -> None:
        lines = format_assignment_output({}, lang="ru")
        self.assertEqual(len(lines), 5)
        self.assertTrue(any("ценност" in s for s in lines))

    def test_empty_report_en_fallbacks(self) -> None:
        lines = format_assignment_output({}, lang="en")
        self.assertEqual(len(lines), 5)
        self.assertTrue(any("value proposition" in s.lower() for s in lines))


class TestFullModeLanguageField(unittest.TestCase):
    """Full mode report includes language field."""

    def test_report_includes_language_after_injection(self) -> None:
        from app.core.models import AuditResult, AuditSummary

        r = AuditResult(summary=AuditSummary())
        report = r.to_dict()
        report["language"] = "en"
        self.assertIn("language", report)
        self.assertEqual(report["language"], "en")


class TestAnalyzerMessages(unittest.TestCase):
    """Localized analyzer strings exist for both languages."""

    def test_keys_present(self) -> None:
        for code in ("ru", "en"):
            m = get_analyzer_messages(code)
            self.assertIn("evidence_missing", m)
            self.assertIn("issue_prefix", m)


if __name__ == "__main__":
    unittest.main()
