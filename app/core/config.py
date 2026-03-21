"""Application configuration management."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    openai_api_key: str
    openai_model: str = "gpt-4.1-mini"
    request_timeout: int = 20
    max_text_chars: int = 12000
    default_lang: str = "ru"


def get_cors_allowed_origins() -> list[str]:
    """
    Parse ``ALLOWED_ORIGINS`` for CORSMiddleware.

    - Default / empty / ``*`` → ``["*"]`` (any origin; development-friendly).
    - Comma-separated list → explicit origins (trimmed, empty parts dropped).
    """
    raw = os.getenv("ALLOWED_ORIGINS", "*").strip()
    if not raw or raw == "*":
        return ["*"]
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return ["*"]
    if parts == ["*"]:
        return ["*"]
    return parts


def _get_int_env(name: str, default: int) -> int:
    """Safely read an integer from env with fallback."""
    value = os.getenv(name)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


def get_settings() -> Settings:
    """Build and return application settings."""
    from app.core.lang import normalize_lang

    raw_lang = os.getenv("DEFAULT_LANG", "").strip()
    default_lang = normalize_lang(raw_lang if raw_lang else None)
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip(),
        request_timeout=_get_int_env("REQUEST_TIMEOUT", 20),
        max_text_chars=_get_int_env("MAX_TEXT_CHARS", 12000),
        default_lang=default_lang,
    )
