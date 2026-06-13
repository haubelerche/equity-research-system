"""Multi-ticker collection loop (the cron entrypoint core).

Runs ticker-scoped collection for each MVP ticker; one ticker failing must not abort
the batch. I/O (DB collect, company lookup) is injected so the loop is offline-testable.
"""
from __future__ import annotations

from backend.database import config as database_config
from backend.news import runner
from backend.news.runner import MVP_TICKERS, collect_for_tickers
from scripts import collect_ticker_news


def test_loops_all_tickers_with_exchange_slug() -> None:
    calls: list[tuple] = []

    def fake_collect(conn, ticker, company, *, exchange_slug, **kw):
        calls.append((ticker, company, exchange_slug))
        return {"articles": 1, "evidence": 3}

    def lookup(ticker):
        return {"DHG": ("Dược Hậu Giang", "HOSE"), "DBD": ("Bidiphar", "UPCOM")}[ticker]

    results = collect_for_tickers(
        None, ["dhg", "dbd"], company_lookup=lookup, collect=fake_collect
    )
    assert calls == [
        ("DHG", "Dược Hậu Giang", "hose"),
        ("DBD", "Bidiphar", "upcom"),
    ]
    assert [r["ticker"] for r in results] == ["DHG", "DBD"]
    assert results[0]["articles"] == 1


def test_one_ticker_error_does_not_abort_batch() -> None:
    def fake_collect(conn, ticker, company, *, exchange_slug, **kw):
        if ticker == "DHG":
            raise RuntimeError("boom")
        return {"articles": 2, "evidence": 5}

    results = collect_for_tickers(
        None, ["DHG", "IMP"],
        company_lookup=lambda t: (t, "HOSE"),
        collect=fake_collect,
    )
    assert results[0]["ticker"] == "DHG" and "error" in results[0]
    assert results[1]["ticker"] == "IMP" and results[1]["articles"] == 2


def test_mvp_tickers_are_the_pharma_set() -> None:
    assert set(MVP_TICKERS) == {"DHG", "IMP", "DMC", "TRA", "DBD"}


def test_cli_returns_nonzero_when_any_ticker_fails(monkeypatch) -> None:
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    monkeypatch.setattr(database_config, "require_database_url", lambda: "postgres://test")
    monkeypatch.setattr(database_config, "connect_with_retry", lambda dsn: FakeConnection())
    monkeypatch.setattr(
        runner,
        "collect_for_tickers",
        lambda *args, **kwargs: [{"ticker": "DHG", "error": "boom"}],
    )

    assert collect_ticker_news.main(["--tickers", "DHG"]) == 1
