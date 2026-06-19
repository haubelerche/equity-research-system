from __future__ import annotations

from types import SimpleNamespace

import scripts.recompute_valuation_inplace as recompute


def test_price_preflight_reports_missing_market_fields(monkeypatch):
    def fake_resolve_market_price(ticker: str, *, allow_live: bool):
        assert ticker == "AGP"
        assert allow_live is False
        return SimpleNamespace(
            current_price=None,
            high=None,
            low=None,
            high_52w=None,
            low_52w=None,
            price_as_of="",
            source="missing_market_price",
            staleness_days=None,
            warnings=["missing_current_price"],
        )

    monkeypatch.setattr(
        "backend.valuation.market_price_resolver.resolve_market_price",
        fake_resolve_market_price,
    )

    result = recompute._price_preflight_snapshot("AGP")

    assert result["status"] == "missing_market_price:current_price,high,low"
    assert result["price_source"] == "missing_market_price"
    assert result["price_warnings"] == "missing_current_price"


def test_price_preflight_accepts_current_high_low(monkeypatch):
    def fake_resolve_market_price(ticker: str, *, allow_live: bool):
        return SimpleNamespace(
            current_price=35_600,
            high=35_900,
            low=35_500,
            high_52w=37_400,
            low_52w=31_900,
            price_as_of="2026-06-19",
            source="manual_market_prices:vietstock_manual",
            staleness_days=0,
            warnings=[],
        )

    monkeypatch.setattr(
        "backend.valuation.market_price_resolver.resolve_market_price",
        fake_resolve_market_price,
    )

    result = recompute._price_preflight_snapshot("AGP")

    assert result["status"] == "market_price_ready"
    assert result["current_price"] == 35_600
    assert result["price_source"] == "manual_market_prices:vietstock_manual"
