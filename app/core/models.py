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
    """Forms summary extracted from the page."""

    count: int
    placeholders: list[str] = field(default_factory=list)


@dataclass
class ParsedLanding:
    """Structured snapshot of a landing page."""

    final_url: str
    title: str
    meta_description: str
    h1: str
    h2_list: list[str]
    buttons: list[str]
    forms: FormInfo
    internal_links: list[LinkItem]
    external_links: list[LinkItem]
    visible_text_excerpt: str

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary."""
        return asdict(self)


@dataclass
class AuditIssue:
    """Detected issue impacting conversion."""

    title: str
    severity: str
    evidence: str
    impact: str


@dataclass
class Recommendation:
    """Recommendation for improving conversion."""

    title: str
    rationale: str
    expected_impact: str
    priority: str


@dataclass
class QuickWin:
    """Fast improvement with low implementation effort."""

    action: str
    why_it_matters: str


@dataclass
class AuditResult:
    """Final audit report in JSON-friendly structure."""

    summary: str
    issues: list[AuditIssue]
    recommendations: list[Recommendation]
    quick_wins: list[QuickWin]

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary."""
        return asdict(self)
