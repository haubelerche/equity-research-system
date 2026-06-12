"""FCFF (Free Cash Flow to Firm) valuation engine.

Formula: FCFF = EBIT(1 - T) + Depreciation - CAPEX - ΔNWC

Uses forecast income statement from forecasting.py to produce
the full FCFF table required by Key report.md.

All arithmetic is deterministic Python — no LLM involvement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.analytics._entry import entry_value
from backend.analytics.forecasting import ForecastArtifact, ForecastYear
from backend.analytics.net_debt_bridge import build_net_debt_bridge, NetDebtBridge
from backend.analytics.shares import explicit_shares_mn
from backend.analytics.tax_policy import TaxPolicy

from backend.facts.normalizer import FactTable


@dataclass
class WACCAssumptions:
    risk_free_rate: float = 0.04           # VN 10Y bond yield ~4%
    beta: float = 0.85                      # VN pharma sector estimate
    expected_market_return: float = 0.12   # VNINDEX long-run return
    size_premium: float = 0.02             # small-mid cap VN premium
    specific_risk_premium: float = 0.01   # company-specific risk adjustment
    cost_of_debt: float = 0.08             # approx bank lending rate
    tax_rate: float = 0.20
    debt_weight: float | None = None       # None → derive from latest balance sheet
    equity_weight: float | None = None
    wacc_override: float | None = None     # if set, bypass component calculation
    assumption_status: str = "default_unapproved"
    tax_policy: TaxPolicy | None = None   # if set, overrides tax_rate for EBIT(1-T)

    @property
    def cost_of_equity(self) -> float:
        """Extended CAPM: Re = Rf + Beta × ERP + Size Premium + Specific Risk Premium."""
        erp = self.expected_market_return - self.risk_free_rate
        return self.risk_free_rate + self.beta * erp + self.size_premium + self.specific_risk_premium

    def wacc(self, d_weight: float, e_weight: float) -> float:
        if self.wacc_override is not None:
            return self.wacc_override
        ke = self.cost_of_equity
        kd_after_tax = self.cost_of_debt * (1 - self.tax_rate)
        return e_weight * ke + d_weight * kd_after_tax


@dataclass
class FCFFYear:
    year: int
    label: str
    ebit: float | None
    ebit_after_tax: float | None       # EBIT(1-T)
    depreciation: float | None
    capex: float | None
    delta_nwc: float | None            # Change in net working capital
    fcff: float | None
    pv_fcff: float | None
    discount_factor: float | None


@dataclass
class FCFFResult:
    ticker: str
    wacc_assumptions: WACCAssumptions
    wacc: float
    terminal_growth: float
    forecast_years: list[FCFFYear]
    sum_pv_fcff: float
    terminal_value: float
    pv_terminal_value: float
    enterprise_value: float
    net_debt: float
    equity_value: float
    shares_mn: float | None
    target_price_vnd: float | None
    current_price_vnd: float | None
    upside_pct: float | None
    net_debt_bridge: NetDebtBridge | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def _r(v, d=1):
            return round(v, d) if v is not None else None

        return {
            "ticker": self.ticker,
            "wacc": round(self.wacc, 4),
            "terminal_growth": round(self.terminal_growth, 4),
            "assumption_status": self.wacc_assumptions.assumption_status,
            "wacc_breakdown": {
                "risk_free_rate": self.wacc_assumptions.risk_free_rate,
                "beta": self.wacc_assumptions.beta,
                "expected_market_return": self.wacc_assumptions.expected_market_return,
                "size_premium": self.wacc_assumptions.size_premium,
                "specific_risk_premium": self.wacc_assumptions.specific_risk_premium,
                "cost_of_equity": round(self.wacc_assumptions.cost_of_equity, 4),
                "cost_of_debt": self.wacc_assumptions.cost_of_debt,
                # Reflect the actual rate used: TaxPolicy.effective_tax_rate when provided
                "tax_rate": (
                    self.wacc_assumptions.tax_policy.effective_tax_rate
                    if self.wacc_assumptions.tax_policy is not None
                    else self.wacc_assumptions.tax_rate
                ),
                "wacc_override": self.wacc_assumptions.wacc_override,
            },
            "capex_convention": "positive_outflow",
            "capex_formula_note": "CAPEX displayed as positive outflow; formula: FCFF = NOPAT + D&A - CAPEX - ΔNWC",
            "fcff_table": [
                {
                    "year": fy.year,
                    "label": fy.label,
                    "ebit": _r(fy.ebit),
                    "ebit_after_tax": _r(fy.ebit_after_tax),
                    "depreciation": _r(fy.depreciation),
                    "capex": _r(fy.capex),
                    "delta_nwc": _r(fy.delta_nwc),
                    "fcff": _r(fy.fcff),
                    "discount_factor": round(fy.discount_factor, 4) if fy.discount_factor else None,
                    "pv_fcff": _r(fy.pv_fcff),
                }
                for fy in self.forecast_years
            ],
            "sum_pv_fcff": _r(self.sum_pv_fcff),
            "terminal_value": _r(self.terminal_value),
            "pv_terminal_value": _r(self.pv_terminal_value),
            "enterprise_value": _r(self.enterprise_value),
            "net_debt": _r(self.net_debt),
            "equity_value": _r(self.equity_value),
            "shares_mn": _r(self.shares_mn),
            "target_price_vnd": round(self.target_price_vnd, 0) if self.target_price_vnd is not None else None,
            "current_price_vnd": _r(self.current_price_vnd, 0),
            "upside_pct": round(self.upside_pct, 4) if self.upside_pct is not None else None,
            "net_debt_bridge": self.net_debt_bridge.to_dict() if self.net_debt_bridge else None,
            "warnings": self.warnings,
        }


def compute_fcff(
    ticker: str,
    forecast: ForecastArtifact,
    fact_table: FactTable,
    current_price_vnd: float | None = None,
    terminal_growth: float = 0.03,
    wacc_assumptions: WACCAssumptions | None = None,
    shares_mn: float | None = None,
) -> FCFFResult:
    """Compute FCFF valuation from forecast income statement.

    FCFF = EBIT(1-T) + Depreciation - CAPEX - ΔNWC

    NWC = current_assets - current_liabilities (simplified; ΔNWC = change YoY).
    For forecast years, ΔNWC is approximated as 2% of revenue change.
    """
    if wacc_assumptions is None:
        wacc_assumptions = WACCAssumptions()

    warnings: list[str] = list(forecast.warnings)

    # Capital structure from latest historical balance sheet
    fy_periods = forecast.historical_periods
    latest_fy = fy_periods[-1] if fy_periods else None

    def _get(key: str, period: str) -> float | None:
        if not period:
            return None
        entry = fact_table.get(key, {}).get(period)
        if entry is None:
            return None
        return entry_value(entry)

    ndb = build_net_debt_bridge(fact_table, latest_fy or "")
    for w in ndb.warnings:
        warnings.append(w)
    total_debt = ndb.total_debt or 0.0
    net_debt   = ndb.net_debt  if ndb.net_debt is not None else 0.0

    equity_book = _get("equity.parent", latest_fy) or 0.0
    total_capital = equity_book + total_debt

    d_weight = wacc_assumptions.debt_weight or (
        total_debt / total_capital if total_capital > 0 else 0.3
    )
    e_weight = wacc_assumptions.equity_weight or (1.0 - d_weight)

    wacc = wacc_assumptions.wacc(d_weight, e_weight)

    if wacc_assumptions.tax_policy is not None:
        tax_rate = wacc_assumptions.tax_policy.effective_tax_rate
        # Warn if the caller's WACCAssumptions.tax_rate differs materially (>2pp)
        diff = abs(wacc_assumptions.tax_rate - tax_rate)
        if diff > 0.02:
            warnings.append(
                f"FCFF: WACCAssumptions.tax_rate={wacc_assumptions.tax_rate:.1%} differs "
                f"from TaxPolicy.effective_tax_rate={tax_rate:.1%} by {diff:.1%}; "
                "using TaxPolicy rate for EBIT(1-T)"
            )
    else:
        tax_rate = wacc_assumptions.tax_rate
        warnings.append(
            f"FCFF: using WACCAssumptions.tax_rate={tax_rate:.1%} — "
            "no TaxPolicy object provided; may differ from forecast P&L effective tax rate"
        )

    # INVALID guard: WACC must exceed terminal growth for Gordon Growth to be meaningful.
    wacc_invalid = False
    if wacc <= terminal_growth:
        warnings.append(
            f"INVALID: WACC ({wacc:.1%}) ≤ terminal growth ({terminal_growth:.1%}) — "
            "terminal value undefined; target price blocked"
        )
        wacc_invalid = True
        terminal_growth = wacc - 0.01  # prevent ZeroDivisionError; result will not yield target price

    # Shares outstanding. Target price requires explicit share-count facts; EPS-
    # implied shares are reserved for reconciliation diagnostics.
    if shares_mn is None:
        shares_mn = _derive_shares(fact_table, latest_fy)
    if shares_mn is None:
        warnings.append(
            "FCFF: shares_outstanding fact missing — target price blocked to avoid EPS-implied share-count error."
        )

    # ── Build FCFF table ───────────────────────────────────────────────────
    n = len(forecast.forecast_years)
    fcff_years: list[FCFFYear] = []
    prev_revenue: float | None = None

    for t, fy in enumerate(forecast.forecast_years, start=1):
        ebit = fy.ebit
        dep = fy.depreciation
        capex = abs(fy.capex) if fy.capex is not None else None

        # ΔNWC: prefer driver-based value from ForecastArtifact (working_capital_schedule);
        # fall back to 2% of revenue change only when not provided.
        if fy.delta_nwc is not None:
            delta_nwc = fy.delta_nwc
        elif prev_revenue is not None and fy.revenue is not None:
            delta_nwc = 0.02 * (fy.revenue - prev_revenue)
            warnings.append(f"FCFF {fy.label}: delta_nwc estimated as 2% revenue change (no WC schedule)")
        elif fy.revenue is not None and prev_revenue is None and fy_periods:
            hist_rev = _get("revenue.net", latest_fy)
            delta_nwc = 0.02 * (fy.revenue - (hist_rev or fy.revenue)) if hist_rev else 0.0
            warnings.append(f"FCFF {fy.label}: delta_nwc estimated as 2% revenue change (no WC schedule)")
        else:
            delta_nwc = 0.0

        ebit_after_tax = ebit * (1 - tax_rate) if ebit is not None else None
        if ebit_after_tax is not None and dep is not None and capex is not None:
            fcff = ebit_after_tax + dep - capex - delta_nwc
        else:
            fcff = None
            warnings.append(f"FCFF for {fy.label} missing inputs — using None")

        discount_factor = 1 / (1 + wacc) ** t
        pv_fcff = fcff * discount_factor if fcff is not None else None

        fcff_years.append(FCFFYear(
            year=fy.year,
            label=fy.label,
            ebit=ebit,
            ebit_after_tax=ebit_after_tax,
            depreciation=dep,
            capex=capex,  # stored as positive outflow; formula: FCFF = NOPAT + D&A - CAPEX - ΔNWC
            delta_nwc=delta_nwc,
            fcff=fcff,
            discount_factor=discount_factor,
            pv_fcff=pv_fcff,
        ))
        prev_revenue = fy.revenue

    sum_pv = sum(fy.pv_fcff for fy in fcff_years if fy.pv_fcff is not None)

    # Terminal value (Gordon Growth) on last projected FCFF
    last_fcff = fcff_years[-1].fcff if fcff_years else None
    if last_fcff is not None:
        terminal_fcff = last_fcff * (1 + terminal_growth)
        tv = terminal_fcff / (wacc - terminal_growth)
        pv_tv = tv / (1 + wacc) ** n
    else:
        tv = 0.0
        pv_tv = 0.0
        warnings.append("Terminal value = 0 due to missing FCFF in final year")

    ev = sum_pv + pv_tv
    equity_val = ev - net_debt

    # Update bridge equity_value_from_ev now that we have EV
    ndb.equity_value_from_ev = equity_val

    target_price: float | None = None
    if ndb.is_blocked:
        warnings.append(
            "FCFF: target price BLOCKED — net_debt_bridge status=blocked (total_debt missing). "
            "Source debt facts before publishing."
        )
    elif not wacc_invalid:
        if shares_mn and shares_mn > 0 and equity_val > 0:
            target_price = (equity_val / shares_mn) * 1_000
        elif equity_val <= 0:
            warnings.append("FCFF: equity value is negative — target price not computed")

    upside_pct: float | None = None
    if target_price and current_price_vnd and current_price_vnd > 0:
        upside_pct = (target_price - current_price_vnd) / current_price_vnd

    return FCFFResult(
        ticker=ticker,
        wacc_assumptions=wacc_assumptions,
        wacc=wacc,
        terminal_growth=terminal_growth,
        forecast_years=fcff_years,
        sum_pv_fcff=sum_pv,
        terminal_value=tv,
        pv_terminal_value=pv_tv,
        enterprise_value=ev,
        net_debt=net_debt,
        equity_value=equity_val,
        shares_mn=shares_mn,
        target_price_vnd=target_price,
        current_price_vnd=current_price_vnd,
        upside_pct=upside_pct,
        net_debt_bridge=ndb,
        warnings=warnings,
    )


def _derive_shares(fact_table: FactTable, latest_fy: str | None) -> float | None:
    return explicit_shares_mn(fact_table, latest_fy)
