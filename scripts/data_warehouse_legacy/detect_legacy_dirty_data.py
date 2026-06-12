"""Phase 9: Detect legacy dirty data before migration to v2.

Scans legacy fact.financial_facts, ingest.sources, and golden CSV files
for duplicates, missing lineage, confidence issues, and other quality problems.

Usage:
    python scripts/data_warehouse_v2/detect_legacy_dirty_data.py
    python scripts/data_warehouse_v2/detect_legacy_dirty_data.py --ticker DHG
    python scripts/data_warehouse_v2/detect_legacy_dirty_data.py --output audits/dirty_data_report.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

import psycopg2
import psycopg2.extras

from backend.database.config import require_database_url


def _dsn() -> str:
    return require_database_url()


def detect_duplicate_facts(ticker: str | None, cur) -> list[dict]:
    """Detect rows in fact.financial_facts with duplicate (ticker, fiscal_year, fiscal_period, line_item_code)."""
    query = """
        SELECT ticker, fiscal_year, fiscal_period, line_item_code,
               COUNT(*) AS source_count,
               COUNT(DISTINCT source_id) AS distinct_sources,
               MIN(value) AS min_val,
               MAX(value) AS max_val,
               CASE WHEN MIN(value) = 0 THEN NULL
                    ELSE ABS(MAX(value) - MIN(value)) / ABS(MIN(value)) * 100
               END AS variance_pct
        FROM fact.financial_facts
        WHERE validation_status != 'rejected'
    """
    params = []
    if ticker:
        query += " AND ticker = %s"
        params.append(ticker)
    query += """
        GROUP BY ticker, fiscal_year, fiscal_period, line_item_code
        HAVING COUNT(DISTINCT source_id) > 1
        ORDER BY ticker, fiscal_year, line_item_code
    """
    cur.execute(query, params)
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def detect_missing_source_lineage(ticker: str | None, cur) -> list[dict]:
    """Detect financial_facts rows with no matching ingest.sources record."""
    query = """
        SELECT f.ticker, f.fiscal_year, f.fiscal_period, f.line_item_code,
               f.source_id, f.validation_status, f.confidence
        FROM fact.financial_facts f
        LEFT JOIN ingest.sources s ON f.source_id = s.source_id
        WHERE s.source_id IS NULL
    """
    params = []
    if ticker:
        query += " AND f.ticker = %s"
        params.append(ticker)
    cur.execute(query, params)
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def detect_golden_csv_synthetic_ids(ticker: str | None, cur) -> list[dict]:
    """Detect synthetic source_ids created by the golden CSV inject in build_facts.py."""
    query = """
        SELECT f.ticker, f.fiscal_year, f.source_id, COUNT(*) AS fact_count
        FROM fact.financial_facts f
        WHERE f.source_id LIKE 'golden_csv_%'
    """
    params = []
    if ticker:
        query += " AND f.ticker = %s"
        params.append(ticker)
    query += " GROUP BY f.ticker, f.fiscal_year, f.source_id ORDER BY f.ticker, f.fiscal_year"
    cur.execute(query, params)
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def detect_low_confidence_accepted_facts(ticker: str | None, cur) -> list[dict]:
    """Detect accepted facts with confidence < 0.80."""
    query = """
        SELECT ticker, fiscal_year, fiscal_period, line_item_code,
               confidence, source_id, validation_status
        FROM fact.financial_facts
        WHERE validation_status = 'accepted'
          AND confidence IS NOT NULL
          AND confidence < 0.80
    """
    params = []
    if ticker:
        query += " AND ticker = %s"
        params.append(ticker)
    query += " ORDER BY ticker, fiscal_year, line_item_code"
    cur.execute(query, params)
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def detect_orphan_snapshot_items(cur) -> list[dict]:
    """Detect snapshot items referencing financial_facts rows that don't exist."""
    cur.execute(
        """
        SELECT si.snapshot_id, si.item_id, si.item_type
        FROM research.snapshot_items si
        WHERE si.item_type = 'financial_fact'
          AND NOT EXISTS (
              SELECT 1 FROM fact.financial_facts ff
              WHERE ff.id = si.item_id::BIGINT
          )
        """
    )
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def detect_corrupt_company_names(cur) -> list[dict]:
    """Detect company names still containing '?' from the T-SQL N'' encoding bug."""
    cur.execute(
        """
        SELECT ticker, company_name_vi, company_name_en
        FROM ref.companies
        WHERE company_name_vi LIKE '%?%' OR company_name_en LIKE '%?%'
        """
    )
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def detect_stale_facts(ticker: str | None, cur) -> list[dict]:
    """Detect facts where ingested_at is more than 18 months ago for recent fiscal years."""
    query = """
        SELECT ticker, fiscal_year, fiscal_period, line_item_code,
               ingested_at,
               NOW() - ingested_at AS age
        FROM fact.financial_facts
        WHERE fiscal_year >= 2023
          AND ingested_at < NOW() - INTERVAL '18 months'
          AND validation_status = 'accepted'
    """
    params = []
    if ticker:
        query += " AND ticker = %s"
        params.append(ticker)
    cur.execute(query, params)
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def run_detection(ticker: str | None = None) -> dict:
    conn = psycopg2.connect(_dsn())
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            results = {
                "ticker_filter": ticker,
                "duplicate_facts": detect_duplicate_facts(ticker, cur),
                "missing_source_lineage": detect_missing_source_lineage(ticker, cur),
                "golden_csv_synthetic_ids": detect_golden_csv_synthetic_ids(ticker, cur),
                "low_confidence_accepted": detect_low_confidence_accepted_facts(ticker, cur),
                "orphan_snapshot_items": detect_orphan_snapshot_items(cur),
                "corrupt_company_names": detect_corrupt_company_names(cur),
                "stale_facts": detect_stale_facts(ticker, cur),
            }
    finally:
        conn.close()

    # Summary
    results["summary"] = {
        k: len(v) for k, v in results.items()
        if isinstance(v, list)
    }
    total_issues = sum(results["summary"].values())
    results["total_issues"] = total_issues
    results["status"] = "clean" if total_issues == 0 else "issues_found"
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect legacy dirty data before v2 migration")
    parser.add_argument("--ticker", help="Limit scan to one ticker")
    parser.add_argument("--output", default="audits/data_warehouse_v2_dirty_data.json",
                        help="Output JSON path")
    args = parser.parse_args()

    print(f"[detect_dirty_data] Scanning legacy warehouse...")
    results = run_detection(ticker=args.ticker)

    for key, count in results["summary"].items():
        status = "OK" if count == 0 else f"ISSUES: {count}"
        print(f"  {key:<40} {status}")

    print(f"\n[detect_dirty_data] Total issues: {results['total_issues']}")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"[detect_dirty_data] Report saved: {out}")


if __name__ == "__main__":
    main()
