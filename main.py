"""Application entrypoint for landing audit CLI."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from urllib.parse import urlparse

from app.core.config import get_settings
from app.core.lang import resolve_effective_lang, used_language_fallback
from app.interfaces.cli import build_parser
from app.providers.llm import LlmProviderError, OpenAiAuditProvider
from app.services.analyzer import AnalyzerError, analyze_landing
from app.services.assignment_formatter import format_assignment_output
from app.services.exporter import export_report
from app.services.parser import ParsingError, parse_landing

logger = logging.getLogger(__name__)


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
        parsed_landing = parse_landing(
            url=args.url,
            settings=settings,
            debug_dir=debug_dir,
        )
        _log("analyzing")
        provider = OpenAiAuditProvider(settings=settings)
        audit_result = analyze_landing(
            parsed_landing=parsed_landing.to_dict(),
            user_task=args.task,
            provider=provider,
            lang=effective_lang,
        )
        report = audit_result.to_dict()
        report["language"] = effective_lang
        if mode == "assignment":
            for line in format_assignment_output(report, lang=effective_lang):
                print(line)
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
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(run())
