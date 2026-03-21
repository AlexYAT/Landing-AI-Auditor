"""Human-readable view of landing audit JSON (optional presentation layer)."""

from __future__ import annotations

from typing import Any


def _issue_line(item: dict[str, Any]) -> str:
    severity = str(item.get("severity", "")).strip().upper() or "?"
    kind = str(item.get("category", item.get("type", ""))).strip().upper() or "OTHER"
    desc = str(item.get("title", item.get("description", ""))).strip() or "—"
    return f"🔥 {severity} {kind}: {desc}"


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

    return {
        "summary": raw_summary,
        "issues_readable": issues_readable,
        "recommendations_readable": recommendations_readable,
        "quick_wins": report.get("quick_wins", []),
    }
