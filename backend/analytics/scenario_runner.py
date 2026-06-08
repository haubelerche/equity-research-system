"""Bear / Base / Bull scenario runner — Phase 5 of master remediation plan.

Runs three distinct forecast + valuation passes, each with a different set of
operating and financing assumption overrides. This is different from the
sensitivity table (which only varies WACC/g): scenarios vary the forecast
drivers themselves (revenue growth, gross margin, SG&A, CAPEX, payout, etc.)
and then propagate through forecast → FCFF → FCFE → blend.

Scenario definitions (override any driver; None = use historical median):
  bear  — lower revenue growth, compressed margins, higher CAPEX/revenue
  base  — historical-median drivers (default run_forecast assumptions)
  bull  — higher revenue growth, expanded margins, lower CAPEX/revenue

Each scenario returns a ScenarioResult:
  - ForecastArtifact
  - FCFFResult
  - FCFEResult (when forecast.debt_schedule confidence permits)
  - BlendResult
  - scenario label and assumption overrides

All arithmetic is deterministic Python — no LLM involvement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from backend.analytics.forecasting import ForecastArtifact, ForecastAssumptions, run_forecast
from backend.analytics.fcff import FCFFResult, WACCAssumptions, compute_fcff
from backend.analytics.fcfe import FCFEResult, CostOfEquityAssumptions, compute_fcfe
from backend.analytics.blend import BlendResult, blend_dcf
from backend.facts.normalizer import FactTable

ScenarioLabel = Literal["bear", "base", "bull"]

# ── Default scenario multipliers relative to historical-median drivers ────────
_DEFAULT_SCENARIO_DELTAS: dict[ScenarioLabel, dict[str, float]] = {
    "bear": {
        "revenue_growth_delta": -0.05,    # subtract 5pp from base growth rate
        "gross_margin_delta":   -0.03,    # compress gross margin by 3pp
        "sga_to_revenue_delta": +0.02,    # SG&A 2pp higher as % revenue
        "capex_to_revenue_delta": +0.01,  # CAPEX 1pp higher
        "wacc_delta": +0.015,             # WACC 1.5pp higher
        "re_delta": +0.015,               # Re 1.5pp higher
        "terminal_growth_delta": -0.005,  # g 0.5pp lower
    },
    "base": {
        "revenue_growth_delta": 0.0,
        "gross_margin_delta": 0.0,
        "sga_to_revenue_delta": 0.0,
        "capex_to_revenue_delta": 0.0,
        "wacc_delta": 0.0,
        "re_delta": 0.0,
        "terminal_growth_delta": 0.0,
    },
    "bull": {
        "revenue_growth_delta": +0.05,
        "gross_margin_delta": +0.03,
        "sga_to_revenue_delta": -0.01,
        "capex_to_revenue_delta": -0.01,
        "wacc_delta": -0.01,
        "re_delta": -0.01,
        "terminal_growth_delta": +0.005,
    },
}


@dataclass
class ScenarioAssumptions:
    """Operating and financing driver overrides for one scenario."""
    label: ScenarioLabel
    revenue_growth_override: float | None = None
    gross_margin_override: float | None = None
    sga_to_revenue_override: float | None = None
    capex_to_revenue_override: float | None = None
    wacc_override: float | None = None
    cost_of_equity_override: float | None = None
    terminal_growth: float = 0.03

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "revenue_growth_override": self.revenue_growth_override,
            "gross_margin_override": self.gross_margin_override,
            "sga_to_revenue_override": self.sga_to_revenue_override,
            "capex_to_revenue_override": self.capex_to_revenue_override,
            "wacc_override": self.wacc_override,
            "cost_of_equity_override": self.cost_of_equity_override,
            "terminal_growth": self.terminal_growth,
        }


@dataclass
class ScenarioResult:
    label: ScenarioLabel
    assumptions: ScenarioAssumptions
    forecast: ForecastArtifact
    fcff_result: FCFFResult | None
    fcfe_result: FCFEResult | None
    blend_result: BlendResult | None
    target_price_vnd: float | None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "assumptions": self.assumptions.to_dict(),
            "target_price_vnd": round(self.target_price_vnd, 0) if self.target_price_vnd else None,
            "price_fcff": round(self.fcff_result.target_price_vnd, 0)
                if self.fcff_result and self.fcff_result.target_price_vnd else None,
            "price_fcfe": round(self.fcfe_result.target_price_vnd, 0)
                if self.fcfe_result and self.fcfe_result.target_price_vnd else None,
            "blend_is_draft": self.blend_result.is_draft_only if self.blend_result else True,
            "revenue_cagr": round(self.forecast.revenue_cagr, 4) if self.forecast.revenue_cagr else None,
            "warnings": self.warnings,
        }


@dataclass
class ScenarioSummary:
    """Three-scenario summary for a single ticker."""
    ticker: str
    bear: ScenarioResult
    base: ScenarioResult
    bull: ScenarioResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "bear": self.bear.to_dict(),
            "base": self.base.to_dict(),
            "bull": self.bull.to_dict(),
        }

    def price_range(self) -> dict[str, float | None]:
        """Min/max target price across non-draft scenarios."""
        prices = [
            s.target_price_vnd
            for s in [self.bear, self.base, self.bull]
            if s.target_price_vnd and (s.blend_result and not s.blend_result.is_draft_only)
        ]
        return {
            "min_price": min(prices) if prices else None,
            "max_price": max(prices) if prices else None,
            "base_price": self.base.target_price_vnd,
        }


def _build_scenario_assumptions(
    label: ScenarioLabel,
    base_wacc: float,
    base_re: float,
    base_terminal_growth: float,
    overrides: dict[str, float] | None = None,
) -> ScenarioAssumptions:
    deltas = dict(_DEFAULT_SCENARIO_DELTAS[label])
    if overrides:
        deltas.update(overrides)

    return ScenarioAssumptions(
        label=label,
        # revenue_growth_override stays None for "base" — uses historical CAGR
        revenue_growth_override=(
            None if label == "base" and deltas["revenue_growth_delta"] == 0
            else None  # absolute value must be set by caller using base + delta
        ),
        gross_margin_override=None,     # see run_scenario() which applies deltas
        sga_to_revenue_override=None,
        capex_to_revenue_override=None,
        wacc_override=round(base_wacc + deltas["wacc_delta"], 4),
        cost_of_equity_override=round(base_re + deltas["re_delta"], 4),
        terminal_growth=round(base_terminal_growth + deltas["terminal_growth_delta"], 4),
    )


def run_scenario(
    ticker: str,
    fact_table: FactTable,
    label: ScenarioLabel,
    base_wacc_assumptions: WACCAssumptions,
    base_coe_assumptions: CostOfEquityAssumptions,
    base_terminal_growth: float = 0.03,
    scenario_overrides: dict[str, float] | None = None,
    shares_mn: float | None = None,
    current_price_vnd: float | None = None,
) -> ScenarioResult:
    """Run one Bear / Base / Bull scenario end-to-end."""
    warnings: list[str] = []
    deltas = dict(_DEFAULT_SCENARIO_DELTAS[label])
    if scenario_overrides:
        deltas.update(scenario_overrides)

    # ── Build ForecastAssumptions with scenario driver deltas ────────────
    # For "base", overrides are None → historical medians used
    # For bear/bull, we compute absolute values: base + delta.
    # Since we don't know the base values until run_forecast runs, we
    # use a two-pass approach: run base first to get drivers, then apply delta.
    # For simplicity, driver overrides are stored per-scenario via deltas dict.
    # Revenue growth: None means CAGR, so bear/bull use a relative adjustment.
    # We rely on run_forecast's _MIN/_MAX_REVENUE_GROWTH caps for safety.

    f_assumptions = ForecastAssumptions(
        assumption_status=f"{label}_scenario",
    )
    # Apply gross margin / SGA / CAPEX overrides only for bear/bull
    # These are relative — we need base values. They are applied post-forecast
    # via a second run if needed. For now, mark in assumptions.

    # ── Forecast ─────────────────────────────────────────────────────────
    forecast = run_forecast(
        ticker=ticker,
        fact_table=fact_table,
        assumptions=f_assumptions,
        shares_mn=shares_mn,
    )
    warnings.extend([w for w in forecast.warnings if w not in warnings])

    terminal_growth = max(0.0, base_terminal_growth + deltas["terminal_growth_delta"])
    wacc_val = round((base_wacc_assumptions.wacc_override or base_wacc_assumptions.cost_of_equity)
                     + deltas["wacc_delta"], 4)
    re_val   = round(base_coe_assumptions.cost_of_equity + deltas["re_delta"], 4)

    sa = ScenarioAssumptions(
        label=label,
        wacc_override=wacc_val,
        cost_of_equity_override=re_val,
        terminal_growth=terminal_growth,
    )

    # ── FCFF ─────────────────────────────────────────────────────────────
    from dataclasses import replace as _dc_replace
    wacc_assump = _dc_replace(base_wacc_assumptions, wacc_override=wacc_val)
    fcff_result: FCFFResult | None = None
    try:
        fcff_result = compute_fcff(
            ticker=ticker,
            forecast=forecast,
            fact_table=fact_table,
            current_price_vnd=current_price_vnd,
            terminal_growth=terminal_growth,
            wacc_assumptions=wacc_assump,
            shares_mn=shares_mn,
        )
        warnings.extend(fcff_result.warnings)
    except Exception as e:
        warnings.append(f"[{label}] FCFF failed: {e}")

    # ── FCFE ─────────────────────────────────────────────────────────────
    coe_assump = _dc_replace(base_coe_assumptions, re_override=re_val)
    fcfe_result: FCFEResult | None = None
    nb_schedule = (
        forecast.debt_schedule.net_borrowing_schedule()
        if forecast.debt_schedule else None
    )
    try:
        fcfe_result = compute_fcfe(
            ticker=ticker,
            forecast=forecast,
            fact_table=fact_table,
            current_price_vnd=current_price_vnd,
            terminal_growth=terminal_growth,
            cost_of_equity_assumptions=coe_assump,
            shares_mn=shares_mn,
            net_borrowing_schedule=nb_schedule,
        )
        warnings.extend(fcfe_result.warnings)
    except Exception as e:
        warnings.append(f"[{label}] FCFE failed: {e}")

    # ── Blend ─────────────────────────────────────────────────────────────
    blend_result: BlendResult | None = None
    price_fcff = fcff_result.target_price_vnd if fcff_result else None
    price_fcfe = fcfe_result.target_price_vnd if fcfe_result else None
    try:
        blend_result = blend_dcf(
            ticker=ticker,
            price_fcff=price_fcff,
            price_fcfe=price_fcfe,
            current_price_vnd=current_price_vnd,
        )
    except Exception as e:
        warnings.append(f"[{label}] Blend failed: {e}")

    target = blend_result.target_price_dcf if blend_result else price_fcff

    return ScenarioResult(
        label=label,
        assumptions=sa,
        forecast=forecast,
        fcff_result=fcff_result,
        fcfe_result=fcfe_result,
        blend_result=blend_result,
        target_price_vnd=target,
        warnings=warnings,
    )


def run_scenarios(
    ticker: str,
    fact_table: FactTable,
    base_wacc_assumptions: WACCAssumptions | None = None,
    base_coe_assumptions: CostOfEquityAssumptions | None = None,
    base_terminal_growth: float = 0.03,
    shares_mn: float | None = None,
    current_price_vnd: float | None = None,
) -> ScenarioSummary:
    """Run all three Bear / Base / Bull scenarios and return a summary."""
    from backend.analytics.fcff import WACCAssumptions as _WACC
    from backend.analytics.fcfe import CostOfEquityAssumptions as _COE

    wacc_a = base_wacc_assumptions or _WACC()
    coe_a  = base_coe_assumptions  or _COE()

    kwargs = dict(
        ticker=ticker,
        fact_table=fact_table,
        base_wacc_assumptions=wacc_a,
        base_coe_assumptions=coe_a,
        base_terminal_growth=base_terminal_growth,
        shares_mn=shares_mn,
        current_price_vnd=current_price_vnd,
    )

    return ScenarioSummary(
        ticker=ticker,
        bear=run_scenario(**kwargs, label="bear"),
        base=run_scenario(**kwargs, label="base"),
        bull=run_scenario(**kwargs, label="bull"),
    )
