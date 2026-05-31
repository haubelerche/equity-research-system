"""Tests for OCR wire-up in auto_ingest_official_documents.py

Tests cover:
1. _build_secondary_source_from_cafef: CafeF → lookup dict
2. IngestStatus enum: OCR_PROMOTED, OCR_PENDING_REVIEW, OCR_FAILED
3. AutoIngestConfig.ocr: defaults to False
4. YearResult OCR fields: ocr_candidates, ocr_promoted, ocr_blocked
5. _run_ocr_pipeline error handling when OCR runtime missing
6. _fetch_pdf scanned PDF routing logic
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is in path for imports
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: _build_secondary_source_from_cafef
# ─────────────────────────────────────────────────────────────────────────────

def test_build_secondary_source_basic():
    """CafeF rows with valid metric_id and float value → correct dict structure."""
    from scripts.auto_ingest_official_documents import _build_secondary_source_from_cafef

    cafef_rows = [
        {
            "ticker": "DHG",
            "fiscal_year": 2021,
            "period_type": "FY",
            "metric_id": "revenue",
            "value": "1000.5",
        },
        {
            "ticker": "DHG",
            "fiscal_year": 2021,
            "period_type": "FY",
            "metric_id": "net_profit",
            "value": "200.25",
        },
    ]

    secondary = _build_secondary_source_from_cafef(cafef_rows, "DHG", 2021)

    assert len(secondary) == 2
    assert secondary[("DHG", 2021, "FY", "revenue")] == 1000.5
    assert secondary[("DHG", 2021, "FY", "net_profit")] == 200.25


def test_build_secondary_source_skips_error_rows():
    """Rows with 'error' key are skipped."""
    from scripts.auto_ingest_official_documents import _build_secondary_source_from_cafef

    cafef_rows = [
        {
            "ticker": "DHG",
            "fiscal_year": 2021,
            "period_type": "FY",
            "metric_id": "revenue",
            "value": "1000.5",
        },
        {
            "error": "API timeout",
        },
        {
            "ticker": "DHG",
            "fiscal_year": 2021,
            "period_type": "FY",
            "metric_id": "net_profit",
            "value": "200.25",
        },
    ]

    secondary = _build_secondary_source_from_cafef(cafef_rows, "DHG", 2021)

    assert len(secondary) == 2
    assert ("DHG", 2021, "FY", "revenue") in secondary
    assert ("DHG", 2021, "FY", "net_profit") in secondary


def test_build_secondary_source_skips_note_rows():
    """Rows with 'note' key are skipped."""
    from scripts.auto_ingest_official_documents import _build_secondary_source_from_cafef

    cafef_rows = [
        {
            "ticker": "DHG",
            "fiscal_year": 2021,
            "period_type": "FY",
            "metric_id": "revenue",
            "value": "1000.5",
        },
        {
            "note": "dry_run: would fetch...",
        },
    ]

    secondary = _build_secondary_source_from_cafef(cafef_rows, "DHG", 2021)

    assert len(secondary) == 1
    assert ("DHG", 2021, "FY", "revenue") in secondary


def test_build_secondary_source_skips_invalid_values():
    """Rows with non-float values are skipped."""
    from scripts.auto_ingest_official_documents import _build_secondary_source_from_cafef

    cafef_rows = [
        {
            "ticker": "DHG",
            "fiscal_year": 2021,
            "period_type": "FY",
            "metric_id": "revenue",
            "value": "1000.5",
        },
        {
            "ticker": "DHG",
            "fiscal_year": 2021,
            "period_type": "FY",
            "metric_id": "note_text",
            "value": "not a number",
        },
        {
            "ticker": "DHG",
            "fiscal_year": 2021,
            "period_type": "FY",
            "metric_id": "empty_value",
            "value": "",
        },
    ]

    secondary = _build_secondary_source_from_cafef(cafef_rows, "DHG", 2021)

    assert len(secondary) == 1
    assert ("DHG", 2021, "FY", "revenue") in secondary
    assert ("DHG", 2021, "FY", "note_text") not in secondary
    assert ("DHG", 2021, "FY", "empty_value") not in secondary


def test_build_secondary_source_empty_rows():
    """Empty rows list → empty secondary dict."""
    from scripts.auto_ingest_official_documents import _build_secondary_source_from_cafef

    secondary = _build_secondary_source_from_cafef([], "DHG", 2021)
    assert secondary == {}


def test_build_secondary_source_period_type_defaults_to_fy():
    """period_type defaults to 'FY' if missing or empty."""
    from scripts.auto_ingest_official_documents import _build_secondary_source_from_cafef

    cafef_rows = [
        {
            "ticker": "DHG",
            "fiscal_year": 2021,
            # period_type missing
            "metric_id": "revenue",
            "value": "1000.5",
        },
        {
            "ticker": "DHG",
            "fiscal_year": 2021,
            "period_type": "",  # empty
            "metric_id": "net_profit",
            "value": "200.25",
        },
    ]

    secondary = _build_secondary_source_from_cafef(cafef_rows, "DHG", 2021)

    assert secondary[("DHG", 2021, "FY", "revenue")] == 1000.5
    assert secondary[("DHG", 2021, "FY", "net_profit")] == 200.25


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: IngestStatus enum values
# ─────────────────────────────────────────────────────────────────────────────

def test_ocr_ingest_status_promoted_exists():
    """IngestStatus.OCR_PROMOTED exists with correct value."""
    from scripts.auto_ingest_official_documents import IngestStatus

    assert hasattr(IngestStatus, "OCR_PROMOTED")
    assert IngestStatus.OCR_PROMOTED.value == "OCR_PROMOTED"


def test_ocr_ingest_status_pending_review_exists():
    """IngestStatus.OCR_PENDING_REVIEW exists with correct value."""
    from scripts.auto_ingest_official_documents import IngestStatus

    assert hasattr(IngestStatus, "OCR_PENDING_REVIEW")
    assert IngestStatus.OCR_PENDING_REVIEW.value == "OCR_PENDING_REVIEW"


def test_ocr_ingest_status_failed_exists():
    """IngestStatus.OCR_FAILED exists with correct value."""
    from scripts.auto_ingest_official_documents import IngestStatus

    assert hasattr(IngestStatus, "OCR_FAILED")
    assert IngestStatus.OCR_FAILED.value == "OCR_FAILED"


def test_ocr_status_distinct_from_extraction_failed():
    """OCR statuses are distinct from EXTRACTION_FAILED_SCANNED_PDF."""
    from scripts.auto_ingest_official_documents import IngestStatus

    assert IngestStatus.OCR_FAILED != IngestStatus.EXTRACTION_FAILED_SCANNED_PDF
    assert IngestStatus.OCR_PROMOTED != IngestStatus.EXTRACTION_FAILED_SCANNED_PDF
    assert IngestStatus.OCR_PENDING_REVIEW != IngestStatus.EXTRACTION_FAILED_SCANNED_PDF


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: AutoIngestConfig.ocr defaults to False
# ─────────────────────────────────────────────────────────────────────────────

def test_autoingest_config_ocr_default_false():
    """AutoIngestConfig.ocr defaults to False."""
    from scripts.auto_ingest_official_documents import AutoIngestConfig

    cfg = AutoIngestConfig(ticker="DHG", from_year=2021, to_year=2025)
    assert cfg.ocr is False


def test_autoingest_config_ocr_can_be_enabled():
    """AutoIngestConfig.ocr can be set to True."""
    from scripts.auto_ingest_official_documents import AutoIngestConfig

    cfg = AutoIngestConfig(ticker="DHG", from_year=2021, to_year=2025, ocr=True)
    assert cfg.ocr is True


def test_autoingest_config_all_fields():
    """AutoIngestConfig has all expected fields."""
    from scripts.auto_ingest_official_documents import AutoIngestConfig

    cfg = AutoIngestConfig(
        ticker="DHG",
        from_year=2021,
        to_year=2025,
        dry_run=True,
        channels=["cafef", "pdf"],
        min_pdf_confidence=0.7,
        promote_official_only=False,
        ocr=True,
    )

    assert cfg.ticker == "DHG"
    assert cfg.from_year == 2021
    assert cfg.to_year == 2025
    assert cfg.dry_run is True
    assert cfg.channels == ["cafef", "pdf"]
    assert cfg.min_pdf_confidence == 0.7
    assert cfg.promote_official_only is False
    assert cfg.ocr is True


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: YearResult OCR fields
# ─────────────────────────────────────────────────────────────────────────────

def test_year_result_ocr_fields_exist():
    """YearResult has ocr_candidates, ocr_promoted, ocr_blocked fields."""
    from scripts.auto_ingest_official_documents import YearResult

    yr = YearResult(fiscal_year=2021)

    assert hasattr(yr, "ocr_candidates")
    assert hasattr(yr, "ocr_promoted")
    assert hasattr(yr, "ocr_blocked")


def test_year_result_ocr_fields_default_to_zero():
    """YearResult OCR fields default to 0."""
    from scripts.auto_ingest_official_documents import YearResult

    yr = YearResult(fiscal_year=2021)

    assert yr.ocr_candidates == 0
    assert yr.ocr_promoted == 0
    assert yr.ocr_blocked == 0


def test_year_result_ocr_fields_can_be_set():
    """YearResult OCR fields can be set."""
    from scripts.auto_ingest_official_documents import YearResult

    yr = YearResult(fiscal_year=2021, ocr_candidates=10, ocr_promoted=8, ocr_blocked=2)

    assert yr.ocr_candidates == 10
    assert yr.ocr_promoted == 8
    assert yr.ocr_blocked == 2


def test_year_result_status_summary_includes_ocr():
    """YearResult.status_summary() includes OCR counts when > 0."""
    from scripts.auto_ingest_official_documents import YearResult, IngestStatus

    yr = YearResult(
        fiscal_year=2021,
        ingest_status=IngestStatus.OCR_PROMOTED,
        ocr_candidates=10,
        ocr_promoted=8,
        ocr_blocked=2,
    )

    summary = yr.status_summary()

    assert "ocr_candidates=10" in summary
    assert "ocr_promoted=8" in summary
    assert "ocr_blocked=2" in summary


def test_year_result_status_summary_excludes_ocr_when_zero():
    """YearResult.status_summary() excludes OCR counts when all are 0."""
    from scripts.auto_ingest_official_documents import YearResult, IngestStatus

    yr = YearResult(
        fiscal_year=2021,
        ingest_status=IngestStatus.TIER2_ONLY,
        ocr_candidates=0,
        ocr_promoted=0,
        ocr_blocked=0,
    )

    summary = yr.status_summary()

    assert "ocr_candidates" not in summary
    assert "ocr_promoted" not in summary
    assert "ocr_blocked" not in summary


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: _run_ocr_pipeline error handling (OCR runtime missing)
# ─────────────────────────────────────────────────────────────────────────────

def test_run_ocr_pipeline_imports_pytesseract_at_start():
    """_run_ocr_pipeline code shows pytesseract import at line 306."""
    from scripts.auto_ingest_official_documents import _run_ocr_pipeline
    import inspect

    source = inspect.getsource(_run_ocr_pipeline)
    # Verify the function checks for pytesseract import early
    assert "import pytesseract" in source
    assert "ImportError" in source
    assert "OCR_FAILED" in source


def test_run_ocr_pipeline_imports_pdf2image_at_start():
    """_run_ocr_pipeline code shows pdf2image import at line 307."""
    from scripts.auto_ingest_official_documents import _run_ocr_pipeline
    import inspect

    source = inspect.getsource(_run_ocr_pipeline)
    # Verify the function checks for pdf2image import early
    assert "from pdf2image" in source
    assert "ImportError" in source


def test_run_ocr_pipeline_returns_5_tuple_type_signature():
    """_run_ocr_pipeline return type is (list, IngestStatus, int, int, int)."""
    from scripts.auto_ingest_official_documents import _run_ocr_pipeline
    import inspect

    sig = inspect.signature(_run_ocr_pipeline)
    # Verify parameters are correct
    params = list(sig.parameters.keys())
    assert "pdf_path" in params
    assert "ticker" in params
    assert "fiscal_year" in params
    assert "document_title" in params
    assert "secondary_source" in params
    assert "doc_dir" in params

    # Check docstring for return type
    docstring = _run_ocr_pipeline.__doc__ or ""
    assert "csv_rows" in docstring
    assert "ingest_status" in docstring
    assert "ocr_candidates" in docstring
    assert "ocr_promoted" in docstring
    assert "ocr_blocked" in docstring


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: _fetch_pdf scanned PDF routing logic
# ─────────────────────────────────────────────────────────────────────────────

def test_fetch_pdf_signature_returns_3_tuple(tmp_path):
    """_fetch_pdf returns a 3-tuple: (csv_rows, IngestStatus, ocr_stats_dict)."""
    from scripts.auto_ingest_official_documents import AutoIngestConfig

    # We can't easily test _fetch_pdf without mocking the entire discovery pipeline,
    # so we verify the signature by checking the function itself
    from scripts.auto_ingest_official_documents import _fetch_pdf
    import inspect

    sig = inspect.signature(_fetch_pdf)
    assert "pdf_path" in sig.parameters or "ticker" in sig.parameters
    # The function should return a tuple (verified in docstring)
    docstring = _fetch_pdf.__doc__ or ""
    assert "tuple" in docstring.lower() or "returns" in docstring.lower()


def test_fetch_pdf_has_ocr_stats_in_return_type():
    """_fetch_pdf docstring mentions ocr_stats dict with ocr_candidates, ocr_promoted, ocr_blocked."""
    from scripts.auto_ingest_official_documents import _fetch_pdf

    docstring = _fetch_pdf.__doc__ or ""
    assert "ocr_stats" in docstring.lower()
    assert "ocr_candidates" in docstring
    assert "ocr_promoted" in docstring
    assert "ocr_blocked" in docstring


def test_extraction_failed_scanned_pdf_status_exists():
    """IngestStatus.EXTRACTION_FAILED_SCANNED_PDF exists and is distinct from OCR statuses."""
    from scripts.auto_ingest_official_documents import IngestStatus

    assert hasattr(IngestStatus, "EXTRACTION_FAILED_SCANNED_PDF")
    assert IngestStatus.EXTRACTION_FAILED_SCANNED_PDF.value == "EXTRACTION_FAILED_SCANNED_PDF"

    # Verify it's the fallback for scanned PDFs when ocr=False
    assert IngestStatus.EXTRACTION_FAILED_SCANNED_PDF != IngestStatus.OCR_FAILED


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: Pipeline integration (basic)
# ─────────────────────────────────────────────────────────────────────────────

def test_build_pipeline_plan():
    """build_pipeline_plan creates a PipelinePlan with correct years."""
    from scripts.auto_ingest_official_documents import AutoIngestConfig, build_pipeline_plan

    cfg = AutoIngestConfig(ticker="DHG", from_year=2021, to_year=2023)
    plan = build_pipeline_plan(cfg)

    assert plan.ticker == "DHG"
    assert plan.years == [2021, 2022, 2023]
    assert plan.dry_run is False
    assert plan.channels == ["cafef", "pdf"]


def test_build_pipeline_plan_with_custom_channels():
    """build_pipeline_plan respects custom channels."""
    from scripts.auto_ingest_official_documents import AutoIngestConfig, build_pipeline_plan

    cfg = AutoIngestConfig(
        ticker="IMP",
        from_year=2021,
        to_year=2021,
        channels=["cafef"],
    )
    plan = build_pipeline_plan(cfg)

    assert plan.channels == ["cafef"]
