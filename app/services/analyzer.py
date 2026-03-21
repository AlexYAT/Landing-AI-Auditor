"""Audit orchestration and output normalization."""

from __future__ import annotations

import logging
from typing import Any

from app.core.lang import DEFAULT_LANG, get_analyzer_messages, normalize_lang
from app.core.user_task import sanitize_user_task
from app.core.models import AuditIssue, AuditResult, AuditSummary, QuickWin, Recommendation
from app.providers.llm import OpenAiAuditProvider

logger = logging.getLogger(__name__)


class AnalyzerError(Exception):
    """Raised when audit analysis fails validation."""


ALLOWED_SEVERITIES = {"high", "medium", "low"}
ALLOWED_PRIORITIES = {"high", "medium", "low"}
ALLOWED_CATEGORIES = {"clarity", "cta", "trust", "friction", "structure", "forms", "offer", "other"}


def _as_list(data: Any) -> list[Any]:
    """Return list or empty list for invalid values."""
    return data if isinstance(data, list) else []


def _as_str(data: Any) -> str:
    """Return stripped string or empty fallback."""
    return " ".join(data.split()) if isinstance(data, str) else ""


def _normalize_choice(value: str, allowed: set[str], default: str) -> str:
    """Normalize enum-like field with fallback."""
    lowered = _as_str(value).lower()
    return lowered if lowered in allowed else default


def _as_str_list(data: Any) -> list[str]:
    """Normalize string list and drop empty items."""
    return [_as_str(item) for item in _as_list(data) if _as_str(item)]


def _build_fallback_summary(lang: str) -> AuditSummary:
    """Return safe fallback summary when model output is missing."""
    msg = get_analyzer_messages(lang)
    return AuditSummary(
        overall_assessment=msg["summary_partial"],
        primary_conversion_goal_guess=msg["goal_unknown"],
        top_strengths=[],
        top_risks=[msg["risk_model"]],
    )


def validate_and_normalize_audit_result(data: dict[str, Any], lang: str = DEFAULT_LANG) -> AuditResult:
    """Normalize partially-valid model JSON into stable audit dataclasses."""
    msg = get_analyzer_messages(lang)
    summary_raw = data.get("summary")
    if not isinstance(summary_raw, dict):
        summary = _build_fallback_summary(lang)
    else:
        summary = AuditSummary(
            overall_assessment=_as_str(summary_raw.get("overall_assessment")),
            primary_conversion_goal_guess=_as_str(summary_raw.get("primary_conversion_goal_guess")),
            top_strengths=_as_str_list(summary_raw.get("top_strengths")),
            top_risks=_as_str_list(summary_raw.get("top_risks")),
        )
        if not summary.overall_assessment:
            summary.overall_assessment = msg["assessment_weak"]
        if not summary.primary_conversion_goal_guess:
            summary.primary_conversion_goal_guess = msg["goal_infer"]

    issues: list[AuditIssue] = []
    for idx, item in enumerate(_as_list(data.get("issues")), start=1):
        if not isinstance(item, dict):
            continue
        issue_id = _as_str(item.get("id")) or f"issue_{idx}"
        issues.append(
            AuditIssue(
                id=issue_id,
                title=_as_str(item.get("title")) or f"{msg['issue_prefix']} {idx}",
                severity=_normalize_choice(_as_str(item.get("severity")), ALLOWED_SEVERITIES, "medium"),
                category=_normalize_choice(_as_str(item.get("category")), ALLOWED_CATEGORIES, "other"),
                evidence=_as_str(item.get("evidence")) or msg["evidence_missing"],
                impact=_as_str(item.get("impact")) or msg["impact_generic"],
                recommendation=_as_str(item.get("recommendation")) or msg["recommendation_generic"],
            )
        )

    recommendations: list[Recommendation] = []
    for item in _as_list(data.get("recommendations")):
        if not isinstance(item, dict):
            continue
        recommendations.append(
            Recommendation(
                priority=_normalize_choice(_as_str(item.get("priority")), ALLOWED_PRIORITIES, "medium"),
                title=_as_str(item.get("title")),
                action=_as_str(item.get("action")),
                expected_impact=_as_str(item.get("expected_impact")),
            )
        )

    quick_wins: list[QuickWin] = []
    for idx, item in enumerate(_as_list(data.get("quick_wins")), start=1):
        if not isinstance(item, dict):
            continue
        quick_wins.append(
            QuickWin(
                title=_as_str(item.get("title")) or f"{msg['quick_win_prefix']} {idx}",
                action=_as_str(item.get("action")),
                why_it_matters=_as_str(item.get("why_it_matters")),
            )
        )

    return AuditResult(
        summary=summary,
        issues=issues,
        recommendations=recommendations,
        quick_wins=quick_wins,
    )


def analyze_landing(
    parsed_landing: dict[str, Any],
    user_task: str | None,
    provider: OpenAiAuditProvider,
    lang: str = DEFAULT_LANG,
) -> AuditResult:
    """Run LLM audit and normalize response into strongly typed result."""
    effective_lang = normalize_lang(lang)
    sanitized = sanitize_user_task(user_task)
    logger.info(f"Task-aware analysis enabled: {'yes' if sanitized else 'no'}")
    if sanitized:
        preview = sanitized if len(sanitized) <= 120 else f"{sanitized[:120]}..."
        logger.info(f'Task: "{preview}"')
    try:
        raw = provider.analyze_landing(
            parsed_data=parsed_landing,
            sanitized_user_task=sanitized,
            lang=effective_lang,
        )
        return validate_and_normalize_audit_result(raw, lang=effective_lang)
    except Exception as exc:
        raise AnalyzerError(f"Failed to analyze and normalize LLM output: {exc}") from exc
