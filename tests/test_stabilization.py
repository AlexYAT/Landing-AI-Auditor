"""Targeted tests: trust anti-fabrication prompts, quick_wins guardrails, parser noise, stdout UTF-8 helper."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

from app.core.prompts import BASE_SYSTEM_PROMPT, REWRITE_BLOCK_GUIDE_EN, REWRITE_BLOCK_GUIDE_RU
from app.services.parser import strip_builder_footer_noise


def _load_main_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "main.py"
    spec = importlib.util.spec_from_file_location("landing_main_cli", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestTrustRewriteAntiFabricationPrompts(unittest.TestCase):
    def test_ru_trust_forbids_fabricated_metrics(self) -> None:
        t = REWRITE_BLOCK_GUIDE_RU["trust"]
        self.assertIn("Более 100 довольных клиентов", t)
        self.assertIn("Рейтинг 4.9", t)
        self.assertIn("КРИТИЧНО", t)
        self.assertIn("visible_text_excerpt", t)

    def test_en_trust_forbids_fabricated_proof(self) -> None:
        t = REWRITE_BLOCK_GUIDE_EN["trust"]
        self.assertIn("100+ happy clients", t)
        self.assertIn("CRITICAL", t)
        self.assertIn("visible_text_excerpt", t)


class TestQuickWinsVisualGuardrails(unittest.TestCase):
    def test_base_prompt_bans_color_and_pixel_tweaks(self) -> None:
        b = BASE_SYSTEM_PROMPT
        self.assertIn("hex codes", b.lower())
        self.assertIn("font-size", b)
        self.assertIn("letter-spacing", b)
        self.assertIn("quick_wins", b)


class TestBuilderFooterNoise(unittest.TestCase):
    def test_removes_russian_craftum_attribution(self) -> None:
        raw = (
            "Астро-психология Записаться Craftum Сайт создан на Craftum"
        )
        out = strip_builder_footer_noise(raw)
        self.assertNotIn("Craftum", out)
        self.assertNotIn("создан", out.lower())
        self.assertIn("Астро-психология", out)
        self.assertIn("Записаться", out)

    def test_removes_powered_by_english(self) -> None:
        raw = "Hello world powered by Craftum"
        out = strip_builder_footer_noise(raw)
        self.assertNotIn("Craftum", out)
        self.assertIn("Hello world", out)

    def test_empty_safe(self) -> None:
        self.assertEqual(strip_builder_footer_noise(""), "")


class TestConfigureStdioUtf8(unittest.TestCase):
    def test_runs_without_error(self) -> None:
        m = _load_main_module()
        m._configure_stdio_utf8()

    def test_swallows_reconfigure_oserror(self) -> None:
        class _BadOut:
            def reconfigure(self, **kwargs):
                raise OSError("simulated")

        m = _load_main_module()
        old = sys.stdout
        try:
            sys.stdout = _BadOut()
            m._configure_stdio_utf8()
        finally:
            sys.stdout = old


if __name__ == "__main__":
    unittest.main()
