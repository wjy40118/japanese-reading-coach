from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.rule_analyzer import RuleBasedAnalyzer
from src.samples import load_samples, sample_to_result
from src.furigana import (
    annotate_japanese,
    annotate_japanese_in_mixed_text,
    furigana_available,
)
from src.text_utils import (
    japanese_character_count,
    japanese_ratio,
    sentence_containing,
    split_sentences,
    validate_article,
)


class TextUtilsTests(unittest.TestCase):
    def test_split_sentences_keeps_punctuation(self) -> None:
        text = "日本語を勉強する。少しずつ読む！わかる？"
        self.assertEqual(
            split_sentences(text),
            ["日本語を勉強する。", "少しずつ読む！", "わかる？"],
        )

    def test_japanese_ratio(self) -> None:
        self.assertGreater(japanese_ratio("日本語を読む"), 0.5)
        self.assertEqual(japanese_ratio("hello world"), 0.0)

    def test_sentence_containing(self) -> None:
        text = "雨が降った。しかし、試合は行われた。"
        self.assertEqual(
            sentence_containing(text, "行われた"),
            "しかし、試合は行われた。",
        )

    def test_validation_rejects_short_and_non_japanese(self) -> None:
        self.assertIsNotNone(validate_article("短い。"))
        self.assertIsNotNone(validate_article("This is an English text. " * 5))
        self.assertIsNone(validate_article("日本語を勉強しています。" * 8))


class AnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analyzer = RuleBasedAnalyzer()
        self.samples = load_samples()

    def test_samples_have_complete_demo_results(self) -> None:
        for sample in self.samples:
            result = sample_to_result(sample)
            self.assertGreaterEqual(len(result.points), 4)
            self.assertGreaterEqual(len(result.practice), 3)
            self.assertTrue(result.summary)
            self.assertTrue(
                all(1 <= point.exam_frequency <= 5 for point in result.points)
            )

    def test_rule_analyzer_finds_known_grammar(self) -> None:
        result = self.analyzer.analyze(
            self.samples[0]["article"],
            level="N3",
            focus=["语法", "词汇"],
        )
        terms = {point.term for point in result.points}
        self.assertIn("だけで精いっぱい", terms)
        self.assertGreaterEqual(len(result.points), 2)
        self.assertTrue(all(point.quote for point in result.points))
        self.assertTrue(
            all(1 <= point.exam_frequency <= 5 for point in result.points)
        )
        vocabulary = {
            point.term: point.reading
            for point in result.points
            if point.kind == "vocabulary"
        }
        if "精いっぱい" in vocabulary:
            self.assertEqual(vocabulary["精いっぱい"], "せいいっぱい")

    def test_rule_analyzer_filters_selected_level(self) -> None:
        result = self.analyzer.analyze(
            self.samples[0]["article"],
            level="N4",
            focus=["全部"],
        )
        self.assertTrue(
            all(point.estimated_level.upper().startswith("N4") for point in result.points)
        )

    def test_sample_vocabulary_has_hiragana_reading(self) -> None:
        for sample in self.samples:
            result = sample_to_result(sample)
            for point in result.points:
                if point.kind == "vocabulary":
                    self.assertTrue(
                        point.reading,
                        f"Vocabulary point lacks reading: {point.term}",
                    )

    def test_rule_analyzer_does_not_invent_outside_lexicon(self) -> None:
        text = "青い空が広がっている。鳥が静かに飛んでいる。" * 4
        result = self.analyzer.analyze(text)
        self.assertEqual(result.points, [])
        self.assertTrue(any("没有匹配" in warning for warning in result.warnings))

    def test_character_count(self) -> None:
        self.assertEqual(japanese_character_count("日本語ABC123"), 3)

    @unittest.skipUnless(furigana_available(), "SudachiPy dictionary is unavailable")
    def test_furigana_renders_hiragana_above_kanji(self) -> None:
        markup = annotate_japanese("日本語を読む")
        self.assertIn("<ruby>日本語<rt>にほんご</rt></ruby>", markup)
        self.assertIn("<ruby>読<rt>よ</rt></ruby>む", markup)
        self.assertIn(
            "<ruby>精<rt>せい</rt></ruby>いっぱい",
            annotate_japanese("精いっぱい"),
        )
        mixed = annotate_japanese_in_mixed_text("请解释「読む」的意思。")
        self.assertIn("<ruby>読<rt>よ</rt></ruby>む", mixed)
        self.assertIn("请解释", mixed)


if __name__ == "__main__":
    unittest.main()

