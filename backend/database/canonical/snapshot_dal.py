"""v2 DAL: research.snapshots â€” frozen canonical fact snapshots.

Write permission: build_facts.py (via this module).
Read permission: valuation engine, report generation.

CRITICAL FIX over legacy snapshot.py:
  - snapshot_items.fact_id is a proper FK to fact.canonical_facts.fact_id (VARCHAR)
  - NOT a TEXT cast of a removed BIGSERIAL fact identifier
  - load_snapshot_facts() joins fact.canonical_facts
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any

import psycopg2.extras

from backend.database.canonical.connection import get_conn
from backend.database.config import require_database_url


def _snapshot_id(
    ticker: str, from_year: int, to_year: int, as_of: date, canonical_version: str
) -> str:
    raw = f"{ticker}_{from_year}_{to_year}_{as_of.isoformat()}_{canonical_version}"
    return f"v2snap_{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


def create_snapshot(
    ticker: str,
    from_year: int,
    to_year: int,
    canonical_version: str | None = None,
    created_by: str = "build_facts",
) -> dict[str, Any]:
    """Freeze v2 canonical facts for ticker/year-range into research.snapshots.

    Idempotent: re-running on the same day updates facts_count and items.
    Uses two transactions to stay within Supabase pooler limits.

    Returns the snapshot header dict.
    """
    as_of = datetime.now(UTC).date()
    snapshot_version = canonical_version or "production_winners"
    snapshot_id = _snapshot_id(ticker, from_year, to_year, as_of, snapshot_version)

    conn = get_conn.__wrapped__() if hasattr(get_conn, "__wrapped__") else None

    import os
    from backend.database.config import connect_with_retry
    dsn = require_database_url()
    conn = connect_with_retry(dsn)

    try:
        # Tx 1: load canonical facts and upsert snapshot header
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                WITH ranked_facts AS (
                    SELECT pf.*,
                           ROW_NUMBER() OVER (
                               PARTITION BY pf.ticker, pf.period, pf.metric
                               ORDER BY pf.source_tier ASC NULLS LAST,
                                        pf.confidence DESC NULLS LAST,
                                        pf.updated_at DESC,
                                        pf.fact_id DESC
                           ) AS winner_rank
                    FROM fact.production_facts pf
                    WHERE pf.ticker = %s
                      AND (%s IS NULL OR pf.canonical_version = %s)
                      AND CAST(SUBSTRING(pf.period, 1, 4) AS SMALLINT) BETWEEN %s AND %s
                )
                SELECT fact_id, period, metric
                FROM ranked_facts
                WHERE winner_rank = 1
                ORDER BY period, metric
                """,
                (ticker, canonical_version, canonical_version, from_year, to_year),
            )
            rows: list[dict] = [dict(r) for r in cur.fetchall()]

        periods = sorted({r["period"] for r in rows})

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO research.snapshots
                    (snapshot_id, ticker, canonical_version, as_of_date, from_year, to_year,
                     periods_json, facts_count, status, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, 'active', %s)
                ON CONFLICT (snapshot_id) DO UPDATE
                SET facts_count       = EXCLUDED.facts_count,
                    periods_json      = EXCLUDED.periods_json,
                    status            = 'active'
                """,
                (
                    snapshot_id, ticker, snapshot_version, as_of, from_year, to_year,
                    json.dumps(periods), len(rows), created_by,
                ),
            )
        conn.commit()

        # Tx 2: batch-upsert snapshot items (using canonical fact_id FK)
        if rows:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM research.snapshot_items WHERE snapshot_id = %s AND item_type = 'canonical_fact'",
                    (snapshot_id,),
                )
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO research.snapshot_items
                        (snapshot_id, item_type, fact_id, included_reason)
                    VALUES %s
                    ON CONFLICT (snapshot_id, item_type,
                        COALESCE(fact_id, ''), COALESCE(item_ref, '')) DO NOTHING
                    """,
                    [
                        (snapshot_id, "canonical_fact", r["fact_id"], "production_fact_fy")
                        for r in rows
                    ],
                    page_size=200,
                )
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "snapshot_id": snapshot_id,
        "ticker": ticker,
        "canonical_version": snapshot_version,
        "as_of_date": as_of.isoformat(),
        "from_year": from_year,
        "to_year": to_year,
        "periods": periods,
        "facts_count": len(rows),
        "status": "active",
    }


def load_snapshot_facts(snapshot_id: str) -> list[dict[str, Any]]:
    """Load all canonical facts belonging to a snapshot.

    Returns fact dicts with the same shape as fact_store.get_accepted_financial_facts()
    so existing normalizer code can process them without changes.

    CRITICAL: Joins fact.canonical_facts.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    cf.fact_id         AS id,
                    cf.ticker,
                    CAST(SUBSTRING(cf.period, 1, 4) AS SMALLINT) AS fiscal_year,
                    'FY'               AS fiscal_period,
                    cf.metric          AS line_item_code,
                    cf.value,
                    cf.unit,
                    cf.currency,
                    cf.confidence,
                    cf.source_tier,
                    cf.reconciliation_status,
                    sd.source_doc_id   AS source_id,
                    sd.source_uri,
                    sd.source_title,
                    sd.connector_version,
                    cf.updated_at      AS ingested_at
                FROM research.snapshot_items si
                JOIN fact.canonical_facts cf ON cf.fact_id = si.fact_id
                LEFT JOIN ingest.observations obs ON obs.observation_id = cf.selected_observation_id
                LEFT JOIN ingest.source_documents sd ON sd.source_doc_id = obs.source_doc_id
                WHERE si.snapshot_id = %s
                  AND si.item_type   = 'canonical_fact'
                ORDER BY cf.period ASC, cf.metric ASC
                """,
                (snapshot_id,),
            )
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_latest_snapshot(
    ticker: str,
    from_year: int,
    to_year: int,
    canonical_version: str = "prod",
) -> dict[str, Any] | None:
    """Return the most recent active snapshot for a ticker/year-range, or None."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT snapshot_id, ticker, canonical_version, as_of_date,
                       from_year, to_year, periods_json, facts_count, status, created_at
                FROM research.snapshots
                WHERE ticker            = %s
                  AND from_year         = %s
                  AND to_year           = %s
                  AND canonical_version = %s
                  AND status            = 'active'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (ticker, from_year, to_year, canonical_version),
            )
            row = cur.fetchone()
            if row is None:
                return None
            cols = [d.name for d in cur.description]
            d = dict(zip(cols, row))
            d["as_of_date"] = d["as_of_date"].isoformat() if d["as_of_date"] else None
            d["created_at"] = d["created_at"].isoformat() if d["created_at"] else None
            return d

