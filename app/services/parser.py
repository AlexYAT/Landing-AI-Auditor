"""Landing page parser service."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from requests import Response
from requests.exceptions import ConnectionError, InvalidURL, RequestException, Timeout

from app.core.config import Settings
from app.core.models import FormInfo, LinkItem, ParsedLanding


MAX_PAGE_BYTES = 3 * 1024 * 1024
MAX_LINKS = 20
CTA_KEYWORDS = (
    "купить",
    "заказать",
    "оставить заявку",
    "записаться",
    "начать",
    "попробовать",
    "получить",
    "связаться",
    "submit",
    "buy",
    "order",
    "start",
    "try",
    "contact",
    "sign up",
    "signup",
    "get started",
)
PRICING_KEYWORDS = ("тариф", "цена", "стоимость", "plans", "pricing", "price")
SOCIAL_PROOF_KEYWORDS = ("отзывы", "кейсы", "клиенты", "results", "testimonials", "reviews")
TRUST_KEYWORDS = ("гарантия", "сертификат", "рейтинг", "лицензия", "secure", "security", "ssl")
CONTACT_KEYWORDS = (
    "телефон",
    "email",
    "e-mail",
    "telegram",
    "whatsapp",
    "address",
    "адрес",
    "contact",
    "contacts",
)


class ParsingError(Exception):
    """Raised when landing parsing fails."""


def _safe_text(value: str | None) -> str:
    """Normalize optional string values."""
    return re.sub(r"\s+", " ", value).strip() if value else ""


def normalize_url(url: str) -> str:
    """Normalize URL and ensure scheme is present."""
    raw = _safe_text(url)
    if not raw:
        raise ParsingError("URL is empty.")

    candidate = raw if "://" in raw else f"https://{raw}"
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        raise ParsingError(f"Invalid URL scheme: '{parsed.scheme}'. Use http/https.")
    if not parsed.netloc:
        raise ParsingError(f"Invalid URL: '{url}'.")
    return urlunparse(parsed)


def fetch_html(url: str, timeout: int) -> Response:
    """Fetch HTML page with robust network and content checks."""
    try:
        response = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": "LandingAuditBot/1.0"},
        )
    except InvalidURL as exc:
        raise ParsingError(f"Invalid URL '{url}': {exc}") from exc
    except Timeout as exc:
        raise ParsingError(f"Request timeout while fetching '{url}'.") from exc
    except ConnectionError as exc:
        raise ParsingError(f"Connection error while fetching '{url}': {exc}") from exc
    except RequestException as exc:
        raise ParsingError(f"Request failed for '{url}': {exc}") from exc

    try:
        response.raise_for_status()
    except RequestException as exc:
        raise ParsingError(f"HTTP error {response.status_code} for '{url}'.") from exc

    content_type = _safe_text(response.headers.get("Content-Type"))
    if "text/html" not in content_type.lower():
        raise ParsingError(f"Unsupported content type '{content_type or 'unknown'}'. Expected HTML page.")

    content_length = response.headers.get("Content-Length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_PAGE_BYTES:
        raise ParsingError("Page is too large to process safely.")
    if len(response.content) > MAX_PAGE_BYTES:
        raise ParsingError("Page is too large to process safely.")

    return response


def extract_meta(soup: BeautifulSoup, final_url: str) -> dict[str, str]:
    """Extract title and meta-level attributes."""
    title_tag = soup.find("title")
    desc = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    keywords = soup.find("meta", attrs={"name": re.compile(r"^keywords$", re.I)})
    canonical = soup.find("link", attrs={"rel": re.compile(r"canonical", re.I)})
    html_tag = soup.find("html")
    canonical_href = _safe_text(canonical.get("href") if canonical else "")
    canonical_url = urljoin(final_url, canonical_href) if canonical_href else ""

    return {
        "title": _safe_text(title_tag.get_text(" ", strip=True) if title_tag else ""),
        "meta_description": _safe_text(desc.get("content") if desc else ""),
        "meta_keywords": _safe_text(keywords.get("content") if keywords else ""),
        "canonical_url": canonical_url,
        "page_language": _safe_text(html_tag.get("lang") if html_tag else ""),
    }


def extract_headings(soup: BeautifulSoup) -> dict[str, list[str] | str]:
    """Extract h1/h2/h3 heading lists and backward-compatible h1."""
    h1_list = [_safe_text(tag.get_text(" ", strip=True)) for tag in soup.find_all("h1")]
    h2_list = [_safe_text(tag.get_text(" ", strip=True)) for tag in soup.find_all("h2")]
    h3_list = [_safe_text(tag.get_text(" ", strip=True)) for tag in soup.find_all("h3")]

    h1_list = [item for item in h1_list if item]
    h2_list = [item for item in h2_list if item]
    h3_list = [item for item in h3_list if item]

    return {
        "h1": h1_list[0] if h1_list else "",
        "h1_list": h1_list,
        "h2_list": h2_list,
        "h3_list": h3_list,
    }


def _is_cta_text(text: str) -> bool:
    """Check if text matches CTA heuristics."""
    lowered = text.lower()
    return any(keyword in lowered for keyword in CTA_KEYWORDS)


def extract_buttons(soup: BeautifulSoup) -> tuple[list[str], list[str], list[str]]:
    """Extract all button-like elements and CTA subsets."""
    all_buttons: list[str] = []
    cta_buttons: list[str] = []
    cta_links: list[str] = []

    button_like_tags = soup.find_all(["button", "input", "a"])
    for tag in button_like_tags:
        tag_name = tag.name.lower() if tag.name else ""
        text = _safe_text(
            tag.get_text(" ", strip=True)
            if tag_name != "input"
            else (tag.get("value") or tag.get("aria-label") or "")
        )
        if not text:
            continue

        is_button_like = tag_name == "button" or (
            tag_name == "input" and _safe_text(tag.get("type")).lower() in {"submit", "button"}
        )
        is_button_like = is_button_like or _safe_text(tag.get("role")).lower() == "button"

        if is_button_like:
            all_buttons.append(text)
            if _is_cta_text(text):
                cta_buttons.append(text)

        if tag_name == "a" and _is_cta_text(text):
            cta_links.append(text)

    return list(dict.fromkeys(all_buttons)), list(dict.fromkeys(cta_buttons)), list(dict.fromkeys(cta_links))


def extract_forms(soup: BeautifulSoup) -> list[FormInfo]:
    """Extract detailed form blocks."""
    result: list[FormInfo] = []

    for form in soup.find_all("form"):
        action = _safe_text(form.get("action"))
        method = _safe_text(form.get("method")).lower() or "get"
        input_types: list[str] = []
        placeholders: list[str] = []
        labels: list[str] = []

        fields = form.find_all(["input", "select", "textarea"])
        for field in fields:
            input_type = _safe_text(field.get("type")) if field.name == "input" else field.name
            if input_type:
                input_types.append(input_type.lower())

            placeholder = _safe_text(field.get("placeholder"))
            if placeholder:
                placeholders.append(placeholder)

            field_id = _safe_text(field.get("id"))
            aria_label = _safe_text(field.get("aria-label"))
            if aria_label:
                labels.append(aria_label)

            if field_id:
                label_tag = form.find("label", attrs={"for": field_id})
                if label_tag:
                    label_text = _safe_text(label_tag.get_text(" ", strip=True))
                    if label_text:
                        labels.append(label_text)

            parent_label = field.find_parent("label")
            if parent_label:
                nested_text = _safe_text(parent_label.get_text(" ", strip=True))
                if nested_text:
                    labels.append(nested_text)

        result.append(
            FormInfo(
                action=action,
                method=method,
                input_types=list(dict.fromkeys(input_types)),
                placeholders=list(dict.fromkeys(placeholders)),
                labels=list(dict.fromkeys(labels)),
            )
        )

    return result


def extract_links(soup: BeautifulSoup, final_url: str, max_links: int = MAX_LINKS) -> tuple[list[LinkItem], list[LinkItem]]:
    """Extract first N internal/external links with href normalization."""
    internal: list[LinkItem] = []
    external: list[LinkItem] = []
    base_domain = urlparse(final_url).netloc.lower()
    seen: set[str] = set()

    for tag in soup.find_all("a", href=True):
        href = _safe_text(tag.get("href"))
        if not href:
            continue
        lowered = href.lower()
        if lowered.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        absolute_href = urljoin(final_url, href)
        parsed = urlparse(absolute_href)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue

        normalized_href = urlunparse(parsed._replace(fragment=""))
        if normalized_href in seen:
            continue
        seen.add(normalized_href)

        item = LinkItem(text=_safe_text(tag.get_text(" ", strip=True)), href=normalized_href)
        target = internal if parsed.netloc.lower() == base_domain else external

        if len(target) < max_links:
            target.append(item)
        if len(internal) >= max_links and len(external) >= max_links:
            break

    return internal, external


def extract_text(soup: BeautifulSoup, max_chars: int) -> str:
    """Extract visible text excerpt and trim noisy spaces."""
    soup_copy = BeautifulSoup(str(soup), "html.parser")
    for unwanted in soup_copy(["script", "style", "noscript"]):
        unwanted.decompose()

    chunks: list[str] = []
    for text in soup_copy.stripped_strings:
        normalized = _safe_text(text)
        if len(normalized) < 2:
            continue
        chunks.append(normalized)

    merged = " ".join(chunks)
    merged = re.sub(r"\s+", " ", merged).strip()
    if len(merged) <= max_chars:
        return merged
    return merged[:max_chars].rstrip() + "..."


def _collect_keyword_hits(text_blob: str, keywords: tuple[str, ...]) -> list[str]:
    """Return matched keyword list preserving order."""
    lowered = text_blob.lower()
    return [kw for kw in keywords if kw in lowered]


def detect_page_signals(soup: BeautifulSoup, visible_text: str) -> dict[str, list[str]]:
    """Detect heuristic CRO signals from page structure and text."""
    text_blob = f"{visible_text} {' '.join(soup.stripped_strings)}".lower()
    hero_signals: list[str] = []

    if soup.find("h1"):
        hero_signals.append("first_screen_h1")
    if soup.find(["button", "a"], string=re.compile("|".join(re.escape(k) for k in CTA_KEYWORDS), re.I)):
        hero_signals.append("prominent_cta_detected")
    if any(token in text_blob for token in ("оффер", "offer", "лучшее решение", "best solution")):
        hero_signals.append("offer_message_detected")

    contact_signals = _collect_keyword_hits(text_blob, CONTACT_KEYWORDS)
    for a_tag in soup.find_all("a", href=True):
        href = _safe_text(a_tag.get("href")).lower()
        if href.startswith("mailto:") and "mailto" not in contact_signals:
            contact_signals.append("mailto")
        if href.startswith("tel:") and "tel" not in contact_signals:
            contact_signals.append("tel")

    return {
        "hero_signals": hero_signals,
        "pricing_signals": _collect_keyword_hits(text_blob, PRICING_KEYWORDS),
        "social_proof_signals": _collect_keyword_hits(text_blob, SOCIAL_PROOF_KEYWORDS),
        "trust_signals": _collect_keyword_hits(text_blob, TRUST_KEYWORDS),
        "contact_signals": contact_signals,
    }


def parse_landing(url: str, settings: Settings) -> ParsedLanding:
    """Download and parse a landing page into structured model."""
    normalized_url = normalize_url(url)
    response = fetch_html(url=normalized_url, timeout=settings.request_timeout)
    final_url = _safe_text(response.url)
    content_type = _safe_text(response.headers.get("Content-Type"))
    soup = BeautifulSoup(response.text, "html.parser")

    meta = extract_meta(soup=soup, final_url=final_url)
    headings = extract_headings(soup=soup)
    buttons, cta_buttons, cta_links = extract_buttons(soup=soup)
    forms = extract_forms(soup=soup)
    internal_links, external_links = extract_links(soup=soup, final_url=final_url)
    visible_text_excerpt = extract_text(soup=soup, max_chars=settings.max_text_chars)
    signals = detect_page_signals(soup=soup, visible_text=visible_text_excerpt)

    return ParsedLanding(
        original_url=normalized_url,
        final_url=final_url,
        status_code=response.status_code,
        content_type=content_type or None,
        title=meta["title"],
        meta_description=meta["meta_description"],
        meta_keywords=meta["meta_keywords"],
        canonical_url=meta["canonical_url"],
        page_language=meta["page_language"],
        h1_list=headings["h1_list"],
        h1=headings["h1"],
        h2_list=headings["h2_list"],
        h3_list=headings["h3_list"],
        buttons=buttons,
        cta_buttons=cta_buttons,
        cta_links=cta_links,
        forms=forms,
        internal_links=internal_links,
        external_links=external_links,
        visible_text_excerpt=visible_text_excerpt,
        hero_signals=signals["hero_signals"],
        pricing_signals=signals["pricing_signals"],
        social_proof_signals=signals["social_proof_signals"],
        trust_signals=signals["trust_signals"],
        contact_signals=signals["contact_signals"],
    )
