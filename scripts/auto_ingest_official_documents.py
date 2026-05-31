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
# Channel 2: PDF discovery + extraction
# ---------------------------------------------------------------------------

def _fetch_pdf(
    ticker: str,
    fiscal_year: int,
    doc_dir: Path,
    cfg: AutoIngestConfig,
) -> list[dict]:
    """Discover, download, and extract a PDF annual report for the given year."""
    try:
        from backend.documents.official_document_discovery import discover_documents, fetch_candidate
        from backend.documents.pdf_extractor import extract_to_csv

        result = discover_documents(
            ticker, fiscal_year, fiscal_year,
            min_confidence=cfg.min_pdf_confidence,
        )

        # Filter to annual_report or audited_financial_statement only
        annual_cands = [
            c for c in result.ranking.selected
            if c.document_type in ("annual_report", "audited_financial_statement")
        ]
        if not annual_cands:
            return []

        best = annual_cands[0]

        if cfg.dry_run:
            return [{"note": f"dry_run: would fetch {best.source_url}"}]

        rec = fetch_candidate(best)
        pdf_path = Path(rec.local_path)

        pdf_csv_path = doc_dir / "extracted_facts_pdf.csv"
        extracted_rows = extract_to_csv(pdf_path, ticker, fiscal_year, best.title, pdf_csv_path)
        csv_rows = [r.to_csv_dict() for r in extracted_rows]

        if csv_rows:
            # PDF is Tier 0 (official document); CafeF is Tier 2. PDF rows take precedence
            # for overlapping metrics. Non-overlapping CafeF rows are preserved.
            existing_csv_path = doc_dir / "extracted_facts.csv"
            if existing_csv_path.exists():
                with existing_csv_path.open(encoding="utf-8-sig", newline="") as fh:
                    existing_rows = list(csv.DictReader(fh))
                pdf_metric_ids = {r.get("metric_id", "") for r in csv_rows}
                # Keep existing (CafeF) rows only for metrics NOT in PDF
                cafef_only_rows = [r for r in existing_rows if r.get("metric_id", "") not in pdf_metric_ids]
                merged = cafef_only_rows + csv_rows  # PDF rows override CafeF for overlapping metrics
                _write_extracted_csv(merged, existing_csv_path)
            else:
                _write_extracted_csv(csv_rows, existing_csv_path)

            # Write metadata.json if not already present
            meta_path = doc_dir / "metadata.json"
            if not meta_path.exists():
                try:
                    from backend.documents.company_registry import get_company, has_company
                    _company_name = get_company(ticker).company_name_vi if has_company(ticker) else ticker
                except Exception:
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
                meta_path.write_text(
                    json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
                )

        return csv_rows if isinstance(csv_rows, list) else []

    except Exception as exc:  # noqa: BLE001
        return [{"error": str(exc)}]


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(cfg: AutoIngestConfig) -> list[YearResult]:
    """Run the full auto-ingest pipeline for each year in the config range."""
    plan = build_pipeline_plan(cfg)
    results: list[YearResult] = []

    for year in plan.years:
        yr = YearResult(fiscal_year=year)
        doc_dir = OFFICIAL_DOCS_DIR / cfg.ticker / str(year)
        doc_dir.mkdir(parents=True, exist_ok=True)

        # Channel 1: CafeF
        if "cafef" in cfg.channels:
            cafef_rows = _fetch_cafef(cfg.ticker, year, doc_dir, cfg.dry_run)
            yr.cafef_rows = len([r for r in cafef_rows if "error" not in r and "note" not in r])
            if any("error" in r for r in cafef_rows):
                yr.errors.append(f"cafef: {cafef_rows}")

        # Channel 2: PDF
        if "pdf" in cfg.channels:
            pdf_rows = _fetch_pdf(cfg.ticker, year, doc_dir, cfg)
            yr.pdf_rows = len([r for r in pdf_rows if "error" not in r and "note" not in r])
            if any("error" in r for r in pdf_rows):
                yr.errors.append(f"pdf: {pdf_rows}")

        if cfg.dry_run:
            yr.status = "dry_run"
            results.append(yr)
            continue

        # Ingest
        if (doc_dir / "extracted_facts.csv").exists():
            try:
                from scripts.ingest_official_documents import ingest_year
                summary = ingest_year(cfg.ticker, year, dry_run=False)
                yr.ingested = summary.get("facts_ingested", 0)
                yr.errors.extend(summary.get("errors", []))
            except Exception as exc:  # noqa: BLE001
                yr.errors.append(f"ingest: {exc}")

        # Reconcile
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

        yr.status = "done" if not yr.errors else "done_with_errors"
        results.append(yr)
        print(
            f"[auto_ingest] {cfg.ticker} {year}: "
            f"cafef={yr.cafef_rows} pdf={yr.pdf_rows} "
            f"ingested={yr.ingested} promoted={yr.promoted} errors={len(yr.errors)}"
        )

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
        "| Year | CafeF rows | PDF rows | Ingested | Promoted | Status |",
        "|------|-----------|---------|----------|----------|--------|",
    ]
    for r in results:
        lines.append(
            f"| {r.fiscal_year} | {r.cafef_rows} | {r.pdf_rows} "
            f"| {r.ingested} | {r.promoted} | {r.status} |"
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
