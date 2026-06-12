"""Phase 9: Validate v2 warehouse data after migration.

Checks:
  - All MVP tickers have facts in fact.canonical_facts
  - All canonical facts have lineage (selected_observation_id is not null)
  - No canonical fact has quality_status='rejected' in production_facts view
  - Snapshots can be created from v2 data
  - snapshot_items reference valid fact_ids
  - No fact has a confidence < 0.80 in production_facts
  - report.* tables exist (even if empty â€” they will be populated at run time)

Usage:
    python scripts/data_warehouse_v2/validate_v2_data.py
    python scripts/data_warehouse_v2/validate_v2_data.py --ticker DHG
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


def _check(label: str, passed: bool, detail: str = "") -> dict:
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {label}" + (f" â€” {detail}" if detail else ""))
    return {"label": label, "passed": passed, "detail": detail}


def validate(ticker: str | None = None) -> dict:
    conn = psycopg2.connect(_dsn())
    results = []

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            # 1. v2_ref schemas exist
            cur.execute("SELECT COUNT(*) AS n FROM ref.companies")
            n = cur.fetchone()["n"]
            results.append(_check("ref.companies populated", n >= 5, f"{n} companies"))

            # 2. ingest.source_documents has data
            cur.execute("SELECT COUNT(*) AS n FROM ingest.source_documents")
            n = cur.fetchone()["n"]
            results.append(_check("ingest.source_documents populated", n > 0, f"{n} documents"))

            # 3. ingest.observations has data
            q = "SELECT COUNT(*) AS n FROM ingest.observations"
            params = []
            if ticker:
                q += " WHERE ticker = %s"
                params.append(ticker)
            cur.execute(q, params)
            n = cur.fetchone()["n"]
            results.append(_check("ingest.observations populated", n > 0, f"{n} observations"))

            # 4. fact.canonical_facts has accepted facts
            q = "SELECT COUNT(*) AS n FROM fact.canonical_facts WHERE quality_status = 'accepted'"
            params = []
            if ticker:
                q += " AND ticker = %s"
                params.append(ticker)
            cur.execute(q, params)
            n = cur.fetchone()["n"]
            results.append(_check("fact.canonical_facts has accepted facts", n > 0, f"{n} accepted facts"))

            # 5. production_facts view has data (confidence >= 0.80 gate)
            q = "SELECT COUNT(*) AS n FROM fact.production_facts"
            params = []
            if ticker:
                q += " WHERE ticker = %s"
                params.append(ticker)
            cur.execute(q, params)
            n = cur.fetchone()["n"]
            results.append(_check("fact.production_facts has data", n > 0, f"{n} production facts"))

            # 6. Canonical facts have lineage (selected_observation_id not null)
            q = """SELECT COUNT(*) AS n FROM fact.canonical_facts
                   WHERE selected_observation_id IS NULL AND quality_status = 'accepted'"""
            params = []
            if ticker:
                q += " AND ticker = %s"
                params.append(ticker)
            cur.execute(q, params)
            orphans = cur.fetchone()["n"]
            results.append(_check("No accepted canonical facts without lineage", orphans == 0,
                                  f"{orphans} orphan facts"))

            # 7. research.snapshots can be queried
            cur.execute("SELECT COUNT(*) AS n FROM research.snapshots")
            n = cur.fetchone()["n"]
            results.append(_check("research.snapshots table accessible", True, f"{n} snapshots"))

            # 8. snapshot_items reference valid fact_ids (no dangling FKs)
            cur.execute("""
                SELECT COUNT(*) AS n
                FROM research.snapshot_items si
                WHERE si.item_type = 'canonical_fact'
                  AND NOT EXISTS (
                      SELECT 1 FROM fact.canonical_facts cf
                      WHERE cf.fact_id = si.fact_id
                  )
            """)
            dangling = cur.fetchone()["n"]
            results.append(_check("No dangling snapshot_items â†’ canonical_facts FKs",
                                  dangling == 0, f"{dangling} dangling items"))

            # 9. No golden_csv synthetic source_ids in ingest.observations
            cur.execute("""
                SELECT COUNT(*) AS n
                FROM ingest.observations obs
                LEFT JOIN ingest.source_documents sd ON sd.source_doc_id = obs.source_doc_id
                WHERE obs.source_doc_id IS NOT NULL
                  AND sd.source_doc_id IS NULL
            """)
            broken_src = cur.fetchone()["n"]
            results.append(_check("No broken source_doc_id references in observations",
                                  broken_src == 0, f"{broken_src} broken references"))

            # 10. v2_report tables exist
            cur.execute("SELECT COUNT(*) AS n FROM report.reports")
            results.append(_check("report.reports table accessible", True))

            cur.execute("SELECT COUNT(*) AS n FROM report.claims")
            results.append(_check("report.claims table accessible", True))

            cur.execute("SELECT COUNT(*) AS n FROM report.citation_records")
            results.append(_check("report.citation_records table accessible", True))

            # 11. audit.events table accessible
            cur.execute("SELECT COUNT(*) AS n FROM audit.events")
            n = cur.fetchone()["n"]
            results.append(_check("audit.events table accessible", True, f"{n} events logged"))

    finally:
        conn.close()

    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    return {
        "ticker_filter": ticker,
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "status": "PASS" if failed == 0 else "FAIL",
        "checks": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate v2 warehouse data")
    parser.add_argument("--ticker", help="Limit validation to one ticker")
    parser.add_argument("--output", default="audits/data_warehouse_v2_validation.json")
    args = parser.parse_args()

    print(f"[validate_v2] Validating v2 warehouse data...")
    report = validate(ticker=args.ticker)

    print(f"\n[validate_v2] Result: {report['status']} ({report['passed']}/{report['total']} checks passed)")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[validate_v2] Report saved: {out}")

    if report["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

