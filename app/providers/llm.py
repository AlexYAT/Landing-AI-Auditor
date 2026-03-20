"""OpenAI provider for landing audit analysis."""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import Settings
from app.core.prompts import SYSTEM_PROMPT, build_user_prompt


class LlmProviderError(Exception):
    """Raised when LLM provider cannot produce a valid response."""


class OpenAiAuditProvider:
    """Thin wrapper around OpenAI API for landing analysis."""

    def __init__(self, settings: Settings) -> None:
        """Initialize OpenAI client with settings."""
        if not settings.openai_api_key:
            raise LlmProviderError("OPENAI_API_KEY is missing. Set it in environment or .env file.")
        self._settings = settings
        self._client = OpenAI(api_key=settings.openai_api_key)

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((LlmProviderError, json.JSONDecodeError)),
    )
    def analyze_landing(self, parsed_data: dict[str, Any], user_task: str) -> dict[str, Any]:
        """Send landing context to LLM and return parsed JSON."""
        try:
            response = self._client.chat.completions.create(
                model=self._settings.openai_model,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(parsed_data=parsed_data, user_task=user_task)},
                ],
            )
            content = response.choices[0].message.content
            if not content:
                raise LlmProviderError("Empty response from OpenAI.")
            return json.loads(content)
        except json.JSONDecodeError:
            raise
        except Exception as exc:
            raise LlmProviderError(f"OpenAI request failed: {exc}") from exc
