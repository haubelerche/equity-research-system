"""Tests for backend.analytics.net_debt_bridge (Phase 5 / checklist item 15-16)."""
from __future__ import annotations

import json
import pytest
from backend.analytics.net_debt_bridge import build_net_debt_bridge, NetDebtBridge


def _ft(debt=None, cash=None, st_inv=None) -> dict:
    ft: dict = {}
    if debt is not None:
        ft["total_debt.ending"] = {"2025FY": {"value": debt}}
    if cash is not None:
        ft["cash_and_equivalents.ending"] = {"2025FY": {"value": cash}}
    if st_inv is not None:
        ft["short_term_investments.ending"] = {"2025FY": {"value": st_inv}}
    return ft


def _component_ft(st_debt=None, lt_debt=None, cash=None, st_inv=None) -> dict:
    ft: dict = {}
    if st_debt is not None:
        ft["short_term_debt.ending"] = {"2025FY": {"value": st_debt}}
    if lt_debt is not None:
        ft["long_term_debt.ending"] = {"2025FY": {"value": lt_debt}}
    if cash is not None:
        ft["cash_and_equivalents.ending"] = {"2025FY": {"value": cash}}
    if st_inv is not None:
        ft["short_term_investments.ending"] = {"2025FY": {"value": st_inv}}
    return ft


class TestNetDebtFormula:
    def test_net_debt_all_components(self):
        bridge = build_net_debt_bridge(_ft(debt=200.0, cash=80.0, st_inv=30.0), "2025FY")
        assert bridge.net_debt == pytest.approx(200.0 - 80.0 - 30.0)

    def test_net_debt_no_short_term_investments(self):
        bridge = build_net_debt_bridge(_ft(debt=150.0, cash=50.0), "2025FY")
        assert bridge.net_debt == pytest.approx(150.0 - 50.0)

    def test_status_ok_when_all_present(self):
        bridge = build_net_debt_bridge(_ft(debt=100.0, cash=40.0, st_inv=10.0), "2025FY")
        assert bridge.status == "ok"
        assert not bridge.is_blocked

    def test_status_warned_when_cash_missing(self):
        bridge = build_net_debt_bridge(_ft(debt=100.0), "2025FY")
        assert bridge.status == "warned"
        assert not bridge.is_blocked

    def test_status_warned_when_st_inv_missing(self):
        bridge = build_net_debt_bridge(_ft(debt=100.0, cash=40.0), "2025FY")
        assert bridge.status == "warned"

    def test_status_blocked_when_total_debt_missing(self):
        bridge = build_net_debt_bridge(_ft(cash=40.0, st_inv=10.0), "2025FY")
        assert bridge.status == "blocked"
        assert bridge.is_blocked
        assert bridge.net_debt is None

    def test_uses_short_and_long_debt_components_when_total_debt_missing(self):
        bridge = build_net_debt_bridge(
            _component_ft(st_debt=43.215, lt_debt=132.0, cash=202.784, st_inv=409.201),
            "2025FY",
        )
        assert bridge.status == "ok"
        assert not bridge.is_blocked
        assert bridge.total_debt == pytest.approx(175.215)
        assert bridge.net_debt == pytest.approx(175.215 - 202.784 - 409.201)
        assert any("derived interest-bearing debt" in w for w in bridge.warnings)

    def test_blocked_emits_warning(self):
        bridge = build_net_debt_bridge(_ft(), "2025FY")
        assert any("BLOCKED" in w for w in bridge.warnings)


class TestEquityValueFromEV:
    def test_equity_value_computed_when_ev_provided(self):
        bridge = build_net_debt_bridge(_ft(debt=200.0, cash=80.0, st_inv=30.0), "2025FY",
                                       enterprise_value=1000.0)
        # net_debt = 200 - 80 - 30 = 90; equity = 1000 - 90 = 910
        assert bridge.equity_value_from_ev == pytest.approx(910.0)

    def test_equity_value_includes_minority_interest(self):
        bridge = build_net_debt_bridge(_ft(debt=200.0, cash=80.0), "2025FY",
                                       enterprise_value=1000.0,
                                       minority_interest_override=20.0)
        # net_debt = 200 - 80 = 120; equity = 1000 - 120 - 20 = 860
        assert bridge.equity_value_from_ev == pytest.approx(860.0)

    def test_equity_value_adds_non_operating_assets(self):
        bridge = build_net_debt_bridge(_ft(debt=100.0, cash=50.0), "2025FY",
                                       enterprise_value=500.0,
                                       non_operating_assets_override=30.0)
        # equity = 500 - 50 + 30 = 480
        assert bridge.equity_value_from_ev == pytest.approx(480.0)

    def test_equity_value_none_when_blocked(self):
        bridge = build_net_debt_bridge(_ft(cash=40.0), "2025FY", enterprise_value=800.0)
        assert bridge.is_blocked
        assert bridge.equity_value_from_ev is None


class TestSerialization:
    def test_to_dict_serializable(self):
        bridge = build_net_debt_bridge(_ft(debt=200.0, cash=80.0, st_inv=30.0), "2025FY",
                                       enterprise_value=1000.0)
        json.dumps(bridge.to_dict())

    def test_to_dict_contains_formula(self):
        bridge = build_net_debt_bridge(_ft(debt=100.0, cash=50.0), "2025FY")
        assert "formula" in bridge.to_dict()

    def test_to_dict_contains_status(self):
        bridge = build_net_debt_bridge(_ft(), "2025FY")
        assert bridge.to_dict()["status"] == "blocked"


class TestFCFFIntegration:
    """When total_debt is missing, FCFF must block target_price."""

    def test_fcff_blocks_target_price_when_debt_missing(self):
        from backend.analytics.forecasting import run_forecast
        from backend.analytics.fcff import compute_fcff, WACCAssumptions

        fact_table = {
            "revenue.net": {"2024FY": 1000.0, "2025FY": 1100.0},
            "gross_profit.total": {"2024FY": 400.0, "2025FY": 450.0},
            "sga.total": {"2024FY": -200.0, "2025FY": -220.0},
            "depreciation.total": {"2024FY": 30.0, "2025FY": 32.0},
            "capex.total": {"2024FY": -50.0, "2025FY": -55.0},
            # No total_debt.ending → bridge should BLOCK
            "cash_and_equivalents.ending": {"2025FY": 100.0},
            "equity.parent": {"2025FY": 500.0},
        }
        forecast = run_forecast("TST", fact_table, shares_mn=50.0)
        result = compute_fcff(
            ticker="TST", forecast=forecast, fact_table=fact_table,
            shares_mn=50.0, wacc_assumptions=WACCAssumptions(wacc_override=0.12),
        )
        assert result.target_price_vnd is None
        assert result.net_debt_bridge is not None
        assert result.net_debt_bridge.is_blocked
        assert any("BLOCKED" in w for w in result.warnings)

    def test_fcff_publishes_when_debt_components_are_present(self):
        from backend.analytics.forecasting import run_forecast
        from backend.analytics.fcff import compute_fcff, WACCAssumptions

        fact_table = {
            "revenue.net": {"2024FY": 1000.0, "2025FY": 1100.0},
            "gross_profit.total": {"2024FY": 400.0, "2025FY": 450.0},
            "sga.total": {"2024FY": -200.0, "2025FY": -220.0},
            "depreciation.total": {"2024FY": 30.0, "2025FY": 32.0},
            "capex.total": {"2024FY": -50.0, "2025FY": -55.0},
            "short_term_debt.ending": {"2025FY": 40.0},
            "long_term_debt.ending": {"2025FY": 60.0},
            "cash_and_equivalents.ending": {"2025FY": 25.0},
            "equity.parent": {"2025FY": 500.0},
        }
        forecast = run_forecast("TST", fact_table, shares_mn=50.0)
        result = compute_fcff(
            ticker="TST", forecast=forecast, fact_table=fact_table,
            shares_mn=50.0, wacc_assumptions=WACCAssumptions(wacc_override=0.12),
        )
        assert result.net_debt_bridge is not None
        assert not result.net_debt_bridge.is_blocked
        assert result.net_debt_bridge.total_debt == pytest.approx(100.0)
        assert result.target_price_vnd is not None
