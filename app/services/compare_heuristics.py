"""Heuristic comparison between baseline and current audit JSON (no line diff, semantic focus)."""

from __future__ import annotations

import re
from typing import Any

from app.services.audit_storage import coerce_audit_meta, format_audit_context_text
from app.services.diff_service import compute_progress_score


def _txt(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x.strip()
    return str(x).strip()


def is_visual_error_stub(report: dict[str, Any] | None) -> bool:
    if not isinstance(report, dict):
        return True
    if report.get("baseline_status") == "error":
        return True
    if report.get("audit_type") != "visual" and "overall_visual_assessment" not in report:
        return True
    return False


def normalize_issue_key(item: Any) -> str:
    if not isinstance(item, dict):
        return _txt(item).lower()[:500]
    sev = _txt(item.get("severity")).upper()
    cat = _txt(item.get("category", item.get("type"))).upper()
    title = _txt(item.get("title", item.get("description")))
    return f"{sev}|{cat}|{title}".lower()


def issues_fingerprint_list(issues: Any) -> list[str]:
    if not isinstance(issues, list):
        return []
    keys = [normalize_issue_key(x) for x in issues if _txt(normalize_issue_key(x))]
    return sorted(set(keys))


def compare_fingerprint_sets(before: list[str], after: list[str]) -> tuple[list[str], list[str], list[str]]:
    sb, sa = set(before), set(after)
    resolved = sorted(sb - sa)
    new_on = sorted(sa - sb)
    unchanged = sorted(sb & sa)
    return resolved, new_on, unchanged


def normalize_string_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out = [_txt(x) for x in raw if _txt(x)]
    return sorted(set(s.lower() for s in out))


def compare_string_buckets(before: list[str], after: list[str]) -> tuple[list[str], list[str], list[str]]:
    sb = set(before)
    sa = set(after)
    removed = sorted(sb - sa, key=str.lower)
    added = sorted(sa - sb, key=str.lower)
    kept = sorted(sb & sa, key=str.lower)
    return removed, added, kept


def summary_overall(report: dict[str, Any] | None) -> str:
    if not isinstance(report, dict):
        return ""
    s = report.get("summary")
    if isinstance(s, dict):
        return _txt(s.get("overall_assessment"))
    return ""


def top_risks_list(report: dict[str, Any] | None) -> list[str]:
    if not isinstance(report, dict):
        return []
    s = report.get("summary")
    if not isinstance(s, dict):
        return []
    return normalize_string_list(s.get("top_risks"))


def top_strengths_list(report: dict[str, Any] | None) -> list[str]:
    if not isinstance(report, dict):
        return []
    s = report.get("summary")
    if not isinstance(s, dict):
        return []
    return normalize_string_list(s.get("top_strengths"))


def quick_win_titles(report: dict[str, Any] | None) -> list[str]:
    if not isinstance(report, dict):
        return []
    q = report.get("quick_wins")
    if not isinstance(q, list):
        return []
    titles: list[str] = []
    for item in q:
        if isinstance(item, dict):
            t = _txt(item.get("title"))
            if t:
                titles.append(t.lower())
        else:
            t = _txt(item)
            if t:
                titles.append(t.lower())
    return sorted(set(titles))


def missing_blocks_ordered(report: dict[str, Any] | None) -> list[str]:
    if not isinstance(report, dict):
        return []
    ba = report.get("block_analysis")
    if not isinstance(ba, dict):
        return []
    mb = ba.get("missing_blocks")
    if not isinstance(mb, list):
        return []
    return sorted({_txt(x) for x in mb if _txt(x)}, key=str.lower)


def next_block_summary(report: dict[str, Any] | None) -> str:
    if not isinstance(report, dict):
        return ""
    ba = report.get("block_analysis")
    if not isinstance(ba, dict):
        return ""
    nb = ba.get("next_block")
    if not isinstance(nb, dict):
        return ""
    t = _txt(nb.get("type"))
    pr = _txt(nb.get("priority"))
    if t and pr:
        return f"{t} ({pr})"
    return t or pr


def visual_issue_count(report: dict[str, Any] | None) -> int | None:
    if is_visual_error_stub(report):
        return None
    if not isinstance(report, dict):
        return None
    vi = report.get("visual_issues")
    if not isinstance(vi, list):
        return 0
    return len([x for x in vi if isinstance(x, dict)])


def overall_visual_text(report: dict[str, Any] | None) -> str:
    if is_visual_error_stub(report):
        return ""
    if not isinstance(report, dict):
        return ""
    return _txt(report.get("overall_visual_assessment"))


def heuristic_conversion_keywords(text: str) -> dict[str, bool]:
    """Very small lexicon for CTA/trust/lead hints (best-effort, bilingual snippets)."""
    t = text.lower()
    return {
        "cta_clear": bool(
            re.search(r"\b(cta|призыв|call to action|кнопк|click)\b", t, re.I),
        ),
        "trust_strong": bool(
            re.search(r"\b(trust|довери|proof|отзыв|соцдоказ|credibil)\b", t, re.I),
        ),
        "friction": bool(
            re.search(r"\b(friction|трени|сомнен|confus|clutter|шум)\b", t, re.I),
        ),
    }


def merge_direction_signals(
    content_score: int,
    craftum_score: int,
    n_resolved: int,
    n_new: int,
    mb_removed: int,
    mb_added: int,
    visual_delta: int | None,
) -> tuple[str, float]:
    """
    Return (direction, confidence in [0,1]).

    direction: improved | degraded | mixed | unchanged
    """
    improved = 0
    degraded = 0
    signals = 0

    combined = int(round(content_score * 0.55 + craftum_score * 0.45))
    if combined > 8:
        improved += 2
        signals += 1
    elif combined < -8:
        degraded += 2
        signals += 1
    elif combined > 0:
        improved += 1
        signals += 1
    elif combined < 0:
        degraded += 1
        signals += 1

    if n_resolved > n_new:
        improved += 2
        signals += 1
    elif n_new > n_resolved:
        degraded += 2
        signals += 1

    if mb_removed > mb_added:
        improved += 1
        signals += 1
    elif mb_added > mb_removed:
        degraded += 1
        signals += 1

    if visual_delta is not None:
        signals += 1
        if visual_delta < 0:
            improved += 1
        elif visual_delta > 0:
            degraded += 1

    if improved == 0 and degraded == 0:
        return "unchanged", min(1.0, 0.35 + 0.08 * signals)

    if improved > degraded:
        return "improved", min(1.0, 0.45 + 0.12 * signals)
    if degraded > improved:
        return "degraded", min(1.0, 0.45 + 0.12 * signals)
    return "mixed", min(1.0, 0.4 + 0.1 * signals)


def build_comparison_payload(
    *,
    url: str,
    baseline_dir: str,
    output_dir: str,
    baseline_content: dict[str, Any],
    current_content: dict[str, Any],
    baseline_craftum: dict[str, Any],
    current_craftum: dict[str, Any],
    baseline_visual: dict[str, Any],
    current_visual: dict[str, Any],
    limitations: list[str],
    current_modes: dict[str, bool],
) -> dict[str, Any]:
    lim_msgs = list(limitations)
    notes: list[str] = []

    b_vis_stub = is_visual_error_stub(baseline_visual)
    c_vis_stub = is_visual_error_stub(current_visual)

    if b_vis_stub:
        lim_msgs.append("Baseline visual is unavailable or error stub; visual comparison limited.")
    if c_vis_stub:
        lim_msgs.append("Current visual is unavailable or error stub; visual comparison limited.")

    issues_b = issues_fingerprint_list(baseline_content.get("issues"))
    issues_a = issues_fingerprint_list(current_content.get("issues"))
    resolved_keys, new_keys, _unchanged_issues = compare_fingerprint_sets(issues_b, issues_a)

    risks_b = top_risks_list(baseline_content)
    risks_a = top_risks_list(current_content)
    risks_res, risks_new, _rk = compare_string_buckets(risks_b, risks_a)

    strengths_b = top_strengths_list(baseline_content)
    strengths_a = top_strengths_list(current_content)
    st_res, st_new, _st = compare_string_buckets(strengths_b, strengths_a)

    mb_b = missing_blocks_ordered(baseline_content)
    mb_a = missing_blocks_ordered(current_content)
    mb_removed, mb_added, mb_kept = compare_string_buckets(mb_b, mb_a)

    qw_b = quick_win_titles(baseline_content)
    qw_a = quick_win_titles(current_content)
    qw_new = sorted(set(qw_a) - set(qw_b), key=str.lower)

    content_score = compute_progress_score(baseline_content, current_content)
    craftum_score = compute_progress_score(baseline_craftum, current_craftum)

    vc_b = visual_issue_count(baseline_visual)
    vc_a = visual_issue_count(current_visual)
    visual_delta: int | None = None
    if vc_b is not None and vc_a is not None:
        visual_delta = vc_a - vc_b

    direction, confidence = merge_direction_signals(
        content_score,
        craftum_score,
        len(resolved_keys),
        len(new_keys),
        len(mb_removed),
        len(mb_added),
        visual_delta,
    )

    improved: list[str] = []
    degraded: list[str] = []
    unchanged: list[str] = []

    if mb_removed:
        improved.append(f"Fewer missing blocks (resolved: {', '.join(mb_removed[:8])}{'…' if len(mb_removed) > 8 else ''})")
    if mb_added:
        degraded.append(f"New missing blocks: {', '.join(mb_added[:8])}{'…' if len(mb_added) > 8 else ''}")
    if mb_kept and not mb_removed and not mb_added:
        unchanged.append("Missing-blocks set unchanged.")

    if resolved_keys:
        improved.append(f"Resolved or removed {len(resolved_keys)} issue fingerprint(s) vs baseline.")
    if new_keys:
        degraded.append(f"New issues vs baseline: {len(new_keys)} fingerprint(s).")

    if risks_res:
        improved.append(f"Risks removed from summary: {len(risks_res)} item(s).")
    if risks_new:
        degraded.append(f"New risks in summary: {len(risks_new)} item(s).")

    if st_new:
        improved.append(f"New strengths noted: {len(st_new)} item(s).")
    if st_res:
        degraded.append(f"Strengths no longer highlighted: {len(st_res)} item(s).")

    if visual_delta is not None:
        if visual_delta < 0:
            improved.append(f"Visual audit: fewer issues reported ({vc_b} → {vc_a}).")
        elif visual_delta > 0:
            degraded.append(f"Visual audit: more issues reported ({vc_b} → {vc_a}).")
        else:
            unchanged.append("Visual issue count unchanged.")

    if content_score > 5:
        notes.append(f"Structural progress score (content): +{content_score} (diff_service heuristic).")
    elif content_score < -5:
        notes.append(f"Structural regression score (content): {content_score} (diff_service heuristic).")

    overall_b = summary_overall(baseline_content)
    overall_a = summary_overall(current_content)
    delta_conv = ""
    if overall_b == overall_a and overall_b:
        delta_conv = "Overall assessment text unchanged."
    elif overall_b and overall_a:
        kb = heuristic_conversion_keywords(overall_b)
        ka = heuristic_conversion_keywords(overall_a)
        if ka.get("cta_clear") and not kb.get("cta_clear"):
            delta_conv += " After: CTA/clarity signals stronger in summary wording. "
        if ka.get("trust_strong") and not kb.get("trust_strong"):
            delta_conv += " After: trust signals stronger. "
        if ka.get("friction") and not kb.get("friction"):
            delta_conv += " After: more friction/clutter noted. "
        if not delta_conv.strip():
            delta_conv = "Overall assessment wording changed; review before/after manually."
    else:
        delta_conv = "Insufficient summary text for automatic delta."

    summary_line = (
        f"Compared current site to baseline. Direction={direction} (heuristic confidence {confidence:.2f}). "
        f"Content progress score={content_score}, craftum progress score={craftum_score}."
    )
    if not current_modes.get("visual", True):
        summary_line += " Current visual partial/failed."

    craftum_mb_b = missing_blocks_ordered(baseline_craftum)
    craftum_mb_a = missing_blocks_ordered(current_craftum)
    cr_rm, cr_ad, _cr_kept = compare_string_buckets(craftum_mb_b, craftum_mb_a)

    ctx_b = coerce_audit_meta(baseline_content, url_fallback=url)
    ctx_a = coerce_audit_meta(current_content, url_fallback=url)
    context_block = (
        "=== CONTEXT ===\n\n"
        + format_audit_context_text("Baseline", ctx_b)
        + "\n"
        + format_audit_context_text("Improved", ctx_a)
    )

    return {
        "url": url,
        "baseline_dir": baseline_dir,
        "current_dir": output_dir,
        "context": {
            "baseline": ctx_b,
            "improved": ctx_a,
            "context_block": context_block,
        },
        "status": "ok",
        "overall_change": {
            "direction": direction,
            "confidence": round(confidence, 4),
            "summary": summary_line,
            "content_progress_score": content_score,
            "craftum_progress_score": craftum_score,
        },
        "changes": {
            "improved": improved,
            "degraded": degraded,
            "unchanged": unchanged,
            "new_issues": new_keys[:50],
            "resolved_issues": resolved_keys[:50],
            "new_risks": risks_new,
            "removed_risks": risks_res,
            "new_quick_win_titles": qw_new[:30],
        },
        "conversion_assessment": {
            "before": overall_b or "—",
            "after": overall_a or "—",
            "delta": delta_conv.strip() or "—",
        },
        "block_assessment": {
            "content": {
                "before_missing_blocks": mb_b,
                "after_missing_blocks": mb_a,
                "added": mb_added,
                "resolved": mb_removed,
            },
            "craftum": {
                "before_missing_blocks": craftum_mb_b,
                "after_missing_blocks": craftum_mb_a,
                "added": cr_ad,
                "resolved": cr_rm,
            },
            "next_action": {
                "before": next_block_summary(baseline_content),
                "after": next_block_summary(current_content),
            },
        },
        "visual": {
            "baseline_stub": b_vis_stub,
            "current_stub": c_vis_stub,
            "issue_counts_before_after": [vc_b, vc_a],
            "overall_before": overall_visual_text(baseline_visual) or "—",
            "overall_after": overall_visual_text(current_visual) or "—",
        },
        "limitations": lim_msgs,
        "notes": notes,
        "current_modes_ok": current_modes,
    }


def render_comparison_markdown(payload: dict[str, Any]) -> str:
    oc = payload.get("overall_change") or {}
    ch = payload.get("changes") or {}
    conv = payload.get("conversion_assessment") or {}
    blocks = payload.get("block_assessment") or {}
    vis = payload.get("visual") or {}
    ctx = payload.get("context") or {}
    ctx_blk = ctx.get("context_block")

    lines: list[str] = [
        "# Full audit comparison",
        "",
        f"- **URL:** {payload.get('url', '')}",
        f"- **Baseline:** `{payload.get('baseline_dir', '')}`",
        f"- **Current run:** `{payload.get('current_dir', '')}`",
        "",
    ]
    if ctx_blk:
        lines.extend([str(ctx_blk).rstrip(), ""])
    lines.extend(
        [
        "# Overall change",
        "",
        f"- **Direction:** {oc.get('direction', '')}",
        f"- **Confidence (heuristic):** {oc.get('confidence', '')}",
        "",
        oc.get("summary", ""),
        "",
        "# What improved",
        "",
        ]
    )
    for x in ch.get("improved") or []:
        lines.append(f"- {x}")
    if not ch.get("improved"):
        lines.append("- (none detected by heuristics)")
    lines.extend(["", "# What got worse", ""])
    for x in ch.get("degraded") or []:
        lines.append(f"- {x}")
    if not ch.get("degraded"):
        lines.append("- (none detected by heuristics)")
    lines.extend(["", "# Resolved issues", ""])
    for x in (ch.get("resolved_issues") or [])[:30]:
        lines.append(f"- `{x}`")
    if not ch.get("resolved_issues"):
        lines.append("- (none)")
    lines.extend(["", "# New issues", ""])
    for x in (ch.get("new_issues") or [])[:30]:
        lines.append(f"- `{x}`")
    if not ch.get("new_issues"):
        lines.append("- (none)")
    lines.extend(["", "# Conversion impact", ""])
    lines.append("## Before (summary excerpt)")
    lines.append(str(conv.get("before", "")))
    lines.append("")
    lines.append("## After (summary excerpt)")
    lines.append(str(conv.get("after", "")))
    lines.append("")
    lines.append("## Delta (heuristic)")
    lines.append(str(conv.get("delta", "")))
    lines.extend(["", "# Blocks / structure", ""])
    bc = blocks.get("content") or {}
    lines.append("## Content preset — missing blocks")
    lines.append(f"- Before: {', '.join(bc.get('before_missing_blocks') or []) or '—'}")
    lines.append(f"- After: {', '.join(bc.get('after_missing_blocks') or []) or '—'}")
    bk = blocks.get("craftum") or {}
    lines.append("")
    lines.append("## Craftum preset — missing blocks")
    lines.append(f"- Before: {', '.join(bk.get('before_missing_blocks') or []) or '—'}")
    lines.append(f"- After: {', '.join(bk.get('after_missing_blocks') or []) or '—'}")
    na = blocks.get("next_action") or {}
    lines.append("")
    lines.append("## Next action (content)")
    lines.append(f"- Before: {na.get('before') or '—'}")
    lines.append(f"- After: {na.get('after') or '—'}")
    lines.extend(["", "# Visual", ""])
    lines.append(f"- Baseline stub: {vis.get('baseline_stub')}")
    lines.append(f"- Current stub: {vis.get('current_stub')}")
    lines.append(f"- Issue counts (before → after): {vis.get('issue_counts_before_after')}")
    lines.append("")
    lines.append("## Overall visual (text)")
    lines.append(f"- Before: {vis.get('overall_before')}")
    lines.append(f"- After: {vis.get('overall_after')}")
    lines.extend(["", "# Limitations", ""])
    for x in payload.get("limitations") or []:
        lines.append(f"- {x}")
    if not payload.get("limitations"):
        lines.append("- (none)")
    lines.extend(["", "# Recommended next actions", ""])
    lines.append(
        "1. Read **resolved** vs **new** issues and validate against the live page.",
    )
    lines.append("2. Re-run baseline after major releases if the comparison reference is stale.")
    lines.append("3. Use `comparison.json` for programmatic follow-up; this file is heuristic, not ground truth.")
    return "\n".join(lines)
