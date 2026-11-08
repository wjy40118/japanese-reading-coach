from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def coerce_exam_frequency(value: Any, default: int = 3) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, 5))


@dataclass
class KnowledgePoint:
    kind: str
    term: str
    reading: str
    quote: str
    explanation: str
    estimated_level: str = "未估计"
    structure: str = ""
    example: str = ""
    confidence: float = 0.0
    exam_frequency: int = 3

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "KnowledgePoint":
        frequency = coerce_exam_frequency(
            payload.get("exam_frequency", payload.get("frequency", 3))
        )
        return cls(
            kind=str(payload.get("kind", "other")),
            term=str(payload.get("term", "")),
            reading=str(payload.get("reading", "")),
            quote=str(payload.get("quote", "")),
            explanation=str(payload.get("explanation", "")),
            estimated_level=str(payload.get("estimated_level", "未估计")),
            structure=str(payload.get("structure", "")),
            example=str(payload.get("example", "")),
            confidence=float(payload.get("confidence", 0.0)),
            exam_frequency=frequency,
        )


@dataclass
class PracticeQuestion:
    question: str
    options: list[str]
    answer_index: int
    explanation: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PracticeQuestion":
        options = [str(item) for item in payload.get("options", [])]
        answer_index = int(payload.get("answer_index", 0))
        if options:
            answer_index = max(0, min(answer_index, len(options) - 1))
        return cls(
            question=str(payload.get("question", "")),
            options=options,
            answer_index=answer_index,
            explanation=str(payload.get("explanation", "")),
        )


@dataclass
class AnalysisResult:
    summary: str
    estimated_level: str
    points: list[KnowledgePoint] = field(default_factory=list)
    practice: list[PracticeQuestion] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    mode: str = "rule"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AnalysisResult":
        return cls(
            summary=str(payload.get("summary", "")),
            estimated_level=str(payload.get("estimated_level", "未估计")),
            points=[
                KnowledgePoint.from_dict(item)
                for item in payload.get("points", [])
            ],
            practice=[
                PracticeQuestion.from_dict(item)
                for item in payload.get("practice", [])
            ],
            warnings=[str(item) for item in payload.get("warnings", [])],
            mode=str(payload.get("mode", "rule")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

