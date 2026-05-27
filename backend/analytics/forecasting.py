"""Deterministic financial forecast engine.

Generates 5-year income statement and balance sheet projections
from historical canonical facts using driver-based methods.

Methods:
  - revenue_growth: historical CAGR (capped ±25%), overridable
  - cost items: ratio-to-revenue (historical median margin)
  - balance sheet: simplified equity waterfall

No LLM involvement — all arithmetic is explicit Python.

Output artifact: ForecastArtifact (to_dict() → JSON-serializable)
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

FactTable = dict[str, dict[str, float]]

_FORECAST_YEARS = [2026, 2027, 2028, 2029, 2030]
_MAX_REVENUE_GROWTH = 0.25
_MIN_REVENUE_GROWTH = -0.10


def _get(table: FactTable, key: str, period: str) -> float | None:
    return table.get(key, {}).get(period)


def _cagr(start: float, end: float, years: int) -> float | None:
    if years <= 0 or start is None or end is None or start <= 0:
        return None
    return (end / start) ** (1.0 / years) - 1.0


def _median_ratio(
    numerator_key: str,
    denominator_key: str,
    table: FactTable,
    periods: list[str],
) -> float | None:
    """Compute median of numerator/denominator across available FY periods."""
    ratios = []
    for p in periods:
        num = _get(table, numerator_key, p)
        den = _get(table, denominator_key, p)
        if num is not None and den is not None and den != 0:
            ratios.append(num / den)
    if not ratios:
        return None
    return statistics.median(ratios)


@dataclass
class ForecastAssumptions:
    revenue_growth_override: float | None = None  # None → use historical CAGR
    gross_margin_override: float | None = None     # None → use historical median
    net_margin_override: float | None = None       # None → derive from other lines
    sga_to_revenue_override: float | None = None
    tax_rate_override: float | None = None
    capex_to_revenue_override: float | None = None
    depreciation_to_revenue_override: float | None = None
    assumption_status: str = "default_unapproved"  # or "analyst_approved"


@dataclass
class ForecastYear:
    year: int
    label: str          # e.g. "2026F"
    revenue: float | None
    cogs: float | None
    gross_profit: float | None
    gross_margin: float | None
    sga: float | None
    ebit: float | None
    ebit_margin: float | None
    depreciation: float | None
    ebitda: float | None
    interest_expense: float | None
    profit_before_tax: float | None
    tax_expense: float | None
    net_income: float | None
    net_margin: float | None
    capex: float | None
    # Balance sheet highlights
    total_assets: float | None
    equity: float | None
    total_debt: float | None
    other_liabilities: float | None  # non-debt liabilities carried forward
    # Per-share
    eps: float | None
    bvps: float | None


@dataclass
class ForecastArtifact:
    ticker: str
    historical_periods: list[str]
    forecast_periods: list[str]
    assumptions: ForecastAssumptions
    revenue_cagr: float | None
    drivers: dict[str, Any]
    forecast_years: list[ForecastYear]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "historical_periods": self.historical_periods,
            "forecast_periods": self.forecast_periods,
            "revenue_cagr_historical": round(self.revenue_cagr, 4) if self.revenue_cagr else None,
            "drivers": self.drivers,
            "assumption_status": self.assumptions.assumption_status,
            "forecast_years": [
                {
                    "year": fy.year,
                    "label": fy.label,
                    "revenue": round(fy.revenue, 1) if fy.revenue is not None else None,
                    "cogs": round(fy.cogs, 1) if fy.cogs is not None else None,
                    "gross_profit": round(fy.gross_profit, 1) if fy.gross_profit is not None else None,
                    "gross_margin": round(fy.gross_margin, 4) if fy.gross_margin is not None else None,
                    "sga": round(fy.sga, 1) if fy.sga is not None else None,
                    "ebit": round(fy.ebit, 1) if fy.ebit is not None else None,
                    "ebit_margin": round(fy.ebit_margin, 4) if fy.ebit_margin is not None else None,
                    "depreciation": round(fy.depreciation, 1) if fy.depreciation is not None else None,
                    "ebitda": round(fy.ebitda, 1) if fy.ebitda is not None else None,
                    "interest_expense": round(fy.interest_expense, 1) if fy.interest_expense is not None else None,
                    "profit_before_tax": round(fy.profit_before_tax, 1) if fy.profit_before_tax is not None else None,
                    "tax_expense": round(fy.tax_expense, 1) if fy.tax_expense is not None else None,
                    "net_income": round(fy.net_income, 1) if fy.net_income is not None else None,
                    "net_margin": round(fy.net_margin, 4) if fy.net_margin is not None else None,
                    "capex": round(fy.capex, 1) if fy.capex is not None else None,
                    "total_assets": round(fy.total_assets, 1) if fy.total_assets is not None else None,
                    "equity": round(fy.equity, 1) if fy.equity is not None else None,
                    "total_debt": round(fy.total_debt, 1) if fy.total_debt is not None else None,
                    "other_liabilities": round(fy.other_liabilities, 1) if fy.other_liabilities is not None else None,
                    "eps": round(fy.eps, 0) if fy.eps is not None else None,
                    "bvps": round(fy.bvps, 0) if fy.bvps is not None else None,
                }
                for fy in self.forecast_years
            ],
            "warnings": self.warnings,
        }


def run_forecast(
    ticker: str,
    fact_table: FactTable,
    forecast_years: list[int] | None = None,
    assumptions: ForecastAssumptions | None = None,
    shares_mn: float | None = None,
) -> ForecastArtifact:
    """Run deterministic 5-year income statement and balance sheet forecast.

    Uses historical CAGR for revenue growth, historical median margins for
    cost lines. All assumptions are explicit and stored in the artifact.
    """
    if assumptions is None:
        assumptions = ForecastAssumptions()
    if forecast_years is None:
        forecast_years = _FORECAST_YEARS

    warnings: list[str] = []

    fy_periods = sorted(
        p for p in {p for vals in fact_table.values() for p in vals} if p.endswith("FY")
    )
    if not fy_periods:
        return ForecastArtifact(
            ticker=ticker, historical_periods=[], forecast_periods=[],
            assumptions=assumptions, revenue_cagr=None, drivers={},
            forecast_years=[], warnings=["No FY periods available for forecast"],
        )

    # ── Historical revenue CAGR ────────────────────────────────────────────
    rev_vals = [_get(fact_table, "revenue.net", p) for p in fy_periods]
    rev_vals = [v for v in rev_vals if v is not None]

    if assumptions.revenue_growth_override is not None:
        rev_growth = assumptions.revenue_growth_override
        revenue_cagr = None
    elif len(rev_vals) >= 2:
        revenue_cagr = _cagr(rev_vals[0], rev_vals[-1], len(rev_vals) - 1)
        # Cap for projection
        rev_growth = max(_MIN_REVENUE_GROWTH, min(_MAX_REVENUE_GROWTH, revenue_cagr or 0.05))
        if revenue_cagr is not None and revenue_cagr != rev_growth:
            warnings.append(
                f"Revenue CAGR {revenue_cagr:.1%} capped to {rev_growth:.1%} for forecast"
            )
    else:
        rev_growth = 0.05
        revenue_cagr = None
        warnings.append("Insufficient revenue history — assuming 5% growth")

    # ── Historical margin drivers ──────────────────────────────────────────
    gross_margin = (
        assumptions.gross_margin_override
        or _median_ratio("gross_profit.total", "revenue.net", fact_table, fy_periods)
    )
    if gross_margin is None:
        gross_margin = 0.40
        warnings.append("No gross margin history — using default 40%")

    # SGA as % of revenue (sga is stored negative)
    sga_ratios = []
    for p in fy_periods:
        sga = _get(fact_table, "sga.total", p)
        rev = _get(fact_table, "revenue.net", p)
        if sga is not None and rev and rev > 0:
            sga_ratios.append(abs(sga) / rev)
    sga_to_rev = (
        assumptions.sga_to_revenue_override
        or (statistics.median(sga_ratios) if sga_ratios else 0.20)
    )

    # Depreciation as % of revenue
    dep_to_rev = (
        assumptions.depreciation_to_revenue_override
        or _median_ratio("depreciation.total", "revenue.net", fact_table, fy_periods)
        or 0.04
    )

    # CAPEX as % of revenue (capex stored negative → use abs)
    capex_ratios = []
    for p in fy_periods:
        capex = _get(fact_table, "capex.total", p)
        rev = _get(fact_table, "revenue.net", p)
        if capex is not None and rev and rev > 0:
            capex_ratios.append(abs(capex) / rev)
    capex_to_rev = (
        assumptions.capex_to_revenue_override
        or (statistics.median(capex_ratios) if capex_ratios else 0.03)
    )

    # Effective tax rate
    tax_rates = []
    for p in fy_periods:
        pbt = _get(fact_table, "profit_before_tax.total", p)
        ni = _get(fact_table, "net_income.parent", p)
        if pbt and pbt > 0 and ni is not None:
            tax_rates.append(max(0, (pbt - ni) / pbt))
    tax_rate = (
        assumptions.tax_rate_override
        or (statistics.median(tax_rates) if tax_rates else 0.20)
    )

    # Interest expense as % of revenue
    interest_ratios = []
    for p in fy_periods:
        ie = _get(fact_table, "interest_expense.total", p)
        rev = _get(fact_table, "revenue.net", p)
        if ie is not None and rev and rev > 0:
            interest_ratios.append(abs(ie) / rev)
    interest_to_rev = statistics.median(interest_ratios) if interest_ratios else 0.01

    # ── Starting balance sheet values ────────────────────────────────────
    latest_fy = fy_periods[-1]
    start_assets = _get(fact_table, "total_assets.ending", latest_fy) or 0
    start_equity = _get(fact_table, "equity.parent", latest_fy) or 0
    start_debt = _get(fact_table, "total_debt.ending", latest_fy) or 0
    # Non-debt liabilities: carry forward as constant (trade payables, accruals, etc.)
    # Satisfies identity: total_assets = equity + total_debt + other_liabilities
    other_liabilities = max(0.0, start_assets - start_equity - start_debt)

    # Shares outstanding
    if shares_mn is None:
        ni_latest = _get(fact_table, "net_income.parent", latest_fy)
        eps_latest = _get(fact_table, "eps.basic", latest_fy)
        if ni_latest and eps_latest and eps_latest > 0:
            shares_mn = (ni_latest * 1_000) / eps_latest
        else:
            shares_mn = None

    # ── Store drivers ──────────────────────────────────────────────────────
    drivers = {
        "revenue_growth": {y: round(rev_growth, 4) for y in forecast_years},
        "gross_margin": {"method": "historical_median", "value": round(gross_margin, 4)},
        "sga_to_revenue": {"method": "historical_median", "value": round(sga_to_rev, 4)},
        "depreciation_to_revenue": {"method": "historical_median", "value": round(dep_to_rev, 4)},
        "capex_to_revenue": {"method": "historical_median", "value": round(capex_to_rev, 4)},
        "effective_tax_rate": {"method": "historical_median", "value": round(tax_rate, 4)},
        "interest_to_revenue": {"method": "historical_median", "value": round(interest_to_rev, 4)},
    }

    # ── Project each year ──────────────────────────────────────────────────
    latest_rev = _get(fact_table, "revenue.net", latest_fy) or 0
    current_rev = latest_rev
    current_equity = start_equity
    current_debt = start_debt

    forecast_year_objects: list[ForecastYear] = []
    forecast_period_labels: list[str] = []

    for year in forecast_years:
        label = f"{year}F"
        forecast_period_labels.append(label)

        revenue = current_rev * (1 + rev_growth)
        cogs = -revenue * (1 - gross_margin)  # negative convention
        gross_profit = revenue + cogs
        sga = -revenue * sga_to_rev       # negative
        depreciation = revenue * dep_to_rev
        ebit = gross_profit + sga          # sga is negative, so this subtracts
        ebitda = ebit + depreciation
        ebit_margin = ebit / revenue if revenue else None

        interest_expense = -revenue * interest_to_rev  # negative
        pbt = ebit + interest_expense
        tax_expense = -max(0, pbt) * tax_rate
        net_income = pbt + tax_expense
        net_margin = net_income / revenue if revenue else None

        capex = -revenue * capex_to_rev   # negative

        # Equity grows by net income (no dividends in MVP)
        current_equity = current_equity + net_income
        # Identity: total_assets = equity + total_debt + other_liabilities
        total_assets = current_equity + current_debt + other_liabilities

        eps = (net_income * 1_000) / shares_mn if shares_mn else None
        bvps = (current_equity / shares_mn) * 1_000 if shares_mn else None

        forecast_year_objects.append(ForecastYear(
            year=year,
            label=label,
            revenue=revenue,
            cogs=cogs,
            gross_profit=gross_profit,
            gross_margin=gross_margin,
            sga=sga,
            ebit=ebit,
            ebit_margin=ebit_margin,
            depreciation=depreciation,
            ebitda=ebitda,
            interest_expense=interest_expense,
            profit_before_tax=pbt,
            tax_expense=tax_expense,
            net_income=net_income,
            net_margin=net_margin,
            capex=capex,
            total_assets=total_assets,
            equity=current_equity,
            total_debt=current_debt,
            other_liabilities=other_liabilities,
            eps=eps,
            bvps=bvps,
        ))

        current_rev = revenue

    return ForecastArtifact(
        ticker=ticker,
        historical_periods=fy_periods,
        forecast_periods=forecast_period_labels,
        assumptions=assumptions,
        revenue_cagr=revenue_cagr,
        drivers=drivers,
        forecast_years=forecast_year_objects,
        warnings=warnings,
    )
