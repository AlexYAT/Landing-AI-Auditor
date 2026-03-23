"""Craftum Block Planner: normalization, preset gating, readable output."""

from __future__ import annotations

import unittest

from app.services.analyzer import validate_and_normalize_audit_result
from app.services.report_builder import build_human_report, craftum_block_plan_section_for_preset
from app.core.prompts import build_system_prompt


_MIN_AUDIT = {
    "summary": {
        "overall_assessment": "x",
        "primary_conversion_goal_guess": "y",
        "top_strengths": [],
        "top_risks": [],
    },
    "issues": [],
    "recommendations": [],
    "quick_wins": [],
    "rewrite_texts": {"hero": "", "cta": "", "trust": ""},
    "block_analysis": {
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
            "style_fit": {"color_guidance": "", "font_guidance": "", "visual_guidance": ""},
        },
    },
    "action_roadmap": [],
}


class TestCraftumBlockPlanNormalization(unittest.TestCase):
    def test_parses_craftum_block_plan(self) -> None:
        data = {
            **_MIN_AUDIT,
            "craftum_block_plan": [
                {
                    "block_type": "testimonials",
                    "goal": "Доверие",
                    "placement": "сразу после hero",
                    "fields": ["Заголовок", "Имя"],
                    "content_example": "Отзыв: ...",
                    "style_guidance": "Как на странице",
                    "validation_check": "2 отзыва видны",
                }
            ],
        }
        r = validate_and_normalize_audit_result(data, lang="ru")
        self.assertEqual(len(r.craftum_block_plan), 1)
        row = r.craftum_block_plan[0]
        self.assertEqual(row.block_type, "testimonials")
        self.assertEqual(row.placement, "сразу после hero")
        self.assertEqual(row.fields, ["Заголовок", "Имя"])

    def test_missing_craftum_block_plan_is_empty(self) -> None:
        r = validate_and_normalize_audit_result(dict(_MIN_AUDIT), lang="ru")
        self.assertEqual(r.craftum_block_plan, [])

    def test_to_dict_includes_craftum_block_plan(self) -> None:
        data = {
            **_MIN_AUDIT,
            "craftum_block_plan": [
                {
                    "block_type": "faq",
                    "goal": "g",
                    "placement": "p",
                    "fields": ["Q1"],
                    "content_example": "e",
                    "style_guidance": "s",
                    "validation_check": "v",
                }
            ],
        }
        d = validate_and_normalize_audit_result(data, lang="ru").to_dict()
        self.assertIn("craftum_block_plan", d)
        self.assertEqual(len(d["craftum_block_plan"]), 1)
        self.assertEqual(d["craftum_block_plan"][0]["block_type"], "faq")


class TestCraftumBlockPlanReadable(unittest.TestCase):
    def test_section_labels_ru(self) -> None:
        rep = {
            "language": "ru",
            "preset": "craftum",
            "craftum_block_plan": [
                {
                    "block_type": "Отзывы",
                    "goal": "Снять сомнения",
                    "placement": "после hero",
                    "fields": ["Имя", "Текст"],
                    "content_example": "Марина: спасибо",
                    "style_guidance": "Спокойный тон",
                    "validation_check": "2 карточки",
                }
            ],
        }
        r = build_human_report(rep)
        text = r["craftum_block_plan_readable"]
        self.assertIn("Рекомендуемые блоки для добавления", text)
        self.assertIn("Тип блока", text)
        self.assertIn("Зачем", text)
        self.assertIn("Куда вставить", text)
        self.assertIn("Что заполнить", text)
        self.assertIn("Имя", text)
        self.assertIn("Как проверить", text)

    def test_craftum_section_includes_empty_notice(self) -> None:
        rep = {"language": "ru", "preset": "craftum", "craftum_block_plan": []}
        sec = craftum_block_plan_section_for_preset(rep)
        self.assertIn("Рекомендуемые блоки", sec)
        self.assertIn("нет элементов", sec.lower())

    def test_general_preset_no_section(self) -> None:
        rep = {"language": "ru", "preset": "general", "craftum_block_plan": []}
        self.assertEqual(craftum_block_plan_section_for_preset(rep), "")

    def test_markdown_includes_craftum_block_plan(self) -> None:
        from main import _build_readable_markdown

        md = _build_readable_markdown(
            {
                "preset": "craftum",
                "language": "ru",
                "summary": {},
                "issues": [],
                "recommendations": [],
                "quick_wins": [],
                "craftum_block_plan": [
                    {
                        "block_type": "FAQ",
                        "goal": "Ответы",
                        "placement": "перед футером",
                        "fields": ["Вопрос"],
                        "content_example": "Как записаться?",
                        "style_guidance": "Как на сайте",
                        "validation_check": "3 вопроса",
                    }
                ],
            }
        )
        self.assertIn("Рекомендуемые блоки для добавления", md)
        self.assertIn("FAQ", md)

    def test_general_markdown_omits_craftum_section(self) -> None:
        from main import _build_readable_markdown

        md = _build_readable_markdown(
            {
                "preset": "general",
                "language": "ru",
                "summary": {},
                "issues": [],
                "recommendations": [],
                "quick_wins": [],
            }
        )
        self.assertNotIn("Рекомендуемые блоки для добавления", md)


class TestCraftumPromptIncludesPlanner(unittest.TestCase):
    def test_craftum_preset_includes_block_planner_and_key(self) -> None:
        text = build_system_prompt("ru", preset="craftum")
        self.assertIn("CRAFTUM BLOCK PLANNER", text)
        self.assertIn("craftum_block_plan", text)

    def test_general_preset_no_block_planner_addon(self) -> None:
        text = build_system_prompt("ru", preset="general")
        self.assertNotIn("CRAFTUM BLOCK PLANNER", text)


if __name__ == "__main__":
    unittest.main()
