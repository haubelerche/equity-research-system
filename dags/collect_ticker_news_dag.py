"""Airflow DAG: ticker-scoped news collection for the MVP pharma tickers.

Discovers CafeF/VietStock per-ticker news, fetches + extracts evidence, and stores it
in the ``news`` schema. Collection is idempotent (already-extracted articles are skipped),
so a frequent schedule is safe and cheap.

Deployment note: this project has no Airflow runtime of its own — drop this file into an
Airflow/Astro ``dags/`` folder where the project package is importable and ``DATABASE_URL``
(and the LLM API key) are set as env vars / Airflow Variables. apache-airflow is therefore
NOT added to the app's requirements.txt; only the Airflow scheduler imports this module.

Best practices applied: TaskFlow API, no top-level work, dynamic task mapping (one mapped
task per ticker — a single ticker failing does not fail the others), retries with backoff,
catchup disabled, max_active_runs=1.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from airflow.decorators import dag, task


@dag(
    dag_id="collect_ticker_news",
    start_date=datetime(2026, 1, 1),
    # Every 3 hours on weekdays (Vietnam trading days). Adjust 2–4h as desired.
    schedule="0 */3 * * 1-5",
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "research",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
        "retry_exponential_backoff": True,
    },
    tags=["news", "ingestion", "research"],
)
def collect_ticker_news():
    @task
    def list_tickers() -> list[str]:
        from backend.news.runner import MVP_TICKERS

        return list(MVP_TICKERS)

    @task(retries=2)
    def collect_one(ticker: str) -> dict:
        from backend.database.config import connect_with_retry, require_database_url
        from backend.news.runner import run_ticker_news_collection
        from backend.reporting.report_data_loader import _COMPANIES

        company_name, exchange = _COMPANIES.get(ticker, (ticker, "HOSE"))
        with connect_with_retry(require_database_url()) as conn:
            result = run_ticker_news_collection(
                conn, ticker, company_name, exchange_slug=exchange.lower()
            )
        return {"ticker": ticker, **result}

    # Dynamic task mapping: one independent, retryable task per ticker.
    collect_one.expand(ticker=list_tickers())


collect_ticker_news()
