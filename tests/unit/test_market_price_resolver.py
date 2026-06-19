from __future__ import annotations

from datetime import date

import pandas as pd

from backend.valuation.market_price_resolver import resolve_market_price


class _Store:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def get_price_history(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        return self.frame


def test_manual_override_wins_over_fact_store(tmp_path):
    manual = tmp_path / "market_prices.csv"
    manual.write_text(
        "\n".join(
            [
                "as_of_date,ticker,price,status,source,high,low,high_52w,low_52w",
                "2026-06-19,AGP,35600,accepted,vietstock_manual,35900,35500,37400,31900",
            ]
        ),
        encoding="utf-8",
    )
    store = _Store(pd.DataFrame([{"trade_date": "2026-06-19", "close": 12.5, "high": 13, "low": 12}]))

    result = resolve_market_price(
        "AGP",
        as_of_date=date(2026, 6, 19),
        store=store,
        manual_csv_path=manual,
        raw_root=tmp_path,
    )

    assert result.current_price == 35_600
    assert result.high == 35_900
    assert result.low == 35_500
    assert result.high_52w == 37_400
    assert result.low_52w == 31_900
    assert result.source == "manual_market_prices:vietstock_manual"


def test_fact_store_price_is_scaled_from_thousand_vnd(tmp_path):
    store = _Store(
        pd.DataFrame(
            [
                {"trade_date": "2026-06-18", "open": 93.6, "high": 93.8, "low": 92.6, "close": 93.6},
                {"trade_date": "2026-06-19", "open": 93.5, "high": 93.6, "low": 93.0, "close": 93.4},
            ]
        )
    )

    result = resolve_market_price(
        "DHG",
        as_of_date=date(2026, 6, 19),
        store=store,
        manual_csv_path=tmp_path / "missing.csv",
        raw_root=tmp_path,
    )

    assert result.current_price == 93_400
    assert result.open == 93_500
    assert result.high == 93_600
    assert result.low == 93_000
    assert result.high_52w == 93_800
    assert result.low_52w == 92_600
    assert result.source == "fact.price_history"


def test_raw_cache_used_when_fact_store_missing(tmp_path):
    raw_dir = tmp_path / "2026-06-18"
    raw_dir.mkdir()
    (raw_dir / "DHG_quote_history.json").write_text(
        """[
          {"time":"2026-06-18T07:00:00.000","open":93.6,"high":93.8,"low":92.6,"close":93.6,"volume":27100}
        ]""",
        encoding="utf-8",
    )

    result = resolve_market_price(
        "DHG",
        as_of_date=date(2026, 6, 19),
        store=_Store(pd.DataFrame()),
        manual_csv_path=tmp_path / "missing.csv",
        raw_root=tmp_path,
    )

    assert result.current_price == 93_600
    assert result.high == 93_800
    assert result.low == 92_600
    assert result.source.startswith("raw_market_cache:")
    assert "raw_cache_short_history_for_52w" in result.warnings


def test_missing_price_does_not_use_live_when_disallowed(tmp_path, monkeypatch):
    def fail_live(*args, **kwargs):
        raise AssertionError("live fetch should not be called")

    monkeypatch.setattr(
        "backend.documents.connectors.cafef_market_connector.fetch_latest_price",
        fail_live,
        raising=False,
    )

    result = resolve_market_price(
        "AGP",
        as_of_date=date(2026, 6, 19),
        allow_live=False,
        store=_Store(pd.DataFrame()),
        manual_csv_path=tmp_path / "missing.csv",
        raw_root=tmp_path,
    )

    assert result.current_price is None
    assert result.source == "missing_market_price"
    assert "missing_current_price" in result.warnings
