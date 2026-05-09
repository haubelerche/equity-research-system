from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, UTC
from decimal import Decimal
from typing import Any, Iterable

import pandas as pd
import psycopg2
from psycopg2.extras import Json, execute_values


@dataclass(frozen=True)
class FinancialFact:
    company_ticker: str
    fiscal_year: int
    fiscal_period: str
    taxonomy_key: str
    value: float
    unit: str
    currency: str
    source_version_id: str
    parser_version: str
    validation_status: str
    confidence: float | None
    effective_date: date | None
    ingested_at: datetime


@dataclass(frozen=True)
class PriceRow:
    ticker: str
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None
    value: float | None
    source_version_id: str | None
    ingested_at: datetime


class PostgresFactStore:
    """Simple Postgres storage layer for the VN pharma dataset."""

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or os.getenv("DATABASE_URL", "postgresql://maer:maer_local@localhost:5432/maer_dev")

    @contextmanager
    def conn(self):
        connection = psycopg2.connect(self.dsn)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def upsert_price_rows(self, rows: Iterable[PriceRow]) -> int:
        payload = [
            (
                r.ticker,
                r.date,
                r.open,
                r.high,
                r.low,
                r.close,
                r.volume,
                r.value,
                r.source_version_id,
                r.ingested_at,
            )
            for r in rows
        ]
        if not payload:
            return 0
        with self.conn() as connection:
            with connection.cursor() as cur:
                execute_values(
                    cur,
                    """
                    INSERT INTO price_history
                    (ticker, date, open, high, low, close, volume, value, source_version_id, ingested_at)
                    VALUES %s
                    ON CONFLICT (ticker, date) DO UPDATE
                    SET open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        value = EXCLUDED.value,
                        source_version_id = EXCLUDED.source_version_id,
                        ingested_at = EXCLUDED.ingested_at
                    """,
                    payload,
                )
        return len(payload)

    def upsert_financial_facts(self, rows: Iterable[FinancialFact]) -> int:
        payload = [
            (
                r.company_ticker,
                r.fiscal_year,
                r.fiscal_period,
                r.taxonomy_key,
                r.value,
                r.unit,
                r.currency,
                r.source_version_id,
                r.parser_version,
                r.validation_status,
                r.confidence,
                r.effective_date,
                r.ingested_at,
            )
            for r in rows
        ]
        if not payload:
            return 0
        with self.conn() as connection:
            with connection.cursor() as cur:
                execute_values(
                    cur,
                    """
                    INSERT INTO financial_facts
                    (company_ticker, fiscal_year, fiscal_period, taxonomy_key, value, unit, currency,
                     source_version_id, parser_version, validation_status, confidence, effective_date, ingested_at)
                    VALUES %s
                    ON CONFLICT (company_ticker, fiscal_year, fiscal_period, taxonomy_key, source_version_id) DO UPDATE
                    SET value = EXCLUDED.value,
                        unit = EXCLUDED.unit,
                        currency = EXCLUDED.currency,
                        parser_version = EXCLUDED.parser_version,
                        validation_status = EXCLUDED.validation_status,
                        confidence = EXCLUDED.confidence,
                        effective_date = EXCLUDED.effective_date,
                        ingested_at = EXCLUDED.ingested_at
                    """,
                    payload,
                )
        return len(payload)

    def upsert_company_profile(
        self,
        ticker: str,
        company_name: str | None,
        exchange: str | None,
        segment: str | None,
        overview_json: dict[str, Any] | list[Any] | None,
        shareholders_json: dict[str, Any] | list[Any] | None,
        officers_json: dict[str, Any] | list[Any] | None,
    ) -> None:
        with self.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO company_profiles
                    (ticker, company_name, exchange, segment, overview_json, shareholders_json, officers_json, last_synced_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (ticker) DO UPDATE
                    SET company_name = EXCLUDED.company_name,
                        exchange = EXCLUDED.exchange,
                        segment = EXCLUDED.segment,
                        overview_json = EXCLUDED.overview_json,
                        shareholders_json = EXCLUDED.shareholders_json,
                        officers_json = EXCLUDED.officers_json,
                        last_synced_at = EXCLUDED.last_synced_at
                    """,
                    (
                        ticker,
                        company_name,
                        exchange,
                        segment,
                        Json(overview_json) if overview_json is not None else None,
                        Json(shareholders_json) if shareholders_json is not None else None,
                        Json(officers_json) if officers_json is not None else None,
                    ),
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
                    row.get("company_ticker"),
                    row.get("materiality_hint"),
                    row["source_url"],
                    row["source_version_id"],
                    row.get("confidence"),
                    row.get("validation_status", "accepted"),
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
                    INSERT INTO catalyst_events
                    (event_id, event_type, title, summary, occurred_at, effective_date, company_ticker,
                     materiality_hint, source_url, source_version_id, confidence, validation_status, ingested_at)
                    VALUES %s
                    ON CONFLICT (event_id) DO UPDATE
                    SET event_type = EXCLUDED.event_type,
                        title = EXCLUDED.title,
                        summary = EXCLUDED.summary,
                        occurred_at = EXCLUDED.occurred_at,
                        effective_date = EXCLUDED.effective_date,
                        company_ticker = EXCLUDED.company_ticker,
                        materiality_hint = EXCLUDED.materiality_hint,
                        source_url = EXCLUDED.source_url,
                        source_version_id = EXCLUDED.source_version_id,
                        confidence = EXCLUDED.confidence,
                        validation_status = EXCLUDED.validation_status,
                        ingested_at = EXCLUDED.ingested_at
                    """,
                    payload,
                )
        return len(payload)

    def insert_peer_metrics_snapshot(self, rows: Iterable[tuple[str, str, str, float, str]]) -> int:
        payload = list(rows)
        if not payload:
            return 0
        with self.conn() as connection:
            with connection.cursor() as cur:
                execute_values(
                    cur,
                    """
                    INSERT INTO peer_metrics_snapshot
                    (ticker, snapshot_period, metric_key, value, computation_run_id)
                    VALUES %s
                    """,
                    payload,
                )
        return len(payload)

    def query_financial_facts_wide(self, ticker: str, statement: str) -> pd.DataFrame:
        statement_filter = {
            "income_statement": ("income_statement",),
            "balance_sheet": ("balance_sheet",),
            "cash_flow": ("cash_flow",),
            "ratio": ("derived",),
        }.get(statement, (statement,))
        with self.conn() as connection:
            sql = """
                SELECT taxonomy_key,
                       CONCAT(fiscal_year::text, fiscal_period) AS period,
                       value
                FROM financial_facts
                WHERE company_ticker = %s
                  AND taxonomy_key IN (
                    SELECT key FROM (
                        SELECT jsonb_object_keys(%s::jsonb) AS key
                    ) x
                  )
                ORDER BY fiscal_year, fiscal_period
            """
            # taxonomy filter intentionally broad; adapter re-filters below.
            frame = pd.read_sql_query(
                "SELECT taxonomy_key, fiscal_year, fiscal_period, value FROM financial_facts WHERE company_ticker=%s",
                connection,
                params=(ticker,),
            )
        if frame.empty:
            return pd.DataFrame(columns=["metrics"])

        frame["period"] = frame["fiscal_year"].astype(str) + frame["fiscal_period"]
        pivot = frame.pivot_table(index="taxonomy_key", columns="period", values="value", aggfunc="last").reset_index()
        pivot = pivot.rename(columns={"taxonomy_key": "metrics"})
        return pivot

    def get_price_history(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        with self.conn() as connection:
            df = pd.read_sql_query(
                """
                SELECT date, open, high, low, close, volume, value
                FROM price_history
                WHERE ticker = %s AND date >= %s AND date <= %s
                ORDER BY date
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
                    FROM catalyst_events
                    WHERE company_ticker = %s
                      AND occurred_at >= NOW() - (%s || ' day')::interval
                    ORDER BY occurred_at DESC
                    """,
                    (ticker, days_back),
                )
                rows = cur.fetchall()
        return [
            {"title": title, "publishedDate": occurred_at.isoformat(), "text": summary, "url": source_url}
            for title, occurred_at, summary, source_url in rows
        ]

