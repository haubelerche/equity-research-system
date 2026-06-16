"""Tests for backend.analytics.debt_schedule (P0-02)."""
from __future__ import annotations

import pytest
from backend.analytics.debt_schedule import (
    build_debt_schedule,
    build_historical_debt_schedule,
    build_forecast_debt_schedule,
    debt_plan_to_manual_path,
    interest_bearing_debt,
    MissingValueReason,
)


_FL = ["2026F", "2027F", "2028F"]
_FY = [2026, 2027, 2028]


class TestDebtPlanToManualPath:
    def test_net_borrowing_rolls_forward_ending_debt(self):
        plan = [{"year": 2026, "amount": 100.0}, {"year": 2027, "amount": -40.0}]
        path = debt_plan_to_manual_path(plan, last_ending=200.0, forecast_labels=_FL, forecast_years=_FY)
        assert path["2026F"] == pytest.approx(300.0)   # 200 + 100
        assert path["2027F"] == pytest.approx(260.0)   # 300 - 40
        assert path["2028F"] == pytest.approx(260.0)   # no plan row → held flat

    def test_no_new_borrowing_from_debt_free_anchor_is_all_zero(self):
        plan = [{"year": y, "amount": 0.0} for y in _FY]
        path = debt_plan_to_manual_path(plan, last_ending=0.0, forecast_labels=_FL, forecast_years=_FY)
        assert all(v == 0.0 for v in path.values())

    def test_ending_debt_floored_at_zero(self):
        plan = [{"year": 2026, "amount": -500.0}]
        path = debt_plan_to_manual_path(plan, last_ending=100.0, forecast_labels=_FL, forecast_years=_FY)
        assert path["2026F"] == 0.0

    def test_empty_plan_returns_none(self):
        assert debt_plan_to_manual_path([], 100.0, _FL, _FY) is None
        assert debt_plan_to_manual_path(None, 100.0, _FL, _FY) is None
        assert debt_plan_to_manual_path([{"description": "x"}], 100.0, _FL, _FY) is None

    def test_plan_path_makes_fcfe_publishable(self):
        # A PDF-stated plan is authoritative → approved manual_override → FCFE publishable
        # even for a company that still carries debt (would otherwise be stable_debt/low).
        ft = _make_ft({"2024FY": 300.0})
        hist = build_historical_debt_schedule("TEST", ft, ["2024FY"])
        path = debt_plan_to_manual_path(
            [{"year": 2026, "amount": -50.0}], last_ending=300.0,
            forecast_labels=_FL, forecast_years=_FY,
        )
        sched = build_debt_schedule(
            "TEST", ft, ["2024FY"], _FL, _FY,
            manual_debt_path=path, manual_debt_path_approved=True,
        )
        assert sched.forecast_method == "manual_override"
        assert sched.is_fcfe_publishable is True


_FORECAST_LABELS = ["2026F", "2027F", "2028F"]
_FORECAST_YEARS = [2026, 2027, 2028]


def _make_ft(debt_by_period: dict[str, float]) -> dict:
    return {"total_debt.ending": debt_by_period}


class TestInterestBearingDebt:
    def test_uses_total_debt_ending(self):
        ft = {"total_debt.ending": {"2024FY": 500.0}}
        assert interest_bearing_debt(ft, "2024FY") == 500.0

    def test_falls_back_to_components(self):
        ft = {
            "short_term_borrowings.ending": {"2024FY": 100.0},
            "long_term_borrowings.ending": {"2024FY": 200.0},
        }
        assert interest_bearing_debt(ft, "2024FY") == 300.0

    def test_returns_none_when_no_data(self):
        assert interest_bearing_debt({}, "2024FY") is None


class TestHistoricalDebtSchedule:
    def test_balance_sheet_delta_net_borrowing(self):
        ft = _make_ft({"2022FY": 100.0, "2023FY": 150.0, "2024FY": 120.0})
        rows = build_historical_debt_schedule("TEST", ft, ["2022FY", "2023FY", "2024FY"])
        assert len(rows) == 3
        # Second row: 150 - 100 = +50 borrowing
        assert rows[1].net_borrowing == pytest.approx(50.0)
        assert rows[1].method == "balance_sheet_delta"
        # Third row: 120 - 150 = -30 (net repayment)
        assert rows[2].net_borrowing == pytest.approx(-30.0)

    def test_first_row_has_no_beginning_debt(self):
        ft = _make_ft({"2022FY": 100.0})
        rows = build_historical_debt_schedule("TEST", ft, ["2022FY"])
        assert rows[0].beginning_interest_bearing_debt is None
        assert rows[0].net_borrowing is None

    def test_missing_ending_debt_adds_missing_reason(self):
        ft: dict = {}  # No debt data
        rows = build_historical_debt_schedule("TEST", ft, ["2024FY"])
        assert rows[0].ending_interest_bearing_debt is None
        assert any(m.field == "ending_interest_bearing_debt" for m in rows[0].missing_fields)

    def test_direct_cash_flow_method_when_cfs_data_available(self):
        ft = {
            "total_debt.ending": {"2024FY": 150.0},
            "proceeds_from_borrowings.total": {"2024FY": 80.0},
            "repayment_of_borrowings.total": {"2024FY": -30.0},
        }
        rows = build_historical_debt_schedule("TEST", ft, ["2024FY"])
        assert rows[0].method == "direct_cash_flow"
        assert rows[0].confidence == "high"
        assert rows[0].net_borrowing == pytest.approx(50.0)  # 80 - 30


class TestForecastDebtSchedule:
    def _hist_rows_with_debt(self, debt: float = 200.0):
        ft = _make_ft({"2024FY": debt})
        return build_historical_debt_schedule("TEST", ft, ["2024FY"])

    def test_zero_debt_policy_when_historical_debt_is_zero(self):
        ft = _make_ft({"2022FY": 0.0, "2023FY": 0.0, "2024FY": 0.0})
        hist = build_historical_debt_schedule("TEST", ft, ["2022FY", "2023FY", "2024FY"])
        rows, method, warnings = build_forecast_debt_schedule(
            "TEST", ft, hist, _FORECAST_LABELS, _FORECAST_YEARS
        )
        assert method == "zero_debt_policy"
        for r in rows:
            assert r.ending_interest_bearing_debt == 0.0
            assert r.net_borrowing == 0.0

    def test_stable_debt_when_historical_debt_exists(self):
        ft = _make_ft({"2022FY": 100.0, "2023FY": 200.0, "2024FY": 150.0})
        hist = build_historical_debt_schedule("TEST", ft, ["2022FY", "2023FY", "2024FY"])
        rows, method, warnings = build_forecast_debt_schedule(
            "TEST", ft, hist, _FORECAST_LABELS, _FORECAST_YEARS
        )
        assert method == "stable_debt"
        assert rows[0].confidence == "low"
        assert all(r.ending_interest_bearing_debt is not None for r in rows)

    def test_paid_down_to_zero_rolls_forward_with_no_phantom_borrowing(self):
        # Regression: DHG paid debt to 0 by the last actual year. The forecast must
        # roll forward from that real closing balance (0) — NOT jump to the historical
        # median — so no phantom net_borrowing is injected into FCFE.
        # Updated intent (2026-06-16): being debt-free at the anchor is now treated as a
        # no-new-debt POLICY (zero_debt_policy, high confidence), which unblocks FCFE.
        # See test_debt_free_at_anchor_is_zero_debt_policy_and_publishable.
        ft = _make_ft({"2022FY": 115.0, "2023FY": 572.0, "2024FY": 650.0, "2025FY": 0.0})
        hist = build_historical_debt_schedule(
            "TEST", ft, ["2022FY", "2023FY", "2024FY", "2025FY"]
        )
        rows, method, _ = build_forecast_debt_schedule(
            "TEST", ft, hist, _FORECAST_LABELS, _FORECAST_YEARS
        )
        assert method == "zero_debt_policy"
        # Every forecast year is debt-free → zero net borrowing throughout (no phantom).
        for r in rows:
            assert r.ending_interest_bearing_debt == pytest.approx(0.0)
            assert r.net_borrowing == pytest.approx(0.0)

    def test_debt_free_at_anchor_is_zero_debt_policy_and_publishable(self):
        # Intent (2026-06-16): a company that has paid its interest-bearing debt down
        # to ~0 by the last actual year (e.g. DHG 2025) is debt-free at the forecast
        # anchor. Net borrowing forecasts to 0 as a defensible no-new-debt POLICY
        # (high confidence), which must unblock FCFE — not be buried as low-confidence
        # stable_debt. (Supersedes the earlier "stays stable_debt by design" stance.)
        from backend.analytics.debt_schedule import DebtSchedule

        ft = _make_ft({"2022FY": 115.0, "2023FY": 572.0, "2024FY": 650.0, "2025FY": 0.0})
        hist = build_historical_debt_schedule(
            "TEST", ft, ["2022FY", "2023FY", "2024FY", "2025FY"]
        )
        rows, method, warnings = build_forecast_debt_schedule(
            "TEST", ft, hist, _FORECAST_LABELS, _FORECAST_YEARS
        )
        assert method == "zero_debt_policy"
        for r in rows:
            assert r.net_borrowing == 0.0
            assert r.confidence == "high"
        sched = DebtSchedule(
            ticker="TEST", historical_rows=hist, forecast_rows=rows,
            forecast_method=method, warnings=warnings,
        )
        assert sched.is_fcfe_publishable is True

    def test_manual_override_uses_provided_path(self):
        hist = self._hist_rows_with_debt(100.0)
        manual = {"2026F": 80.0, "2027F": 60.0, "2028F": 40.0}
        rows, method, warnings = build_forecast_debt_schedule(
            "TEST", {}, hist, _FORECAST_LABELS, _FORECAST_YEARS,
            manual_debt_path=manual,
        )
        assert method == "manual_override"
        assert rows[0].ending_interest_bearing_debt == 80.0
        assert rows[1].ending_interest_bearing_debt == 60.0

    def test_missing_method_when_no_historical_data(self):
        rows, method, warnings = build_forecast_debt_schedule(
            "TEST", {}, [], _FORECAST_LABELS, _FORECAST_YEARS
        )
        assert method == "missing"
        for r in rows:
            assert r.ending_interest_bearing_debt is None
            assert r.net_borrowing is None
            assert any(m.status == "missing_source_data" for m in r.missing_fields)

    def test_forecast_cannot_silently_become_zero_without_zero_debt_policy(self):
        """Forecast with actual debt history must NOT silently use zero net_borrowing."""
        ft = _make_ft({"2022FY": 100.0, "2023FY": 200.0, "2024FY": 150.0})
        hist = build_historical_debt_schedule("TEST", ft, ["2022FY", "2023FY", "2024FY"])
        rows, method, _ = build_forecast_debt_schedule(
            "TEST", ft, hist, _FORECAST_LABELS, _FORECAST_YEARS
        )
        # Method must not be zero_debt_policy when there is real historical debt
        assert method != "zero_debt_policy"


class TestDebtScheduleEntryPoint:
    def test_build_debt_schedule_returns_complete_object(self):
        ft = _make_ft({"2022FY": 100.0, "2023FY": 150.0, "2024FY": 120.0})
        ds = build_debt_schedule(
            "TEST", ft,
            fy_periods=["2022FY", "2023FY", "2024FY"],
            forecast_labels=_FORECAST_LABELS,
            forecast_years=_FORECAST_YEARS,
        )
        assert len(ds.historical_rows) == 3
        assert len(ds.forecast_rows) == 3
        assert ds.forecast_method != "missing"

    def test_net_borrowing_schedule_for_fcfe(self):
        ft = _make_ft({"2024FY": 200.0})
        ds = build_debt_schedule(
            "TEST", ft,
            fy_periods=["2024FY"],
            forecast_labels=_FORECAST_LABELS,
            forecast_years=_FORECAST_YEARS,
        )
        nb_schedule = ds.net_borrowing_schedule()
        assert isinstance(nb_schedule, dict)
        assert set(nb_schedule.keys()) == set(_FORECAST_LABELS)

    def test_to_dict_is_json_serializable(self):
        import json
        ft = _make_ft({"2024FY": 100.0})
        ds = build_debt_schedule(
            "TEST", ft,
            fy_periods=["2024FY"],
            forecast_labels=["2026F"],
            forecast_years=[2026],
        )
        result = json.dumps(ds.to_dict())
        assert "historical_rows" in result


class TestFCFEIntegration:
    def test_fcfe_blocks_net_borrowing_from_unpublishable_debt_schedule(self):
        """FCFE must not publish net borrowing from a low-confidence debt schedule."""
        from backend.analytics.fcfe import compute_fcfe, CostOfEquityAssumptions
        from backend.analytics.forecasting import run_forecast

        ft: dict = {
            "revenue.net": {"2023FY": 1000.0, "2024FY": 1100.0},
            "gross_profit.total": {"2023FY": 400.0, "2024FY": 440.0},
            "sga.total": {"2023FY": -200.0, "2024FY": -220.0},
            "depreciation.total": {"2023FY": 40.0, "2024FY": 44.0},
            "capex.total": {"2023FY": -30.0, "2024FY": -33.0},
            "interest_expense.total": {"2023FY": -5.0, "2024FY": -6.0},
            "profit_before_tax.total": {"2023FY": 195.0, "2024FY": 214.0},
            "net_income.parent": {"2023FY": 175.5, "2024FY": 192.6},
            "total_debt.ending": {"2023FY": 100.0, "2024FY": 150.0},
            "cash_and_equivalents.ending": {"2024FY": 50.0},
            "equity.parent": {"2024FY": 900.0},
            "total_assets.ending": {"2024FY": 1100.0},
            "eps.basic": {"2024FY": 9000.0},
        }
        forecast = run_forecast("TEST", ft, forecast_years=[2026, 2027])
        ds = build_debt_schedule(
            "TEST", ft,
            fy_periods=["2023FY", "2024FY"],
            forecast_labels=["2026F", "2027F"],
            forecast_years=[2026, 2027],
        )
        nb_schedule = ds.net_borrowing_schedule()

        re_asm = CostOfEquityAssumptions()
        result = compute_fcfe(
            "TEST", forecast, ft,
            net_borrowing_schedule=nb_schedule,
            cost_of_equity_assumptions=re_asm,
        )
        assert ds.is_fcfe_publishable is False
        assert all(fy.net_borrowing is None for fy in result.forecast_years)
        assert all(fy.fcfe is None for fy in result.forecast_years)
        assert result.target_price_vnd is None
