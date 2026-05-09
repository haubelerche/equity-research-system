from __future__ import annotations

import argparse

from scripts.dataset.config_io import load_universe_tickers

from backend.executor import RunExecutor
from backend.orchestrator import RunContext, Supervisor
from backend.runtime_store import RuntimeStore
from backend.settings import settings
from backend.utils import deterministic_id


def submit_universe_runs(limit: int | None = None) -> list[str]:
    store = RuntimeStore(dsn=settings.database_url)
    store.ensure_schema()
    supervisor = Supervisor(store=store)
    executor = RunExecutor(store=store, supervisor=supervisor)

    tickers = load_universe_tickers()
    if limit is not None:
        tickers = tickers[:limit]

    submitted: list[str] = []
    for ticker in tickers:
        run_id = deterministic_id(ticker, "full_report", "batch")
        flags = {
            "factsChanged": False,
            "catalystChanged": False,
            "valuationChanged": False,
            "thesisNeedsRefresh": False,
            "citationsNeedRefresh": False,
        }
        policy = {
            "budget_policy": settings.default_budget_policy,
            "soft_budget_usd": settings.soft_budget_usd,
            "hard_budget_usd": settings.hard_budget_usd,
            "fallback_model": settings.fallback_model,
        }
        try:
            store.create_run(
                run_id=run_id,
                ticker=ticker,
                run_type="full_report",
                objective=f"Batch full report for {ticker}",
                flags=flags,
                policy=policy,
                requested_by="batch_runner",
            )
        except Exception:
            # Run may already exist; continue to submit/resume style behavior.
            pass
        executor.submit(
            RunContext(
                run_id=run_id,
                ticker=ticker,
                run_type="full_report",
                objective=f"Batch full report for {ticker}",
                policy=policy,
                flags=flags,
            )
        )
        submitted.append(run_id)
    return submitted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Submit batch research runs for VN pharma universe.")
    parser.add_argument("--limit", type=int, default=0, help="Optional cap on number of tickers.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    limit = args.limit if args.limit > 0 else None
    run_ids = submit_universe_runs(limit=limit)
    print(f"Submitted {len(run_ids)} runs")
    for run_id in run_ids:
        print(run_id)


if __name__ == "__main__":
    main()

