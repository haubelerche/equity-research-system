"""Airflow DAG: full research pipeline across the ticker universe (deploy-only).

Each ticker is a mapped task running scripts/run_research.py as an isolated subprocess
(OCR + agents + valuation). HEAVY: concurrency is capped and the DAG is manual-only until
the runtime and cost profile has been measured on a staged subset.
This DAG is a deploy target for a SEPARATE Airflow/Astro runtime — it is intentionally
not an application dependency (see astro/README.md).
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta

try:
    from airflow.decorators import dag, task
except ModuleNotFoundError as exc:  # pragma: no cover - app runtime has no scheduler dep
    raise ModuleNotFoundError(
        "run_research_batch_dag requires Apache Airflow (a SEPARATE scheduler runtime; "
        "see astro/README.md) — it is not an application dependency."
    ) from exc

_AIRFLOW_HOME = os.environ.get("AIRFLOW_HOME", "/usr/local/airflow")


@dag(
    dag_id="run_research_batch",
    start_date=datetime(2026, 1, 1),
    # Manual-only: deploying scheduler infrastructure must not launch 53 paid runs.
    schedule=None,
    catchup=False,
    max_active_runs=1,
    max_active_tasks=2,  # heavy per-ticker work — cap concurrency
    default_args={
        "owner": "research",
        "retries": 1,
        "retry_delay": timedelta(minutes=10),
    },
    tags=["research", "pipeline", "batch"],
)
def run_research_batch():
    @task
    def list_tickers() -> list[str]:
        from backend.reporting.report_data_loader import _COMPANIES

        return sorted(_COMPANIES)

    @task
    def run_one(ticker: str) -> dict:
        cmd = [
            sys.executable,
            f"{_AIRFLOW_HOME}/scripts/run_research.py",
            "--ticker", ticker, "--draft",
        ]
        proc = subprocess.run(cmd)  # isolated subprocess per ticker
        if proc.returncode != 0:
            raise RuntimeError(f"run_research exited {proc.returncode} for {ticker}")
        return {"ticker": ticker, "returncode": 0}

    run_one.expand(ticker=list_tickers())


run_research_batch()
