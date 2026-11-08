from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.jmdict_cn import lookup_chinese_meaning


class JmdictCnTests(unittest.TestCase):
    def test_common_words_have_chinese_meanings(self) -> None:
        for word in ("単語", "文章", "気づく", "読む"):
            result = lookup_chinese_meaning(word)
            self.assertIsNotNone(result, word)
            assert result is not None
            self.assertTrue(result[0])

    def test_unknown_word_returns_none(self) -> None:
        self.assertIsNone(lookup_chinese_meaning("この語は辞書にない架空語XYZ"))

    def test_license_files_exist(self) -> None:
        data_dir = ROOT / "data" / "jmdict_cn"
        self.assertTrue((data_dir / "LICENSE").exists())
        self.assertTrue((data_dir / "ATTRIBUTION.md").exists())


if __name__ == "__main__":
    unittest.main()

