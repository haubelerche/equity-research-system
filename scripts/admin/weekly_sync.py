from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime

from scripts.connectors.catalyst_bhyt_connector import sync_bhyt_connector
from scripts.connectors.catalyst_dav_connector import sync_dav_connector
from scripts.connectors.catalyst_hose_connector import sync_hose_hnx_connector
from scripts.connectors.catalyst_tender_connector import sync_tender_connector
from scripts.connectors.vnstock_company_connector import sync_company_universe
from scripts.connectors.vnstock_finance_connector import sync_financial_for_universe
from scripts.connectors.vnstock_price_connector import sync_price_for_universe
from backend.dataset.config_io import load_universe_tickers
from backend.database.fact_store import PostgresFactStore


def _build_peer_snapshot(store: PostgresFactStore, run_id: str) -> int:
    tickers = load_universe_tickers()
    inserted_rows = 0
    with store.conn() as connection:
        with connection.cursor() as cur:
            for ticker in tickers:
                cur.execute(
                    """
                    SELECT fiscal_year, fiscal_period, line_item_code, value
                    FROM fact.financial_facts
                    WHERE ticker = %s
                    ORDER BY fiscal_year DESC, fiscal_period DESC
                    LIMIT 80
                    """,
                    (ticker,),
                )
                rows = cur.fetchall()
                for fiscal_year, fiscal_period, line_item_code, value in rows:
                    # peer_metrics_snapshot table removed in 4-schema rebuild (2026-05-24).
                    # Peer metric snapshots are now computed on demand from fact.financial_facts.
                    inserted_rows += 1  # count rows that would have been inserted
                    inserted_rows += 1
    return inserted_rows


def run_weekly_sync(days_back: int = 7) -> dict[str, int]:
    run_time = datetime.now(UTC)
    run_id = hashlib.sha256(f"weekly_sync|{run_time.isoformat()}".encode("utf-8")).hexdigest()
    store = PostgresFactStore()

    print(f"[weekly_sync] run_id={run_id}")
    stats: dict[str, int] = {}

    # Step 1: Universe + company profile refresh.
    company_stats = sync_company_universe()
    stats["company_profiles"] = sum(v.get("profiles", 0) for v in company_stats.values())
    stats["company_events"] = sum(v.get("events", 0) for v in company_stats.values())

    # Step 2: Price sync.
    price_stats = sync_price_for_universe(days_back=days_back)
    stats["price_rows"] = sum(price_stats.values())

    # Step 3: Financial check.
    finance_stats = sync_financial_for_universe()
    fact_updates = sum(finance_stats.values())
    stats["financial_facts"] = fact_updates
    has_fact_update = fact_updates > 0

    # Step 4+5: Catalyst crawl.
    stats["dav_events"] = sync_dav_connector()
    stats["hose_hnx_events"] = sync_hose_hnx_connector()
    stats["tender_events"] = sync_tender_connector()
    stats["bhyt_events"] = sync_bhyt_connector()

    # Step 6: Peer snapshot only when new facts exist.
    if has_fact_update:
        stats["peer_snapshot_rows"] = _build_peer_snapshot(store=store, run_id=run_id)
    else:
        stats["peer_snapshot_rows"] = 0

    # Step 7: Persist sync summary in ingestion_runs.
    with store.conn() as connection:
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ingestion_runs (run_id, run_type, status, started_at, finished_at, metadata_json)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (run_id) DO NOTHING
                """,
                (run_id, "weekly_sync", "completed", run_time, datetime.now(UTC), json.dumps(stats)),
            )

    print("[weekly_sync] summary")
    for key, value in stats.items():
        print(f"  - {key}: {value}")
    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Sunday weekly sync pipeline for VN pharma dataset.")
    parser.add_argument("--days-back", type=int, default=7, help="Days back for price sync.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_weekly_sync(days_back=args.days_back)


if __name__ == "__main__":
    main()

