from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import AnalysisResult


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_samples(path: Path | str = DATA_DIR / "samples.json") -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError("samples.json must contain a JSON list")
    return payload


def sample_to_result(sample: dict[str, Any]) -> AnalysisResult:
    result = AnalysisResult.from_dict(sample["analysis"])
    result.mode = "demo"
    return result

