from __future__ import annotations

import re
from collections import Counter


SENTENCE_END_RE = re.compile(r"(?<=[。！？!?])\s*")
JAPANESE_CHAR_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
NON_SPACE_RE = re.compile(r"\S")
JLPT_LEVEL_RE = re.compile(r"N[1-5]", re.IGNORECASE)


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_END_RE.split(text) if part.strip()]


def japanese_character_count(text: str) -> int:
    return len(JAPANESE_CHAR_RE.findall(text))


def japanese_ratio(text: str) -> float:
    non_space = len(NON_SPACE_RE.findall(text))
    if non_space == 0:
        return 0.0
    return japanese_character_count(text) / non_space


def sentence_containing(text: str, fragment: str) -> str:
    if not fragment:
        return ""
    sentences = split_sentences(text)
    for sentence in sentences:
        if fragment in sentence:
            return sentence
    index = text.find(fragment)
    if index < 0:
        return ""
    start = max(
        text.rfind("。", 0, index),
        text.rfind("！", 0, index),
        text.rfind("？", 0, index),
        text.rfind("\n", 0, index),
    )
    start = 0 if start < 0 else start + 1
    ends = [
        pos
        for pos in (
            text.find("。", index),
            text.find("！", index),
            text.find("？", index),
            text.find("\n", index),
        )
        if pos >= 0
    ]
    end = min(ends) + 1 if ends else len(text)
    return text[start:end].strip()


def validate_article(text: str, *, min_chars: int = 40, max_chars: int = 1200) -> str | None:
    stripped = text.strip()
    if len(stripped) < min_chars:
        return f"文章太短，请至少输入 {min_chars} 个字符，建议提供 3–5 句。"
    if len(stripped) > max_chars:
        return f"文章超过 {max_chars} 个字符，请分成段落后再分析。"
    if japanese_character_count(stripped) < 20:
        return "没有检测到足够的日文内容，请确认粘贴的是日语文章。"
    if japanese_ratio(stripped) < 0.2:
        return "日文字符比例过低。可以混合中文说明，但正文应以日文为主。"
    return None


def level_sort_key(level: str) -> int:
    normalized = level.upper().replace("JLPT", "").strip()
    order = {"N5": 1, "N4": 2, "N3": 3, "N2": 4, "N1": 5}
    return order.get(normalized, 0)


def normalize_jlpt_level(level: str) -> str:
    match = JLPT_LEVEL_RE.search(str(level))
    return match.group(0).upper() if match else ""


def level_matches(point_level: str, selected_level: str) -> bool:
    normalized_point = normalize_jlpt_level(point_level)
    normalized_selected = normalize_jlpt_level(selected_level)
    if not normalized_selected:
        return True
    return normalized_point == normalized_selected


def estimate_level(levels: list[str]) -> str:
    valid = [level.upper() for level in levels if level_sort_key(level)]
    if not valid:
        return "未估计"
    counts = Counter(valid)
    return sorted(
        counts,
        key=lambda item: (counts[item], level_sort_key(item)),
        reverse=True,
    )[0] + "（估计）"

