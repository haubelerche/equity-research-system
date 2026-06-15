"""Aggregate per-ticker auto-ingest results into an honest cohort OCR coverage report.

The auto-ingest pipeline (scripts/auto_ingest_official_documents.py) runs
discover -> fetch -> OCR -> promote per ticker per year, emitting an explicit
``ingest_status`` for each year. This module rolls those year-level results up to
one status per ticker, so the batch can report — across the whole universe —
which tickers actually obtained official/OCR-backed facts and which are still
vnstock-only because no source PDF was reachable.

Status is deliberately honest: many small UPCOM names have no discoverable PDF
and land in ``no_source_pdf`` rather than being silently counted as covered.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

# Year ingest_status values that mean a source PDF was actually downloaded.
PDF_DOWNLOADED_STATUSES = frozenset({
    "OFFICIAL_FACTS_READY",
    "OCR_PROMOTED",
    "OCR_PENDING_REVIEW",
    "OCR_FAILED",
    "EXTRACTION_FAILED_SCANNED_PDF",
    "EXTRACTION_FAILED_NO_TABLES",
    "LOW_CONFIDENCE",
})

# Per-ticker coverage states.
STATUS_OFFICIAL_OR_OCR = "official_or_ocr"
STATUS_PDF_NO_FACTS = "pdf_found_no_facts"
STATUS_NO_SOURCE_PDF = "no_source_pdf"

COHORT_STATUSES = (STATUS_OFFICIAL_OR_OCR, STATUS_PDF_NO_FACTS, STATUS_NO_SOURCE_PDF)


@dataclass
class TickerCoverage:
    ticker: str
    years_total: int
    pdf_years: int
    official_text_years: int
    ocr_years: int
    ocr_candidates: int
    ocr_promoted: int
    ocr_blocked: int
    status: str
    errors: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def _year_has_official_facts(status: str, ocr_promoted: int) -> bool:
    """A year contributes official/OCR-backed facts if a text PDF was parsed or OCR promoted."""
    return status == "OFFICIAL_FACTS_READY" or ocr_promoted > 0


def aggregate_ticker(ticker: str, year_results: list[dict]) -> TickerCoverage:
    """Roll per-year ingest results up to a single honest coverage status for one ticker."""
    pdf_years = 0
    official_text_years = 0
    ocr_years = 0
    ocr_candidates = 0
    ocr_promoted = 0
    ocr_blocked = 0
    errors = 0
    any_official_facts = False

    for yr in year_results:
        status = str(yr.get("ingest_status") or "")
        promoted = int(yr.get("ocr_promoted") or 0)
        ocr_candidates += int(yr.get("ocr_candidates") or 0)
        ocr_promoted += promoted
        ocr_blocked += int(yr.get("ocr_blocked") or 0)
        errors += int(yr.get("errors") or 0)

        if status in PDF_DOWNLOADED_STATUSES:
            pdf_years += 1
        if status == "OFFICIAL_FACTS_READY":
            official_text_years += 1
        if promoted > 0:
            ocr_years += 1
        if _year_has_official_facts(status, promoted):
            any_official_facts = True

    if any_official_facts:
        status = STATUS_OFFICIAL_OR_OCR
    elif pdf_years > 0:
        status = STATUS_PDF_NO_FACTS
    else:
        status = STATUS_NO_SOURCE_PDF

    return TickerCoverage(
        ticker=ticker,
        years_total=len(year_results),
        pdf_years=pdf_years,
        official_text_years=official_text_years,
        ocr_years=ocr_years,
        ocr_candidates=ocr_candidates,
        ocr_promoted=ocr_promoted,
        ocr_blocked=ocr_blocked,
        status=status,
        errors=errors,
    )


def coverage_from_payload(payload: dict) -> TickerCoverage:
    """Build a TickerCoverage from an auto_ingest per-ticker JSON payload.

    Expected shape: ``{"ticker": str, "years": [ {fiscal_year, ingest_status, ...}, ... ]}``.
    """
    return aggregate_ticker(str(payload.get("ticker") or ""), list(payload.get("years") or []))


def cohort_summary(coverages: list[TickerCoverage]) -> dict:
    """Aggregate cohort-level counts: tickers per status and total OCR facts."""
    by_status = {s: 0 for s in COHORT_STATUSES}
    for cov in coverages:
        by_status[cov.status] = by_status.get(cov.status, 0) + 1
    return {
        "tickers": len(coverages),
        "by_status": by_status,
        "ocr_candidates": sum(c.ocr_candidates for c in coverages),
        "ocr_promoted": sum(c.ocr_promoted for c in coverages),
        "ocr_blocked": sum(c.ocr_blocked for c in coverages),
    }


def render_cohort_markdown(
    coverages: list[TickerCoverage], *, from_year: int, to_year: int
) -> str:
    """Render an honest cohort coverage report as Markdown."""
    summary = cohort_summary(coverages)
    covered = summary["by_status"][STATUS_OFFICIAL_OR_OCR]
    total = summary["tickers"]

    lines = [
        "# OCR / Official-Document Coverage Report",
        "",
        f"- Fiscal range: {from_year}–{to_year}",
        f"- Tickers with official/OCR-backed facts: **{covered}/{total}**",
        f"- PDF found but no facts: {summary['by_status'][STATUS_PDF_NO_FACTS]}",
        f"- No source PDF (vnstock-only): {summary['by_status'][STATUS_NO_SOURCE_PDF]}",
        f"- Total OCR facts promoted: {summary['ocr_promoted']} "
        f"(candidates {summary['ocr_candidates']}, blocked {summary['ocr_blocked']})",
        "",
        "| Ticker | Status | Years | PDF yrs | OCR yrs | OCR cand | OCR promoted | OCR blocked | Errors |",
        "|--------|--------|-------|---------|---------|----------|--------------|-------------|--------|",
    ]
    for cov in sorted(coverages, key=lambda c: (COHORT_STATUSES.index(c.status), c.ticker)):
        lines.append(
            f"| {cov.ticker} | `{cov.status}` | {cov.years_total} | {cov.pdf_years} "
            f"| {cov.ocr_years} | {cov.ocr_candidates} | {cov.ocr_promoted} "
            f"| {cov.ocr_blocked} | {cov.errors} |"
        )
    lines.append("")
    return "\n".join(lines)
