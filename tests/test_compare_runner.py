"""Full-audit compare workflow (mocked audits)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.baseline_runner import (
    CONTENT_JSON,
    CRAFTUM_JSON,
    MANIFEST_JSON,
    VISUAL_JSON,
)
from app.services.compare_runner import (
    COMPARISON_JSON,
    COMPARISON_READABLE,
    CURRENT_CONTENT_JSON,
    CURRENT_CRAFTUM_JSON,
    CURRENT_VISUAL_JSON,
    validate_baseline_directory,
    run_full_audit_compare,
)
from app.services.report_builder import build_human_report

_BASE_BLOCK = {
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
}


def _report(
    *,
    preset: str,
    missing_blocks: list[str],
    issues: list[dict],
    overall: str = "ok",
) -> dict:
    r = {
        "summary": {
            "overall_assessment": overall,
            "primary_conversion_goal_guess": "leads",
            "top_strengths": [],
            "top_risks": [],
        },
        "issues": issues,
        "recommendations": [],
        "quick_wins": [],
        "rewrites": [],
        "rewrite_texts": {"hero": "", "cta": "", "trust": ""},
        "action_roadmap": [],
        "block_analysis": {**_BASE_BLOCK, "missing_blocks": list(missing_blocks)},
        "language": "ru",
        "preset": preset,
    }
    r["report_readable"] = build_human_report(r)
    return r


def _write_baseline(root: Path, content: dict, craftum: dict, visual: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / CONTENT_JSON).write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    (root / CRAFTUM_JSON).write_text(json.dumps(craftum, ensure_ascii=False), encoding="utf-8")
    (root / VISUAL_JSON).write_text(json.dumps(visual, ensure_ascii=False), encoding="utf-8")
    man = {
        "url": "https://example.com/",
        "artifacts": {},
        "status": "ok",
        "modes_run": ["content", "craftum", "visual"],
    }
    (root / MANIFEST_JSON).write_text(json.dumps(man, ensure_ascii=False), encoding="utf-8")


class TestCompareRunner(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = MagicMock()
        self.settings.default_lang = "ru"

    def test_missing_baseline_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "none"
            empty.mkdir()
            out = Path(tmp) / "out"
            with patch("app.services.compare_runner._try_git_commit", return_value=None):
                summary = run_full_audit_compare(
                    "https://x.com/",
                    settings=self.settings,
                    effective_lang="ru",
                    baseline_dir=empty,
                    output_dir=out,
                    run_landing_audit_fn=MagicMock(),
                    run_visual_audit_fn=MagicMock(),
                )
            self.assertFalse(summary.exit_ok)
            cmp_json = json.loads((out / COMPARISON_JSON).read_text(encoding="utf-8"))
            self.assertEqual(cmp_json.get("status"), "failed")
            err = str(cmp_json.get("error", "")).lower()
            self.assertTrue("manifest" in err or "baseline" in err, msg=cmp_json)

    def test_compare_creates_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "baseline"
            c0 = _report(preset="general", missing_blocks=["faq"], issues=[])
            cr0 = _report(preset="craftum", missing_blocks=["faq"], issues=[])
            vis0 = {"audit_type": "visual", "overall_visual_assessment": "a", "visual_issues": []}
            _write_baseline(base, c0, cr0, vis0)

            c1 = _report(preset="general", missing_blocks=[], issues=[])
            cr1 = _report(preset="craftum", missing_blocks=[], issues=[])
            vis1 = {"audit_type": "visual", "overall_visual_assessment": "b", "visual_issues": []}

            def landing(url: str, **kwargs: object) -> dict:
                p = kwargs.get("preset", "general")
                return c1 if p == "general" else cr1

            def visual(url: str, **kwargs: object) -> dict:
                return vis1

            out = Path(tmp) / "compare"
            with patch("app.services.compare_runner._try_git_commit", return_value=None):
                summary = run_full_audit_compare(
                    "https://example.com/",
                    settings=self.settings,
                    effective_lang="ru",
                    baseline_dir=base,
                    output_dir=out,
                    run_landing_audit_fn=landing,
                    run_visual_audit_fn=visual,
                )
            self.assertTrue(summary.exit_ok)
            self.assertEqual(summary.status, "ok")
            for name in (
                CURRENT_CONTENT_JSON,
                CURRENT_CRAFTUM_JSON,
                CURRENT_VISUAL_JSON,
                COMPARISON_JSON,
                COMPARISON_READABLE,
                "manifest.json",
            ):
                self.assertTrue((out / name).is_file(), msg=name)
            md = (out / COMPARISON_READABLE).read_text(encoding="utf-8")
            self.assertIn("# Full audit comparison", md)
            self.assertIn("# What improved", md)

    def test_improvement_fewer_missing_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "b"
            c0 = _report(preset="general", missing_blocks=["faq", "pricing"], issues=[])
            cr0 = _report(preset="craftum", missing_blocks=[], issues=[])
            vis0 = {"audit_type": "visual", "visual_issues": [{"problem": "x"}]}
            _write_baseline(base, c0, cr0, vis0)
            c1 = _report(preset="general", missing_blocks=["faq"], issues=[])
            cr1 = _report(preset="craftum", missing_blocks=[], issues=[])
            vis1 = {"audit_type": "visual", "visual_issues": []}

            def landing(url: str, **kwargs: object) -> dict:
                return c1 if kwargs.get("preset") == "general" else cr1

            def visual(url: str, **kwargs: object) -> dict:
                return vis1

            out = Path(tmp) / "o"
            with patch("app.services.compare_runner._try_git_commit", return_value=None):
                run_full_audit_compare(
                    "https://example.com/",
                    settings=self.settings,
                    effective_lang="ru",
                    baseline_dir=base,
                    output_dir=out,
                    run_landing_audit_fn=landing,
                    run_visual_audit_fn=visual,
                )
            payload = json.loads((out / COMPARISON_JSON).read_text(encoding="utf-8"))
            self.assertEqual(payload["overall_change"]["direction"], "improved")
            imp = "\n".join(payload["changes"]["improved"])
            self.assertIn("missing", imp.lower())

    def test_degraded_new_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "b"
            c0 = _report(preset="general", missing_blocks=[], issues=[])
            cr0 = _report(preset="craftum", missing_blocks=[], issues=[])
            vis0 = {"audit_type": "visual", "visual_issues": []}
            _write_baseline(base, c0, cr0, vis0)
            issue = {
                "severity": "high",
                "category": "CTA",
                "title": "Weak button",
            }
            c1 = _report(preset="general", missing_blocks=[], issues=[issue])
            cr1 = _report(preset="craftum", missing_blocks=[], issues=[])

            def landing(url: str, **kwargs: object) -> dict:
                return c1 if kwargs.get("preset") == "general" else cr1

            out = Path(tmp) / "o"
            with patch("app.services.compare_runner._try_git_commit", return_value=None):
                run_full_audit_compare(
                    "https://example.com/",
                    settings=self.settings,
                    effective_lang="ru",
                    baseline_dir=base,
                    output_dir=out,
                    run_landing_audit_fn=landing,
                    run_visual_audit_fn=lambda *_a, **_k: vis0,
                )
            payload = json.loads((out / COMPARISON_JSON).read_text(encoding="utf-8"))
            self.assertGreater(len(payload["changes"]["new_issues"]), 0)
            deg = "\n".join(payload["changes"]["degraded"]).lower()
            self.assertTrue("new" in deg or "issue" in deg)

    def test_partial_current_visual_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "b"
            c0 = _report(preset="general", missing_blocks=[], issues=[])
            _write_baseline(base, c0, c0, {"audit_type": "visual", "visual_issues": []})

            c1 = _report(preset="general", missing_blocks=[], issues=[])

            def landing(url: str, **kwargs: object) -> dict:
                return c1 if kwargs.get("preset") == "general" else c0

            def vis_boom(url: str, **kwargs: object) -> dict:
                raise RuntimeError("screenshot")

            out = Path(tmp) / "o"
            with patch("app.services.compare_runner._try_git_commit", return_value=None):
                summary = run_full_audit_compare(
                    "https://example.com/",
                    settings=self.settings,
                    effective_lang="ru",
                    baseline_dir=base,
                    output_dir=out,
                    run_landing_audit_fn=landing,
                    run_visual_audit_fn=vis_boom,
                )
            self.assertTrue(summary.exit_ok)
            self.assertEqual(summary.status, "partial")
            stub = json.loads((out / CURRENT_VISUAL_JSON).read_text(encoding="utf-8"))
            self.assertEqual(stub.get("baseline_status"), "error")

    def test_validate_baseline_requires_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            with self.assertRaises(ValueError):
                validate_baseline_directory(d)


if __name__ == "__main__":
    unittest.main()
