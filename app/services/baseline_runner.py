"""Baseline audit: content + craftum + visual snapshots for compare workflows."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.core import paths
from app.core.config import Settings
from app.services.audit_pipeline import run_landing_audit, run_visual_audit
from app.services.readable_export import build_landing_audit_readable_markdown

logger = logging.getLogger(__name__)

PROJECT_VERSION = "1.0"

CONTENT_JSON = "content.json"
CONTENT_READABLE = "content_readable.md"
CRAFTUM_JSON = "craftum.json"
VISUAL_JSON = "visual.json"
MANIFEST_JSON = "manifest.json"


@dataclass
class _ModeResult:
    ok: bool = False
    error: str | None = None
    error_type: str | None = None


@dataclass
class BaselineRunSummary:
    status: str
    manifest_path: Path
    exit_ok: bool
    modes: dict[str, _ModeResult] = field(default_factory=dict)


def _try_git_commit() -> str | None:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(paths.PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if r.returncode == 0 and r.stdout:
            return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _rel_to_project(path: Path) -> str:
    try:
        return path.resolve().relative_to(paths.PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run_baseline_audit(
    url: str,
    *,
    settings: Settings,
    effective_lang: str,
    output_dir: Path | None = None,
    user_task: str | None = None,
    debug_dir: str | Path | None = None,
    run_landing_audit_fn: Callable[..., dict[str, Any]] = run_landing_audit,
    run_visual_audit_fn: Callable[..., dict[str, Any]] = run_visual_audit,
) -> BaselineRunSummary:
    """
    Run content (general), craftum, and visual audits; write JSON, content readable, manifest.

    Partial failures are recorded in manifest (``status`` ``partial``); visual errors write a stub ``visual.json``.
    """
    base = (output_dir or (paths.get_audits_dir() / "baseline")).resolve()
    base.mkdir(parents=True, exist_ok=True)

    modes: dict[str, _ModeResult] = {
        "content": _ModeResult(),
        "craftum": _ModeResult(),
        "visual": _ModeResult(),
    }
    limitations: list[dict[str, str]] = []
    artifacts: dict[str, str] = {}
    notes: list[str] = []

    path_content = base / CONTENT_JSON
    path_readable = base / CONTENT_READABLE
    path_craftum = base / CRAFTUM_JSON
    path_visual = base / VISUAL_JSON
    path_manifest = base / MANIFEST_JSON

    # --- content (general preset) ---
    try:
        report_content = run_landing_audit_fn(
            url,
            settings=settings,
            user_task=user_task,
            effective_lang=effective_lang,
            rewrite_targets=None,
            preset="general",
            debug_dir=debug_dir,
        )
        _write_json(path_content, report_content)
        artifacts["content_json"] = _rel_to_project(path_content)
        path_readable.write_text(
            build_landing_audit_readable_markdown(report_content),
            encoding="utf-8",
        )
        artifacts["content_readable"] = _rel_to_project(path_readable)
        modes["content"].ok = True
    except Exception as exc:
        logger.exception("Baseline content audit failed")
        modes["content"].error = str(exc)
        modes["content"].error_type = type(exc).__name__
        limitations.append(
            {"mode": "content", "error": str(exc), "error_type": type(exc).__name__},
        )
        notes.append("Content audit failed; content.json not written.")

    # --- craftum preset ---
    try:
        report_craftum = run_landing_audit_fn(
            url,
            settings=settings,
            user_task=user_task,
            effective_lang=effective_lang,
            rewrite_targets=None,
            preset="craftum",
            debug_dir=debug_dir,
        )
        _write_json(path_craftum, report_craftum)
        artifacts["craftum_json"] = _rel_to_project(path_craftum)
        modes["craftum"].ok = True
    except Exception as exc:
        logger.exception("Baseline craftum audit failed")
        modes["craftum"].error = str(exc)
        modes["craftum"].error_type = type(exc).__name__
        limitations.append(
            {"mode": "craftum", "error": str(exc), "error_type": type(exc).__name__},
        )
        notes.append("Craftum audit failed; craftum.json not written.")

    # --- visual ---
    try:
        report_visual = run_visual_audit_fn(
            url,
            settings=settings,
            effective_lang=effective_lang,
            debug_dir=debug_dir,
        )
        _write_json(path_visual, report_visual)
        artifacts["visual_json"] = _rel_to_project(path_visual)
        modes["visual"].ok = True
    except Exception as exc:
        logger.exception("Baseline visual audit failed")
        modes["visual"].error = str(exc)
        modes["visual"].error_type = type(exc).__name__
        limitations.append(
            {"mode": "visual", "error": str(exc), "error_type": type(exc).__name__},
        )
        stub = {
            "baseline_status": "error",
            "error_message": str(exc),
            "error_type": type(exc).__name__,
            "audit_type": "visual",
        }
        _write_json(path_visual, stub)
        artifacts["visual_json"] = _rel_to_project(path_visual)
        notes.append("Visual audit failed; visual.json contains error stub.")

    ok_count = sum(1 for m in modes.values() if m.ok)
    if ok_count == 3:
        status = "ok"
    elif ok_count > 0:
        status = "partial"
    else:
        status = "failed"

    modes_run = ["content", "craftum", "visual"]
    git_commit = _try_git_commit()

    manifest: dict[str, Any] = {
        "url": url,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "modes_run": modes_run,
        "artifacts": artifacts,
        "status": status,
        "limitations": limitations,
        "notes": notes,
        "project_version": PROJECT_VERSION,
        "git_commit": git_commit,
        "modes_detail": {
            k: {"ok": v.ok, "error": v.error, "error_type": v.error_type} for k, v in modes.items()
        },
    }

    _write_json(path_manifest, manifest)

    exit_ok = status != "failed"
    return BaselineRunSummary(
        status=status,
        manifest_path=path_manifest,
        exit_ok=exit_ok,
        modes=modes,
    )
