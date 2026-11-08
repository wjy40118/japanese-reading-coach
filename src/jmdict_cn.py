from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "jmdict_cn"


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).strip()


@lru_cache(maxsize=1)
def _load_index() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for level in range(1, 6):
        path = DATA_DIR / f"jmdict-cn-N{level}.json"
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            entries = json.load(handle)
        for entry in entries:
            forms = [
                item.get("text", "")
                for field in ("kanji", "kana")
                for item in entry.get(field, [])
            ]
            for form in forms:
                normalized = _normalize(form)
                if normalized and normalized not in index:
                    index[normalized] = entry
    return index


def lookup_chinese_meaning(term: str) -> tuple[str, str] | None:
    entry = _load_index().get(_normalize(term))
    if not entry:
        return None
    glosses: list[str] = []
    contexts: list[str] = []
    for sense in entry.get("senses_zh", [])[:2]:
        for gloss in sense.get("glosses", []):
            gloss = str(gloss).strip()
            if gloss and gloss not in glosses:
                glosses.append(gloss)
        context = str(sense.get("context", "")).strip()
        if context and context not in contexts:
            contexts.append(context)
    if not glosses:
        return None
    meaning = "；".join(glosses[:4])
    if contexts:
        meaning += f"（{contexts[0]}）"
    return meaning, str(entry.get("id", ""))

