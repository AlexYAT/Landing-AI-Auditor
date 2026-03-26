"""CLI interface for landing audit tool."""

from __future__ import annotations

import argparse

from app.core.presets import ALLOWED_PRESETS, DEFAULT_PRESET
from app.core.rewrite_targets import parse_rewrite_targets_arg


def build_parser() -> argparse.ArgumentParser:
    """Build and return CLI argument parser."""
    parser = argparse.ArgumentParser(description="Landing page audit CLI (MVP v1)")
    url_or_diff = parser.add_mutually_exclusive_group(required=True)
    url_or_diff.add_argument("--url", default=None, help="Landing page URL to audit")
    url_or_diff.add_argument(
        "--diff",
        nargs=2,
        metavar=("FILE1", "FILE2"),
        help="Compare two saved audit JSON files (no live audit)",
    )
    parser.add_argument(
        "--task",
        type=str,
        default=None,
        help="Business goal for task-aware audit (optional; omit for general CRO audit)",
    )
    parser.add_argument(
        "--mode",
        default="full",
        choices=["full", "assignment", "visual"],
        help="Run mode: full (default), assignment, or visual-only audit (no CRO/content pipeline)",
    )
    parser.add_argument(
        "--output",
        default="output/report.json",
        help="Output JSON path (default: output/report.json)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logs for pipeline steps",
    )
    parser.add_argument(
        "--lang",
        type=str,
        default=None,
        help="Response language: ru or en (default from DEFAULT_LANG env, else ru)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save raw.html and extracted_text.txt under output/debug/<host> and log encoding/text preview",
    )
    parser.add_argument(
        "--rewrite",
        type=parse_rewrite_targets_arg,
        default=None,
        metavar="TARGETS",
        help='Comma-separated content rewrites: hero, cta, trust (e.g. "hero" or "hero,cta,trust")',
    )
    parser.add_argument(
        "--preset",
        default=DEFAULT_PRESET,
        choices=sorted(ALLOWED_PRESETS),
        help="Landing type preset for analysis focus (default: general)",
    )
    parser.add_argument(
        "--output-format",
        dest="output_format",
        choices=["json", "readable"],
        default="json",
        help="Console output in full mode: json (default) or human-readable report",
    )
    parser.add_argument(
        "--save-report",
        dest="save_report",
        default=None,
        metavar="PATH",
        help="Save analysis to PATH (JSON or markdown-like text per --output-format)",
    )
    parser.add_argument(
        "--save-run",
        dest="save_run",
        choices=["baseline", "improved"],
        default=None,
        help="Save full JSON + readable .md under audits/baseline/ or audits/improved/ (single-audit run only)",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Run baseline snapshot: content + craftum + visual into <AUDITS_DIR>/baseline (requires --url; no compare yet)",
    )
    parser.add_argument(
        "--baseline-dir",
        dest="baseline_dir",
        default=None,
        metavar="PATH",
        help="Baseline output directory (default: <AUDITS_DIR>/baseline; relative paths are under project root)",
    )
    parser.add_argument(
        "--full-audit",
        "--compare-baseline",
        dest="full_audit",
        action="store_true",
        help="Compare current site to saved baseline: refresh audits + comparison artifacts (alias: --compare-baseline)",
    )
    parser.add_argument(
        "--compare-dir",
        dest="compare_dir",
        default=None,
        metavar="PATH",
        help="Compare/full-audit output directory (default: <AUDITS_DIR>/compare)",
    )
    return parser
