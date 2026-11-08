from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "official_samples.json"


@dataclass(frozen=True)
class OfficialSampleResource:
    id: str
    level: str
    collection_id: str
    collection_label: str
    description: str
    published_year: int | None
    question_url: str
    answer_url: str | None
    source_url: str
    policy_url: str


def load_official_catalog(path: Path | str = DATA_PATH) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("collections"), list):
        raise ValueError("official_samples.json has an invalid structure")
    return payload


def official_resources(catalog: dict[str, Any]) -> list[OfficialSampleResource]:
    resources: list[OfficialSampleResource] = []
    source_url = str(catalog["source_url"])
    policy_url = str(catalog["policy_url"])
    for collection in catalog["collections"]:
        for level, item in collection["levels"].items():
            resources.append(
                OfficialSampleResource(
                    id=f"{level}-{collection['id']}",
                    level=level,
                    collection_id=str(collection["id"]),
                    collection_label=str(collection["label"]),
                    description=str(collection["description"]),
                    published_year=collection.get("published_year"),
                    question_url=str(item["question_url"]),
                    answer_url=(
                        str(item["answer_url"])
                        if item.get("answer_url")
                        else None
                    ),
                    source_url=source_url,
                    policy_url=policy_url,
                )
            )
    return resources


def search_official_samples(
    catalog: dict[str, Any],
    *,
    level: str,
    collection_id: str,
) -> OfficialSampleResource | None:
    for resource in official_resources(catalog):
        if (
            resource.level.upper() == level.upper()
            and resource.collection_id == collection_id
        ):
            return resource
    return None


def is_official_jlpt_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname == "www.jlpt.jp"

