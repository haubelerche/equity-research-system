"""Full research-pipeline batch loop (scale to the ticker universe).

Runs the heavy per-ticker pipeline (ingestion → facts → valuation → report) for many
tickers. Failure-isolated: one ticker raising never aborts the batch. Resumable: a
``should_skip`` predicate lets a re-run skip tickers already completed.

The per-ticker work (``run_one``) is injected so this loop is pure and offline-testable;
the production wiring (scripts/run_research_batch.py) runs each ticker as an isolated
subprocess so even a hard crash in one ticker's pipeline cannot take down the batch.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence


def run_pipeline_for_tickers(
    tickers: Sequence[str],
    *,
    run_one: Callable[[str], dict],
    should_skip: Callable[[str], bool] | None = None,
    max_runs: int | None = None,
) -> list[dict]:
    """Run tickers with failure isolation, resume skips, and an optional paid-run cap."""
    results: list[dict] = []
    seen: set[str] = set()
    runs_started = 0
    for raw in tickers:
        ticker = raw.strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        if should_skip is not None and should_skip(ticker):
            results.append({"ticker": ticker, "status": "skipped"})
            continue
        if max_runs is not None and runs_started >= max_runs:
            break
        runs_started += 1
        try:
            result = run_one(ticker) or {}
            results.append({**result, "ticker": ticker, "status": "ok"})
        except Exception as exc:  # noqa: BLE001 — keep running the remaining tickers
            results.append({"ticker": ticker, "status": "error", "error": str(exc)})
    return results
