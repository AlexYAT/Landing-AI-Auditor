"""Filesystem paths shared by CLI and HTTP (stable regardless of process cwd)."""

from __future__ import annotations

import os
from pathlib import Path

# app/core/paths.py → project root (parent of ``app/``)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def get_audits_dir() -> Path:
    """
    Directory for saved audit JSON (CLI history + UI).

    Override with env ``AUDITS_DIR`` (absolute or relative path) if needed.
    """
    raw = os.getenv("AUDITS_DIR", "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            return (PROJECT_ROOT / p).resolve()
        return p.resolve()
    return (PROJECT_ROOT / "audits").resolve()
