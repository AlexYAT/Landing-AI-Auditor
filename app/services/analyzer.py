"""Audit orchestration and output normalization."""

from __future__ import annotations

from typing import Any

from app.core.models import AuditIssue, AuditResult, QuickWin, Recommendation
from app.providers.llm import OpenAiAuditProvider


class AnalyzerError(Exception):
    """Raised when audit analysis fails validation."""


def _as_list(data: Any) -> list[Any]:
    """Return list or empty list for invalid values."""
    return data if isinstance(data, list) else []


def _as_str(data: Any) -> str:
    """Return stripped string or empty fallback."""
    return data.strip() if isinstance(data, str) else ""


def analyze_landing(parsed_landing: dict[str, Any], user_task: str, provider: OpenAiAuditProvider) -> AuditResult:
    """Run LLM audit and normalize response into strongly typed result."""
    raw = provider.analyze_landing(parsed_data=parsed_landing, user_task=user_task)

    issues = [
        AuditIssue(
            title=_as_str(item.get("title")),
            severity=_as_str(item.get("severity")) or "medium",
            evidence=_as_str(item.get("evidence")),
            impact=_as_str(item.get("impact")),
        )
        for item in _as_list(raw.get("issues"))
        if isinstance(item, dict)
    ]

    recommendations = [
        Recommendation(
            title=_as_str(item.get("title")),
            rationale=_as_str(item.get("rationale")),
            expected_impact=_as_str(item.get("expected_impact")),
            priority=_as_str(item.get("priority")) or "medium",
        )
        for item in _as_list(raw.get("recommendations"))
        if isinstance(item, dict)
    ]

    quick_wins = [
        QuickWin(
            action=_as_str(item.get("action")),
            why_it_matters=_as_str(item.get("why_it_matters")),
        )
        for item in _as_list(raw.get("quick_wins"))
        if isinstance(item, dict)
    ]

    result = AuditResult(
        summary=_as_str(raw.get("summary")),
        issues=issues,
        recommendations=recommendations,
        quick_wins=quick_wins,
    )

    if not result.summary:
        raise AnalyzerError("Invalid LLM response: 'summary' is missing or empty.")

    return result
