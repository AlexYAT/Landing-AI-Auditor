"""Optional full-page screenshot for visual audit (Playwright; graceful fallback if missing)."""

from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_SCREENSHOT_TIMEOUT_MS = 15_000


def capture_page_screenshot(url: str, *, timeout_ms: int = DEFAULT_SCREENSHOT_TIMEOUT_MS) -> str | None:
    """
    Headless full-page PNG screenshot. Returns path to a temp file, or ``None`` on any failure.

    Requires: ``pip install playwright`` and ``playwright install chromium``.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning(
            "Playwright not installed; skipping screenshot. "
            "Install with: pip install playwright && playwright install chromium"
        )
        return None

    out = Path(tempfile.gettempdir()) / f"landing_visual_{uuid.uuid4().hex}.png"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_default_timeout(timeout_ms)
                page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                page.screenshot(path=str(out), full_page=True, timeout=timeout_ms)
            finally:
                browser.close()
        size_b = out.stat().st_size
        logger.info("Visual audit: screenshot OK path=%s size_bytes=%s", out, size_b)
        return str(out)
    except Exception as exc:
        logger.warning("Visual audit: screenshot failed (%s)", exc)
        try:
            if out.exists():
                out.unlink()
        except OSError:
            pass
        return None
