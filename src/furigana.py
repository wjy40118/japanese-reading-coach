from __future__ import annotations

import html
import re
from functools import lru_cache


KANJI_RE = re.compile(r"[\u3400-\u9fff]")
KATAKANA_RE = re.compile(r"[\u30a1-\u30f6]")
HIRAGANA_RE = re.compile(r"[\u3041-\u3096ー]+")
SEGMENT_RE = re.compile(r"([\u3400-\u9fff]+|[^\u3400-\u9fff]+)")
QUOTED_JAPANESE_RE = re.compile(r"(「[^」]+」)")


def furigana_available() -> bool:
    try:
        from sudachipy import dictionary  # noqa: F401
    except ImportError:
        return False
    return True


@lru_cache(maxsize=1)
def _tokenizer():
    from sudachipy import dictionary

    return dictionary.Dictionary(dict="core").tokenizer()


def katakana_to_hiragana(text: str) -> str:
    return "".join(
        chr(ord(char) - 0x60) if KATAKANA_RE.fullmatch(char) else char
        for char in text
    )


def _ruby(surface: str, reading: str) -> str:
    return (
        f"<ruby>{html.escape(surface)}"
        f"<rt>{html.escape(reading)}</rt></ruby>"
    )


def _render_token(surface: str, reading: str) -> str:
    """Apply readings to kanji runs while leaving okurigana plain."""
    if not reading or reading in {"*", surface}:
        return html.escape(surface)
    if not KANJI_RE.search(surface):
        return html.escape(surface)

    parts = SEGMENT_RE.findall(surface)
    if not all(
        KANJI_RE.search(part) or HIRAGANA_RE.fullmatch(part)
        for part in parts
    ):
        return _ruby(surface, reading)

    rendered: list[str] = []
    reading_pos = 0
    for index, part in enumerate(parts):
        if not KANJI_RE.search(part):
            anchor_pos = reading.find(part, reading_pos)
            rendered.append(html.escape(part))
            if anchor_pos >= 0:
                reading_pos = anchor_pos + len(part)
            continue

        next_kana = ""
        for later in parts[index + 1 :]:
            if not KANJI_RE.search(later):
                next_kana = later
                break
        anchor_pos = (
            reading.find(next_kana, reading_pos)
            if next_kana
            else -1
        )
        if anchor_pos >= 0:
            part_reading = reading[reading_pos:anchor_pos]
            reading_pos = anchor_pos
        else:
            part_reading = reading[reading_pos:]
            reading_pos = len(reading)
        rendered.append(
            _ruby(part, part_reading) if part_reading else html.escape(part)
        )
    return "".join(rendered)


@lru_cache(maxsize=2048)
def annotate_japanese(text: str) -> str:
    """Return escaped HTML with hiragana readings above Japanese kanji tokens.

    Sudachi reads a token or short phrase as katakana. The display converts it
    to hiragana and keeps the original token as the ruby base.
    """
    if not text:
        return ""
    if not furigana_available():
        return html.escape(text)

    try:
        tokens = _tokenizer().tokenize(text)
    except Exception:
        return html.escape(text)

    rendered: list[str] = []
    for token in tokens:
        surface = token.surface()
        if not KANJI_RE.search(surface):
            rendered.append(html.escape(surface))
            continue

        reading_form = (token.reading_form() or "").strip()
        reading = katakana_to_hiragana(reading_form)
        if not reading or reading in {"*", surface}:
            rendered.append(html.escape(surface))
            continue
        rendered.append(_render_token(surface, reading))
    return "".join(rendered)


def annotate_japanese_in_mixed_text(text: str) -> str:
    """Annotate Japanese inside quotation marks without reading Chinese UI copy."""
    rendered: list[str] = []
    for part in QUOTED_JAPANESE_RE.split(text):
        if part.startswith("「") and part.endswith("」"):
            inner = part[1:-1]
            rendered.append(f"「{annotate_japanese(inner)}」")
        else:
            rendered.append(html.escape(part))
    return "".join(rendered)

