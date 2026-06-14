"""Ingest accountable CafeF tier-2 audited-statement evidence into document_chunks.

The pipeline (not a human) fetches the figures: CafeFReportConnector hits the documented
``FinanceReport.ashx`` endpoint, and every chunk records its exact ``api_url`` + audited
flag for provenance. This is tier-2 evidence (parsed aggregator), not the original PDF.

Usage:
    python scripts/ingest_cafef_report.py --ticker DBD --from-year 2022 --to-year 2025
    python scripts/ingest_cafef_report.py --ticker DBD --from-year 2022 --to-year 2025 --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
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

from backend.database.canonical.source_dal import upsert_source_document
from backend.database.config import connect_with_retry, require_database_url
from backend.documents.connectors.cafef_report_connector import (
    STATEMENT_TYPES,
    CafeFReportConnector,
)
from scripts.build_index import _upsert_page_chunks

_STATEMENT_TITLE = {
    "income_statement": "KQKD",
    "balance_sheet": "CĐKT",
}


def ingest(ticker: str, from_year: int, to_year: int, dry_run: bool = False) -> dict:
    ticker = ticker.strip().upper()
    connector = CafeFReportConnector()
    evidence = connector.fetch_evidence(ticker, from_year, to_year)
    if not evidence:
        return {"ticker": ticker, "status": "no_evidence", "sources": 0, "chunks": 0}

    # Group by statement_type: one source_document per statement (its api_url),
    # one chunk per fiscal year underneath it.
    by_statement: dict[str, list] = {}
    for rec in evidence:
        by_statement.setdefault(rec.statement_type, []).append(rec)

    summary = {"ticker": ticker, "status": "ok", "sources": 0, "chunks": 0, "detail": []}
    if dry_run:
        for statement_type, recs in by_statement.items():
            summary["sources"] += 1
            summary["chunks"] += len(recs)
            summary["detail"].append({
                "statement_type": statement_type,
                "years": sorted(r.fiscal_year for r in recs),
                "api_url": recs[0].api_url,
                "audited": all(r.audited for r in recs),
            })
        summary["status"] = "dry_run"
        return summary

    conn = connect_with_retry(require_database_url())
    try:
        for statement_type, recs in by_statement.items():
            recs.sort(key=lambda r: r.fiscal_year)
            api_url = recs[0].api_url
            combined = "\n\n".join(r.evidence_text for r in recs)
            checksum = hashlib.sha256(f"{api_url}|{combined}".encode()).hexdigest()
            source_id = upsert_source_document(
                ticker=ticker,
                source_type="cafef_financial",
                source_tier=2,
                source_uri=api_url,
                checksum=checksum,
                source_title=(
                    f"BCTC {ticker} {_STATEMENT_TITLE.get(statement_type, statement_type)} "
                    f"- CafeF (Đã kiểm toán)"
                ),
                fiscal_period="FY",
                language="vi",
                connector_name=connector.source_name,
                connector_version="1.0",
                metadata={
                    "statement_type": statement_type,
                    "audited": all(r.audited for r in recs),
                    "api_url": api_url,
                    "years": sorted(r.fiscal_year for r in recs),
                },
            )
            # page_number is an ordinal here (structured data has no real pages); it
            # preserves chunk order + idempotency. Citation/eval match is term-based.
            page_chunks = []
            for idx, rec in enumerate(recs, start=1):
                page_chunks.append((
                    f"{_STATEMENT_TITLE.get(statement_type, statement_type)} {rec.fiscal_year} (CafeF)",
                    rec.evidence_text,
                    rec.fiscal_year,
                    idx,
                    {
                        "extraction_method": "cafef_structured",
                        "statement_type": statement_type,
                        "audited": rec.audited,
                        "api_url": rec.api_url,
                        "source_tier": rec.source_tier,
                    },
                ))
            inserted = _upsert_page_chunks(conn, source_id, ticker, page_chunks)
            conn.commit()
            summary["sources"] += 1
            summary["chunks"] += len(page_chunks)
            summary["detail"].append({
                "statement_type": statement_type,
                "source_id": source_id,
                "years": sorted(r.fiscal_year for r in recs),
                "newly_inserted": inserted,
            })
    finally:
        conn.close()
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--from-year", type=int, required=True, dest="from_year")
    parser.add_argument("--to-year", type=int, required=True, dest="to_year")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = ingest(args.ticker, args.from_year, args.to_year, dry_run=args.dry_run)
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in ("ok", "dry_run") else 1


if __name__ == "__main__":
    raise SystemExit(main())
