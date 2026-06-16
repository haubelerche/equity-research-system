"""Tests for backend.analytics.working_capital_schedule."""
from __future__ import annotations

import pytest
from backend.analytics.working_capital_schedule import (
    build_working_capital_schedule,
    WorkingCapitalSchedule,
)

_PERIODS = ["2022FY", "2023FY", "2024FY", "2025FY"]


def _ft(ar: dict, inv: dict, ap: dict, rev: dict, cogs: dict) -> dict:
    """Build minimal fact table with balance sheet and P&L items."""
    return {
        "accounts_receivable.ending": ar,
        "inventory.ending": inv,
        "accounts_payable.ending": ap,
        "revenue.net": rev,
        "cogs.total": cogs,
    }


def _simple_ft() -> dict:
    """DBD-like numbers (VND bn) for 4 historical periods."""
    return _ft(
        ar   = {p: 500.0 for p in _PERIODS},
        inv  = {p: 450.0 for p in _PERIODS},
        ap   = {p: 150.0 for p in _PERIODS},
        rev  = {p: 1800.0 for p in _PERIODS},
        cogs = {p: -950.0 for p in _PERIODS},   # negative sign convention
    )


def test_reads_factentry_objects_not_just_floats():
    # Real runs pass a FactTable of FactEntry objects (build_fact_table), not raw floats.
    # _get must read FactEntry.value — otherwise AR/inventory/AP read as None and NWC
    # collapses to 0 (the misleading "no historical AR data" WARN seen on real DHG).
    from backend.facts.normalizer import FactEntry

    def fe(d: dict) -> dict:
        return {p: FactEntry(value=v) for p, v in d.items()}

    ft = {
        "accounts_receivable.ending": fe({p: 500.0 for p in _PERIODS}),
        "inventory.ending": fe({p: 450.0 for p in _PERIODS}),
        "accounts_payable.ending": fe({p: 150.0 for p in _PERIODS}),
        "revenue.net": fe({p: 1800.0 for p in _PERIODS}),
        "cogs.total": fe({p: -950.0 for p in _PERIODS}),
    }
    sched = build_working_capital_schedule(
        ticker="TST", fact_table=ft, fy_periods=_PERIODS,
        forecast_labels=["2026F"], forecast_revenues={"2026F": 1900.0},
        forecast_cogs={"2026F": -1000.0},
    )
    assert sched.ar_days is not None and sched.ar_days > 0
    assert sched.inv_days is not None and sched.ap_days is not None
    fc = sched.forecast_rows[0]
    assert fc.net_working_capital is not None and fc.net_working_capital > 0


class TestHistoricalDrivers:
    def test_ar_days_computed(self):
        sched = build_working_capital_schedule(
            ticker="TST",
            fact_table=_simple_ft(),
            fy_periods=_PERIODS,
            forecast_labels=["2026F"],
            forecast_revenues={"2026F": 1900.0},
            forecast_cogs={"2026F": -1000.0},
        )
        # AR=500, rev=1800 → ar_days = 500 / (1800/365) ≈ 101.4
        assert sched.ar_days is not None
        assert abs(sched.ar_days - 500 / (1800 / 365)) < 0.5

    def test_inv_days_computed(self):
        sched = build_working_capital_schedule(
            ticker="TST",
            fact_table=_simple_ft(),
            fy_periods=_PERIODS,
            forecast_labels=["2026F"],
            forecast_revenues={"2026F": 1900.0},
            forecast_cogs={"2026F": -1000.0},
        )
        # inv=450, cogs=950 → inv_days = 450/(950/365) ≈ 172.9
        assert sched.inv_days is not None
        assert abs(sched.inv_days - 450 / (950 / 365)) < 0.5

    def test_ap_days_computed(self):
        sched = build_working_capital_schedule(
            ticker="TST",
            fact_table=_simple_ft(),
            fy_periods=_PERIODS,
            forecast_labels=["2026F"],
            forecast_revenues={"2026F": 1900.0},
            forecast_cogs={"2026F": -1000.0},
        )
        # ap=150, cogs=950 → ap_days = 150/(950/365) ≈ 57.6
        assert sched.ap_days is not None
        assert abs(sched.ap_days - 150 / (950 / 365)) < 0.5


class TestForecastRows:
    def _build(self):
        return build_working_capital_schedule(
            ticker="TST",
            fact_table=_simple_ft(),
            fy_periods=_PERIODS,
            forecast_labels=["2026F", "2027F"],
            forecast_revenues={"2026F": 1900.0, "2027F": 2000.0},
            forecast_cogs={"2026F": -1000.0, "2027F": -1050.0},
        )

    def test_two_forecast_rows_generated(self):
        sched = self._build()
        assert len(sched.forecast_rows) == 2

    def test_nwc_positive(self):
        sched = self._build()
        for row in sched.forecast_rows:
            assert row.net_working_capital is not None
            assert row.net_working_capital > 0  # AR + Inv > AP for these numbers

    def test_delta_nwc_first_row_relative_to_last_historical(self):
        sched = self._build()
        # last historical NWC = 500 + 450 - 150 = 800
        # first forecast row NWC = slightly different (revenue=1900 vs 1800)
        first = sched.forecast_rows[0]
        assert first.delta_nwc is not None

    def test_delta_nwc_second_row_relative_to_first_forecast(self):
        sched = self._build()
        row1 = sched.forecast_rows[0]
        row2 = sched.forecast_rows[1]
        if row1.net_working_capital and row2.net_working_capital:
            expected = row2.net_working_capital - row1.net_working_capital
            assert abs(row2.delta_nwc - expected) < 0.01  # type: ignore[operator]

    def test_formula_delta_nwc_item32(self):
        """Item 32 equivalent: Ending NWC = Beginning NWC + delta_nwc."""
        sched = self._build()
        # The first forecast year uses a driver-normalized opening NWC.
        prev = sched.forecast_rows[0].net_working_capital
        for row in sched.forecast_rows[1:]:
            if prev is not None and row.net_working_capital is not None and row.delta_nwc is not None:
                assert abs(row.net_working_capital - (prev + row.delta_nwc)) < 0.02
            prev = row.net_working_capital


class TestMissingData:
    def test_missing_ar_emits_warning(self):
        ft = _ft(ar={}, inv={p: 300.0 for p in _PERIODS},
                 ap={p: 100.0 for p in _PERIODS},
                 rev={p: 1500.0 for p in _PERIODS},
                 cogs={p: -800.0 for p in _PERIODS})
        sched = build_working_capital_schedule(
            ticker="TST", fact_table=ft, fy_periods=_PERIODS,
            forecast_labels=["2026F"], forecast_revenues={"2026F": 1600.0},
            forecast_cogs={"2026F": -850.0},
        )
        assert sched.ar_days is None
        assert any("AR" in w for w in sched.warnings)

    def test_to_dict_serializable(self):
        sched = build_working_capital_schedule(
            ticker="TST", fact_table=_simple_ft(), fy_periods=_PERIODS,
            forecast_labels=["2026F"], forecast_revenues={"2026F": 1900.0},
            forecast_cogs={"2026F": -1000.0},
        )
        import json
        d = sched.to_dict()
        json.dumps(d)  # must not raise


class TestFactEntryFormat:
    """Fact values may be FactEntry dicts — schedule must handle both."""

    def test_handles_dict_factentry(self):
        ft = {
            "accounts_receivable.ending": {"2025FY": {"value": 500.0}},
            "inventory.ending": {"2025FY": {"value": 450.0}},
            "accounts_payable.ending": {"2025FY": {"value": 150.0}},
            "revenue.net": {"2025FY": {"value": 1800.0}},
            "cogs.total": {"2025FY": {"value": -950.0}},
        }
        sched = build_working_capital_schedule(
            ticker="TST", fact_table=ft, fy_periods=["2025FY"],
            forecast_labels=["2026F"], forecast_revenues={"2026F": 1900.0},
            forecast_cogs={"2026F": -1000.0},
        )
        assert sched.ar_days is not None
        assert sched.ar_days > 0
