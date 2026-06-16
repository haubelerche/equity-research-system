"""Shared PDF page-text loader: pdfplumber text layer, Tesseract OCR fallback (cached).

Shared by the offline ingestion scripts (ingest_pdf_llm, ingest_agm) so OCR behaviour is
identical. Lives under scripts/ (not backend/) because it touches the local filesystem —
the backend run-path reaches storage only through Supabase. Scanned PDFs (no text layer)
are OCR'd at 300 dpi (vie+eng) and cached on disk so reruns skip re-OCR."""
from __future__ import annotations

from pathlib import Path

_TEXT_LAYER_MIN_CHARS = 200  # below this total → treat as scanned and OCR


def _should_ocr(text_pages: list[tuple[int, str]]) -> bool:
    """True when the extracted text layer is too sparse to be a real text PDF."""
    return sum(len(t) for _, t in text_pages) <= _TEXT_LAYER_MIN_CHARS


def _read_ocr_cache(cache_dir: Path) -> list[tuple[int, str]] | None:
    """Return cached OCR pages (page_NNN.txt) if present, else None."""
    if not cache_dir.exists():
        return None
    cached = sorted(cache_dir.glob("page_*.txt"))
    if not cached:
        return None
    pages: list[tuple[int, str]] = []
    for f in cached:
        n = int(f.stem.split("_")[1])
        pages.append((n, f.read_text(encoding="utf-8", errors="replace")))
    return pages


def _ocr_pages(pdf_path: Path, cache_dir: Path, lang: str) -> list[tuple[int, str]]:
    import pytesseract  # type: ignore
    from pdf2image import convert_from_path  # type: ignore

    from backend.documents.pdf_extractor import _find_tesseract_cmd, _tesseract_config

    cmd = _find_tesseract_cmd()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    config = _tesseract_config()
    images = convert_from_path(str(pdf_path), dpi=300)
    cache_dir.mkdir(parents=True, exist_ok=True)
    pages: list[tuple[int, str]] = []
    for n, image in enumerate(images, start=1):
        try:
            txt = pytesseract.image_to_string(image, lang=lang, config=config)
        except Exception:  # noqa: BLE001
            txt = ""
        (cache_dir / f"page_{n:03d}.txt").write_text(txt, encoding="utf-8")
        pages.append((n, txt))
    return pages


def load_pdf_pages(
    pdf_path: Path, *, cache_dir: Path, lang: str = "vie+eng"
) -> tuple[list[tuple[int, str]], str]:
    """Return (pages, kind). kind is 'text' (pdfplumber) or 'ocr' (Tesseract, cached)."""
    import pdfplumber

    with pdfplumber.open(str(pdf_path)) as pdf:
        text_pages = [((i + 1), (p.extract_text() or "")) for i, p in enumerate(pdf.pages)]
    if not _should_ocr(text_pages):
        return text_pages, "text"

    cached = _read_ocr_cache(cache_dir)
    if cached is not None:
        return cached, "ocr"
    return _ocr_pages(pdf_path, cache_dir, lang), "ocr"
