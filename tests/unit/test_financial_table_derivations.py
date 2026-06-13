"""Regression tests for financial table derivations used by the client report."""
from __future__ import annotations

import pytest

from backend.reporting.client_report_view_model import (
    _DASH,
    _VND_TO_BN,
    _table_bs_cf,
    _table_profitability_valuation,
    _table_valuation_model,
)
from backend.reporting.client_section_builder import _fmt_metric


def _fact(value_bn: float) -> dict[str, float]:
    return {"value": value_bn * _VND_TO_BN}


def _facts() -> dict[str, dict[str, dict[str, float]]]:
    return {
        "revenue.net": {"2025FY": _fact(1_000.0)},
        "gross_profit.total": {"2025FY": _fact(400.0)},
        "operating_profit.total": {"2025FY": _fact(250.0)},
        "depreciation.total": {"2025FY": _fact(30.0)},
        "net_income.parent": {"2025FY": _fact(200.0)},
        "equity.parent": {"2025FY": _fact(800.0)},
        "total_assets.ending": {"2025FY": _fact(1_200.0)},
        "short_term_debt.ending": {"2025FY": _fact(150.0)},
        "cash_and_equivalents.ending": {"2025FY": _fact(50.0)},
        "eps.basic": {"2025FY": {"value": 2_000.0}},
    }


def _rows(table):
    return {label: values for label, values in table.rows}


def test_historical_sga_and_ebitda_are_derived_when_direct_sga_is_missing() -> None:
    table = _table_valuation_model(_facts(), {}, {}, ["2025FY"], shares_mn=100.0)
    rows = _rows(table)

    assert rows["Chi phí bán hàng và quản lý"][0] == pytest.approx(-150.0)
    assert rows["EBITDA"][0] == pytest.approx(280.0)
    assert rows["Tỷ suất EBITDA"][0] == pytest.approx(0.28)


def test_historical_ebitda_is_derived_from_pbt_and_financial_expense_when_ebit_is_missing() -> None:
    facts = _facts()
    facts.pop("operating_profit.total")
    facts["profit_before_tax.total"] = {"2025FY": _fact(250.0)}
    facts["financial_expense.total"] = {"2025FY": _fact(-30.0)}

    table = _table_valuation_model(facts, {}, {}, ["2025FY"], shares_mn=100.0)
    rows = _rows(table)

    assert rows["Lợi nhuận từ HĐKD / EBIT"][0] == pytest.approx(280.0)
    assert rows["Chi phí bán hàng và quản lý"][0] == pytest.approx(-120.0)
    assert rows["EBITDA"][0] == pytest.approx(310.0)


def test_historical_net_debt_ebitda_roic_and_ev_ebitda_are_not_blank_when_inputs_exist() -> None:
    facts = _facts()
    bs = _rows(_table_bs_cf(facts, {}, {}, ["2025FY"], shares_mn=100.0))
    profitability = _rows(
        _table_profitability_valuation(
            facts,
            {},
            current_price=10_000.0,
            fcff={"wacc": 0.10, "wacc_breakdown": {"tax_rate": 0.20}},
            periods=["2025FY"],
            shares_mn=100.0,
            dividend_per_share=None,
        )
    )

    assert bs["Nợ ròng cuối năm (nợ vay có lãi - tiền)"][0] == pytest.approx(100.0)
    assert bs["Nợ ròng / EBITDA"][0] == pytest.approx(100.0 / 280.0)
    assert profitability["ROIC"][0] == pytest.approx(250.0 * 0.80 / 900.0)
    assert profitability["EV/EBITDA"][0] == pytest.approx(1_100.0 / 280.0)


def test_total_liabilities_falls_back_to_assets_minus_equity_when_direct_fact_is_missing() -> None:
    facts = _facts()
    table = _table_bs_cf(facts, {}, {}, ["2025FY"], shares_mn=100.0)
    rows = _rows(table)

    assert rows["Tổng nợ phải trả"][0] == pytest.approx(400.0)


def test_historical_delta_nwc_falls_back_to_indirect_cash_flow_components() -> None:
    facts = _facts()
    facts["operating_cash_flow.total"] = {"2025FY": _fact(180.0)}
    table = _table_bs_cf(facts, {}, {}, ["2025FY"], shares_mn=100.0)
    rows = _rows(table)

    assert rows["Thay đổi vốn lưu động"][0] == pytest.approx(200.0 + 30.0 - 180.0)


def test_near_zero_values_do_not_render_as_negative_zero() -> None:
    assert _fmt_metric("Thay đổi nợ vay có lãi", -0.04) == "0"
    assert _fmt_metric("Nợ ròng / EBITDA", -0.04) == "0.0x"
    assert _fmt_metric("Tăng trưởng doanh thu", -0.0001) == "0.0%"
    assert _fmt_metric("Dữ liệu thiếu", _DASH) == _DASH
