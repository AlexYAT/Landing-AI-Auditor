"""Minimal FastAPI layer for landing audit (reuses audit_pipeline)."""

from __future__ import annotations

import json
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, urlparse

from fastapi import FastAPI, Form, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.middleware.cors import CORSMiddleware

from app.core.config import get_cors_allowed_origins, get_settings
from app.core.lang import SUPPORTED_LANGS, SUPPORTED_LANGS_API_ORDER, resolve_effective_lang
from app.core import paths
from app.core.presets import PRESETS_API_ORDER
from app.core.rewrite_targets import REWRITE_TARGETS_API_ORDER
from app.providers.llm import LlmProviderError
from app.services.analyzer import AnalyzerError
from app.services.audit_pipeline import run_landing_audit
from app.services.audit_storage import save_audit_report
from app.services.parser import ParsingError
from app.services.report_builder import build_human_report

logger = logging.getLogger(__name__)

API_VERSION = "v1"

templates = Jinja2Templates(directory=str(paths.PROJECT_ROOT / "templates"))


def _log_audits_dir_status() -> None:
    """One-line diagnostics: same ``audits/`` as CLI (see ``app.core.paths``)."""
    audits = paths.get_audits_dir()
    exists = audits.is_dir()
    n_json = 0
    if exists:
        n_json = sum(1 for p in audits.iterdir() if p.is_file() and p.suffix.lower() == ".json")
    logger.info(
        "Audits history: project_root=%s audits_dir=%s dir_exists=%s json_files=%s",
        paths.PROJECT_ROOT,
        audits,
        exists,
        n_json,
    )


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _log_audits_dir_status()
    yield

_AUDIT_FILENAME_RE = re.compile(
    r"^(.+)_([a-z]{2})_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2})\.json$",
    re.IGNORECASE,
)


def _audit_history_entries() -> list[dict[str, str]]:
    """Saved audits under ``audits/`` for UI and ``GET /audits`` (newest first)."""
    audits = paths.get_audits_dir()
    rows: list[tuple[tuple[int, int], dict[str, str]]] = []
    if not audits.is_dir():
        return []
    for p in audits.iterdir():
        if not p.is_file() or p.suffix.lower() != ".json":
            continue
        m = _AUDIT_FILENAME_RE.match(p.name)
        if m:
            domain, _lang, date_part, time_part = m.groups()
            hh, mm = time_part.split("-", 1)
            ts = f"{date_part} {hh}:{mm}"
            sort_key = (int(date_part.replace("-", "")), int(hh) * 60 + int(mm))
        else:
            domain, ts = "—", p.name
            sort_key = (0, 0)
        q = quote(p.name)
        rows.append(
            (
                sort_key,
                {
                    "filename": p.name,
                    "domain": domain,
                    "timestamp": ts,
                    "open_url": f"/ui/audit/file?filename={q}&output_mode=readable",
                    "open_url_json": f"/ui/audit/file?filename={q}&output_mode=json",
                },
            )
        )
    rows.sort(key=lambda x: x[0], reverse=True)
    return [r[1] for r in rows]


def _safe_audit_file_path(filename: str) -> Path | None:
    """Resolve a basename under ``audits/`` or return ``None`` (path traversal rejected)."""
    if not filename or not filename.strip():
        return None
    base = Path(filename).name
    if base != filename.strip():
        return None
    if ".." in base or "/" in base or "\\" in base:
        return None
    if not base.endswith(".json"):
        return None
    audits = paths.get_audits_dir()
    path = (audits / base).resolve()
    try:
        path.relative_to(audits.resolve())
    except ValueError:
        return None
    if not path.is_file():
        return None
    return path


app = FastAPI(
    title="Landing AI Auditor",
    version="1.0",
    description="HTTP API for the same audit flow as the CLI (no auth).",
    lifespan=_lifespan,
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
    rewrite_texts: dict[str, str] | None = Field(
        default=None,
        description="Paste-ready hero/cta/trust copy (distinct from structured rewrites array)",
    )
    report_readable: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Human-readable presentation (summary, issues_readable, recommendations_readable, "
            "quick_wins, rewrite_texts_readable)"
        ),
    )


def _error_payload(code: str, message: str) -> dict[str, str]:
    return {"error": code, "message": message}


def _format_summary_display(summary: Any) -> str:
    if summary is None:
        return ""
    if isinstance(summary, dict):
        return json.dumps(summary, ensure_ascii=False, indent=2)
    return str(summary)


def _quick_win_lines(items: list[Any]) -> list[str]:
    lines: list[str] = []
    for item in items:
        if isinstance(item, dict):
            t = str(item.get("title", "")).strip()
            a = str(item.get("action", "")).strip()
            if t and a:
                lines.append(f"{t}: {a}")
            elif t:
                lines.append(t)
            elif a:
                lines.append(a)
            else:
                lines.append(str(item))
        else:
            lines.append(str(item))
    return lines


def _readable_sections(report: dict[str, Any]) -> dict[str, Any]:
    rr = report.get("report_readable")
    if not isinstance(rr, dict):
        rr = build_human_report(report)
    return {
        "rr": rr,
        "summary_display": _format_summary_display(rr.get("summary")),
        "issues_list": list(rr.get("issues_readable") or []),
        "rec_blocks": list(rr.get("recommendations_readable") or []),
        "qw_lines": _quick_win_lines(list(rr.get("quick_wins") or [])),
    }


def _run_audit_from_body(body: AuditRequest) -> dict[str, Any]:
    """Shared audit call for JSON API and demo UI (same as previous inline ``post_audit`` body)."""
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
    return run_landing_audit(
        body.url,
        settings=settings,
        user_task=body.task,
        effective_lang=effective_lang,
        rewrite_targets=rewrite_targets,
        preset=body.preset,
        debug_dir=debug_dir,
    )


def _ui_base_context(
    *,
    form: dict[str, str],
    error: str | None = None,
    report: dict[str, Any] | None = None,
    output_mode: str = "readable",
    audit_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "form": form,
        "error": error,
        "preset_options": list(PRESETS_API_ORDER),
        "json_pretty": None,
        "rr": None,
        "summary_display": "",
        "issues_list": [],
        "rec_blocks": [],
        "qw_lines": [],
        "rewrite_texts": None,
        "audit_history": audit_history if audit_history is not None else _audit_history_entries(),
    }
    if report is None:
        return ctx
    if output_mode == "json":
        ctx["json_pretty"] = json.dumps(report, ensure_ascii=False, indent=2)
        return ctx
    ctx.update(_readable_sections(report))
    rt = report.get("rewrite_texts")
    if isinstance(rt, dict):
        ctx["rewrite_texts"] = rt
    return ctx


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


@app.get("/audits", tags=["history"])
def list_saved_audits() -> list[dict[str, str]]:
    """List JSON files in ``audits/`` (CLI history), with domain and timestamp from filename."""
    return [
        {"filename": r["filename"], "domain": r["domain"], "timestamp": r["timestamp"]}
        for r in _audit_history_entries()
    ]


@app.get("/", include_in_schema=False)
def ui_index(request: Request) -> Any:
    """Minimal HTML demo: form only."""
    return templates.TemplateResponse(
        request,
        "index.html",
        _ui_base_context(
            form={
                "url": "",
                "task": "",
                "preset": "general",
                "lang": "",
                "output_mode": "readable",
            },
        ),
    )


@app.get("/ui/audit/file", include_in_schema=False)
def ui_open_saved_audit(
    request: Request,
    filename: str,
    output_mode: str = "readable",
) -> Any:
    """Open a saved audit JSON from ``audits/`` (same rendering as a fresh UI run)."""
    mode = output_mode if output_mode in ("json", "readable") else "readable"
    empty_form = {
        "url": "",
        "task": "",
        "preset": "general",
        "lang": "",
        "output_mode": mode,
    }
    path = _safe_audit_file_path(filename)
    if path is None:
        return templates.TemplateResponse(
            request,
            "index.html",
            _ui_base_context(
                form={**empty_form, "output_mode": "readable"},
                error="Saved audit not found or invalid filename.",
            ),
            status_code=404,
        )
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return templates.TemplateResponse(
            request,
            "index.html",
            _ui_base_context(form=empty_form, error=f"Could not read audit file: {exc}"),
            status_code=400,
        )
    return templates.TemplateResponse(
        request,
        "index.html",
        _ui_base_context(form=empty_form, report=report, output_mode=mode),
    )


@app.post("/ui/audit", include_in_schema=False)
def ui_audit_submit(
    request: Request,
    url: str = Form(...),
    task: str = Form(""),
    preset: str = Form("general"),
    lang: str = Form(""),
    output_mode: str = Form("readable"),
) -> Any:
    """Demo UI: same pipeline as ``POST /audit``; renders result HTML."""
    form = {
        "url": url.strip(),
        "task": task.strip(),
        "preset": preset.strip() or "general",
        "lang": lang.strip(),
        "output_mode": output_mode if output_mode in ("json", "readable") else "readable",
    }
    try:
        body = AuditRequest(
            url=form["url"],
            task=form["task"] or None,
            preset=form["preset"],  # type: ignore[arg-type]
            lang=form["lang"] or None,
        )
    except ValidationError as exc:
        return templates.TemplateResponse(
            request,
            "index.html",
            _ui_base_context(form=form, error="Invalid input: " + str(exc)),
            status_code=422,
        )
    try:
        report = _run_audit_from_body(body)
    except ParsingError as exc:
        return templates.TemplateResponse(
            request,
            "index.html",
            _ui_base_context(form=form, error=str(exc)),
            status_code=400,
        )
    except LlmProviderError as exc:
        return templates.TemplateResponse(
            request,
            "index.html",
            _ui_base_context(form=form, error=str(exc)),
            status_code=502,
        )
    except AnalyzerError as exc:
        return templates.TemplateResponse(
            request,
            "index.html",
            _ui_base_context(form=form, error=str(exc)),
            status_code=500,
        )
    except Exception:
        logger.exception("UI audit unexpected failure")
        return templates.TemplateResponse(
            request,
            "index.html",
            _ui_base_context(
                form=form,
                error="An unexpected error occurred while processing the audit.",
            ),
            status_code=500,
        )
    try:
        saved = save_audit_report(body.url, report)
        logger.info("UI audit snapshot saved: %s", saved)
    except OSError as exc:
        logger.warning("Could not persist UI audit snapshot: %s", exc)
    return templates.TemplateResponse(
        request,
        "index.html",
        _ui_base_context(
            form=form,
            report=report,
            output_mode=form["output_mode"],
        ),
    )


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
    try:
        return _run_audit_from_body(body)
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
