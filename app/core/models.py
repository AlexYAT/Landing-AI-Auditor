"""Domain models for landing parsing and audit output."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class LinkItem:
    """Link representation for parsed landing data."""

    text: str
    href: str


@dataclass
class FormInfo:
    """Detailed form structure extracted from the page."""

    action: str
    method: str
    input_types: list[str] = field(default_factory=list)
    placeholders: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)


@dataclass
class ParsedLanding:
    """Structured snapshot of a landing page."""

    original_url: str
    final_url: str
    status_code: int | None
    content_type: str | None
    title: str
    meta_description: str
    meta_keywords: str
    canonical_url: str
    page_language: str
    h1_list: list[str]
    # Backward compatibility with old parser shape.
    h1: str
    h2_list: list[str]
    h3_list: list[str]
    buttons: list[str]
    cta_buttons: list[str]
    cta_links: list[str]
    forms: list[FormInfo]
    internal_links: list[LinkItem]
    external_links: list[LinkItem]
    visible_text_excerpt: str
    hero_signals: list[str]
    pricing_signals: list[str]
    social_proof_signals: list[str]
    trust_signals: list[str]
    contact_signals: list[str]
    audit_meta: dict[str, Any] = field(default_factory=dict)
    # Mirrors audit_meta["text_quality_score"] (0.0–1.0) for API/UI convenience.
    text_quality_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary."""
        return asdict(self)


@dataclass
class AuditIssue:
    """Detected issue impacting conversion."""

    id: str
    title: str
    severity: str
    category: str
    evidence: str
    impact: str
    recommendation: str


@dataclass
class Recommendation:
    """Recommendation for improving conversion."""

    priority: str
    title: str
    action: str
    expected_impact: str
    implementation_for_craftum: str = ""
    example_text: str = ""


@dataclass
class QuickWin:
    """Fast improvement with low implementation effort."""

    title: str
    action: str
    why_it_matters: str


@dataclass
class CraftumBlockPlan:
    """
    Structured Craftum Block Planner row: what to add, where, fill, verify.

    Separate from ``Recommendation`` — additive planner view for craftum preset.
    """

    block_type: str = ""
    goal: str = ""
    placement: str = ""
    fields: list[str] = field(default_factory=list)
    content_example: str = ""
    style_guidance: str = ""
    validation_check: str = ""


@dataclass
class ContentRewrite:
    """Generated rewrite for a page block (e.g. hero)."""

    block: str
    before: str
    after: str
    why: str


@dataclass
class AuditSummary:
    """High-level conversion assessment."""

    overall_assessment: str = ""
    primary_conversion_goal_guess: str = ""
    top_strengths: list[str] = field(default_factory=list)
    top_risks: list[str] = field(default_factory=list)


def _default_rewrite_texts() -> dict[str, str]:
    return {"hero": "", "cta": "", "trust": ""}


def _default_block_analysis() -> dict[str, Any]:
    return {
        "blocks_detected": [],
        "missing_blocks": [],
        "next_block": {
            "type": "",
            "priority": "",
            "reason": "",
            "placement": "",
            "implementation_for_craftum": "",
            "example": "",
            "expected_impact": "",
            "confidence": 0.0,
            "why_now": "",
            "effort": "medium",
            "style_fit": {
                "color_guidance": "",
                "font_guidance": "",
                "visual_guidance": "",
            },
        },
    }


@dataclass
class VisualIssue:
    """Visual communication issue (visual audit mode; separate from ``AuditIssue``)."""

    problem: str = ""
    why_it_matters: str = ""
    recommendation: str = ""
    severity: str = "medium"


@dataclass
class VisualAuditResult:
    """Structured visual audit (text + structure inference only; separate from ``AuditResult``)."""

    overall_visual_assessment: str = ""
    visual_issues: list[VisualIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_type": "visual",
            "overall_visual_assessment": self.overall_visual_assessment,
            "visual_issues": [asdict(v) for v in self.visual_issues],
        }


@dataclass
class AuditResult:
    """Final audit report in JSON-friendly structure."""

    summary: AuditSummary = field(default_factory=AuditSummary)
    issues: list[AuditIssue] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    quick_wins: list[QuickWin] = field(default_factory=list)
    rewrites: list[ContentRewrite] = field(default_factory=list)
    # Ready-to-paste strings per block (distinct from ``rewrites`` array for structured rewrite mode).
    rewrite_texts: dict[str, str] = field(default_factory=_default_rewrite_texts)
    block_analysis: dict[str, Any] = field(default_factory=_default_block_analysis)
    action_roadmap: list[dict[str, Any]] = field(default_factory=list)
    craftum_block_plan: list[CraftumBlockPlan] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary."""
        return asdict(self)
