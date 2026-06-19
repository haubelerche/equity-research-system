from __future__ import annotations

from scripts import ingest_manual_market_prices as manual_ingest


def test_manual_market_ingest_preserves_optional_ohlc_and_volume(tmp_path, monkeypatch):
    csv_path = tmp_path / "market_prices.csv"
    csv_path.write_text(
        "\n".join(
            [
                "as_of_date,ticker,price,status,source,open,high,low,volume",
                "2026-06-19,AGP,35600,accepted,vietstock_manual,35600,35900,35500,4900",
            ]
        ),
        encoding="utf-8",
    )
    captured = {}

    class FakeStore:
        def upsert_price_rows(self, rows):
            captured["rows"] = list(rows)
            return len(captured["rows"])

    monkeypatch.setattr(manual_ingest, "PostgresFactStore", FakeStore)
    monkeypatch.setattr(manual_ingest, "RuntimeStore", lambda: object())
    monkeypatch.setattr(manual_ingest, "ensure_ticker_registered_from_universe", lambda store, ticker: None)

    result = manual_ingest.load_manual_market_prices(csv_path=csv_path, dry_run=False)

    row = captured["rows"][0]
    assert result["inserted_rows"] == 1
    assert row.ticker == "AGP"
    assert row.close == 35.6
    assert row.open == 35.6
    assert row.high == 35.9
    assert row.low == 35.5
    assert row.volume == 4900
