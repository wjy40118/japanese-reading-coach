from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.n2_frequency import build_n2_matcher, load_n2_frequency_data
from src.schema import coerce_exam_frequency


class N2FrequencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.matcher = build_n2_matcher(load_n2_frequency_data())

    def test_known_grammar_is_highlighted(self) -> None:
        self.assertTrue(self.matcher("にもかかわらず"))
        self.assertTrue(self.matcher("ざるを得ない"))
        self.assertTrue(self.matcher("ようにする"))

    def test_alias_is_highlighted(self) -> None:
        self.assertTrue(self.matcher("に伴って"))
        self.assertTrue(self.matcher("ようになってから"))

    def test_unlisted_grammar_is_not_highlighted(self) -> None:
        self.assertFalse(self.matcher("だけで精いっぱい"))
        self.assertFalse(self.matcher("を皮切りに"))

    def test_none_exam_frequency_is_safe(self) -> None:
        self.assertEqual(coerce_exam_frequency(None), 3)
        self.assertEqual(coerce_exam_frequency("5"), 5)
        self.assertEqual(coerce_exam_frequency(99), 5)


if __name__ == "__main__":
    unittest.main()

