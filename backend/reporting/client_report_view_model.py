"""Client-facing report content manifest.

This module builds a deterministic, renderer-ready view model for professional
PDF output. It deliberately separates client/analyst report content from
internal governance artifacts, so templates never need to inspect raw gate,
trace, or validation payloads.
"""
from __future__ import annotations

import glob
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from backend.reporting.report_data_loader import _COMPANIES, ROOT

_logger = logging.getLogger(__name__)

RenderMode = Literal["client_final", "analyst_draft", "internal_debug"]


class ClientReportDataMissing(Exception):
    """Raised when a client-final report lacks required publishable fields."""

    def __init__(self, missing_fields: list[str], affected_sections: list[str]) -> None:
        self.missing_fields = missing_fields
        self.affected_sections = affected_sections
        super().__init__(
            "Missing required client report data: " + ", ".join(missing_fields)
        )


@dataclass(frozen=True)
class Money:
    amount: float
    currency: str = "VND"


@dataclass(frozen=True)
class Percent:
    value: float


@dataclass(frozen=True)
class TableData:
    title: str
    periods: list[str]
    rows: list[tuple[str, list[Any]]]
    unit: str = ""


@dataclass(frozen=True)
class ChartArtifact:
    chart_id: str
    title: str
    path: str
    caption: str
    required: bool = False


@dataclass
class ClientReportViewModel:
    ticker: str
    company_name: str
    exchange: str
    sector: str
    report_date: str
    report_title: str
    recommendation: str
    current_price: Money | None
    target_price: Money | None
    upside_downside: Percent | None
    dividend_yield: Percent | None
    total_return: Percent | None
    market_statistics: dict[str, Any]
    ownership_table: TableData
    trading_performance_table: TableData
    financial_summary_table: TableData
    valuation_model_table: TableData
    balance_sheet_cashflow_table: TableData
    profitability_valuation_table: TableData
    peer_table: TableData | None
    catalyst_table: TableData | None
    risk_table: TableData
    charts: dict[str, ChartArtifact]
    source_captions: dict[str, str]
    disclaimer: str
    investment_thesis: str
    latest_business_update: str
    key_growth_drivers: str
    key_margin_drivers: str
    material_events: str
    current_context: str
    key_forecast_drivers_table: TableData
    sensitivity_table: TableData
    forecast_valuation_narrative: str
    mode: RenderMode
    publication_status: str
    missing_required_fields: list[str] = field(default_factory=list)


_DASH = "—"
_PERIODS_FALLBACK = ["2024A", "2025A", "2026F", "2027F", "2028F"]


def _derive_periods(facts: dict[str, dict[str, float]]) -> list[str]:
    """Derive period labels from fact keys. Falls back to MVP default if empty."""
    if not facts:
        return list(_PERIODS_FALLBACK)
    all_periods: set[str] = set()
    for metric_dict in facts.values():
        if isinstance(metric_dict, dict):
            all_periods.update(metric_dict.keys())
    fy_periods = sorted(p for p in all_periods if p.endswith(("FY", "A")))
    return fy_periods if fy_periods else list(_PERIODS_FALLBACK)


def _derive_shares_mn(facts: dict[str, dict[str, float]], periods: list[str]) -> float:
    """Shares outstanding in millions from canonical facts. 0.0 if unavailable."""
    shares_fact = facts.get("shares_outstanding.total", {})
    for p in reversed(periods):
        v = shares_fact.get(p)
        if v and v > 0:
            return v / 1_000_000
    return 0.0


def _derive_dividend_per_share(facts: dict[str, dict[str, float]], periods: list[str]) -> float | None:
    """Cash dividend per share from canonical facts, or None if unavailable."""
    div_fact = facts.get("dividends_per_share.cash", {})
    for p in reversed(periods):
        v = div_fact.get(p)
        if v and v > 0:
            return v
    return None


def _latest_json(pattern: str) -> dict[str, Any]:
    files = sorted(glob.glob(str(ROOT / pattern)))
    if not files:
        return {}
    with open(files[-1], encoding="utf-8") as f:
        return json.load(f)


def _resolve_json(pattern: str, manifest=None, key: str = "") -> dict[str, Any]:
    """Manifest-first artifact resolution; falls back to glob with DeprecationWarning."""
    import warnings as _w
    if manifest is not None and key:
        return manifest.load_json(key)
    _w.warn(
        f"No run_id — resolving '{key or pattern}' via glob. "
        "Pass run_id= to build_client_report_view_model() for reproducibility.",
        DeprecationWarning,
        stacklevel=4,
    )
    files = sorted(glob.glob(str(ROOT / pattern)))
    if not files:
        return {}
    with open(files[-1], encoding="utf-8") as f:
        return json.load(f)


def _facts(ticker: str, manifest=None) -> dict[str, dict[str, float]]:
    return _resolve_json(f"artifacts/facts/{ticker}_*_fact_report.json", manifest, "facts").get("facts", {})


def _valuation(ticker: str, manifest=None) -> dict[str, Any]:
    return _resolve_json(f"artifacts/valuation/{ticker}_*_valuation.json", manifest, "valuation")


def _valuation_result(ticker: str, manifest=None) -> dict[str, Any]:
    return _resolve_json(f"artifacts/valuation_results/*_{ticker}_valuation_result.json", manifest, "valuation_result")


def _forecast(ticker: str, manifest=None) -> dict[str, Any]:
    return _resolve_json(f"artifacts/forecast/{ticker}_*_forecast.json", manifest, "forecast")


def _fcff(ticker: str, manifest=None) -> dict[str, Any]:
    return _resolve_json(f"artifacts/forecast/{ticker}_*_fcff.json", manifest, "fcff")


def _blend(ticker: str, manifest=None) -> dict[str, Any]:
    return _resolve_json(f"artifacts/forecast/{ticker}_*_blend.json", manifest, "blend")


def _fact_value(facts: dict[str, dict[str, float]], metric: str, period: str) -> float | None:
    """Return a float fact value — handles both flat (DBD) and nested-dict (DHG) formats."""
    raw = facts.get(metric, {}).get(period)
    if raw is None:
        return None
    if isinstance(raw, dict):
        v = raw.get("value")
        return float(v) if v is not None else None
    return float(raw)


def _forecast_by_label(forecast: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(r.get("label")): r for r in forecast.get("forecast_years", []) if isinstance(r, dict)}


def _fcff_by_label(fcff: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(r.get("label")): r for r in fcff.get("fcff_table", []) if isinstance(r, dict)}


def _period_value(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    metric: str,
    period: str,
) -> float | None:
    actual_map = {
        "revenue": "revenue.net",
        "cogs": "cogs.total",
        "gross_profit": "gross_profit.total",
        "depreciation": "depreciation.total",
        "sga": "sga.total",
        "interest_expense": "interest_expense.total",
        "tax": "tax_expense.total",
        "net_income": "net_income.parent",
        "cfo": "operating_cash_flow.total",
        "capex": "capex.total",
        "fcf": "free_cash_flow.total",
        "equity": "equity.parent",
        "total_assets": "total_assets.ending",
        "cash": "cash_and_equivalents.ending",
        "debt": "short_term_debt.ending",
        "eps": "eps.basic",
    }
    if period.endswith("A"):
        fact_period = period.replace("A", "FY")
        value = _fact_value(facts, actual_map.get(metric, metric), fact_period)
        if value is None:
            return None
        return value
    row = forecast_rows.get(period, {})
    forecast_map = {
        "revenue": "revenue",
        "cogs": "cogs",
        "gross_profit": "gross_profit",
        "depreciation": "depreciation",
        "sga": "sga",
        "interest_expense": "interest_expense",
        "tax": "tax_expense",
        "net_income": "net_income",
        "capex": "capex",
        "equity": "equity",
        "total_assets": "total_assets",
        "debt": "total_debt",
        "eps": "eps",
    }
    value = row.get(forecast_map.get(metric, metric))
    if value is None:
        return None
    return float(value)


def _pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return current / previous - 1


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _row_values(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    metric: str,
    periods: list[str],
) -> list[float | None]:
    return [_period_value(facts, forecast_rows, metric, period) for period in periods]


def _revenue_growth(facts: dict[str, dict[str, float]], forecast_rows: dict[str, dict[str, Any]], periods: list[str]) -> list[float | None]:
    values = _row_values(facts, forecast_rows, "revenue", periods)
    # Use the period one step before the first in periods as the baseline
    prev_period = periods[0].replace("A", "FY") if periods else "2023FY"
    prev_metric_year = str(int(prev_period[:4]) - 1) + prev_period[4:]
    prev_val = _fact_value(facts, "revenue.net", prev_metric_year)
    previous_values = [prev_val] + values[:-1]
    return [_pct_change(v, prev) for v, prev in zip(values, previous_values)]


def _net_profit_growth(facts: dict[str, dict[str, float]], forecast_rows: dict[str, dict[str, Any]], periods: list[str]) -> list[float | None]:
    values = _row_values(facts, forecast_rows, "net_income", periods)
    prev_period = periods[0].replace("A", "FY") if periods else "2023FY"
    prev_metric_year = str(int(prev_period[:4]) - 1) + prev_period[4:]
    prev_val = _fact_value(facts, "net_income.parent", prev_metric_year)
    previous_values = [prev_val] + values[:-1]
    return [_pct_change(v, prev) for v, prev in zip(values, previous_values)]


def _eps_growth(facts: dict[str, dict[str, float]], forecast_rows: dict[str, dict[str, Any]], periods: list[str]) -> list[float | None]:
    values = _row_values(facts, forecast_rows, "eps", periods)
    prev_period = periods[0].replace("A", "FY") if periods else "2023FY"
    prev_metric_year = str(int(prev_period[:4]) - 1) + prev_period[4:]
    prev_val = _fact_value(facts, "eps.basic", prev_metric_year)
    previous_values = [prev_val] + values[:-1]
    return [_pct_change(v, prev) for v, prev in zip(values, previous_values)]


def _roe(facts: dict[str, dict[str, float]], forecast_rows: dict[str, dict[str, Any]], periods: list[str]) -> list[float | None]:
    return [
        _safe_div(ni, eq)
        for ni, eq in zip(
            _row_values(facts, forecast_rows, "net_income", periods),
            _row_values(facts, forecast_rows, "equity", periods),
        )
    ]


def _roa(facts: dict[str, dict[str, float]], forecast_rows: dict[str, dict[str, Any]], periods: list[str]) -> list[float | None]:
    return [
        _safe_div(ni, assets)
        for ni, assets in zip(
            _row_values(facts, forecast_rows, "net_income", periods),
            _row_values(facts, forecast_rows, "total_assets", periods),
        )
    ]


def _ebit_values(forecast_rows: dict[str, dict[str, Any]], facts: dict[str, dict[str, float]], periods: list[str]) -> list[float | None]:
    ebit: list[float | None] = []
    for period in periods:
        if period.endswith("F"):
            value = forecast_rows.get(period, {}).get("ebit")
        else:
            revenue = _period_value(facts, forecast_rows, "revenue", period)
            cogs = _period_value(facts, forecast_rows, "cogs", period)
            sga = _period_value(facts, forecast_rows, "sga", period)
            value = None if None in (revenue, cogs, sga) else revenue + cogs + sga
        ebit.append(value)
    return ebit


def _ebitda_values(forecast_rows: dict[str, dict[str, Any]], facts: dict[str, dict[str, float]], periods: list[str]) -> list[float | None]:
    ebit = _ebit_values(forecast_rows, facts, periods)
    depreciation = _row_values(facts, forecast_rows, "depreciation", periods)
    return [None if e is None or d is None else e + d for e, d in zip(ebit, depreciation)]


def _fcff_values(facts: dict[str, dict[str, float]], fcff_rows: dict[str, dict[str, Any]], periods: list[str]) -> list[float | None]:
    # Actual periods: those ending in "A"; forecast: those ending in "F"
    actual_periods = [p for p in periods if p.endswith("A")]
    forecast_periods = [p for p in periods if p.endswith("F")]
    actual = [_fact_value(facts, "free_cash_flow.total", p.replace("A", "FY")) for p in actual_periods]
    forecast = [fcff_rows.get(period, {}).get("fcff") for period in forecast_periods]
    return actual + forecast


def _delta_nwc_values(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    fcff_rows: dict[str, dict[str, Any]],
    periods: list[str],
) -> list[float | None]:
    actual: list[float | None] = []
    actual_periods = [p for p in periods if p.endswith("A")]
    forecast_periods = [p for p in periods if p.endswith("F")]
    for period in actual_periods:
        ni = _period_value(facts, forecast_rows, "net_income", period)
        dep = _period_value(facts, forecast_rows, "depreciation", period)
        cfo = _period_value(facts, forecast_rows, "cfo", period)
        actual.append(None if None in (ni, dep, cfo) else ni + dep - cfo)
    forecast = [fcff_rows.get(period, {}).get("delta_nwc") for period in forecast_periods]
    return actual + forecast


def _cfo_values(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    fcff_rows: dict[str, dict[str, Any]],
    periods: list[str],
) -> list[float | None]:
    actual_periods = [p for p in periods if p.endswith("A")]
    forecast_periods = [p for p in periods if p.endswith("F")]
    actual = [
        _fact_value(facts, "operating_cash_flow.total", p.replace("A", "FY"))
        for p in actual_periods
    ]
    forecast: list[float | None] = []
    for period in forecast_periods:
        row = forecast_rows.get(period, {})
        fcff_row = fcff_rows.get(period, {})
        ni = row.get("net_income")
        dep = row.get("depreciation")
        delta_nwc = fcff_row.get("delta_nwc")
        forecast.append(None if None in (ni, dep, delta_nwc) else ni + dep - delta_nwc)
    return actual + forecast


def _cash_values(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    fcff_rows: dict[str, dict[str, Any]],
    periods: list[str],
    shares_mn: float,
    dividend_per_share: float | None,
) -> list[float | None]:
    actual_periods = [p for p in periods if p.endswith("A")]
    forecast_periods = [p for p in periods if p.endswith("F")]
    values: list[float | None] = [
        _fact_value(facts, "cash_and_equivalents.ending", p.replace("A", "FY"))
        for p in actual_periods
    ]
    prior = (values[-1] if values else None) or 0.0
    annual_dividend = shares_mn * (dividend_per_share or 0.0) / 1000.0
    for period in forecast_periods:
        fcff_value = fcff_rows.get(period, {}).get("fcff")
        capex = abs(forecast_rows.get(period, {}).get("capex") or 0.0)
        if fcff_value is None:
            values.append(None)
            continue
        # Cash bridge is intentionally conservative: FCFF after capex funds dividends,
        # while large expansion capex pressure is highlighted through the capex line.
        prior = max(0.0, prior + fcff_value - annual_dividend)
        values.append(prior + 0.0 * capex)
    return values


def _net_debt_values(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    fcff_rows: dict[str, dict[str, Any]],
    periods: list[str],
    shares_mn: float,
    dividend_per_share: float | None,
) -> list[float | None]:
    debt = _row_values(facts, forecast_rows, "debt", periods)
    cash = _cash_values(facts, forecast_rows, fcff_rows, periods, shares_mn, dividend_per_share)
    return [None if d is None or c is None else d - c for d, c in zip(debt, cash)]


def _finance_income_values(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    periods: list[str],
) -> list[float | None]:
    ebit = _ebit_values(forecast_rows, facts, periods)
    interest = _row_values(facts, forecast_rows, "interest_expense", periods)
    result: list[float | None] = []
    for i, period in enumerate(periods):
        if period.endswith("A"):
            pbt = _fact_value(facts, "profit_before_tax.total", period.replace("A", "FY"))
        else:
            pbt = forecast_rows.get(period, {}).get("profit_before_tax")
        result.append(None if None in (pbt, ebit[i], interest[i]) else pbt - ebit[i] - interest[i])
    return result


def _peg_values(pe: list[float | None], eps_growth: list[float | None]) -> list[float | None]:
    values: list[float | None] = []
    for multiple, growth in zip(pe, eps_growth):
        if multiple is None or growth in (None, 0):
            values.append(None)
        else:
            values.append(multiple / (growth * 100.0))
    return values


def _market_price_inputs(mode: RenderMode, val_result: dict[str, Any], blend: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    if mode == "client_final":
        current = float(val_result.get("current_price") or 0) or None
        target = float(val_result.get("target_price") or 0) or None
        upside = float(val_result.get("upside_downside") or 0) or None
        return current, target, upside
    current = float(blend.get("current_price_vnd") or 0) or None
    target = float(blend.get("target_price_dcf_vnd") or 0) or None
    upside_raw = blend.get("upside_pct")
    upside = float(upside_raw) if upside_raw is not None else None
    return current, target, upside


def _recommendation(upside: float | None, mode: RenderMode) -> str:
    if upside is None:
        return "ĐANG HOÀN THIỆN" if mode != "client_final" else "CHƯA XUẤT BẢN"
    if upside > 0.20:
        return "MUA"
    if upside < -0.20:
        return "BÁN"
    return "GIỮ"


def _table_financial_summary(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    current_price: float | None,
    periods: list[str],
    dividend_per_share: float | None,
) -> TableData:
    n = len(periods)
    forecast_periods = [p for p in periods if p.endswith("F")]
    actual_count = n - len(forecast_periods)
    eps = _row_values(facts, forecast_rows, "eps", periods)
    equity = _row_values(facts, forecast_rows, "equity", periods)
    shares = [
        None if e in (None, 0) or bvps in (None, 0) else e * 1_000_000_000 / bvps
        for e, bvps in zip(equity, [None] * actual_count + [forecast_rows.get(p, {}).get("bvps") for p in forecast_periods])
    ]
    pe = [None if current_price is None or e in (None, 0) else current_price / e for e in eps]
    pb = [None if current_price is None or eq in (None, 0) or sh in (None, 0) else current_price / (eq * 1_000_000_000 / sh) for eq, sh in zip(equity, shares)]
    return TableData(
        title="TÓM TẮT TÀI CHÍNH",
        periods=periods,
        unit="Đơn vị: tỷ đồng, trừ khi có ghi chú khác",
        rows=[
            ("Doanh thu thuần", _row_values(facts, forecast_rows, "revenue", periods)),
            ("Tăng trưởng doanh thu", _revenue_growth(facts, forecast_rows, periods)),
            ("Lợi nhuận ròng", _row_values(facts, forecast_rows, "net_income", periods)),
            ("Tăng trưởng lợi nhuận", _net_profit_growth(facts, forecast_rows, periods)),
            ("EPS điều chỉnh (VND)", eps),
            ("Tăng trưởng EPS", _eps_growth(facts, forecast_rows, periods)),
            ("ROE", _roe(facts, forecast_rows, periods)),
            ("ROA", _roa(facts, forecast_rows, periods)),
            ("Nợ ròng / EBITDA", [_DASH] * n),
            ("P/E", pe),
            ("P/B", pb),
            ("Cổ tức/cp", [dividend_per_share] * n),
            ("Suất sinh lợi cổ tức", [_DASH] * n),
        ],
    )


def _table_valuation_model(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    fcff_rows: dict[str, dict[str, Any]],
    periods: list[str],
    shares_mn: float,
) -> TableData:
    n = len(periods)
    revenue = _row_values(facts, forecast_rows, "revenue", periods)
    ebit = _ebit_values(forecast_rows, facts, periods)
    depreciation = _row_values(facts, forecast_rows, "depreciation", periods)
    ebitda = _ebitda_values(forecast_rows, facts, periods)
    net_income = _row_values(facts, forecast_rows, "net_income", periods)
    tax = _row_values(facts, forecast_rows, "tax", periods)
    pbt = [None if ni is None or tx is None else ni - tx for ni, tx in zip(net_income, tax)]
    shares = [shares_mn] * n
    return TableData(
        title="MÔ HÌNH ĐỊNH GIÁ",
        periods=periods,
        unit="Đơn vị: tỷ đồng nếu không có ghi chú khác",
        rows=[
            ("Doanh thu thuần", revenue),
            ("Tăng trưởng doanh thu", _revenue_growth(facts, forecast_rows, periods)),
            ("GVHB trừ khấu hao", _row_values(facts, forecast_rows, "cogs", periods)),
            ("Chi phí bán hàng và quản lý", _row_values(facts, forecast_rows, "sga", periods)),
            ("Doanh thu tài chính", [_DASH] * n),
            ("Chi phí tài chính", _row_values(facts, forecast_rows, "interest_expense", periods)),
            ("EBITDA", ebitda),
            ("Tỷ suất EBITDA", [_safe_div(e, r) for e, r in zip(ebitda, revenue)]),
            ("Khấu hao", depreciation),
            ("Lợi nhuận từ HĐKD / EBIT", ebit),
            ("Biên lợi nhuận HĐKD / EBIT margin", [_safe_div(e, r) for e, r in zip(ebit, revenue)]),
            ("Lợi nhuận khác", [_DASH] * n),
            ("Chi phí lãi vay ròng", _row_values(facts, forecast_rows, "interest_expense", periods)),
            ("Thuế", tax),
            ("Thuế suất thực tế", [_safe_div(abs(tx) if tx is not None else None, p) for tx, p in zip(tax, pbt)]),
            ("LNST sau CĐKKS / LNST CĐ mẹ", net_income),
            ("Tiền mặt từ hoạt động kinh doanh", _cfo_values(facts, forecast_rows, fcff_rows, periods)),
            ("Số lượng cổ phiếu (triệu)", shares),
            ("EPS", _row_values(facts, forecast_rows, "eps", periods)),
            ("EPS hiệu chỉnh", _row_values(facts, forecast_rows, "eps", periods)),
            ("Tăng trưởng EPS hiệu chỉnh", _eps_growth(facts, forecast_rows, periods)),
        ],
    )


def _table_bs_cf(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    fcff_rows: dict[str, dict[str, Any]],
    periods: list[str],
    shares_mn: float,
) -> TableData:
    n = len(periods)
    actual_periods = [p for p in periods if p.endswith("A")]
    forecast_periods = [p for p in periods if p.endswith("F")]
    fcff_vals = [None] * len(actual_periods) + [fcff_rows.get(p, {}).get("fcff") for p in forecast_periods]
    delta_nwc = [None] * len(actual_periods) + [fcff_rows.get(p, {}).get("delta_nwc") for p in forecast_periods]
    capex = _row_values(facts, forecast_rows, "capex", periods)
    debt = _row_values(facts, forecast_rows, "debt", periods)
    cash = _row_values(facts, forecast_rows, "cash", periods)
    net_debt = [None if d is None else d - (c or 0) for d, c in zip(debt, cash)]
    equity = _row_values(facts, forecast_rows, "equity", periods)
    shares_count = shares_mn * 1_000_000 if shares_mn else 0.0
    bvps = [None if eq is None or shares_count == 0 else eq * 1_000_000_000 / shares_count for eq in equity]
    return TableData(
        title="CÁC KHOẢN MỤC CĐKT VÀ DÒNG TIỀN",
        periods=periods,
        unit="Đơn vị: tỷ đồng nếu không có ghi chú khác",
        rows=[
            ("Thay đổi vốn lưu động", delta_nwc),
            ("Capex", [abs(v) if isinstance(v, (int, float)) else v for v in capex]),
            ("Đầu tư vào công ty liên kết/liên doanh", [_DASH] * n),
            ("Các khoản mục dòng tiền khác", [_DASH] * n),
            ("Dòng tiền tự do", fcff_vals),
            ("Phát hành cổ phiếu", [_DASH] * n),
            ("Cổ tức", [_DASH] * n),
            ("Thay đổi nợ ròng", [_DASH] * n),
            ("Nợ ròng cuối năm", net_debt),
            ("Vốn CSH", equity),
            ("Giá trị sổ sách/cp (VND)", bvps),
            ("Nợ ròng / VCSH", [_safe_div(nd, eq) for nd, eq in zip(net_debt, equity)]),
            ("Nợ ròng / EBITDA", [_DASH] * n),
            ("Tổng tài sản", _row_values(facts, forecast_rows, "total_assets", periods)),
        ],
    )


def _table_profitability_valuation(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    current_price: float | None,
    fcff: dict[str, Any],
    periods: list[str],
    shares_mn: float,
) -> TableData:
    n = len(periods)
    revenue = _row_values(facts, forecast_rows, "revenue", periods)
    ebitda = _ebitda_values(forecast_rows, facts, periods)
    fcf = _row_values(facts, forecast_rows, "fcf", periods)
    eps = _row_values(facts, forecast_rows, "eps", periods)
    equity = _row_values(facts, forecast_rows, "equity", periods)
    assets = _row_values(facts, forecast_rows, "total_assets", periods)
    net_income = _row_values(facts, forecast_rows, "net_income", periods)
    ebit = _ebit_values(forecast_rows, facts, periods)
    tax_rate = fcff.get("wacc_breakdown", {}).get("tax_rate", 0.1579)
    market_cap = None if current_price is None or shares_mn == 0 else current_price * shares_mn / 1000
    enterprise_value = market_cap
    invested_capital = [None if eq is None else eq for eq in equity]
    roic = [_safe_div(None if e is None else e * (1 - tax_rate), ic) for e, ic in zip(ebit, invested_capital)]
    pe = [None if current_price is None or e in (None, 0) else current_price / e for e in eps]
    ev_ebitda = [None if enterprise_value is None or e in (None, 0) else enterprise_value / e for e in ebitda]
    ev_fcf = [None if enterprise_value is None or v in (None, 0) else enterprise_value / v for v in fcf]
    pb = [None if market_cap is None or eq in (None, 0) else market_cap / eq for eq in equity]
    ps = [None if market_cap is None or rev in (None, 0) else market_cap / rev for rev in revenue]
    return TableData(
        title="CHỈ SỐ KHẢ NĂNG SINH LỢI VÀ ĐỊNH GIÁ",
        periods=periods,
        unit="Đơn vị: lần hoặc %, trừ khi có ghi chú khác",
        rows=[
            ("ROE", [_safe_div(ni, eq) for ni, eq in zip(net_income, equity)]),
            ("ROA", [_safe_div(ni, asset) for ni, asset in zip(net_income, assets)]),
            ("ROIC", roic),
            ("WACC", [fcff.get("wacc")] * n),
            ("EVA", [None if r is None or fcff.get("wacc") is None else r - fcff.get("wacc") for r in roic]),
            ("P/E", pe),
            ("EV/EBITDA", ev_ebitda),
            ("EV/FCF", ev_fcf),
            ("P/B", pb),
            ("P/S", ps),
            ("EV/Doanh thu", [None if enterprise_value is None or rev in (None, 0) else enterprise_value / rev for rev in revenue]),
            ("PEG", [_DASH] * n),
            ("Suất sinh lợi cổ tức", [_DASH] * n),
        ],
    )


def _table_key_forecast_drivers(
    forecast: dict[str, Any],
    fcff: dict[str, Any],
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    ticker: str,
) -> TableData:
    """Build the ĐỘNG LỰC DỰ PHÓNG CHÍNH driver table from forecast artifact."""
    drivers = forecast.get("drivers", {})
    wb = fcff.get("wacc_breakdown", {})
    wacc = fcff.get("wacc", wb.get("cost_of_equity", 0.138))
    terminal_growth = fcff.get("terminal_growth", 0.03)

    rev_growth_raw = drivers.get("revenue_growth", {})
    if isinstance(rev_growth_raw, dict):
        # Could be {year: value} or {method, value}
        if "value" in rev_growth_raw:
            rev_growth = float(rev_growth_raw["value"])
        else:
            values = [v for k, v in rev_growth_raw.items() if isinstance(v, (int, float))]
            rev_growth = values[0] if values else 0.0
    else:
        rev_growth = float(rev_growth_raw) if rev_growth_raw else 0.0

    def _driver_pct(key: str) -> float | None:
        d = drivers.get(key, {})
        if isinstance(d, dict):
            return d.get("value")
        return float(d) if d else None

    gross_margin = _driver_pct("gross_margin") or 0.0
    sga = _driver_pct("sga_to_revenue") or 0.0
    dep = _driver_pct("depreciation_to_revenue") or 0.0
    capex = _driver_pct("capex_to_revenue") or 0.0
    tax_rate = _driver_pct("effective_tax_rate") or wb.get("tax_rate", 0.158)

    # Compute cash conversion for 2025A if possible
    ni_2025 = _fact_value(facts, "net_income.parent", "2025FY")
    cfo_2025 = _fact_value(facts, "operating_cash_flow.total", "2025FY")
    if ni_2025 and ni_2025 != 0 and cfo_2025 is not None:
        cash_conversion = cfo_2025 / ni_2025
    else:
        cash_conversion = None

    rows = [
        ("Tăng trưởng doanh thu", [rev_growth, "Doanh thu -> EBIT -> FCFF"]),
        ("Biên lợi nhuận gộp", [gross_margin, "Giá vốn -> lợi nhuận gộp"]),
        ("SG&A / doanh thu", [sga, "Chi phí vận hành -> EBIT margin"]),
        ("Khấu hao / doanh thu", [dep, "EBIT và lá chắn thuế"]),
        ("Capex / doanh thu", [capex, "FCFF và mở rộng công suất"]),
        ("Thuế suất hiệu dụng", [tax_rate, "LNST và NOPAT"]),
        ("Cash conversion 2025", [cash_conversion, "Kỷ luật vốn lưu động"]),
        ("WACC", [wacc, "Tỷ lệ chiết khấu DCF"]),
        ("Tăng trưởng dài hạn", [terminal_growth, "Terminal value DCF"]),
    ]
    return TableData(
        title="ĐỘNG LỰC DỰ PHÓNG CHÍNH",
        periods=["Giả định cơ sở", "Liên kết tài chính"],
        unit="Giả định driver được hiệu chỉnh từ dữ liệu lịch sử và định hướng kinh doanh hiện tại.",
        rows=rows,
    )


def _table_driver_sensitivity(
    fcff: dict[str, Any],
    blend: dict[str, Any],
    forecast: dict[str, Any],
) -> TableData:
    """Build the ĐỘ NHẠY THEO DRIVER sensitivity table from valuation artifact."""
    drivers = forecast.get("drivers", {})
    wb = fcff.get("wacc_breakdown", {})
    wacc_base = fcff.get("wacc", wb.get("cost_of_equity", 0.138))
    terminal_growth = fcff.get("terminal_growth", 0.03)

    def _driver_pct(key: str) -> float | None:
        d = drivers.get(key, {})
        if isinstance(d, dict):
            return d.get("value")
        return float(d) if d else None

    rev_growth_raw = drivers.get("revenue_growth", {})
    if isinstance(rev_growth_raw, dict):
        if "value" in rev_growth_raw:
            rev_growth = float(rev_growth_raw["value"])
        else:
            values = [v for k, v in rev_growth_raw.items() if isinstance(v, (int, float))]
            rev_growth = values[0] if values else 0.04
    else:
        rev_growth = float(rev_growth_raw) if rev_growth_raw else 0.04

    gross_margin_base = _driver_pct("gross_margin") or 0.47

    # Target price from blend artifact
    target_base = float(blend.get("target_price_dcf_vnd") or 0) or None
    current_price = float(blend.get("current_price_vnd") or 0) or None

    # Build bear/base/bull scenarios from base ± stress
    rev_bear = max(0.0, rev_growth - 0.03)
    rev_bull = rev_growth + 0.03
    gm_bear = max(0.0, gross_margin_base - 0.02)
    gm_bull = gross_margin_base + 0.02
    wacc_bear = wacc_base + 0.01
    wacc_bull = max(0.0, wacc_base - 0.01)

    def _upside(tp: float | None, cp: float | None) -> float | None:
        if tp is None or cp in (None, 0):
            return None
        return tp / cp - 1

    # Stress target price ≈ ±15% from base (simplified)
    tp_bear = (target_base * 0.85) if target_base else None
    tp_bull = (target_base * 1.15) if target_base else None

    rows = [
        ("Target price", [tp_bear, target_base, tp_bull]),
        ("Upside/downside", [_upside(tp_bear, current_price), _upside(target_base, current_price), _upside(tp_bull, current_price)]),
        ("Revenue growth stress", [rev_bear, rev_growth, rev_bull]),
        ("Gross margin stress", [gm_bear, gross_margin_base, gm_bull]),
        ("WACC stress", [wacc_bear, wacc_base, wacc_bull]),
    ]
    return TableData(
        title="ĐỘ NHẠY THEO DRIVER",
        periods=["Bear", "Base", "Bull"],
        unit="Minh họa độ nhạy theo kịch bản; báo cáo chính thức cần giả định được phê duyệt.",
        rows=rows,
    )


def _build_current_context(ticker: str, company_name: str, facts: dict[str, Any], forecast: dict[str, Any]) -> str:
    """Build a brief current-context narrative mentioning key operating factors."""
    drivers = forecast.get("drivers", {})

    def _driver_pct(key: str) -> float | None:
        d = drivers.get(key, {})
        if isinstance(d, dict):
            return d.get("value")
        return float(d) if d else None

    gross_margin = _driver_pct("gross_margin")
    capex = _driver_pct("capex_to_revenue")
    gm_str = f"{gross_margin * 100:.1f}%" if gross_margin else "—"
    capex_str = f"{capex * 100:.1f}%" if capex else "—"

    return (
        f"{company_name} đang trong giai đoạn kiểm soát biên lợi nhuận với biên gộp trung vị "
        f"{gm_str}. Áp lực đến từ chi phí API/nguyên liệu nhập khẩu, biến động tỷ giá và "
        f"cạnh tranh đấu thầu ETC. Chu kỳ đầu tư capex/{capex_str} doanh thu cần được theo dõi sát "
        "trong bối cảnh nâng chuẩn GMP-EU và dự án nhà máy. "
        "Tồn kho và nợ vay, hàng tồn kho được phản ánh qua CCC và delta NWC trong mô hình FCFF. "
        "Các driver biên lợi nhuận và giá vốn, chi phí bán hàng, hàng tồn kho và nợ vay tăng "
        "là các tín hiệu cần đưa trực tiếp vào driver margin, SG&A và working capital của mô hình."
    )


def _charts(ticker: str) -> dict[str, ChartArtifact]:
    charts_dir = ROOT / "artifacts/charts"
    titles = {
        "C1": "Diễn biến giá cổ phiếu so với VNINDEX",
        "C2": "Doanh thu và lợi nhuận",
        "C4": "Biên lợi nhuận và ROE",
    }
    result: dict[str, ChartArtifact] = {}
    for chart_id, title in titles.items():
        path = charts_dir / f"{ticker}_{chart_id}.png"
        if path.exists():
            result[chart_id] = ChartArtifact(
                chart_id=chart_id,
                title=title,
                path=str(path),
                caption="Nguồn: Báo cáo tài chính công ty; dữ liệu thị trường; tính toán của nhóm phân tích.",
                required=chart_id in {"C1", "C2"},
            )
    return result


def build_client_report_view_model(
    ticker: str,
    mode: RenderMode | str = "analyst_draft",
    run_id: str | None = None,
) -> ClientReportViewModel:
    ticker = ticker.upper()
    company_name, exchange = _COMPANIES.get(ticker, (ticker, "HOSE"))

    manifest = None
    if run_id:
        from backend.reporting.artifact_manifest import read_manifest
        manifest = read_manifest(run_id, base_dir=ROOT / "artifacts")
        if manifest is None:
            _logger.warning(
                "run_id=%s provided but no manifest found in artifacts/manifests/ — falling back to glob",
                run_id,
            )

    facts = _facts(ticker, manifest)
    val = _valuation(ticker, manifest)
    val_result = _valuation_result(ticker, manifest)
    forecast = _forecast(ticker, manifest)
    fcff = _fcff(ticker, manifest)
    blend = _blend(ticker, manifest)
    forecast_rows = _forecast_by_label(forecast)
    fcff_rows = _fcff_by_label(fcff)
    current_price, target_price, upside = _market_price_inputs(mode, val_result, blend)
    recommendation = _recommendation(upside, mode)
    charts = _charts(ticker)

    periods = _derive_periods(facts)
    shares_mn = _derive_shares_mn(facts, periods)
    dividend_per_share = _derive_dividend_per_share(facts, periods)
    market_cap = None if current_price is None or shares_mn == 0 else current_price * shares_mn / 1000
    missing: list[str] = []
    if current_price is None:
        missing.append("current_price")
    if target_price is None:
        missing.append("target_price")
    if upside is None:
        missing.append("upside_downside")
    if not forecast_rows:
        missing.append("forecast_years")
    if not fcff_rows:
        missing.append("fcff_table")
    if "C1" not in charts:
        missing.append("price_chart")

    publication_status = (
        "client_exportable"
        if mode == "client_final" and not missing and str(val_result.get("is_publishable")).lower() == "true"
        else "analyst_review_only"
    )
    if mode == "client_final" and (missing or publication_status != "client_exportable"):
        missing = sorted(set(missing + ["approval_status"]))

    thesis = (
        f"{company_name} có nền tảng doanh thu dược phẩm ổn định, biên lợi nhuận cao và "
        "khả năng tạo dòng tiền tốt trong giai đoạn gần đây. Bản phân tích tập trung vào "
        "động lực tăng trưởng doanh thu, kiểm soát chi phí, rủi ro đấu thầu và mức định giá "
        "so với triển vọng lợi nhuận."
    )
    latest_update = (
        "Doanh thu và lợi nhuận được dự phóng dựa trên quỹ đạo lịch sử, biên gộp trung vị, "
        "chi phí bán hàng và quản lý theo tỷ lệ doanh thu, cùng giả định đầu tư tài sản cố định "
        "phù hợp với mô hình FCFF."
    )
    growth_drivers = (
        "Động lực chính gồm mở rộng kênh ETC/OTC, danh mục thuốc generic có biên lợi nhuận tốt, "
        "năng lực sản xuất và nhu cầu chăm sóc sức khỏe tiếp tục tăng."
    )
    margin_drivers = (
        "Biên lợi nhuận phụ thuộc vào giá nguyên liệu nhập khẩu, tỷ giá, cơ cấu sản phẩm, "
        "mức độ cạnh tranh trong đấu thầu và khả năng kiểm soát chi phí bán hàng."
    )
    events = (
        "Các sự kiện cần theo dõi gồm kết quả đấu thầu thuốc, tiến độ phê duyệt sản phẩm, "
        "đầu tư nhà máy, biến động chi phí API và thay đổi trong quy định quản lý dược."
    )
    forecast_text = (
        "Mô hình định giá sử dụng FCFF kết hợp kiểm tra tương quan với P/E, P/B, EV/EBITDA và EV/FCF. "
        "Forecast được nối theo driver: revenue growth phản ánh mục tiêu kinh doanh và nền lịch sử; "
        "gross margin phản ánh áp lực giá vốn/API; SG&A/revenue phản ánh chi phí bán hàng; "
        "capex/revenue phản ánh chu kỳ đầu tư GMP-EU. "
        "Các bảng dưới đây giữ đầy đủ cấu trúc dự phóng và tỷ số để người đọc có thể kiểm tra "
        "luận điểm định giá thay vì chỉ nhìn vào một con số mục tiêu."
    )
    current_context = _build_current_context(ticker, company_name, facts, forecast)
    key_forecast_drivers_table = _table_key_forecast_drivers(forecast, fcff, facts, forecast_rows, ticker)
    sensitivity_table = _table_driver_sensitivity(fcff, blend, forecast)

    return ClientReportViewModel(
        ticker=ticker,
        company_name=company_name,
        exchange=exchange,
        sector="Dược phẩm",
        report_date=datetime.now().strftime("%Y-%m-%d"),
        report_title=f"Cập nhật {ticker}",
        recommendation=recommendation,
        current_price=Money(current_price) if current_price is not None else None,
        target_price=Money(target_price) if target_price is not None else None,
        upside_downside=Percent(upside) if upside is not None else None,
        dividend_yield=None,
        total_return=Percent(upside) if upside is not None else None,
        market_statistics={
            "Mã giao dịch": f"{ticker} VN",
            "Sàn": exchange,
            "Ngành": "Dược phẩm",
            "Vốn hóa": market_cap,
            "Số lượng cổ phiếu": shares_mn if shares_mn else _DASH,
            "Giá cao/thấp 52 tuần": _DASH,
            "KLGD bình quân 3 tháng": _DASH,
            "Tỷ giá VND/USD": _DASH,
        },
        ownership_table=TableData(
            title="CƠ CẤU SỞ HỮU",
            periods=["Tỷ lệ"],
            rows=[("Cổ đông lớn và nhà đầu tư tổ chức", [_DASH]), ("Cổ đông khác", [_DASH])],
        ),
        trading_performance_table=TableData(
            title="DIỄN BIẾN GIÁ CỔ PHIẾU",
            periods=["YTD", "1T", "3T", "12T"],
            rows=[("Tuyệt đối", [_DASH] * 4), ("Tương đối", [_DASH] * 4)],
        ),
        financial_summary_table=_table_financial_summary(facts, forecast_rows, current_price, periods, dividend_per_share),
        valuation_model_table=_table_valuation_model(facts, forecast_rows, fcff_rows, periods, shares_mn),
        balance_sheet_cashflow_table=_table_bs_cf(facts, forecast_rows, fcff_rows, periods, shares_mn),
        profitability_valuation_table=_table_profitability_valuation(facts, forecast_rows, current_price, fcff, periods, shares_mn),
        peer_table=None,
        catalyst_table=None,
        risk_table=TableData(
            title="RỦI RO ĐẦU TƯ",
            periods=["Mức độ", "Theo dõi"],
            rows=[
                ("Áp lực giá thầu thuốc", ["Cao", "Kết quả đấu thầu ETC"]),
                ("Biến động nguyên liệu và tỷ giá", ["Trung bình", "API, USD/VND"]),
                ("Cạnh tranh generic", ["Trung bình", "Thị phần và giá bán"]),
            ],
        ),
        charts=charts,
        source_captions={
            "financials": "Nguồn: Báo cáo tài chính công ty; tính toán của nhóm phân tích.",
            "market": "Nguồn: Dữ liệu thị trường; tính toán của nhóm phân tích.",
        },
        disclaimer=(
            "Báo cáo này chỉ nhằm mục đích cung cấp thông tin và không phải là lời mời mua "
            "hoặc bán chứng khoán. Nhà đầu tư cần tự đánh giá khẩu vị rủi ro và tham khảo ý kiến "
            "chuyên gia được cấp phép trước khi ra quyết định."
        ),
        investment_thesis=thesis,
        latest_business_update=latest_update,
        key_growth_drivers=growth_drivers,
        key_margin_drivers=margin_drivers,
        material_events=events,
        current_context=current_context,
        key_forecast_drivers_table=key_forecast_drivers_table,
        sensitivity_table=sensitivity_table,
        forecast_valuation_narrative=forecast_text,
        mode=mode,
        publication_status=publication_status,
        missing_required_fields=missing,
    )


def assert_client_final_ready(vm: ClientReportViewModel) -> None:
    if vm.mode == "client_final" and vm.missing_required_fields:
        raise ClientReportDataMissing(
            missing_fields=vm.missing_required_fields,
            affected_sections=[
                "page_1_snapshot",
                "page_6_valuation_model_table",
                "page_7_bs_cf_ratios",
            ],
        )
