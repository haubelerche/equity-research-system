"""FCFE (Free Cash Flow to Equity) valuation engine.

Formula (from income statement):
    FCFE = Net Income + D&A - CAPEX_positive - ΔNWC + Net Borrowing

Formula (from CFO, when CAPEX_CFS is negative in source data):
    FCFE = CFO + CAPEX_CFS + Net Borrowing

Discount rate: Re (cost of equity) — NEVER WACC.
Output: Equity Value directly — no EV → Equity bridge (no net debt subtraction).

CAPEX sign convention: stored negative in ForecastYear; converted to positive
for arithmetic via abs(), consistent with fcff.py.

Net Borrowing in forecast years: assumed 0 (stable leverage). Override per-year
by passing net_borrowing_schedule.

All arithmetic is deterministic Python — no LLM involvement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.analytics.shares import explicit_shares_mn
from backend.analytics.forecasting import ForecastArtifact, ForecastYear  # noqa: F401

from backend.facts.normalizer import FactTable


@dataclass
class CostOfEquityAssumptions:
    """Extended CAPM: Re = Rf + Beta × ERP + Size Premium + Specific Risk Premium.

    To directly override Re (e.g., for sensitivity grids), set re_override.
    All other fields are ignored when re_override is set.
    """
    risk_free_rate: float = 0.04           # VN 10Y government bond yield
    beta: float = 0.85                      # VN pharma sector estimate
    equity_risk_premium: float = 0.08      # Vietnam ERP = Rm - Rf
    size_premium: float = 0.02             # small-mid cap VN pharma premium
    specific_risk_premium: float = 0.01   # company-specific risk
    re_override: float | None = None       # if set, skip component formula
    assumption_status: str = "default_unapproved"

    @property
    def cost_of_equity(self) -> float:
        if self.re_override is not None:
            return self.re_override
        return (
            self.risk_free_rate
            + self.beta * self.equity_risk_premium
            + self.size_premium
            + self.specific_risk_premium
        )


@dataclass
class FCFEYear:
    year: int
    label: str
    net_income: float | None
    depreciation: float | None
    capex: float | None          # stored as negative per display convention
    delta_nwc: float | None      # positive = working capital absorbed (reduces FCFE)
    net_borrowing: float | None  # positive = net new debt drawn (increases FCFE)
    fcfe: float | None
    discount_factor: float | None
    pv_fcfe: float | None


@dataclass
class FCFEResult:
    ticker: str
    cost_of_equity_assumptions: CostOfEquityAssumptions
    cost_of_equity: float
    terminal_growth: float
    forecast_years: list[FCFEYear]
    sum_pv_fcfe: float
    terminal_value: float
    pv_terminal_value: float
    equity_value: float          # FCFE gives Equity Value directly — no net debt bridge
    shares_mn: float | None
    target_price_vnd: float | None
    current_price_vnd: float | None
    upside_pct: float | None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def _r(v: float | None, d: int = 1) -> float | None:
            return round(v, d) if v is not None else None

        return {
            "ticker": self.ticker,
            "cost_of_equity": round(self.cost_of_equity, 4),
            "terminal_growth": round(self.terminal_growth, 4),
            "assumption_status": self.cost_of_equity_assumptions.assumption_status,
            "cost_of_equity_breakdown": {
                "risk_free_rate": self.cost_of_equity_assumptions.risk_free_rate,
                "beta": self.cost_of_equity_assumptions.beta,
                "equity_risk_premium": self.cost_of_equity_assumptions.equity_risk_premium,
                "size_premium": self.cost_of_equity_assumptions.size_premium,
                "specific_risk_premium": self.cost_of_equity_assumptions.specific_risk_premium,
                "re_override": self.cost_of_equity_assumptions.re_override,
            },
            "capex_convention": "positive_outflow",
            "capex_formula_note": "CAPEX displayed as positive outflow; formula: FCFE = NI + D&A - CAPEX - ΔNWC + Net Borrowing",
            "fcfe_table": [
                {
                    "year": fy.year,
                    "label": fy.label,
                    "net_income": _r(fy.net_income),
                    "depreciation": _r(fy.depreciation),
                    "capex": _r(fy.capex),
                    "delta_nwc": _r(fy.delta_nwc),
                    "net_borrowing": _r(fy.net_borrowing),
                    "fcfe": _r(fy.fcfe),
                    "discount_factor": round(fy.discount_factor, 4) if fy.discount_factor else None,
                    "pv_fcfe": _r(fy.pv_fcfe),
                }
                for fy in self.forecast_years
            ],
            "sum_pv_fcfe": _r(self.sum_pv_fcfe),
            "terminal_value": _r(self.terminal_value),
            "pv_terminal_value": _r(self.pv_terminal_value),
            "equity_value": _r(self.equity_value),
            "shares_mn": _r(self.shares_mn),
            "target_price_vnd": round(self.target_price_vnd, 0) if self.target_price_vnd is not None else None,
            "current_price_vnd": _r(self.current_price_vnd, 0),
            "upside_pct": round(self.upside_pct, 4) if self.upside_pct is not None else None,
            "warnings": self.warnings,
        }


def compute_fcfe(
    ticker: str,
    forecast: ForecastArtifact,
    fact_table: FactTable,
    current_price_vnd: float | None = None,
    terminal_growth: float = 0.03,
    cost_of_equity_assumptions: CostOfEquityAssumptions | None = None,
    shares_mn: float | None = None,
    net_borrowing_schedule: dict[str, float] | None = None,
) -> FCFEResult:
    """Compute FCFE valuation from forecast income statement.

    FCFE = Net Income + D&A - CAPEX_positive - ΔNWC + Net Borrowing

    Args:
        net_borrowing_schedule: Optional dict mapping forecast label (e.g. "2026F")
            to Net Borrowing value (VND bn). Positive = new debt drawn, negative = repaid.
            If None, Net Borrowing = 0 for all forecast years (stable leverage assumption).

    Key invariants per valuation handbook:
    - Discount rate MUST be Re, never WACC.
    - FCFE gives Equity Value directly — do NOT subtract net debt again.
    - Terminal FCFE should be normalized (no unusual borrowing): NB=0 ensures this.
    - Condition: Re > terminal_growth.
    """
    if cost_of_equity_assumptions is None:
        cost_of_equity_assumptions = CostOfEquityAssumptions()

    warnings: list[str] = list(forecast.warnings)
    re = cost_of_equity_assumptions.cost_of_equity

    # INVALID guard: Re (cost of equity) must exceed terminal growth for Gordon Growth to be finite.
    re_invalid = False
    if re <= terminal_growth:
        warnings.append(
            f"INVALID: Re ({re:.1%}) ≤ terminal growth ({terminal_growth:.1%}) — "
            "terminal value undefined; target price blocked"
        )
        re_invalid = True
        terminal_growth = re - 0.01  # prevent ZeroDivisionError; result will not yield target price

    fy_periods = forecast.historical_periods
    latest_fy = fy_periods[-1] if fy_periods else None

    def _get(key: str, period: str | None) -> float | None:
        if not period:
            return None
        entry = fact_table.get(key, {}).get(period)
        if entry is None:
            return None
        return entry.value if hasattr(entry, "value") else float(entry)

    # Target price requires explicit share-count facts; EPS-implied shares are a
    # reconciliation diagnostic and must not drive report-facing valuation.
    if shares_mn is None:
        shares_mn = explicit_shares_mn(fact_table, latest_fy)
    if shares_mn is None:
        warnings.append(
            "FCFE: shares_outstanding fact missing — target price blocked to avoid EPS-implied share-count error."
        )

    if net_borrowing_schedule is None:
        warnings.append(
            "FCFE forecast assumes stable leverage (Net Borrowing = 0 each year). "
            "Provide net_borrowing_schedule to override with actual vay/trả nợ data."
        )

    n = len(forecast.forecast_years)
    fcfe_years: list[FCFEYear] = []
    prev_revenue: float | None = None

    for t, fy in enumerate(forecast.forecast_years, start=1):
        ni = fy.net_income
        dep = fy.depreciation
        capex_pos = abs(fy.capex) if fy.capex is not None else None

        # ΔNWC: 2% of revenue change — consistent with fcff.py approximation
        if prev_revenue is not None and fy.revenue is not None:
            delta_nwc = 0.02 * (fy.revenue - prev_revenue)
        elif fy.revenue is not None and prev_revenue is None and latest_fy:
            hist_rev = _get("revenue.net", latest_fy)
            delta_nwc = 0.02 * (fy.revenue - (hist_rev or fy.revenue)) if hist_rev else 0.0
        else:
            delta_nwc = 0.0

        # Net Borrowing: from schedule if provided, else 0
        net_borrowing = (
            net_borrowing_schedule.get(fy.label, 0.0)
            if net_borrowing_schedule
            else 0.0
        )

        # FCFE = NI + D&A - CAPEX_positive - ΔNWC + Net Borrowing
        if ni is not None and dep is not None and capex_pos is not None:
            fcfe = ni + dep - capex_pos - delta_nwc + net_borrowing
        else:
            fcfe = None
            warnings.append(f"FCFE for {fy.label} missing inputs (NI/D&A/CAPEX) — using None")

        discount_factor = 1 / (1 + re) ** t
        pv_fcfe = fcfe * discount_factor if fcfe is not None else None

        fcfe_years.append(FCFEYear(
            year=fy.year,
            label=fy.label,
            net_income=ni,
            depreciation=dep,
            capex=capex_pos,  # stored as positive outflow; formula: FCFE = NI + D&A - CAPEX - ΔNWC + NB
            delta_nwc=delta_nwc,
            net_borrowing=net_borrowing,
            fcfe=fcfe,
            discount_factor=discount_factor,
            pv_fcfe=pv_fcfe,
        ))
        prev_revenue = fy.revenue

    sum_pv = sum(fy.pv_fcfe for fy in fcfe_years if fy.pv_fcfe is not None)

    # Terminal value (Gordon Growth) on last projected FCFE
    # Use FCFE with NB=0 in terminal year (normalized, no unusual borrowing effect)
    last_fcfe = fcfe_years[-1].fcfe if fcfe_years else None
    if last_fcfe is not None:
        terminal_fcfe = last_fcfe * (1 + terminal_growth)
        tv = terminal_fcfe / (re - terminal_growth)
        pv_tv = tv / (1 + re) ** n
    else:
        tv = 0.0
        pv_tv = 0.0
        warnings.append("Terminal value = 0 due to missing FCFE in final forecast year")

    # FCFE → Equity Value directly (no net debt subtraction)
    equity_val = sum_pv + pv_tv

    target_price: float | None = None
    if not re_invalid:
        if shares_mn and shares_mn > 0 and equity_val > 0:
            target_price = (equity_val / shares_mn) * 1_000  # VND bn / mn shares * 1000 = VND/share
        elif equity_val <= 0:
            warnings.append("FCFE: equity value is non-positive — target price not computed")

    upside_pct: float | None = None
    if target_price and current_price_vnd and current_price_vnd > 0:
        upside_pct = (target_price - current_price_vnd) / current_price_vnd

    return FCFEResult(
        ticker=ticker,
        cost_of_equity_assumptions=cost_of_equity_assumptions,
        cost_of_equity=re,
        terminal_growth=terminal_growth,
        forecast_years=fcfe_years,
        sum_pv_fcfe=sum_pv,
        terminal_value=tv,
        pv_terminal_value=pv_tv,
        equity_value=equity_val,
        shares_mn=shares_mn,
        target_price_vnd=target_price,
        current_price_vnd=current_price_vnd,
        upside_pct=upside_pct,
        warnings=warnings,
    )
