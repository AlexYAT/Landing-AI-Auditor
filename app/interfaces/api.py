"""Minimal FastAPI layer for landing audit (reuses audit_pipeline)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.middleware.cors import CORSMiddleware

from app.core.config import get_cors_allowed_origins, get_settings
from app.core.lang import SUPPORTED_LANGS, SUPPORTED_LANGS_API_ORDER, resolve_effective_lang
from app.core.presets import PRESETS_API_ORDER
from app.core.rewrite_targets import REWRITE_TARGETS_API_ORDER
from app.providers.llm import LlmProviderError
from app.services.analyzer import AnalyzerError
from app.services.audit_pipeline import run_landing_audit
from app.services.parser import ParsingError

logger = logging.getLogger(__name__)

API_VERSION = "v1"

app = FastAPI(
    title="Landing AI Auditor",
    version="1.0",
    description="HTTP API for the same audit flow as the CLI (no auth).",
)

_origins = get_cors_allowed_origins()
_cors_wildcard = _origins == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=not _cors_wildcard,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    """GET /health body."""

    status: Literal["ok"] = "ok"


class CapabilitiesResponse(BaseModel):
    """GET /meta/capabilities — stable hints for UI clients (languages, rewrite blocks, flags)."""

    supported_languages: list[str]
    rewrite_targets: list[str]
    presets: list[str]
    debug_supported: bool = True
    api_version: str


class ApiErrorResponse(BaseModel):
    """Stable error envelope for domain failures (no stack traces)."""

    error: str = Field(..., description="Short machine-readable code")
    message: str = Field(..., description="Human-readable explanation")


class AuditRequest(BaseModel):
    """POST /audit body."""

    url: str = Field(..., min_length=1, description="Landing page URL (http/https)")
    task: str | None = Field(default=None, description="Optional business goal for task-aware analysis")
    lang: str | None = Field(
        default=None,
        description="Output language: ru or en (optional; falls back to env when omitted)",
    )
    rewrite: list[Literal["hero", "cta", "trust"]] | None = Field(
        default=None,
        description="Optional rewrite blocks (subset of hero, cta, trust); empty list means no rewrites",
    )
    debug: bool = Field(default=False, description="Save parser debug artifacts under output/debug/<host>")
    preset: Literal["general", "services", "expert", "course", "leadgen"] = Field(
        default="general",
        description="Landing type preset (analysis focus); default general",
    )

    @field_validator("url")
    @classmethod
    def strip_url(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("url cannot be empty or whitespace")
        return s

    @field_validator("lang")
    @classmethod
    def validate_lang(cls, v: str | None) -> str | None:
        if v is None:
            return None
        code = v.strip().lower()
        if not code:
            return None
        if code not in SUPPORTED_LANGS:
            allowed = ", ".join(sorted(SUPPORTED_LANGS))
            raise ValueError(f"lang must be one of: {allowed}")
        return code

    @field_validator("rewrite", mode="after")
    @classmethod
    def normalize_rewrite(cls, v: list[str] | None) -> list[str] | None:
        if v is None or len(v) == 0:
            return None
        return list(dict.fromkeys(v))


class AuditSuccessResponse(BaseModel):
    """Full-mode audit JSON (same shape as CLI); extra root keys allowed for forward compatibility."""

    model_config = ConfigDict(extra="allow")

    language: str
    summary: dict[str, Any]
    issues: list[Any]
    recommendations: list[Any]
    quick_wins: list[Any]
    rewrites: list[Any]


def _error_payload(code: str, message: str) -> dict[str, str]:
    return {"error": code, "message": message}


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Return API error bodies as flat ``{error, message}`` instead of ``{detail: ...}``."""
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail and "message" in detail:
        return JSONResponse(status_code=exc.status_code, content=detail)
    if isinstance(detail, dict):
        return JSONResponse(status_code=exc.status_code, content={"detail": detail})
    return JSONResponse(status_code=exc.status_code, content={"detail": detail})


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def get_health() -> HealthResponse:
    """Liveness probe for load balancers and UI integration."""
    return HealthResponse()


@app.get("/meta/capabilities", response_model=CapabilitiesResponse, tags=["meta"])
def get_capabilities() -> CapabilitiesResponse:
    """
    Describe supported options (languages, rewrite blocks) without hard-coding in the frontend.

    Aligns with ``SUPPORTED_LANGS`` / ``ALLOWED_REWRITE_TARGETS`` in core modules.
    """
    return CapabilitiesResponse(
        supported_languages=list(SUPPORTED_LANGS_API_ORDER),
        rewrite_targets=list(REWRITE_TARGETS_API_ORDER),
        presets=list(PRESETS_API_ORDER),
        debug_supported=True,
        api_version=API_VERSION,
    )


@app.post(
    "/audit",
    response_model=AuditSuccessResponse,
    responses={
        400: {"model": ApiErrorResponse, "description": "Fetch/parse failed"},
        502: {"model": ApiErrorResponse, "description": "LLM provider failed"},
        500: {"model": ApiErrorResponse, "description": "Analysis failed or unexpected error"},
    },
    tags=["audit"],
)
def post_audit(body: AuditRequest) -> dict[str, Any]:
    """
    Run full audit (and optional rewrites) for ``url``.

    Response matches CLI full-mode JSON: audit fields plus ``language`` and ``rewrites`` (possibly empty).
    """
    settings = get_settings()
    effective_lang = resolve_effective_lang(cli_lang=body.lang, env_lang=settings.default_lang)
    rewrite_targets: tuple[str, ...] | None = (
        tuple(body.rewrite) if body.rewrite else None
    )

    debug_dir: Path | None = None
    if body.debug:
        host = urlparse(body.url).netloc.replace(":", "_") or "unknown"
        debug_dir = Path("output") / "debug" / host
        logger.info("API debug: writing parser artifacts to %s", debug_dir)

    try:
        return run_landing_audit(
            body.url,
            settings=settings,
            user_task=body.task,
            effective_lang=effective_lang,
            rewrite_targets=rewrite_targets,
            preset=body.preset,
            debug_dir=debug_dir,
        )
    except ParsingError as exc:
        logger.info("Audit parsing failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error_payload("parsing_failed", str(exc)),
        ) from exc
    except LlmProviderError as exc:
        logger.warning("LLM provider error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_error_payload("llm_failed", str(exc)),
        ) from exc
    except AnalyzerError as exc:
        logger.warning("Analyzer error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_error_payload("audit_failed", str(exc)),
        ) from exc
    except Exception:
        logger.exception("Unexpected audit failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_error_payload("internal_error", "An unexpected error occurred while processing the audit."),
        ) from None


# Uvicorn: uvicorn app.interfaces.api:app --host 127.0.0.1 --port 8000
