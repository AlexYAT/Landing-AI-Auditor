"""Full-audit / compare workflow: current snapshot vs baseline on disk."""

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
from app.services.baseline_runner import (
    CONTENT_JSON,
    CRAFTUM_JSON,
    MANIFEST_JSON,
    VISUAL_JSON,
)
from app.services.audit_storage import merge_report_meta
from app.services.compare_heuristics import (
    build_comparison_payload,
    render_comparison_markdown,
)
from app.services.readable_export import build_landing_audit_readable_markdown

logger = logging.getLogger(__name__)

PROJECT_VERSION = "1.0"

CURRENT_CONTENT_JSON = "current_content.json"
CURRENT_CONTENT_READABLE = "current_content_readable.md"
CURRENT_CRAFTUM_JSON = "current_craftum.json"
CURRENT_VISUAL_JSON = "current_visual.json"
COMPARISON_JSON = "comparison.json"
COMPARISON_READABLE = "comparison_readable.md"
COMPARE_MANIFEST_JSON = "manifest.json"


@dataclass
class CompareRunSummary:
    status: str
    exit_ok: bool
    manifest_path: Path
    comparison_path: Path | None
    limitations: list[str] = field(default_factory=list)


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


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_baseline_directory(base: Path) -> dict[str, Any]:
    """
    Ensure baseline folder has manifest and core artifacts.

    ``visual.json`` may be an error stub (still a valid file).
    """
    if not base.is_dir():
        raise ValueError(f"Baseline directory does not exist or is not a directory: {base}")
    manifest_path = base / MANIFEST_JSON
    if not manifest_path.is_file():
        raise ValueError(
            f"Baseline manifest missing ({MANIFEST_JSON}). "
            f"Run `python main.py --url <URL> --baseline` first (see README).",
        )
    for name in (CONTENT_JSON, CRAFTUM_JSON, VISUAL_JSON):
        p = base / name
        if not p.is_file():
            raise ValueError(f"Baseline artifact missing: {name} under {base}")
    try:
        manifest = _read_json(manifest_path)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Baseline manifest is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Baseline manifest must be a JSON object.")
    return manifest


def load_baseline_reports(base: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    content = _read_json(base / CONTENT_JSON)
    craftum = _read_json(base / CRAFTUM_JSON)
    visual = _read_json(base / VISUAL_JSON)
    if not isinstance(content, dict):
        raise ValueError(f"{CONTENT_JSON} must be a JSON object.")
    if not isinstance(craftum, dict):
        raise ValueError(f"{CRAFTUM_JSON} must be a JSON object.")
    if not isinstance(visual, dict):
        raise ValueError(f"{VISUAL_JSON} must be a JSON object.")
    return content, craftum, visual


def run_full_audit_compare(
    url: str,
    *,
    settings: Settings,
    effective_lang: str,
    baseline_dir: Path | None = None,
    output_dir: Path | None = None,
    user_task: str | None = None,
    debug_dir: str | Path | None = None,
    run_landing_audit_fn: Callable[..., dict[str, Any]] = run_landing_audit,
    run_visual_audit_fn: Callable[..., dict[str, Any]] = run_visual_audit,
) -> CompareRunSummary:
    """
    Load baseline from disk, run fresh content/craftum/visual for ``url``, write compare artifacts.

    Returns ``exit_ok=False`` if baseline is invalid or current content audit fails (no meaningful compare).
    """
    base = (baseline_dir or (paths.get_audits_dir() / "baseline")).resolve()
    out = (output_dir or (paths.get_audits_dir() / "compare")).resolve()
    out.mkdir(parents=True, exist_ok=True)

    limitations: list[str] = []
    try:
        validate_baseline_directory(base)
        baseline_content, baseline_craftum, baseline_visual = load_baseline_reports(base)
    except ValueError as exc:
        logger.warning("Baseline validation failed: %s", exc)
        fail = {
            "url": url,
            "status": "failed",
            "error": str(exc),
            "baseline_dir": _rel_to_project(base) if base.exists() else str(base),
        }
        _write_json(out / COMPARISON_JSON, fail)
        (out / COMPARISON_READABLE).write_text(
            "# Full audit comparison\n\n**Failed:** "
            + str(exc)
            + "\n",
            encoding="utf-8",
        )
        man = {
            "url": url,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "baseline_dir": _rel_to_project(base) if base.exists() else str(base),
            "compare_output_dir": _rel_to_project(out),
            "status": "failed",
            "limitations": [str(exc)],
            "artifacts": {
                "comparison_json": _rel_to_project(out / COMPARISON_JSON),
                "comparison_readable": _rel_to_project(out / COMPARISON_READABLE),
            },
            "project_version": PROJECT_VERSION,
            "git_commit": _try_git_commit(),
        }
        _write_json(out / COMPARE_MANIFEST_JSON, man)
        return CompareRunSummary(
            status="failed",
            exit_ok=False,
            manifest_path=out / COMPARE_MANIFEST_JSON,
            comparison_path=out / COMPARISON_JSON,
            limitations=[str(exc)],
        )

    current_content: dict[str, Any] | None = None
    current_craftum: dict[str, Any] | None = None
    current_visual: dict[str, Any] | None = None
    modes_ok = {"content": False, "craftum": False, "visual": False}

    path_cc = out / CURRENT_CONTENT_JSON
    path_cread = out / CURRENT_CONTENT_READABLE
    path_craft = out / CURRENT_CRAFTUM_JSON
    path_vis = out / CURRENT_VISUAL_JSON

    try:
        current_content = run_landing_audit_fn(
            url,
            settings=settings,
            user_task=user_task,
            effective_lang=effective_lang,
            rewrite_targets=None,
            preset="general",
            debug_dir=debug_dir,
        )
        current_content = merge_report_meta(
            current_content,
            url,
            mode="full",
            preset="general",
            run_type=None,
            language=effective_lang,
        )
        _write_json(path_cc, current_content)
        path_cread.write_text(
            build_landing_audit_readable_markdown(current_content),
            encoding="utf-8",
        )
        modes_ok["content"] = True
    except Exception as exc:
        logger.exception("Compare: current content audit failed")
        limitations.append(f"Current content audit failed: {exc}")

    try:
        current_craftum = run_landing_audit_fn(
            url,
            settings=settings,
            user_task=user_task,
            effective_lang=effective_lang,
            rewrite_targets=None,
            preset="craftum",
            debug_dir=debug_dir,
        )
        current_craftum = merge_report_meta(
            current_craftum,
            url,
            mode="full",
            preset="craftum",
            run_type=None,
            language=effective_lang,
        )
        _write_json(path_craft, current_craftum)
        modes_ok["craftum"] = True
    except Exception as exc:
        logger.exception("Compare: current craftum audit failed")
        limitations.append(f"Current craftum audit failed: {exc}")
        current_craftum = {
            "baseline_status": "error",
            "error_message": str(exc),
            "error_type": type(exc).__name__,
            "preset": "craftum",
        }
        current_craftum = merge_report_meta(
            current_craftum,
            url,
            mode="full",
            preset="craftum",
            run_type=None,
            language=effective_lang,
        )
        _write_json(path_craft, current_craftum)

    try:
        current_visual = run_visual_audit_fn(
            url,
            settings=settings,
            effective_lang=effective_lang,
            debug_dir=debug_dir,
        )
        current_visual = merge_report_meta(
            current_visual,
            url,
            mode="visual",
            preset="general",
            run_type=None,
            language=effective_lang,
        )
        _write_json(path_vis, current_visual)
        modes_ok["visual"] = True
    except Exception as exc:
        logger.exception("Compare: current visual audit failed")
        limitations.append(f"Current visual audit failed: {exc}")
        stub = {
            "baseline_status": "error",
            "error_message": str(exc),
            "error_type": type(exc).__name__,
            "audit_type": "visual",
        }
        current_visual = merge_report_meta(
            stub,
            url,
            mode="visual",
            preset="general",
            run_type=None,
            language=effective_lang,
        )
        _write_json(path_vis, current_visual)

    if current_content is None:
        cmp_fail = {
            "url": url,
            "baseline_dir": _rel_to_project(base),
            "current_dir": _rel_to_project(out),
            "status": "failed",
            "error": "Current content audit did not complete; cannot compare.",
            "limitations": limitations,
        }
        _write_json(out / COMPARISON_JSON, cmp_fail)
        (out / COMPARISON_READABLE).write_text(
            render_comparison_markdown(
                {
                    "url": url,
                    "baseline_dir": _rel_to_project(base),
                    "current_dir": _rel_to_project(out),
                    "status": "failed",
                    "overall_change": {"direction": "unchanged", "confidence": 0.0, "summary": cmp_fail["error"]},
                    "changes": {"improved": [], "degraded": [], "unchanged": [], "new_issues": [], "resolved_issues": []},
                    "conversion_assessment": {"before": "—", "after": "—", "delta": "—"},
                    "block_assessment": {},
                    "visual": {},
                    "limitations": limitations,
                    "notes": [],
                },
            ),
            encoding="utf-8",
        )
        man = _build_compare_manifest(
            url=url,
            base=base,
            out=out,
            status="failed",
            limitations=limitations,
            modes_ok=modes_ok,
        )
        _write_json(out / COMPARE_MANIFEST_JSON, man)
        return CompareRunSummary(
            status="failed",
            exit_ok=False,
            manifest_path=out / COMPARE_MANIFEST_JSON,
            comparison_path=out / COMPARISON_JSON,
            limitations=limitations,
        )

    assert current_craftum is not None and current_visual is not None

    compare_status = "ok"
    if not modes_ok["craftum"] or not modes_ok["visual"]:
        compare_status = "partial"

    payload = build_comparison_payload(
        url=url,
        baseline_dir=_rel_to_project(base),
        output_dir=_rel_to_project(out),
        baseline_content=baseline_content,
        current_content=current_content,
        baseline_craftum=baseline_craftum,
        current_craftum=current_craftum,
        baseline_visual=baseline_visual,
        current_visual=current_visual,
        limitations=limitations,
        current_modes=modes_ok,
    )
    payload["status"] = compare_status
    payload["created_at"] = datetime.now(timezone.utc).isoformat()
    payload["project_version"] = PROJECT_VERSION

    _write_json(out / COMPARISON_JSON, payload)
    (out / COMPARISON_READABLE).write_text(render_comparison_markdown(payload), encoding="utf-8")

    man = _build_compare_manifest(
        url=url,
        base=base,
        out=out,
        status=compare_status,
        limitations=limitations + (payload.get("limitations") or []),
        modes_ok=modes_ok,
    )
    _write_json(out / COMPARE_MANIFEST_JSON, man)

    return CompareRunSummary(
        status=compare_status,
        exit_ok=True,
        manifest_path=out / COMPARE_MANIFEST_JSON,
        comparison_path=out / COMPARISON_JSON,
        limitations=list(dict.fromkeys(limitations + (payload.get("limitations") or []))),
    )


def _build_compare_manifest(
    *,
    url: str,
    base: Path,
    out: Path,
    status: str,
    limitations: list[str],
    modes_ok: dict[str, bool],
) -> dict[str, Any]:
    lim_dedup = list(dict.fromkeys(limitations))
    return {
        "url": url,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline_dir": _rel_to_project(base),
        "baseline_manifest_ref": _rel_to_project(base / MANIFEST_JSON),
        "compare_output_dir": _rel_to_project(out),
        "status": status,
        "limitations": lim_dedup,
        "current_modes_ok": modes_ok,
        "artifacts": {
            "current_content_json": _rel_to_project(out / CURRENT_CONTENT_JSON),
            "current_content_readable": _rel_to_project(out / CURRENT_CONTENT_READABLE),
            "current_craftum_json": _rel_to_project(out / CURRENT_CRAFTUM_JSON),
            "current_visual_json": _rel_to_project(out / CURRENT_VISUAL_JSON),
            "comparison_json": _rel_to_project(out / COMPARISON_JSON),
            "comparison_readable": _rel_to_project(out / COMPARISON_READABLE),
        },
        "project_version": PROJECT_VERSION,
        "git_commit": _try_git_commit(),
    }
