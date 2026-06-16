"""Tests for OCR two-pass text extraction in pdf_extractor.

Root cause of "OCR ran but 0 facts saved": extract_from_pdf_ocr's parser only
matched same-line `label␣␣value`, but scanned BCTC OCR puts the label on one
line and the value on the next. It also skipped any page where the statement
type was not re-declared on that page. These tests pin the fix:
  - _parse_ocr_text_to_rows pairs a label line with the following value line
  - it skips standalone Mã-số codes (3-digit template ids) as value candidates
  - extract_rows_from_ocr_pages carries the statement type forward across pages
"""
from __future__ import annotations

from backend.documents.pdf_extractor import (
    _parse_ocr_text_to_rows,
    _parse_ocr_vnd_bn,
    _tesseract_config,
    extract_rows_from_ocr_pages,
)


# ── _parse_ocr_vnd_bn: BCTC dot-thousands full-đồng → tỷ VND ─────────────────

def test_ocr_value_dot_thousands_dong_to_billions():
    # "4.343.720.860.197" đồng = 4,343.72 tỷ VND
    assert abs(_parse_ocr_vnd_bn("4.343.720.860.197") - 4343.720860197) < 1e-5


def test_ocr_value_revenue_scale():
    # "5.622.839.978.328" đồng = 5,622.84 tỷ VND (not 5,622,839,978)
    assert abs(_parse_ocr_vnd_bn("5.622.839.978.328") - 5622.839978328) < 1e-6


def test_ocr_value_negative_parentheses():
    assert abs(_parse_ocr_vnd_bn("(2.060.673.782.276)") - (-2060.673782276)) < 1e-5


def test_ocr_value_null_markers_return_none():
    assert _parse_ocr_vnd_bn("") is None
    assert _parse_ocr_vnd_bn("—") is None


# ── _parse_ocr_text_to_rows: consecutive-line (scanned layout) ──────────────

def test_tesseract_config_uses_unquoted_tessdata_path():
    # pytesseract tokenizes config itself; embedded quotes become path text on Windows.
    assert '"' not in _tesseract_config()


def test_parse_pairs_label_with_following_value_line():
    text = "Loi nhuan gop\n4,343,720\n"
    rows = _parse_ocr_text_to_rows(text)
    assert ["Loi nhuan gop", "4,343,720"] in rows


def test_parse_skips_standalone_ma_so_code_and_pairs_real_value():
    # "Doanh thu thuan" then a Mã-số code "100" then the real value on next line.
    text = "Doanh thu thuan ve ban hang\n100\n5,622,840\n"
    rows = _parse_ocr_text_to_rows(text)
    labels_values = {(r[0], r[1]) for r in rows}
    assert ("Doanh thu thuan ve ban hang", "5,622,840") in labels_values
    # The Mã-số code must not be paired as a value.
    assert all(v != "100" for _, v in labels_values)


def test_parse_same_line_label_value_still_works():
    text = "Tong tai san                 9,123,456\n"
    rows = _parse_ocr_text_to_rows(text)
    assert ["Tong tai san", "9,123,456"] in rows


# ── extract_rows_from_ocr_pages: statement-type carry-forward ───────────────

def test_extract_carries_statement_type_to_later_pages():
    # Page 1 declares the income statement header (no values yet);
    # page 2 has a mappable label+value on consecutive lines but no header.
    pages = [
        (1, "BAO CAO KET QUA HOAT DONG KINH DOANH\nCho nam tai chinh 2025\n"),
        (2, "Loi nhuan gop\n4.343.720.860.197\n"),
    ]
    rows = extract_rows_from_ocr_pages(
        pages, ticker="DHG", fiscal_year=2025, document_title="DHG FY2025"
    )
    assert rows, "expected at least one extracted row from a carry-forward page"
    by_metric = {r.metric_id: r for r in rows}
    assert "gross_profit.total" in by_metric
    assert all(r.statement_type == "income_statement" for r in rows)
    # Value must be scaled đồng→tỷ (4,343.72), not left as raw 4.3e12.
    assert abs(by_metric["gross_profit.total"].value - 4343.720860197) < 1e-3


def test_extract_skips_pages_before_any_statement_header():
    # Cover page text with no statement header and no values → no rows, no crash.
    pages = [(1, "Deloitte.\nCONG TY CO PHAN DUOC HAU GIANG\nBAO CAO TAI CHINH\n")]
    rows = extract_rows_from_ocr_pages(
        pages, ticker="DHG", fiscal_year=2025, document_title="DHG FY2025"
    )
    assert rows == []
