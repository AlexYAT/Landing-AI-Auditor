"""Application entrypoint for landing audit CLI."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.core.config import get_settings
from app.core.lang import normalize_lang, resolve_effective_lang, used_language_fallback
from app.interfaces.cli import build_parser
from app.providers.llm import LlmProviderError
from app.services.analyzer import AnalyzerError
from app.services.assignment_formatter import format_assignment_output
from app.services.audit_pipeline import run_landing_audit
from app.services.exporter import export_report
from app.services.parser import ParsingError

logger = logging.getLogger(__name__)


def _configure_stdio_utf8() -> None:
    """Reduce UnicodeEncodeError on Windows (cp1251) when printing Russian JSON to console."""
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            try:
                reconf(encoding="utf-8", errors="replace")
            except (OSError, ValueError, AttributeError, TypeError):
                pass


def _print_assignment_rewrites(report: dict[str, Any], lang: str) -> None:
    """Print rewrite blocks after five assignment lines (order matches normalized report)."""
    items = report.get("rewrites")
    if not isinstance(items, list) or not items:
        return
    code = normalize_lang(lang)
    if code == "ru":
        b_lbl, a_lbl, w_lbl = "До:", "После:", "Почему:"
    else:
        b_lbl, a_lbl, w_lbl = "Before:", "After:", "Why:"
    print()
    for item in items:
        if not isinstance(item, dict):
            continue
        block = str(item.get("block", "")).lower()
        if block not in {"hero", "cta", "trust"}:
            continue
        hdr = f"--- Rewrite: {block} ---" if code == "en" else f"--- Перепись: {block} ---"
        print(hdr)
        print(f"{b_lbl} {item.get('before', '')}".strip())
        print(f"{a_lbl} {item.get('after', '')}".strip())
        print(f"{w_lbl} {item.get('why', '')}".strip())
        print()


def run() -> int:
    """Run CLI flow and return process exit code."""
    parser = build_parser()
    args = parser.parse_args()
    settings = get_settings()
    verbose = bool(args.verbose)
    mode: str = getattr(args, "mode", "full") or "full"
    effective_lang = resolve_effective_lang(
        cli_lang=getattr(args, "lang", None),
        env_lang=settings.default_lang,
    )
    logger.info(f"Requested lang: {args.lang!r}, effective lang: {effective_lang}")
    if used_language_fallback(getattr(args, "lang", None)):
        logger.info("Language fallback applied: unsupported code, using ru.")

    def _log(step: str) -> None:
        if verbose:
            print(f"[verbose] {step}")

    try:
        if mode == "assignment":
            logger.info("Mode: assignment")
            print("Running in assignment mode")

        _log("fetching")
        _log("parsing")
        debug_dir: Path | None = None
        if getattr(args, "debug", False):
            host = urlparse(args.url).netloc.replace(":", "_") or "unknown"
            debug_dir = Path("output") / "debug" / host
            logger.info("Debug mode: writing parser artifacts to %s", debug_dir)
        _log("analyzing")
        rewrite_targets: tuple[str, ...] | None = getattr(args, "rewrite", None)

        report = run_landing_audit(
            args.url,
            settings=settings,
            user_task=args.task,
            effective_lang=effective_lang,
            rewrite_targets=rewrite_targets,
            preset=getattr(args, "preset", None),
            debug_dir=debug_dir,
        )
        if mode == "assignment":
            for line in format_assignment_output(report, lang=effective_lang):
                print(line)
            if rewrite_targets:
                _print_assignment_rewrites(report, lang=effective_lang)
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))

        if mode == "full":
            _log("exporting")
            export_report(report=report, output_path=args.output)
            print("Audit completed successfully")
            print(f"Output saved to: {args.output}")
        else:
            print("Audit completed successfully")
        return 0
    except (ParsingError, LlmProviderError, AnalyzerError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: unexpected failure while processing audit: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    _configure_stdio_utf8()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(run())
