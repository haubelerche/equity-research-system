"""v2 DAL: fact.canonical_facts â€” production canonical fact store.

Read permission: snapshot creation, valuation (via snapshot), report (via snapshot).
Write permission: fact_promotion.py ONLY.

Valuation and report code must never read directly from canonical_facts.
They must read from a frozen snapshot via snapshot_dal.load_snapshot_facts().
"""
from __future__ import annotations

import hashlib
from typing import Any

from backend.database.canonical.connection import get_conn


def compute_fact_id(ticker: str, period: str, metric: str, canonical_version: str) -> str:
    """Deterministic fact_id = SHA256(ticker|period|metric|canonical_version)."""
    raw = f"{ticker}|{period}|{metric}|{canonical_version}"
    return hashlib.sha256(raw.encode()).hexdigest()


def upsert_canonical_fact(
    ticker: str,
    period: str,
    metric: str,
    value: float,
    unit: str,
    canonical_version: str = "prod",
    currency: str = "VND",
    selected_observation_id: int | None = None,
    selection_policy: str = "highest_tier_then_confidence",
    confidence: float | None = None,
    quality_status: str = "accepted",
    source_tier: int | None = None,
    official_document_id: str | None = None,
    reconciliation_status: str = "missing_official",
) -> str:
    """Insert or update a canonical fact. Returns fact_id.

    This function is called ONLY by fact_promotion.py.
    Never call from connectors, LLM, or report code.
    """
    fact_id = compute_fact_id(ticker, period, metric, canonical_version)
    period_type = "Q" if not period.endswith("FY") else "FY"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO fact.canonical_facts (
                    fact_id, ticker, period, period_type, canonical_version,
                    metric, value, unit, currency,
                    selected_observation_id, selection_policy, confidence,
                    quality_status, source_tier,
                    official_document_id, reconciliation_status,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (ticker, period, metric, canonical_version) DO UPDATE
                SET value                   = EXCLUDED.value,
                    unit                    = EXCLUDED.unit,
                    selected_observation_id = EXCLUDED.selected_observation_id,
                    confidence              = EXCLUDED.confidence,
                    quality_status          = EXCLUDED.quality_status,
                    source_tier             = EXCLUDED.source_tier,
                    official_document_id    = EXCLUDED.official_document_id,
                    reconciliation_status   = EXCLUDED.reconciliation_status,
                    updated_at              = NOW()
                """,
                (
                    fact_id, ticker, period, period_type, canonical_version,
                    metric, value, unit, currency,
                    selected_observation_id, selection_policy, confidence,
                    quality_status, source_tier,
                    official_document_id, reconciliation_status,
                ),
            )
    return fact_id


def get_production_facts(
    ticker: str,
    from_year: int | None = None,
    to_year: int | None = None,
    canonical_version: str | None = None,
) -> list[dict[str, Any]]:
    """Return FY production facts for a ticker. Reads from fact.production_facts view.

    This is the only approved way to read canonical facts for valuation.
    Always use snapshot_dal for a frozen run; use this only for ad-hoc queries.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            query = """
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
                )
                SELECT rf.fact_id, rf.ticker, rf.period, rf.metric, rf.value,
                       rf.unit, rf.currency, rf.confidence, rf.source_tier,
                       'accepted'::text AS quality_status,
                       rf.reconciliation_status, rf.canonical_version,
                       rf.official_document_id, rf.updated_at,
                       sd.source_doc_id, sd.source_uri, sd.source_title,
                       COALESCE(sd.connector_version, rf.canonical_version) AS ingestion_version
                FROM ranked_facts rf
                LEFT JOIN ingest.observations obs
                  ON obs.observation_id = rf.selected_observation_id
                LEFT JOIN ingest.source_documents sd
                  ON sd.source_doc_id = COALESCE(rf.official_document_id, obs.source_doc_id)
                WHERE rf.winner_rank = 1
            """
            params: list[Any] = [ticker, canonical_version, canonical_version]
            if from_year:
                query += " AND CAST(SUBSTRING(rf.period, 1, 4) AS SMALLINT) >= %s"
                params.append(from_year)
            if to_year:
                query += " AND CAST(SUBSTRING(rf.period, 1, 4) AS SMALLINT) <= %s"
                params.append(to_year)
            query += " ORDER BY rf.period ASC, rf.metric ASC"
            cur.execute(query, params)
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_facts_needing_review(ticker: str) -> list[dict[str, Any]]:
    """Return canonical facts with quality_status='needs_review' for HITL queue."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT fact_id, ticker, period, metric, value, confidence,
                       source_tier, reconciliation_status, created_at
                FROM fact.canonical_facts
                WHERE ticker = %s AND quality_status = 'needs_review'
                ORDER BY period DESC, metric ASC
                """,
                (ticker,),
            )
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

