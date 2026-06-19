from __future__ import annotations

import csv
from types import SimpleNamespace

from backend.documents.connectors.cafef_market_connector import CafeFQuote
from scripts import crawl_cafef_manual_market_prices as crawler


def _rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_crawls_missing_tickers_and_preserves_existing_manual_row(tmp_path, monkeypatch):
    csv_path = tmp_path / "market_prices.csv"
    csv_path.write_text(
        "\n".join(
            [
                "as_of_date,ticker,price,status,source,open,high,low,volume,high_52w,low_52w",
                "2026-06-19,AGP,35600,accepted,vietstock_manual_2026-06-19,35600,35900,35500,4900,37400,31900",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(crawler, "load_universe_tickers", lambda: ["AGP", "DHG"])

    def fetcher(ticker: str) -> CafeFQuote:
        return CafeFQuote(
            ticker=ticker,
            last_price=93_400.0,
            as_of_date="2026-06-19",
            volume=3900.0,
            source_url="https://cafef.vn/test",
            open_price=93_500.0,
            high_price=93_600.0,
            low_price=93_000.0,
            high_52w=102_800.0,
            low_52w=93_000.0,
        )

    result = crawler.crawl_cafef_manual_market_prices(
        csv_path=csv_path,
        tickers=["AGP", "DHG"],
        fetcher=fetcher,
        sleep_seconds=0,
    )

    rows = {row["ticker"]: row for row in _rows(csv_path)}
    assert result["skipped_existing"] == ["AGP"]
    assert result["fetched"] == ["DHG"]
    assert rows["AGP"]["source"] == "vietstock_manual_2026-06-19"
    assert rows["DHG"]["price"] == "93400"
    assert rows["DHG"]["high"] == "93600"
    assert rows["DHG"]["low"] == "93000"
    assert rows["DHG"]["high_52w"] == "102800"
    assert rows["DHG"]["low_52w"] == "93000"


def test_uses_local_fallback_when_cafef_has_no_quote(tmp_path, monkeypatch):
    csv_path = tmp_path / "market_prices.csv"
    csv_path.write_text(
        "as_of_date,ticker,price,status,source,open,high,low,volume,high_52w,low_52w\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(crawler, "load_universe_tickers", lambda: ["AMV"])
    monkeypatch.setattr(
        crawler,
        "resolve_market_price",
        lambda ticker, allow_live, manual_csv_path: SimpleNamespace(
            ticker=ticker,
            current_price=1500.0,
            open=1500.0,
            high=1500.0,
            low=1500.0,
            volume=1200.0,
            high_52w=1800.0,
            low_52w=1000.0,
            price_as_of="2026-06-19",
            source="fact.price_history",
        ),
    )

    result = crawler.crawl_cafef_manual_market_prices(
        csv_path=csv_path,
        tickers=["AMV"],
        fetcher=lambda ticker: CafeFQuote(ticker, None, None, None, "url"),
        sleep_seconds=0,
    )

    rows = _rows(csv_path)
    assert result["fetched"] == ["AMV"]
    assert rows[0]["source"] == "fact.price_history"
    assert rows[0]["price"] == "1500"
