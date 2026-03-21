"""Shared orchestration: parse landing + LLM audit (used by CLI and API)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.providers.llm import OpenAiAuditProvider
from app.services.analyzer import analyze_landing
from app.services.parser import parse_landing

logger = logging.getLogger(__name__)


def run_landing_audit(
    url: str,
    *,
    settings: Settings,
    user_task: str | None,
    effective_lang: str,
    rewrite_targets: tuple[str, ...] | None = None,
    debug_dir: str | Path | None = None,
) -> dict[str, Any]:
    """
    Fetch/parse URL, run OpenAI audit, return report dict (same shape as CLI full mode, before file export).

    ``language`` is set on the returned dict to ``effective_lang``.
    """
    parsed_landing = parse_landing(url=url, settings=settings, debug_dir=debug_dir)
    provider = OpenAiAuditProvider(settings=settings)
    audit_result = analyze_landing(
        parsed_landing=parsed_landing.to_dict(),
        user_task=user_task,
        provider=provider,
        lang=effective_lang,
        rewrite_targets=rewrite_targets,
    )
    report = audit_result.to_dict()
    report["language"] = effective_lang
    return report
