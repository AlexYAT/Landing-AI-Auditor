"""Tests for --rewrite CLI (hero, cta, trust), prompts, and audit rewrites ordering."""

from __future__ import annotations

import argparse
import io
import unittest
from contextlib import redirect_stderr

from app.core.models import AuditResult, AuditSummary, ContentRewrite
from app.core.prompts import LANG_RULES, build_system_prompt, build_user_prompt
from app.core.rewrite_targets import parse_rewrite_targets_arg
from app.interfaces.cli import build_parser
from app.services.analyzer import validate_and_normalize_audit_result


class TestParseRewriteTargetsArg(unittest.TestCase):
    def test_single_hero(self) -> None:
        self.assertEqual(parse_rewrite_targets_arg("hero"), ("hero",))

    def test_multiple(self) -> None:
        self.assertEqual(parse_rewrite_targets_arg("hero,cta,trust"), ("hero", "cta", "trust"))

    def test_whitespace(self) -> None:
        self.assertEqual(parse_rewrite_targets_arg(" hero , cta "), ("hero", "cta"))

    def test_dedupe_preserves_order(self) -> None:
        self.assertEqual(parse_rewrite_targets_arg("hero,cta,hero"), ("hero", "cta"))

    def test_invalid_raises(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_rewrite_targets_arg("footer")

    def test_empty_raises(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_rewrite_targets_arg("")


class TestRewriteCli(unittest.TestCase):
    def test_parse_rewrite_hero(self) -> None:
        p = build_parser()
        args = p.parse_args(["--url", "https://example.com", "--rewrite", "hero"])
        self.assertEqual(args.rewrite, ("hero",))

    def test_parse_rewrite_multiple(self) -> None:
        p = build_parser()
        args = p.parse_args(["--url", "https://example.com", "--rewrite", "hero,cta"])
        self.assertEqual(args.rewrite, ("hero", "cta"))

    def test_parse_without_rewrite(self) -> None:
        p = build_parser()
        args = p.parse_args(["--url", "https://example.com"])
        self.assertIsNone(args.rewrite)

    def test_invalid_rewrite_target_rejected(self) -> None:
        p = build_parser()
        buf = io.StringIO()
        with self.assertRaises(SystemExit), redirect_stderr(buf):
            p.parse_args(["--url", "https://example.com", "--rewrite", "footer"])


class TestRewritePrompts(unittest.TestCase):
    def test_system_prompt_without_rewrite_unchanged_addon(self) -> None:
        base = build_system_prompt("en")
        self.assertNotIn("Also REQUIRED top-level key", base)
        self.assertNotIn("Rewrite mode:", base)

    def test_system_prompt_with_hero_includes_rewrite_rules(self) -> None:
        text = build_system_prompt("en", rewrite_targets=("hero",))
        self.assertIn("Rewrite mode:", text)
        self.assertIn('"rewrites"', text)
        self.assertIn('"hero"', text)

    def test_system_prompt_includes_cta_and_trust_guides(self) -> None:
        text_en = build_system_prompt("en", rewrite_targets=("cta", "trust"))
        self.assertIn("Block \"cta\"", text_en)
        self.assertIn("Block \"trust\"", text_en)
        text_ru = build_system_prompt("ru", rewrite_targets=("cta",))
        self.assertIn("Блок \"cta\"", text_ru)

    def test_user_prompt_with_rewrite_reminder_lists_blocks(self) -> None:
        body = build_user_prompt({}, None, lang="en", rewrite_targets=("trust", "hero"))
        self.assertIn("rewrites", body.lower())
        self.assertIn("trust", body.lower())
        self.assertIn("hero", body.lower())

    def test_lang_rules_mention_all_blocks(self) -> None:
        self.assertIn("cta", LANG_RULES["en"])
        self.assertIn("trust", LANG_RULES["en"])
        self.assertIn("cta", LANG_RULES["ru"])
        self.assertIn("trust", LANG_RULES["ru"])


class TestRewriteSchema(unittest.TestCase):
    def test_audit_result_to_dict_has_rewrites(self) -> None:
        r = AuditResult(summary=AuditSummary())
        d = r.to_dict()
        self.assertIn("rewrites", d)
        self.assertEqual(d["rewrites"], [])

    def test_validate_extracts_hero_rewrite(self) -> None:
        data = {
            "summary": {
                "overall_assessment": "ok",
                "primary_conversion_goal_guess": "leads",
                "top_strengths": [],
                "top_risks": [],
            },
            "issues": [],
            "recommendations": [],
            "quick_wins": [],
            "rewrites": [
                {
                    "block": "hero",
                    "before": "weak",
                    "after": "strong",
                    "why": "clearer cta",
                }
            ],
        }
        result = validate_and_normalize_audit_result(data, lang="en", rewrite_targets=("hero",))
        self.assertEqual(len(result.rewrites), 1)
        self.assertEqual(result.rewrites[0].block, "hero")
        self.assertEqual(result.rewrites[0].after, "strong")

    def test_validate_drops_unrequested_blocks(self) -> None:
        data = {
            "summary": {
                "overall_assessment": "ok",
                "primary_conversion_goal_guess": "x",
                "top_strengths": [],
                "top_risks": [],
            },
            "issues": [],
            "recommendations": [],
            "quick_wins": [],
            "rewrites": [
                {"block": "hero", "before": "h", "after": "H", "why": "w"},
                {"block": "cta", "before": "c", "after": "C", "why": "w"},
            ],
        }
        result = validate_and_normalize_audit_result(data, lang="en", rewrite_targets=("hero",))
        self.assertEqual(len(result.rewrites), 1)
        self.assertEqual(result.rewrites[0].block, "hero")

    def test_validate_order_follows_request_not_model(self) -> None:
        data = {
            "summary": {
                "overall_assessment": "ok",
                "primary_conversion_goal_guess": "x",
                "top_strengths": [],
                "top_risks": [],
            },
            "issues": [],
            "recommendations": [],
            "quick_wins": [],
            "rewrites": [
                {"block": "hero", "before": "h", "after": "H", "why": "w"},
                {"block": "trust", "before": "t", "after": "T", "why": "w"},
            ],
        }
        result = validate_and_normalize_audit_result(
            data,
            lang="en",
            rewrite_targets=("trust", "hero"),
        )
        self.assertEqual([r.block for r in result.rewrites], ["trust", "hero"])

    def test_validate_drops_rewrites_when_not_requested(self) -> None:
        data = {
            "summary": {
                "overall_assessment": "ok",
                "primary_conversion_goal_guess": "x",
                "top_strengths": [],
                "top_risks": [],
            },
            "issues": [],
            "recommendations": [],
            "quick_wins": [],
            "rewrites": [{"block": "hero", "before": "a", "after": "b", "why": "c"}],
        }
        result = validate_and_normalize_audit_result(data, lang="en", rewrite_targets=None)
        self.assertEqual(result.rewrites, [])


class TestContentRewriteModel(unittest.TestCase):
    def test_content_rewrite_dataclass(self) -> None:
        cr = ContentRewrite(block="hero", before="x", after="y", why="z")
        self.assertEqual(cr.block, "hero")


if __name__ == "__main__":
    unittest.main()
