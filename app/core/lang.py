"""Language codes and normalization for multi-language audit output."""

from __future__ import annotations

DEFAULT_LANG: str = "ru"
SUPPORTED_LANGS: frozenset[str] = frozenset({"ru", "en"})


def normalize_lang(lang: str | None) -> str:
    """
    Normalize user-provided language code.

    Returns a supported code; unsupported or empty values map to DEFAULT_LANG ("ru").
    """
    if lang is None:
        return DEFAULT_LANG
    if not isinstance(lang, str):
        return DEFAULT_LANG
    code = lang.strip().lower()
    return code if code in SUPPORTED_LANGS else DEFAULT_LANG


def resolve_effective_lang(cli_lang: str | None, env_lang: str) -> str:
    """
    Resolve effective language with priority: CLI arg > env DEFAULT_LANG > ru.

    cli_lang: value from --lang (None when not passed).
    env_lang: already-normalized default from config (env DEFAULT_LANG or ru).
    """
    if cli_lang is not None and str(cli_lang).strip():
        return normalize_lang(cli_lang)
    return normalize_lang(env_lang)


def used_language_fallback(requested: str | None) -> bool:
    """True if the raw CLI value is not a supported language code (after strip/lower)."""
    if requested is None:
        return False
    if not isinstance(requested, str):
        return True
    raw = requested.strip().lower()
    return raw not in SUPPORTED_LANGS


# Analyzer / normalization fallbacks when LLM omits text (keyed by effective lang code).
ANALYZER_FALLBACK_MESSAGES: dict[str, dict[str, str]] = {
    "ru": {
        "summary_partial": "Недостаточно структурированного summary от модели; применён частичный fallback.",
        "goal_unknown": "Недостаточно данных в ответе модели.",
        "risk_model": "В ответе модели не хватило полных данных summary.",
        "assessment_weak": "Недостаточно оснований для уверенной общей оценки.",
        "goal_infer": "Недостаточно данных, чтобы вывести одну основную конверсионную цель.",
        "evidence_missing": "Доказательства моделью явно не приведены.",
        "impact_generic": "Возможное влияние на конверсию есть, уверенность ограничена.",
        "recommendation_generic": "Уточните проблему конкретным действием.",
        "quick_win_prefix": "Быстрая победа",
        "issue_prefix": "Проблема",
    },
    "en": {
        "summary_partial": "Insufficient structured summary from model; partial fallback applied.",
        "goal_unknown": "Not enough evidence in LLM output.",
        "risk_model": "Model response lacked complete summary details.",
        "assessment_weak": "Insufficient evidence for confident overall assessment.",
        "goal_infer": "Not enough evidence to infer a single primary conversion goal.",
        "evidence_missing": "Evidence not explicitly provided by model.",
        "impact_generic": "Potential conversion impact exists, confidence is limited.",
        "recommendation_generic": "Refine this issue with a concrete action.",
        "quick_win_prefix": "Quick win",
        "issue_prefix": "Issue",
    },
}


def get_analyzer_messages(lang: str) -> dict[str, str]:
    """Return localized strings for analyzer normalization fallbacks."""
    code = normalize_lang(lang)
    return ANALYZER_FALLBACK_MESSAGES.get(code, ANALYZER_FALLBACK_MESSAGES[DEFAULT_LANG])
