"""Human-readable view of landing audit JSON (optional presentation layer)."""

from __future__ import annotations

from typing import Any

from app.core.lang import normalize_lang

_REWRITE_KEYS = ("hero", "cta", "trust")

_CRAFTUM_PLAN_LABELS = {
    "ru": {
        "title": "Рекомендуемые блоки для добавления",
        "block_type": "Тип блока",
        "goal": "Зачем",
        "placement": "Куда вставить",
        "fields": "Что заполнить",
        "content_example": "Пример",
        "style_guidance": "Стиль (общие указания, без пикселей)",
        "validation_check": "Как проверить",
        "empty": "(В ответе нет элементов craftum_block_plan.)",
    },
    "en": {
        "title": "Suggested blocks to add",
        "block_type": "Block type",
        "goal": "Why",
        "placement": "Where to insert",
        "fields": "What to fill in",
        "content_example": "Example",
        "style_guidance": "Style (high-level, no pixels)",
        "validation_check": "How to verify",
        "empty": "(No craftum_block_plan items in the response.)",
    },
}


def _txt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return str(v).strip()


def _safe_confidence(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return f


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
            "confidence": 0.0,
            "why_now": "",
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
        "why_now": _txt(nb.get("why_now")),
        "placement": _txt(nb.get("placement")),
        "example": _txt(nb.get("example")),
        "implementation_for_craftum": _txt(nb.get("implementation_for_craftum")),
        "expected_impact": _txt(nb.get("expected_impact")),
        "confidence": _safe_confidence(nb.get("confidence")),
    }
    return {"missing_blocks": missing_list, "next_action": next_action}


def _next_action_text_block(next_action: dict[str, Any]) -> str:
    """Multiline block for CLI/markdown (same spirit as recommendations)."""
    sections: list[str] = []
    if next_action.get("type"):
        sections.append(f"Тип блока:\n{next_action['type']}")
    if next_action.get("priority"):
        sections.append(f"Приоритет:\n{next_action['priority']}")
    if next_action.get("reason"):
        sections.append(f"Причина:\n{next_action['reason']}")
    if next_action.get("why_now"):
        sections.append(f"Почему сейчас:\n{next_action['why_now']}")
    if next_action.get("placement"):
        sections.append(f"Где вставить:\n{next_action['placement']}")
    if next_action.get("example"):
        sections.append(f"Пример текста:\n{next_action['example']}")
    if next_action.get("implementation_for_craftum"):
        sections.append(f"Как внедрить:\n{next_action['implementation_for_craftum']}")
    if next_action.get("expected_impact"):
        sections.append(f"Ожидаемый эффект:\n{next_action['expected_impact']}")
    conf = next_action.get("confidence")
    if isinstance(conf, (int, float)) and float(conf) > 0:
        sections.append(f"Уверенность:\n{float(conf)}")
    if not sections:
        return ""
    body = "\n\n".join(sections)
    return f"---\n{body}\n---"


def _build_action_roadmap_steps(report: dict) -> list[dict[str, Any]]:
    """Up to 3 roadmap steps from ``action_roadmap`` for UI/CLI."""
    ar = report.get("action_roadmap")
    if not isinstance(ar, list) or not ar:
        return []
    steps: list[dict[str, Any]] = []
    for item in ar[:3]:
        if not isinstance(item, dict):
            continue
        step_raw = item.get("step")
        try:
            step_n = int(step_raw) if step_raw is not None else len(steps) + 1
        except (TypeError, ValueError):
            step_n = len(steps) + 1
        action = _txt(item.get("action"))
        reason = _txt(item.get("reason"))
        exp = _txt(item.get("expected_impact"))
        if not action and not reason and not exp:
            continue
        pr = _txt(item.get("priority")).lower() or "medium"
        steps.append(
            {
                "step": step_n,
                "action": action,
                "reason": reason,
                "expected_impact": exp,
                "priority": pr,
            }
        )
    return steps


def _format_action_roadmap_readable(steps: list[dict[str, Any]]) -> str:
    """Plain text for CLI / save-report (=== ACTION ROADMAP ===)."""
    if not steps:
        return ""
    lines: list[str] = []
    for s in steps:
        pr = str(s.get("priority", "")).strip().upper() or "?"
        act = str(s.get("action", "")).strip()
        step_n = s.get("step", "")
        lines.append(f"{step_n}. [{pr}] {act}".rstrip())
        rs = str(s.get("reason", "")).strip()
        if rs:
            lines.append(f"   Причина: {rs}")
        ei = str(s.get("expected_impact", "")).strip()
        if ei:
            lines.append(f"   Эффект: {ei}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _craftum_block_plan_items(report: dict) -> list[dict[str, Any]]:
    """Normalized list of craftum block planner rows from report dict."""
    raw = report.get("craftum_block_plan")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        fr = item.get("fields")
        if isinstance(fr, list):
            fields = [_txt(x) for x in fr if _txt(x)]
        else:
            fields = []
        out.append(
            {
                "block_type": _txt(item.get("block_type")),
                "goal": _txt(item.get("goal")),
                "placement": _txt(item.get("placement")),
                "fields": fields,
                "content_example": _txt(item.get("content_example")),
                "style_guidance": _txt(item.get("style_guidance")),
                "validation_check": _txt(item.get("validation_check")),
            }
        )
    return out


def _format_craftum_block_plan_readable(report: dict) -> str:
    """Plain-text section for CLI / markdown (Craftum Block Planner)."""
    code = normalize_lang(report.get("language"))
    L = _CRAFTUM_PLAN_LABELS.get(code, _CRAFTUM_PLAN_LABELS["en"])
    items = _craftum_block_plan_items(report)
    if not items:
        return ""
    blocks: list[str] = []
    for idx, b in enumerate(items, start=1):
        parts: list[str] = [f"### {idx}."]
        bt = b.get("block_type") or "—"
        parts.append(f"{L['block_type']}:\n{bt}")
        if b.get("goal"):
            parts.append(f"{L['goal']}:\n{b['goal']}")
        if b.get("placement"):
            parts.append(f"{L['placement']}:\n{b['placement']}")
        flds = b.get("fields") or []
        if flds:
            lines = "\n".join(f"* {line}" for line in flds)
            parts.append(f"{L['fields']}:\n{lines}")
        if b.get("content_example"):
            parts.append(f"{L['content_example']}:\n{b['content_example']}")
        if b.get("style_guidance"):
            parts.append(f"{L['style_guidance']}:\n{b['style_guidance']}")
        if b.get("validation_check"):
            parts.append(f"{L['validation_check']}:\n{b['validation_check']}")
        blocks.append("\n\n".join(parts))
    return f"{L['title']}\n\n" + "\n\n---\n\n".join(blocks)


def craftum_block_plan_section_for_preset(report: dict) -> str:
    """
    Readable Craftum Block Planner section when preset is craftum: data or empty notice.

    For non-craftum presets returns empty string (callers should not print a heading).
    """
    if str(report.get("preset", "")).lower() != "craftum":
        return ""
    code = normalize_lang(report.get("language"))
    L = _CRAFTUM_PLAN_LABELS.get(code, _CRAFTUM_PLAN_LABELS["en"])
    body = _format_craftum_block_plan_readable(report)
    if body.strip():
        return body
    return f"{L['title']}\n\n{L['empty']}"


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
    ar_steps = _build_action_roadmap_steps(report)
    action_roadmap_readable = _format_action_roadmap_readable(ar_steps)

    cbi = _craftum_block_plan_items(report)
    return {
        "summary": raw_summary,
        "issues_readable": issues_readable,
        "recommendations_readable": recommendations_readable,
        "quick_wins": report.get("quick_wins", []),
        "rewrite_texts_readable": _normalize_rewrite_texts_readable(report),
        "block_analysis_readable": bar,
        "next_action_readable": next_action_readable,
        "action_roadmap_steps": ar_steps,
        "action_roadmap_readable": action_roadmap_readable,
        "craftum_block_plan_items": cbi,
        "craftum_block_plan_readable": _format_craftum_block_plan_readable(report),
        "craftum_block_plan_section": craftum_block_plan_section_for_preset(report),
    }


_VISUAL_READABLE_LABELS = {
    "ru": {
        "header": "=== VISUAL AUDIT ===",
        "overall": "Общая оценка",
        "problems": "Проблемы",
        "problem": "Проблема",
        "why": "Почему важно",
        "recommendation": "Рекомендация",
        "severity": "Серьёзность",
    },
    "en": {
        "header": "=== VISUAL AUDIT ===",
        "overall": "Overall assessment",
        "problems": "Issues",
        "problem": "Problem",
        "why": "Why it matters",
        "recommendation": "Recommendation",
        "severity": "Severity",
    },
}


def format_visual_audit_readable(report: dict[str, Any], lang: str | None = None) -> str:
    """
    Plain-text visual audit for CLI / ``--save-report`` (visual mode only).

    Expects keys ``overall_visual_assessment`` and ``visual_issues`` (and optional ``audit_type``).
    """
    code = normalize_lang(lang) if lang is not None else normalize_lang(report.get("language"))
    L = _VISUAL_READABLE_LABELS.get(code, _VISUAL_READABLE_LABELS["en"])
    lines: list[str] = [L["header"], ""]
    lines.append(f"{L['overall']}:")
    lines.append(_txt(report.get("overall_visual_assessment")) or "—")
    lines.append("")
    lines.append(f"{L['problems']}:")
    raw = report.get("visual_issues")
    if not isinstance(raw, list) or not raw:
        lines.append("—")
        return "\n".join(lines)
    dict_items = [x for x in raw if isinstance(x, dict)]
    for idx, item in enumerate(dict_items, start=1):
        lines.append(f"{idx}.")
        lines.append(f"{L['problem']}:")
        lines.append(_txt(item.get("problem")) or "—")
        lines.append(f"{L['why']}:")
        lines.append(_txt(item.get("why_it_matters")) or "—")
        lines.append(f"{L['recommendation']}:")
        lines.append(_txt(item.get("recommendation")) or "—")
        lines.append(f"{L['severity']}: {_txt(item.get('severity')) or 'medium'}")
        lines.append("")
        if idx < len(dict_items):
            lines.append("---")
            lines.append("")
    return "\n".join(lines).rstrip()
