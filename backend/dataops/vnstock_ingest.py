"""Best-effort vnstock financial ingestion for a single ticker.

Reuses the proven single-ticker path (see scripts/ingest_ticker.py) so the
report-generation pipeline can pull financial statements from vnstock as an
additional source alongside CafeF and official PDFs. Non-blocking by contract:
any failure returns a warn summary and the caller continues with whatever other
sources produced.
"""
from __future__ import annotations

from typing import Any

from backend.period_scope import DEFAULT_FROM_YEAR, DEFAULT_TO_YEAR


def ingest_vnstock_financials(
    ticker: str,
    from_year: int = DEFAULT_FROM_YEAR,
    to_year: int = DEFAULT_TO_YEAR,
) -> dict[str, Any]:
    """Sync vnstock financial statements into canonical facts. Never raises."""
    ticker = ticker.strip().upper()
    try:
        from backend.database.canonical.fact_promotion import promote_accepted_facts
        from backend.database.fact_store import PostgresFactStore
        from backend.database.source_registry import SourceRegistry
        from scripts.connectors.vnstock_finance_connector import sync_financial_for_ticker

        store = PostgresFactStore()
        registry = SourceRegistry(store=store)
        inserted = sync_financial_for_ticker(
            ticker=ticker,
            store=store,
            registry=registry,
            period="year",
            from_year=from_year,
            to_year=to_year,
            provider="auto",
        )
        promo = promote_accepted_facts(ticker=ticker, from_year=from_year, to_year=to_year)
        return {
            "status": "completed",
            "facts_upserted": inserted,
            "facts_promoted": getattr(promo, "promoted", 0),
        }
    except Exception as exc:  # noqa: BLE001 — never let vnstock break the run
        return {
            "status": "warn",
            "facts_upserted": 0,
            "facts_promoted": 0,
            "warning": str(exc)[:200],
        }
