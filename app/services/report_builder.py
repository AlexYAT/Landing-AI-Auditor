"""Human-readable view of landing audit JSON (optional presentation layer)."""

from __future__ import annotations

from typing import Any

from app.core.lang import normalize_lang

_REWRITE_KEYS = ("hero", "cta", "trust")


def _txt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return str(v).strip()


def _empty_block_analysis_readable() -> dict[str, Any]:
    return {
        "missing_blocks": [],
        "next_action": {
            "type": "",
            "priority": "",
            "reason": "",
            "placement": "",
            "example": "",
            "implementation_for_craftum": "",
            "expected_impact": "",
        },
    }


def _build_block_analysis_readable(report: dict) -> dict[str, Any]:
    """Human-readable slice of ``block_analysis`` (Next action + missing list)."""
    ba = report.get("block_analysis")
    if not isinstance(ba, dict):
        return _empty_block_analysis_readable()
    missing_raw = ba.get("missing_blocks")
    missing_list: list[str] = []
    if isinstance(missing_raw, list):
        for x in missing_raw:
            t = _txt(x)
            if t:
                missing_list.append(t)
    nb = ba.get("next_block")
    if not isinstance(nb, dict):
        nb = {}
    next_action = {
        "type": _txt(nb.get("type")),
        "priority": _txt(nb.get("priority")),
        "reason": _txt(nb.get("reason")),
        "placement": _txt(nb.get("placement")),
        "example": _txt(nb.get("example")),
        "implementation_for_craftum": _txt(nb.get("implementation_for_craftum")),
        "expected_impact": _txt(nb.get("expected_impact")),
    }
    return {"missing_blocks": missing_list, "next_action": next_action}


def _next_action_text_block(next_action: dict[str, str]) -> str:
    """Multiline block for CLI/markdown (same spirit as recommendations)."""
    sections: list[str] = []
    if next_action.get("type"):
        sections.append(f"Тип блока:\n{next_action['type']}")
    if next_action.get("priority"):
        sections.append(f"Приоритет:\n{next_action['priority']}")
    if next_action.get("reason"):
        sections.append(f"Причина:\n{next_action['reason']}")
    if next_action.get("placement"):
        sections.append(f"Где вставить:\n{next_action['placement']}")
    if next_action.get("example"):
        sections.append(f"Пример текста:\n{next_action['example']}")
    if next_action.get("implementation_for_craftum"):
        sections.append(f"Как внедрить:\n{next_action['implementation_for_craftum']}")
    if next_action.get("expected_impact"):
        sections.append(f"Ожидаемый эффект:\n{next_action['expected_impact']}")
    if not sections:
        return ""
    body = "\n\n".join(sections)
    return f"---\n{body}\n---"


def _normalize_rewrite_texts_readable(report: dict) -> dict[str, str]:
    """Hero/cta/trust strings for human-readable views; safe when missing or malformed."""
    raw = report.get("rewrite_texts")
    if not isinstance(raw, dict):
        return {k: "" for k in _REWRITE_KEYS}
    out: dict[str, str] = {}
    for key in _REWRITE_KEYS:
        v = raw.get(key)
        out[key] = str(v).strip() if v is not None else ""
    return out


def _issue_line(item: dict[str, Any]) -> str:
    severity = str(item.get("severity", "")).strip().upper() or "?"
    kind = str(item.get("category", item.get("type", ""))).strip().upper() or "OTHER"
    desc = str(item.get("title", item.get("description", ""))).strip() or "—"
    return f"🔥 {severity} {kind}: {desc}"


def format_summary_readable(summary: Any, lang: str | None = None) -> str:
    """
    Turn ``summary`` dict into plain text (aligned with demo UI sections).

    Skips empty fields/sections. Non-dict ``summary`` is returned as ``str``.
    """
    if summary is None:
        return ""
    code = normalize_lang(lang)
    if not isinstance(summary, dict):
        return str(summary)

    labels = {
        "ru": {
            "overall": "Общая оценка:",
            "goal": "Основная цель конверсии:",
            "strengths": "Сильные стороны:",
            "risks": "Риски:",
        },
        "en": {
            "overall": "Overall assessment:",
            "goal": "Primary conversion goal:",
            "strengths": "Strengths:",
            "risks": "Risks:",
        },
    }
    L = labels.get(code, labels["en"])

    parts: list[str] = []
    oa = _txt(summary.get("overall_assessment"))
    if oa:
        parts.extend([L["overall"], oa, ""])

    pg = _txt(summary.get("primary_conversion_goal_guess"))
    if pg:
        parts.extend([L["goal"], pg, ""])

    strengths: list[str] = []
    ts = summary.get("top_strengths")
    if isinstance(ts, list):
        for x in ts:
            t = _txt(x)
            if t:
                strengths.append(t)
    if strengths:
        parts.append(L["strengths"])
        for s in strengths:
            parts.append(f"* {s}")
        parts.append("")

    risks: list[str] = []
    tr = summary.get("top_risks")
    if isinstance(tr, list):
        for x in tr:
            t = _txt(x)
            if t:
                risks.append(t)
    if risks:
        parts.append(L["risks"])
        for s in risks:
            parts.append(f"* {s}")
        parts.append("")

    return "\n".join(parts).rstrip()


def _recommendation_block(rec: dict[str, Any]) -> str:
    priority = str(rec.get("priority", "")).strip()
    problem = str(rec.get("problem") or rec.get("title", "")).strip()
    solution = str(rec.get("solution") or rec.get("action", "")).strip()
    impl = str(rec.get("implementation_for_craftum", "")).strip()
    example = str(rec.get("example_text") or rec.get("example", "")).strip()
    effect = str(rec.get("expected_effect") or rec.get("expected_impact", "")).strip()

    return (
        "---\n"
        f"🔥 Приоритет: {priority}\n\n"
        f"Проблема:\n{problem}\n\n"
        f"Решение:\n{solution}\n\n"
        f"Как внедрить:\n{impl}\n\n"
        f"Пример:\n{example}\n\n"
        f"Ожидаемый эффект:\n{effect}\n"
        "---"
    )


def build_human_report(report: dict) -> dict:
    """
    Преобразовать JSON-ответ анализа в человеко-читаемый вид.

    Отсутствующие поля не приводят к ошибке (используется .get).
    """
    raw_summary = report.get("summary")

    issues_readable: list[str] = []
    for item in report.get("issues") or []:
        if isinstance(item, dict):
            issues_readable.append(_issue_line(item))

    recommendations_readable: list[str] = []
    for rec in report.get("recommendations") or []:
        if isinstance(rec, dict):
            recommendations_readable.append(_recommendation_block(rec))

    bar = _build_block_analysis_readable(report)
    next_action_readable = _next_action_text_block(bar["next_action"])

    return {
        "summary": raw_summary,
        "issues_readable": issues_readable,
        "recommendations_readable": recommendations_readable,
        "quick_wins": report.get("quick_wins", []),
        "rewrite_texts_readable": _normalize_rewrite_texts_readable(report),
        "block_analysis_readable": bar,
        "next_action_readable": next_action_readable,
    }
