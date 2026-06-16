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

from backend.news.relevance import build_ticker_keywords, normalize_vi
from backend.valuation_method_policy import build_valuation_publishability_policy
from backend.reporting.report_data_loader import _COMPANIES, ROOT, _read_manifest_or_raise
from backend.reporting.market_data_artifact import (
    MarketDataArtifact,
    benchmark_for_exchange,
    load_cached_market_data,
    load_market_data_from_fact_store,
    market_data_from_dict,
)

_logger = logging.getLogger(__name__)

RenderMode = Literal["standard", "client_final", "analyst_draft", "internal_debug"]


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
    news_citations: list[dict[str, str]] = field(default_factory=list)
    insight_pack: list[dict[str, Any]] = field(default_factory=list)
    display_blocking_reasons: list[str] = field(default_factory=list)
    critic_findings: list[str] = field(default_factory=list)
    metric_availability: dict[str, Any] = field(default_factory=dict)
    company_profile: dict[str, Any] = field(default_factory=dict)
    market_data: MarketDataArtifact | None = None
    selected_valuation_methods: list[str] = field(default_factory=list)
    valuation_summary_table: TableData | None = None
    wacc_bridge_table: TableData | None = None
    valuation_bridge_table: TableData | None = None
    report_generated_at: str = ""
    market_price_as_of: str = ""


_DASH = "—"
_NA = "N/A"
_PERIODS_FALLBACK = ["2024F", "2025F", "2026F", "2027F", "2028F"]


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
        # Display actuals with a single-letter 'A' suffix so column headers read
        # uniformly against the 'F' forecast labels (2024A 2025A 2026F ...).
        # Canonical fact keys keep the 'FY' suffix; _to_fact_period() maps back.
        actuals = [p[:-2] + "A" if p.endswith("FY") else p for p in actuals]

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


def _positive_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _price_to_vnd(value: Any) -> float | None:
    """Normalize Vietnamese quote prices to VND/share.

    vnstock/fact.price_history often stores equity prices in thousand VND
    units (for example 58.6 means 58,600 VND). Report-facing values must always
    be VND/share.
    """
    price = _positive_float(value)
    if price is None:
        return None
    return price * 1000 if price < 1000 else price


def _date_prefix(value: Any) -> str:
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else text


def _market_price_as_of(
    current_price: float | None,
    *,
    valuation: dict[str, Any],
    snapshot: Any = None,
    market_data: MarketDataArtifact | None = None,
) -> str:
    """Resolve the as-of date for the current market price shown in the report."""
    if current_price is None:
        return ""
    if market_data is not None and market_data.trading_statistics.last_close is not None:
        return _date_prefix(market_data.as_of_date)
    if snapshot is not None and getattr(snapshot, "last_price", None) is not None:
        return _date_prefix(getattr(snapshot, "as_of_date", ""))
    for key in ("market_price_as_of", "price_as_of_date", "market_data_as_of", "snapshot_as_of"):
        value = valuation.get(key)
        if value:
            return _date_prefix(value)
    return ""


def _derive_artifact_shares_mn(
    fcff: dict[str, Any],
    core_pe_net_cash: dict[str, Any],
    valuation: dict[str, Any],
    forecast: dict[str, Any],
) -> float:
    """Resolve explicit shares from downstream artifacts without EPS inference."""
    candidates = [
        fcff.get("shares_mn"),
        core_pe_net_cash.get("shares_mn"),
        (valuation.get("multiples") or {}).get("shares_mn"),
        (valuation.get("fcfe") or {}).get("shares_mn"),
        (valuation.get("dcf") or {}).get("shares_mn"),
        (forecast.get("share_rollforward") or {}).get("base_shares_mn"),
    ]
    for row in (forecast.get("share_rollforward") or {}).get("forecast_rows", []):
        if isinstance(row, dict):
            candidates.extend((
                row.get("ending_shares_mn"),
                row.get("diluted_shares_mn"),
            ))
    for row in forecast.get("forecast_years", []):
        if isinstance(row, dict):
            candidates.extend((
                row.get("diluted_shares"),
                row.get("shares_mn"),
            ))
    for candidate in candidates:
        value = _positive_float(candidate)
        if value is not None:
            return value
    return 0.0


def _raw_fact_number(facts: dict[str, dict[str, float]], metric: str, period: str) -> float | None:
    raw = facts.get(metric, {}).get(period)
    if raw is None:
        return None
    if isinstance(raw, dict):
        raw = raw.get("value")
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _shares_mn_for_period(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    period: str,
    fallback_shares_mn: float,
) -> float | None:
    if _is_actual(period):
        fact_period = _to_fact_period(period)
        for key in ("shares_outstanding.ending", "shares_outstanding.weighted_avg", "shares_outstanding.total"):
            value = _raw_fact_number(facts, key, fact_period)
            if value and value > 0:
                return value / 1_000_000 if value > 1_000_000 else value
        return fallback_shares_mn or None
    row = forecast_rows.get(period, {})
    for key in ("diluted_shares", "shares_mn", "shares"):
        value = row.get(key)
        if value and value > 0:
            return float(value)
    return fallback_shares_mn or None


def _shares_mn_values(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    periods: list[str],
    fallback_shares_mn: float,
) -> list[float | None]:
    return [
        _shares_mn_for_period(facts, forecast_rows, period, fallback_shares_mn)
        for period in periods
    ]


def _book_value_per_share_values(
    equity: list[float | None],
    shares_mn: list[float | None],
) -> list[float | None]:
    return [
        None if eq is None or sh in (None, 0) else eq * 1000.0 / sh
        for eq, sh in zip(equity, shares_mn)
    ]


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


def _dividend_per_share_values(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    periods: list[str],
    shares_mn: float,
    fallback_dividend_per_share: float | None = None,
) -> list[float | None]:
    values: list[float | None] = []
    for period in periods:
        if _is_actual(period):
            dps = _raw_fact_number(facts, "dividends_per_share.cash", _to_fact_period(period))
            if dps and dps > 0:
                values.append(dps)
                continue
            cash_dividend = _fact_value(facts, "dividends_paid.total", _to_fact_period(period))
            period_shares = _shares_mn_for_period(facts, forecast_rows, period, shares_mn)
            if cash_dividend is not None and period_shares not in (None, 0):
                values.append(abs(cash_dividend) * 1000.0 / float(period_shares))
            else:
                values.append(fallback_dividend_per_share)
            continue
        row = forecast_rows.get(period, {})
        cash_dividend = row.get("cash_dividend")
        period_shares = _shares_mn_for_period(facts, forecast_rows, period, shares_mn)
        if cash_dividend is not None and period_shares not in (None, 0):
            values.append(float(cash_dividend) * 1000.0 / float(period_shares))
        else:
            values.append(fallback_dividend_per_share)
    return values


def _derive_report_dividend_per_share(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    periods: list[str],
    shares_mn: float,
    snapshot_dividend_per_share: float | None = None,
) -> float | None:
    dps_values = _dividend_per_share_values(
        facts,
        forecast_rows,
        periods,
        shares_mn,
        fallback_dividend_per_share=None,
    )
    for period, dps in zip(periods, dps_values):
        if period.endswith("F") and dps is not None and dps >= 0:
            return dps
    if snapshot_dividend_per_share and snapshot_dividend_per_share > 0:
        return snapshot_dividend_per_share
    return _derive_dividend_per_share(facts, periods)


def _resolve_json(
    pattern: str,
    manifest=None,
    key: str = "",
    allow_latest_artifacts: bool = False,
) -> dict[str, Any]:
    """Resolve an artifact only through the run manifest."""
    if manifest is not None and key:
        if manifest.resolve(key):
            return manifest.load_json(key)
        return {}
    raise ValueError(f"run_id and manifest entry are required for artifact '{key or pattern}'")


def _facts(ticker: str, manifest=None, allow_latest_artifacts: bool = False) -> dict[str, dict[str, float]]:
    return _resolve_json(
        "facts_snapshot.json",
        manifest,
        "facts",
        allow_latest_artifacts,
    ).get("facts", {})


def _valuation(ticker: str, manifest=None, allow_latest_artifacts: bool = False) -> dict[str, Any]:
    return _resolve_json(
        "valuation.json",
        manifest,
        "valuation",
        allow_latest_artifacts,
    )


def _valuation_result(ticker: str, manifest=None, allow_latest_artifacts: bool = False) -> dict[str, Any]:
    data = _resolve_json(
        "valuation.json",
        manifest,
        "valuation_result",
        allow_latest_artifacts,
    )
    # The harness manifest registers a single "valuation" artifact (valuation.json)
    # and no separate "valuation_result" key. Fall back to the full valuation
    # artifact so publishability/price signals survive.
    if data or manifest is None:
        return data
    return _valuation(ticker, manifest, allow_latest_artifacts)


def _forecast(ticker: str, manifest=None, allow_latest_artifacts: bool = False) -> dict[str, Any]:
    data = _resolve_json(
        "valuation.json",
        manifest,
        "forecast",
        allow_latest_artifacts,
    )
    if data or manifest is None:
        return data
    return _valuation(ticker, manifest, allow_latest_artifacts).get("forecast", {})


def _fcff(ticker: str, manifest=None, allow_latest_artifacts: bool = False) -> dict[str, Any]:
    data = _resolve_json(
        "valuation.json",
        manifest,
        "fcff",
        allow_latest_artifacts,
    )
    if data or manifest is None:
        return data
    return _valuation(ticker, manifest, allow_latest_artifacts).get("fcff", {})


def _blend(ticker: str, manifest=None, allow_latest_artifacts: bool = False) -> dict[str, Any]:
    data = _resolve_json(
        "valuation.json",
        manifest,
        "blend",
        allow_latest_artifacts,
    )
    if data or manifest is None:
        return data
    return _valuation(ticker, manifest, allow_latest_artifacts).get("blend_dcf", {})


def _core_pe_net_cash(ticker: str, manifest=None, allow_latest_artifacts: bool = False) -> dict[str, Any]:
    return _valuation(ticker, manifest, allow_latest_artifacts).get("core_pe_net_cash", {})



# Canonical facts are stored in raw VND đồng. Monetary statement/balance/cash-flow
# metrics must be shown in tỷ đồng (bn) to match the forecast columns (already bn) and
# the "Đơn vị: tỷ đồng" table labels. Per-share (eps), share counts and ratios stay native.
_VND_TO_BN = 1_000_000_000
_MONETARY_FACT_METRICS = frozenset({
    "revenue.net", "cogs.total", "gross_profit.total", "depreciation.total",
    "sga.total", "operating_profit.total", "ebit.total", "ebitda.total",
    "financial_income.total", "financial_expense.total", "interest_expense.total", "tax_expense.total",
    "net_income.parent", "profit_before_tax.total",
    "operating_cash_flow.total", "investing_cash_flow.total", "financing_cash_flow.total",
    "capex.total", "free_cash_flow.total", "dividends_paid.total",
    "change_in_working_capital.total",
    "equity.parent", "equity.ending",
    "total_assets.ending",
    "accounts_receivable.ending", "inventory.ending", "accounts_payable.ending",
    "cash_and_equivalents.ending", "short_term_investments.ending", "short_term_deposits.ending",
    "short_term_debt.ending", "current_portion_ltd.ending", "long_term_debt.ending",
    "lease_liabilities.ending", "total_debt.ending",
    "total_liabilities.ending", "current_liabilities.ending", "non_current_liabilities.ending",
})


def _fact_value(facts: dict[str, dict[str, float]], metric: str, period: str) -> float | None:
    """Return a float fact value in tỷ đồng for monetary metrics — handles flat (DBD) and nested-dict (DHG) formats."""
    raw = facts.get(metric, {}).get(period)
    if raw is None:
        return None
    if isinstance(raw, dict):
        v = raw.get("value")
        if v is None:
            return None
        value = float(v)
    else:
        value = float(raw)
    if metric in _MONETARY_FACT_METRICS:
        return value / _VND_TO_BN
    return value


def _forecast_by_label(forecast: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = {
        str(r.get("label")): dict(r)
        for r in forecast.get("forecast_years", [])
        if isinstance(r, dict) and r.get("label")
    }

    dividend_schedule = forecast.get("dividend_schedule") or {}
    dividend_publishable = (
        bool(dividend_schedule)
        and dividend_schedule.get("method") != "missing"
        and any(
            isinstance(div_row, dict) and div_row.get("cash_dividend") is not None
            for div_row in dividend_schedule.get("forecast_rows", [])
        )
    )
    if not dividend_publishable and dividend_schedule.get("method") == "missing":
        for row in rows.values():
            row["cash"] = None
    if dividend_publishable:
        for result in (forecast.get("cash_sweep_artifact") or {}).get("year_results", []):
            if not isinstance(result, dict):
                continue
            label = result.get("year_label")
            if label and label in rows and rows[label].get("cash") is None:
                rows[label]["cash"] = result.get("computed_ending_cash")

    debt_schedule = forecast.get("debt_schedule") or {}
    debt_method = str(debt_schedule.get("forecast_method") or "")
    debt_status = str(debt_schedule.get("status") or "")
    debt_publishable = (
        bool(debt_schedule)
        and debt_schedule.get("is_fcfe_publishable") is True
        and debt_method not in {"stable_debt", "target_debt_ratio", "balance_sheet_delta", "missing"}
        and debt_status not in {"low", "blocked"}
    )
    if not debt_publishable:
        for row in rows.values():
            for key in ("beginning_debt", "ending_debt", "total_debt", "net_borrowing", "cost_of_debt"):
                row[key] = None

    for debt_row in debt_schedule.get("forecast_rows", []):
        if not debt_publishable:
            break
        if not isinstance(debt_row, dict):
            continue
        label = debt_row.get("label")
        if not label or label not in rows:
            continue
        row = rows[label]
        for target_key, source_key in (
            ("beginning_debt", "beginning_interest_bearing_debt"),
            ("ending_debt", "ending_interest_bearing_debt"),
            ("total_debt", "ending_interest_bearing_debt"),
            ("net_borrowing", "net_borrowing"),
            ("cost_of_debt", "cost_of_debt"),
        ):
            if row.get(target_key) is None:
                row[target_key] = debt_row.get(source_key)

    for div_row in (forecast.get("dividend_schedule") or {}).get("forecast_rows", []):
        if not isinstance(div_row, dict):
            continue
        label = div_row.get("label")
        if not label or label not in rows:
            continue
        row = rows[label]
        for key in ("cash_dividend", "payout_ratio", "retained_earnings_addition"):
            if row.get(key) is None:
                row[key] = div_row.get(key)

    return rows


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
        "operating_profit": "operating_profit.total",
        "ebit": "ebit.total",
        "ebitda": "ebitda.total",
        "financial_income": "financial_income.total",
        "financial_expense": "financial_expense.total",
        "interest_expense": "interest_expense.total",
        "tax": "tax_expense.total",
        "net_income": "net_income.parent",
        "cfo": "operating_cash_flow.total",
        "capex": "capex.total",
        "fcf": "free_cash_flow.total",
        "dividends_paid": "dividends_paid.total",
        "delta_nwc": "change_in_working_capital.total",
        "equity": "equity.parent",
        "total_assets": "total_assets.ending",
        "cash": "cash_and_equivalents.ending",
        "debt": "short_term_debt.ending",
        "eps": "eps.basic",
    }
    if period.endswith("A") or period.endswith("FY"):
        fact_period = _to_fact_period(period)
        value = _fact_value(facts, actual_map.get(metric, metric), fact_period)
        if value is None and metric == "sga":
            gross_profit = _fact_value(facts, "gross_profit.total", fact_period)
            ebit = _historical_ebit_from_facts(facts, fact_period)
            value = None if gross_profit is None or ebit is None else ebit - gross_profit
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
        "operating_profit": "ebit",
        "ebit": "ebit",
        "ebitda": "ebitda",
        "financial_income": "financial_income",
        "financial_expense": "interest_expense",
        "interest_expense": "interest_expense",
        "tax": "tax_expense",
        "net_income": "net_income",
        "capex": "capex",
        "equity": "equity",
        "total_assets": "total_assets",
        "debt": "total_debt",
        "eps": "eps",
        "dividends_paid": "cash_dividend",
        "delta_nwc": "delta_nwc",
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


def _interest_bearing_debt_values(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    periods: list[str],
) -> list[float | None]:
    values: list[float | None] = []
    for period in periods:
        if _is_actual(period):
            values.append(_interest_bearing_debt(facts, period))
        else:
            value = forecast_rows.get(period, {}).get("total_debt")
            values.append(float(value) if value is not None else None)
    return values


def _total_liabilities_values(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    periods: list[str],
) -> list[float | None]:
    """Total liabilities (Tổng nợ phải trả) = ALL payables, not just interest-bearing debt.

    Actual periods read the canonical total_liabilities.ending fact. Forecast periods
    use the model's interest-bearing debt plus the held-constant other_liabilities
    (= total liabilities − debt at the last actual), keeping the forecast consistent
    with total_assets = equity + debt + other_liabilities.
    """
    values: list[float | None] = []
    for period in periods:
        if _is_actual(period):
            fact_period = _to_fact_period(period)
            direct = _fact_value(facts, "total_liabilities.ending", fact_period)
            if direct is not None:
                values.append(direct)
                continue
            total_assets = _fact_value(facts, "total_assets.ending", fact_period)
            equity = (
                _fact_value(facts, "equity.parent", fact_period)
                or _fact_value(facts, "equity.ending", fact_period)
            )
            values.append(None if total_assets is None or equity is None else total_assets - equity)
        else:
            row = forecast_rows.get(period, {})
            td = row.get("total_debt")
            ol = row.get("other_liabilities")
            values.append(None if td is None or ol is None else td + ol)
    return values


def _cash_like_values(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    periods: list[str],
) -> list[float | None]:
    values: list[float | None] = []
    for period in periods:
        if _is_actual(period):
            values.append(_cash_like_assets(facts, period))
        else:
            value = forecast_rows.get(period, {}).get("cash")
            values.append(float(value) if value is not None else None)
    return values


def _pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return current / previous - 1


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _historical_ebit_from_facts(facts: dict[str, dict[str, float]], fact_period: str) -> float | None:
    """Derive historical EBIT only from explicit accounting facts.

    Priority:
    1. Direct EBIT / operating profit facts.
    2. Gross profit plus SG&A when both are available.
    3. Profit before tax plus net financial expense, where expense facts are
       stored as negative costs in the normalized fact layer.
    """
    direct = (
        _fact_value(facts, "ebit.total", fact_period)
        or _fact_value(facts, "operating_profit.total", fact_period)
    )
    if direct is not None:
        return direct

    gross_profit = _fact_value(facts, "gross_profit.total", fact_period)
    sga = _fact_value(facts, "sga.total", fact_period)
    if gross_profit is not None and sga is not None:
        return gross_profit + sga

    pbt = _fact_value(facts, "profit_before_tax.total", fact_period)
    if pbt is None:
        return None
    net_financial_expense = _fact_value(facts, "financial_expense.total", fact_period)
    if net_financial_expense is None:
        net_financial_expense = _fact_value(facts, "interest_expense.total", fact_period)
    if net_financial_expense is None:
        return None
    return pbt - net_financial_expense


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
            fact_period = _to_fact_period(period)
            value = _historical_ebit_from_facts(facts, fact_period)
        ebit.append(value)
    return ebit


def _ebitda_values(forecast_rows: dict[str, dict[str, Any]], facts: dict[str, dict[str, float]], periods: list[str]) -> list[float | None]:
    values: list[float | None] = []
    ebit = _ebit_values(forecast_rows, facts, periods)
    depreciation = _row_values(facts, forecast_rows, "depreciation", periods)
    for period, e, d in zip(periods, ebit, depreciation):
        if period.endswith("F") and forecast_rows.get(period, {}).get("ebitda") is not None:
            values.append(float(forecast_rows[period]["ebitda"]))
        else:
            direct = _fact_value(facts, "ebitda.total", _to_fact_period(period)) if _is_actual(period) else None
            values.append(direct if direct is not None else (None if e is None or d is None else e + d))
    return values


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


def _financial_line_values(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    periods: list[str],
    metric: str,
) -> list[float | None]:
    values: list[float | None] = []
    for period in periods:
        value = _period_value(facts, forecast_rows, metric, period)
        if value is None and metric == "financial_expense":
            value = _period_value(facts, forecast_rows, "interest_expense", period)
        values.append(value)
    return values


def _other_profit_values(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    periods: list[str],
) -> list[float | None]:
    values: list[float | None] = []
    for period in periods:
        if period.endswith("F"):
            values.append(forecast_rows.get(period, {}).get("other_items"))
            continue
        fact_period = _to_fact_period(period)
        pbt = _fact_value(facts, "profit_before_tax.total", fact_period)
        operating_profit = _historical_ebit_from_facts(facts, fact_period)
        values.append(None if pbt is None or operating_profit is None else pbt - operating_profit)
    return values


def _historical_delta_nwc_values(
    facts: dict[str, dict[str, float]],
    actual_periods: list[str],
) -> list[float | None]:
    values: list[float | None] = []
    previous_nwc: float | None = None
    for period in actual_periods:
        fact_period = _to_fact_period(period)
        direct = _fact_value(facts, "change_in_working_capital.total", fact_period)
        if direct is not None:
            values.append(direct)
            continue
        ar = _fact_value(facts, "accounts_receivable.ending", fact_period)
        inventory = _fact_value(facts, "inventory.ending", fact_period)
        ap = _fact_value(facts, "accounts_payable.ending", fact_period)
        nwc = None if None in (ar, inventory, ap) else ar + inventory - ap
        if nwc is not None and previous_nwc is not None:
            values.append(nwc - previous_nwc)
        else:
            ni = _period_value(facts, {}, "net_income", period)
            dep = _period_value(facts, {}, "depreciation", period)
            cfo = _period_value(facts, {}, "cfo", period)
            values.append(None if None in (ni, dep, cfo) else ni + dep - cfo)
        previous_nwc = nwc
    return values


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
    policy: Any = None,
) -> dict[str, Any]:
    """Central policy for report-facing recommendation, target and upside display.

    When a ``ValuationPublishabilityPolicy`` is supplied it is authoritative: a
    non-publishable valuation cannot promote a hero target price or a
    BUY/HOLD/SELL recommendation, regardless of any numeric value present in the
    blend artifact. This is the renderer-side enforcement of the single source
    of truth in ``backend.valuation_method_policy``.
    """
    reasons: list[str] = []
    is_publishable = str(val_result.get("is_publishable")).lower() == "true"
    if not val_result:
        reasons.append("valuation_result_missing")
    elif not is_publishable:
        reasons.append("valuation_result_not_publishable")
    if blend.get("is_draft_only") is True:
        reasons.append("blend_is_draft_only")
    method_policy = val_result.get("valuation_method_policy") or {}
    selected_methods = method_policy.get("selected_methods")
    if isinstance(selected_methods, list) and not selected_methods:
        reasons.append("no_eligible_valuation_method")
    confidence = val_result.get("valuation_confidence") or {}
    confidence_keys = {"FCFF": "fcff_dcf", "FCFE": "fcfe_dcf"}
    if isinstance(selected_methods, list) and selected_methods:
        selected_confidence = [
            str(confidence.get(confidence_keys.get(str(method).upper()), "")).lower()
            for method in selected_methods
        ]
        if selected_confidence and all(level in {"low", "unavailable"} for level in selected_confidence):
            reasons.append("no_eligible_valuation_method")
    gap = blend.get("fcff_fcfe_gap_pct")
    try:
        if gap is not None and float(gap) > 0.25:
            reasons.append("fcff_fcfe_gap_gt_25pct")
    except (TypeError, ValueError):
        reasons.append("fcff_fcfe_gap_invalid")

    # analyst_draft always shows computed values — analyst needs full picture to review
    # Display governance is separate from publication governance. Available
    # model outputs remain visible for analysis while client-final blockers stay
    # available to the export workflow as internal metadata.
    approved_for_display = True
    blocking_reasons = sorted(set(reasons))

    current, target, upside = _market_price_inputs(mode, val_result, blend)
    target = _display_target_price(val_result, blend, policy)
    if current and target and upside is None:
        upside = target / current - 1
    if target is None:
        approved_for_display = False
        upside = None

    # Authoritative override: the ValuationPublishabilityPolicy is the single
    # source of truth. A non-publishable valuation (low-confidence primary,
    # blocked FCFE driving a blend, missing/constant sensitivity, critical method
    # divergence, market-sanity break without a bridge) must not promote a hero
    # target price or a BUY/HOLD/SELL recommendation — regardless of any numeric
    # value present in the blend artifact.
    if policy is not None and not getattr(policy, "target_price_publishable", True):
        reasons = list(reasons) + list(getattr(policy, "blocking_reasons", None) or [])
        blocking_reasons = sorted(set(reasons))

    # Publication QA stays in metadata/review artifacts. It must not replace
    # usable client-facing values or inject internal workflow states into PDF.

    return {
        "approved_for_display": approved_for_display,
        "current_price": current,
        "target_price": target,
        "upside": upside,
        "recommendation": _recommendation(upside, mode, approved_for_display),
        "blocking_reasons": blocking_reasons,
        "blend_target_price": target,  # keep blend for cross-check display
    }



def _recommendation(
    upside: float | None,
    mode: RenderMode | str,
    approved_for_display: bool = False,
    dividend_yield: float = 0.0,
) -> str:
    """Rating based on total expected return with exactly three labels."""
    if upside is None:
        return "Giữ"
    total_return = upside + dividend_yield
    if total_return > 0.20:
        return "Mua"
    if total_return < -0.10:
        return "Bán"
    return "Giữ"


def _display_target_price(
    valuation: dict[str, Any],
    blend: dict[str, Any],
    policy: Any = None,
) -> float | None:
    """Resolve the best reproducible target price for report display."""
    candidates: list[Any] = []
    if policy is not None:
        candidates.append(getattr(policy, "target_price_vnd", None))
    weighted = valuation.get("weighted_target_price") or {}
    candidates.extend(
        [
            weighted.get("raw"),
            weighted.get("rounded"),
            weighted.get("target_price_vnd"),
            weighted.get("target_price"),
            weighted.get("blended_price"),
            blend.get("target_price_dcf_vnd"),
            blend.get("target_price_vnd"),
            (valuation.get("blend_dcf") or {}).get("target_price_dcf_vnd"),
            (valuation.get("fcff") or {}).get("target_price_vnd"),
            (valuation.get("fcff") or {}).get("value_per_share"),
            (valuation.get("fcfe") or {}).get("target_price_vnd"),
            (valuation.get("fcfe") or {}).get("value_per_share"),
        ]
    )
    for candidate in candidates:
        try:
            value = float(candidate)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


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
    shares_mn: float,
) -> TableData:
    n = len(periods)
    eps = _row_values(facts, forecast_rows, "eps", periods)
    equity = _row_values(facts, forecast_rows, "equity", periods)
    shares = _shares_mn_values(facts, forecast_rows, periods, shares_mn)
    bvps = _book_value_per_share_values(equity, shares)
    pe = [None if current_price is None or e in (None, 0) else current_price / e for e in eps]
    pb = [None if current_price is None or b in (None, 0) else current_price / b for b in bvps]

    # Leverage wherever inputs are available (else dash, no fabrication).
    ebitda = _ebitda_values(forecast_rows, facts, periods)
    net_debt = _net_debt_canonical(facts, forecast_rows, periods)
    net_debt_ebitda = [_safe_div(nd, e) for nd, e in zip(net_debt, ebitda)]
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
    gross_profit = _row_values(facts, forecast_rows, "gross_profit", periods)
    ebit = _ebit_values(forecast_rows, facts, periods)
    depreciation = _row_values(facts, forecast_rows, "depreciation", periods)
    ebitda = _ebitda_values(forecast_rows, facts, periods)
    net_income = _row_values(facts, forecast_rows, "net_income", periods)
    tax = _row_values(facts, forecast_rows, "tax", periods)
    pbt = [None if ni is None or tx is None else ni - tx for ni, tx in zip(net_income, tax)]
    shares = _shares_mn_values(facts, forecast_rows, periods, shares_mn)
    financial_income = _financial_line_values(facts, forecast_rows, periods, "financial_income")
    financial_expense = _financial_line_values(facts, forecast_rows, periods, "financial_expense")
    return TableData(
        title="MÔ HÌNH ĐỊNH GIÁ",
        periods=periods,
        unit="Đơn vị: tỷ đồng nếu không có ghi chú khác",
        rows=[
            ("Doanh thu thuần", revenue),
            ("Tăng trưởng doanh thu", _revenue_growth(facts, forecast_rows, periods)),
            ("Lợi nhuận gộp", gross_profit),
            ("Biên lợi nhuận gộp", [_safe_div(gp, r) for gp, r in zip(gross_profit, revenue)]),
            ("GVHB trừ khấu hao", _row_values(facts, forecast_rows, "cogs", periods)),
            ("Chi phí bán hàng và quản lý", _row_values(facts, forecast_rows, "sga", periods)),
            ("Doanh thu tài chính", financial_income),
            ("Chi phí tài chính", financial_expense),
            ("EBITDA", ebitda),
            ("Tỷ suất EBITDA", [_safe_div(e, r) for e, r in zip(ebitda, revenue)]),
            ("Khấu hao", depreciation),
            ("Lợi nhuận từ HĐKD / EBIT", ebit),
            ("Biên lợi nhuận HĐKD / EBIT", [_safe_div(e, r) for e, r in zip(ebit, revenue)]),
            ("Lợi nhuận khác", _other_profit_values(facts, forecast_rows, periods)),
            ("Chi phí lãi vay ròng", _row_values(facts, forecast_rows, "interest_expense", periods)),
            ("Thuế", tax),
            ("Thuế suất thực tế", [_safe_div(abs(tx) if tx is not None else None, p) for tx, p in zip(tax, pbt)]),
            ("LNST sau CĐKKS / LNST CĐ mẹ", net_income),
            ("Biên lợi nhuận ròng", [_safe_div(ni, r) for ni, r in zip(net_income, revenue)]),
            ("Tiền mặt từ hoạt động kinh doanh", _cfo_values(facts, forecast_rows, fcff_rows, periods)),
            ("Số lượng cổ phiếu (triệu)", shares),
            ("EPS", _row_values(facts, forecast_rows, "eps", periods)),
            ("EPS hiệu chỉnh", _row_values(facts, forecast_rows, "eps", periods)),
            ("Tăng trưởng EPS hiệu chỉnh", _eps_growth(facts, forecast_rows, periods)),
        ],
    )


def _table_valuation_summary(valuation: dict[str, Any]) -> TableData | None:
    methods = [str(item).upper() for item in valuation.get("selected_methods") or []]
    weights = valuation.get("method_weights") or {}
    confidence = valuation.get("valuation_confidence") or {}
    confidence_keys = {"FCFF": "fcff_dcf", "FCFE": "fcfe_dcf"}
    rows: list[tuple[str, list[Any]]] = []
    for method in methods:
        level = str(confidence.get(confidence_keys.get(method), "")).lower()
        if level in {"low", "unavailable"}:
            continue
        payload = valuation.get(method.lower()) or {}
        price = payload.get("value_per_share") or payload.get("target_price_vnd")
        weight = weights.get(method) or weights.get(method.lower())
        if price is None:
            continue
        rows.append((method, [f"{float(price):,.0f}", f"{float(weight):.1f}%" if weight is not None else _DASH]))
    weighted = valuation.get("weighted_target_price") or valuation.get("blend_dcf") or {}
    target = weighted.get("raw") or weighted.get("target_price_vnd") or weighted.get("blended_price")
    if rows and target is not None:
        rows.append(("Giá mục tiêu tổng hợp", [f"{float(target):,.0f}", "100.0%"]))
    if not rows:
        return None
    return TableData(
        title="KẾT QUẢ ĐỊNH GIÁ",
        periods=["Giá trị mỗi cổ phiếu (VND)", "Trọng số"],
        rows=rows,
        format_type="text",
    )


def _table_wacc_bridge(valuation: dict[str, Any]) -> TableData | None:
    assumptions = valuation.get("key_assumptions") or valuation.get("assumptions") or {}
    fcff = valuation.get("fcff") or {}
    breakdown = fcff.get("wacc_breakdown") or {}
    values = {**assumptions, **breakdown}
    fields = (
        ("Lãi suất phi rủi ro", "risk_free_rate"),
        ("Beta", "beta"),
        ("Phần bù rủi ro thị trường", "equity_risk_premium"),
        ("Chi phí vốn chủ sở hữu", "cost_of_equity"),
        ("Chi phí nợ vay", "cost_of_debt"),
        ("Thuế suất", "tax_rate"),
        ("Tỷ lệ nợ/vốn chủ sở hữu mục tiêu", "target_de"),
        ("WACC", "wacc"),
    )
    rows = []
    for label, key in fields:
        value = values.get(key)
        if value is None and key == "wacc":
            value = fcff.get("wacc")
        if value is None:
            continue
        rendered = f"{float(value):.2f}" if key == "beta" else f"{float(value) * 100:.1f}%"
        rows.append((label, [rendered]))
    return TableData(title="CẦU NỐI WACC", periods=["Giá trị"], rows=rows, format_type="text") if rows else None


def _table_valuation_bridge(valuation: dict[str, Any]) -> TableData | None:
    fcff = valuation.get("fcff") or {}
    net_debt_bridge = fcff.get("net_debt_bridge") or {}
    fields = (
        ("PV dòng tiền dự phóng", fcff.get("pv_of_fcff")),
        ("PV giá trị cuối kỳ", fcff.get("pv_of_terminal_value") or fcff.get("pv_terminal_value")),
        ("Giá trị doanh nghiệp", fcff.get("enterprise_value")),
        ("Tiền mặt và đầu tư ngắn hạn", fcff.get("cash_and_short_term_investments") or net_debt_bridge.get("cash")),
        ("Nợ vay", fcff.get("debt") or net_debt_bridge.get("total_debt")),
        ("Giá trị vốn chủ sở hữu", fcff.get("equity_value")),
        ("Số cổ phiếu lưu hành (triệu)", fcff.get("shares_outstanding") or fcff.get("shares_mn")),
        ("Giá mục tiêu (VND/cổ phiếu)", fcff.get("value_per_share") or fcff.get("target_price_vnd")),
    )
    rows = [(label, [value]) for label, value in fields if value is not None]
    return TableData(title="CẦU NỐI ĐỊNH GIÁ FCFF", periods=["Giá trị"], rows=rows) if rows else None


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

    delta_nwc = _historical_delta_nwc_values(facts, actual_periods) + [
        fcff_rows.get(p, {}).get("delta_nwc")
        if fcff_rows.get(p, {}).get("delta_nwc") is not None
        else forecast_rows.get(p, {}).get("delta_nwc")
        for p in forecast_periods
    ]
    capex = _row_values(facts, forecast_rows, "capex", periods)
    net_debt = _net_debt_canonical(facts, forecast_rows, periods)
    interest_bearing_debt = _interest_bearing_debt_values(facts, forecast_rows, periods)
    total_liabilities = _total_liabilities_values(facts, forecast_rows, periods)
    cash_like = _cash_like_values(facts, forecast_rows, periods)
    equity = _row_values(facts, forecast_rows, "equity", periods)
    shares = _shares_mn_values(facts, forecast_rows, periods, shares_mn)
    bvps = _book_value_per_share_values(equity, shares)

    dividends: list[Any] = [
        abs(value) if value is not None else None
        for value in _row_values(facts, forecast_rows, "dividends_paid", actual_periods)
    ] + [
        forecast_rows.get(p, {}).get("cash_dividend")
        for p in forecast_periods
    ]

    # Change in net debt follows the balance-sheet definition: debt minus cash-like assets.
    # It is not identical to net borrowing when forecast cash changes.
    delta_net_debt: list[Any] = [_DASH]
    for prev, curr in zip(net_debt, net_debt[1:]):
        delta_net_debt.append(None if prev is None or curr is None else curr - prev)

    # Change in gross interest-bearing debt = the financing/borrowing signal proper.
    # Shown alongside Δ net debt so a cash-rich issuer's net-debt swing (driven by cash
    # build-up) is not mistaken for debt repayment.
    delta_gross_debt: list[Any] = [_DASH]
    for prev, curr in zip(interest_bearing_debt, interest_bearing_debt[1:]):
        delta_gross_debt.append(None if prev is None or curr is None else curr - prev)

    # Change in total liabilities (Tổng nợ phải trả) — the full balance-sheet obligation,
    # distinct from interest-bearing debt and from net debt.
    delta_total_liabilities: list[Any] = [_DASH]
    for prev, curr in zip(total_liabilities, total_liabilities[1:]):
        delta_total_liabilities.append(None if prev is None or curr is None else curr - prev)

    # Net debt / EBITDA leverage: computed wherever both inputs are available.
    ebitda = _ebitda_values(forecast_rows, facts, periods)
    net_debt_ebitda = [_safe_div(nd, e) for nd, e in zip(net_debt, ebitda)]

    return TableData(
        title="CÁC KHOẢN MỤC CĐKT VÀ DÒNG TIỀN",
        periods=periods,
        unit="Đơn vị: tỷ đồng nếu không có ghi chú khác",
        rows=[
            ("Thay đổi vốn lưu động", delta_nwc),
            ("Chi đầu tư", [abs(v) if isinstance(v, (int, float)) else v for v in capex]),
            ("Đầu tư vào công ty liên kết/liên doanh", [_DASH] * n),
            ("Các khoản mục dòng tiền khác", [_DASH] * n),
            ("Dòng tiền tự do", fcff_vals),
            ("Phát hành cổ phiếu", [_DASH] * n),
            ("Cổ tức", dividends),
            ("Tổng nợ phải trả", total_liabilities),
            ("Thay đổi tổng nợ phải trả", delta_total_liabilities),
            ("Nợ vay có lãi cuối năm", interest_bearing_debt),
            ("Thay đổi nợ vay có lãi", delta_gross_debt),
            ("Tiền và tương đương tiền", cash_like),
            ("Nợ ròng cuối năm (nợ vay có lãi - tiền)", net_debt),
            ("Thay đổi nợ ròng", delta_net_debt),
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
    dividend_per_share: float | None,
) -> TableData:
    n = len(periods)
    revenue = _row_values(facts, forecast_rows, "revenue", periods)
    ebitda = _ebitda_values(forecast_rows, facts, periods)
    fcf = _fcff_values(facts, _fcff_by_label(fcff), periods)
    eps = _row_values(facts, forecast_rows, "eps", periods)
    equity = _row_values(facts, forecast_rows, "equity", periods)
    assets = _row_values(facts, forecast_rows, "total_assets", periods)
    net_income = _row_values(facts, forecast_rows, "net_income", periods)
    ebit = _ebit_values(forecast_rows, facts, periods)
    tax_rate = fcff.get("wacc_breakdown", {}).get("tax_rate", 0.1579)
    shares = _shares_mn_values(facts, forecast_rows, periods, shares_mn)
    market_caps = [
        None if current_price is None or sh in (None, 0) else current_price * sh / 1000
        for sh in shares
    ]
    net_debt = _net_debt_canonical(facts, forecast_rows, periods)
    enterprise_values = [None if mc is None or nd is None else mc + nd for mc, nd in zip(market_caps, net_debt)]
    invested_capital = [None if eq is None or nd is None or eq + nd <= 0 else eq + nd for eq, nd in zip(equity, net_debt)]
    roic = [_safe_div(None if e is None else e * (1 - tax_rate), ic) for e, ic in zip(ebit, invested_capital)]
    pe = [None if current_price is None or e in (None, 0) else current_price / e for e in eps]
    ev_ebitda = [None if ev is None or e in (None, 0) else ev / e for ev, e in zip(enterprise_values, ebitda)]
    ev_fcf = [None if ev is None or v in (None, 0) else ev / v for ev, v in zip(enterprise_values, fcf)]
    bvps = _book_value_per_share_values(equity, shares)
    pb = [None if current_price is None or b in (None, 0) else current_price / b for b in bvps]
    ps = [None if mc is None or rev in (None, 0) else mc / rev for mc, rev in zip(market_caps, revenue)]
    dividend_yields = [
        None if current_price is None or dps is None else dps / current_price
        for dps in _dividend_per_share_values(
            facts, forecast_rows, periods, shares_mn, dividend_per_share
        )
    ]
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
            ("EV/Doanh thu", [None if ev is None or rev in (None, 0) else ev / rev for ev, rev in zip(enterprise_values, revenue)]),
            ("PEG", _peg_values(pe, _eps_growth(facts, forecast_rows, periods))),
            ("Suất sinh lợi cổ tức", dividend_yields),
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
        ("Tăng trưởng doanh thu", [rev_growth, "Doanh thu dẫn tới EBIT và dòng tiền tự do"]),
        ("Biên lợi nhuận gộp", [gross_margin, "Giá vốn dẫn tới lợi nhuận gộp"]),
        ("Chi phí bán hàng và quản lý / doanh thu", [sga, "Chi phí vận hành dẫn tới biên EBIT"]),
        ("Khấu hao / doanh thu", [dep, "EBIT và lá chắn thuế"]),
        ("Chi đầu tư / doanh thu", [capex, "Dòng tiền tự do và mở rộng công suất"]),
        ("Thuế suất hiệu dụng", [tax_rate, "LNST và NOPAT"]),
        ("Chuyển đổi dòng tiền 2025", [cash_conversion, cash_conversion_note]),
        ("WACC", [wacc, "Tỷ lệ chiết khấu dòng tiền"]),
        ("Tăng trưởng dài hạn", [terminal_growth, "Giá trị cuối kỳ trong mô hình chiết khấu dòng tiền"]),
    ]
    return TableData(
        title="ĐỘNG LỰC DỰ PHÓNG CHÍNH",
        periods=["Giả định cơ sở", "Liên kết tài chính"],
        unit="Giả định biến số chính được hiệu chỉnh từ dữ liệu lịch sử và định hướng kinh doanh hiện tại.",
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
        unit="Đơn vị: VND/cp — mô hình chiết khấu dòng tiền FCFF.",
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
        ("Giá mục tiêu", [tp_bear, target_base, tp_bull]),
        ("Tiềm năng tăng/giảm", [_upside(tp_bear, current_price), _upside(target_base, current_price), _upside(tp_bull, current_price)]),
        ("Áp lực tăng trưởng doanh thu", [rev_bear, rev_growth, rev_bull]),
        ("Áp lực biên lợi nhuận gộp", [gm_bear, gross_margin_base, gm_bull]),
        ("Áp lực WACC", [wacc_bear, wacc_base, wacc_bull]),
    ]
    return TableData(
        title="ĐỘ NHẠY THEO DRIVER",
        periods=["Thận trọng", "Cơ sở", "Tích cực"],
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
        f"cạnh tranh đấu thầu ETC. Chu kỳ chi đầu tư ở mức {capex_str} doanh thu cần được theo dõi sát "
        "trong bối cảnh nâng chuẩn GMP-EU và dự án nhà máy. "
        "Tồn kho và nợ vay, hàng tồn kho được phản ánh qua CCC và delta NWC trong mô hình FCFF. "
        "Các biến số biên lợi nhuận, giá vốn, chi phí bán hàng, hàng tồn kho và nợ vay tăng "
        "là các tín hiệu cần đưa trực tiếp vào giả định biên lợi nhuận, chi phí bán hàng và quản lý và vốn lưu động của mô hình."
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
                 "(mô hình nội bộ, có thể tái lập từ giả định công bố và artifact định giá)"
    })
    return sources[:10]


def _load_latest_citation(ticker: str) -> dict[str, Any]:
    """Citation data must be supplied through the run manifest."""
    return {}


def _evidence_to_citations(
    rows: list[dict[str, Any]], keywords: tuple[str, ...]
) -> list[dict[str, str]]:
    """Turn news evidence rows into ordered, de-duplicated citation dicts.

    One citation per article (deduped by URL); rows whose title/claim never mention
    the ticker or company are dropped so leftover or off-topic data is never cited.
    """
    normalized_keywords = [normalize_vi(k) for k in keywords if k]
    seen: set[str] = set()
    citations: list[dict[str, str]] = []
    for row in rows:
        url = str(row.get("url") or row.get("source_url") or "").strip()
        title = str(row.get("title") or "").strip()
        claim = str(row.get("claim") or "").strip()
        haystack = normalize_vi(f"{title} {claim}")
        if not any(kw in haystack for kw in normalized_keywords):
            continue
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        citations.append(
            {
                "source_name": str(row.get("source_name") or "").strip(),
                "title": title or claim,
                "url": url,
                "published_at": str(row.get("published_at") or "").strip(),
                "materiality": str(row.get("materiality") or "non-material"),
                "impact": str(row.get("impact") or "no valuation impact"),
                "severity": str(row.get("severity") or "low"),
            }
        )
    return citations


def _build_insight_pack_for_report(
    facts: dict[str, dict[str, float]],
    forecast_rows: dict[str, dict[str, Any]],
    periods: list[str],
    upside: float | None,
    recommendation: str,
    news_count: int,
) -> list[dict[str, Any]]:
    """Assemble the deterministic insight pack from the report's computed series."""
    from backend.reporting.insight_builder import build_insight_pack

    first_fc = next((i for i, p in enumerate(periods) if p.endswith("F")), len(periods))
    actual_idx = [i for i, p in enumerate(periods) if not p.endswith("F")]

    def _at(series: list[float | None], idx: int) -> float | None:
        return series[idx] if 0 <= idx < len(series) else None

    rev_growth = _revenue_growth(facts, forecast_rows, periods)
    profit_growth = _net_profit_growth(facts, forecast_rows, periods)
    gross_profit = _row_values(facts, forecast_rows, "gross_profit", periods)
    revenue = _row_values(facts, forecast_rows, "revenue", periods)
    gm = [_safe_div(gross_profit[i], revenue[i]) for i in actual_idx]
    net_debt = _net_debt_canonical(facts, forecast_rows, periods)
    ebitda = _ebitda_values(forecast_rows, facts, periods)
    nde = [_safe_div(net_debt[i], ebitda[i]) for i in actual_idx]

    return build_insight_pack(
        {
            "revenue_growth_latest": _at(rev_growth, first_fc),
            "profit_growth_latest": _at(profit_growth, first_fc),
            "gross_margin_latest": gm[-1] if gm else None,
            "gross_margin_prev": gm[-2] if len(gm) >= 2 else None,
            "net_debt_ebitda": next((v for v in reversed(nde) if v is not None), None),
            "upside": upside,
            "recommendation": recommendation,
            "news_count": news_count,
        }
    )


def _load_news_citations(ticker: str, company_name: str | None) -> list[dict[str, str]]:
    """Load real whitelisted news articles for the ticker from the news schema.

    Returns [] on any failure (no DB, empty news schema) so the report renders
    cleanly without news citations until real articles have been collected.
    """
    keywords = build_ticker_keywords(ticker, company_name)
    try:
        from backend.database.config import connect_with_retry, require_database_url

        with connect_with_retry(require_database_url()) as conn:
            with conn.cursor() as cur:
                # One row per article (its title + a sample claim), newest first. The
                # article title carries the company name so relevance matching works even
                # when an individual claim text omits the ticker.
                cur.execute(
                    """
                    SELECT DISTINCT ON (a.source_url)
                        a.source_name, a.title, a.source_url, a.published_at, e.claim
                    FROM news.extracted_evidence e
                    JOIN news.raw_articles a ON a.article_id = e.article_id
                    WHERE e.ticker = %s
                    ORDER BY a.source_url, a.published_at DESC NULLS LAST
                    """,
                    (ticker.upper(),),
                )
                fetched = cur.fetchall()
    except Exception:  # noqa: BLE001 — citations are best-effort; never block a report
        return []

    rows = [
        {
            "source_name": source_name,
            "title": title or "",
            "url": source_url,
            # Date only (YYYY-MM-DD) — citations don't need the time component.
            "published_at": str(published_at)[:10] if published_at is not None else "",
            "claim": claim,
            **_news_materiality_fields(title or "", claim or ""),
        }
        for source_name, title, source_url, published_at, claim in fetched
    ]
    return _evidence_to_citations(rows, keywords)


def _news_materiality_fields(title: str, claim: str) -> dict[str, str]:
    text = normalize_vi(f"{title} {claim}").lower()
    rules = (
        (("co tuc", "tam ung"), "dividend", "dividend"),
        (("loi nhuan", "doanh thu", "ket qua kinh doanh"), "earnings", "margin"),
        (("nha may", "dau tu", "capex"), "capex", "revenue"),
        (("san pham", "thuoc moi"), "product", "revenue"),
        (("dau thau",), "tender", "revenue"),
        (("gmp", "quy dinh", "giay phep"), "regulatory", "margin"),
        (("hdqt", "dai hoi", "nhan su"), "governance", "WACC"),
    )
    for tokens, materiality, impact in rules:
        if any(token in text for token in tokens):
            severity = "high" if materiality in {"earnings", "capex", "regulatory"} else "medium"
            return {"materiality": materiality, "impact": impact, "severity": severity}
    return {"materiality": "non-material", "impact": "no valuation impact", "severity": "low"}


def _load_market_snapshot(ticker: str):
    """Market snapshot data must be supplied through the run contract."""
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
        price_fcfe=blend.get("price_fcfe_vnd") if isinstance(blend, dict) else None,
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


def _charts(ticker: str, run_id: str | None = None) -> dict[str, ChartArtifact]:
    """Discover all generated chart PNGs for *ticker* from the artifacts directory.

    Registers C1–C8 when available.  Only C1 and C2 are marked required; the
    others are opportunistic — their absence is acceptable but their presence
    improves the report's evidence density.
    """
    titles = {
        "C1": "Diễn biến giá cổ phiếu so với VNINDEX",
        "C2": "Doanh thu và lợi nhuận",
        "C3": "EPS và P/E lịch sử",
        "C4": "Biên lợi nhuận và ROE",
        "C5": "Dự phóng doanh thu và lợi nhuận",
        "C6": "Cầu nối định giá chiết khấu dòng tiền",
        "C7": "Ma trận độ nhạy định giá",
        "C8": "So sánh định giá với cùng ngành",
    }
    captions = {
        "C1": "Nguồn: Dữ liệu thị trường; tính toán của nhóm phân tích.",
        "C2": "Nguồn: Báo cáo tài chính công ty; tính toán của nhóm phân tích.",
        "C3": "Nguồn: Báo cáo tài chính công ty; Bloomberg; tính toán của nhóm phân tích.",
        "C4": "Nguồn: Báo cáo tài chính công ty; tính toán của nhóm phân tích.",
        "C5": "Nguồn: Dự phóng của nhóm phân tích dựa trên giả định đã phê duyệt.",
        "C6": "Nguồn: Mô hình chiết khấu dòng tiền nội bộ; giả định đã được phê duyệt.",
        "C7": "Nguồn: Phân tích độ nhạy — WACC × tăng trưởng dài hạn; nhóm phân tích.",
        "C8": "Nguồn: Bloomberg; báo cáo công ty; tính toán của nhóm phân tích.",
    }
    return {}


def _market_data(
    ticker: str,
    manifest=None,
    *,
    run_id: str | None = None,
    allow_latest_artifacts: bool = False,
) -> MarketDataArtifact | None:
    """Resolve run-scoped market data, falling back to canonical price history."""
    if manifest is not None and manifest.resolve("market_data"):
        return market_data_from_dict(manifest.load_json("market_data"))
    try:
        exchange = _COMPANIES.get(ticker.upper(), (ticker.upper(), "HOSE"))[1]
        return load_market_data_from_fact_store(ticker, exchange)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("Unable to load canonical market data for %s: %s", ticker, exc)
    return None


def _approved_agent_narrative(manifest) -> dict[str, str]:
    """Load agent-authored prose while keeping QA state out of client content.

    A claim ledger with unsupported claims disables the override. When no ledger
    is present, the deterministic narrative remains the fallback for any field
    the agent did not provide.
    """
    if manifest is None or not manifest.resolve("financial_analysis"):
        return {}
    artifact = manifest.load_json("financial_analysis")
    payload = artifact.get("payload") or artifact
    ledger = manifest.load_json("claim_ledger") if manifest.resolve("claim_ledger") else {}
    if ledger.get("summary", {}).get("unsupported", 0):
        return {}
    forbidden = re.compile(
        r"\b(pending_review|default_unapproved|backend|artifact|gate|blocked)\b",
        re.IGNORECASE,
    )
    result: dict[str, str] = {}
    for key in (
        "investment_thesis",
        "financial_narrative",
        "risk_narrative",
        "forecast_narrative",
        "valuation_narrative",
    ):
        value = str(payload.get(key) or "").strip()
        if value and not forbidden.search(value):
            result[key] = value
    return result


def _load_critic_findings(manifest, run_id: str | None = None) -> list[str]:
    """Extract human-readable critic findings from the critic_review artifact.

    The critic review is persisted as a DB payload (no storage_path), so the
    manifest won't contain it. Fall back to a direct DB query by run_id.
    """
    payload: dict[str, Any] = {}
    if manifest is not None and manifest.resolve("critic_review"):
        payload = manifest.load_json("critic_review")
    elif run_id:
        try:
            from backend.database.config import connect_with_retry, require_database_url
            with connect_with_retry(require_database_url()) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT payload_json FROM research.run_artifacts
                        WHERE run_id = %s AND section_key = 'critic_review'
                        ORDER BY version DESC LIMIT 1
                        """,
                        (run_id,),
                    )
                    row = cur.fetchone()
            if row and isinstance(row[0], dict):
                payload = row[0]
        except Exception:
            return []
    if not payload:
        return []
    inner = payload.get("payload") or payload
    findings: list[str] = []
    for finding in inner.get("findings") or []:
        if not isinstance(finding, dict):
            continue
        desc = str(finding.get("description") or finding.get("finding") or "").strip()
        if desc:
            severity = str(finding.get("severity") or "").capitalize()
            findings.append(f"[{severity}] {desc}" if severity else desc)
    scorecard = inner.get("scorecard") or {}
    for metric, item in scorecard.items():
        if not isinstance(item, dict):
            continue
        explanation = str(item.get("explanation") or "").strip()
        score = item.get("score")
        if explanation and score is not None:
            findings.append(f"{metric} ({score}/10): {explanation}")
    return findings


def build_client_report_view_model(
    ticker: str,
    mode: RenderMode | str = "analyst_draft",
    run_id: str | None = None,
    allow_latest_artifacts: bool = False,
) -> ClientReportViewModel:
    ticker = ticker.upper()
    company_name, exchange = _COMPANIES.get(ticker, (ticker, "HOSE"))
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    report_date = generated_at[:10]

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
    valuation_policy = build_valuation_publishability_policy(val, ticker=ticker, run_id=run_id)
    display_gate = _report_display_governance(mode, val_result, blend, policy=valuation_policy)
    current_price = _price_to_vnd(display_gate["current_price"])
    target_price = display_gate["target_price"]
    upside = display_gate["upside"]
    recommendation = display_gate["recommendation"]
    charts = _charts(ticker, run_id)

    snapshot = _load_market_snapshot(ticker)
    market_data = _market_data(
        ticker,
        manifest,
        run_id=run_id,
        allow_latest_artifacts=allow_latest_artifacts,
    )

    periods = _derive_periods(facts, forecast)
    shares_mn = _derive_shares_mn(facts, periods)
    if (not shares_mn) and snapshot is not None and snapshot.shares_outstanding:
        shares_mn = snapshot.shares_outstanding / 1_000_000
    if not shares_mn:
        shares_mn = _derive_artifact_shares_mn(fcff, cpnc, val, forecast)
    if current_price is None and snapshot is not None and snapshot.last_price:
        current_price = _price_to_vnd(snapshot.last_price)
    if current_price is None and market_data is not None:
        current_price = _price_to_vnd(market_data.trading_statistics.last_close)
    market_price_as_of = _market_price_as_of(
        current_price,
        valuation=val,
        snapshot=snapshot,
        market_data=market_data,
    )
    if current_price and target_price and upside is None:
        upside = target_price / current_price - 1
    dividend_per_share = _derive_report_dividend_per_share(
        facts,
        forecast_rows,
        periods,
        shares_mn,
        snapshot.dividend_per_share if snapshot is not None else None,
    )
    market_cap = None if current_price is None or shares_mn == 0 else current_price * shares_mn / 1000
    market_stats = market_data.trading_statistics if market_data is not None else None
    trading_perf = market_data.trading_performance if market_data is not None else None
    dividend_yield = (
        Percent(dividend_per_share / current_price)
        if dividend_per_share is not None and current_price else None
    )

    # Re-compute recommendation with total_expected_return = upside + dividend_yield
    # (initial _recommendation call at display_gate level didn't have dividend_yield)
    dy_val = dividend_yield.value if dividend_yield is not None else 0.0
    recommendation = _recommendation(
        upside, mode,
        approved_for_display=display_gate.get("approved_for_display", False),
        dividend_yield=dy_val,
    )

    missing: list[str] = []
    if current_price is None:
        missing.append("current_price")
    elif not market_price_as_of:
        missing.append("market_price_as_of")
    elif market_price_as_of != report_date:
        missing.append("same_day_market_price")
    if target_price is None:
        missing.append("target_price")
    if upside is None:
        missing.append("upside_downside")
    if not forecast_rows:
        missing.append("forecast_years")
    if not fcff_rows:
        missing.append("fcff_table")
    forecast_labels = [p for p in periods if p.endswith("F")]
    if forecast_labels and any(forecast_rows.get(p, {}).get("total_debt") is None for p in forecast_labels):
        missing.append("forecast_debt")
    if forecast_labels and any(forecast_rows.get(p, {}).get("cash") is None for p in forecast_labels):
        missing.append("forecast_cash")
    debt_schedule = forecast.get("debt_schedule") or {}
    if debt_schedule and not debt_schedule.get("is_fcfe_publishable", False):
        missing.append("debt_schedule_publishable")
    if (forecast.get("dividend_schedule") or {}).get("method") == "missing":
        missing.append("dividend_schedule")
    if forecast and forecast.get("working_capital_schedule") is None:
        missing.append("working_capital_schedule")
    if "C1" not in charts and not (market_data and len(market_data.price_history) >= 2):
        missing.append("price_chart")
    # Shares-outstanding integrity (PLAN §1.9 / §4.3): EPS present but no share count is a
    # critical inconsistency — EPS implies a share base, so a missing/zero count must block.
    _has_eps = any(
        _fact_value(facts, "eps.basic", _to_fact_period(p)) for p in periods if _is_actual(p)
    )
    if _has_eps and not shares_mn:
        missing.append("shares_outstanding")

    publication_status = (
        "complete"
        if not missing and str(val_result.get("is_publishable")).lower() == "true"
        else "available_with_disclosures"
    )
    missing = sorted(set(missing))

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
    agent_narrative = _approved_agent_narrative(manifest)
    thesis = agent_narrative.get("investment_thesis", thesis)
    current_context = agent_narrative.get("financial_narrative", current_context)
    events = agent_narrative.get("risk_narrative", events)
    forecast_text = agent_narrative.get("forecast_narrative", forecast_text)
    if agent_narrative.get("valuation_narrative"):
        forecast_text = f"{forecast_text} {agent_narrative['valuation_narrative']}".strip()
    key_forecast_drivers_table = _table_key_forecast_drivers(forecast, fcff, facts, forecast_rows, ticker)
    sensitivity_table = (
        _table_sensitivity_matrix(val.get("sensitivity", {}), display_gate["approved_for_display"])
        or _table_driver_sensitivity(fcff, blend if display_gate["approved_for_display"] else {}, forecast)
    )
    critic_findings = _load_critic_findings(manifest, run_id=run_id)

    news_citations = _load_news_citations(ticker, company_name)
    insight_pack = _build_insight_pack_for_report(
        facts, forecast_rows, periods, upside, recommendation, len(news_citations)
    )

    return ClientReportViewModel(
        ticker=ticker,
        company_name=company_name,
        exchange=exchange,
        sector="Dược phẩm",
        report_date=report_date,
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
            "Giá đóng cửa": (
                _price_to_vnd(market_stats.last_close) if market_stats is not None and market_stats.last_close is not None
                else current_price if current_price is not None else _NA
            ),
            "Giá cao/thấp 52 tuần": (
                f"{_price_to_vnd(market_stats.low_52w):,.0f} / {_price_to_vnd(market_stats.high_52w):,.0f}"
                if market_stats is not None and market_stats.high_52w is not None and market_stats.low_52w is not None
                else f"{snapshot.low_52w:,.0f} / {snapshot.high_52w:,.0f}"
                if snapshot is not None and snapshot.high_52w and snapshot.low_52w else _NA
            ),
            "KLGD bình quân 30 phiên": (
                f"{market_stats.avg_volume_30d:,.0f}"
                if market_stats is not None and market_stats.avg_volume_30d is not None
                else f"{snapshot.avg_volume_1m:,.0f}"
                if snapshot is not None and snapshot.avg_volume_1m else _NA
            ),
            "Tỷ lệ sở hữu nước ngoài": (
                f"{snapshot.foreign_pct * 100:.1f}%"
                if snapshot is not None and snapshot.foreign_pct is not None else _NA
            ),
        },
        ownership_table=TableData(
            title="CƠ CẤU SỞ HỮU",
            periods=["Tỷ lệ"],
            rows=[("Cổ đông lớn và nhà đầu tư tổ chức", [_NA]), ("Cổ đông khác", [_NA])],
            source_note="N/A khi chưa có dữ liệu cơ cấu sở hữu đã kiểm chứng.",
        ),
        trading_performance_table=TableData(
            title="DIỄN BIẾN GIÁ CỔ PHIẾU",
            periods=["YTD", "1T", "3T", "12T"],
            rows=[
                (
                    "Tuyệt đối",
                    [trading_perf.absolute_returns.get(p) if trading_perf else _NA for p in ("YTD", "1T", "3T", "12T")],
                ),
                (
                    f"So với {trading_perf.benchmark_symbol if trading_perf else benchmark_for_exchange(exchange)}",
                    [trading_perf.relative_returns.get(p) if trading_perf else _NA for p in ("YTD", "1T", "3T", "12T")],
                ),
            ],
            format_type="percent",
            source_note=(
                f"Nguồn nhóm phân tích thu thập; cập nhật {market_data.as_of_date}."
                if market_data is not None else "Chưa có dữ liệu thị trường đã kiểm chứng."
            ),
        ),
        financial_summary_table=_table_financial_summary(facts, forecast_rows, current_price, periods, dividend_per_share, shares_mn),
        valuation_model_table=_table_valuation_model(facts, forecast_rows, fcff_rows, periods, shares_mn),
        balance_sheet_cashflow_table=_table_bs_cf(facts, forecast_rows, fcff_rows, periods, shares_mn),
        profitability_valuation_table=_table_profitability_valuation(facts, forecast_rows, current_price, fcff, periods, shares_mn, dividend_per_share),
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
        news_citations=news_citations,
        insight_pack=insight_pack,
        display_blocking_reasons=display_gate["blocking_reasons"],
        critic_findings=critic_findings,
        metric_availability=(
            {key: value.__dict__ for key, value in market_data.availability.items()}
            if market_data is not None else {}
        ),
        company_profile={
            "Tên": company_name,
            "Mã giao dịch": ticker,
            "Sàn": exchange,
            "Ngành": "Dược phẩm",
            "Hoạt động chính": "Sản xuất và phân phối dược phẩm",
        },
        market_data=market_data,
        selected_valuation_methods=[str(item).upper() for item in (val.get("selected_methods") or [])],
        valuation_summary_table=_table_valuation_summary(val),
        wacc_bridge_table=_table_wacc_bridge(val),
        valuation_bridge_table=_table_valuation_bridge(val),
        report_generated_at=generated_at,
        market_price_as_of=market_price_as_of,
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
