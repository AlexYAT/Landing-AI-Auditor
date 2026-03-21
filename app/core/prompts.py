"""Prompt templates for LLM landing page audit."""

from __future__ import annotations

import json

from app.core.lang import DEFAULT_LANG, normalize_lang

LANG_RULES: dict[str, str] = {
    "ru": (
        "Отвечай строго на русском языке. Весь пользовательский текст в summary, issues, "
        "recommendations, quick_wins должен быть строго на русском. Не используй английский "
        "в этих полях. Если ты используешь другой язык в текстовых полях ответа, это ошибка. "
        "Все формулировки должны звучать естественно для носителя русского языка. Избегай "
        "буквального перевода. Поля severity, priority и category оставляй латиницей в значениях "
        "из схемы (high|medium|low и коды категорий)."
    ),
    "en": (
        "Respond strictly in English. All user-facing text in summary, issues, recommendations, "
        "quick_wins must be strictly in English. Do not use Russian or other languages in those "
        "fields. If you use another language in textual fields of the response, that is an error. "
        "All wording must sound natural to a native English speaker. Avoid literal translation. "
        "Keep severity, priority, and category field values exactly as in the schema "
        "(high|medium|low and category codes)."
    ),
}

USER_PROMPT_LABELS: dict[str, dict[str, str]] = {
    "ru": {
        "task": "Задача пользователя:",
        "data": "Данные лендинга (JSON):",
        "footer": "Сформируй отчёт только по этим данным и верни строгий JSON.",
    },
    "en": {
        "task": "User task:",
        "data": "Parsed landing data (JSON):",
        "footer": "Generate the audit report using only this data and return strict JSON.",
    },
}

BASE_SYSTEM_PROMPT = """
You are a Senior conversion rate optimization auditor for landing pages.

Guardrails:
- Analyze ONLY from supplied parsed landing data and user_task.
- Do NOT fabricate facts, metrics, UX test outcomes, or user behavior claims.
- Do NOT use unsupported certainty. If evidence is missing, state this explicitly in assessment/evidence.
- Recommendations must be practical and implementation-ready.
- Avoid pixel-perfect micro-advice (e.g. move button by exact pixels).

Evaluation focus:
- Clarity of value proposition
- CTA strength and prominence
- Trust and credibility
- Friction and cognitive load
- Structure and scannability
- Forms friction
- Relevance to user_task

Allowed issue categories only:
- clarity
- cta
- trust
- friction
- structure
- forms
- offer
- other

Return STRICT JSON only.
- No markdown.
- No code fences.
- No text before or after JSON.
- Always return all top-level keys with correct types.

JSON schema:
{
  "summary": {
    "overall_assessment": "string",
    "primary_conversion_goal_guess": "string",
    "top_strengths": ["string"],
    "top_risks": ["string"]
  },
  "issues": [
    {
      "id": "string",
      "title": "string",
      "severity": "high|medium|low",
      "category": "clarity|cta|trust|friction|structure|forms|offer|other",
      "evidence": "string",
      "impact": "string",
      "recommendation": "string"
    }
  ],
  "recommendations": [
    {
      "priority": "high|medium|low",
      "title": "string",
      "action": "string",
      "expected_impact": "string"
    }
  ],
  "quick_wins": [
    {
      "title": "string",
      "action": "string",
      "why_it_matters": "string"
    }
  ]
}
""".strip()


def build_system_prompt(lang: str) -> str:
    """Build full system prompt including language output policy."""
    code = normalize_lang(lang)
    rule = LANG_RULES.get(code, LANG_RULES[DEFAULT_LANG])
    return f"{BASE_SYSTEM_PROMPT}\n\nLanguage output policy:\n{rule}"


def build_user_prompt(parsed_data: dict, user_task: str, lang: str = DEFAULT_LANG) -> str:
    """Build user prompt with explicit task and parsed context."""
    code = normalize_lang(lang)
    labels = USER_PROMPT_LABELS.get(code, USER_PROMPT_LABELS[DEFAULT_LANG])
    return (
        f"{labels['task']}\n"
        f"{user_task}\n\n"
        f"{labels['data']}\n"
        f"{json.dumps(parsed_data, ensure_ascii=False)}\n\n"
        f"{labels['footer']}"
    )
