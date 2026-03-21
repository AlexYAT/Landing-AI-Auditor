"""OpenAI provider for landing audit analysis."""

from __future__ import annotations

import json
import re
from typing import Any, Sequence

from openai import OpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import Settings
from app.core.lang import DEFAULT_LANG
from app.core.presets import DEFAULT_PRESET
from app.core.prompts import build_system_prompt, build_user_prompt


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

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """Remove markdown code fences if model accidentally adds them."""
        stripped = text.strip()
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
        return stripped.strip()

    @staticmethod
    def _extract_json_object(text: str) -> str:
        """Extract first valid JSON object candidate from mixed text."""
        start = text.find("{")
        if start == -1:
            raise LlmProviderError("LLM response does not contain a JSON object.")

        depth = 0
        in_string = False
        escape = False
        for idx, char in enumerate(text[start:], start=start):
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : idx + 1]

        raise LlmProviderError("Could not extract a complete JSON object from LLM response.")

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """Parse raw response text into JSON dict with fallback extraction."""
        cleaned = self._strip_code_fences(text)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            extracted = self._extract_json_object(cleaned)
            try:
                parsed = json.loads(extracted)
            except json.JSONDecodeError as exc:
                raise LlmProviderError(f"Failed to parse LLM JSON response: {exc}") from exc

        if not isinstance(parsed, dict):
            raise LlmProviderError("LLM response JSON root must be an object.")
        return parsed

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(LlmProviderError),
    )
    def analyze_landing(
        self,
        parsed_data: dict[str, Any],
        sanitized_user_task: str | None,
        lang: str = DEFAULT_LANG,
        rewrite_targets: Sequence[str] | None = None,
        preset: str = DEFAULT_PRESET,
    ) -> dict[str, Any]:
        """Send landing context to LLM and return parsed JSON."""
        try:
            response = self._client.chat.completions.create(
                model=self._settings.openai_model,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": build_system_prompt(
                            lang,
                            rewrite_targets=rewrite_targets,
                            preset=preset,
                        ),
                    },
                    {
                        "role": "user",
                        "content": build_user_prompt(
                            parsed_data=parsed_data,
                            sanitized_user_task=sanitized_user_task,
                            lang=lang,
                            rewrite_targets=rewrite_targets,
                        ),
                    },
                ],
            )
            content = response.choices[0].message.content
            if not content:
                raise LlmProviderError("Empty response from OpenAI.")
            return self._parse_json_response(content)
        except Exception as exc:
            if isinstance(exc, LlmProviderError):
                raise
            raise LlmProviderError(f"OpenAI request failed: {exc}") from exc
