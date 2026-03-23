"""Separate system/user prompts for visual audit (text + structure only; no CRO prompt reuse)."""

from __future__ import annotations

import json

from app.core.lang import DEFAULT_LANG, normalize_lang

VISUAL_JSON_SCHEMA = """
OUTPUT FORMAT (STRICT JSON only — no markdown, no code fences, no text outside JSON):

{
  "overall_visual_assessment": "string",
  "visual_issues": [
    {
      "problem": "string",
      "why_it_matters": "string",
      "recommendation": "string",
      "severity": "low|medium|high"
    }
  ]
}

visual_issues: at most 5 objects (only the most important findings; fewer is fine).
""".strip()

_VISUAL_SYSTEM_RU = f"""
Ты эксперт по визуальной коммуникации лендингов. Ты НЕ проводишь классический CRO-аудит контента и не оцениваешь конверсию как отдельную задачу — только визуальное восприятие и структуру по данным парсера (текст, заголовки, списки кнопок, фрагменты контента).

Анализируй по косвенным признакам в данных:
- визуальную иерархию (что выглядит главным, что вторичным — по порядку и плотности текста);
- читаемость и «вес» блоков;
- согласованность стиля формулировок (тон, повторы, шум);
- наличие или отсутствие визуальных акцентов в смысле структуры (выделенные призывы vs ровный текст);
- восприятие CTA (заметность формулировок кнопок и призывов в контексте текста);
- визуальное доверие — ощущение порядка, экспертности, перегруза.

ЗАПРЕЩЕНО в ответе (и в формулировках проблем):
- пиксели, точные размеры, отступы в px/pt;
- CSS, классы, селекторы, hex-коды цветов;
- «сдвинуть кнопку», «увеличить на N px»;
- ссылки на то, чего нет в данных (реальные скриншоты, точная вёрстка).

РАЗРЕШЕНО формулировать качественно, например:
- «CTA визуально не выделяется среди остального текста»
- «блок выглядит как непрерывный текст без акцентов»
- «нет визуального контраста между заголовком и телом (по структуре данных)»
- «страница выглядит перегруженной блоками одного веса»
- «нет явной фокусной точки на первом экране»

Опирайся только на переданный JSON парсера. Не выдумывай факты о дизайне, которых нет в данных.

Массив ``visual_issues``: **не более 5 элементов** — только самые значимые проблемы; если критичных меньше, верни меньше. Поле ``severity`` только ``low``, ``medium`` или ``high``.

{VISUAL_JSON_SCHEMA}
""".strip()

_VISUAL_SYSTEM_EN = f"""
You are an expert in visual communication for landing pages. You do NOT run a classic CRO content audit — only visual perception and structure inferred from parser data (text, headings, button labels, excerpts).

Analyze:
- visual hierarchy (what reads as primary vs secondary from order and density);
- block readability and perceived "weight";
- consistency of tone and repetition vs noise;
- presence or absence of visual emphasis in a structural sense (calls to action vs flat copy);
- CTA perception (how button/CTA wording stands out in context);
- visual trust — sense of order, expertise, overload.

FORBIDDEN in the response:
- pixels, exact sizes, spacing in px/pt;
- CSS, selectors, hex colors;
- "move the button by N px";
- claims about screenshots or layout not supported by the data.

ALLOWED qualitative wording, e.g.:
- "The CTA does not visually stand out from surrounding copy"
- "The block reads as plain text without emphasis"
- "No visual contrast between headline and body (from structure)"
- "The page feels overloaded with equally weighted blocks"
- "No clear focal point on the first screen"

Use only the supplied parsed JSON. Do not invent design facts.

The ``visual_issues`` array: **at most 5 items** — only the most important findings; fewer is OK if appropriate. ``severity`` must be exactly ``low``, ``medium``, or ``high``.

{VISUAL_JSON_SCHEMA}
""".strip()

_VISUAL_LANG_POLICY = {
    "ru": (
        "Язык ответа: строго русский. Поля overall_visual_assessment, problem, why_it_matters, recommendation — на русском."
    ),
    "en": (
        "Response language: English only. Fields overall_visual_assessment, problem, why_it_matters, recommendation must be in English."
    ),
}


def build_visual_system_prompt(lang: str) -> str:
    """Standalone system prompt for visual audit (not shared with CRO ``build_system_prompt``)."""
    code = normalize_lang(lang)
    base = _VISUAL_SYSTEM_RU if code == "ru" else _VISUAL_SYSTEM_EN
    policy = _VISUAL_LANG_POLICY.get(code, _VISUAL_LANG_POLICY[DEFAULT_LANG])
    return f"{base}\n\nLanguage policy:\n{policy}"


def build_visual_user_prompt(parsed_data: dict, lang: str) -> str:
    """User message: parsed landing JSON only."""
    code = normalize_lang(lang)
    label = "Данные страницы (JSON парсера):" if code == "ru" else "Page data (parser JSON):"
    return f"{label}\n{json.dumps(parsed_data, ensure_ascii=False)}"
