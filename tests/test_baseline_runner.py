"""Baseline audit orchestration (mocked pipelines, no network)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.baseline_runner import (
    CONTENT_JSON,
    CONTENT_READABLE,
    CRAFTUM_JSON,
    MANIFEST_JSON,
    VISUAL_JSON,
    run_baseline_audit,
)
from app.services.report_builder import build_human_report

_MINIMAL_LANDING = {
    "summary": {
        "overall_assessment": "ok",
        "primary_conversion_goal_guess": "leads",
        "top_strengths": ["a"],
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


def _landing_report(preset: str) -> dict:
    r = dict(_MINIMAL_LANDING)
    r["preset"] = preset
    r["report_readable"] = build_human_report(r)
    return r


class TestBaselineRunner(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = MagicMock()
        self.settings.default_lang = "ru"

    def test_baseline_creates_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def landing(url: str, **kwargs: object) -> dict:
                p = kwargs.get("preset", "general")
                assert p in ("general", "craftum")
                return _landing_report(str(p))

            def visual(url: str, **kwargs: object) -> dict:
                return {
                    "audit_type": "visual",
                    "language": "ru",
                    "overall_visual_assessment": "fine",
                    "visual_issues": [],
                }

            with patch("app.services.baseline_runner._try_git_commit", return_value=None):
                summary = run_baseline_audit(
                    "https://example.com/page",
                    settings=self.settings,
                    effective_lang="ru",
                    output_dir=root,
                    run_landing_audit_fn=landing,
                    run_visual_audit_fn=visual,
                )
            self.assertEqual(summary.status, "ok")
            self.assertTrue(summary.exit_ok)
            self.assertTrue((root / CONTENT_JSON).is_file())
            self.assertTrue((root / CONTENT_READABLE).is_file())
            self.assertTrue((root / CRAFTUM_JSON).is_file())
            self.assertTrue((root / VISUAL_JSON).is_file())
            self.assertTrue((root / MANIFEST_JSON).is_file())

            md = (root / CONTENT_READABLE).read_text(encoding="utf-8")
            self.assertIn("# Summary", md)
            self.assertIn("ok", md)

            man = json.loads((root / MANIFEST_JSON).read_text(encoding="utf-8"))
            self.assertEqual(man["status"], "ok")
            self.assertEqual(man["url"], "https://example.com/page")
            self.assertIn("content_json", man["artifacts"])
            self.assertIn("content_readable", man["artifacts"])
            self.assertIn("craftum_json", man["artifacts"])
            self.assertIn("visual_json", man["artifacts"])
            self.assertEqual(man["modes_run"], ["content", "craftum", "visual"])
            self.assertEqual(man["project_version"], "1.0")
            self.assertIn("modes_detail", man)
            for m in ("content", "craftum", "visual"):
                self.assertTrue(man["modes_detail"][m]["ok"], msg=m)

    def test_partial_failure_visual_keeps_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def landing(url: str, **kwargs: object) -> dict:
                return _landing_report(str(kwargs.get("preset", "general")))

            def visual_fail(url: str, **kwargs: object) -> dict:
                raise ValueError("visual pipeline down")

            with patch("app.services.baseline_runner._try_git_commit", return_value="abc12"):
                summary = run_baseline_audit(
                    "https://example.com/",
                    settings=self.settings,
                    effective_lang="en",
                    output_dir=root,
                    run_landing_audit_fn=landing,
                    run_visual_audit_fn=visual_fail,
                )
            self.assertEqual(summary.status, "partial")
            self.assertTrue(summary.exit_ok)
            man = json.loads((root / MANIFEST_JSON).read_text(encoding="utf-8"))
            self.assertEqual(man["status"], "partial")
            self.assertEqual(man["git_commit"], "abc12")
            self.assertTrue(any(x.get("mode") == "visual" for x in man["limitations"]))
            vis = json.loads((root / VISUAL_JSON).read_text(encoding="utf-8"))
            self.assertEqual(vis.get("baseline_status"), "error")
            self.assertIn("error_message", vis)

    def test_all_failed_status_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def boom(url: str, **kwargs: object) -> dict:
                raise RuntimeError("no")

            with patch("app.services.baseline_runner._try_git_commit", return_value=None):
                summary = run_baseline_audit(
                    "https://fail.example/",
                    settings=self.settings,
                    effective_lang="ru",
                    output_dir=root,
                    run_landing_audit_fn=boom,
                    run_visual_audit_fn=boom,
                )
            self.assertEqual(summary.status, "failed")
            self.assertFalse(summary.exit_ok)
            man = json.loads((root / MANIFEST_JSON).read_text(encoding="utf-8"))
            self.assertEqual(man["status"], "failed")
            self.assertNotIn("content_json", man["artifacts"])
            self.assertNotIn("craftum_json", man["artifacts"])
            self.assertIn("visual_json", man["artifacts"])


if __name__ == "__main__":
    unittest.main()
