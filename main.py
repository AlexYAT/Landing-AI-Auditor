"""Application entrypoint for landing audit CLI."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
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
from app.services.report_builder import build_human_report, format_summary_readable

logger = logging.getLogger(__name__)

_AUDITS_DIR = Path("audits")


def _audit_domain_slug(url: str) -> str:
    """First hostname label for filenames (e.g. my-astro.ru → my-astro)."""
    host = urlparse(url).hostname or ""
    if not host:
        return "unknown"
    label = host.split(".")[0].lower()
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in label)
    return safe.strip("_") or "unknown"


def _missing_blocks_set(report: dict[str, Any]) -> set[str]:
    ba = report.get("block_analysis")
    if not isinstance(ba, dict):
        return set()
    mb = ba.get("missing_blocks")
    if not isinstance(mb, list):
        return set()
    return {str(x).strip() for x in mb if str(x).strip()}


def _next_block_type(report: dict[str, Any]) -> str:
    ba = report.get("block_analysis")
    if not isinstance(ba, dict):
        return ""
    nb = ba.get("next_block")
    if not isinstance(nb, dict):
        return ""
    return str(nb.get("type", "")).strip()


def _roadmap_actions_set(report: dict[str, Any]) -> set[str]:
    ar = report.get("action_roadmap")
    if not isinstance(ar, list):
        return set()
    out: set[str] = set()
    for item in ar:
        if isinstance(item, dict):
            a = str(item.get("action", "")).strip()
            if a:
                out.add(a)
    return out


def _load_audit_json(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(path)
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def _print_audit_diff(report_old: dict[str, Any], report_new: dict[str, Any]) -> None:
    """Print readable diff between two audit JSON payloads."""
    s_old = _missing_blocks_set(report_old)
    s_new = _missing_blocks_set(report_new)
    added_mb = sorted(s_new - s_old)
    removed_mb = sorted(s_old - s_new)

    t_old = _next_block_type(report_old)
    t_new = _next_block_type(report_new)

    r_old = _roadmap_actions_set(report_old)
    r_new = _roadmap_actions_set(report_new)
    added_r = sorted(r_new - r_old)
    removed_r = sorted(r_old - r_new)

    print("=== DIFF ===")
    print()
    print("BLOCKS:")
    if added_mb or removed_mb:
        for line in added_mb:
            print(f"* {line}")
        for line in removed_mb:
            print(f"- {line}")
    else:
        print("(no changes)")
    print()
    print("NEXT ACTION:")
    if t_old != t_new:
        print(f"было: {t_old or '—'}")
        print(f"стало: {t_new or '—'}")
    else:
        print("(без изменений)")
    print()
    print("ROADMAP CHANGES:")
    if added_r or removed_r:
        for line in added_r:
            print(f"* {line}")
        for line in removed_r:
            print(f"- {line}")
    else:
        print("(no changes)")


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


def _write_audit_history(url: str, report: dict[str, Any]) -> str:
    """
    Persist full report JSON under ``audits/`` for CLI history.

    Returns POSIX-style relative path for display (e.g. ``audits/foo_ru_2026-03-22_10-30.json``).
    """
    _AUDITS_DIR.mkdir(parents=True, exist_ok=True)
    domain = _audit_domain_slug(url)
    lang = normalize_lang(report.get("language"))
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    fname = f"{domain}_{lang}_{ts}.json"
    path = _AUDITS_DIR / fname
    with path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return path.as_posix()


def _configure_stdio_utf8() -> None:
    """Reduce UnicodeEncodeError on Windows (cp1251) when printing Russian JSON to console."""
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            try:
                reconf(encoding="utf-8", errors="replace")
            except (OSError, ValueError, AttributeError, TypeError):
                pass


def _summary_for_readable(report: dict[str, Any], rr: dict[str, Any]) -> str:
    """Plain-text summary for CLI readable / save-report (not raw JSON)."""
    return format_summary_readable(rr.get("summary"), report.get("language"))


def _readable_payload(report: dict[str, Any]) -> dict[str, Any]:
    """``report_readable`` dict or ``build_human_report(report)``."""
    rr = report.get("report_readable")
    if isinstance(rr, dict):
        return rr
    return build_human_report(report)


def _block_analysis_visible(rr: dict[str, Any]) -> bool:
    if rr.get("next_action_readable"):
        return True
    bar = rr.get("block_analysis_readable")
    if not isinstance(bar, dict):
        return False
    mb = bar.get("missing_blocks") or []
    if mb:
        return True
    na = bar.get("next_action")
    if not isinstance(na, dict):
        return False
    for k, v in na.items():
        if k == "confidence":
            if isinstance(v, (int, float)) and float(v) > 0:
                return True
            continue
        if v is not None and str(v).strip():
            return True
    return False


def _rewrite_texts_readable_nonempty(rr: dict[str, Any]) -> bool:
    rt = rr.get("rewrite_texts_readable")
    if not isinstance(rt, dict):
        return False
    for key in ("hero", "cta", "trust"):
        if str(rt.get(key, "")).strip():
            return True
    return False


def _format_quick_win_line(item: Any) -> str:
    if isinstance(item, dict):
        title = str(item.get("title", "")).strip()
        action = str(item.get("action", "")).strip()
        if title and action:
            return f"- {title}: {action}"
        if title:
            return f"- {title}"
        if action:
            return f"- {action}"
        return f"- {item}"
    return f"- {item}"


def _print_quick_win_line(item: Any) -> None:
    print(_format_quick_win_line(item))


def _build_readable_markdown(report: dict[str, Any]) -> str:
    """Markdown-like file body for ``--save-report`` with ``--output-format readable``."""
    rr = _readable_payload(report)
    parts: list[str] = [
        "# Summary",
        _summary_for_readable(report, rr),
        "",
        "# Issues",
    ]
    for line in rr.get("issues_readable") or []:
        parts.append(f"- {line}")
    parts.extend(["", "# Recommendations"])
    blocks = rr.get("recommendations_readable") or []
    for i, block in enumerate(blocks):
        if i > 0:
            parts.append("")
        parts.append(block)
    parts.extend(["", "# Quick Wins"])
    for item in rr.get("quick_wins") or []:
        parts.append(_format_quick_win_line(item))
    if _block_analysis_visible(rr):
        bar = rr.get("block_analysis_readable")
        if not isinstance(bar, dict):
            bar = {}
        mb = list(bar.get("missing_blocks") or [])
        if mb:
            parts.extend(["", "# Missing blocks", ""])
            for line in mb:
                parts.append(f"- {line}")
        nar = rr.get("next_action_readable") or ""
        if nar.strip():
            parts.extend(["", "# Next action", "", nar])
    arr = (rr.get("action_roadmap_readable") or "").strip()
    if arr:
        parts.extend(["", "# Action roadmap", "", arr])
    if _rewrite_texts_readable_nonempty(rr):
        rt = rr.get("rewrite_texts_readable")
        if not isinstance(rt, dict):
            rt = {}
        parts.extend(
            [
                "",
                "# Rewrites",
                "",
                "## Hero",
                str(rt.get("hero", "")),
                "",
                "## CTA",
                str(rt.get("cta", "")),
                "",
                "## Trust",
                str(rt.get("trust", "")),
            ]
        )
    return "\n".join(parts)


def _write_saved_report(path_str: str, report: dict[str, Any], output_format: str) -> None:
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "readable":
        path.write_text(_build_readable_markdown(report), encoding="utf-8")
    else:
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _print_readable_console(report: dict[str, Any]) -> None:
    """Print ``report_readable`` (or rebuild via ``build_human_report``) to stdout."""
    rr = _readable_payload(report)

    print("=== SUMMARY ===")
    print(_summary_for_readable(report, rr))
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
    print()
    print("=== QUICK WINS ===")
    for item in rr.get("quick_wins") or []:
        _print_quick_win_line(item)
    if _block_analysis_visible(rr):
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
    if _rewrite_texts_readable_nonempty(rr):
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
        elif getattr(args, "output_format", "json") == "readable":
            _print_readable_console(report)
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))

        history_path = _write_audit_history(args.url, report)

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
