from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any


DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "n2_high_frequency_terms.json"
IGNORED_CHARS_RE = re.compile(r"[\s～〜~・、。,.「」『』（）()+/]")


def normalize_grammar_term(term: str) -> str:
    normalized = unicodedata.normalize("NFKC", term)
    return IGNORED_CHARS_RE.sub("", normalized)


def load_n2_frequency_data(path: Path | str = DATA_PATH) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("terms"), list):
        raise ValueError("Invalid N2 frequency data")
    return payload


def build_n2_matcher(payload: dict[str, Any]):
    terms = {normalize_grammar_term(str(term)) for term in payload["terms"]}
    aliases: dict[str, set[str]] = {}
    for term, values in payload.get("aliases", {}).items():
        aliases[normalize_grammar_term(str(term))] = {
            normalize_grammar_term(str(value)) for value in values
        }

    def is_hit(term: str) -> bool:
        normalized = normalize_grammar_term(term)
        if not normalized:
            return False
        if normalized in terms:
            return True
        for canonical, canonical_aliases in aliases.items():
            if normalized in canonical_aliases:
                return True
            if canonical in normalized:
                return True
        return False

    return is_hit

