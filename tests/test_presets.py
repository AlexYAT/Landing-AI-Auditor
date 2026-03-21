"""Tests for landing audit presets (CLI, normalization, prompts)."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr

from app.core.presets import (
    ALLOWED_PRESETS,
    DEFAULT_PRESET,
    PRESETS_API_ORDER,
    build_preset_addon,
    normalize_preset,
    preset_section_title,
)
from app.core.prompts import build_system_prompt
from app.interfaces.cli import build_parser


class TestNormalizePreset(unittest.TestCase):
    def test_default_general(self) -> None:
        self.assertEqual(normalize_preset(None), DEFAULT_PRESET)
        self.assertEqual(normalize_preset(""), DEFAULT_PRESET)

    def test_services_lowercase(self) -> None:
        self.assertEqual(normalize_preset("  SERVICES "), "services")

    def test_invalid_raises(self) -> None:
        with self.assertRaises(ValueError):
            normalize_preset("not-a-preset")


class TestBuildPresetAddon(unittest.TestCase):
    def test_general_empty(self) -> None:
        self.assertEqual(build_preset_addon("general", "en"), "")
        self.assertEqual(build_preset_addon("general", "ru"), "")

    def test_services_non_empty_ru(self) -> None:
        text = build_preset_addon("services", "ru")
        self.assertIn("лид", text.lower())
        self.assertIn("конверс", text.lower())

    def test_course_en_keywords(self) -> None:
        text = build_preset_addon("course", "en")
        self.assertIn("course", text.lower())


class TestBuildSystemPromptPreset(unittest.TestCase):
    def test_general_omits_preset_section(self) -> None:
        text = build_system_prompt("en", preset="general")
        self.assertNotIn(preset_section_title("en"), text)

    def test_services_includes_focus_block_en(self) -> None:
        text = build_system_prompt("en", preset="services")
        self.assertIn(preset_section_title("en"), text)
        self.assertIn("lead capture", text.lower())

    def test_expert_includes_ru_block(self) -> None:
        text = build_system_prompt("ru", preset="expert")
        self.assertIn(preset_section_title("ru"), text)
        self.assertIn("эксперт", text.lower())


class TestCliPreset(unittest.TestCase):
    def test_default_is_general(self) -> None:
        args = build_parser().parse_args(["--url", "https://example.com"])
        self.assertEqual(args.preset, "general")

    def test_preset_services(self) -> None:
        args = build_parser().parse_args(
            ["--url", "https://example.com", "--preset", "services"],
        )
        self.assertEqual(args.preset, "services")

    def test_invalid_preset_exits(self) -> None:
        buf = io.StringIO()
        with self.assertRaises(SystemExit), redirect_stderr(buf):
            build_parser().parse_args(["--url", "https://example.com", "--preset", "bad"])


class TestPresetsApiOrder(unittest.TestCase):
    def test_order_matches_allowed(self) -> None:
        self.assertEqual(frozenset(PRESETS_API_ORDER), ALLOWED_PRESETS)


if __name__ == "__main__":
    unittest.main()
