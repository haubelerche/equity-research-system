from __future__ import annotations

from backend.documents.connectors.cafef_market_connector import CafeFQuote
from backend.reporting.market_data_artifact import load_cached_market_data
from scripts.ingest_cafef_market_data import ingest_cafef_market_data


def test_ingests_cafef_quote_to_run_scoped_market_data_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "scripts.ingest_cafef_market_data._exchange_for_ticker",
        lambda ticker: "UPCOM",
    )

    result = ingest_cafef_market_data(
        ticker="DPP",
        run_id="run-dpp",
        base_dir=tmp_path,
        fetcher=lambda ticker: CafeFQuote(
            ticker=ticker,
            last_price=26_500.0,
            as_of_date="2026-06-19",
            volume=123_000.0,
            source_url="https://cafef.vn/test",
        ),
    )

    cached = load_cached_market_data("DPP", run_id="run-dpp", base_dir=tmp_path)

    assert result["path"].endswith("run-dpp\\market_data.json") or result["path"].endswith("run-dpp/market_data.json")
    assert cached is not None
    assert cached.source == "cafef_price_history"
    assert cached.exchange == "UPCOM"
    assert cached.as_of_date == "2026-06-19"
    assert cached.trading_statistics.last_close == 26_500.0
    assert cached.price_history[0]["close"] == 26_500.0
