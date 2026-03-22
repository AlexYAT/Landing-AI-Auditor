"""Human-readable report builder."""

from __future__ import annotations

import unittest

from app.services.report_builder import build_human_report, format_summary_readable


class TestBuildHumanReport(unittest.TestCase):
    def test_summary_readable_not_json(self) -> None:
        rep = {
            "language": "ru",
            "summary": {
                "overall_assessment": "Ок",
                "primary_conversion_goal_guess": "Лиды",
                "top_strengths": ["А", "Б"],
                "top_risks": ["В"],
            },
        }
        rr = build_human_report(rep)
        text = format_summary_readable(rr.get("summary"), rep.get("language"))
        self.assertNotIn("{", text)
        self.assertIn("Общая оценка:", text)
        self.assertIn("Ок", text)
        self.assertIn("* А", text)

    def test_format_summary_readable_en(self) -> None:
        s = format_summary_readable(
            {
                "overall_assessment": "Good",
                "primary_conversion_goal_guess": "Leads",
                "top_strengths": ["X"],
                "top_risks": [],
            },
            "en",
        )
        self.assertIn("Overall assessment:", s)
        self.assertIn("Good", s)

    def test_rewrite_texts_readable_defaults_when_missing(self) -> None:
        rr = build_human_report({})
        self.assertEqual(
            rr["rewrite_texts_readable"],
            {"hero": "", "cta": "", "trust": ""},
        )
        self.assertEqual(rr["next_action_readable"], "")
        bar = rr["block_analysis_readable"]
        self.assertEqual(bar["missing_blocks"], [])
        self.assertEqual(
            bar["next_action"],
            {"type": "", "reason": "", "placement": "", "example": ""},
        )

    def test_rewrite_texts_readable_from_report(self) -> None:
        rr = build_human_report(
            {
                "rewrite_texts": {
                    "hero": "  H  ",
                    "cta": "C",
                    "trust": "",
                },
            }
        )
        self.assertEqual(
            rr["rewrite_texts_readable"],
            {"hero": "H", "cta": "C", "trust": ""},
        )

    def test_rewrite_texts_readable_ignores_non_dict(self) -> None:
        rr = build_human_report({"rewrite_texts": "bad"})
        self.assertEqual(
            rr["rewrite_texts_readable"],
            {"hero": "", "cta": "", "trust": ""},
        )


class TestReadableMarkdownRewrites(unittest.TestCase):
    def test_save_report_markdown_includes_rewrites_when_nonempty(self) -> None:
        from main import _build_readable_markdown

        md = _build_readable_markdown(
            {
                "summary": {},
                "issues": [],
                "recommendations": [],
                "quick_wins": [],
                "rewrite_texts": {"hero": "H1", "cta": "C1", "trust": ""},
            }
        )
        self.assertIn("# Rewrites", md)
        self.assertIn("## Hero", md)
        self.assertIn("## CTA", md)
        self.assertIn("## Trust", md)
        self.assertIn("H1", md)
        self.assertIn("C1", md)

    def test_save_report_markdown_omits_rewrites_when_all_empty(self) -> None:
        from main import _build_readable_markdown

        md = _build_readable_markdown(
            {
                "summary": {},
                "issues": [],
                "recommendations": [],
                "quick_wins": [],
                "rewrite_texts": {"hero": "", "cta": "", "trust": ""},
            }
        )
        self.assertNotIn("# Rewrites", md)


if __name__ == "__main__":
    unittest.main()
