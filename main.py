"""Application entrypoint for landing audit CLI."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.core import paths
from app.core.config import get_settings
from app.core.lang import normalize_lang, resolve_effective_lang, used_language_fallback
from app.interfaces.cli import build_parser
from app.providers.llm import LlmProviderError
from app.services.analyzer import AnalyzerError
from app.services.assignment_formatter import format_assignment_output
from app.services.audit_pipeline import run_landing_audit, run_visual_audit
from app.services.audit_storage import save_audit_report
from app.services.diff_service import compute_audit_diff_output
from app.services.exporter import export_report
from app.services.parser import ParsingError
from app.services.baseline_runner import run_baseline_audit
from app.services.compare_runner import run_full_audit_compare
from app.services.readable_export import (
    block_analysis_visible,
    build_landing_audit_readable_markdown as _build_readable_markdown,
    format_quick_win_line,
    readable_payload,
    rewrite_texts_readable_nonempty,
    summary_for_readable,
)
from app.services.report_builder import format_visual_audit_readable

logger = logging.getLogger(__name__)


def _load_audit_json(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(path)
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def _print_audit_diff(report_old: dict[str, Any], report_new: dict[str, Any]) -> None:
    """Print readable diff between two audit JSON payloads (same output as ``compute_audit_diff_output``)."""
    out = compute_audit_diff_output(report_old, report_new)
    sys.stdout.write(out["change_summary"])
    sys.stdout.write(out["diff"])
    sys.stdout.write(out["progress_text"])


def _run_diff(path1: str, path2: str) -> int:
    """Load two audit JSON files and print diff; no pipeline."""
    try:
        old_rep = _load_audit_json(path1)
    except FileNotFoundError:
        print(f"Error: file not found: {path1}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON in {path1}: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error: cannot read {path1}: {exc}", file=sys.stderr)
        return 1
    try:
        new_rep = _load_audit_json(path2)
    except FileNotFoundError:
        print(f"Error: file not found: {path2}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON in {path2}: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error: cannot read {path2}: {exc}", file=sys.stderr)
        return 1
    _print_audit_diff(old_rep, new_rep)
    return 0


def _configure_stdio_utf8() -> None:
    """Reduce UnicodeEncodeError on Windows (cp1251) when printing Russian JSON to console."""
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            try:
                reconf(encoding="utf-8", errors="replace")
            except (OSError, ValueError, AttributeError, TypeError):
                pass


def _print_quick_win_line(item: Any) -> None:
    print(format_quick_win_line(item))


def _write_saved_report(path_str: str, report: dict[str, Any], output_format: str) -> None:
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "readable":
        path.write_text(_build_readable_markdown(report), encoding="utf-8")
    else:
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _visual_report_text(report: dict[str, Any], output_format: str, lang: str) -> str:
    """Serialize visual audit for stdout or file (JSON or readable only)."""
    if output_format == "readable":
        return format_visual_audit_readable(report, lang)
    return json.dumps(report, ensure_ascii=False, indent=2)


def _write_saved_visual_report(path_str: str, report: dict[str, Any], output_format: str, lang: str) -> None:
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_visual_report_text(report, output_format, lang), encoding="utf-8")


def _print_readable_console(report: dict[str, Any]) -> None:
    """Print ``report_readable`` (or rebuild via ``build_human_report``) to stdout."""
    rr = readable_payload(report)

    print("=== SUMMARY ===")
    print(summary_for_readable(report, rr))
    print()
    print("=== ISSUES ===")
    for line in rr.get("issues_readable") or []:
        print(f"- {line}")
    print()
    print("=== RECOMMENDATIONS ===")
    blocks = rr.get("recommendations_readable") or []
    for i, block in enumerate(blocks):
        if i > 0:
            print()
        print(block)
    if str(report.get("preset", "")).lower() == "craftum":
        csec = (rr.get("craftum_block_plan_section") or "").strip()
        if csec:
            print()
            print(csec)
    print()
    print("=== QUICK WINS ===")
    for item in rr.get("quick_wins") or []:
        _print_quick_win_line(item)
    if block_analysis_visible(rr):
        bar = rr.get("block_analysis_readable")
        if not isinstance(bar, dict):
            bar = {}
        mb = list(bar.get("missing_blocks") or [])
        if mb:
            print()
            print("=== MISSING BLOCKS ===")
            for line in mb:
                print(f"- {line}")
        nar = (rr.get("next_action_readable") or "").strip()
        if nar:
            print()
            print("=== NEXT ACTION ===")
            print(nar)
    arr = (rr.get("action_roadmap_readable") or "").strip()
    if arr:
        print()
        print("=== ACTION ROADMAP ===")
        print(arr)
    if rewrite_texts_readable_nonempty(rr):
        rt = rr.get("rewrite_texts_readable")
        if not isinstance(rt, dict):
            rt = {}
        print()
        print("=== REWRITES ===")
        print("Hero:")
        print(rt.get("hero", ""))
        print()
        print("CTA:")
        print(rt.get("cta", ""))
        print()
        print("Trust:")
        print(rt.get("trust", ""))


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

    if getattr(args, "diff", None):
        return _run_diff(args.diff[0], args.diff[1])

    if getattr(args, "baseline", False):
        if not args.url:
            print("Error: --baseline requires --url", file=sys.stderr)
            return 1
        _log("baseline: output directory")
        out_arg = getattr(args, "baseline_dir", None)
        baseline_out = Path(out_arg) if out_arg else paths.get_audits_dir() / "baseline"
        if not baseline_out.is_absolute():
            baseline_out = (paths.PROJECT_ROOT / baseline_out).resolve()
        debug_dir_b: Path | None = None
        if getattr(args, "debug", False):
            host = urlparse(args.url).netloc.replace(":", "_") or "unknown"
            debug_dir_b = Path("output") / "debug" / host
            logger.info("Debug mode: baseline using parser artifacts under %s", debug_dir_b)
        try:
            summary = run_baseline_audit(
                args.url.strip(),
                settings=settings,
                effective_lang=effective_lang,
                output_dir=baseline_out,
                user_task=getattr(args, "task", None),
                debug_dir=debug_dir_b,
            )
            print(f"Baseline finished: status={summary.status}")
            print(f"Manifest: {summary.manifest_path}")
            rel = summary.manifest_path
            try:
                rel = rel.relative_to(paths.PROJECT_ROOT)
            except ValueError:
                pass
            print(f"(relative to project: {rel})")
            return 0 if summary.exit_ok else 1
        except Exception as exc:
            print(f"Error: baseline run failed: {exc}", file=sys.stderr)
            return 1

    if getattr(args, "full_audit", False):
        if not args.url:
            print("Error: --full-audit / --compare-baseline requires --url", file=sys.stderr)
            return 1
        baseline_ref = (
            Path(args.baseline_dir)
            if getattr(args, "baseline_dir", None)
            else paths.get_audits_dir() / "baseline"
        )
        if not baseline_ref.is_absolute():
            baseline_ref = (paths.PROJECT_ROOT / baseline_ref).resolve()
        compare_out = (
            Path(args.compare_dir) if getattr(args, "compare_dir", None) else paths.get_audits_dir() / "compare"
        )
        if not compare_out.is_absolute():
            compare_out = (paths.PROJECT_ROOT / compare_out).resolve()
        debug_dir_c: Path | None = None
        if getattr(args, "debug", False):
            host = urlparse(args.url).netloc.replace(":", "_") or "unknown"
            debug_dir_c = Path("output") / "debug" / host
            logger.info("Debug mode: full-audit using parser artifacts under %s", debug_dir_c)
        try:
            summary = run_full_audit_compare(
                args.url.strip(),
                settings=settings,
                effective_lang=effective_lang,
                baseline_dir=baseline_ref,
                output_dir=compare_out,
                user_task=getattr(args, "task", None),
                debug_dir=debug_dir_c,
            )
            print(f"Full-audit compare finished: status={summary.status}")
            print(f"Manifest: {summary.manifest_path}")
            print(f"Comparison: {summary.comparison_path}")
            return 0 if summary.exit_ok else 1
        except Exception as exc:
            print(f"Error: full-audit compare failed: {exc}", file=sys.stderr)
            return 1

    try:
        if mode == "assignment":
            logger.info("Mode: assignment")
            print("Running in assignment mode")
        elif mode == "visual":
            logger.info("Mode: visual")
            print("Running in visual audit mode")

        _log("fetching")
        _log("parsing")
        debug_dir: Path | None = None
        if getattr(args, "debug", False):
            host = urlparse(args.url).netloc.replace(":", "_") or "unknown"
            debug_dir = Path("output") / "debug" / host
            logger.info("Debug mode: writing parser artifacts to %s", debug_dir)
        _log("analyzing")
        rewrite_targets: tuple[str, ...] | None = getattr(args, "rewrite", None)

        if mode == "visual":
            report = run_visual_audit(
                args.url,
                settings=settings,
                effective_lang=effective_lang,
                debug_dir=debug_dir,
            )
            out_fmt = getattr(args, "output_format", "json") or "json"
            text_out = _visual_report_text(report, out_fmt, effective_lang)
            sys.stdout.write(text_out)
            if not text_out.endswith("\n"):
                sys.stdout.write("\n")
            history_path = save_audit_report(args.url, report)
            save_path = getattr(args, "save_report", None)
            if save_path:
                _write_saved_visual_report(save_path, report, out_fmt, effective_lang)
                logger.info("Report saved to %s", save_path)
            print("Audit completed successfully")
            print(f"Аудит сохранён в: {history_path}")
            return 0

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
        elif getattr(args, "output_format", "json") == "readable":
            _print_readable_console(report)
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))

        history_path = save_audit_report(args.url, report)

        save_path = getattr(args, "save_report", None)
        if save_path:
            _write_saved_report(
                save_path,
                report,
                getattr(args, "output_format", "json"),
            )
            logger.info("Report saved to %s", save_path)

        if mode == "full":
            _log("exporting")
            export_report(report=report, output_path=args.output)
            print("Audit completed successfully")
            print(f"Output saved to: {args.output}")
        else:
            print("Audit completed successfully")
        print(f"Аудит сохранён в: {history_path}")
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
