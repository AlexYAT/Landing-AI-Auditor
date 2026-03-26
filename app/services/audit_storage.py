"""Persist full audit JSON under ``audits/`` (CLI + UI)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from app.core.lang import normalize_lang
from app.core import paths

RunType = Literal["baseline", "improved"]

_HISTORY_NAME_RE = re.compile(
    r"^(.+)_([a-z]{2})_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2})\.json$",
    re.IGNORECASE,
)


def build_audit_meta(
    url: str,
    *,
    mode: str,
    language: str,
    preset: str,
    run_type: str | None = None,
    label: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Structured context for saved audits (embedded in JSON root as ``meta``)."""
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    return {
        "url": url.strip(),
        "domain": audit_domain_slug(url),
        "mode": mode,
        "preset": (preset or "general").strip().lower(),
        "language": normalize_lang(language),
        "timestamp": ts,
        "run_type": run_type,
        "label": label,
    }


def merge_report_meta(
    report: dict[str, Any],
    url: str,
    *,
    mode: str,
    preset: str | None = None,
    run_type: str | None = None,
    label: str | None = None,
    language: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Shallow copy of report with ``meta`` set (does not mutate original)."""
    lang_code = language if language is not None else str(report.get("language") or "")
    pr = preset if preset is not None else report.get("preset")
    if not pr:
        pr = "general"
    out = dict(report)
    out["meta"] = build_audit_meta(
        url,
        mode=mode,
        language=lang_code,
        preset=str(pr),
        run_type=run_type,
        label=label,
        timestamp=timestamp,
    )
    return out


def coerce_audit_meta(
    report: dict[str, Any],
    *,
    filename: str = "",
    url_fallback: str = "",
) -> dict[str, Any]:
    """Return displayable meta for UI/compare; safe for legacy JSON without ``meta``."""
    m = report.get("meta")
    if isinstance(m, dict) and "mode" in m:
        return {
            "url": str(m.get("url") or url_fallback or "?"),
            "domain": str(m.get("domain") or audit_domain_slug(str(m.get("url") or url_fallback)) or "?"),
            "mode": str(m.get("mode") or "?"),
            "preset": str(m.get("preset") or report.get("preset") or "?"),
            "language": str(m.get("language") or report.get("language") or "?"),
            "timestamp": str(m.get("timestamp") or _timestamp_from_filename(filename)),
            "run_type": m.get("run_type"),
            "label": m.get("label"),
        }
    url = url_fallback or str(report.get("url") or "")
    mode = "visual" if report.get("audit_type") == "visual" else "full"
    preset = report.get("preset")
    if not preset:
        preset = "general"
    return {
        "url": url or "?",
        "domain": audit_domain_slug(url) if url else "?",
        "mode": mode,
        "preset": str(preset),
        "language": str(normalize_lang(report.get("language"))),
        "timestamp": _timestamp_from_filename(filename),
        "run_type": None,
        "label": None,
    }


def _timestamp_from_filename(filename: str) -> str:
    m = _HISTORY_NAME_RE.match(filename)
    if not m:
        return "?"
    _, _lang, date_part, time_part = m.groups()
    hh, mm = time_part.split("-", 1)
    return f"{date_part} {hh}:{mm}"


def format_history_context_line(meta: dict[str, Any]) -> str:
    """Compact suffix for audit history list (e.g. ``full · craftum · improved``)."""
    parts: list[str] = [str(meta.get("mode") or "?"), str(meta.get("preset") or "?")]
    rt = meta.get("run_type")
    if rt is not None and str(rt).strip():
        parts.append(str(rt))
    return " · ".join(parts)


def format_audit_context_text(label: str, meta: dict[str, Any]) -> str:
    """Human-readable bullet block for diff/compare."""
    rt = meta.get("run_type")
    rt_s = str(rt) if rt is not None and str(rt).strip() else "—"
    return (
        f"{label}:\n"
        f"- domain: {meta.get('domain')}\n"
        f"- mode: {meta.get('mode')}\n"
        f"- preset: {meta.get('preset')}\n"
        f"- language: {meta.get('language')}\n"
        f"- run_type: {rt_s}\n"
        f"- timestamp: {meta.get('timestamp')}\n"
    )


def audit_domain_slug(url: str) -> str:
    """First hostname label for filenames (e.g. my-astro.ru → my-astro)."""
    host = urlparse(url).hostname or ""
    if not host:
        return "unknown"
    label = host.split(".")[0].lower()
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in label)
    return safe.strip("_") or "unknown"


def save_audit_report(
    url: str,
    report: dict[str, Any],
    *,
    mode: str = "full",
    preset: str | None = None,
    run_type: str | None = None,
    label: str | None = None,
) -> str:
    """
    Write report JSON next to the project ``audits/`` folder.

    Returns POSIX-style relative path for display (e.g. ``audits/foo_ru_2026-03-22_10-30.json``).
    """
    audits = paths.get_audits_dir()
    audits.mkdir(parents=True, exist_ok=True)
    domain = audit_domain_slug(url)
    lang = normalize_lang(report.get("language"))
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    fname = f"{domain}_{lang}_{ts}.json"
    path = audits / fname
    ts_iso = datetime.now(timezone.utc).isoformat()
    to_save = merge_report_meta(
        report,
        url,
        mode=mode,
        preset=preset,
        run_type=run_type,
        label=label,
        language=lang,
        timestamp=ts_iso,
    )
    with path.open("w", encoding="utf-8") as f:
        json.dump(to_save, f, ensure_ascii=False, indent=2)
    try:
        return path.relative_to(paths.PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _safe_mode_slug(cli_mode: str) -> str:
    s = (cli_mode or "full").strip().lower()
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in s)
    return safe.strip("_") or "full"


def save_run_audit_pair(
    url: str,
    report: dict[str, Any],
    *,
    run_type: RunType,
    cli_mode: str,
    readable_body: str,
) -> tuple[str, str]:
    """
    Write full JSON + readable ``.md`` under ``audits/<baseline|improved>/``.

    Filename pattern: ``{domain}_{mode}_{timestamp}.json`` / same stem ``.md``.

    Returns ``(json_rel_path, md_rel_path)`` for console (relative to project root when possible).
    """
    audits = paths.get_audits_dir()
    sub = audits / run_type
    sub.mkdir(parents=True, exist_ok=True)
    domain = audit_domain_slug(url)
    mode_slug = _safe_mode_slug(cli_mode)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    stem = f"{domain}_{mode_slug}_{ts}"
    json_path: Path = sub / f"{stem}.json"
    md_path: Path = sub / f"{stem}.md"
    ts_slug = datetime.now(timezone.utc).isoformat()
    pr = report.get("preset") or "general"
    to_save = merge_report_meta(
        report,
        url,
        mode=cli_mode,
        preset=str(pr),
        run_type=run_type,
        label=None,
        language=str(report.get("language") or ""),
        timestamp=ts_slug,
    )
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(to_save, f, ensure_ascii=False, indent=2)
    md_path.write_text(readable_body, encoding="utf-8")

    def _disp(p: Path) -> str:
        try:
            return p.resolve().relative_to(paths.PROJECT_ROOT.resolve()).as_posix()
        except ValueError:
            return p.resolve().as_posix()

    return _disp(json_path), _disp(md_path)
