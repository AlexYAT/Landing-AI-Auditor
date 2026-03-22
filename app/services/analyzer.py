"""Audit orchestration and output normalization."""

from __future__ import annotations

import logging
from typing import Any, Sequence

from app.core.lang import DEFAULT_LANG, get_analyzer_messages, normalize_lang
from app.core.presets import DEFAULT_PRESET
from app.core.rewrite_targets import ALLOWED_REWRITE_TARGETS
from app.core.user_task import sanitize_user_task
from app.core.models import (
    AuditIssue,
    AuditResult,
    AuditSummary,
    ContentRewrite,
    QuickWin,
    Recommendation,
)
from app.providers.llm import OpenAiAuditProvider

logger = logging.getLogger(__name__)


class AnalyzerError(Exception):
    """Raised when audit analysis fails validation."""


ALLOWED_SEVERITIES = {"high", "medium", "low"}
ALLOWED_PRIORITIES = {"high", "medium", "low"}
ALLOWED_CATEGORIES = {"clarity", "cta", "trust", "friction", "structure", "forms", "offer", "other"}
ALLOWED_REWRITE_BLOCKS = ALLOWED_REWRITE_TARGETS


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


def _normalize_rewrites_ordered(
    data: dict[str, Any],
    requested_ordered: tuple[str, ...],
) -> list[ContentRewrite]:
    """Parse rewrites; keep first model entry per block; output order follows requested_ordered."""
    allowed = frozenset(requested_ordered)
    by_block: dict[str, ContentRewrite] = {}
    for item in _as_list(data.get("rewrites")):
        if not isinstance(item, dict):
            continue
        block = _as_str(item.get("block")).lower()
        if block not in allowed or block in by_block:
            continue
        by_block[block] = ContentRewrite(
            block=block,
            before=_as_str(item.get("before")),
            after=_as_str(item.get("after")),
            why=_as_str(item.get("why")),
        )
    return [by_block[b] for b in requested_ordered if b in by_block]


def _normalize_rewrite_texts(data: dict[str, Any]) -> dict[str, str]:
    """Parse ``rewrite_texts`` object (hero/cta/trust paste-ready copy) from model JSON."""
    raw = data.get("rewrite_texts")
    if not isinstance(raw, dict):
        raw = {}
    return {
        "hero": _as_str(raw.get("hero")),
        "cta": _as_str(raw.get("cta")),
        "trust": _as_str(raw.get("trust")),
    }


def _as_block_text(data: Any) -> str:
    """String for block_analysis fields; preserve newlines for multi-line copy."""
    if data is None:
        return ""
    if isinstance(data, str):
        return data.strip()
    return str(data).strip()


def _normalize_block_analysis(data: dict[str, Any]) -> dict[str, Any]:
    """Parse ``block_analysis`` from model JSON; safe when missing or partial."""
    raw = data.get("block_analysis")
    if not isinstance(raw, dict):
        return {
            "blocks_detected": [],
            "missing_blocks": [],
            "next_block": {
                "type": "",
                "reason": "",
                "placement": "",
                "implementation_for_craftum": "",
                "example": "",
                "style_fit": {
                    "color_guidance": "",
                    "font_guidance": "",
                    "visual_guidance": "",
                },
            },
        }
    blocks_detected = _as_str_list(raw.get("blocks_detected"))
    missing_blocks = _as_str_list(raw.get("missing_blocks"))
    nb_raw = raw.get("next_block")
    if not isinstance(nb_raw, dict):
        nb_raw = {}
    sf_raw = nb_raw.get("style_fit")
    if not isinstance(sf_raw, dict):
        sf_raw = {}
    next_block = {
        "type": _as_block_text(nb_raw.get("type")),
        "reason": _as_block_text(nb_raw.get("reason")),
        "placement": _as_block_text(nb_raw.get("placement")),
        "implementation_for_craftum": _as_block_text(nb_raw.get("implementation_for_craftum")),
        "example": _as_block_text(nb_raw.get("example")),
        "style_fit": {
            "color_guidance": _as_block_text(sf_raw.get("color_guidance")),
            "font_guidance": _as_block_text(sf_raw.get("font_guidance")),
            "visual_guidance": _as_block_text(sf_raw.get("visual_guidance")),
        },
    }
    return {
        "blocks_detected": blocks_detected,
        "missing_blocks": missing_blocks,
        "next_block": next_block,
    }


def validate_and_normalize_audit_result(
    data: dict[str, Any],
    lang: str = DEFAULT_LANG,
    rewrite_targets: Sequence[str] | None = None,
) -> AuditResult:
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
                implementation_for_craftum=_as_str(item.get("implementation_for_craftum")),
                example_text=_as_str(item.get("example_text")),
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

    rewrites: list[ContentRewrite] = []
    if rewrite_targets:
        ordered: list[str] = []
        seen_o: set[str] = set()
        for t in rewrite_targets:
            b = _as_str(t).lower()
            if b in ALLOWED_REWRITE_BLOCKS and b not in seen_o:
                seen_o.add(b)
                ordered.append(b)
        if ordered:
            rewrites = _normalize_rewrites_ordered(data, tuple(ordered))

    rewrite_texts = _normalize_rewrite_texts(data)
    block_analysis = _normalize_block_analysis(data)

    return AuditResult(
        summary=summary,
        issues=issues,
        recommendations=recommendations,
        quick_wins=quick_wins,
        rewrites=rewrites,
        rewrite_texts=rewrite_texts,
        block_analysis=block_analysis,
    )


def analyze_landing(
    parsed_landing: dict[str, Any],
    user_task: str | None,
    provider: OpenAiAuditProvider,
    lang: str = DEFAULT_LANG,
    rewrite_targets: Sequence[str] | None = None,
    preset: str = DEFAULT_PRESET,
) -> AuditResult:
    """Run LLM audit and normalize response into strongly typed result."""
    effective_lang = normalize_lang(lang)
    sanitized = sanitize_user_task(user_task)
    logger.info(f"Task-aware analysis enabled: {'yes' if sanitized else 'no'}")
    logger.info("Preset: %s", preset)
    if rewrite_targets:
        logger.info("Rewrite targets: %s", tuple(rewrite_targets))
    if sanitized:
        preview = sanitized if len(sanitized) <= 120 else f"{sanitized[:120]}..."
        logger.info(f'Task: "{preview}"')
    try:
        raw = provider.analyze_landing(
            parsed_data=parsed_landing,
            sanitized_user_task=sanitized,
            lang=effective_lang,
            rewrite_targets=rewrite_targets,
            preset=preset,
        )
        return validate_and_normalize_audit_result(
            raw,
            lang=effective_lang,
            rewrite_targets=rewrite_targets,
        )
    except Exception as exc:
        raise AnalyzerError(f"Failed to analyze and normalize LLM output: {exc}") from exc
