"""FCFF artifact must disclose the EV→equity bridge.

The publishability policy requires ``ev_to_equity_bridge`` as evidence the
enterprise-value-to-equity walk is disclosed. The data (EV, net debt, equity)
already exists in the FCFF result; it just was never serialised, so FCFF was
blocked cohort-wide (``fcff_wacc_or_ev_to_equity_bridge_missing``).
"""
from __future__ import annotations

from backend.analytics.fcff import compute_fcff
from backend.analytics.forecasting import run_forecast
from backend.facts.normalizer import FactTable


def _healthy_table() -> FactTable:
    rev = {p: 1000.0 for p in ("2022FY", "2023FY", "2024FY", "2025FY")}
    return {
        "revenue.net": rev,
        "gross_profit.total": {p: 400.0 for p in rev},
        "ebit.total": {p: 200.0 for p in rev},
        "depreciation.total": {p: 30.0 for p in rev},
        "capex.total": {p: -30.0 for p in rev},
        "profit_before_tax.total": {p: 190.0 for p in rev},
        "tax_expense.total": {p: -38.0 for p in rev},
        "total_assets.ending": {p: 2000.0 for p in rev},
        "total_debt.ending": {p: 100.0 for p in rev},
        "cash_and_equivalents.ending": {p: 200.0 for p in rev},
        "equity.parent": {p: 1500.0 for p in rev},
    }


def test_fcff_emits_ev_to_equity_bridge():
    table = _healthy_table()
    art = run_forecast("HLT", table, n_years=5)
    res = compute_fcff("HLT", art, table, shares_mn=100.0)
    payload = res.to_dict()

    bridge = payload.get("ev_to_equity_bridge")
    assert bridge is not None, "FCFF must emit ev_to_equity_bridge"
    assert "enterprise_value" in bridge
    assert "equity_value" in bridge


def test_ev_to_equity_bridge_satisfies_identity():
    table = _healthy_table()
    art = run_forecast("HLT", table, n_years=5)
    res = compute_fcff("HLT", art, table, shares_mn=100.0)
    bridge = res.to_dict()["ev_to_equity_bridge"]

    # enterprise_value - net_debt = equity_value
    walk = bridge["enterprise_value"] - bridge["less_net_debt"]
    assert abs(walk - bridge["equity_value"]) < 1.0, (
        f"EV ({bridge['enterprise_value']}) - net_debt ({bridge['less_net_debt']}) "
        f"should equal equity ({bridge['equity_value']})"
    )
