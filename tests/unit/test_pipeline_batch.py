"""Full-pipeline batch loop: run research per ticker, failure-isolated + resumable.

The heavy per-ticker pipeline (OCR + agents + valuation) is injected as run_one so the
loop is offline-testable. One ticker failing must not abort the batch; already-done
tickers are skipped when resuming.
"""
from __future__ import annotations

from backend import pipeline_batch
from backend.pipeline_batch import run_pipeline_for_tickers
from scripts import run_research_batch


def test_runs_each_ticker_and_reports_ok() -> None:
    seen: list[str] = []

    def run_one(ticker: str) -> dict:
        seen.append(ticker)
        return {"run_id": f"run_{ticker}"}

    results = run_pipeline_for_tickers(["dhg", "imp"], run_one=run_one)
    assert seen == ["DHG", "IMP"]
    assert [r["status"] for r in results] == ["ok", "ok"]
    assert results[0]["run_id"] == "run_DHG"


def test_one_failure_does_not_abort_batch() -> None:
    def run_one(ticker: str) -> dict:
        if ticker == "DHG":
            raise RuntimeError("pipeline boom")
        return {"run_id": f"run_{ticker}"}

    results = run_pipeline_for_tickers(["DHG", "IMP"], run_one=run_one)
    assert results[0]["status"] == "error" and "boom" in results[0]["error"]
    assert results[1]["status"] == "ok"


def test_resume_skips_already_done_tickers() -> None:
    calls: list[str] = []

    def run_one(ticker: str) -> dict:
        calls.append(ticker)
        return {}

    results = run_pipeline_for_tickers(
        ["DHG", "IMP"], run_one=run_one, should_skip=lambda t: t == "DHG"
    )
    assert calls == ["IMP"]  # DHG skipped, not run
    assert results[0]["status"] == "skipped"
    assert results[1]["status"] == "ok"


def test_paid_run_cap_advances_past_resume_skips() -> None:
    calls: list[str] = []

    results = run_pipeline_for_tickers(
        ["DHG", "IMP", "TRA", "DBD"],
        run_one=lambda ticker: calls.append(ticker) or {},
        should_skip=lambda ticker: ticker in {"DHG", "IMP"},
        max_runs=1,
    )

    assert calls == ["TRA"]
    assert [result["status"] for result in results] == ["skipped", "skipped", "ok"]


def test_normalizes_and_deduplicates_tickers_before_paid_work() -> None:
    calls: list[str] = []

    results = run_pipeline_for_tickers(
        [" dhg ", "DHG", "", "imp", "IMP"],
        run_one=lambda ticker: calls.append(ticker) or {},
    )

    assert calls == ["DHG", "IMP"]
    assert [result["ticker"] for result in results] == ["DHG", "IMP"]


def test_dry_run_selects_bounded_universe_without_running_pipeline(capsys) -> None:
    exit_code = run_research_batch.main(
        ["--all", "--max-tickers", "2", "--draft", "--dry-run"]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "selected=2" in output
    assert "--ticker <TICKER> --draft" in output


def test_batch_cli_returns_nonzero_when_any_ticker_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        pipeline_batch,
        "run_pipeline_for_tickers",
        lambda *args, **kwargs: [
            {"ticker": "DHG", "status": "error", "error": "pipeline boom"}
        ],
    )

    assert run_research_batch.main(["--tickers", "DHG"]) == 1
