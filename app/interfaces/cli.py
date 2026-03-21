"""CLI interface for landing audit tool."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Build and return CLI argument parser."""
    parser = argparse.ArgumentParser(description="Landing page audit CLI (MVP v1)")
    parser.add_argument("--url", required=True, help="Landing page URL to audit")
    parser.add_argument(
        "--task",
        type=str,
        default=None,
        help="Business goal for task-aware audit (optional; omit for general CRO audit)",
    )
    parser.add_argument(
        "--mode",
        default="full",
        choices=["full", "assignment"],
        help="Run mode: full (default) or assignment",
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
    return parser
