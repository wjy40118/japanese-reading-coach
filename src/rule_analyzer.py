from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .context_vocab import extract_context_vocabulary
from .schema import (
    AnalysisResult,
    KnowledgePoint,
    PracticeQuestion,
    coerce_exam_frequency,
)
from .text_utils import (
    estimate_level,
    level_matches,
    sentence_containing,
    split_sentences,
    validate_article,
)


DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FOCUS_KIND_MAP = {
    "语法": {"grammar"},
    "词汇": {"vocabulary"},
    "句型": {"structure"},
    "篇章": {"cohesion"},
}


class RuleBasedAnalyzer:
    """Deterministic demonstration backend.

    It never invents a definition for a word outside the local lexicon. The
    result is intentionally marked as a rule-based candidate list.
    """

    def __init__(self, data_dir: Path | str = DEFAULT_DATA_DIR):
        self.data_dir = Path(data_dir)
        self.patterns = self._load_json("grammar_patterns.json")
        self.lexicon = self._load_json("lexicon.json")

    def _load_json(self, filename: str) -> list[dict[str, Any]]:
        path = self.data_dir / filename
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, list):
            raise ValueError(f"{filename} must contain a JSON list")
        return payload

    @staticmethod
    def _matches_focus(kind: str, focus: list[str]) -> bool:
        if not focus or "全部" in focus:
            return True
        allowed: set[str] = set()
        for item in focus:
            allowed.update(FOCUS_KIND_MAP.get(item, set()))
        return kind in allowed

    @staticmethod
    def _frequency(payload: dict[str, Any]) -> int:
        return coerce_exam_frequency(
            payload.get("exam_frequency", payload.get("frequency", 3))
        )

    @staticmethod
    def _fallback_practice(
        points: list[KnowledgePoint],
        existing_terms: set[str],
    ) -> list[PracticeQuestion]:
        questions: list[PracticeQuestion] = []
        grammar_explanations = [
            point.explanation
            for point in points
            if point.kind in {"grammar", "structure", "cohesion"}
            and point.explanation
        ]
        vocabulary_explanations = [
            point.explanation
            for point in points
            if point.kind == "vocabulary" and point.explanation
        ]
        pos_options = ["名词", "动词", "形容词", "副词"]

        for point in points:
            if point.term in existing_terms:
                continue

            pos_match = re.search(
                r"语境词汇（(名词|动词|形容词|副词)）",
                point.explanation,
            )
            if pos_match:
                correct_pos = pos_match.group(1)
                questions.append(
                    PracticeQuestion(
                        question=f"「{point.term}」在文中属于哪类词？",
                        options=list(pos_options),
                        answer_index=pos_options.index(correct_pos),
                        explanation=point.explanation,
                    )
                )
                continue

            if point.kind == "vocabulary":
                correct = point.explanation
                distractors = [
                    text
                    for text in vocabulary_explanations
                    if text and text != correct
                ][:2]
                if len(distractors) < 2:
                    continue
                options = [correct, *distractors]
                shift = len(questions) % len(options)
                options = options[shift:] + options[:shift]
                questions.append(
                    PracticeQuestion(
                        question=f"「{point.term}」在文中最接近哪个意思？",
                        options=options,
                        answer_index=options.index(correct),
                        explanation=f"{point.term}：{correct}",
                    )
                )
                continue

            correct = point.explanation
            distractors = [
                text
                for text in grammar_explanations
                if text and text != correct
            ][:2]
            if len(distractors) < 2:
                continue
            options = [correct, *distractors]
            shift = len(questions) % len(options)
            options = options[shift:] + options[:shift]
            questions.append(
                PracticeQuestion(
                    question=(
                        f"文中「{point.term}」的作用或含义最接近哪一项？"
                    ),
                    options=options,
                    answer_index=options.index(correct),
                    explanation=f"{point.term}：{correct}",
                )
            )
        return questions

    def analyze(
        self,
        text: str,
        *,
        level: str = "N3",
        focus: list[str] | None = None,
        max_points: int | None = None,
        include_context_vocabulary: bool = True,
    ) -> AnalysisResult:
        focus = focus or ["全部"]
        error = validate_article(text)
        if error:
            raise ValueError(error)

        points: list[KnowledgePoint] = []
        practice: list[PracticeQuestion] = []
        matched_terms: set[str] = set()
        quiz_terms: set[str] = set()

        ordered_patterns = sorted(
            self.patterns,
            key=lambda item: len(str(item.get("term", ""))),
            reverse=True,
        )
        for pattern in ordered_patterns:
            if max_points is not None and len(points) >= max_points:
                break
            term = str(pattern.get("term", "")).strip()
            kind = str(pattern.get("kind", "grammar"))
            point_level = str(pattern.get("estimated_level", "未估计"))
            if not term or term not in text or term in matched_terms:
                continue
            if not level_matches(point_level, level):
                continue
            if not self._matches_focus(kind, focus):
                continue
            if any(term != other and term in other for other in matched_terms):
                continue
            quote = sentence_containing(text, term)
            points.append(
                KnowledgePoint(
                    kind=kind,
                    term=term,
                    reading="",
                    quote=quote,
                    explanation=str(pattern.get("explanation", "")),
                    estimated_level=point_level,
                    structure=str(pattern.get("structure", "")),
                    example=str(pattern.get("example", "")),
                    confidence=float(pattern.get("confidence", 0.8)),
                    exam_frequency=self._frequency(pattern),
                )
            )
            matched_terms.add(term)
            quiz = pattern.get("quiz")
            if isinstance(quiz, dict):
                practice.append(PracticeQuestion.from_dict(quiz))
                quiz_terms.add(term)

        ordered_lexicon = sorted(
            self.lexicon,
            key=lambda item: len(str(item.get("term", ""))),
            reverse=True,
        )
        for entry in ordered_lexicon:
            if max_points is not None and len(points) >= max_points:
                break
            term = str(entry.get("term", "")).strip()
            point_level = str(entry.get("estimated_level", "未估计"))
            if not term or term not in text:
                continue
            if not level_matches(point_level, level):
                continue
            if not self._matches_focus("vocabulary", focus):
                continue
            if any(term in other for other in matched_terms):
                continue
            points.append(
                KnowledgePoint(
                    kind="vocabulary",
                    term=term,
                    reading=str(entry.get("reading", "")),
                    quote=sentence_containing(text, term),
                    explanation=str(entry.get("meaning", "")),
                    estimated_level=point_level,
                    example=str(entry.get("example", "")),
                    confidence=float(entry.get("confidence", 0.7)),
                    exam_frequency=self._frequency(entry),
                )
            )
            matched_terms.add(term)

        if (
            include_context_vocabulary
            and self._matches_focus("vocabulary", focus)
        ):
            limit = (
                10_000
                if max_points is None
                else max_points - len(points)
            )
            points.extend(
                extract_context_vocabulary(
                    text,
                    level=level,
                    excluded_terms=matched_terms,
                    limit=max(0, limit),
                )
            )

        points.sort(
            key=lambda point: (
                -coerce_exam_frequency(point.exam_frequency),
                -point.confidence,
                point.term,
            )
        )

        practice.extend(
            self._fallback_practice(
                points,
                quiz_terms,
            )
        )

        sentences = split_sentences(text)
        terms = "、".join(point.term for point in points[:4])
        summary = (
            f"规则模式共识别 {len(points)} 个候选知识点，"
            f"文章约 {len(sentences)} 句。"
        )
        if terms:
            summary += f" 当前重点包括：{terms}。"

        warnings: list[str] = []
        if not points:
            warnings.append(
                f"没有匹配到 {level} 等级的本地语法或词汇知识点。"
                "请确认已按所选等级重新分析，或切换其他等级。"
            )
        if not practice:
            warnings.append("规则模式没有为这些候选点生成练习，可使用演示案例查看完整练习。")
        warnings.append(
            "这是确定性的候选分析，不等同于完整语义理解；模型模式下仍需保留原文引用进行核验。"
        )

        return AnalysisResult(
            summary=summary,
            estimated_level=estimate_level(
                [point.estimated_level for point in points]
            ),
            points=points,
            practice=practice,
            warnings=warnings,
            mode="rule",
        )

