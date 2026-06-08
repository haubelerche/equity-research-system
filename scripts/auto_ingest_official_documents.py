"""Auto-ingest orchestrator — Source-Provenance Rebuild.

Chains CafeF fetch → PDF discovery + download + extraction → ingest_year → reconcile_ticker
in a single command, replacing all manual steps.

Usage:
    python scripts/auto_ingest_official_documents.py --ticker DHG --from-year 2021 --to-year 2025
    python scripts/auto_ingest_official_documents.py --ticker DHG --from-year 2021 --to-year 2025 --dry-run
    python scripts/auto_ingest_official_documents.py --ticker DHG --from-year 2021 --to-year 2025 --channels cafef
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_env_file = Path(_PROJECT_ROOT) / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

ROOT = Path(_PROJECT_ROOT)
OFFICIAL_DOCS_DIR = ROOT / "data" / "official_documents"
ARTIFACT_DIR = ROOT / "artifacts" / "official_sources"

_CSV_FIELDNAMES = [
    "ticker", "fiscal_year", "period_type", "statement_type", "metric_id",
    "value", "unit", "document_title", "page_number", "table_name",
    "extracted_text", "extraction_method", "verified_by", "verified_at",
]


# ---------------------------------------------------------------------------
# Explicit pipeline status (never silently continue without knowing why)
# ---------------------------------------------------------------------------

class IngestStatus(str, Enum):
    """Explicit data-readiness states for one fiscal year.

    These states replace the previous silent-continue behaviour where
    `ingested=0 errors=0` looked like success but actually meant no data.
    """
    OFFICIAL_FACTS_READY = "OFFICIAL_FACTS_READY"
    """PDF or official structured source parsed, reconciled, promoted. Safe for final report."""

    TIER2_ONLY = "TIER2_ONLY"
    """Only Tier-2 source (CafeF/structured aggregator) — block final export, allow draft."""

    EXTRACTION_FAILED_SCANNED_PDF = "EXTRACTION_FAILED_SCANNED_PDF"
    """PDF downloaded but is scanned (no text layer) — OCR required for extraction."""

    EXTRACTION_FAILED_NO_TABLES = "EXTRACTION_FAILED_NO_TABLES"
    """PDF has text layer but no recognisable BCTC tables — narrative/governance PDF."""

    SOURCE_MISSING = "SOURCE_MISSING"
    """No official document or structured source found for this year."""

    CAFEF_EMPTY = "CAFEF_EMPTY"
    """CafeF API returned no rows (undocumented endpoint, may be rate-limited or absent)."""

    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    """Extraction returned data but confidence is below threshold — needs review."""

    CONFLICT_REVIEW = "CONFLICT_REVIEW"
    """CafeF and PDF values diverge beyond tolerance — needs analyst reconciliation."""

    DRY_RUN = "dry_run"
    """Dry-run mode — no DB writes, no actual fetch."""

    DONE = "done"
    """At least some facts ingested and promoted successfully."""

    DONE_WITH_ERRORS = "done_with_errors"
    """Facts partially ingested; some errors encountered."""

    OCR_PROMOTED = "OCR_PROMOTED"
    """OCR extraction succeeded and facts were validated, reconciled, and promoted."""

    OCR_PENDING_REVIEW = "OCR_PENDING_REVIEW"
    """OCR extracted facts but some are unresolved (conflicted or missing secondary). Draft only."""

    OCR_FAILED = "OCR_FAILED"
    """OCR runtime missing or extraction produced zero candidate facts."""


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AutoIngestConfig:
    ticker: str
    from_year: int
    to_year: int
    dry_run: bool = False
    channels: list[str] = field(default_factory=lambda: ["cafef", "pdf"])
    min_pdf_confidence: float = 0.6
    promote_official_only: bool = True
    ocr: bool = False  # enable OCR path for scanned PDFs


@dataclass
class PipelinePlan:
    ticker: str
    years: list[int]
    dry_run: bool
    channels: list[str]


@dataclass
class YearResult:
    fiscal_year: int
    cafef_rows: int = 0
    pdf_rows: int = 0
    ingested: int = 0
    promoted: int = 0
    errors: list[str] = field(default_factory=list)
    status: str = "pending"
    ingest_status: IngestStatus = IngestStatus.SOURCE_MISSING
    ocr_candidates: int = 0
    ocr_promoted: int = 0
    ocr_blocked: int = 0

    def status_summary(self) -> str:
        """Human-readable summary line for this year's ingest result."""
        parts = [
            f"FY{self.fiscal_year}",
            f"status={self.ingest_status.value}",
            f"cafef={self.cafef_rows}",
            f"pdf={self.pdf_rows}",
            f"ingested={self.ingested}",
            f"promoted={self.promoted}",
        ]
        if self.ocr_candidates > 0:
            parts.append(f"ocr_candidates={self.ocr_candidates}")
            parts.append(f"ocr_promoted={self.ocr_promoted}")
            parts.append(f"ocr_blocked={self.ocr_blocked}")
        if self.errors:
            parts.append(f"errors={len(self.errors)}")
        return " | ".join(parts)


# ---------------------------------------------------------------------------
# Pipeline plan
# ---------------------------------------------------------------------------

def build_pipeline_plan(cfg: AutoIngestConfig) -> PipelinePlan:
    """Build a simple execution plan from config."""
    return PipelinePlan(
        ticker=cfg.ticker,
        years=list(range(cfg.from_year, cfg.to_year + 1)),
        dry_run=cfg.dry_run,
        channels=cfg.channels,
    )


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------

def _write_extracted_csv(rows: list[dict], out_path: Path) -> None:
    """Write rows to out_path as CSV using _CSV_FIELDNAMES."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _validate_pdf_rows(
    rows: list[dict],
    requested_year: int,
) -> tuple[list[dict], list[str]]:
    """Return run-year PDF facts that are sufficiently complete for ingestion."""
    errors: list[str] = []
    accepted: dict[tuple[str, str, str], dict] = {}
    rejected_years: set[str] = set()

    for row in rows:
        raw_year = str(row.get("fiscal_year", "")).strip()
        if raw_year != str(requested_year):
            if raw_year:
                rejected_years.add(raw_year)
            continue

        metric_id = str(row.get("metric_id", "")).strip()
        statement_type = str(row.get("statement_type", "")).strip()
        period_type = str(row.get("period_type", "FY")).strip() or "FY"
        if not metric_id:
            continue

        key = (period_type, statement_type, metric_id)
        previous = accepted.get(key)
        if previous is None:
            accepted[key] = row
            continue
        if str(previous.get("value", "")) != str(row.get("value", "")):
            errors.append(
                f"FY{requested_year}: conflicting PDF values for {metric_id}"
            )

    if rejected_years:
        errors.append(
            f"FY{requested_year}: ignored rows belonging to fiscal years "
            f"{', '.join(sorted(rejected_years))}"
        )

    valid_rows = list(accepted.values())
    distinct_metrics = {row.get("metric_id") for row in valid_rows}
    if len(distinct_metrics) < 2:
        errors.append(
            f"FY{requested_year}: PDF extraction has only {len(distinct_metrics)} "
            "distinct run-year metric(s); minimum is 2"
        )
        return [], errors

    return valid_rows, errors


def _sanitize_extracted_csv_for_year(csv_path: Path, requested_year: int) -> int:
    """Remove stale cross-year and duplicate rows before DB ingestion."""
    if not csv_path.exists():
        return 0

    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))

    unique: dict[tuple[str, str, str, str], dict] = {}
    for row in rows:
        if str(row.get("fiscal_year", "")).strip() != str(requested_year):
            continue
        key = (
            str(row.get("period_type", "")).strip(),
            str(row.get("statement_type", "")).strip(),
            str(row.get("metric_id", "")).strip(),
            str(row.get("extraction_method", "")).strip(),
        )
        unique.setdefault(key, row)

    sanitized = list(unique.values())
    _write_extracted_csv(sanitized, csv_path)
    return len(sanitized)


# ---------------------------------------------------------------------------
# Channel 1: CafeF
# ---------------------------------------------------------------------------

def _fetch_cafef(
    ticker: str,
    fiscal_year: int,
    doc_dir: Path,
    dry_run: bool,
) -> list[dict]:
    """Fetch structured financial data from CafeF and write to extracted_facts.csv."""
    from backend.documents.connectors.cafef_connector import CafeFinanceConnector

    conn = CafeFinanceConnector()
    try:
        rows_raw = conn.fetch(ticker, fiscal_year)
    except Exception as exc:  # noqa: BLE001
        return [{"error": str(exc)}]

    now_str = datetime.now(UTC).isoformat()
    csv_rows: list[dict] = []
    for r in rows_raw:
        csv_rows.append({
            "ticker": ticker,
            "fiscal_year": fiscal_year,
            "period_type": "FY",
            "statement_type": "",
            "metric_id": r.metric_id,
            "value": r.value,
            "unit": r.unit,
            "document_title": f"CafeF {ticker} {fiscal_year} (HOSE/HNX filing data)",
            "page_number": "",
            "table_name": "structured_api",
            "extracted_text": r.raw_label,
            "extraction_method": "cafef_api",
            "verified_by": "",
            "verified_at": now_str,
        })

    if not dry_run and csv_rows:
        _write_extracted_csv(csv_rows, doc_dir / "extracted_facts.csv")

        meta_path = doc_dir / "metadata.json"
        if not meta_path.exists():
            ticker_lower = ticker.lower()
            try:
                from backend.documents.company_registry import get_company, has_company
                _company_name = get_company(ticker).company_name_vi if has_company(ticker) else ticker
            except Exception:
                _company_name = ticker
            meta = {
                "ticker": ticker,
                "company_name": _company_name,
                "source_type": "annual_report",
                "issuer": "CafeF / HOSE / HNX",
                "title": f"CafeF {ticker} {fiscal_year} — Dữ liệu BCTC từ HOSE/HNX",
                "url": f"https://s.cafef.vn/bctc/{ticker_lower}-bao-cao-tai-chinh.chn",
                "local_path": "",
                "published_date": f"{fiscal_year}-12-31",
                "fiscal_year": fiscal_year,
                "language": "vi",
                "file_hash": "",
            }
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return csv_rows


# ---------------------------------------------------------------------------
# OCR helpers
# ---------------------------------------------------------------------------

def _build_secondary_source_from_cafef(
    cafef_rows: list[dict],
    ticker: str,
    fiscal_year: int,
) -> dict[tuple[str, int, str, str], float]:
    """Convert CafeF CSV rows to secondary source lookup for OCR reconciliation.

    Key: (ticker, fiscal_year, period_type, metric_id)
    Value: normalized_value (float)
    """
    secondary: dict[tuple[str, int, str, str], float] = {}
    for row in cafef_rows:
        if "error" in row or "note" in row:
            continue
        metric_id = row.get("metric_id", "").strip()
        period_type = row.get("period_type", "FY").strip() or "FY"
        try:
            value = float(row.get("value", ""))
        except (ValueError, TypeError):
            continue
        if metric_id:
            secondary[(ticker, fiscal_year, period_type, metric_id)] = value
    return secondary


def _run_ocr_pipeline(
    pdf_path: Path,
    ticker: str,
    fiscal_year: int,
    document_title: str,
    secondary_source: dict,
    doc_dir: Path,
) -> tuple[list[dict], IngestStatus, int, int, int]:
    """Run OCR extraction → staging → validation → reconciliation → promotion.

    Returns (csv_rows_for_db, ingest_status, ocr_candidates, ocr_promoted, ocr_blocked).

    csv_rows_for_db: list of dicts in _CSV_FIELDNAMES format for downstream DB ingest.
    ingest_status: OCR_PROMOTED | OCR_PENDING_REVIEW | OCR_FAILED
    """
    from backend.documents.pdf_extractor import extract_from_pdf_ocr
    from backend.documents.ocr_artifacts import (
        compute_file_checksum, init_ocr_run, save_candidate_rows, finalize_ocr_run,
    )
    from backend.documents.ocr_candidate_facts import from_extracted_rows, save_candidate_facts
    from backend.documents.ocr_validation import validate_candidate_facts, load_known_metric_ids
    from backend.documents.ocr_reconciliation import reconcile_candidate_facts, save_reconciliation_report
    from backend.documents.fact_promotion import promote_candidate_facts

    # 1. Check OCR runtime
    try:
        import pytesseract  # noqa: F401
        from pdf2image import convert_from_path  # noqa: F401
    except ImportError as exc:
        missing = str(exc)
        print(f"[auto_ingest] OCR runtime missing ({missing}) — run scripts/check_ocr_runtime.py")
        return [], IngestStatus.OCR_FAILED, 0, 0, 0

    # 2. Compute checksum + init OCR run
    try:
        checksum = compute_file_checksum(pdf_path)
        document_id = f"{ticker}_{fiscal_year}_{checksum[:12]}"
        ocr_artifacts_dir = ROOT / "data" / "ocr_artifacts"
        meta, run_dir = init_ocr_run(
            ticker=ticker,
            fiscal_year=fiscal_year,
            document_id=document_id,
            source_uri=str(pdf_path),
            source_checksum=checksum,
            pdf_type="scanned",
            ocr_lang="vie+eng",
            dpi=300,
            base_dir=ocr_artifacts_dir,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[auto_ingest] OCR artifact init failed: {exc}")
        return [], IngestStatus.OCR_FAILED, 0, 0, 0

    # 3. Extract via OCR
    print(f"[auto_ingest] {ticker} {fiscal_year}: running OCR on scanned PDF...")
    try:
        extracted_rows = extract_from_pdf_ocr(
            pdf_path=pdf_path,
            ticker=ticker,
            fiscal_year=fiscal_year,
            document_title=document_title,
            lang="vie+eng",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[auto_ingest] OCR extraction error: {exc}")
        finalize_ocr_run(run_dir, meta, 0, 1, 0, 0, [], [str(exc)], status="failed")
        return [], IngestStatus.OCR_FAILED, 0, 0, 0

    if not extracted_rows:
        print(f"[auto_ingest] {ticker} {fiscal_year}: OCR produced no recognisable facts")
        finalize_ocr_run(run_dir, meta, 0, 0, 0, 0, ["no_facts_extracted"], [], status="completed")
        return [], IngestStatus.OCR_FAILED, 0, 0, 0

    # 4. Save raw candidate rows to artifact
    raw_rows = [
        {"page_number": r.page_number, "raw_label": r.extracted_text, "raw_value": str(r.value)}
        for r in extracted_rows
    ]
    save_candidate_rows(run_dir, raw_rows)
    finalize_ocr_run(run_dir, meta, len(extracted_rows), 0, len(extracted_rows), 0, [], [], status="completed")

    # 5. Stage as CandidateFact
    candidate_facts = from_extracted_rows(extracted_rows, ocr_run_id=meta.ocr_run_id, document_id=document_id)

    # 6. Validate
    known_metrics = load_known_metric_ids()
    validate_candidate_facts(candidate_facts, known_metrics)

    # 7. Reconcile against CafeF
    recon_records = reconcile_candidate_facts(candidate_facts, secondary_source, "cafef")
    recon_dir = ROOT / "data" / "reconciliation"
    save_reconciliation_report(recon_records, ticker, fiscal_year, recon_dir)

    # 8. Promote
    fact_table, promo_results = promote_candidate_facts(candidate_facts)

    # 9. Save candidate facts artifact
    candidates_dir = ROOT / "data" / "candidate_facts" / ticker / str(fiscal_year)
    candidates_dir.mkdir(parents=True, exist_ok=True)
    save_candidate_facts(candidate_facts, candidates_dir / "candidate_facts.json")

    # 10. Count results
    n_candidates = len(candidate_facts)
    n_promoted = sum(1 for r in promo_results if r.promoted)
    n_blocked = sum(1 for r in promo_results if not r.promoted)

    print(
        f"[auto_ingest] {ticker} {fiscal_year}: OCR candidates={n_candidates} "
        f"promoted={n_promoted} blocked={n_blocked}"
    )

    # 11. Convert promoted facts to CSV rows for downstream DB ingest
    now_str = datetime.now(UTC).isoformat()
    csv_rows: list[dict] = []
    for metric_id, period_dict in fact_table.items():
        for _period_key, entry in period_dict.items():
            csv_rows.append({
                "ticker": ticker,
                "fiscal_year": fiscal_year,
                "period_type": "FY",
                "statement_type": "",
                "metric_id": metric_id,
                "value": entry.value,
                "unit": "vnd_bn",
                "document_title": document_title,
                "page_number": "",
                "table_name": "ocr_extracted",
                "extracted_text": "",
                "extraction_method": "ocr_tesseract",
                "verified_by": "",
                "verified_at": now_str,
            })

    if csv_rows:
        _write_extracted_csv(csv_rows, doc_dir / "extracted_facts_ocr.csv")
        # Merge into main extracted_facts.csv (OCR facts fill gaps, PDF-text facts take precedence)
        existing_path = doc_dir / "extracted_facts.csv"
        if existing_path.exists():
            import csv as csv_mod
            with existing_path.open(encoding="utf-8-sig", newline="") as fh:
                existing = list(csv_mod.DictReader(fh))
            existing_metrics = {r.get("metric_id", "") for r in existing}
            ocr_only = [r for r in csv_rows if r.get("metric_id", "") not in existing_metrics]
            if ocr_only:
                _write_extracted_csv(existing + ocr_only, existing_path)
        else:
            _write_extracted_csv(csv_rows, existing_path)

    # Determine status
    if n_blocked > 0:
        status = IngestStatus.OCR_PENDING_REVIEW
    else:
        status = IngestStatus.OCR_PROMOTED

    return csv_rows, status, n_candidates, n_promoted, n_blocked


# ---------------------------------------------------------------------------
# Channel 2: PDF discovery + extraction
# ---------------------------------------------------------------------------

def _is_scanned_pdf(pdf_path: Path, sample_pages: int = 5) -> bool:
    """Return True if the PDF has no extractable text (likely a scanned image)."""
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            pages_to_check = pdf.pages[:sample_pages]
            total_chars = sum(len(p.extract_text() or "") for p in pages_to_check)
            return total_chars == 0
    except Exception:  # noqa: BLE001
        return False


def _fetch_pdf(
    ticker: str,
    fiscal_year: int,
    doc_dir: Path,
    cfg: AutoIngestConfig,
    cafef_rows: list[dict] | None = None,
) -> tuple[list[dict], IngestStatus, dict]:
    """Discover, download, and extract a PDF annual report for the given year.

    Returns (csv_rows, IngestStatus, ocr_stats):
      - EXTRACTION_FAILED_SCANNED_PDF: PDF downloaded but pdfplumber reads 0 text (OCR disabled)
      - EXTRACTION_FAILED_NO_TABLES: text readable but no BCTC metrics mapped
      - SOURCE_MISSING: no high-confidence PDF found by the discovery connectors
      - OFFICIAL_FACTS_READY: extraction succeeded with ≥1 facts
      - OCR_PROMOTED / OCR_PENDING_REVIEW / OCR_FAILED: OCR path results (when cfg.ocr=True)

    ocr_stats keys: ocr_candidates, ocr_promoted, ocr_blocked (all 0 when OCR not run).
    """
    try:
        from backend.documents.official_document_discovery import discover_documents, fetch_candidate
        from backend.documents.pdf_extractor import extract_to_csv

        result = discover_documents(
            ticker, fiscal_year, fiscal_year,
            min_confidence=cfg.min_pdf_confidence,
        )

        # Filter to financial documents (not governance/sustainability)
        annual_cands = [
            c for c in result.ranking.selected
            if c.document_type in ("annual_report", "audited_financial_statement",
                                   "financial_statement")
        ]
        if not annual_cands:
            return [], IngestStatus.SOURCE_MISSING, {}

        best = annual_cands[0]

        if cfg.dry_run:
            return [{"note": f"dry_run: would fetch {best.source_url}"}], IngestStatus.DRY_RUN, {}

        rec = fetch_candidate(best)
        pdf_path = Path(rec.local_path)

        # Detect scanned PDF — route to OCR if enabled, else return explicit status
        if _is_scanned_pdf(pdf_path):
            print(f"[auto_ingest] {ticker} {fiscal_year}: PDF is scanned ({best.title[:40]})")
            if cfg.ocr:
                secondary = _build_secondary_source_from_cafef(
                    cafef_rows or [], ticker, fiscal_year,
                )
                ocr_rows, ocr_status, n_cand, n_prom, n_bloc = _run_ocr_pipeline(
                    pdf_path=pdf_path,
                    ticker=ticker,
                    fiscal_year=fiscal_year,
                    document_title=best.title,
                    secondary_source=secondary,
                    doc_dir=doc_dir,
                )
                return ocr_rows, ocr_status, {
                    "ocr_candidates": n_cand,
                    "ocr_promoted": n_prom,
                    "ocr_blocked": n_bloc,
                }
            print(f"[auto_ingest]   → OCR disabled (pass --ocr to enable OCR extraction)")
            return [], IngestStatus.EXTRACTION_FAILED_SCANNED_PDF, {}

        pdf_csv_path = doc_dir / "extracted_facts_pdf.csv"
        extracted_rows = extract_to_csv(pdf_path, ticker, fiscal_year, best.title, pdf_csv_path)
        raw_csv_rows = [r.to_csv_dict() for r in extracted_rows]
        csv_rows, validation_errors = _validate_pdf_rows(raw_csv_rows, fiscal_year)

        if not csv_rows:
            return (
                [{"error": error} for error in validation_errors],
                IngestStatus.LOW_CONFIDENCE if raw_csv_rows else IngestStatus.EXTRACTION_FAILED_NO_TABLES,
                {},
            )

        # PDF is Tier 0; CafeF is Tier 2. PDF rows take precedence for overlapping metrics.
        existing_csv_path = doc_dir / "extracted_facts.csv"
        if existing_csv_path.exists():
            with existing_csv_path.open(encoding="utf-8-sig", newline="") as fh:
                existing_rows = list(csv.DictReader(fh))
            pdf_metric_ids = {r.get("metric_id", "") for r in csv_rows}
            cafef_only_rows = [r for r in existing_rows if r.get("metric_id", "") not in pdf_metric_ids]
            merged = cafef_only_rows + csv_rows
            _write_extracted_csv(merged, existing_csv_path)
        else:
            _write_extracted_csv(csv_rows, existing_csv_path)

        # Write metadata.json if not already present
        meta_path = doc_dir / "metadata.json"
        if not meta_path.exists():
            try:
                from backend.documents.company_registry import get_company, has_company
                _company_name = get_company(ticker).company_name_vi if has_company(ticker) else ticker
            except Exception:  # noqa: BLE001
                _company_name = ticker
            meta = {
                "ticker": ticker,
                "company_name": _company_name,
                "source_type": "audited_financial_statement",
                "issuer": best.publisher or best.source_name,
                "title": best.title,
                "url": best.source_url,
                "local_path": rec.local_path,
                "published_date": f"{fiscal_year}-12-31",
                "fiscal_year": fiscal_year,
                "language": "vi",
                "file_hash": rec.file_hash,
            }
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        result_rows = csv_rows + [{"error": error} for error in validation_errors]
        return result_rows, IngestStatus.OFFICIAL_FACTS_READY, {}

    except Exception as exc:  # noqa: BLE001
        return [{"error": str(exc)}], IngestStatus.SOURCE_MISSING, {}


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(cfg: AutoIngestConfig) -> list[YearResult]:
    """Run the full auto-ingest pipeline for each year in the config range.

    Each YearResult.ingest_status carries an explicit IngestStatus so callers
    know *why* a year has no promoted facts (SOURCE_MISSING vs SCANNED_PDF vs
    CAFEF_EMPTY), rather than seeing a silent ``ingested=0``.
    """
    plan = build_pipeline_plan(cfg)
    results: list[YearResult] = []

    for year in plan.years:
        yr = YearResult(fiscal_year=year, ingest_status=IngestStatus.SOURCE_MISSING)
        doc_dir = OFFICIAL_DOCS_DIR / cfg.ticker / str(year)
        doc_dir.mkdir(parents=True, exist_ok=True)

        # ── Channel 1: CafeF (Tier 2) ──────────────────────────────────────
        if "cafef" in cfg.channels:
            cafef_rows = _fetch_cafef(cfg.ticker, year, doc_dir, cfg.dry_run)
            good_cafef = [r for r in cafef_rows if "error" not in r and "note" not in r]
            yr.cafef_rows = len(good_cafef)
            if yr.cafef_rows > 0:
                yr.ingest_status = IngestStatus.TIER2_ONLY
            elif not cafef_rows:
                yr.errors.append(f"FY{year}: CafeF API returned no rows (CAFEF_EMPTY)")
            if any("error" in r for r in cafef_rows):
                yr.errors.append(f"cafef: {[r['error'] for r in cafef_rows if 'error' in r]}")

        # ── Channel 2: PDF (Tier 0) ─────────────────────────────────────────
        if "pdf" in cfg.channels:
            cafef_rows_for_ocr = (
                [r for r in cafef_rows if "error" not in r and "note" not in r]
                if "cafef" in cfg.channels
                else []
            )
            pdf_rows, pdf_status, ocr_stats = _fetch_pdf(
                cfg.ticker, year, doc_dir, cfg, cafef_rows=cafef_rows_for_ocr
            )
            yr.ocr_candidates = ocr_stats.get("ocr_candidates", 0)
            yr.ocr_promoted = ocr_stats.get("ocr_promoted", 0)
            yr.ocr_blocked = ocr_stats.get("ocr_blocked", 0)
            good_pdf = [r for r in pdf_rows if "error" not in r and "note" not in r]
            yr.pdf_rows = len(good_pdf)
            yr.errors.extend(
                str(r["error"]) for r in pdf_rows if "error" in r
            )
            # PDF status overrides CafeF when it gives a definitive verdict
            if pdf_status not in (IngestStatus.SOURCE_MISSING,):
                yr.ingest_status = pdf_status
            elif yr.cafef_rows > 0:
                yr.ingest_status = IngestStatus.TIER2_ONLY
            if pdf_status == IngestStatus.EXTRACTION_FAILED_SCANNED_PDF:
                yr.errors.append(
                    f"FY{year}: PDF is scanned image (0 text) — OCR required. "
                    f"Manually enter facts into "
                    f"data/official_documents/{cfg.ticker}/{year}/extracted_facts.csv"
                )
            elif pdf_status == IngestStatus.EXTRACTION_FAILED_NO_TABLES:
                yr.errors.append(
                    f"FY{year}: PDF has text but no recognisable BCTC tables "
                    "(likely narrative/governance document)."
                )

        if cfg.dry_run:
            yr.ingest_status = IngestStatus.DRY_RUN
            yr.status = "dry_run"
            results.append(yr)
            print(f"[auto_ingest] (dry-run) {yr.status_summary()}")
            continue

        # ── Ingest into DB ──────────────────────────────────────────────────
        extracted_csv = doc_dir / "extracted_facts.csv"
        sanitized_rows = _sanitize_extracted_csv_for_year(extracted_csv, year)
        if sanitized_rows > 0:
            try:
                from scripts.ingest_official_documents import ingest_year
                summary = ingest_year(cfg.ticker, year, dry_run=False)
                yr.ingested = summary.get("facts_ingested", 0)
                yr.errors.extend(summary.get("errors", []))
            except Exception as exc:  # noqa: BLE001
                yr.errors.append(f"ingest: {exc}")

        # ── Reconcile and promote ───────────────────────────────────────────
        if yr.ingested > 0:
            try:
                from backend.reconciliation.financial_fact_reconciler import reconcile_ticker
                rec_sum = reconcile_ticker(
                    cfg.ticker, year, year,
                    promote=True,
                    promote_official_only=cfg.promote_official_only,
                )
                yr.promoted = rec_sum.promoted
            except Exception as exc:  # noqa: BLE001
                yr.errors.append(f"reconcile: {exc}")

        if yr.ingest_status == IngestStatus.OFFICIAL_FACTS_READY and (
            yr.ingested <= 0 or yr.promoted <= 0 or yr.errors
        ):
            yr.ingest_status = IngestStatus.LOW_CONFIDENCE

        yr.status = "done" if not yr.errors else "done_with_errors"
        results.append(yr)
        print(f"[auto_ingest] {yr.status_summary()}")

    return results


# ---------------------------------------------------------------------------
# Artifact writer
# ---------------------------------------------------------------------------

def _write_artifact(ticker: str, cfg: AutoIngestConfig, results: list[YearResult]) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out = ARTIFACT_DIR / f"{ticker}_auto_ingest_report.md"
    total_ingested = sum(r.ingested for r in results)
    total_promoted = sum(r.promoted for r in results)
    total_errors = sum(len(r.errors) for r in results)
    now_str = datetime.now(UTC).isoformat()

    lines = [
        f"# {ticker} Auto-Ingest Report",
        "",
        f"- Generated: {now_str}",
        f"- Channels: {', '.join(cfg.channels) or '(none)'}",
        f"- Dry run: {cfg.dry_run}",
        "",
        "| Year | IngestStatus | CafeF | PDF | Ingested | Promoted |",
        "|------|-------------|-------|-----|----------|----------|",
    ]
    for r in results:
        status_val = r.ingest_status.value if isinstance(r.ingest_status, IngestStatus) else r.ingest_status
        lines.append(
            f"| {r.fiscal_year} | `{status_val}` | {r.cafef_rows} | {r.pdf_rows} "
            f"| {r.ingested} | {r.promoted} |"
        )
    lines += [
        "",
        f"**Total ingested:** {total_ingested}  ",
        f"**Total promoted:** {total_promoted}  ",
        f"**Total errors:** {total_errors}  ",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Auto-ingest official documents: CafeF + PDF → ingest → reconcile."
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol (e.g. DHG)")
    parser.add_argument("--from-year", type=int, required=True, dest="from_year")
    parser.add_argument("--to-year", type=int, required=True, dest="to_year")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="Validate without writing to DB")
    parser.add_argument("--channels", default="cafef,pdf",
                        help="Comma-separated channels: cafef,pdf (default: cafef,pdf)")
    parser.add_argument("--min-pdf-confidence", type=float, default=0.6,
                        dest="min_pdf_confidence")
    parser.add_argument("--ocr", action="store_true",
                        help="Enable OCR for scanned PDFs (requires tesseract + poppler)")
    args = parser.parse_args()

    ticker = args.ticker.strip().upper()
    channels = [c.strip() for c in args.channels.split(",") if c.strip()]

    cfg = AutoIngestConfig(
        ticker=ticker,
        from_year=args.from_year,
        to_year=args.to_year,
        dry_run=args.dry_run,
        channels=channels,
        min_pdf_confidence=args.min_pdf_confidence,
        ocr=args.ocr,
    )

    results = run_pipeline(cfg)

    total_ingested = sum(r.ingested for r in results)
    total_promoted = sum(r.promoted for r in results)
    total_errors = sum(len(r.errors) for r in results)
    print(
        f"[auto_ingest] DONE {ticker} {args.from_year}–{args.to_year}: "
        f"ingested={total_ingested} promoted={total_promoted} errors={total_errors}"
    )

    artifact = _write_artifact(ticker, cfg, results)
    print(f"[auto_ingest] artifact: {artifact}")


if __name__ == "__main__":
    main()
