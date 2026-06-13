from __future__ import annotations

import pandas as pd
import pytest

from backend.reporting.market_data_artifact import load_market_data_from_fact_store


class _FakeStore:
    def get_price_history(self, ticker, start, end):
        if ticker != "DHG":
            return pd.DataFrame()
        return pd.DataFrame(
            [
                {"trade_date": "2026-05-28", "close": 103.0, "volume": 1000},
                {"trade_date": "2026-05-29", "close": 102.0, "volume": 1200},
            ]
        )


def test_loads_stock_history_from_canonical_fact_store():
    artifact = load_market_data_from_fact_store("DHG", "HOSE", store=_FakeStore())

    assert artifact.source == "fact.price_history"
    assert len(artifact.price_history) == 2
    assert artifact.primary_benchmark == "VNINDEX"
    assert artifact.primary_benchmark_history == []
    assert artifact.availability["price_history"].available
    assert not artifact.availability["primary_benchmark"].available
    assert artifact.trading_performance.absolute_returns["1T"] == pytest.approx(-1 / 103)
    assert artifact.trading_performance.relative_returns["1T"] is None
