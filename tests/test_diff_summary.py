"""LLM diff summary helper (``--diff``), no network."""

from __future__ import annotations

import unittest

from app.core.config import Settings
from app.services.diff_summary import build_diff_payload_for_llm, summarize_diff_with_llm


class TestDiffSummaryLlm(unittest.TestCase):
    def test_returns_empty_without_api_key(self) -> None:
        s = Settings(openai_api_key="")
        out = summarize_diff_with_llm({}, {}, {"old_missing_blocks": []}, "ru", s)
        self.assertEqual(out, "")

    def test_build_payload_includes_lists_and_diff(self) -> None:
        p = build_diff_payload_for_llm(
            ["a"],
            ["a", "b"],
            ["s1"],
            ["s1", "s2"],
            ["b"],
            [],
            ["s2"],
            [],
            "hero",
            "cta",
            {},
            {},
        )
        self.assertEqual(p["old_missing_blocks"], ["a"])
        self.assertEqual(p["new_missing_blocks"], ["a", "b"])
        self.assertEqual(p["diff"]["missing_blocks_added"], ["b"])


if __name__ == "__main__":
    unittest.main()
