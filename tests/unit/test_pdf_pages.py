"""Shared PDF page loader — text-layer decision + OCR cache read.

The pdfplumber/Tesseract I/O is verified live; here we cover the pure seams:
the scanned-vs-text decision and reading a populated OCR cache directory.
"""
from __future__ import annotations

from scripts import pdf_pages as pp


def test_should_ocr_when_text_layer_sparse():
    assert pp._should_ocr([(1, ""), (2, "  ")]) is True


def test_should_ocr_false_when_text_layer_rich():
    assert pp._should_ocr([(1, "x" * 300)]) is False


def test_read_ocr_cache_reads_numbered_pages(tmp_path):
    (tmp_path / "page_001.txt").write_text("trang mot", encoding="utf-8")
    (tmp_path / "page_002.txt").write_text("trang hai", encoding="utf-8")
    pages = pp._read_ocr_cache(tmp_path)
    assert pages == [(1, "trang mot"), (2, "trang hai")]


def test_read_ocr_cache_returns_none_when_empty(tmp_path):
    assert pp._read_ocr_cache(tmp_path) is None
