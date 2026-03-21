"""Format full audit JSON into five short lines for assignment mode."""

from __future__ import annotations

import re
from typing import Any

_FALLBACKS: tuple[str, ...] = (
    "Improve clarity of the main value proposition",
    "Strengthen call-to-action visibility and wording",
    "Add trust elements near conversion points",
    "Simplify page structure for better readability",
    "Ensure consistent visual hierarchy",
)


def _first_sentence(text: str) -> str:
    """Return at most one sentence, whitespace-normalized."""
    stripped = " ".join(text.split()).strip()
    if not stripped:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", stripped, maxsplit=1)
    return parts[0].strip()


def _strings_from_items(
    report: dict[str, Any],
    list_key: str,
    field: str,
) -> list[str]:
    """Extract non-empty one-sentence strings from report[list_key][*][field]."""
    out: list[str] = []
    raw_list = report.get(list_key)
    if not isinstance(raw_list, list):
        return out
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        val = item.get(field)
        if not isinstance(val, str):
            continue
        one = _first_sentence(val)
        if one:
            out.append(one)
    return out


def format_assignment_output(report: dict) -> list[str]:
    """
    Build exactly five short recommendation lines from a full audit report dict.

    Sources (priority order): quick_wins.action, recommendations.action,
    issues.recommendation. Deduped, then padded with fallbacks if needed.
    """
    data: dict[str, Any] = report if isinstance(report, dict) else {}

    ordered: list[str] = []
    ordered.extend(_strings_from_items(data, "quick_wins", "action"))
    ordered.extend(_strings_from_items(data, "recommendations", "action"))
    ordered.extend(_strings_from_items(data, "issues", "recommendation"))

    seen_lower: set[str] = set()
    unique: list[str] = []
    for line in ordered:
        key = line.lower()
        if key in seen_lower:
            continue
        seen_lower.add(key)
        unique.append(line)
        if len(unique) >= 5:
            return unique[:5]

    for fb in _FALLBACKS:
        if len(unique) >= 5:
            break
        key = fb.lower()
        if key in seen_lower:
            continue
        seen_lower.add(key)
        unique.append(fb)

    idx = 0
    while len(unique) < 5:
        unique.append(_FALLBACKS[idx % len(_FALLBACKS)])
        idx += 1

    return unique[:5]
