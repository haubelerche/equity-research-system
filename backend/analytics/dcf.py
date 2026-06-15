"""Deterministic DCF valuation (simplified reference model).

Standard 2-stage DCF:
  Stage 1: explicit FCF forecast for `forecast_years`
  Stage 2: Gordon Growth terminal value at period n

FCF = operating_cash_flow.total + capex.total  (capex stored negative from CFS)
Shares (mn) are accepted only from explicit shares_outstanding facts.

NOTE: This is a simplified OCF-CAPEX reference DCF.
The primary valuation uses the 60% FCFF + 40% FCFE blend in fcff.py / fcfe.py / blend.py.
All arithmetic is pure Python — no LLM involvement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.analytics._entry import entry_value
from backend.analytics.shares import explicit_shares_mn
from backend.facts.normalizer import FactTable


@dataclass
class DCFAssumptions:
    wacc: float = 0.10
    terminal_growth: float = 0.03
    forecast_years: int = 5
    fcf_growth_override: float | None = None  # None → use historical CAGR


@dataclass
class DCFResult:
    ticker: str
    scenario: str
    assumptions: DCFAssumptions
    periods_used: list[str]
    fcf_history_vnd_bn: dict[str, float]
    fcf_cagr: float | None
    projected_fcf_vnd_bn: list[float]
    pv_fcf_vnd_bn: list[float]
    terminal_value_vnd_bn: float
    pv_terminal_value_vnd_bn: float
    enterprise_value_vnd_bn: float
    net_debt_vnd_bn: float
    equity_value_vnd_bn: float
    shares_mn: float | None
    intrinsic_value_per_share_vnd: float | None
    terminal_value_weight: float | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "scenario": self.scenario,
            "assumptions": {
                "wacc": self.assumptions.wacc,
                "terminal_growth": self.assumptions.terminal_growth,
                "forecast_years": self.assumptions.forecast_years,
                "fcf_growth_override": self.assumptions.fcf_growth_override,
            },
            "periods_used": self.periods_used,
            "fcf_history_vnd_bn": self.fcf_history_vnd_bn,
            "fcf_cagr": self.fcf_cagr,
            "projected_fcf_vnd_bn": [round(v, 4) for v in self.projected_fcf_vnd_bn],
            "pv_fcf_vnd_bn": [round(v, 4) for v in self.pv_fcf_vnd_bn],
            "terminal_value_vnd_bn": round(self.terminal_value_vnd_bn, 4),
            "pv_terminal_value_vnd_bn": round(self.pv_terminal_value_vnd_bn, 4),
            "enterprise_value_vnd_bn": round(self.enterprise_value_vnd_bn, 4),
            "net_debt_vnd_bn": round(self.net_debt_vnd_bn, 4),
            "equity_value_vnd_bn": round(self.equity_value_vnd_bn, 4),
            "shares_mn": round(self.shares_mn, 4) if self.shares_mn is not None else None,
            "intrinsic_value_per_share_vnd": (
                round(self.intrinsic_value_per_share_vnd, 0)
                if self.intrinsic_value_per_share_vnd is not None else None
            ),
            "terminal_value_weight": (
                round(self.terminal_value_weight, 4)
                if self.terminal_value_weight is not None else None
            ),
            "warnings": self.warnings,
        }


def _get(table: FactTable, key: str, period: str) -> float | None:
    entry = table.get(key, {}).get(period)
    if entry is None:
        return None
    return entry_value(entry)


def _cagr(start: float, end: float, years: int) -> float | None:
    if start is None or end is None or years <= 0 or start <= 0 or end <= 0:
        return None
    return (end / start) ** (1.0 / years) - 1.0


def run_dcf(
    ticker: str,
    fact_table: FactTable,
    assumptions: DCFAssumptions,
    scenario: str = "base",
) -> DCFResult:
    """Run a simplified OCF-CAPEX DCF for a single scenario (reference model only).

    FCF = OCF + CAPEX_CFS  (CAPEX stored as negative from CFS; + adds it back correctly).
    Uses explicit shares_outstanding facts for per-share valuation.
    """
    warnings: list[str] = [
        "Simplified OCF-CAPEX DCF — sử dụng CAGR lịch sử, không phải driver-based forecast. "
        "Dùng FCFF/FCFE blend (60/40) làm định giá chính. Kết quả này chỉ mang tính tham khảo."
    ]

    def _empty() -> DCFResult:
        return DCFResult(
            ticker=ticker, scenario=scenario, assumptions=assumptions,
            periods_used=[], fcf_history_vnd_bn={}, fcf_cagr=None,
            projected_fcf_vnd_bn=[], pv_fcf_vnd_bn=[],
            terminal_value_vnd_bn=0.0, pv_terminal_value_vnd_bn=0.0,
            enterprise_value_vnd_bn=0.0, net_debt_vnd_bn=0.0,
            equity_value_vnd_bn=0.0, shares_mn=None,
            intrinsic_value_per_share_vnd=None, warnings=warnings,
        )

    if assumptions.forecast_years <= 0:
        warnings.append("forecast_years must be > 0; DCF cannot be computed")
        return _empty()

    fy_periods = sorted(
        p for p in {p for vals in fact_table.values() for p in vals} if p.endswith("FY")
    )

    # Collect FCF history.
    # CAPEX sign convention: stored as negative in CFS (cash outflow).
    # FCF = OCF + CAPEX_signed  (NOT ocf - capex, which would add capex back).
    # If CAPEX arrives as positive, auto-negate and warn — positive CAPEX from CFS is anomalous.
    fcf_history: dict[str, float] = {}
    for p in fy_periods:
        ocf = _get(fact_table, "operating_cash_flow.total", p)
        capex = _get(fact_table, "capex.total", p)
        if ocf is not None and capex is not None:
            if capex > 0:
                warnings.append(
                    f"{p}: CAPEX={capex:+.1f} tỷ VND positive (expected negative from CFS); "
                    "auto-negating to maintain correct FCF sign convention"
                )
                capex = -capex
            fcf_history[p] = ocf + capex   # capex negative → reduces FCF correctly
        elif ocf is not None:
            fcf_history[p] = ocf
            warnings.append(f"capex missing for {p}; using OCF as proxy for FCF")

    if not fcf_history:
        warnings.append("No FCF history available — DCF cannot be computed")
        return _empty()

    fcf_vals = [fcf_history[p] for p in sorted(fcf_history)]
    latest_fcf = fcf_vals[-1]

    neg_fcf_periods = [p for p, v in sorted(fcf_history.items()) if v < 0]
    neg_fcf_block = False
    if neg_fcf_periods:
        warnings.append(
            f"Negative FCF in history: {neg_fcf_periods} — "
            "CAGR-based projection unreliable; simplified DCF target price blocked"
        )
        neg_fcf_block = True
    if latest_fcf <= 0:
        warnings.append(
            "Latest-year FCF is non-positive — DCF projection base invalid; result not meaningful"
        )
        neg_fcf_block = True

    # Growth rate
    cagr: float | None = None
    if assumptions.fcf_growth_override is not None:
        fcf_growth = assumptions.fcf_growth_override
    elif len(fcf_vals) >= 2:
        cagr = _cagr(fcf_vals[0], fcf_vals[-1], len(fcf_vals) - 1)
        if cagr is None:
            # Start value ≤ 0 — CAGR undefined; fall back to conservative default
            fcf_growth = 0.05
            warnings.append("FCF CAGR unavailable (start or end value <= 0); assuming 5% FCF growth")
        else:
            fcf_growth = max(-0.10, min(0.25, cagr))
            if cagr != fcf_growth:
                warnings.append(f"FCF CAGR {cagr:.1%} capped to {fcf_growth:.1%} for projection")
    else:
        fcf_growth = 0.05
        warnings.append("Only 1 FCF period available; assuming 5% FCF growth")

    # Stage 1: explicit forecast
    n = assumptions.forecast_years
    wacc = assumptions.wacc
    g = assumptions.terminal_growth

    # INVALID guard: WACC must exceed terminal growth for Gordon Growth to be finite and positive.
    wacc_invalid = False
    if wacc <= g:
        warnings.append(
            f"INVALID: WACC ({wacc:.1%}) ≤ terminal growth ({g:.1%}) — "
            "terminal value undefined; target price blocked"
        )
        wacc_invalid = True
        g = wacc - 0.01  # prevent ZeroDivisionError; result will not produce a target price

    projected: list[float] = []
    fcf_t = latest_fcf
    for _ in range(n):
        fcf_t *= (1 + fcf_growth)
        projected.append(fcf_t)

    pv_fcf = [fcf / (1 + wacc) ** (t + 1) for t, fcf in enumerate(projected)]

    # Stage 2: terminal value
    terminal_fcf = projected[-1] * (1 + g)
    tv = terminal_fcf / (wacc - g)
    pv_tv = tv / (1 + wacc) ** n

    ev = sum(pv_fcf) + pv_tv

    # Terminal value weight warning
    tv_weight: float | None = None
    if ev > 0:
        tv_weight = pv_tv / ev
        if tv_weight > 0.85:
            warnings.append(f"Terminal value weight {tv_weight:.1%} > 85% — DCF result highly unreliable")
        elif tv_weight > 0.70:
            warnings.append(f"Terminal value weight {tv_weight:.1%} > 70% — sensitivity analysis required")

    # Net debt: total_debt - cash - short_term_investments (use latest available FY)
    latest_fy = sorted(fcf_history)[-1]
    total_debt = _get(fact_table, "total_debt.ending", latest_fy) or 0.0
    cash = _get(fact_table, "cash_and_equivalents.ending", latest_fy) or 0.0
    short_inv = _get(fact_table, "short_term_investments.ending", latest_fy) or 0.0
    net_debt = total_debt - cash - short_inv

    equity_val = ev - net_debt

    shares_mn = explicit_shares_mn(fact_table, latest_fy)
    if shares_mn is None:
        warnings.append(
            "Simplified DCF: shares_outstanding fact missing; target price blocked "
            "to avoid EPS-implied share-count error."
        )

    # Block target price when model assumptions are invalid or FCF history is unreliable
    intrinsic_per_share: float | None = None
    if not wacc_invalid and not neg_fcf_block:
        if shares_mn and shares_mn > 0 and equity_val > 0:
            intrinsic_per_share = (equity_val / shares_mn) * 1_000  # VND bn / mn shares * 1000 = VND/share
        elif equity_val <= 0:
            warnings.append("Equity value is negative — target price not computed")

    return DCFResult(
        ticker=ticker,
        scenario=scenario,
        assumptions=assumptions,
        periods_used=sorted(fcf_history),
        fcf_history_vnd_bn=fcf_history,
        fcf_cagr=cagr,
        projected_fcf_vnd_bn=projected,
        pv_fcf_vnd_bn=pv_fcf,
        terminal_value_vnd_bn=tv,
        pv_terminal_value_vnd_bn=pv_tv,
        enterprise_value_vnd_bn=ev,
        net_debt_vnd_bn=net_debt,
        equity_value_vnd_bn=equity_val,
        shares_mn=shares_mn,
        intrinsic_value_per_share_vnd=intrinsic_per_share,
        terminal_value_weight=tv_weight,
        warnings=warnings,
    )


def _derive_base_fcf_growth(fact_table: FactTable) -> float:
    """Compute FCF CAGR from historical OCF + CAPEX data for scenario adjustment baseline."""
    fy_periods = sorted(
        p for p in {p for vals in fact_table.values() for p in vals} if p.endswith("FY")
    )
    fcf_hist: dict[str, float] = {}
    for p in fy_periods:
        ocf = _get(fact_table, "operating_cash_flow.total", p)
        capex = _get(fact_table, "capex.total", p)
        if ocf is not None and capex is not None:
            c = -abs(capex) if capex > 0 else capex  # normalize positive CAPEX
            fcf_hist[p] = ocf + c
    fcf_vals = [fcf_hist[p] for p in sorted(fcf_hist)]
    if len(fcf_vals) >= 2:
        if fcf_vals[0] <= 0 or fcf_vals[-1] <= 0:
            return 0.05
        cagr = _cagr(fcf_vals[0], fcf_vals[-1], len(fcf_vals) - 1)
        return max(-0.10, min(0.25, cagr)) if cagr is not None else 0.05
    return 0.05


def run_three_scenarios(
    ticker: str,
    fact_table: FactTable,
    base: DCFAssumptions | None = None,
) -> dict[str, DCFResult]:
    """Run bear / base / bull DCF scenarios.

    Bear:  WACC +2pp, terminal_growth -1pp, FCF growth -3pp
    Base:  as provided (or defaults)
    Bull:  WACC -2pp, terminal_growth +1pp, FCF growth +3pp

    FCF growth adjustments are applied relative to the historical CAGR baseline even
    when base.fcf_growth_override is None, so Bear/Bull scenarios differ in growth rate.
    """
    if base is None:
        base = DCFAssumptions()

    # Derive base FCF growth so Bear/Bull deltas are always applied
    base_fcf_growth = (
        base.fcf_growth_override
        if base.fcf_growth_override is not None
        else _derive_base_fcf_growth(fact_table)
    )

    def _adj(wacc_delta: float, g_delta: float, growth_delta: float) -> DCFAssumptions:
        return DCFAssumptions(
            wacc=round(base.wacc + wacc_delta, 4),
            terminal_growth=round(base.terminal_growth + g_delta, 4),
            forecast_years=base.forecast_years,
            fcf_growth_override=round(base_fcf_growth + growth_delta, 4),
        )

    return {
        "bear": run_dcf(ticker, fact_table, _adj(+0.02, -0.01, -0.03), "bear"),
        "base": run_dcf(ticker, fact_table, base, "base"),
        "bull": run_dcf(ticker, fact_table, _adj(-0.02, +0.01, +0.03), "bull"),
    }
