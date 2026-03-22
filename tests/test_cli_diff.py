"""CLI --diff (compare two audit JSON files)."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from app.interfaces.cli import build_parser


class TestDiffCli(unittest.TestCase):
    def test_parser_accepts_diff(self) -> None:
        args = build_parser().parse_args(["--diff", "audits/a.json", "audits/b.json"])
        self.assertEqual(args.diff, ["audits/a.json", "audits/b.json"])
        self.assertIsNone(args.url)

    def test_diff_output_structure(self) -> None:
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
        self.assertIn("=== DIFF ===", out)
        self.assertIn("* testimonials", out)
        self.assertIn("было: lead_form", out)
        self.assertIn("стало: testimonials", out)
        self.assertIn("* Add reviews", out)
        self.assertIn("- Add form", out)


if __name__ == "__main__":
    unittest.main()
