"""v2 DAL: ingest.observations â€” raw fact candidates before winner selection.

Write permission: connector DAL, fact_promotion.py.
Read permission: fact_promotion.py ONLY â€” not valuation, not report.

LLM and report modules must NEVER import this module for writing.
"""
from __future__ import annotations

from typing import Any, Iterable

import psycopg2.extras

from backend.database.canonical.connection import get_conn


def insert_observations(rows: Iterable[dict[str, Any]]) -> int:
    """Batch-insert observations. Silently deduplicates on (ticker, period, metric, source_doc_id).

    Each row dict must contain: ticker, period, metric, value, unit, currency,
    source_tier, extraction_method.
    Optional: source_doc_id, confidence, page_number, table_name, extracted_text.
    """
    payload = [
        (
            r["ticker"],
            r["period"],
            "Q" if not r["period"].endswith("FY") else "FY",
            r["metric"],
            r["value"],
            r["unit"],
            r.get("currency", "VND"),
            r.get("source_doc_id"),
            r.get("source_tier", 3),
            r.get("extraction_method", "api_structured"),
            r.get("confidence"),
            r.get("page_number"),
            r.get("table_name"),
            r.get("extracted_text"),
        )
        for r in rows
    ]
    if not payload:
        return 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO ingest.observations (
                    ticker, period, period_type, metric, value, unit, currency,
                    source_doc_id, source_tier, extraction_method, confidence,
                    page_number, table_name, extracted_text
                )
                VALUES %s
                ON CONFLICT (ticker, period, metric, source_doc_id) DO NOTHING
                """,
                payload,
            )
    return len(payload)


def get_observations_for_ticker(
    ticker: str,
    period: str | None = None,
    metric: str | None = None,
    max_tier: int = 3,
) -> list[dict[str, Any]]:
    """Return observations for a ticker, optionally filtered.

    Used by fact_promotion.py to select the canonical winner.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT
                    observation_id, ticker, period, period_type, metric,
                    value, unit, currency, source_doc_id, source_tier,
                    extraction_method, confidence, created_at
                FROM ingest.observations
                WHERE ticker = %s
                  AND source_tier <= %s
            """
            params: list[Any] = [ticker, max_tier]
            if period:
                query += " AND period = %s"
                params.append(period)
            if metric:
                query += " AND metric = %s"
                params.append(metric)
            query += " ORDER BY period ASC, metric ASC, source_tier ASC, confidence DESC NULLS LAST"
            cur.execute(query, params)
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

