from __future__ import annotations

from .furigana import furigana_available, katakana_to_hiragana
from .schema import KnowledgePoint
from .text_utils import sentence_containing


CONTENT_POS_LABELS = {
    "名詞": "名词",
    "動詞": "动词",
    "形容詞": "形容词",
    "副詞": "副词",
}

STOPWORDS = {
    "こと",
    "もの",
    "ため",
    "よう",
    "そう",
    "ところ",
    "これ",
    "それ",
    "あれ",
    "ここ",
    "そこ",
    "人",
    "時",
    "中",
    "前",
    "後",
}


def extract_context_vocabulary(
    text: str,
    *,
    level: str,
    excluded_terms: set[str],
    limit: int,
) -> list[KnowledgePoint]:
    if not furigana_available() or limit <= 0:
        return []
    try:
        from sudachipy import dictionary

        tokenizer = dictionary.Dictionary(dict="core").tokenizer()
        tokens = tokenizer.tokenize(text)
    except Exception:
        return []

    points: list[KnowledgePoint] = []
    seen = set(excluded_terms)
    for token in tokens:
        if len(points) >= limit:
            break
        pos = token.part_of_speech()
        if not pos or pos[0] not in CONTENT_POS_LABELS:
            continue
        if pos[1] in {"代名詞", "数詞"}:
            continue
        surface = token.surface().strip()
        dictionary_form = (token.dictionary_form() or surface).strip()
        if len(surface) < 2 or surface in STOPWORDS or dictionary_form in seen:
            continue
        quote = sentence_containing(text, surface)
        if not quote:
            continue
        reading = katakana_to_hiragana(token.reading_form() or "")
        pos_label = CONTENT_POS_LABELS[pos[0]]
        explanation = (
            f"语境词汇（{pos_label}）。辞书形：{dictionary_form}。"
            "先结合原句、前后搭配和词性判断它在当前语境中的具体含义。"
        )
        points.append(
            KnowledgePoint(
                kind="vocabulary",
                term=surface,
                reading=reading,
                quote=quote,
                explanation=explanation,
                estimated_level=f"{level}（语境候选）",
                confidence=0.42,
                exam_frequency=2,
            )
        )
        seen.add(surface)
        seen.add(dictionary_form)
    return points

