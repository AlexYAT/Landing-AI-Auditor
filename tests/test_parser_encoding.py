"""Tests for HTML decoding, text quality heuristics, and content stripping."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.services.parser import (
    assess_visible_text_quality,
    decode_response_html,
    strip_non_content_tags,
)
from bs4 import BeautifulSoup


class TestDecodeResponseHtml(unittest.TestCase):
    def test_utf8_content(self) -> None:
        r = MagicMock()
        r.content = "<html>тест</html>".encode("utf-8")
        r.status_code = 200
        r.encoding = "utf-8"
        r.apparent_encoding = "utf-8"
        r.headers = {"Content-Type": "text/html; charset=utf-8"}
        text, meta = decode_response_html(r)
        self.assertIn("тест", text)
        self.assertEqual(meta.get("used_encoding"), "utf-8")

    def test_wrong_header_utf8_bytes(self) -> None:
        """Latin-1 header but body is UTF-8 — apparent or utf-8 candidate should win."""
        r = MagicMock()
        body = "<title>Кот</title>".encode("utf-8")
        r.content = body
        r.status_code = 200
        r.encoding = "ISO-8859-1"
        r.apparent_encoding = "utf-8"
        r.headers = {"Content-Type": "text/html; charset=ISO-8859-1"}
        text, meta = decode_response_html(r)
        self.assertIn("Кот", text)


class TestAssessVisibleTextQuality(unittest.TestCase):
    def test_normal_russian(self) -> None:
        q = assess_visible_text_quality("Астрология и гороскопы для всех знаков зодиака.")
        self.assertEqual(q["quality_hint"], "good")
        self.assertLess(q["replacement_char_ratio"], 0.0001)
        self.assertIn("text_quality_score", q)
        self.assertGreaterEqual(q["text_quality_score"], 0.0)
        self.assertLessEqual(q["text_quality_score"], 1.0)
        self.assertGreater(q["text_quality_score"], 0.85)

    def test_many_replacement_chars(self) -> None:
        bad = "a" * 100 + "\ufffd" * 20
        q = assess_visible_text_quality(bad)
        self.assertEqual(q["quality_hint"], "poor")
        self.assertLess(q["text_quality_score"], 0.55)

    def test_empty_text_score_zero(self) -> None:
        q = assess_visible_text_quality("")
        self.assertEqual(q["quality_hint"], "empty")
        self.assertEqual(q["text_quality_score"], 0.0)


class TestStripNonContent(unittest.TestCase):
    def test_removes_script_json_ld(self) -> None:
        html = (
            "<html><head>"
            '<script type="application/ld+json">{"x":1}</script>'
            "</head><body><p>Hello</p></body></html>"
        )
        soup = BeautifulSoup(html, "html.parser")
        strip_non_content_tags(soup)
        text = soup.get_text()
        self.assertIn("Hello", text)
        self.assertNotIn("application", text)


if __name__ == "__main__":
    unittest.main()
