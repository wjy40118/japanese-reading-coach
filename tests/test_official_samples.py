from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.official_samples import (
    is_official_jlpt_url,
    load_official_catalog,
    official_resources,
    search_official_samples,
)


class OfficialSampleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_official_catalog()
        self.resources = official_resources(self.catalog)

    def test_catalog_has_all_levels_and_collections(self) -> None:
        self.assertEqual(len(self.resources), 20)
        self.assertEqual(
            {resource.level for resource in self.resources},
            {"N1", "N2", "N3", "N4", "N5"},
        )
        self.assertEqual(
            {resource.collection_id for resource in self.resources},
            {"sample2009", "workbook2012", "workbook2018", "interactive"},
        )

    def test_all_links_are_official_jlpt_urls(self) -> None:
        for resource in self.resources:
            self.assertTrue(is_official_jlpt_url(resource.question_url))
            self.assertTrue(is_official_jlpt_url(resource.source_url))
            self.assertTrue(is_official_jlpt_url(resource.policy_url))
            if resource.answer_url:
                self.assertTrue(is_official_jlpt_url(resource.answer_url))

    def test_exact_level_and_collection_search(self) -> None:
        resource = search_official_samples(
            self.catalog,
            level="N2",
            collection_id="workbook2018",
        )
        self.assertIsNotNone(resource)
        assert resource is not None
        self.assertEqual(resource.level, "N2")
        self.assertEqual(resource.collection_id, "workbook2018")
        self.assertIsNone(
            search_official_samples(
                self.catalog,
                level="N6",
                collection_id="workbook2018",
            )
        )


if __name__ == "__main__":
    unittest.main()

