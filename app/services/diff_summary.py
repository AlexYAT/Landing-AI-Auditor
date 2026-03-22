"""LLM-assisted human-readable summary for ``--diff`` (separate from main audit)."""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from app.core.config import Settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_RU = """Твоя задача — кратко объяснить изменения между двумя аудитами лендинга.

Сформируй ответ в 3 блоках:

1. Что улучшилось:

* перечисли реальные улучшения (структура, блоки, логика)

2. Что не изменилось:

* ключевые проблемы, которые остались
* если next action не изменился — явно укажи это

3. Что ещё нужно сделать:

* кратко, 1–2 пункта
* на основе нового состояния

Правила:

* не перечисляй технические diff-строки
* не повторяй один и тот же смысл
* пиши кратко и по делу
* не выдумывай фактов; опирайся только на переданные данные (контекст и diff_data)
* пиши по-русски, если аудит на русском"""

_SYSTEM_PROMPT_EN = """Your task is to briefly explain the changes between two landing page audits.

Structure your answer in 3 blocks:

1. What improved:

* list real improvements (structure, blocks, logic)

2. What did not change:

* key issues that remain
* if next action did not change — state this explicitly

3. What still needs to be done:

* briefly, 1–2 bullet points
* based on the new state

Rules:

* do not list technical diff strings
* do not repeat the same idea twice
* write concisely and to the point
* do not invent facts; use only the provided data (context and diff_data)
* write in English"""


def _compact_report_context(report: dict[str, Any]) -> dict[str, Any]:
    """Small excerpts only — avoid sending full noisy JSON."""
    out: dict[str, Any] = {}
    lang = report.get("language")
    if lang is not None:
        out["language"] = lang
    summary = report.get("summary")
    if isinstance(summary, str) and summary.strip():
        out["summary_excerpt"] = summary.strip()[:2000]
    return out


def build_diff_payload_for_llm(
    old_missing_blocks: list[str],
    new_missing_blocks: list[str],
    old_roadmap: list[str],
    new_roadmap: list[str],
    added_mb: list[str],
    removed_mb: list[str],
    added_r: list[str],
    removed_r: list[str],
    old_next_action: str,
    new_next_action: str,
    report_old: dict[str, Any],
    report_new: dict[str, Any],
) -> dict[str, Any]:
    """Compact payload for diff summary LLM (facts + tiny context snippets)."""
    return {
        "old_missing_blocks": old_missing_blocks,
        "new_missing_blocks": new_missing_blocks,
        "old_next_action": old_next_action,
        "new_next_action": new_next_action,
        "old_roadmap": old_roadmap,
        "new_roadmap": new_roadmap,
        "diff": {
            "missing_blocks_added": added_mb,
            "missing_blocks_removed": removed_mb,
            "roadmap_added": added_r,
            "roadmap_removed": removed_r,
        },
        "old_context": _compact_report_context(report_old),
        "new_context": _compact_report_context(report_new),
    }


def summarize_diff_with_llm(
    old_report: dict[str, Any],
    new_report: dict[str, Any],
    diff_data: dict[str, Any],
    lang: str,
    settings: Settings,
) -> str:
    """
    Short human-readable change summary via a separate cheap chat completion.

    On any failure or empty model output, returns ``""`` so CLI can use rule-based fallback.
    """
    if not settings.openai_api_key.strip():
        return ""
    lang_code = (lang or "ru").split("-")[0].lower()
    system = _SYSTEM_PROMPT_EN if lang_code == "en" else _SYSTEM_PROMPT_RU
    user_payload: dict[str, Any] = {"lang": lang, **diff_data}
    user_text = json.dumps(user_payload, ensure_ascii=False)
    try:
        client = OpenAI(api_key=settings.openai_api_key, timeout=float(settings.request_timeout))
        response = client.chat.completions.create(
            model=settings.diff_summary_model or "gpt-4o-mini",
            temperature=0.25,
            max_tokens=600,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": (
                        "Данные для анализа (JSON):\n"
                        if lang_code != "en"
                        else "Data to analyze (JSON):\n"
                    )
                    + user_text,
                },
            ],
        )
        content = response.choices[0].message.content
        if not content or not str(content).strip():
            return ""
        return str(content).strip()
    except Exception as exc:
        logger.debug("diff summary LLM skipped: %s", exc, exc_info=False)
        return ""
