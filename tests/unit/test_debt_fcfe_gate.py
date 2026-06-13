"""Tests for debt schedule gate chain (plan §7 and §8)."""
from __future__ import annotations

import pytest
from backend.analytics.debt_schedule import (
    DebtSchedule,
    DebtScheduleRow,
    build_debt_schedule,
)
from backend.analytics.forecasting import run_forecast
from backend.analytics.fcfe import compute_fcfe, CostOfEquityAssumptions


def _make_schedule(method: str, confidence: str, labels=("2026F",)) -> DebtSchedule:
    rows = [
        DebtScheduleRow(
            year=2026 + i, label=lbl,
            beginning_interest_bearing_debt=40.0,
            ending_interest_bearing_debt=40.0,
            net_borrowing=0.0,
            method=method,  # type: ignore[arg-type]
            confidence=confidence,  # type: ignore[arg-type]
        )
        for i, lbl in enumerate(labels)
    ]
    return DebtSchedule(
        ticker="TST",
        historical_rows=[],
        forecast_rows=rows,
        forecast_method=method,  # type: ignore[arg-type]
    )


class TestIsfcfePublishable:
    def test_direct_cash_flow_high_is_publishable(self):
        ds = _make_schedule("direct_cash_flow", "high")
        assert ds.is_fcfe_publishable is True

    def test_zero_debt_policy_high_is_publishable(self):
        ds = _make_schedule("zero_debt_policy", "high")
        assert ds.is_fcfe_publishable is True

    def test_target_debt_ratio_low_is_blocked(self):
        ds = _make_schedule("target_debt_ratio", "low")
        assert ds.is_fcfe_publishable is False

    def test_balance_sheet_delta_medium_is_blocked(self):
        ds = _make_schedule("balance_sheet_delta", "medium")
        assert ds.is_fcfe_publishable is False

    def test_manual_override_medium_is_blocked(self):
        ds = _make_schedule("manual_override", "medium")
        assert ds.is_fcfe_publishable is False

    def test_manual_override_high_with_approval_is_publishable(self):
        ds = _make_schedule("manual_override", "high")
        ds.analyst_approved = True
        assert ds.is_fcfe_publishable is True
        assert ds.status == "approved"

    def test_missing_low_is_blocked(self):
        ds = _make_schedule("missing", "low")
        assert ds.is_fcfe_publishable is False

    def test_fcfe_block_reason_populated_when_blocked(self):
        ds = _make_schedule("target_debt_ratio", "low")
        reason = ds.fcfe_block_reason
        assert reason is not None
        assert "median" in reason.lower() or "historical" in reason.lower()

    def test_fcfe_block_reason_none_when_publishable(self):
        ds = _make_schedule("direct_cash_flow", "high")
        assert ds.fcfe_block_reason is None

    def test_to_dict_includes_publishable_flag(self):
        ds = _make_schedule("target_debt_ratio", "low")
        d = ds.to_dict()
        assert "is_fcfe_publishable" in d
        assert d["is_fcfe_publishable"] is False

    def test_net_borrowing_schedule_returns_none_for_missing(self):
        rows = [
            DebtScheduleRow(
                year=2026, label="2026F",
                beginning_interest_bearing_debt=None,
                ending_interest_bearing_debt=None,
                net_borrowing=None,
                method="missing", confidence="low",
            )
        ]
        ds = DebtSchedule("TST", [], rows, "missing")
        sched = ds.net_borrowing_schedule()
        assert sched["2026F"] is None   # explicit None, not 0.0

    def test_net_borrowing_schedule_safe_returns_zero_fallback(self):
        rows = [
            DebtScheduleRow(
                year=2026, label="2026F",
                beginning_interest_bearing_debt=None,
                ending_interest_bearing_debt=None,
                net_borrowing=None,
                method="missing", confidence="low",
            )
        ]
        ds = DebtSchedule("TST", [], rows, "missing")
        safe = ds.net_borrowing_schedule_safe()
        assert safe["2026F"] == 0.0


class TestFCFEGate:
    """When debt_schedule uses an unapproved model path, FCFE target_price must be None."""

    def _minimal_ft(self) -> dict:
        return {
            "revenue.net": {"2023FY": 1500.0, "2024FY": 1700.0, "2025FY": 1865.0},
            "gross_profit.total": {"2023FY": 680.0, "2024FY": 780.0, "2025FY": 884.0},
            "sga.total": {"2023FY": -350.0, "2024FY": -380.0, "2025FY": -418.0},
            "depreciation.total": {"2023FY": 40.0, "2024FY": 44.0, "2025FY": 48.0},
            "capex.total": {"2023FY": -80.0, "2024FY": -90.0, "2025FY": -100.0},
            "total_debt.ending": {"2025FY": 43.0},
            "cash_and_equivalents.ending": {"2025FY": 120.0},
            "equity.parent": {"2025FY": 1500.0},
            "total_assets.ending": {"2025FY": 2500.0},
            "profit_before_tax.total": {"2023FY": 290.0, "2024FY": 320.0, "2025FY": 346.0},
            "tax_expense.total": {"2023FY": -50.0, "2024FY": -55.0, "2025FY": -54.0},
            "net_income.parent": {"2023FY": 240.0, "2024FY": 265.0, "2025FY": 292.0},
        }

    def test_stable_debt_blocks_fcfe_target_price(self):
        """P0: historical_median_debt path MUST block FCFE publishable target price."""
        ft = self._minimal_ft()
        forecast = run_forecast("TST", ft, shares_mn=94.45)
        # forecast.debt_schedule uses stable_debt (no CFS data)
        assert forecast.debt_schedule is not None
        assert forecast.debt_schedule.forecast_method == "stable_debt"
        assert not forecast.debt_schedule.is_fcfe_publishable

        result = compute_fcfe(
            ticker="TST", forecast=forecast, fact_table=ft,
            shares_mn=94.45,
            cost_of_equity_assumptions=CostOfEquityAssumptions(re_override=0.14),
        )
        assert result.target_price_vnd is None
        assert any("BLOCKED" in w for w in result.warnings)
        assert all(row.fcfe is None for row in result.forecast_years)
        assert all(row.net_borrowing is None for row in result.forecast_years)

    def test_zero_debt_policy_allows_fcfe_target_price(self):
        """When company carries no debt (zero_debt_policy), FCFE must produce target price."""
        ft = self._minimal_ft()
        # Provide explicitly negligible debt (< 1 VND bn) → zero_debt_policy
        ft["total_debt.ending"] = {
            "2023FY": 0.0, "2024FY": 0.0, "2025FY": 0.0,
        }
        forecast = run_forecast("TST", ft, shares_mn=94.45)
        assert forecast.debt_schedule is not None
        assert forecast.debt_schedule.forecast_method == "zero_debt_policy"
        assert forecast.debt_schedule.is_fcfe_publishable

        result = compute_fcfe(
            ticker="TST", forecast=forecast, fact_table=ft,
            shares_mn=94.45,
            cost_of_equity_assumptions=CostOfEquityAssumptions(re_override=0.14),
        )
        assert result.target_price_vnd is not None
        assert result.target_price_vnd > 0

    def test_median_debt_blocking_test_item8(self):
        """Plan §8: if ending_debt == historical_median and not approved → block."""
        ft = self._minimal_ft()
        forecast = run_forecast("TST", ft, shares_mn=94.45)
        ds = forecast.debt_schedule
        assert ds is not None

        if ds.forecast_method == "stable_debt":
            # Verify net_borrowing is a low-confidence model path, not CFS-sourced.
            for row in ds.forecast_rows:
                assert row.method == "stable_debt"
                assert row.confidence == "low"
            assert not ds.is_fcfe_publishable

    def test_approval_flag_alone_does_not_make_fcfe_publishable(self):
        """An approval flag with NO analyst-supplied debt path must NOT launder the
        model's target_debt_ratio output into an approved manual_override. Approval is
        only meaningful against a concrete path; otherwise FCFE stays blocked
        (doctrine: no source → no claim; net_borrowing must be high-confidence)."""
        from backend.analytics.forecasting import ForecastAssumptions

        ft = self._minimal_ft()
        forecast = run_forecast(
            "TST",
            ft,
            shares_mn=94.45,
            assumptions=ForecastAssumptions(
                assumption_status="analyst_approved",
                debt_schedule_approved=True,
                manual_debt_path=None,
            ),
        )
        ds = forecast.debt_schedule
        assert ds is not None
        assert ds.forecast_method == "stable_debt"
        assert ds.is_fcfe_publishable is False

    def test_real_manual_debt_path_with_approval_is_publishable(self):
        """When the analyst DOES supply a concrete debt path and approves it, the
        schedule legitimately becomes an approved manual_override → FCFE publishable."""
        from backend.analytics.forecasting import ForecastAssumptions

        ft = self._minimal_ft()
        forecast = run_forecast(
            "TST",
            ft,
            shares_mn=94.45,
            assumptions=ForecastAssumptions(
                assumption_status="analyst_approved",
                debt_schedule_approved=True,
                manual_debt_path={"2026F": 100.0, "2027F": 100.0, "2028F": 100.0,
                                  "2029F": 100.0, "2030F": 100.0},
            ),
        )
        ds = forecast.debt_schedule
        assert ds is not None
        assert ds.forecast_method == "manual_override"
        assert ds.analyst_approved is True
        assert ds.is_fcfe_publishable is True

        result = compute_fcfe(
            ticker="TST",
            forecast=forecast,
            fact_table=ft,
            shares_mn=94.45,
            cost_of_equity_assumptions=CostOfEquityAssumptions(re_override=0.14),
        )
        assert result.target_price_vnd is not None
        assert result.target_price_vnd > 0


class TestBlendDraftWhenFCFEMissing:
    """When FCFE price is None, blend must be draft-only."""

    def test_blend_is_draft_when_fcfe_none(self):
        from backend.analytics.blend import blend_dcf
        result = blend_dcf(
            ticker="TST",
            price_fcff=60_000.0,
            price_fcfe=None,    # blocked (FCFE unavailable)
            current_price_vnd=50_000.0,
        )
        assert result.is_draft_only is True

    def test_blend_publishable_when_both_prices_present(self):
        from backend.analytics.blend import blend_dcf
        result = blend_dcf(
            ticker="TST",
            price_fcff=60_000.0,
            price_fcfe=58_000.0,  # gap ~3.4% within 25%
            current_price_vnd=50_000.0,
        )
        assert result.is_draft_only is False

class TestMinimumCashPolicy:
    def test_absolute_floor_used_when_no_revenue(self):
        from backend.analytics.cash_sweep import MinimumCashPolicy
        pol = MinimumCashPolicy(absolute_floor_bn=50.0, pct_of_revenue=0.05)
        assert pol.compute() == 50.0

    def test_revenue_pct_dominates_when_large(self):
        from backend.analytics.cash_sweep import MinimumCashPolicy
        pol = MinimumCashPolicy(absolute_floor_bn=50.0, pct_of_revenue=0.05)
        # 5% of 2000 = 100 > 50 → 100
        assert pol.compute(revenue_bn=2000.0) == 100.0

    def test_floor_dominates_when_revenue_small(self):
        from backend.analytics.cash_sweep import MinimumCashPolicy
        pol = MinimumCashPolicy(absolute_floor_bn=50.0, pct_of_revenue=0.05)
        # 5% of 800 = 40 < 50 → 50
        assert pol.compute(revenue_bn=800.0) == 50.0

    def test_check_minimum_cash_pass(self):
        from backend.analytics.cash_sweep import check_minimum_cash
        r = check_minimum_cash("2026F", ending_cash=120.0, minimum_cash=80.0)
        assert r["gate"] == "PASS"
        assert r["new_borrowing_required"] is False

    def test_check_minimum_cash_fail_triggers_borrowing(self):
        from backend.analytics.cash_sweep import check_minimum_cash
        r = check_minimum_cash("2026F", ending_cash=30.0, minimum_cash=80.0)
        assert r["gate"] == "WARN"
        assert r["new_borrowing_required"] is True
        assert r["shortfall"] == pytest.approx(50.0)
