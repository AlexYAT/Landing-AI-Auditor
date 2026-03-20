"""Application entrypoint for landing audit CLI."""

from __future__ import annotations

import json
import sys

from app.core.config import get_settings
from app.interfaces.cli import build_parser
from app.providers.llm import LlmProviderError, OpenAiAuditProvider
from app.services.analyzer import AnalyzerError, analyze_landing
from app.services.exporter import export_report
from app.services.parser import ParsingError, parse_landing


def run() -> int:
    """Run CLI flow and return process exit code."""
    parser = build_parser()
    args = parser.parse_args()
    settings = get_settings()
    verbose = bool(args.verbose)

    def _log(step: str) -> None:
        if verbose:
            print(f"[verbose] {step}")

    try:
        _log("fetching")
        _log("parsing")
        parsed_landing = parse_landing(url=args.url, settings=settings)
        _log("analyzing")
        provider = OpenAiAuditProvider(settings=settings)
        audit_result = analyze_landing(
            parsed_landing=parsed_landing.to_dict(),
            user_task=args.task,
            provider=provider,
        )
        _log("exporting")
        export_report(report=audit_result, output_path=args.output)
        report = audit_result.to_dict()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print("Audit completed successfully")
        print(f"Output saved to: {args.output}")
        return 0
    except (ParsingError, LlmProviderError, AnalyzerError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: unexpected failure while processing audit: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
