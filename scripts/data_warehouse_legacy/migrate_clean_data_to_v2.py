"""Phase 9: Migrate clean legacy data to v2 warehouse.

Runs the v2 SQL migrations (016â€“020) via the migration runner,
then promotes clean canonical facts from legacy_import to prod.

Also imports golden CSV files as governed observations (not silent overrides).

Usage:
    python scripts/data_warehouse_v2/migrate_clean_data_to_v2.py
    python scripts/data_warehouse_v2/migrate_clean_data_to_v2.py --ticker DHG
    python scripts/data_warehouse_v2/migrate_clean_data_to_v2.py --dry-run
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

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


GOLDEN_DIR = _ROOT / "config" / "dataset" / "golden" / "financials"
MVP_TICKERS = ["DHG", "IMP", "DMC", "TRA", "DBD"]


def _run_migrations(dry_run: bool = False) -> list[str]:
    """Apply v2 migrations (016â€“020) via the migration runner."""
    from backend.database.migrate import run_migrations
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise SystemExit("ERROR: DATABASE_URL not set")
    applied = run_migrations(dsn, dry_run=dry_run)
    return applied


def _import_golden_csv_for_ticker(ticker: str, dry_run: bool = False) -> dict:
    """Import golden CSV for a ticker as a governed source_document + observations."""
    from backend.database.canonical.source_dal import upsert_source_document
    from backend.database.canonical.observation_dal import insert_observations

    csv_path = GOLDEN_DIR / f"{ticker.upper()}.csv"
    prov_path = GOLDEN_DIR / f"{ticker.upper()}_golden_provenance.json"

    if not csv_path.exists():
        return {"ticker": ticker, "status": "no_csv", "rows": 0}

    provenance = {}
    if prov_path.exists():
        provenance = json.loads(prov_path.read_text(encoding="utf-8"))

    source_tier = int(provenance.get("source_tier", 3))
    publisher = provenance.get("publisher", "Golden CSV")
    source_urls = provenance.get("source_urls", [])
    checksum = hashlib.sha256(csv_path.read_bytes()).hexdigest()

    if not dry_run:
        source_doc_id = upsert_source_document(
            ticker=ticker,
            source_type="golden_csv",
            source_tier=source_tier,
            source_uri=source_urls[0] if source_urls else f"file://{csv_path}",
            checksum=checksum,
            source_title=f"{publisher} â€” Golden CSV",
            local_path=str(csv_path),
            fetch_status="verified",
            metadata_json={
                "provenance": provenance,
                "migrated_from": "config/dataset/golden/financials",
            },
        )
    else:
        source_doc_id = "DRY_RUN"

    # Load CSV rows as observations
    observations = []
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            period = row.get("period", "").strip()
            if not period.endswith("FY"):
                continue
            try:
                value = float(row["value"])
            except (ValueError, KeyError):
                continue

            observations.append({
                "ticker": ticker,
                "period": period,
                "metric": row["canonical_key"].strip(),
                "value": value,
                "unit": row.get("unit", "vnd_bn").strip(),
                "currency": row.get("currency", "VND").strip(),
                "source_doc_id": source_doc_id,
                "source_tier": source_tier,
                "extraction_method": "csv",
                "confidence": float(row.get("confidence") or 0.75),
            })

    if not dry_run and observations:
        inserted = insert_observations(observations)
    else:
        inserted = len(observations)

    return {"ticker": ticker, "status": "ok", "rows": inserted, "source_doc_id": source_doc_id}


def _promote_production_facts(ticker: str, dry_run: bool = False) -> dict:
    """Promote accepted v2 observations to prod canonical facts."""
    if dry_run:
        return {"ticker": ticker, "status": "dry_run", "promoted": 0}

    from backend.database.canonical.fact_promotion import promote_accepted_facts
    result = promote_accepted_facts(
        ticker=ticker,
        from_year=2021,
        to_year=2025,
        canonical_version="prod",
    )
    return {
        "ticker": ticker,
        "promoted": result.promoted,
        "skipped_low_confidence": result.skipped_low_confidence,
        "warnings": result.warnings,
        "errors": result.errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate clean legacy data to v2 warehouse")
    parser.add_argument("--ticker", help="Limit migration to one ticker")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done; no writes")
    parser.add_argument("--skip-migrations", action="store_true", help="Skip SQL migrations (assume already applied)")
    args = parser.parse_args()

    tickers = [args.ticker.upper()] if args.ticker else MVP_TICKERS
    dry_run = args.dry_run

    print(f"[migrate_to_v2] {'DRY RUN â€” ' if dry_run else ''}Starting migration")
    print(f"[migrate_to_v2] Tickers: {tickers}")

    # Step 1: Apply v2 SQL migrations
    if not args.skip_migrations:
        print("\n[migrate_to_v2] Step 1: Applying v2 SQL migrations...")
        applied = _run_migrations(dry_run=dry_run)
        print(f"[migrate_to_v2] Migrations applied: {applied or '(none pending)'}")
    else:
        print("[migrate_to_v2] Step 1: Skipped (--skip-migrations)")

    # Step 2: Import golden CSVs as governed sources
    print("\n[migrate_to_v2] Step 2: Importing golden CSV files as governed observations...")
    for ticker in tickers:
        result = _import_golden_csv_for_ticker(ticker, dry_run=dry_run)
        print(f"  {ticker}: {result['status']} â€” {result['rows']} observations")

    # Step 3: Promote to prod canonical facts
    print("\n[migrate_to_v2] Step 3: Promoting observations to prod canonical facts...")
    for ticker in tickers:
        result = _promote_production_facts(ticker, dry_run=dry_run)
        print(f"  {ticker}: promoted={result.get('promoted',0)} "
              f"needs_review={result.get('skipped_low_confidence',0)}")
        if result.get("errors"):
            for e in result["errors"]:
                print(f"    ERROR: {e}")

    print(f"\n[migrate_to_v2] {'DRY RUN complete' if dry_run else 'Migration complete'}")


if __name__ == "__main__":
    main()

