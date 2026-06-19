"""Forecast CAPEX must taper toward maintenance (D&A) and equal D&A in terminal.

Root cause (2026-06-19): CAPEX was projected at a flat historical-median ratio
every year. For companies exiting an investment phase (one-time factory/plant
build) that median is inflated, so the model projects heavy CAPEX in perpetuity
while earning a single-digit EBIT margin — terminal FCFF goes negative and the
DCF target collapses or disappears.

Fix (user-approved): taper CAPEX/revenue from the historical level toward
maintenance CAPEX (~D&A) across the explicit forecast, with the terminal (last)
year at CAPEX = D&A — the sustainable steady state.
"""
from __future__ import annotations

import pytest

from backend.analytics.forecasting import run_forecast
from backend.facts.normalizer import FactTable


def _capex_heavy_fact_table() -> FactTable:
    """Flat revenue, 30% gross / 15% EBIT, D&A ~1%, but CAPEX ~10% of revenue."""
    rev = {p: 1000.0 for p in ("2022FY", "2023FY", "2024FY", "2025FY")}
    return {
        "revenue.net": rev,
        "gross_profit.total": {p: 300.0 for p in rev},
        "ebit.total": {p: 150.0 for p in rev},
        "depreciation.total": {p: 10.0 for p in rev},   # 1% of revenue (maintenance)
        "capex.total": {p: -100.0 for p in rev},         # 10% of revenue (inflated)
        "profit_before_tax.total": {p: 145.0 for p in rev},
        "tax_expense.total": {p: -29.0 for p in rev},
    }


def _old_capex_spike_fact_table() -> FactTable:
    rev = {p: 1000.0 for p in ("2022FY", "2023FY", "2024FY", "2025FY")}
    table = {
        "revenue.net": rev,
        "gross_profit.total": {p: 300.0 for p in rev},
        "ebit.total": {p: 150.0 for p in rev},
        "depreciation.total": {p: 20.0 for p in rev},
        "capex.total": {
            "2022FY": -200.0,
            "2023FY": -180.0,
            "2024FY": -30.0,
            "2025FY": -30.0,
        },
        "profit_before_tax.total": {p: 145.0 for p in rev},
        "tax_expense.total": {p: -29.0 for p in rev},
    }
    return table


class TestCapexTapersToMaintenance:
    def test_terminal_capex_equals_depreciation(self):
        table = _capex_heavy_fact_table()
        art = run_forecast("CAPHVY", table, n_years=5)
        terminal = art.forecast_years[-1]
        assert terminal.capex is not None and terminal.depreciation is not None
        # Terminal CAPEX (outflow, stored negative) magnitude == D&A.
        assert abs(abs(terminal.capex) - terminal.depreciation) < 0.01, (
            f"Terminal CAPEX {abs(terminal.capex):.2f} should equal D&A "
            f"{terminal.depreciation:.2f} (maintenance steady state)"
        )

    def test_capex_ratio_declines_monotonically(self):
        table = _capex_heavy_fact_table()
        art = run_forecast("CAPHVY", table, n_years=5)
        ratios = [abs(fy.capex) / fy.revenue for fy in art.forecast_years]
        for earlier, later in zip(ratios, ratios[1:]):
            assert later <= earlier + 1e-9, (
                f"CAPEX/revenue should taper down, got sequence {ratios}"
            )
        # And it must actually move (not flat) when historical > maintenance.
        assert ratios[0] > ratios[-1] + 1e-6

    def test_first_year_starts_near_historical_level(self):
        table = _capex_heavy_fact_table()
        art = run_forecast("CAPHVY", table, n_years=5)
        first = art.forecast_years[0]
        assert abs(abs(first.capex) / first.revenue - 0.10) < 0.005, (
            "First forecast year CAPEX/revenue should start near the historical 10%"
        )

    def test_first_year_uses_recent_capex_not_old_spike_median(self):
        table = _old_capex_spike_fact_table()
        art = run_forecast("CAPOLD", table, n_years=5)
        first = art.forecast_years[0]
        ratio = abs(first.capex) / first.revenue
        assert ratio == pytest.approx(0.03)
        assert art.drivers["capex_to_revenue"]["method"] == "recent_to_maintenance_taper"

    def test_terminal_fcff_not_dragged_negative_by_capex(self):
        """With CAPEX→D&A in terminal, NOPAT-based FCFF stays positive."""
        table = _capex_heavy_fact_table()
        art = run_forecast("CAPHVY", table, n_years=5)
        t = art.forecast_years[-1]
        nopat = (t.ebit or 0) * 0.8
        fcff = nopat + t.depreciation - abs(t.capex)  # ΔNWC ~0 with flat revenue
        assert fcff > 0, f"Terminal FCFF should be positive, got {fcff:.2f}"
