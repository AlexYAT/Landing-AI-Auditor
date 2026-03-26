"""Persist full audit JSON under ``audits/`` (CLI + UI)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from app.core.lang import normalize_lang
from app.core import paths

RunType = Literal["baseline", "improved"]


def audit_domain_slug(url: str) -> str:
    """First hostname label for filenames (e.g. my-astro.ru → my-astro)."""
    host = urlparse(url).hostname or ""
    if not host:
        return "unknown"
    label = host.split(".")[0].lower()
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in label)
    return safe.strip("_") or "unknown"


def save_audit_report(url: str, report: dict[str, Any]) -> str:
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
    with path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
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
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    md_path.write_text(readable_body, encoding="utf-8")

    def _disp(p: Path) -> str:
        try:
            return p.resolve().relative_to(paths.PROJECT_ROOT.resolve()).as_posix()
        except ValueError:
            return p.resolve().as_posix()

    return _disp(json_path), _disp(md_path)
