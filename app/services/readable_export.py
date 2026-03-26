"""Human-readable markdown export for landing audits (CLI, baseline, web UI)."""

from __future__ import annotations

from typing import Any

from app.services.report_builder import build_human_report, format_summary_readable


def readable_payload(report: dict[str, Any]) -> dict[str, Any]:
    """``report_readable`` dict or ``build_human_report(report)``."""
    rr = report.get("report_readable")
    if isinstance(rr, dict):
        return rr
    return build_human_report(report)


def summary_for_readable(report: dict[str, Any], rr: dict[str, Any]) -> str:
    """Plain-text summary block (not raw JSON)."""
    return format_summary_readable(rr.get("summary"), report.get("language"))


def block_analysis_visible(rr: dict[str, Any]) -> bool:
    if rr.get("next_action_readable"):
        return True
    bar = rr.get("block_analysis_readable")
    if not isinstance(bar, dict):
        return False
    mb = bar.get("missing_blocks") or []
    if mb:
        return True
    na = bar.get("next_action")
    if not isinstance(na, dict):
        return False
    for k, v in na.items():
        if k == "confidence":
            if isinstance(v, (int, float)) and float(v) > 0:
                return True
            continue
        if v is not None and str(v).strip():
            return True
    return False


def rewrite_texts_readable_nonempty(rr: dict[str, Any]) -> bool:
    rt = rr.get("rewrite_texts_readable")
    if not isinstance(rt, dict):
        return False
    for key in ("hero", "cta", "trust"):
        if str(rt.get(key, "")).strip():
            return True
    return False


def format_quick_win_line(item: Any) -> str:
    if isinstance(item, dict):
        title = str(item.get("title", "")).strip()
        action = str(item.get("action", "")).strip()
        if title and action:
            return f"- {title}: {action}"
        if title:
            return f"- {title}"
        if action:
            return f"- {action}"
        return f"- {item}"
    return f"- {item}"


def build_landing_audit_readable_markdown(report: dict[str, Any]) -> str:
    """
    Markdown-like body: summary, strengths/risks, issues, recommendations, quick wins,
    blocks, roadmap, rewrites (same as ``--save-report`` with readable format).
    """
    rr = readable_payload(report)
    parts: list[str] = [
        "# Summary",
        summary_for_readable(report, rr),
        "",
        "# Issues",
    ]
    for line in rr.get("issues_readable") or []:
        parts.append(f"- {line}")
    parts.extend(["", "# Recommendations"])
    blocks = rr.get("recommendations_readable") or []
    for i, block in enumerate(blocks):
        if i > 0:
            parts.append("")
        parts.append(block)
    if str(report.get("preset", "")).lower() == "craftum":
        csec = (rr.get("craftum_block_plan_section") or "").strip()
        if csec:
            parts.extend(["", csec])
    parts.extend(["", "# Quick Wins"])
    for item in rr.get("quick_wins") or []:
        parts.append(format_quick_win_line(item))
    if block_analysis_visible(rr):
        bar = rr.get("block_analysis_readable")
        if not isinstance(bar, dict):
            bar = {}
        mb = list(bar.get("missing_blocks") or [])
        if mb:
            parts.extend(["", "# Missing blocks", ""])
            for line in mb:
                parts.append(f"- {line}")
        nar = rr.get("next_action_readable") or ""
        if nar.strip():
            parts.extend(["", "# Next action", "", nar])
    arr = (rr.get("action_roadmap_readable") or "").strip()
    if arr:
        parts.extend(["", "# Action roadmap", "", arr])
    if rewrite_texts_readable_nonempty(rr):
        rt = rr.get("rewrite_texts_readable")
        if not isinstance(rt, dict):
            rt = {}
        parts.extend(
            [
                "",
                "# Rewrites",
                "",
                "## Hero",
                str(rt.get("hero", "")),
                "",
                "## CTA",
                str(rt.get("cta", "")),
                "",
                "## Trust",
                str(rt.get("trust", "")),
            ]
        )
    return "\n".join(parts)
