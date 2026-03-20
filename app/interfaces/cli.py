"""CLI interface for landing audit tool."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Build and return CLI argument parser."""
    parser = argparse.ArgumentParser(description="Landing page audit CLI (MVP v1)")
    parser.add_argument("--url", required=True, help="Landing page URL to audit")
    parser.add_argument("--task", required=True, help="User task / audit focus")
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
    return parser
