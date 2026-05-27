"""Deterministic 5-year income statement forecasting engine.

Builds a forward projection using historical drivers derived from the FactTable.
All arithmetic is deterministic Python — no LLM involvement.

Conventions (matching the rest of the analytics layer):
  - Values are in tỷ VND (bn VND) unless stated otherwise.
  - sga.total          → stored NEGATIVE (expense)
  - interest_expense.total → stored NEGATIVE (cost)
  - profit_before_tax.total → stored POSITIVE
  - gross_profit.total      → stored POSITIVE

The PBT gap fix:
  EBIT_model = gross_profit + sga          (sga negative → subtracts correctly)
  naive_pbt  = EBIT_model + interest_expense
  Historical data consistently shows actual PBT < naive_pbt.
  The residual  other_items = PBT − (EBIT_model + interest_expense)
  captures provisions, net finance income/loss, subsidiary results, etc.
  The median historical ratio (other_items / revenue) is applied to each
  forecast year so the model does not spuriously inflate forward PBT.
"""
from __future__ import annotations

import statistics
import warnings as _warnings_module
from dataclasses import dataclass, field
from typing import Any

from backend.facts.normalizer import FactTable


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ForecastYear:
    year: int
    period_key: str          # e.g. "2026F"
    revenue: float | None
    gross_profit: float | None
    gross_margin: float | None
    sga: float | None        # negative value (expense)
    ebit: float | None
    interest_expense: float | None  # negative value (cost)
    other_items: float | None       # residual non-SGA gap (typically negative)
    profit_before_tax: float | None
    tax_expense: float | None       # negative value
    net_income: float | None
    net_margin: float | None


@dataclass
class ForecastArtifact:
    ticker: str
    base_period: str                 # last historical period used
    forecast_years: list[ForecastYear] = field(default_factory=list)
    drivers: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "base_period": self.base_period,
            "drivers": self.drivers,
            "warnings": self.warnings,
            "forecast": [
                {
                    "year": fy.year,
                    "period_key": fy.period_key,
                    "revenue": round(fy.revenue, 1) if fy.revenue is not None else None,
                    "gross_profit": round(fy.gross_profit, 1) if fy.gross_profit is not None else None,
                    "gross_margin": round(fy.gross_margin, 4) if fy.gross_margin is not None else None,
                    "sga": round(fy.sga, 1) if fy.sga is not None else None,
                    "ebit": round(fy.ebit, 1) if fy.ebit is not None else None,
                    "interest_expense": round(fy.interest_expense, 1) if fy.interest_expense is not None else None,
                    "other_items": round(fy.other_items, 1) if fy.other_items is not None else None,
                    "profit_before_tax": round(fy.profit_before_tax, 1) if fy.profit_before_tax is not None else None,
                    "tax_expense": round(fy.tax_expense, 1) if fy.tax_expense is not None else None,
                    "net_income": round(fy.net_income, 1) if fy.net_income is not None else None,
                    "net_margin": round(fy.net_margin, 4) if fy.net_margin is not None else None,
                }
                for fy in self.forecast_years
            ],
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get(table: FactTable, key: str, period: str) -> float | None:
    return table.get(key, {}).get(period)


def _fy_periods(fact_table: FactTable) -> list[str]:
    """Return sorted FY period keys present in the fact table."""
    periods = {p for periods in fact_table.values() for p in periods if p.endswith("FY")}
    return sorted(periods)


# ---------------------------------------------------------------------------
# Core forecasting function
# ---------------------------------------------------------------------------

def run_forecast(
    ticker: str,
    fact_table: FactTable,
    n_years: int = 5,
    revenue_growth_override: float | None = None,
) -> ForecastArtifact:
    """Build a deterministic n-year income statement forecast.

    Parameters
    ----------
    ticker:
        Stock ticker (e.g. "DHG").
    fact_table:
        Normalised FactTable from build_fact_table / compute_derived.
    n_years:
        Number of forward years to project (default 5).
    revenue_growth_override:
        If provided, overrides the historical median revenue growth rate.

    Returns
    -------
    ForecastArtifact with per-year projections and driver metadata.
    """
    artifact_warnings: list[str] = []

    fy_periods = _fy_periods(fact_table)
    if not fy_periods:
        artifact_warnings.append("No FY periods found in fact table — forecast is empty.")
        return ForecastArtifact(
            ticker=ticker,
            base_period="",
            warnings=artifact_warnings,
        )

    base_period = fy_periods[-1]
    base_year = int(base_period.replace("FY", ""))

    # ------------------------------------------------------------------
    # Driver 1: Revenue growth (historical median YoY)
    # ------------------------------------------------------------------
    rev_growth_rates: list[float] = []
    for i in range(1, len(fy_periods)):
        prev_p = fy_periods[i - 1]
        curr_p = fy_periods[i]
        rev_prev = _get(fact_table, "revenue.net", prev_p)
        rev_curr = _get(fact_table, "revenue.net", curr_p)
        if rev_prev and rev_curr and rev_prev > 0:
            rev_growth_rates.append((rev_curr - rev_prev) / rev_prev)

    if revenue_growth_override is not None:
        rev_growth = revenue_growth_override
        artifact_warnings.append(
            f"Revenue growth overridden to {rev_growth:.1%} (historical median ignored)."
        )
    elif rev_growth_rates:
        rev_growth = statistics.median(rev_growth_rates)
    else:
        rev_growth = 0.04  # default 4% if no history
        artifact_warnings.append("No revenue history to compute growth — defaulting to 4%.")

    # ------------------------------------------------------------------
    # Driver 2: Gross margin (historical median)
    # ------------------------------------------------------------------
    gm_ratios: list[float] = []
    for p in fy_periods:
        gp = _get(fact_table, "gross_profit.total", p)
        rev = _get(fact_table, "revenue.net", p)
        if gp is not None and rev and rev > 0:
            gm_ratios.append(gp / rev)

    gross_margin_fwd = statistics.median(gm_ratios) if gm_ratios else 0.35

    # ------------------------------------------------------------------
    # Driver 3: SGA as % of revenue (historical median; sga is negative)
    # ------------------------------------------------------------------
    sga_ratios: list[float] = []
    for p in fy_periods:
        sga = _get(fact_table, "sga.total", p)
        rev = _get(fact_table, "revenue.net", p)
        if sga is not None and rev and rev > 0:
            sga_ratios.append(sga / rev)  # negative ratio

    sga_to_rev = statistics.median(sga_ratios) if sga_ratios else -0.20

    # ------------------------------------------------------------------
    # Driver 4: Interest expense as % of revenue (historical median)
    # ------------------------------------------------------------------
    interest_ratios: list[float] = []
    for p in fy_periods:
        ie = _get(fact_table, "interest_expense.total", p)
        rev = _get(fact_table, "revenue.net", p)
        if ie is not None and rev and rev > 0:
            interest_ratios.append(ie / rev)  # negative ratio

    interest_to_rev = statistics.median(interest_ratios) if interest_ratios else 0.0

    # ------------------------------------------------------------------
    # Driver 5: Other items (PBT gap) as % of revenue (historical median)
    # ------------------------------------------------------------------
    # For each historical period: other_items = PBT − (EBIT_model + interest_expense)
    # where EBIT_model = gross_profit + sga  (sga negative)
    # and interest_expense is stored negative.
    # A negative other_items_to_rev reduces forecast PBT (the correct direction for DHG).
    other_items_ratios: list[float] = []
    for p in fy_periods:
        gp_h = _get(fact_table, "gross_profit.total", p)
        sga_h = _get(fact_table, "sga.total", p)
        ie_h = _get(fact_table, "interest_expense.total", p)
        pbt_h = _get(fact_table, "profit_before_tax.total", p)
        rev_h = _get(fact_table, "revenue.net", p)
        if all(v is not None for v in [gp_h, sga_h, ie_h, pbt_h, rev_h]) and rev_h > 0:
            ebit_model = gp_h + sga_h          # sga_h negative → correct subtraction
            other_items = pbt_h - (ebit_model + ie_h)   # ie_h negative → correct
            other_items_ratios.append(other_items / rev_h)

    other_items_to_rev = statistics.median(other_items_ratios) if other_items_ratios else 0.0
    if other_items_ratios and other_items_to_rev != 0.0:
        artifact_warnings.append(
            f"Non-operating items (provisions, finance income, etc.) = "
            f"{other_items_to_rev:.1%} of revenue (historical median). "
            f"Applied to forecast. Individual years ranged from "
            f"{min(other_items_ratios):.1%} to {max(other_items_ratios):.1%}."
        )

    # ------------------------------------------------------------------
    # Driver 6: Effective tax rate (historical median)
    # ------------------------------------------------------------------
    tax_rates: list[float] = []
    for p in fy_periods:
        pbt = _get(fact_table, "profit_before_tax.total", p)
        tax = _get(fact_table, "tax_expense.total", p)
        if pbt and pbt > 0 and tax is not None:
            tax_rates.append(abs(tax) / pbt)

    eff_tax_rate = statistics.median(tax_rates) if tax_rates else 0.20

    # ------------------------------------------------------------------
    # Assemble drivers dict
    # ------------------------------------------------------------------
    drivers: dict[str, Any] = {
        "revenue_growth": {
            "method": "historical_median" if revenue_growth_override is None else "override",
            "value": round(rev_growth, 4),
        },
        "gross_margin": {
            "method": "historical_median",
            "value": round(gross_margin_fwd, 4),
        },
        "sga_to_revenue": {
            "method": "historical_median",
            "value": round(sga_to_rev, 4),
        },
        "interest_to_revenue": {
            "method": "historical_median",
            "value": round(interest_to_rev, 4),
        },
        "other_items_to_revenue": {
            "method": "historical_median",
            "value": round(other_items_to_rev, 4),
        },
        "effective_tax_rate": {
            "method": "historical_median",
            "value": round(eff_tax_rate, 4),
        },
    }

    # ------------------------------------------------------------------
    # Per-year projection loop
    # ------------------------------------------------------------------
    base_revenue = _get(fact_table, "revenue.net", base_period)
    if base_revenue is None:
        artifact_warnings.append(
            f"No revenue found for base period {base_period} — cannot project forward."
        )
        return ForecastArtifact(
            ticker=ticker,
            base_period=base_period,
            drivers=drivers,
            warnings=artifact_warnings,
        )

    forecast_years_list: list[ForecastYear] = []
    prev_revenue = base_revenue

    forecast_years = [base_year + i for i in range(1, n_years + 1)]

    for year in forecast_years:
        revenue = prev_revenue * (1 + rev_growth)
        gross_profit = revenue * gross_margin_fwd
        sga = revenue * sga_to_rev                   # negative
        ebit = gross_profit + sga
        interest_expense = revenue * interest_to_rev  # negative
        other_items = revenue * other_items_to_rev    # typically negative
        pbt = ebit + interest_expense + other_items
        tax_expense = -abs(pbt) * eff_tax_rate if pbt is not None else None
        net_income = pbt + tax_expense if (pbt is not None and tax_expense is not None) else None
        net_margin = (net_income / revenue) if (net_income is not None and revenue > 0) else None

        forecast_years_list.append(
            ForecastYear(
                year=year,
                period_key=f"{year}F",
                revenue=revenue,
                gross_profit=gross_profit,
                gross_margin=gross_margin_fwd,
                sga=sga,
                ebit=ebit,
                interest_expense=interest_expense,
                other_items=other_items,
                profit_before_tax=pbt,
                tax_expense=tax_expense,
                net_income=net_income,
                net_margin=net_margin,
            )
        )
        prev_revenue = revenue

    return ForecastArtifact(
        ticker=ticker,
        base_period=base_period,
        forecast_years=forecast_years_list,
        drivers=drivers,
        warnings=artifact_warnings,
    )
