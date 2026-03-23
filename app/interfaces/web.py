"""Minimal HTML UI for audit (FastAPI + Jinja2; no duplicate pipeline logic)."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core import paths
from app.core.config import get_settings
from app.core.lang import resolve_effective_lang
from app.core.presets import normalize_preset
from app.providers.llm import LlmProviderError
from app.services.analyzer import AnalyzerError
from app.services.audit_pipeline import run_landing_audit, run_visual_audit
from app.services.audit_storage import save_audit_report
from app.services.parser import ParsingError
from app.services.report_builder import format_visual_audit_readable
from main import _build_readable_markdown

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=str(paths.PROJECT_ROOT / "templates"))

web_router = APIRouter(prefix="/web", tags=["web"])

_PRESET_OPTIONS = ("general", "services", "expert", "course", "leadgen", "craftum")


def _format_web_result(report: dict[str, Any], output_format: str, lang: str, mode: str) -> str:
    """String for ``<pre>``: full JSON, or plain text (same as CLI ``--output-format readable``)."""
    code = lang if lang in ("ru", "en") else "ru"
    if output_format != "readable":
        return json.dumps(report, ensure_ascii=False, indent=2)
    if mode == "visual":
        return format_visual_audit_readable(report, code)
    return _build_readable_markdown(report)


def _run_pipeline(url: str, mode: str, preset: str, lang_code: str) -> dict[str, Any]:
    settings = get_settings()
    effective_lang = resolve_effective_lang(cli_lang=lang_code or None, env_lang=settings.default_lang)
    m = (mode or "content").strip().lower()
    if m == "visual":
        return run_visual_audit(
            url,
            settings=settings,
            effective_lang=effective_lang,
            debug_dir=None,
        )
    if m == "craftum":
        p = "craftum"
    else:
        p = normalize_preset(preset or "general")
    return run_landing_audit(
        url,
        settings=settings,
        user_task=None,
        effective_lang=effective_lang,
        rewrite_targets=None,
        preset=p,
        debug_dir=None,
    )


def _default_form() -> dict[str, str]:
    return {
        "url": "",
        "mode": "content",
        "preset": "general",
        "lang": "ru",
        "output_format": "readable",
    }


@web_router.get("/", response_class=HTMLResponse, include_in_schema=False)
def web_audit_form(request: Request) -> Any:
    return templates.TemplateResponse(
        request,
        "web_index.html",
        {"form": _default_form(), "error": None, "result": None},
    )


@web_router.post("/audit", response_class=HTMLResponse, include_in_schema=False)
def web_audit_submit(
    request: Request,
    url: str = Form(...),
    mode: str = Form("content"),
    preset: str = Form("general"),
    lang: str = Form("ru"),
    output_format: str = Form("readable"),
) -> Any:
    form = {
        "url": url.strip(),
        "mode": (mode or "content").strip().lower(),
        "preset": (preset or "general").strip().lower(),
        "lang": (lang or "ru").strip().lower(),
        "output_format": output_format if output_format in ("json", "readable") else "readable",
    }
    if not form["url"]:
        return templates.TemplateResponse(
            request,
            "web_index.html",
            {"form": form, "error": "URL не может быть пустым.", "result": None},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    if form["preset"] not in _PRESET_OPTIONS:
        form["preset"] = "general"
    if form["mode"] not in ("content", "craftum", "visual"):
        form["mode"] = "content"

    try:
        report = _run_pipeline(form["url"], form["mode"], form["preset"], form["lang"])
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "web_index.html",
            {"form": form, "error": str(exc), "result": None},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    except ParsingError as exc:
        return templates.TemplateResponse(
            request,
            "web_index.html",
            {"form": form, "error": str(exc), "result": None},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except LlmProviderError as exc:
        return templates.TemplateResponse(
            request,
            "web_index.html",
            {"form": form, "error": str(exc), "result": None},
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
    except AnalyzerError as exc:
        return templates.TemplateResponse(
            request,
            "web_index.html",
            {"form": form, "error": str(exc), "result": None},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except Exception:
        logger.exception("Web UI audit unexpected failure")
        return templates.TemplateResponse(
            request,
            "web_index.html",
            {
                "form": form,
                "error": "Внутренняя ошибка при выполнении аудита.",
                "result": None,
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    try:
        save_audit_report(form["url"], report)
    except OSError as exc:
        logger.warning("Could not persist web UI audit snapshot: %s", exc)

    result_text = _format_web_result(report, form["output_format"], form["lang"], form["mode"])
    return templates.TemplateResponse(
        request,
        "web_index.html",
        {"form": form, "error": None, "result": result_text},
    )
