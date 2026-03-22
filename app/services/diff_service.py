"""Audit-vs-audit diff (shared by CLI ``--diff`` and HTTP ``GET /audits/diff``)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.lang import normalize_lang
from app.services.diff_summary import build_diff_payload_for_llm, summarize_diff_with_llm


def _missing_blocks_set(report: dict[str, Any]) -> set[str]:
    ba = report.get("block_analysis")
    if not isinstance(ba, dict):
        return set()
    mb = ba.get("missing_blocks")
    if not isinstance(mb, list):
        return set()
    return {str(x).strip() for x in mb if str(x).strip()}


def _next_block_type(report: dict[str, Any]) -> str:
    ba = report.get("block_analysis")
    if not isinstance(ba, dict):
        return ""
    nb = ba.get("next_block")
    if not isinstance(nb, dict):
        return ""
    return str(nb.get("type", "")).strip()


def _roadmap_actions_set(report: dict[str, Any]) -> set[str]:
    ar = report.get("action_roadmap")
    if not isinstance(ar, list):
        return set()
    out: set[str] = set()
    for item in ar:
        if isinstance(item, dict):
            a = str(item.get("action", "")).strip()
            if a:
                out.add(a)
    return out


def _roadmap_actions_ordered(report: dict[str, Any]) -> list[str]:
    ar = report.get("action_roadmap")
    if not isinstance(ar, list):
        return []
    out: list[str] = []
    for item in ar:
        if isinstance(item, dict):
            a = str(item.get("action", "")).strip()
            if a:
                out.append(a)
    return out


def compute_progress_score(report_old: dict[str, Any], report_new: dict[str, Any]) -> int:
    """Simple score from diff only; clamped to [-100, 100]."""
    s_old = _missing_blocks_set(report_old)
    s_new = _missing_blocks_set(report_new)
    t_old = _next_block_type(report_old)
    t_new = _next_block_type(report_new)
    r_old = _roadmap_actions_set(report_old)
    r_new = _roadmap_actions_set(report_new)

    score = 0
    for _ in s_old - s_new:
        score += 10
    for _ in s_new - s_old:
        score -= 5
    if t_old != t_new:
        score += 5
    for _ in r_new - r_old:
        score += 5
    for _ in r_old - r_new:
        score -= 3
    return max(-100, min(100, score))


def _format_signed_score(score: int) -> str:
    if score > 0:
        return f"+{score}"
    return str(score)


def _progress_summary_line(score: int) -> str:
    if score > 20:
        return "Сайт стал заметно лучше с точки зрения конверсии"
    if score > 0:
        return "Есть небольшие улучшения"
    if score == 0:
        return "Без изменений"
    return "Изменения ухудшили структуру лендинга"


def _change_summary_verdict(progress: int) -> str:
    if progress > 20:
        return "Сайт стал заметно лучше"
    if progress >= 0:
        return "Есть улучшения, но требуется доработка"
    return "Изменения ухудшили структуру"


def _change_summary_body(
    added_mb: list[str],
    removed_mb: list[str],
    added_r: list[str],
    removed_r: list[str],
    t_old: str,
    t_new: str,
    progress: int,
    llm_summary: str | None,
) -> str:
    buf = io.StringIO()
    if (llm_summary or "").strip():
        buf.write(llm_summary.strip())
        buf.write("\n")
        return buf.getvalue()
    if added_mb:
        buf.write(f"Добавлены блоки: {', '.join(added_mb)}\n")
    if removed_mb:
        buf.write(f"Удалены блоки: {', '.join(removed_mb)}\n")
    if added_mb and removed_mb:
        buf.write("Изменены блоки: обновлён список недостающих блоков.\n")
    if added_r:
        buf.write(f"Добавлены действия: {', '.join(added_r)}\n")
    if removed_r:
        buf.write(f"Убраны действия: {', '.join(removed_r)}\n")
    if t_old != t_new:
        buf.write(f"Изменён следующий шаг: было {t_old or '—'} → стало {t_new or '—'}\n")
    buf.write(_change_summary_verdict(progress))
    buf.write("\n")
    return buf.getvalue()


def _diff_block_text(
    added_mb: list[str],
    removed_mb: list[str],
    t_old: str,
    t_new: str,
    added_r: list[str],
    removed_r: list[str],
) -> str:
    buf = io.StringIO()
    buf.write("=== DIFF ===\n\n")
    buf.write("BLOCKS:\n")
    if added_mb or removed_mb:
        for line in added_mb:
            buf.write(f"* {line}\n")
        for line in removed_mb:
            buf.write(f"- {line}\n")
    else:
        buf.write("(no changes)\n")
    buf.write("\n")
    buf.write("NEXT ACTION:\n")
    if t_old != t_new:
        buf.write(f"было: {t_old or '—'}\n")
        buf.write(f"стало: {t_new or '—'}\n")
    else:
        buf.write("(без изменений)\n")
    buf.write("\n")
    buf.write("ROADMAP CHANGES:\n")
    if added_r or removed_r:
        for line in added_r:
            buf.write(f"* {line}\n")
        for line in removed_r:
            buf.write(f"- {line}\n")
    else:
        buf.write("(no changes)\n")
    return buf.getvalue()


def _progress_block_strings(score: int) -> tuple[str, dict[str, Any]]:
    """Full PROGRESS block text and structured fields for JSON."""
    lines = [
        "",
        "=== PROGRESS ===",
        "",
        f"Score: {_format_signed_score(score)}",
        "",
        "Interpretation:",
        "+20 и выше → заметное улучшение",
        "0 → без изменений",
        "отрицательное → стало хуже",
        "",
        _progress_summary_line(score),
    ]
    text = "\n".join(lines) + "\n"
    progress_obj: dict[str, Any] = {
        "score": score,
        "score_display": _format_signed_score(score),
        "interpretation": "+20 и выше → заметное улучшение\n0 → без изменений\nотрицательное → стало хуже",
        "summary_line": _progress_summary_line(score),
    }
    return text, progress_obj


def compute_audit_diff_output(report_old: dict[str, Any], report_new: dict[str, Any]) -> dict[str, Any]:
    """
    Same semantics as CLI ``--diff``: change summary (LLM or rule-based), technical diff, progress.

    Returns keys: ``change_summary``, ``diff``, ``progress_text``, ``progress`` (object).
    """
    s_old = _missing_blocks_set(report_old)
    s_new = _missing_blocks_set(report_new)
    added_mb = sorted(s_new - s_old)
    removed_mb = sorted(s_old - s_new)

    t_old = _next_block_type(report_old)
    t_new = _next_block_type(report_new)

    r_old = _roadmap_actions_set(report_old)
    r_new = _roadmap_actions_set(report_new)
    added_r = sorted(r_new - r_old)
    removed_r = sorted(r_old - r_new)

    progress = compute_progress_score(report_old, report_new)
    diff_lang = normalize_lang(report_new.get("language")) or "ru"
    settings = get_settings()
    diff_payload = build_diff_payload_for_llm(
        sorted(s_old),
        sorted(s_new),
        _roadmap_actions_ordered(report_old),
        _roadmap_actions_ordered(report_new),
        added_mb,
        removed_mb,
        added_r,
        removed_r,
        t_old,
        t_new,
        report_old,
        report_new,
    )
    llm_summary = summarize_diff_with_llm(
        report_old,
        report_new,
        diff_payload,
        diff_lang,
        settings,
    )

    summary_inner = _change_summary_body(
        added_mb,
        removed_mb,
        added_r,
        removed_r,
        t_old,
        t_new,
        progress,
        llm_summary=llm_summary or None,
    )
    change_summary_block = "=== CHANGE SUMMARY ===\n\n" + summary_inner + "\n"

    diff_text = _diff_block_text(added_mb, removed_mb, t_old, t_new, added_r, removed_r)
    progress_text, progress_obj = _progress_block_strings(progress)

    return {
        "change_summary": change_summary_block,
        "diff": diff_text,
        "progress_text": progress_text,
        "progress": progress_obj,
    }


def load_audit_json_file(path: Path) -> dict[str, Any]:
    """Load audit JSON from path (raises FileNotFoundError, json.JSONDecodeError, OSError)."""
    if not path.is_file():
        raise FileNotFoundError(str(path))
    with path.open(encoding="utf-8") as f:
        return json.load(f)
