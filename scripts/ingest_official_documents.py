"""Official-document ingestion — Source-Provenance Rebuild, Phase 3.

Ingests manually-placed official documents (audited BCTC / annual reports / exchange
disclosures / company IR) and their extracted financial facts into the verification
layer (ingest.official_documents + fact.fact_observations).

Directory layout (manual placement; analyst drops files in):

    data/official_documents/<TICKER>/<YEAR>/
        metadata.json          # document metadata (see _TEMPLATE)
        extracted_facts.csv     # facts transcribed from the document
        source_document.pdf      # the official PDF (hash-checked against metadata)

Usage:
    python scripts/ingest_official_documents.py --ticker DHG --from-year 2021 --to-year 2025
    python scripts/ingest_official_documents.py --ticker DHG --from-year 2021 --to-year 2025 --dry-run

If no documents are present the script reports them as MISSING (it never fabricates
facts). Final report export stays blocked until real documents are ingested.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
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
DOCS_DIR = ROOT / "data" / "official_documents"
ARTIFACT_DIR = ROOT / "artifacts" / "official_sources"

# Minimum metrics expected per fiscal year (plan Phase 3).
MIN_METRICS: tuple[str, ...] = (
    "revenue.net", "gross_profit.total", "operating_profit.total",
    "profit_before_tax.total", "net_income.parent", "eps.basic",
    "total_assets.ending", "equity.parent", "short_term_debt.ending",
    "long_term_debt.ending", "operating_cash_flow.total", "capex.total",
)

# Friendly metric_id aliases → canonical ref.line_items codes.
METRIC_ALIASES: dict[str, str] = {
    "revenue_net": "revenue.net",
    "gross_profit": "gross_profit.total",
    "operating_profit": "operating_profit.total",
    "profit_before_tax": "profit_before_tax.total",
    "net_income": "net_income.parent",
    "eps": "eps.basic",
    "total_assets": "total_assets.ending",
    "total_equity": "equity.parent",
    "short_term_debt": "short_term_debt.ending",
    "long_term_debt": "long_term_debt.ending",
    "operating_cash_flow": "operating_cash_flow.total",
    "capex": "capex.total",
}

REQUIRED_CSV_COLUMNS = {
    "ticker", "fiscal_year", "period_type", "statement_type", "metric_id",
    "value", "unit", "document_title", "page_number", "table_name",
    "extracted_text", "extraction_method", "verified_by", "verified_at",
}


def canonical_metric(metric_id: str) -> str:
    return METRIC_ALIASES.get(metric_id.strip(), metric_id.strip())


def compute_file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_metadata(year_dir: Path) -> dict | None:
    meta_path = year_dir / "metadata.json"
    if not meta_path.exists():
        return None
    return json.loads(meta_path.read_text(encoding="utf-8"))


def load_extracted_facts(year_dir: Path) -> tuple[list[dict], list[str]]:
    """Return (rows, errors). Validates required columns."""
    csv_path = year_dir / "extracted_facts.csv"
    if not csv_path.exists():
        return [], ["extracted_facts.csv missing"]
    errors: list[str] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        cols = set(reader.fieldnames or [])
        missing = REQUIRED_CSV_COLUMNS - cols
        if missing:
            errors.append(f"extracted_facts.csv missing columns: {sorted(missing)}")
            return [], errors
        rows = [r for r in reader if (r.get("metric_id") or "").strip()]
    return rows, errors


def ingest_year(ticker: str, year: int, *, dry_run: bool) -> dict:
    """Ingest one fiscal year directory. Returns a per-year summary dict."""
    year_dir = DOCS_DIR / ticker / str(year)
    summary: dict = {
        "fiscal_year": year, "status": "missing", "document_title": None,
        "file_hash": None, "facts_ingested": 0, "metrics": [],
        "missing_metrics": list(MIN_METRICS), "errors": [],
    }
    meta = load_metadata(year_dir)
    if meta is None:
        summary["errors"].append("metadata.json not found — document not placed")
        return summary

    summary["document_title"] = meta.get("title")
    pdf_path = year_dir / "source_document.pdf"
    actual_hash = compute_file_hash(pdf_path)
    summary["file_hash"] = actual_hash
    declared_hash = (meta.get("file_hash") or "").strip()
    if declared_hash and actual_hash and declared_hash != actual_hash:
        summary["errors"].append(
            f"file_hash mismatch: metadata={declared_hash[:12]}.. actual={actual_hash[:12]}.."
        )
        summary["status"] = "hash_mismatch"
        return summary
    if not pdf_path.exists():
        summary["errors"].append("source_document.pdf not found (metadata present)")

    rows, csv_errors = load_extracted_facts(year_dir)
    summary["errors"].extend(csv_errors)
    if csv_errors and not rows:
        summary["status"] = "extract_error"
        return summary

    ingested_metrics: list[str] = []
    if dry_run:
        for r in rows:
            ingested_metrics.append(canonical_metric(r["metric_id"]))
    else:
        from backend.database.official_documents import (
            OfficialDocumentInput,
            OfficialDocumentRegistry,
        )
        reg = OfficialDocumentRegistry()
        doc_id = reg.register_official_document(OfficialDocumentInput(
            ticker=ticker,
            company_name=meta.get("company_name"),
            source_type=meta.get("source_type", "audited_financial_statement"),
            title=meta.get("title", f"{ticker} {year} official document"),
            issuer=meta.get("issuer"),
            url=meta.get("url"),
            local_path=str(pdf_path) if pdf_path.exists() else meta.get("local_path"),
            published_date=meta.get("published_date") or None,
            fiscal_year=meta.get("fiscal_year", year),
            language=meta.get("language", "vi"),
            file_hash=actual_hash or declared_hash or None,
            status="extracted",
        ))
        for r in rows:
            metric = canonical_metric(r["metric_id"])
            try:
                value = float(str(r["value"]).replace(",", ""))
            except ValueError:
                summary["errors"].append(f"non-numeric value for {metric}: {r['value']!r}")
                continue
            period = f"{year}{r.get('period_type', 'FY') or 'FY'}"
            reg.add_official_observation(
                ticker=ticker, period=period, metric=metric, value=value,
                unit=r.get("unit", "vnd_bn"), official_document_id=doc_id,
                page_number=int(r["page_number"]) if str(r.get("page_number", "")).strip().isdigit() else None,
                table_name=r.get("table_name") or None,
                extracted_text=r.get("extracted_text") or None,
                extraction_method=r.get("extraction_method", "manual"),
            )
            ingested_metrics.append(metric)

    summary["facts_ingested"] = len(ingested_metrics)
    summary["metrics"] = sorted(set(ingested_metrics))
    summary["missing_metrics"] = [m for m in MIN_METRICS if m not in ingested_metrics]
    summary["status"] = "ingested" if ingested_metrics else "no_facts"
    return summary


def write_artifact(ticker: str, results: list[dict]) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out = ARTIFACT_DIR / f"{ticker}_official_document_ingestion.md"
    docs_ingested = sum(1 for r in results if r["status"] == "ingested")
    facts_total = sum(r["facts_ingested"] for r in results)
    missing_years = [r["fiscal_year"] for r in results if r["status"] == "missing"]
    lines = [
        f"# {ticker} Official Document Ingestion (Phase 3)",
        "",
        f"- Generated: {datetime.now(UTC).isoformat()}",
        f"- Documents ingested: **{docs_ingested}** / {len(results)} years",
        f"- Official facts extracted: **{facts_total}**",
        f"- Missing years (no document placed): {missing_years or 'none'}",
        "",
        "| FY | Status | Document | Facts | Missing metrics | Errors |",
        "|----|--------|----------|-------|-----------------|--------|",
    ]
    for r in results:
        miss = ", ".join(r["missing_metrics"][:4]) + ("…" if len(r["missing_metrics"]) > 4 else "")
        err = "; ".join(r["errors"][:2]) if r["errors"] else "—"
        title = (r["document_title"] or "—")[:40]
        lines.append(
            f"| {r['fiscal_year']} | {r['status']} | {title} | {r['facts_ingested']} | {miss or '—'} | {err} |"
        )
    lines += [
        "",
        "## File hashes",
        "",
    ]
    for r in results:
        lines.append(f"- {r['fiscal_year']}: `{r['file_hash'] or '(no document)'}`")
    lines += [
        "",
        "## Notes",
        "",
        "- This pipeline **never fabricates facts**. Years marked `missing` need an analyst to",
        "  place `metadata.json` + `extracted_facts.csv` (+ `source_document.pdf`) under",
        f"  `data/official_documents/{ticker}/<year>/`. See `_TEMPLATE/` for the schema.",
        "- Until official facts exist and are reconciled (Phase 4), final report export stays",
        "  blocked by the source-tier gate (Phase 2) — this is the intended behavior.",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest official documents for a ticker.")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--from-year", type=int, required=True, dest="from_year")
    parser.add_argument("--to-year", type=int, required=True, dest="to_year")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate + count without writing to the DB")
    args = parser.parse_args()
    ticker = args.ticker.strip().upper()

    results = [
        ingest_year(ticker, year, dry_run=args.dry_run)
        for year in range(args.from_year, args.to_year + 1)
    ]
    artifact = write_artifact(ticker, results)

    docs = sum(1 for r in results if r["status"] == "ingested")
    facts = sum(r["facts_ingested"] for r in results)
    print(f"[ingest_official_documents] {ticker}: {docs} document(s), {facts} fact(s) "
          f"{'(dry-run)' if args.dry_run else ''}")
    for r in results:
        print(f"  FY{r['fiscal_year']}: {r['status']} — {r['facts_ingested']} facts"
              + (f" — {r['errors'][0]}" if r["errors"] else ""))
    print(f"[ingest_official_documents] artifact: {artifact}")


if __name__ == "__main__":
    main()
