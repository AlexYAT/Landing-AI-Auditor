"""Shared orchestration: parse landing + LLM audit (used by CLI and API)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.presets import normalize_preset
from app.providers.llm import OpenAiAuditProvider
from app.services.analyzer import analyze_landing, analyze_visual_landing
from app.services.parser import parse_landing
from app.services.report_builder import build_human_report

logger = logging.getLogger(__name__)


def run_landing_audit(
    url: str,
    *,
    settings: Settings,
    user_task: str | None,
    effective_lang: str,
    rewrite_targets: tuple[str, ...] | None = None,
    preset: str | None = None,
    debug_dir: str | Path | None = None,
) -> dict[str, Any]:
    """
    Fetch/parse URL, run OpenAI audit, return report dict (same shape as CLI full mode, before file export).

    ``language`` and ``preset`` are set on the returned dict.
    """
    effective_preset = normalize_preset(preset)
    parsed_landing = parse_landing(url=url, settings=settings, debug_dir=debug_dir)
    provider = OpenAiAuditProvider(settings=settings)
    audit_result = analyze_landing(
        parsed_landing=parsed_landing.to_dict(),
        user_task=user_task,
        provider=provider,
        lang=effective_lang,
        rewrite_targets=rewrite_targets,
        preset=effective_preset,
    )
    report = audit_result.to_dict()
    report["language"] = effective_lang
    report["preset"] = effective_preset
    report["report_readable"] = build_human_report(report)
    return report


def run_visual_audit(
    url: str,
    *,
    settings: Settings,
    effective_lang: str,
    debug_dir: str | Path | None = None,
) -> dict[str, Any]:
    """
    Fetch/parse URL, run visual-only LLM audit (no CRO/content audit, no presets/rewrite).

    Returns a dict with ``audit_type``, ``language``, ``overall_visual_assessment``, ``visual_issues``.
    """
    parsed_landing = parse_landing(url=url, settings=settings, debug_dir=debug_dir)
    provider = OpenAiAuditProvider(settings=settings)
    visual = analyze_visual_landing(
        parsed_landing=parsed_landing.to_dict(),
        provider=provider,
        lang=effective_lang,
    )
    report = visual.to_dict()
    report["language"] = effective_lang
    return report
