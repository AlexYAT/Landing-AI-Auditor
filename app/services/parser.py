"""Landing page parser service."""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests import Response
from requests.exceptions import RequestException

from app.core.config import Settings
from app.core.models import FormInfo, LinkItem, ParsedLanding


class ParsingError(Exception):
    """Raised when landing parsing fails."""


def _safe_text(value: str | None) -> str:
    """Normalize optional string values."""
    return value.strip() if value else ""


def _extract_links(soup: BeautifulSoup, final_url: str, max_links: int = 10) -> tuple[list[LinkItem], list[LinkItem]]:
    """Extract first N internal and external links."""
    internal: list[LinkItem] = []
    external: list[LinkItem] = []
    base_domain = urlparse(final_url).netloc

    for tag in soup.find_all("a", href=True):
        href = tag.get("href", "").strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue

        absolute_href = urljoin(final_url, href)
        domain = urlparse(absolute_href).netloc
        link_item = LinkItem(text=_safe_text(tag.get_text(" ", strip=True)), href=absolute_href)

        if domain == base_domain and len(internal) < max_links:
            internal.append(link_item)
        elif domain != base_domain and len(external) < max_links:
            external.append(link_item)

        if len(internal) >= max_links and len(external) >= max_links:
            break

    return internal, external


def _extract_forms(soup: BeautifulSoup, max_placeholders: int = 20) -> FormInfo:
    """Extract forms count and placeholders from input fields."""
    forms = soup.find_all("form")
    placeholders: list[str] = []

    for form in forms:
        fields = form.find_all(["input", "textarea"])
        for field in fields:
            value = _safe_text(field.get("placeholder"))
            if value and value not in placeholders:
                placeholders.append(value)
            if len(placeholders) >= max_placeholders:
                break
        if len(placeholders) >= max_placeholders:
            break

    return FormInfo(count=len(forms), placeholders=placeholders)


def _extract_visible_text(soup: BeautifulSoup, max_chars: int) -> str:
    """Extract visible text excerpt with truncation."""
    for unwanted in soup(["script", "style", "noscript"]):
        unwanted.decompose()

    text = " ".join(soup.stripped_strings)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def _fetch_page(url: str, timeout: int) -> Response:
    """Fetch URL and raise ParsingError on network failures."""
    try:
        response = requests.get(url, timeout=timeout, headers={"User-Agent": "LandingAuditBot/1.0"})
        response.raise_for_status()
        return response
    except RequestException as exc:
        raise ParsingError(f"Failed to fetch URL '{url}': {exc}") from exc


def parse_landing(url: str, settings: Settings) -> ParsedLanding:
    """Download and parse a landing page into structured model."""
    response = _fetch_page(url=url, timeout=settings.request_timeout)
    final_url = response.url
    soup = BeautifulSoup(response.text, "html.parser")

    title_tag = soup.find("title")
    meta_description_tag = soup.find("meta", attrs={"name": "description"})
    h1_tag = soup.find("h1")
    h2_tags = soup.find_all("h2")
    button_tags = soup.find_all(["button", "a"], attrs={"role": "button"})
    button_tags += soup.find_all("input", attrs={"type": ["submit", "button"]})

    internal_links, external_links = _extract_links(soup=soup, final_url=final_url)

    return ParsedLanding(
        final_url=final_url,
        title=_safe_text(title_tag.get_text(" ", strip=True) if title_tag else ""),
        meta_description=_safe_text(meta_description_tag.get("content") if meta_description_tag else ""),
        h1=_safe_text(h1_tag.get_text(" ", strip=True) if h1_tag else ""),
        h2_list=[_safe_text(h.get_text(" ", strip=True)) for h in h2_tags if _safe_text(h.get_text(" ", strip=True))],
        buttons=[
            _safe_text(btn.get_text(" ", strip=True) if hasattr(btn, "get_text") else btn.get("value"))
            for btn in button_tags
            if _safe_text(btn.get_text(" ", strip=True) if hasattr(btn, "get_text") else btn.get("value"))
        ],
        forms=_extract_forms(soup),
        internal_links=internal_links,
        external_links=external_links,
        visible_text_excerpt=_extract_visible_text(soup=soup, max_chars=settings.max_text_chars),
    )
