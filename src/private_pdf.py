from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO


@dataclass
class PrivatePageExtraction:
    page_number: int
    page_count: int
    text: str
    method: str
    warnings: list[str] = field(default_factory=list)


def get_pdf_page_count(pdf_bytes: bytes) -> int:
    import pdfplumber

    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        return len(pdf.pages)


def ocr_available() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
    except Exception:
        return False
    return True


def _ocr_page(pdf_bytes: bytes, page_number: int) -> tuple[str, list[str]]:
    warnings: list[str] = []
    try:
        import pytesseract
        from pdf2image import convert_from_bytes

        images = convert_from_bytes(
            pdf_bytes,
            dpi=180,
            first_page=page_number,
            last_page=page_number,
            fmt="png",
        )
        if not images:
            return "", ["未能渲染 PDF 页面。"]
        languages = set(pytesseract.get_languages(config=""))
        selected = [lang for lang in ("jpn", "eng") if lang in languages]
        if "jpn" not in selected:
            return "", ["Tesseract 未安装日语语言包 tesseract-ocr-jpn。"]
        text = pytesseract.image_to_string(
            images[0],
            lang="+".join(selected),
            config="--psm 6",
        )
        return text.strip(), warnings
    except Exception as exc:
        return "", [f"OCR 不可用：{exc}"]


def extract_private_pdf_page(
    pdf_bytes: bytes,
    page_number: int,
    *,
    use_ocr: bool = True,
) -> PrivatePageExtraction:
    import pdfplumber

    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        page_count = len(pdf.pages)
        if page_number < 1 or page_number > page_count:
            raise ValueError(f"页码必须在 1–{page_count} 之间。")
        text = (pdf.pages[page_number - 1].extract_text() or "").strip()

    if len(text) >= 40:
        return PrivatePageExtraction(
            page_number=page_number,
            page_count=page_count,
            text=text,
            method="PDF text",
        )
    if not use_ocr:
        return PrivatePageExtraction(
            page_number=page_number,
            page_count=page_count,
            text=text,
            method="PDF text",
            warnings=["该页可能是扫描页，未启用 OCR。"],
        )

    ocr_text, warnings = _ocr_page(pdf_bytes, page_number)
    return PrivatePageExtraction(
        page_number=page_number,
        page_count=page_count,
        text=ocr_text or text,
        method="OCR" if ocr_text else "PDF text",
        warnings=warnings,
    )

