"""Landing audit presets — single source of truth and prompt add-ons."""

from __future__ import annotations

from app.core.lang import DEFAULT_LANG, normalize_lang

ALLOWED_PRESETS: frozenset[str] = frozenset({"general", "services", "expert", "course", "leadgen"})
PRESETS_API_ORDER: tuple[str, ...] = ("general", "services", "expert", "course", "leadgen")
assert frozenset(PRESETS_API_ORDER) == ALLOWED_PRESETS

DEFAULT_PRESET: str = "general"

_PRESET_ADDONS_RU: dict[str, str] = {
    "services": (
        "Сфокусируй аудит на услугах и заявках: конверсия лида, ясный исход услуги, снижение сомнений до заявки.\n"
        "Удели внимание блокам доверия (кейсы, процесс, гарантии там, где это видно в данных), "
        "снятию типичных возражений и однозначности следующего шага.\n"
        "Не ослабляй общие правила CRO и запрет на выдуманные факты."
    ),
    "expert": (
        "Сфокусируй аудит на экспертном позиционировании: личный бренд, авторитет, опыт, отличие от альтернатив.\n"
        "Проверь, насколько страница доказывает компетенцию и доверие к человеку/команде без выдуманных достижений.\n"
        "Сохрани баланс с ясностью оффера и призывом к действию."
    ),
    "course": (
        "Сфокусируй аудит на образовательном продукте: ясные результаты обучения, структура программы в тексте, "
        "работа с возражениями (время, сложность, формат), соотношение ценности и цены.\n"
        "Не придумывай отзывы или метрики; опирайся только на переданные данные."
    ),
    "leadgen": (
        "Сфокусируй аудит на агрессивной конверсии лида: минимальное трение, короткий путь до целевого действия, "
        "сильный и заметный CTA, устранение лишних отвлечений на пути к форме/кнопке.\n"
        "Сохрани требования к честности доказательств и отсутствию выдуманных фактов."
    ),
}

_PRESET_ADDONS_EN: dict[str, str] = {
    "services": (
        "Focus the audit on service/lead conversion: lead capture, a clear service outcome, and reducing hesitation "
        "before the request.\n"
        "Emphasize trust blocks visible in the data (process, proof types, clarity of what happens after contact) and "
        "removing ambiguity in the next step.\n"
        "Do not relax global CRO rules or the ban on fabricated facts."
    ),
    "expert": (
        "Focus the audit on expert-led positioning: personal brand, authority, experience, and differentiation.\n"
        "Assess how well the page proves credibility without inventing achievements.\n"
        "Keep balance with offer clarity and a strong call-to-action."
    ),
    "course": (
        "Focus the audit on course/education offers: learning outcomes, structure in copy, objections (time, difficulty, "
        "format), and value versus price.\n"
        "Do not invent testimonials or metrics; ground claims only in supplied data."
    ),
    "leadgen": (
        "Focus the audit on aggressive lead capture: minimal friction, a short path to the target action, a strong "
        "visible CTA, and fewer distractions on the way to form/button.\n"
        "Keep honesty requirements for evidence and no fabricated facts."
    ),
}


def normalize_preset(raw: str | None) -> str:
    """Return a canonical preset; ``None``/empty → ``general``."""
    if raw is None:
        return DEFAULT_PRESET
    s = str(raw).strip().lower()
    if not s:
        return DEFAULT_PRESET
    if s not in ALLOWED_PRESETS:
        raise ValueError(f"preset must be one of: {', '.join(sorted(ALLOWED_PRESETS))}")
    return s


def build_preset_addon(preset: str, lang: str) -> str:
    """
    Preset-specific instructions appended to the system prompt (not a full rewrite of the system prompt).

    ``general`` returns an empty string (legacy balanced behavior).
    """
    code = normalize_lang(lang)
    p = normalize_preset(preset)
    if p == DEFAULT_PRESET:
        return ""
    guides = _PRESET_ADDONS_RU if code == "ru" else _PRESET_ADDONS_EN
    return guides.get(p, "")


def preset_section_title(lang: str) -> str:
    """Localized heading placed before the preset addon in the system prompt."""
    code = normalize_lang(lang)
    if code == "ru":
        return "Фокус аудита (тип лендинга, preset):"
    return "Audit focus (landing preset):"
