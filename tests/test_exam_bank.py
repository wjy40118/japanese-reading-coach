from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.exam_bank import (
    analyze_exam_bank,
    filter_exam_bank,
    load_exam_bank,
    search_exam_bank,
)
from src.rule_analyzer import RuleBasedAnalyzer


class ExamBankTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entries = load_exam_bank()
        self.analyzer = RuleBasedAnalyzer()

    def test_bank_covers_five_years(self) -> None:
        years = {entry["year"] for entry in self.entries}
        self.assertEqual(years, set(range(2017, 2027)))
        self.assertGreaterEqual(len(self.entries), 20)

    def test_filter_by_year(self) -> None:
        selected = filter_exam_bank(self.entries, [2025, 2026])
        self.assertEqual(len(selected), 4)
        self.assertTrue(all(entry["year"] in {2025, 2026} for entry in selected))

    def test_search_requires_exact_year_and_level(self) -> None:
        selected = search_exam_bank(self.entries, 2025, "N1")
        self.assertTrue(selected)
        self.assertTrue(
            all(
                entry["year"] == 2025 and entry["level"] == "N1"
                for entry in selected
            )
        )
        self.assertEqual(search_exam_bank(self.entries, 2025, "N4"), [])

    def test_batch_analysis_aggregates_points(self) -> None:
        result = analyze_exam_bank(
            self.entries,
            self.analyzer,
            focus=["全部"],
        )
        self.assertEqual(len(result.articles), 20)
        self.assertEqual(result.total_questions, 40)
        self.assertGreaterEqual(len(result.knowledge_points), 6)
        self.assertTrue(result.practice)
        self.assertTrue(
            all(1 <= point.exam_frequency <= 5 for point in result.knowledge_points)
        )

        keys = [(point.kind, point.term) for point in result.knowledge_points]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(point.years for point in result.knowledge_points))
        self.assertTrue(all(point.quotes for point in result.knowledge_points))
        passages = [entry["passage"] for entry in self.entries]
        self.assertTrue(
            all(
                any(quote in passage for passage in passages)
                for point in result.knowledge_points
                for quote in point.quotes
            )
        )
        self.assertIn("原创模拟题", result.disclaimer)
        self.assertEqual(result.source_label, "原创模拟题")

    def test_every_selected_article_has_points(self) -> None:
        result = analyze_exam_bank(
            filter_exam_bank(self.entries, [2023]),
            self.analyzer,
            focus=["全部"],
        )
        self.assertTrue(all(item.analysis.points for item in result.articles))

    def test_bank_analysis_uses_selected_level(self) -> None:
        for selected_level in ("N4", "N2", "N1"):
            result = analyze_exam_bank(
                self.entries,
                self.analyzer,
                level=selected_level,
                focus=["全部"],
            )
            point_levels = [
                point.estimated_level
                for article in result.articles
                for point in article.analysis.points
            ]
            self.assertTrue(point_levels)
            self.assertTrue(
                all(level.startswith(selected_level) for level in point_levels)
            )
            self.assertTrue(result.knowledge_points)

    def test_n2_and_n1_bank_have_practice(self) -> None:
        for selected_level in ("N2", "N1"):
            result = analyze_exam_bank(
                self.entries,
                self.analyzer,
                level=selected_level,
                focus=["全部"],
            )
            self.assertTrue(result.practice)
            self.assertTrue(
                all(point.estimated_level.startswith(selected_level)
                    for point in result.knowledge_points)
            )


if __name__ == "__main__":
    unittest.main()

