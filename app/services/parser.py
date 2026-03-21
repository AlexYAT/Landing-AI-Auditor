"""Landing page parser service."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any
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

# Narrow builder attribution phrases (avoid stripping arbitrary brand mentions).
_BUILDER_ATTRIBUTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\s*сайт\s+создан\s+на\s+craftum\.?\s*"),
    re.compile(r"(?i)\s*создан[ао]?\s+на\s+craftum\.?\s*"),
    re.compile(r"(?i)\s*(?:website|site)\s+(?:made|created)\s+(?:with|on|using)\s+craftum\.?\s*"),
    re.compile(r"(?i)\s*powered\s+by\s+craftum\.?\s*"),
)
# Trailing builder name after phrase removal (conservative: end of string only).
_TRAILING_BUILDER_CRAFTUM = re.compile(r"(?i)\s+craftum\.?\s*$")


def strip_builder_footer_noise(text: str) -> str:
    """Remove common no-code builder footer boilerplate from merged visible text."""
    if not text:
        return text
    cleaned = text
    for rx in _BUILDER_ATTRIBUTION_PATTERNS:
        cleaned = rx.sub(" ", cleaned)
    cleaned = _TRAILING_BUILDER_CRAFTUM.sub("", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


logger = logging.getLogger(__name__)


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


def _charset_from_content_type(content_type: str | None) -> str | None:
    """Parse charset from Content-Type header."""
    if not content_type or "charset=" not in content_type.lower():
        return None
    try:
        part = content_type.split("charset=")[1].split(";")[0].strip().strip('"').strip("'")
        return part or None
    except IndexError:
        return None


def decode_response_html(response: Response) -> tuple[str, dict[str, str | None]]:
    """
    Decode HTML from raw bytes using a safe candidate order.

    Avoid relying on ``response.text`` alone when the declared encoding is wrong.
    Generic ISO-8859-1 / Latin-1 headers are often wrong for UTF-8 sites; try apparent + utf-8 first.
    """
    raw: bytes = response.content
    header_cs = _charset_from_content_type(response.headers.get("Content-Type"))
    meta: dict[str, str | None] = {
        "status_code": str(response.status_code),
        "header_encoding": response.encoding,
        "apparent_encoding": response.apparent_encoding,
        "charset_from_content_type": header_cs,
    }

    _LOW_TRUST = frozenset(
        {"iso-8859-1", "latin-1", "windows-1252", "cp1252", "us-ascii"},
    )

    def _norm(enc: str | None) -> str | None:
        if not enc or str(enc).lower() in {"none", "7bit", "8bit", "binary"}:
            return None
        return str(enc).lower().replace("utf8", "utf-8")

    candidates: list[str] = []
    seen: set[str] = set()

    def _add(enc: str | None) -> None:
        n = _norm(enc)
        if n and n not in seen:
            seen.add(n)
            candidates.append(n)

    # High trust first: chardet guess + UTF-8 (common for modern HTML)
    _add(response.apparent_encoding)
    _add("utf-8")

    for c in (header_cs, response.encoding):
        n = _norm(c)
        if n and n not in _LOW_TRUST:
            _add(c)

    for c in (header_cs, response.encoding):
        n = _norm(c)
        if n and n in _LOW_TRUST:
            _add(c)

    for enc in candidates:
        try:
            text = raw.decode(enc)
            meta["used_encoding"] = enc
            return text, meta
        except (LookupError, UnicodeDecodeError):
            continue

    text = raw.decode("utf-8", errors="replace")
    meta["used_encoding"] = "utf-8-replace"
    return text, meta


def _text_quality_score(ratio_rep: float, ratio_ctl: float, letter_ratio: float, char_count: int) -> float:
    """
    Normalized 0.0–1.0 score from the same ratios used for quality_hint (practical heuristic).

    Higher = cleaner, more readable extracted text for auditing.
    """
    if char_count <= 0:
        return 0.0
    score = 1.0
    # Replacement characters (strong signal of decode/extraction damage)
    score -= min(0.6, ratio_rep * 100.0)
    # Control characters
    score -= min(0.45, ratio_ctl * 40.0)
    # Very low letter/symbol density suggests garbage or broken text
    score -= max(0.0, 0.42 - letter_ratio * 3.5)
    return round(max(0.0, min(1.0, score)), 4)


def assess_visible_text_quality(text: str) -> dict[str, Any]:
    """
    Heuristic for whether extracted text looks like normal human-readable content.

    Returns quality_hint, ratio metrics, and text_quality_score (0.0-1.0) for audit_meta / UI.
    """
    if not text:
        return {
            "quality_hint": "empty",
            "replacement_char_ratio": 0.0,
            "control_char_ratio": 0.0,
            "letter_ratio": 0.0,
            "character_count": 0,
            "text_quality_score": 0.0,
        }

    n = len(text)
    replacement = text.count("\ufffd")
    control_bad = len(re.findall(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", text))
    letters = len(re.findall(r"[\wА-Яа-яЁёĀ-ž]", text, re.UNICODE))

    ratio_rep = replacement / n
    ratio_ctl = control_bad / n
    letter_ratio = letters / n

    if ratio_rep > 0.005 or ratio_ctl > 0.01 or letter_ratio < 0.05:
        quality = "poor"
    elif ratio_rep > 0.0008 or ratio_ctl > 0.003:
        quality = "uncertain"
    else:
        quality = "good"

    tqs = _text_quality_score(ratio_rep, ratio_ctl, letter_ratio, n)

    return {
        "quality_hint": quality,
        "replacement_char_ratio": round(ratio_rep, 6),
        "control_char_ratio": round(ratio_ctl, 6),
        "letter_ratio": round(letter_ratio, 4),
        "character_count": n,
        "text_quality_score": tqs,
    }


def strip_non_content_tags(soup: BeautifulSoup) -> None:
    """Remove tags that should not contribute to visible text (in-place)."""
    for tag_name in ("script", "style", "noscript", "svg", "iframe", "template", "link", "meta"):
        for tag in soup.find_all(tag_name):
            tag.decompose()

    for tag in soup.find_all("script", type=re.compile(r"ld\+json", re.I)):
        tag.decompose()


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
    strip_non_content_tags(soup_copy)

    chunks: list[str] = []
    for text in soup_copy.stripped_strings:
        normalized = _safe_text(text)
        if len(normalized) < 2:
            continue
        chunks.append(normalized)

    merged = " ".join(chunks)
    merged = re.sub(r"\s+", " ", merged).strip()
    merged = strip_builder_footer_noise(merged)
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


def parse_landing(
    url: str,
    settings: Settings,
    debug_dir: str | Path | None = None,
) -> ParsedLanding:
    """Download and parse a landing page into structured model."""
    normalized_url = normalize_url(url)
    response = fetch_html(url=normalized_url, timeout=settings.request_timeout)
    final_url = _safe_text(response.url)
    content_type = _safe_text(response.headers.get("Content-Type"))
    html_text, decode_meta = decode_response_html(response)
    soup = BeautifulSoup(html_text, "html.parser")
    strip_non_content_tags(soup)

    meta = extract_meta(soup=soup, final_url=final_url)
    headings = extract_headings(soup=soup)
    buttons, cta_buttons, cta_links = extract_buttons(soup=soup)
    forms = extract_forms(soup=soup)
    internal_links, external_links = extract_links(soup=soup, final_url=final_url)
    visible_text_excerpt = extract_text(soup=soup, max_chars=settings.max_text_chars)
    signals = detect_page_signals(soup=soup, visible_text=visible_text_excerpt)
    text_quality = assess_visible_text_quality(visible_text_excerpt)
    audit_meta: dict[str, Any] = {
        "decoding": decode_meta,
        "visible_text_quality": text_quality,
        "quality_hint": text_quality.get("quality_hint"),
        "text_quality_score": text_quality.get("text_quality_score"),
    }

    if debug_dir is not None:
        dbg = Path(debug_dir)
        dbg.mkdir(parents=True, exist_ok=True)
        (dbg / "raw.html").write_text(html_text, encoding="utf-8", errors="replace")
        (dbg / "extracted_text.txt").write_text(visible_text_excerpt, encoding="utf-8", errors="replace")
        preview_len = min(2000, len(visible_text_excerpt))
        preview = visible_text_excerpt[:preview_len]
        # Console-safe line (Windows cp1251 etc.): real text is in output/debug/.../extracted_text.txt
        preview_safe = preview.encode("ascii", errors="backslashreplace").decode("ascii")
        logger.info(
            "Parser debug: status_code=%s response.encoding=%s apparent_encoding=%s used_encoding=%s "
            "text_quality_hint=%s",
            decode_meta.get("status_code"),
            decode_meta.get("header_encoding"),
            decode_meta.get("apparent_encoding"),
            decode_meta.get("used_encoding"),
            text_quality.get("quality_hint"),
        )
        logger.info(
            "Parser debug: clean_text preview (first %s chars, ASCII-escaped for logs):\n%s",
            preview_len,
            preview_safe,
        )

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
        audit_meta=audit_meta,
        text_quality_score=float(text_quality.get("text_quality_score") or 0.0),
    )
