from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .rule_analyzer import RuleBasedAnalyzer
from .schema import AnalysisResult, KnowledgePoint


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_exam_bank(path: Path | str = DATA_DIR / "exam_bank.json") -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError("exam_bank.json must contain a JSON list")
    return payload


def filter_exam_bank(
    entries: list[dict[str, Any]],
    years: list[int],
) -> list[dict[str, Any]]:
    if not years:
        return list(entries)
    wanted = {int(year) for year in years}
    return [entry for entry in entries if int(entry.get("year", 0)) in wanted]


@dataclass
class ArticleBankAnalysis:
    entry: dict[str, Any]
    analysis: AnalysisResult


@dataclass
class BankKnowledgePoint:
    kind: str
    term: str
    reading: str
    explanation: str
    estimated_level: str
    exam_frequency: int
    confidence: float
    quotes: list[str]
    example: str
    years: list[int] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)

    @classmethod
    def from_point(
        cls,
        point: KnowledgePoint,
        entry: dict[str, Any],
    ) -> "BankKnowledgePoint":
        return cls(
            kind=point.kind,
            term=point.term,
            reading=point.reading,
            explanation=point.explanation,
            estimated_level=point.estimated_level,
            exam_frequency=point.exam_frequency,
            confidence=point.confidence,
            quotes=[point.quote] if point.quote else [],
            example=point.example,
            years=[int(entry.get("year", 0))],
            titles=[str(entry.get("title", ""))],
        )

    def merge_source(self, point: KnowledgePoint, entry: dict[str, Any]) -> None:
        year = int(entry.get("year", 0))
        title = str(entry.get("title", ""))
        if year and year not in self.years:
            self.years.append(year)
        if title and title not in self.titles:
            self.titles.append(title)
        if point.exam_frequency > self.exam_frequency:
            self.exam_frequency = point.exam_frequency
        if point.confidence > self.confidence:
            self.confidence = point.confidence
        if point.quote and point.quote not in self.quotes:
            self.quotes.append(point.quote)


@dataclass
class BankPracticeQuestion:
    question: str
    options: list[str]
    answer_index: int
    explanation: str
    term: str
    years: list[int] = field(default_factory=list)


def _build_bank_practice(
    points: list[BankKnowledgePoint],
    patterns: list[dict[str, Any]],
    *,
    max_questions: int = 10,
) -> list[BankPracticeQuestion]:
    practice: list[BankPracticeQuestion] = []
    pattern_map = {
        str(pattern.get("term", "")): pattern
        for pattern in patterns
        if isinstance(pattern.get("quiz"), dict)
    }
    vocabulary_meanings = [
        point.explanation
        for point in points
        if point.kind == "vocabulary" and point.explanation
    ]

    for point in points:
        if len(practice) >= max_questions:
            break
        pattern = pattern_map.get(point.term)
        if pattern:
            quiz = pattern["quiz"]
            practice.append(
                BankPracticeQuestion(
                    question=str(quiz.get("question", "")),
                    options=[str(item) for item in quiz.get("options", [])],
                    answer_index=int(quiz.get("answer_index", 0)),
                    explanation=str(quiz.get("explanation", "")),
                    term=point.term,
                    years=point.years,
                )
            )
            continue

        if point.kind != "vocabulary":
            continue
        distractors = [
            meaning
            for meaning in vocabulary_meanings
            if meaning and meaning != point.explanation
        ][:2]
        if len(distractors) < 2:
            continue
        options = [point.explanation, *distractors]
        shift = len(practice) % len(options)
        options = options[shift:] + options[:shift]
        practice.append(
            BankPracticeQuestion(
                question=f"「{point.term}」在题库文章中最接近哪个意思？",
                options=options,
                answer_index=options.index(point.explanation),
                explanation=f"{point.term}：{point.explanation}",
                term=point.term,
                years=point.years,
            )
        )
    return practice


@dataclass
class BankAnalysis:
    selected_years: list[int]
    level: str
    articles: list[ArticleBankAnalysis]
    knowledge_points: list[BankKnowledgePoint]
    practice: list[BankPracticeQuestion]
    disclaimer: str

    @property
    def total_questions(self) -> int:
        return sum(len(item.entry.get("questions", [])) for item in self.articles)

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_years": self.selected_years,
            "level": self.level,
            "total_articles": len(self.articles),
            "total_questions": self.total_questions,
            "disclaimer": self.disclaimer,
            "articles": [
                {
                    "entry": item.entry,
                    "analysis": item.analysis.to_dict(),
                }
                for item in self.articles
            ],
            "knowledge_points": [
                asdict(point) for point in self.knowledge_points
            ],
            "practice": [asdict(question) for question in self.practice],
        }


def analyze_exam_bank(
    entries: list[dict[str, Any]],
    analyzer: RuleBasedAnalyzer,
    *,
    level: str | None = None,
    focus: list[str] | None = None,
    max_points_per_article: int = 10,
) -> BankAnalysis:
    article_results: list[ArticleBankAnalysis] = []
    point_index: dict[tuple[str, str], BankKnowledgePoint] = {}

    for entry in entries:
        passage = str(entry.get("passage", "")).strip()
        if not passage:
            continue
        result = analyzer.analyze(
            passage,
            level=level or str(entry.get("level", "N3")),
            focus=focus,
            max_points=max_points_per_article,
            include_context_vocabulary=False,
        )
        article_results.append(ArticleBankAnalysis(entry=entry, analysis=result))

        for point in result.points:
            key = (point.kind, point.term)
            if key not in point_index:
                point_index[key] = BankKnowledgePoint.from_point(point, entry)
            else:
                point_index[key].merge_source(point, entry)

    knowledge_points = sorted(
        point_index.values(),
        key=lambda point: (
            -point.exam_frequency,
            -len(point.years),
            -point.confidence,
            point.term,
        ),
    )
    practice = _build_bank_practice(knowledge_points, analyzer.patterns)
    selected_years = sorted(
        {int(entry.get("year", 0)) for entry in entries if entry.get("year")}
    )
    return BankAnalysis(
        selected_years=selected_years,
        level=level or "混合等级",
        articles=article_results,
        knowledge_points=knowledge_points,
        practice=practice,
        disclaimer="题库为按近10年题型和难度编写的原创模拟题，不包含或复刻受版权保护的历年真题。",
    )

