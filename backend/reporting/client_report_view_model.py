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
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from backend.reporting.report_data_loader import _COMPANIES, ROOT, _read_manifest_or_raise

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
    format_type: str = "auto"  # auto | currency | percent | multiple | text
    source_note: str = ""      # optional clean citation string, e.g. "Nguồn: BCTC kiểm toán 2025"


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
    key_sources: list[dict[str, str]] = field(default_factory=list)
    display_blocking_reasons: list[str] = field(default_factory=list)


_DASH = "—"
_PERIODS_FALLBACK = ["2024A", "2025A", "2026F", "2027F", "2028F"]


def _forecast_period_labels(forecast: dict[str, Any] | None) -> list[str]:
    """Extract forecast period labels (e.g. '2026F') from the forecast artifact, in order."""
    if not forecast:
        return []
    labels: list[str] = []
    for row in forecast.get("forecast_years", []):
        if isinstance(row, dict) and row.get("label"):
            labels.append(str(row["label"]))
    return labels


def _derive_periods(
    facts: dict[str, dict[str, float]],
    forecast: dict[str, Any] | None = None,
) -> list[str]:
    """Derive period labels: historical actuals (FY/A) followed by forecast (F) years.

    Forecast years come from the forecast artifact's ``forecast_years[].label`` so that
    the financial tables show 2026F..2030F columns. Falls back to the MVP default period
    set only when there are no actual fact periods at all.
    """
    actuals: list[str] = []
    if facts:
        all_periods: set[str] = set()
        for metric_dict in facts.values():
            if isinstance(metric_dict, dict):
                all_periods.update(metric_dict.keys())
        actuals = sorted(p for p in all_periods if p.endswith(("FY", "A")))

    forecast_labels = _forecast_period_labels(forecast)

    if not actuals:
        # No historical facts: use the default period set (already includes forecast years),
        # but prefer real forecast labels when the artifact provides them.
        if forecast_labels:
            fallback_actuals = [p for p in _PERIODS_FALLBACK if not p.endswith("F")]
            return fallback_actuals + forecast_labels
        return list(_PERIODS_FALLBACK)

    return actuals + forecast_labels


def _derive_shares_mn(facts: dict[str, dict[str, float]], periods: list[str]) -> float:
    """Shares outstanding in millions from canonical facts. 0.0 if unavailable.

    Tries keys in priority order: shares_outstanding.ending (period-end count),
    shares_outstanding.weighted_avg (for EPS consistency), shares_outstanding.total
    (legacy alias). Values stored as absolute share count (e.g. 94,000,000).
    """
    for key in ("shares_outstanding.ending", "shares_outstanding.weighted_avg", "shares_outstanding.total"):
        shares_fact = facts.get(key, {})
        for p in reversed(periods):
            period_key = _to_fact_period(p)
            raw = shares_fact.get(period_key) or shares_fact.get(p)
            v = raw.get("value") if isinstance(raw, dict) else raw
            if v and v > 0:
                return v / 1_000_000
    return 0.0


def _derive_dividend_per_share(facts: dict[str, dict[str, float]], periods: list[str]) -> float | None:
    """Cash dividend per share from canonical facts, or None if unavailable."""
    div_fact = facts.get("dividends_per_share.cash", {})
    for p in reversed(periods):
        raw = div_fact.get(p)
        v = raw.get("value") if isinstance(raw, dict) else raw
        try:
            v = float(v) if v is not None else None
        except (TypeError, ValueError):
            v = None
        if v and v > 0:
            return v
    return None


def _resolve_json(
    pattern: str,
    manifest=None,
    key: str = "",
    allow_latest_artifacts: bool = False,
) -> dict[str, Any]:
    """Manifest-first artifact resolution; falls back to glob with DeprecationWarning."""
    if manifest is not None and key:
        if manifest.resolve(key):
            return manifest.load_json(key)
        return {}
    if not allow_latest_artifacts:
        raise ValueError(
            f"run_id is required to resolve artifact '{key or pattern}'. "
            "Pass allow_latest_artifacts=True only for internal debug rendering."
        )
    files = sorted(glob.glob(str(ROOT / pattern)))
    if not files:
        return {}
    with open(files[-1], encoding="utf-8") as f:
        return json.load(f)


def _facts(ticker: str, manifest=None, allow_latest_artifacts: bool = False) -> dict[str, dict[str, float]]:
    return _resolve_json(
        f"artifacts/facts/{ticker}_*_fact_report.json",
        manifest,
        "facts",
        allow_latest_artifacts,
    ).get("facts", {})


def _valuation(ticker: str, manifest=None, allow_latest_artifacts: bool = False) -> dict[str, Any]:
    return _resolve_json(
        f"artifacts/valuation/{ticker}_*_valuation.json",
        manifest,
        "valuation",
        allow_latest_artifacts,
    )


def _valuation_result(ticker: str, manifest=None, allow_latest_artifacts: bool = False) -> dict[str, Any]:
    return _resolve_json(
        f"artifacts/valuation_results/*_{ticker}_valuation_result.json",
        manifest,
        "valuation_result",
        allow_latest_artifacts,
    )


def _forecast(ticker: str, manifest=None, allow_latest_artifacts: bool = False) -> dict[str, Any]:
    data = _resolve_json(
        f"artifacts/forecast/{ticker}_*_forecast.json",
        manifest,
        "forecast",
        allow_latest_artifacts,
    )
    if data or manifest is None:
        return data
    return _valuation(ticker, manifest, allow_latest_artifacts).get("forecast", {})


def _fcff(ticker: str, manifest=None, allow_latest_artifacts: bool = False) -> dict[str, Any]:
    data = _resolve_json(
        f"artifacts/forecast/{ticker}_*_fcff.json",
        manifest,
        "fcff",
        allow_latest_artifacts,
    )
    if data or manifest is None:
        return data
    return _valuation(ticker, manifest, allow_latest_artifacts).get("fcff", {})


def _blend(ticker: str, manifest=None, allow_latest_artifacts: bool = False) -> dict[str, Any]:
    data = _resolve_json(
        f"artifacts/forecast/{ticker}_*_blend.json",
        manifest,
        "blend",
        allow_latest_artifacts,
    )
    if data or manifest is None:
        return data
    return _valuation(ticker, manifest, allow_latest_artifacts).get("blend_dcf", {})


def _core_pe_net_cash(ticker: str, manifest=None, allow_latest_artifacts: bool = False) -> dict[str, Any]:
    return _valuation(ticker, manifest, allow_latest_artifacts).get("core_pe_net_cash", {})



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
    if period.endswith("A") or period.endswith("FY"):
        fact_period = _to_fact_period(period)
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


def _interest_bearing_debt(facts: dict[str, dict[str, float]], period: str) -> float | None:
    """Interest-bearing debt for an actual period.

    = short-term borrowings + current portion of LTD + long-term debt + lease liabilities.
    Falls back to total_debt.ending when the component breakdown is unavailable.
    (Audit NUMERIC-04: net debt must include long-term debt, not just short-term.)
    """
    fp = _to_fact_period(period)
    components = [
        v for v in (
            _fact_value(facts, "short_term_debt.ending", fp),
            _fact_value(facts, "current_portion_ltd.ending", fp),
            _fact_value(facts, "long_term_debt.ending", fp),
            _fact_value(facts, "lease_liabilities.ending", fp),
        ) if v is not None
    ]
    if components:
        return sum(components)
    return _fact_value(facts, "total_debt.ending", fp)


def _cash_like_assets(facts: dict[str, dict[str, float]], period: str) -> float | None:
    """Cash-like assets for an actual period.

    = cash & equivalents + short-term deposits + liquid short-term investments.
    (Audit NUMERIC-04: short-term investments are treated as cash-like.)
    """
    fp = _to_fact_period(period)
    cash = _fact_value(facts, "cash_and_equivalents.ending", fp)
    if cash is None:
        return None
    sti = _fact_value(facts, "short_term_investments.ending", fp) or 0.0
    dep = _fact_value(facts, "short_term_deposits.ending", fp) or 0.0
    return cash + sti + dep


def _net_debt_canonical(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    periods: list[str],
) -> list[float | None]:
    """Net debt = interest-bearing debt - cash-like assets (negative = net cash).

    Actual periods use the full balance-sheet bridge; forecast periods use the
    forecast total_debt vs forecast cash when both are available.
    """
    out: list[float | None] = []
    for p in periods:
        if _is_actual(p):
            ibd = _interest_bearing_debt(facts, p)
            cl = _cash_like_assets(facts, p)
            out.append(None if ibd is None or cl is None else ibd - cl)
        else:
            d = forecast_rows.get(p, {}).get("total_debt")
            c = forecast_rows.get(p, {}).get("cash")
            out.append(None if d is None or c is None else d - c)
    return out


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
    prev_period = _to_fact_period(periods[0]) if periods else "2023FY"
    prev_metric_year = str(int(prev_period[:4]) - 1) + prev_period[4:]
    prev_val = _fact_value(facts, "revenue.net", prev_metric_year)
    previous_values = [prev_val] + values[:-1]
    return [_pct_change(v, prev) for v, prev in zip(values, previous_values)]


def _net_profit_growth(facts: dict[str, dict[str, float]], forecast_rows: dict[str, dict[str, Any]], periods: list[str]) -> list[float | None]:
    values = _row_values(facts, forecast_rows, "net_income", periods)
    prev_period = _to_fact_period(periods[0]) if periods else "2023FY"
    prev_metric_year = str(int(prev_period[:4]) - 1) + prev_period[4:]
    prev_val = _fact_value(facts, "net_income.parent", prev_metric_year)
    previous_values = [prev_val] + values[:-1]
    return [_pct_change(v, prev) for v, prev in zip(values, previous_values)]


def _eps_growth(facts: dict[str, dict[str, float]], forecast_rows: dict[str, dict[str, Any]], periods: list[str]) -> list[float | None]:
    values = _row_values(facts, forecast_rows, "eps", periods)
    prev_period = _to_fact_period(periods[0]) if periods else "2023FY"
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


def _is_actual(period: str) -> bool:
    """Return True if the period label represents an actual (historical) year."""
    return period.endswith("A") or period.endswith("FY")


def _to_fact_period(period: str) -> str:
    """Normalize a display period label to the canonical "FY"-suffix fact key.

    Canonical facts use "YYYYFY" keys (e.g. "2024FY").
    Display labels may use "YYYYA" suffix for actuals. This helper converts both.
    Expected input format: "<4-digit-year>FY" or "<4-digit-year>A".
    """
    return period if period.endswith("FY") else (period[:-1] + "FY" if period.endswith("A") else period)


def _fcff_values(facts: dict[str, dict[str, float]], fcff_rows: dict[str, dict[str, Any]], periods: list[str]) -> list[float | None]:
    # Actual periods: those ending in "A" or "FY"; forecast: those ending in "F"
    actual_periods = [p for p in periods if _is_actual(p)]
    forecast_periods = [p for p in periods if p.endswith("F")]
    actual = [_fact_value(facts, "free_cash_flow.total", _to_fact_period(p)) for p in actual_periods]
    forecast = [fcff_rows.get(period, {}).get("fcff") for period in forecast_periods]
    return actual + forecast


def _delta_nwc_values(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    fcff_rows: dict[str, dict[str, Any]],
    periods: list[str],
) -> list[float | None]:
    actual: list[float | None] = []
    actual_periods = [p for p in periods if _is_actual(p)]
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
    actual_periods = [p for p in periods if _is_actual(p)]
    forecast_periods = [p for p in periods if p.endswith("F")]
    actual = [
        _fact_value(facts, "operating_cash_flow.total", _to_fact_period(p))
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
    actual_periods = [p for p in periods if _is_actual(p)]
    forecast_periods = [p for p in periods if p.endswith("F")]
    values: list[float | None] = [
        _fact_value(facts, "cash_and_equivalents.ending", _to_fact_period(p))
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
    # Actual periods: full interest-bearing-debt vs cash-like bridge (incl. LT debt + ST investments).
    # Forecast periods: forecast total_debt vs the cash-sweep estimate.
    canonical = _net_debt_canonical(facts, forecast_rows, periods)
    debt = _row_values(facts, forecast_rows, "debt", periods)
    cash = _cash_values(facts, forecast_rows, fcff_rows, periods, shares_mn, dividend_per_share)
    out: list[float | None] = []
    for i, p in enumerate(periods):
        if _is_actual(p):
            out.append(canonical[i])
        else:
            d, c = debt[i], cash[i]
            out.append(None if d is None or c is None else d - c)
    return out


def _finance_income_values(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    periods: list[str],
) -> list[float | None]:
    ebit = _ebit_values(forecast_rows, facts, periods)
    interest = _row_values(facts, forecast_rows, "interest_expense", periods)
    result: list[float | None] = []
    for i, period in enumerate(periods):
        if _is_actual(period):
            pbt = _fact_value(facts, "profit_before_tax.total", _to_fact_period(period))
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
        upside_raw = val_result.get("upside_downside")
        upside = float(upside_raw) if upside_raw is not None else None
        # A missing/non-publishable valuation_result must not erase usable
        # computed values. Client-final readiness is enforced separately.
        current = current or (float(blend.get("current_price_vnd") or 0) or None)
        target = target or (float(blend.get("target_price_dcf_vnd") or 0) or None)
        if upside is None and blend.get("upside_pct") is not None:
            upside = float(blend["upside_pct"])
        return current, target, upside
    current = float(blend.get("current_price_vnd") or 0) or None
    target = float(blend.get("target_price_dcf_vnd") or 0) or None
    upside_raw = blend.get("upside_pct")
    upside = float(upside_raw) if upside_raw is not None else None
    return current, target, upside


def _report_display_governance(
    mode: RenderMode | str,
    val_result: dict[str, Any],
    blend: dict[str, Any],
) -> dict[str, Any]:
    """Central policy for report-facing recommendation, target and upside display."""
    reasons: list[str] = []
    is_publishable = str(val_result.get("is_publishable")).lower() == "true"
    if not val_result:
        reasons.append("valuation_result_missing")
    elif not is_publishable:
        reasons.append("valuation_result_not_publishable")
    if blend.get("is_draft_only") is True:
        reasons.append("blend_is_draft_only")
    gap = blend.get("valuation_gap_pct")
    try:
        if gap is not None and float(gap) > 0.25:
            reasons.append("valuation_gap_gt_25pct")
    except (TypeError, ValueError):
        reasons.append("valuation_gap_invalid")

    # analyst_draft always shows computed values — analyst needs full picture to review
    # Display governance is separate from publication governance. Available
    # model outputs remain visible for analysis while client-final blockers stay
    # available to the export workflow as internal metadata.
    approved_for_display = True
    blocking_reasons = sorted(set(reasons)) if mode == "client_final" else []

    current, target, upside = _market_price_inputs(mode, val_result, blend)
    if target is None:
        approved_for_display = False
        target = None
        upside = None

    # client_final with blocking reasons: lock recommendation but keep values visible for review
    if mode == "client_final" and blocking_reasons:
        approved_for_display = False

    return {
        "approved_for_display": approved_for_display,
        "current_price": current,
        "target_price": target,
        "upside": upside,
        "recommendation": _recommendation(upside, mode, approved_for_display),
        "blocking_reasons": blocking_reasons,
        "blend_target_price": target,  # keep blend for cross-check display
    }


def _apply_core_pe_override(
    display_gate: dict[str, Any],
    cpnc: dict[str, Any],
) -> dict[str, Any]:
    """Override target price with Core P/E + Net Cash when available (Guidance §11)."""
    cpnc_target = float(cpnc.get("target_price_vnd") or 0) or None
    current = display_gate.get("current_price")
    if cpnc_target is not None:
        cpnc_upside = (cpnc_target / current - 1) if current else None
        return {
            **display_gate,
            "target_price": cpnc_target,
            "upside": cpnc_upside,
            "recommendation": _recommendation(cpnc_upside, "analyst_draft", display_gate.get("approved_for_display", True)),
        }
    return display_gate


def _recommendation(upside: float | None, mode: RenderMode | str, approved_for_display: bool = False) -> str:
    if not approved_for_display or upside is None:
        return "ĐANG HOÀN THIỆN" if mode != "client_final" else "CHƯA XUẤT BẢN"
    if upside > 0.20:
        return "MUA"
    if upside < -0.20:
        return "BÁN"
    return "GIỮ"


def _total_return(upside: float | None, dividend_yield: "Percent | None") -> "Percent | None":
    """Total return = price return (upside) + 12-month expected dividend yield.

    Audit DATA-03: total return must add the dividend yield, not equal the bare
    downside. Returns None when upside is unavailable.
    """
    if upside is None:
        return None
    dy = dividend_yield.value if dividend_yield is not None else 0.0
    return Percent(upside + dy)


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

    # Leverage and dividend yield wherever inputs are available (else dash, no fabrication).
    ebitda = _ebitda_values(forecast_rows, facts, periods)
    net_debt = _net_debt_canonical(facts, forecast_rows, periods)
    net_debt_ebitda = [_safe_div(nd, e) for nd, e in zip(net_debt, ebitda)]
    div_yield_val = (
        dividend_per_share / current_price
        if dividend_per_share and current_price else None
    )
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
            ("Nợ ròng / EBITDA", net_debt_ebitda),
            ("P/E", pe),
            ("P/B", pb),
            ("Cổ tức/cp", [dividend_per_share] * n),
            ("Suất sinh lợi cổ tức", [div_yield_val] * n),
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
    actual_periods = [p for p in periods if _is_actual(p)]
    forecast_periods = [p for p in periods if p.endswith("F")]

    # Historical FCF: CFO - |CAPEX| using canonical facts (consistent sign convention).
    # Forecast FCF: FCFF from the valuation engine.
    cfo_hist = [
        _fact_value(facts, "operating_cash_flow.total", _to_fact_period(p))
        for p in actual_periods
    ]
    capex_hist = [
        _fact_value(facts, "capex.total", _to_fact_period(p))
        for p in actual_periods
    ]
    fcf_hist = [
        None if cfo is None else cfo - abs(cap or 0.0)
        for cfo, cap in zip(cfo_hist, capex_hist)
    ]
    fcff_vals = fcf_hist + [fcff_rows.get(p, {}).get("fcff") for p in forecast_periods]

    delta_nwc = [None] * len(actual_periods) + [fcff_rows.get(p, {}).get("delta_nwc") for p in forecast_periods]
    capex = _row_values(facts, forecast_rows, "capex", periods)
    net_debt = _net_debt_canonical(facts, forecast_rows, periods)
    equity = _row_values(facts, forecast_rows, "equity", periods)
    shares_count = shares_mn * 1_000_000 if shares_mn else 0.0
    bvps = [None if eq is None or shares_count == 0 else eq * 1_000_000_000 / shares_count for eq in equity]

    # Dividend row: use forecast_rows for forecast periods (cash_dividend field), dash for historical.
    dividends: list[Any] = [_DASH] * len(actual_periods) + [
        forecast_rows.get(p, {}).get("cash_dividend")
        for p in forecast_periods
    ]

    # Net borrowing (Δ net debt) from the debt schedule: forecast periods carry the
    # net_borrowing field; historical net borrowing is not reconstructed here.
    net_borrowing: list[Any] = [_DASH] * len(actual_periods) + [
        forecast_rows.get(p, {}).get("net_borrowing")
        for p in forecast_periods
    ]

    # Net debt / EBITDA leverage: computed wherever both inputs are available.
    ebitda = _ebitda_values(forecast_rows, facts, periods)
    net_debt_ebitda = [_safe_div(nd, e) for nd, e in zip(net_debt, ebitda)]

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
            ("Cổ tức", dividends),
            ("Thay đổi nợ ròng", net_borrowing),
            ("Nợ ròng cuối năm", net_debt),
            ("Vốn CSH", equity),
            ("Giá trị sổ sách/cp (VND)", bvps),
            ("Nợ ròng / VCSH", [_safe_div(nd, eq) for nd, eq in zip(net_debt, equity)]),
            ("Nợ ròng / EBITDA", net_debt_ebitda),
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

    # Audit NUMERIC-08: a one-year CFO/PAT outside [50%, 150%] may be driven by
    # working-capital release/timing and must NOT be presented as a sustainable
    # quality signal — flag it instead of stating it as a clean positive.
    if cash_conversion is not None and (cash_conversion > 1.5 or cash_conversion < 0.5):
        cash_conversion_note = "Bất thường — cần soi vốn lưu động (không dùng làm luận điểm bền vững)"
    else:
        cash_conversion_note = "Kỷ luật vốn lưu động"

    rows = [
        ("Tăng trưởng doanh thu", [rev_growth, "Doanh thu -> EBIT -> FCFF"]),
        ("Biên lợi nhuận gộp", [gross_margin, "Giá vốn -> lợi nhuận gộp"]),
        ("SG&A / doanh thu", [sga, "Chi phí vận hành -> EBIT margin"]),
        ("Khấu hao / doanh thu", [dep, "EBIT và lá chắn thuế"]),
        ("Capex / doanh thu", [capex, "FCFF và mở rộng công suất"]),
        ("Thuế suất hiệu dụng", [tax_rate, "LNST và NOPAT"]),
        ("Cash conversion 2025", [cash_conversion, cash_conversion_note]),
        ("WACC", [wacc, "Tỷ lệ chiết khấu DCF"]),
        ("Tăng trưởng dài hạn", [terminal_growth, "Terminal value DCF"]),
    ]
    return TableData(
        title="ĐỘNG LỰC DỰ PHÓNG CHÍNH",
        periods=["Giả định cơ sở", "Liên kết tài chính"],
        unit="Giả định driver được hiệu chỉnh từ dữ liệu lịch sử và định hướng kinh doanh hiện tại.",
        rows=rows,
    )


def _table_sensitivity_matrix(sensitivity: dict[str, Any], valuation_publishable: bool = True) -> TableData | None:
    """WACC × terminal-growth target-price matrix from the valuation sensitivity artifact.

    Returns None when the matrix is absent or all-null (e.g. shares missing at compute
    time), so the caller can fall back to the scenario view rather than render empty cells.
    """
    if not valuation_publishable:
        return None
    fw = (sensitivity or {}).get("fcff_wacc_g", {})
    matrix = fw.get("matrix", {})
    wacc_range = fw.get("wacc_range", [])
    g_range = fw.get("g_range", [])
    if not matrix or not wacc_range or not g_range:
        return None

    def _g_key(g: float) -> str:
        return f"{g:.4f}".rstrip("0").rstrip(".")

    has_value = any(
        matrix.get(f"{w:.3f}", {}).get(_g_key(g)) is not None
        for w in wacc_range
        for g in g_range
    )
    if not has_value:
        return None

    periods = [f"g={g * 100:.1f}%" for g in g_range]
    rows: list[tuple[str, list[Any]]] = []
    for w in wacc_range:
        wk = f"{w:.3f}"
        rows.append((f"WACC {w * 100:.1f}%", [matrix.get(wk, {}).get(_g_key(g)) for g in g_range]))
    fmt = "currency"
    return TableData(
        title="ĐỘ NHẠY GIÁ MỤC TIÊU (WACC × tăng trưởng dài hạn)",
        periods=periods,
        unit="Đơn vị: VND/cp — định giá FCFF DCF.",
        rows=rows,
        format_type=fmt,
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


_STATEMENT_LABELS = {
    "balance sheet": "Bảng cân đối kế toán (dữ liệu thị trường VCI)",
    "income statement": "Báo cáo kết quả kinh doanh (dữ liệu thị trường VCI)",
    "cash flow": "Báo cáo lưu chuyển tiền tệ (dữ liệu thị trường VCI)",
}


def _clean_source_title(raw: str) -> str | None:
    """Map a backend source_title to a client-safe Vietnamese label (no 'Tier' jargon)."""
    if not raw:
        return None
    head = raw.split("[")[0].strip().lower()
    for key, label in _STATEMENT_LABELS.items():
        if key in head:
            return label
    if "api" in head or "tổng hợp" in head:
        return "Dữ liệu tài chính tổng hợp (VCI)"
    return None


def _key_sources(ticker: str, snapshot) -> list[dict[str, str]]:
    """Build a client-facing 'Nguồn tham khảo chính' list from real data provenance.

    Sources are honestly labelled by what they are (market data / financial statements via
    VCI / internal valuation model). Backend tier jargon is stripped. No source is invented
    and none is presented as an official filing it is not.
    """
    sources: list[dict[str, str]] = []
    if snapshot is not None:
        as_of = f" (cập nhật {snapshot.as_of_date})" if getattr(snapshot, "as_of_date", "") else ""
        sources.append({
            "label": f"Dữ liệu thị trường {ticker}: giá, vốn hóa, số cổ phiếu lưu hành, "
                     f"khối lượng, sở hữu nước ngoài — vnstock VCI{as_of}"
        })

    # Distinct financial-statement sources + fiscal-year span from the citation artifact.
    cit = _load_latest_citation(ticker)
    spans: dict[str, set[int]] = {}
    for entry in (cit.get("citation_map", {}) or {}).values():
        label = _clean_source_title(entry.get("source_title", ""))
        if not label:
            continue
        fy = entry.get("fiscal_year")
        spans.setdefault(label, set())
        if isinstance(fy, int):
            spans[label].add(fy)
    for label, years in spans.items():
        yrs = sorted(years)
        span = f" {yrs[0]}–{yrs[-1]}" if len(yrs) > 1 else (f" {yrs[0]}" if yrs else "")
        sources.append({"label": f"{label} — {ticker}{span}"})

    sources.append({
        "label": "Mô hình định giá FCFF/FCFE và độ nhạy WACC × tăng trưởng dài hạn "
                 "(tính toán nội bộ, có thể tái lập từ giả định công bố)"
    })
    return sources[:10]


def _load_latest_citation(ticker: str) -> dict[str, Any]:
    import glob as _glob
    import json as _json
    files = sorted(_glob.glob(str(ROOT / "artifacts" / "reports" / f"{ticker}_*citation*.json")))
    if not files:
        return {}
    try:
        return _json.loads(Path(files[-1]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _load_market_snapshot(ticker: str):
    """Load the latest cached market snapshot for the ticker (offline-safe)."""
    try:
        from backend.reporting.market_snapshot import load_cached_snapshot
        return load_cached_snapshot(ticker, base_dir=ROOT / "artifacts" / "market_snapshot")
    except Exception:  # noqa: BLE001 - rendering must not fail on snapshot absence
        return None


def _driver_value(forecast: dict[str, Any], key: str) -> float | None:
    """Extract a single driver value from forecast['drivers'], handling year-dict + {value} forms."""
    d = (forecast.get("drivers", {}) or {}).get(key, {})
    if isinstance(d, dict):
        if "value" in d:
            return d.get("value")
        nums = [v for v in d.values() if isinstance(v, (int, float))]
        return nums[0] if nums else None
    return float(d) if isinstance(d, (int, float)) else None


def _build_narratives(
    ticker: str,
    company_name: str,
    facts: dict[str, dict[str, float]],
    forecast: dict[str, Any],
    fcff: dict[str, Any],
    blend: dict[str, Any],
    val: dict[str, Any],
    periods: list[str],
    current_price: float | None,
    target_price: float | None,
    upside: float | None,
    rating: str,
    dividend_yield: "Percent | None",
    core_pe_net_cash: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Compute artifact-grounded narrative sections (≥300 words each)."""
    from backend.reporting.narrative_builder import NarrativeInputs, build_all

    actual_periods = [p for p in periods if _is_actual(p)]
    latest_a = actual_periods[-1] if actual_periods else None
    prev_a = actual_periods[-2] if len(actual_periods) >= 2 else None

    def _fv(metric: str, p: str | None) -> float | None:
        return _fact_value(facts, metric, _to_fact_period(p)) if p else None

    rev_latest = _fv("revenue.net", latest_a)
    rev_prev = _fv("revenue.net", prev_a)
    rev_growth = (rev_latest / rev_prev - 1) if rev_latest and rev_prev else None
    ni_latest = _fv("net_income.parent", latest_a)
    gp_latest = _fv("gross_profit.total", latest_a)
    cfo_latest = _fv("operating_cash_flow.total", latest_a)

    wb = fcff.get("wacc_breakdown", {}) if isinstance(fcff, dict) else {}
    matrix = (val.get("sensitivity", {}) or {}).get("fcff_wacc_g", {}).get("matrix", {})
    cells = [v for row in matrix.values() for v in row.values() if isinstance(v, (int, float))]

    n = NarrativeInputs(
        ticker=ticker,
        company_name=company_name,
        revenue_latest=rev_latest,
        revenue_prev=rev_prev,
        revenue_growth_latest=rev_growth,
        revenue_cagr=forecast.get("revenue_cagr_historical"),
        net_income_latest=ni_latest,
        net_margin_latest=(ni_latest / rev_latest) if ni_latest and rev_latest else None,
        gross_margin_latest=(gp_latest / rev_latest) if gp_latest and rev_latest else None,
        eps_latest=_fv("eps.basic", latest_a),
        cash_conversion=(cfo_latest / ni_latest) if cfo_latest and ni_latest else None,
        rev_growth_driver=_driver_value(forecast, "revenue_growth"),
        gross_margin_driver=_driver_value(forecast, "gross_margin"),
        sga_driver=_driver_value(forecast, "sga_to_revenue"),
        capex_driver=_driver_value(forecast, "capex_to_revenue"),
        tax_driver=_driver_value(forecast, "effective_tax_rate") or wb.get("tax_rate"),
        wacc=fcff.get("wacc") if isinstance(fcff, dict) else None,
        terminal_growth=fcff.get("terminal_growth") if isinstance(fcff, dict) else None,
        current_price=current_price,
        target_price=target_price,
        upside=upside,
        rating=rating,
        price_fcff=blend.get("price_fcff_vnd") if isinstance(blend, dict) else None,
        price_pe_forward=blend.get("price_pe_forward_vnd") if isinstance(blend, dict) else None,
        core_pe_target=(core_pe_net_cash or {}).get("target_price_vnd"),
        net_cash_per_share=(core_pe_net_cash or {}).get("net_cash_per_share_vnd"),
        core_eps=(core_pe_net_cash or {}).get("core_eps_vnd"),
        target_core_pe=(core_pe_net_cash or {}).get("target_core_pe"),
        sens_low=min(cells) if cells else None,
        sens_high=max(cells) if cells else None,
        dividend_yield=dividend_yield.value if dividend_yield is not None else None,
    )
    return build_all(n)


_VALUATION_LEAK_TERMS = (
    "target price",
    "price_fcff",
    "price_fcfe",
    "fcff",
    "fcfe",
    "wacc",
    "dcf",
    "valuation",
    "giá mục tiêu",
    "gia muc tieu",
    "định giá",
    "dinh gia",
)


def _sanitize_non_valuation_narrative(text: str) -> str:
    """Remove valuation sentences from business/financial section snippets."""
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    kept = [
        part
        for part in parts
        if part and not any(term in part.lower() for term in _VALUATION_LEAK_TERMS)
    ]
    if kept:
        return " ".join(kept)
    return "Nội dung đang được chuẩn hóa theo contract section; xem trang định giá cho các giả định mô hình."


def _charts(ticker: str) -> dict[str, ChartArtifact]:
    """Discover all generated chart PNGs for *ticker* from the artifacts directory.

    Registers C1–C8 when available.  Only C1 and C2 are marked required; the
    others are opportunistic — their absence is acceptable but their presence
    improves the report's evidence density.
    """
    charts_dir = ROOT / "artifacts/charts"
    titles = {
        "C1": "Diễn biến giá cổ phiếu so với VNINDEX",
        "C2": "Doanh thu và lợi nhuận",
        "C3": "EPS và P/E lịch sử",
        "C4": "Biên lợi nhuận và ROE",
        "C5": "Dự phóng doanh thu và lợi nhuận",
        "C6": "Cầu nối định giá DCF",
        "C7": "Ma trận độ nhạy định giá",
        "C8": "So sánh định giá với cùng ngành",
    }
    captions = {
        "C1": "Nguồn: Dữ liệu thị trường; tính toán của nhóm phân tích.",
        "C2": "Nguồn: Báo cáo tài chính công ty; tính toán của nhóm phân tích.",
        "C3": "Nguồn: Báo cáo tài chính công ty; Bloomberg; tính toán của nhóm phân tích.",
        "C4": "Nguồn: Báo cáo tài chính công ty; tính toán của nhóm phân tích.",
        "C5": "Nguồn: Dự phóng của nhóm phân tích dựa trên giả định đã phê duyệt.",
        "C6": "Nguồn: Mô hình DCF nội bộ; giả định đã được phê duyệt.",
        "C7": "Nguồn: Phân tích độ nhạy — WACC × tăng trưởng dài hạn; nhóm phân tích.",
        "C8": "Nguồn: Bloomberg; báo cáo công ty; tính toán của nhóm phân tích.",
    }
    result: dict[str, ChartArtifact] = {}
    for chart_id, title in titles.items():
        path = charts_dir / f"{ticker}_{chart_id}.png"
        if path.exists():
            result[chart_id] = ChartArtifact(
                chart_id=chart_id,
                title=title,
                path=str(path),
                caption=captions.get(chart_id, "Nguồn: Nhóm phân tích."),
                required=chart_id in {"C1", "C2"},
            )
    return result


def build_client_report_view_model(
    ticker: str,
    mode: RenderMode | str = "analyst_draft",
    run_id: str | None = None,
    allow_latest_artifacts: bool = False,
) -> ClientReportViewModel:
    ticker = ticker.upper()
    company_name, exchange = _COMPANIES.get(ticker, (ticker, "HOSE"))

    manifest = None
    if run_id:
        manifest = _read_manifest_or_raise(run_id, base_dir=ROOT)

    facts = _facts(ticker, manifest, allow_latest_artifacts)
    val = _valuation(ticker, manifest, allow_latest_artifacts)
    val_result = _valuation_result(ticker, manifest, allow_latest_artifacts)
    forecast = _forecast(ticker, manifest, allow_latest_artifacts)
    fcff = _fcff(ticker, manifest, allow_latest_artifacts)
    blend = _blend(ticker, manifest, allow_latest_artifacts)
    cpnc = _core_pe_net_cash(ticker, manifest, allow_latest_artifacts)
    forecast_rows = _forecast_by_label(forecast)
    fcff_rows = _fcff_by_label(fcff)
    display_gate = _report_display_governance(mode, val_result, blend)
    # Prefer Core P/E + Net Cash target over blend target (Guidance §11)
    if cpnc:
        display_gate = _apply_core_pe_override(display_gate, cpnc)
    current_price = display_gate["current_price"]
    target_price = display_gate["target_price"]
    upside = display_gate["upside"]
    recommendation = display_gate["recommendation"]
    charts = _charts(ticker)

    snapshot = _load_market_snapshot(ticker)

    periods = _derive_periods(facts, forecast)
    shares_mn = _derive_shares_mn(facts, periods)
    if (not shares_mn) and snapshot is not None and snapshot.shares_outstanding:
        shares_mn = snapshot.shares_outstanding / 1_000_000
    if current_price is None and snapshot is not None and snapshot.last_price:
        current_price = snapshot.last_price
    dividend_per_share = _derive_dividend_per_share(facts, periods)
    if dividend_per_share is None and snapshot is not None and snapshot.dividend_per_share:
        dividend_per_share = snapshot.dividend_per_share
    market_cap = None if current_price is None or shares_mn == 0 else current_price * shares_mn / 1000
    dividend_yield = (
        Percent(dividend_per_share / current_price)
        if dividend_per_share and current_price else None
    )
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
    # Shares-outstanding integrity (PLAN §1.9 / §4.3): EPS present but no share count is a
    # critical inconsistency — EPS implies a share base, so a missing/zero count must block.
    _has_eps = any(
        _fact_value(facts, "eps.basic", _to_fact_period(p)) for p in periods if _is_actual(p)
    )
    if _has_eps and not shares_mn:
        missing.append("shares_outstanding")

    publication_status = (
        "client_exportable"
        if mode == "client_final" and not missing and str(val_result.get("is_publishable")).lower() == "true"
        else "analyst_review_only"
    )
    if mode == "client_final" and (missing or publication_status != "client_exportable"):
        missing = sorted(set(missing + ["approval_status"]))

    _narr = _build_narratives(
        ticker, company_name, facts, forecast, fcff, blend, val, periods,
        current_price, target_price, upside, recommendation, dividend_yield,
        core_pe_net_cash=cpnc if cpnc else None,
    )
    thesis = _narr["investment_thesis"]
    latest_update = _sanitize_non_valuation_narrative(_narr["latest_business_update"])
    current_context = _sanitize_non_valuation_narrative(_narr["financial_performance"])
    # Distinct growth/margin narratives (audit NARRATIVE-01: no duplicated paragraphs).
    growth_drivers = _sanitize_non_valuation_narrative(_narr["growth_drivers"])
    margin_drivers = _sanitize_non_valuation_narrative(_narr["margin_drivers"])
    events = _narr["risks_catalysts"]
    forecast_text = _narr["forecast_valuation_narrative"]
    key_forecast_drivers_table = _table_key_forecast_drivers(forecast, fcff, facts, forecast_rows, ticker)
    sensitivity_table = (
        _table_sensitivity_matrix(val.get("sensitivity", {}), display_gate["approved_for_display"])
        or _table_driver_sensitivity(fcff, blend if display_gate["approved_for_display"] else {}, forecast)
    )

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
        dividend_yield=dividend_yield,
        total_return=_total_return(upside, dividend_yield),
        market_statistics={
            "Mã giao dịch": f"{ticker} VN",
            "Sàn": exchange,
            "Ngành": "Dược phẩm",
            "Vốn hóa": market_cap,
            "Số lượng cổ phiếu": shares_mn if shares_mn else _DASH,
            "Giá cao/thấp 52 tuần": (
                f"{snapshot.low_52w:,.0f} / {snapshot.high_52w:,.0f}"
                if snapshot is not None and snapshot.high_52w and snapshot.low_52w else _DASH
            ),
            "KLGD bình quân 1 tháng": (
                f"{snapshot.avg_volume_1m:,.0f}"
                if snapshot is not None and snapshot.avg_volume_1m else _DASH
            ),
            "Tỷ lệ sở hữu nước ngoài": (
                f"{snapshot.foreign_pct * 100:.1f}%"
                if snapshot is not None and snapshot.foreign_pct is not None else _DASH
            ),
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
        key_sources=_key_sources(ticker, snapshot),
        display_blocking_reasons=display_gate["blocking_reasons"],
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
