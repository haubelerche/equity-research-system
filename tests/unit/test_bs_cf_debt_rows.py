"""Regression: the balance-sheet / cash-flow table presents the three distinct debt
layers correctly, and the change-rows are arithmetically right.

Covers the user concern: "are the values all negative across every year because of a
calculation error?" The answer is no — for a cash-rich issuer Δ net debt is negative
because cash accumulates, which is proven here via the identity
    Δ net debt = Δ interest-bearing debt − Δ cash.
The test also includes a rising-debt scenario to prove the signs are not hard-coded.
"""
from __future__ import annotations

import pytest

from backend.reporting.client_report_view_model import _table_bs_cf, _VND_TO_BN, _DASH

_BN = _VND_TO_BN  # raw VND per 1 tỷ đồng; facts are stored raw, scaled on read


def _facts(total_liab, ibd, cash):
    """Build an actual-period facts dict (values given in tỷ → stored raw VND)."""
    def col(d):
        return {p: {"value": v * _BN} for p, v in d.items()}
    return {
        "total_liabilities.ending": col(total_liab),
        "short_term_debt.ending": col(ibd),          # interest-bearing (no LT debt)
        "cash_and_equivalents.ending": col(cash),
    }


def _rows(table):
    return {label: vals for label, vals in table.rows}


# ---------------------------------------------------------------------------
# 1. Cash-rich issuer (DHG-like): 0 debt, growing cash → Δ net debt negative
# ---------------------------------------------------------------------------

class TestCashRichDebtLayers:
    periods = ["2024FY", "2025FY", "2026F", "2027F"]
    facts = _facts(
        total_liab={"2024FY": 1800.0, "2025FY": 1000.0},
        ibd={"2024FY": 600.0, "2025FY": 0.0},
        cash={"2024FY": 60.0, "2025FY": 130.0},
    )
    forecast_rows = {
        "2026F": {"total_debt": 0.0, "other_liabilities": 1000.0, "cash": 1400.0},
        "2027F": {"total_debt": 0.0, "other_liabilities": 1000.0, "cash": 2700.0},
    }

    def _table(self):
        return _table_bs_cf(self.facts, self.forecast_rows, {}, self.periods, shares_mn=100.0)

    def test_all_seven_debt_layers_present_in_order(self):
        labels = [label for label, _ in self._table().rows]
        expected_order = [
            "Tổng nợ phải trả",
            "Thay đổi tổng nợ phải trả",
            "Nợ vay có lãi cuối năm",
            "Thay đổi nợ vay có lãi",
            "Tiền và tương đương tiền",
            "Nợ ròng cuối năm (nợ vay có lãi - tiền)",
            "Thay đổi nợ ròng",
        ]
        # All present
        for lbl in expected_order:
            assert lbl in labels, f"missing row {lbl!r}"
        # And in this relative order
        idx = [labels.index(lbl) for lbl in expected_order]
        assert idx == sorted(idx), f"rows out of order: {idx}"

    def test_level_rows_exact_values(self):
        r = _rows(self._table())
        assert r["Tổng nợ phải trả"] == pytest.approx([1800, 1000, 1000, 1000])
        assert r["Nợ vay có lãi cuối năm"] == pytest.approx([600, 0, 0, 0])
        assert r["Tiền và tương đương tiền"] == pytest.approx([60, 130, 1400, 2700])
        # net debt = interest-bearing debt − cash
        assert r["Nợ ròng cuối năm (nợ vay có lãi - tiền)"] == pytest.approx([540, -130, -1400, -2700])

    def test_change_rows_exact_values(self):
        r = _rows(self._table())
        assert r["Thay đổi tổng nợ phải trả"] == [_DASH, pytest.approx(-800), pytest.approx(0), pytest.approx(0)]
        assert r["Thay đổi nợ vay có lãi"] == [_DASH, pytest.approx(-600), pytest.approx(0), pytest.approx(0)]
        assert r["Thay đổi nợ ròng"] == [_DASH, pytest.approx(-670), pytest.approx(-1270), pytest.approx(-1300)]

    def test_identity_net_debt_equals_debt_minus_cash(self):
        r = _rows(self._table())
        ibd = r["Nợ vay có lãi cuối năm"]
        cash = r["Tiền và tương đương tiền"]
        net = r["Nợ ròng cuối năm (nợ vay có lãi - tiền)"]
        for d, c, nd in zip(ibd, cash, net):
            assert nd == pytest.approx(d - c)

    def test_identity_delta_net_debt_equals_delta_debt_minus_delta_cash(self):
        """The crux: Δ net debt is negative because of CASH growth, not a sign bug."""
        r = _rows(self._table())
        ibd = r["Nợ vay có lãi cuối năm"]
        cash = r["Tiền và tương đương tiền"]
        d_net = r["Thay đổi nợ ròng"]
        for i in range(1, len(ibd)):
            d_debt = ibd[i] - ibd[i - 1]
            d_cash = cash[i] - cash[i - 1]
            assert d_net[i] == pytest.approx(d_debt - d_cash)
        # Forecast Δ net debt is negative ONLY because Δ debt = 0 while cash rises.
        assert all(ibd[i] - ibd[i - 1] == 0 for i in (2, 3))   # debt flat in forecast
        assert d_net[2] < 0 and d_net[3] < 0                    # yet Δ net debt negative

    def test_total_liabilities_never_below_interest_bearing_debt(self):
        r = _rows(self._table())
        for tl, ibd in zip(r["Tổng nợ phải trả"], r["Nợ vay có lãi cuối năm"]):
            assert tl >= ibd, "total liabilities must include interest-bearing debt"


# ---------------------------------------------------------------------------
# 2. Rising-debt scenario: proves signs are not hard-coded negative
# ---------------------------------------------------------------------------

class TestRisingDebtSigns:
    periods = ["2024FY", "2025F", "2026F"]
    facts = _facts(
        total_liab={"2024FY": 500.0},
        ibd={"2024FY": 100.0},
        cash={"2024FY": 50.0},
    )
    forecast_rows = {
        "2025F": {"total_debt": 300.0, "other_liabilities": 400.0, "cash": 50.0},
        "2026F": {"total_debt": 500.0, "other_liabilities": 400.0, "cash": 50.0},
    }

    def test_rising_debt_flat_cash_gives_positive_changes(self):
        table = _table_bs_cf(self.facts, self.forecast_rows, {}, self.periods, shares_mn=100.0)
        r = _rows(table)
        # Debt rises 100 → 300 → 500, cash flat at 50.
        assert r["Nợ vay có lãi cuối năm"] == pytest.approx([100, 300, 500])
        # Δ interest-bearing debt is POSITIVE when the company borrows.
        assert r["Thay đổi nợ vay có lãi"] == [_DASH, pytest.approx(200), pytest.approx(200)]
        # Net debt rises too (more debt, same cash) → Δ net debt POSITIVE.
        assert r["Nợ ròng cuối năm (nợ vay có lãi - tiền)"] == pytest.approx([50, 250, 450])
        assert r["Thay đổi nợ ròng"] == [_DASH, pytest.approx(200), pytest.approx(200)]
