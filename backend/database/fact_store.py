from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, UTC
from typing import Any, Iterable

import pandas as pd
import psycopg2
from psycopg2.extras import Json, execute_values

from backend.database.config import connect_with_retry, require_database_url

@dataclass(frozen=True)
class FinancialFact:
    ticker: str
    fiscal_year: int
    fiscal_period: str
    line_item_code: str
    value: float
    unit: str
    currency: str
    source_id: str
    connector_version: str
    validation_status: str
    confidence: float | None
    effective_date: date | None
    ingested_at: datetime


@dataclass(frozen=True)
class PriceRow:
    ticker: str
    trade_date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    adjusted_close: float | None
    volume: int | None
    traded_value: float | None
    market_cap: float | None
    source_id: str | None
    ingested_at: datetime


class PostgresFactStore:
    """Storage layer for the VN pharma dataset. All SQL targets the 4-schema design."""

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = require_database_url(dsn)

    @contextmanager
    def conn(self):
        connection = connect_with_retry(self.dsn)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def upsert_price_rows(self, rows: Iterable[PriceRow]) -> int:
        # Dual-write shim: writes to fact.price_history (new) only.
        # fact.price_history will be dropped in migration 023.
        import os as _os
        from psycopg2.extras import execute_values as _execute_values
        payload = [
            (
                r.ticker,
                r.trade_date,
                r.open,
                r.high,
                r.low,
                r.close,
                r.adjusted_close,
                r.volume,
                r.traded_value,
                r.market_cap,
                r.ingested_at,
            )
            for r in rows
        ]
        if not payload:
            return 0
        dsn = _os.getenv("DATABASE_URL", self.dsn)
        with connect_with_retry(dsn) as conn:
            with conn.cursor() as cur:
                _execute_values(
                    cur,
                    """
                    INSERT INTO fact.price_history
                    (ticker, trade_date, open, high, low, close, adjusted_close,
                     volume, traded_value, market_cap, ingested_at)
                    VALUES %s
                    ON CONFLICT (ticker, trade_date) DO UPDATE
                    SET open           = EXCLUDED.open,
                        high           = EXCLUDED.high,
                        low            = EXCLUDED.low,
                        close          = EXCLUDED.close,
                        adjusted_close = EXCLUDED.adjusted_close,
                        volume         = EXCLUDED.volume,
                        traded_value   = EXCLUDED.traded_value,
                        market_cap     = EXCLUDED.market_cap,
                        ingested_at    = EXCLUDED.ingested_at
                    """,
                    payload,
                )
            conn.commit()
        return len(payload)

    def upsert_financial_facts(self, rows: Iterable[FinancialFact]) -> int:
        # FROZEN: removed legacy fact table is no longer the production write target.
        # Use backend.database.canonical.observation_dal.insert_observations() instead.
        raise DeprecationWarning(
            "removed legacy fact table is frozen. "
            "Write to ingest.observations via backend.database.canonical.observation_dal.insert_observations(). "
            "See docs/data_warehouse/final_schema_decision.md for the migration guide."
        )

    def upsert_company_snapshot(
        self,
        ticker: str,
        company_name_vi: str | None,
        company_name_en: str | None,
        exchange: str | None,
        sector: str | None,
        subsector: str | None,
        overview_json: Any = None,
        shareholders_json: Any = None,
        officers_json: Any = None,
    ) -> None:
        """Update ref.companies with the latest company profile data."""
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ref.companies
                    (ticker, company_name_vi, company_name_en, exchange, sector, subsector)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker) DO UPDATE
                    SET company_name_vi = COALESCE(EXCLUDED.company_name_vi, ref.companies.company_name_vi),
                        company_name_en = COALESCE(EXCLUDED.company_name_en, ref.companies.company_name_en),
                        exchange        = COALESCE(EXCLUDED.exchange,        ref.companies.exchange),
                        sector          = COALESCE(EXCLUDED.sector,          ref.companies.sector),
                        subsector       = COALESCE(EXCLUDED.subsector,       ref.companies.subsector),
                        updated_at      = NOW()
                    """,
                    (ticker, company_name_vi, company_name_en, exchange, sector, subsector),
                )

    # Backward-compatibility alias.
    def upsert_company_profile(
        self,
        ticker: str,
        company_name: str | None,
        exchange: str | None,
        segment: str | None,
        overview_json: Any = None,
        shareholders_json: Any = None,
        officers_json: Any = None,
    ) -> None:
        self.upsert_company_snapshot(
            ticker=ticker,
            company_name_vi=company_name,
            company_name_en=None,
            exchange=exchange,
            sector=segment,
            subsector=None,
            overview_json=overview_json,
            shareholders_json=shareholders_json,
            officers_json=officers_json,
        )

    def upsert_catalyst_events(self, rows: Iterable[dict[str, Any]]) -> int:
        payload = []
        for row in rows:
            payload.append(
                (
                    row["event_id"],
                    row["event_type"],
                    row["title"],
                    row.get("summary"),
                    row["occurred_at"],
                    row.get("effective_date"),
                    row.get("ticker") or row.get("company_ticker"),
                    row.get("materiality_hint"),
                    row.get("source_url"),
                    row.get("source_id"),
                    row.get("confidence"),
                    row.get("validation_status", "raw"),
                    row.get("ingested_at", datetime.now(UTC)),
                )
            )
        if not payload:
            return 0
        with self.conn() as connection:
            with connection.cursor() as cur:
                execute_values(
                    cur,
                    """
                    INSERT INTO fact.catalyst_events
                    (event_id, event_type, title, summary, occurred_at, effective_date, ticker,
                     materiality_hint, source_url, source_id, confidence, validation_status, ingested_at)
                    VALUES %s
                    ON CONFLICT (event_id) DO UPDATE
                    SET event_type        = EXCLUDED.event_type,
                        title             = EXCLUDED.title,
                        summary           = EXCLUDED.summary,
                        occurred_at       = EXCLUDED.occurred_at,
                        effective_date    = EXCLUDED.effective_date,
                        ticker            = EXCLUDED.ticker,
                        materiality_hint  = EXCLUDED.materiality_hint,
                        source_url        = EXCLUDED.source_url,
                        source_id         = EXCLUDED.source_id,
                        confidence        = EXCLUDED.confidence,
                        validation_status = EXCLUDED.validation_status,
                        ingested_at       = EXCLUDED.ingested_at
                    """,
                    payload,
                )
        return len(payload)

    def get_financial_facts_for_ticker(self, ticker: str) -> list[dict[str, Any]]:
        """Return all financial facts for a ticker with source provenance.

        Joins ingest.sources to include source_tier, source_uri, and source_title
        so that build_fact_table() can produce FactEntry objects with full lineage.
        """
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT f.fact_id AS id, f.metric AS line_item_code,
                           CAST(SUBSTRING(f.period, 1, 4) AS SMALLINT) AS fiscal_year,
                           'FY' AS fiscal_period,
                           f.value, f.unit, f.currency,
                           s.source_doc_id AS source_id, s.connector_version,
                           f.quality_status AS validation_status,
                           f.confidence, f.updated_at AS ingested_at,
                           s.source_tier, s.source_uri, s.source_title,
                           s.source_tier AS src_reliability_tier
                    FROM fact.canonical_facts f
                    LEFT JOIN ingest.observations o ON o.observation_id = f.selected_observation_id
                    LEFT JOIN ingest.source_documents s ON s.source_doc_id = o.source_doc_id
                    WHERE f.ticker = %s
                    ORDER BY f.period ASC, f.metric ASC
                    """,
                    (ticker,),
                )
                cols = [d.name for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_accepted_financial_facts(self, ticker: str) -> list[dict[str, Any]]:
        """Deprecated: use get_financial_facts_for_ticker() which reads fact.canonical_facts."""
        return self.get_financial_facts_for_ticker(ticker)

    def get_accepted_canonical_facts(self, ticker: str, canonical_version: str = "v_legacy") -> list[dict[str, Any]]:
        """Return canonical facts from fact.canonical_facts for FactEntry construction."""
        return self.get_financial_facts_for_ticker(ticker)

    def get_price_history(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        with self.conn() as connection:
            df = pd.read_sql_query(
                """
                SELECT trade_date, open, high, low, close, adjusted_close, volume, traded_value, market_cap
                FROM fact.price_history
                WHERE ticker = %s AND trade_date >= %s AND trade_date <= %s
                ORDER BY trade_date
                """,
                connection,
                params=(ticker, start, end),
            )
        return df

    def get_company_news(self, ticker: str, days_back: int = 30) -> list[dict[str, Any]]:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT title, occurred_at, COALESCE(summary, '') AS summary, source_url
                    FROM fact.catalyst_events
                    WHERE ticker = %s
                      AND occurred_at >= NOW() - (%s || ' day')::interval
                    ORDER BY occurred_at DESC
                    """,
                    (ticker, days_back),
                )
                rows = cur.fetchall()
        return [
            {"title": t, "publishedDate": oc.isoformat(), "text": sm, "url": url}
            for t, oc, sm, url in rows
        ]

    def query_financial_facts_wide(self, ticker: str) -> pd.DataFrame:
        """Return a wide pivot of all financial facts for a ticker (line_item_code Ã— period)."""
        with self.conn() as connection:
            frame = pd.read_sql_query(
                "SELECT metric AS line_item_code, CAST(SUBSTRING(period, 1, 4) AS SMALLINT) AS fiscal_year, "
                "'FY' AS fiscal_period, value FROM fact.production_facts WHERE ticker=%s",
                connection,
                params=(ticker,),
            )
        if frame.empty:
            return pd.DataFrame(columns=["metrics"])
        frame["period"] = frame["fiscal_year"].astype(str) + frame["fiscal_period"]
        pivot = frame.pivot_table(
            index="line_item_code", columns="period", values="value", aggfunc="last"
        ).reset_index()
        return pivot.rename(columns={"line_item_code": "metrics"})
