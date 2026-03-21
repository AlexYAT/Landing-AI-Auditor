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


@dataclass
class QuickWin:
    """Fast improvement with low implementation effort."""

    title: str
    action: str
    why_it_matters: str


@dataclass
class AuditSummary:
    """High-level conversion assessment."""

    overall_assessment: str = ""
    primary_conversion_goal_guess: str = ""
    top_strengths: list[str] = field(default_factory=list)
    top_risks: list[str] = field(default_factory=list)


@dataclass
class AuditResult:
    """Final audit report in JSON-friendly structure."""

    summary: AuditSummary = field(default_factory=AuditSummary)
    issues: list[AuditIssue] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    quick_wins: list[QuickWin] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary."""
        return asdict(self)
