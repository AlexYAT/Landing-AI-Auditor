"""Persist full audit JSON under ``audits/`` (CLI + UI)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from app.core.lang import normalize_lang
from app.core import paths


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
