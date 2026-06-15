"""Tests for OCR cohort coverage aggregation (honest per-ticker reporting)."""
from __future__ import annotations

from backend.dataops.ocr_coverage import (
    TickerCoverage,
    aggregate_ticker,
    cohort_summary,
    coverage_from_payload,
    render_cohort_markdown,
)


def _year(fy: int, status: str, *, candidates: int = 0, promoted: int = 0,
          blocked: int = 0, errors: int = 0) -> dict:
    return {
        "fiscal_year": fy,
        "ingest_status": status,
        "ocr_candidates": candidates,
        "ocr_promoted": promoted,
        "ocr_blocked": blocked,
        "errors": errors,
    }


# ── aggregate_ticker: status classification ─────────────────────────────────

def test_no_source_pdf_when_all_years_source_missing():
    cov = aggregate_ticker("VHE", [_year(2023, "SOURCE_MISSING"), _year(2024, "SOURCE_MISSING")])
    assert cov.status == "no_source_pdf"
    assert cov.pdf_years == 0
    assert cov.ocr_promoted == 0


def test_no_source_pdf_when_only_tier2_cafef():
    cov = aggregate_ticker("DP3", [_year(2023, "TIER2_ONLY"), _year(2024, "CAFEF_EMPTY")])
    assert cov.status == "no_source_pdf"


def test_official_or_ocr_when_ocr_promoted():
    cov = aggregate_ticker(
        "DHG",
        [_year(2024, "OCR_PROMOTED", candidates=10, promoted=8, blocked=0)],
    )
    assert cov.status == "official_or_ocr"
    assert cov.ocr_years == 1
    assert cov.ocr_promoted == 8


def test_official_or_ocr_when_text_pdf_ready_without_ocr():
    cov = aggregate_ticker("IMP", [_year(2024, "OFFICIAL_FACTS_READY")])
    assert cov.status == "official_or_ocr"
    assert cov.official_text_years == 1
    assert cov.ocr_years == 0


def test_pending_review_with_promoted_facts_counts_as_official_or_ocr():
    cov = aggregate_ticker(
        "TRA",
        [_year(2024, "OCR_PENDING_REVIEW", candidates=6, promoted=4, blocked=2)],
    )
    assert cov.status == "official_or_ocr"
    assert cov.ocr_promoted == 4
    assert cov.ocr_blocked == 2


def test_pdf_found_no_facts_when_scanned_but_ocr_failed():
    cov = aggregate_ticker(
        "MKP",
        [_year(2024, "OCR_FAILED", candidates=0, promoted=0)],
    )
    assert cov.status == "pdf_found_no_facts"
    assert cov.pdf_years == 1
    assert cov.ocr_promoted == 0


def test_pdf_found_no_facts_when_scanned_and_ocr_disabled():
    cov = aggregate_ticker("DMC", [_year(2024, "EXTRACTION_FAILED_SCANNED_PDF")])
    assert cov.status == "pdf_found_no_facts"
    assert cov.pdf_years == 1


# ── aggregate_ticker: counts summed across years ────────────────────────────

def test_counts_summed_across_years():
    cov = aggregate_ticker(
        "DHG",
        [
            _year(2023, "OCR_PROMOTED", candidates=5, promoted=5, blocked=0),
            _year(2024, "OCR_PENDING_REVIEW", candidates=8, promoted=6, blocked=2, errors=1),
        ],
    )
    assert cov.years_total == 2
    assert cov.ocr_candidates == 13
    assert cov.ocr_promoted == 11
    assert cov.ocr_blocked == 2
    assert cov.errors == 1
    assert cov.pdf_years == 2


# ── coverage_from_payload (auto_ingest JSON contract) ───────────────────────

def test_coverage_from_payload_matches_aggregate_ticker():
    payload = {
        "ticker": "DHG",
        "years": [_year(2024, "OCR_PROMOTED", candidates=10, promoted=8)],
    }
    cov = coverage_from_payload(payload)
    assert cov == aggregate_ticker("DHG", payload["years"])


def test_coverage_from_payload_handles_missing_years():
    cov = coverage_from_payload({"ticker": "X"})
    assert cov.status == "no_source_pdf"
    assert cov.years_total == 0


# ── cohort_summary ──────────────────────────────────────────────────────────

def test_cohort_summary_groups_by_status_and_totals():
    coverages = [
        aggregate_ticker("DHG", [_year(2024, "OCR_PROMOTED", candidates=10, promoted=8)]),
        aggregate_ticker("VHE", [_year(2024, "SOURCE_MISSING")]),
        aggregate_ticker("DP3", [_year(2024, "SOURCE_MISSING")]),
        aggregate_ticker("MKP", [_year(2024, "OCR_FAILED")]),
    ]
    summary = cohort_summary(coverages)
    assert summary["tickers"] == 4
    assert summary["by_status"]["no_source_pdf"] == 2
    assert summary["by_status"]["official_or_ocr"] == 1
    assert summary["by_status"]["pdf_found_no_facts"] == 1
    assert summary["ocr_promoted"] == 8
    assert summary["ocr_candidates"] == 10


# ── render_cohort_markdown ──────────────────────────────────────────────────

def test_render_markdown_lists_every_ticker_and_status():
    coverages = [
        aggregate_ticker("DHG", [_year(2024, "OCR_PROMOTED", candidates=10, promoted=8)]),
        aggregate_ticker("VHE", [_year(2024, "SOURCE_MISSING")]),
    ]
    md = render_cohort_markdown(coverages, from_year=2024, to_year=2024)
    assert "DHG" in md
    assert "VHE" in md
    assert "official_or_ocr" in md
    assert "no_source_pdf" in md
    # Honest cohort totals are surfaced
    assert "2/2" in md or "tickers" in md.lower()
