"""Research snapshot service.

Creates and loads immutable snapshots of accepted financial facts so that
valuation and reporting always read from a frozen dataset, not the live DB.

Usage:
    snap = create_snapshot("DHG", 2021, 2025)
    facts = load_snapshot_facts(snap["snapshot_id"])
"""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any

import psycopg2
import psycopg2.extras


def _dsn() -> str:
    return os.getenv("DATABASE_URL", "postgresql://maer:maer_local@localhost:5432/maer_dev")


@contextmanager
def _conn():
    conn = psycopg2.connect(_dsn())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _snapshot_id(ticker: str, from_year: int, to_year: int, as_of: date) -> str:
    raw = f"{ticker}_{from_year}_{to_year}_{as_of.isoformat()}"
    return f"snap_{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


def create_snapshot(
    ticker: str,
    from_year: int,
    to_year: int,
    created_by: str = "system",
) -> dict[str, Any]:
    """Freeze accepted FY facts for ticker/year-range into research.snapshots.

    Idempotent: re-running on the same day updates the facts_count and items
    but reuses the same snapshot_id.

    Uses two small transactions (header + items) to stay within Supabase
    pooler statement_timeout limits.

    Returns the snapshot header dict.
    """
    as_of = datetime.now(UTC).date()
    snapshot_id = _snapshot_id(ticker, from_year, to_year, as_of)

    # Open one connection; use two explicit commits to keep each Tx short
    conn = psycopg2.connect(_dsn())
    try:
        # ── Tx 1: load facts and upsert snapshot header ────────────────────
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, fiscal_year, fiscal_period, line_item_code, source_id
                FROM fact.accepted_financial_facts
                WHERE ticker      = %s
                  AND fiscal_year >= %s
                  AND fiscal_year <= %s
                ORDER BY fiscal_year, line_item_code
                """,
                (ticker, from_year, to_year),
            )
            # Convert to plain dicts immediately so cursor can be closed
            rows: list[dict] = [dict(r) for r in cur.fetchall()]

        periods = sorted({f"{r['fiscal_year']}FY" for r in rows})

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO research.snapshots
                    (snapshot_id, ticker, as_of_date, from_year, to_year,
                     periods_json, facts_count, status, created_by)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, 'active', %s)
                ON CONFLICT (snapshot_id) DO UPDATE
                SET facts_count  = EXCLUDED.facts_count,
                    periods_json = EXCLUDED.periods_json,
                    status       = 'active'
                """,
                (
                    snapshot_id, ticker, as_of, from_year, to_year,
                    json.dumps(periods), len(rows), created_by,
                ),
            )
        conn.commit()  # Commit Tx 1 before items

        # ── Tx 2: batch-upsert snapshot items ──────────────────────────────
        if rows:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM research.snapshot_items WHERE snapshot_id = %s AND item_type = 'financial_fact'",
                    (snapshot_id,),
                )
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO research.snapshot_items
                        (snapshot_id, item_type, item_id, source_id, included_reason)
                    VALUES %s
                    ON CONFLICT (snapshot_id, item_type, item_id) DO NOTHING
                    """,
                    [
                        (snapshot_id, "financial_fact", str(r["id"]), r["source_id"], "accepted_fy_fact")
                        for r in rows
                    ],
                    page_size=50,
                )
            conn.commit()  # Commit Tx 2
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "snapshot_id": snapshot_id,
        "ticker": ticker,
        "as_of_date": as_of.isoformat(),
        "from_year": from_year,
        "to_year": to_year,
        "periods": periods,
        "facts_count": len(rows),
        "status": "active",
    }


def load_snapshot_facts(snapshot_id: str) -> list[dict[str, Any]]:
    """Load all financial facts belonging to a snapshot.

    Returns fact dicts with the same shape as PostgresFactStore.get_financial_facts_for_ticker()
    so existing normalizer code can process them unchanged.
    """
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT
                    ff.id, ff.ticker, ff.fiscal_year, ff.fiscal_period,
                    ff.line_item_code, ff.value, ff.unit, ff.currency,
                    ff.source_id, ff.connector_version,
                    ff.validation_status, ff.confidence, ff.ingested_at,
                    s.source_title   AS src_title,
                    s.source_uri     AS src_uri,
                    s.source_type    AS src_type,
                    s.published_at   AS src_published_at,
                    s.reliability_tier AS src_reliability_tier
                FROM research.snapshot_items si
                JOIN fact.financial_facts ff ON ff.id = si.item_id::BIGINT
                LEFT JOIN ingest.sources s ON s.source_id = ff.source_id
                WHERE si.snapshot_id = %s
                  AND si.item_type   = 'financial_fact'
                ORDER BY ff.fiscal_year, ff.line_item_code
                """,
                (snapshot_id,),
            )
            return [dict(r) for r in cur.fetchall()]


def get_latest_snapshot(ticker: str, from_year: int, to_year: int) -> dict[str, Any] | None:
    """Return the most recent active snapshot for a ticker/year-range, or None."""
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT snapshot_id, ticker, as_of_date, from_year, to_year,
                       periods_json, facts_count, status, created_at
                FROM research.snapshots
                WHERE ticker    = %s
                  AND from_year = %s
                  AND to_year   = %s
                  AND status    = 'active'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (ticker, from_year, to_year),
            )
            row = cur.fetchone()
            if row is None:
                return None
            d = dict(row)
            d["as_of_date"] = d["as_of_date"].isoformat() if d["as_of_date"] else None
            d["created_at"] = d["created_at"].isoformat() if d["created_at"] else None
            return d
