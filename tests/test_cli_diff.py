"""CLI --diff (compare two audit JSON files)."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from app.interfaces.cli import build_parser


class TestDiffCli(unittest.TestCase):
    def test_parser_accepts_diff(self) -> None:
        args = build_parser().parse_args(["--diff", "audits/a.json", "audits/b.json"])
        self.assertEqual(args.diff, ["audits/a.json", "audits/b.json"])
        self.assertIsNone(args.url)

    @patch("app.services.diff_service.summarize_diff_with_llm", return_value="")
    def test_diff_output_structure(self, _mock_llm: object) -> None:
        from main import _print_audit_diff

        old = {
            "block_analysis": {
                "missing_blocks": ["faq"],
                "next_block": {"type": "lead_form"},
            },
            "action_roadmap": [{"action": "Add form", "step": 1}],
        }
        new = {
            "block_analysis": {
                "missing_blocks": ["faq", "testimonials"],
                "next_block": {"type": "testimonials"},
            },
            "action_roadmap": [{"action": "Add reviews", "step": 1}],
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_audit_diff(old, new)
        out = buf.getvalue()
        self.assertLess(out.index("=== CHANGE SUMMARY ==="), out.index("=== DIFF ==="))
        self.assertIn("Добавлены блоки: testimonials", out)
        self.assertIn("Добавлены действия: Add reviews", out)
        self.assertIn("Убраны действия: Add form", out)
        self.assertIn("Изменён следующий шаг: было lead_form → стало testimonials", out)
        self.assertIn("Есть улучшения, но требуется доработка", out)
        self.assertIn("=== DIFF ===", out)
        self.assertIn("* testimonials", out)
        self.assertIn("было: lead_form", out)
        self.assertIn("стало: testimonials", out)
        self.assertIn("* Add reviews", out)
        self.assertIn("- Add form", out)
        self.assertIn("=== PROGRESS ===", out)
        self.assertIn("Score: +2", out)
        self.assertIn("Есть небольшие улучшения", out)

    def test_progress_score_clamped(self) -> None:
        from app.services.diff_service import compute_progress_score as _compute_progress_score

        old = {"block_analysis": {"missing_blocks": [], "next_block": {}}, "action_roadmap": []}
        new = {
            "block_analysis": {
                "missing_blocks": [f"b{i}" for i in range(50)],
                "next_block": {"type": "x"},
            },
            "action_roadmap": [],
        }
        self.assertEqual(_compute_progress_score(old, new), -100)

    @patch("app.services.diff_service.summarize_diff_with_llm", return_value="Краткое смысловое резюме.")
    def test_change_summary_uses_llm_when_available(self, _mock_llm: object) -> None:
        from main import _print_audit_diff

        old = {
            "block_analysis": {"missing_blocks": [], "next_block": {}},
            "action_roadmap": [],
        }
        new = {
            "block_analysis": {"missing_blocks": [], "next_block": {}},
            "action_roadmap": [],
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_audit_diff(old, new)
        out = buf.getvalue()
        self.assertIn("Краткое смысловое резюме.", out)
        self.assertNotIn("Добавлены блоки:", out)


if __name__ == "__main__":
    unittest.main()
