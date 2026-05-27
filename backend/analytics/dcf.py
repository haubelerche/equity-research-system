"""Deterministic DCF valuation.

Standard 2-stage DCF:
  Stage 1: explicit FCF forecast for `forecast_years`
  Stage 2: Gordon Growth terminal value at period n

FCF = operating_cash_flow.total - |capex.total|
Shares (mn) derived from net_income / EPS (avoids needing a separate shares field).

All arithmetic is pure Python — no LLM involvement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

FactTable = dict[str, dict[str, float]]


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
            "shares_mn": round(self.shares_mn, 4) if self.shares_mn else None,
            "intrinsic_value_per_share_vnd": (
                round(self.intrinsic_value_per_share_vnd, 0)
                if self.intrinsic_value_per_share_vnd else None
            ),
            "warnings": self.warnings,
        }


def _get(table: FactTable, key: str, period: str) -> float | None:
    return table.get(key, {}).get(period)


def _cagr(start: float, end: float, years: int) -> float | None:
    if start is None or end is None or years <= 0 or start <= 0:
        return None
    return (end / start) ** (1.0 / years) - 1.0


def run_dcf(
    ticker: str,
    fact_table: FactTable,
    assumptions: DCFAssumptions,
    scenario: str = "base",
) -> DCFResult:
    """Run a DCF valuation for a single scenario.

    Uses FCF = operating_cash_flow - capex (absolute value).
    Derives shares from net_income / eps.basic.
    """
    warnings: list[str] = [
        "Simplified OCF-CAPEX DCF — sử dụng CAGR lịch sử, không phải driver-based forecast. "
        "Dùng FCFF/FCFE blend (60/40) làm định giá chính. Kết quả này chỉ mang tính tham khảo."
    ]

    fy_periods = sorted(
        p for p in {p for vals in fact_table.values() for p in vals} if p.endswith("FY")
    )

    # Collect FCF history
    # CAPEX sign convention: stored as negative in CFS (cash outflow).
    # FCF = OCF + CAPEX_signed  (NOT ocf - capex, which would add capex back).
    fcf_history: dict[str, float] = {}
    capex_sign_anomaly: list[str] = []
    for p in fy_periods:
        ocf = _get(fact_table, "operating_cash_flow.total", p)
        capex = _get(fact_table, "capex.total", p)
        if ocf is not None and capex is not None:
            if capex > 0:
                capex_sign_anomaly.append(
                    f"{p}: CAPEX={capex:+.1f} tỷ VND (positive — expected negative from CFS)"
                )
            fcf_history[p] = ocf + capex   # capex negative → reduces FCF correctly
        elif ocf is not None:
            fcf_history[p] = ocf
            warnings.append(f"capex missing for {p}; using OCF as proxy for FCF")

    if capex_sign_anomaly:
        warnings.append(
            "CAPEX sign anomaly detected — CAPEX should be negative (cash outflow): "
            + "; ".join(capex_sign_anomaly)
        )

    if not fcf_history:
        warnings.append("No FCF history available — DCF cannot be computed")
        return DCFResult(
            ticker=ticker, scenario=scenario, assumptions=assumptions,
            periods_used=[], fcf_history_vnd_bn={}, fcf_cagr=None,
            projected_fcf_vnd_bn=[], pv_fcf_vnd_bn=[],
            terminal_value_vnd_bn=0.0, pv_terminal_value_vnd_bn=0.0,
            enterprise_value_vnd_bn=0.0, net_debt_vnd_bn=0.0,
            equity_value_vnd_bn=0.0, shares_mn=None,
            intrinsic_value_per_share_vnd=None, warnings=warnings,
        )

    fcf_vals = [fcf_history[p] for p in sorted(fcf_history)]
    latest_fcf = fcf_vals[-1]

    # Warn on negative FCF in history — CAGR-based projection unreliable
    neg_fcf_periods = [p for p, v in sorted(fcf_history.items()) if v < 0]
    if neg_fcf_periods:
        warnings.append(
            f"Negative FCF in history: {neg_fcf_periods} — "
            "CAGR-based projection unreliable; treat simplified DCF as indicative only"
        )
    if latest_fcf <= 0:
        warnings.append(
            "Latest-year FCF is non-positive — DCF projection base invalid; result not meaningful"
        )

    # Growth rate
    if assumptions.fcf_growth_override is not None:
        fcf_growth = assumptions.fcf_growth_override
        cagr = None
    elif len(fcf_vals) >= 2:
        cagr = _cagr(fcf_vals[0], fcf_vals[-1], len(fcf_vals) - 1)
        # Cap historical CAGR for projection: max 25%, min -10%
        fcf_growth = max(-0.10, min(0.25, cagr)) if cagr is not None else 0.05
        if cagr != fcf_growth:
            warnings.append(f"FCF CAGR {cagr:.1%} capped to {fcf_growth:.1%} for projection")
    else:
        fcf_growth = 0.05
        cagr = None
        warnings.append("Only 1 FCF period available; assuming 5% FCF growth")

    # Stage 1: explicit forecast
    n = assumptions.forecast_years
    wacc = assumptions.wacc
    g = assumptions.terminal_growth

    if wacc <= g:
        warnings.append(f"WACC ({wacc:.1%}) ≤ terminal growth ({g:.1%}); terminal value undefined — capped g")
        g = wacc - 0.01

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

    # Net debt: total_debt - cash (use latest available FY)
    latest_fy = sorted(fcf_history)[-1]
    total_debt = _get(fact_table, "total_debt.ending", latest_fy) or 0.0
    cash = _get(fact_table, "cash_and_equivalents.ending", latest_fy) or 0.0
    net_debt = total_debt - cash

    equity_val = ev - net_debt

    # Shares outstanding (millions) from EPS + net income
    shares_mn: float | None = None
    ni = _get(fact_table, "net_income.parent", latest_fy)
    eps = _get(fact_table, "eps.basic", latest_fy)
    if ni is not None and eps is not None and eps > 0:
        # net_income is in VND bn, eps in VND/share → shares in mn
        shares_mn = (ni * 1_000) / eps  # bn * 1000 / VND per share = mn shares

    intrinsic_per_share: float | None = None
    if shares_mn and shares_mn > 0 and equity_val > 0:
        intrinsic_per_share = (equity_val / shares_mn) * 1_000  # VND bn / mn shares * 1000 = VND/share

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
        warnings=warnings,
    )


def run_three_scenarios(
    ticker: str,
    fact_table: FactTable,
    base: DCFAssumptions | None = None,
) -> dict[str, DCFResult]:
    """Run bear / base / bull DCF scenarios.

    Bear:  WACC +2pp, terminal_growth -1pp, FCF growth -3pp
    Base:  as provided (or defaults)
    Bull:  WACC -2pp, terminal_growth +1pp, FCF growth +3pp
    """
    if base is None:
        base = DCFAssumptions()

    def _adj(wacc_delta: float, g_delta: float, growth_delta: float) -> DCFAssumptions:
        growth_override = (
            (base.fcf_growth_override or 0.0) + growth_delta
            if base.fcf_growth_override is not None
            else None
        )
        return DCFAssumptions(
            wacc=round(base.wacc + wacc_delta, 4),
            terminal_growth=round(base.terminal_growth + g_delta, 4),
            forecast_years=base.forecast_years,
            fcf_growth_override=growth_override,
        )

    return {
        "bear": run_dcf(ticker, fact_table, _adj(+0.02, -0.01, -0.03), "bear"),
        "base": run_dcf(ticker, fact_table, base, "base"),
        "bull": run_dcf(ticker, fact_table, _adj(-0.02, +0.01, +0.03), "bull"),
    }
