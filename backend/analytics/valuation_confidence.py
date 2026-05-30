"""Valuation confidence scoring module (P2-01).

Produces a module-level confidence table for valuation outputs.
Each module gets a confidence level and reasons, so readers understand
which parts of the valuation are reliable vs. uncertain.

All logic is deterministic Python — no LLM involvement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ConfidenceLevel = Literal["high", "medium", "low", "unavailable"]
FinalRating = Literal["approved", "draft_only", "blocked"]


@dataclass
class ValuationConfidence:
    historical_financials: ConfidenceLevel
    forecast_model: ConfidenceLevel
    tax_policy: ConfidenceLevel
    debt_schedule: ConfidenceLevel
    dividend_schedule: ConfidenceLevel
    fcff_dcf: ConfidenceLevel
    fcfe_dcf: ConfidenceLevel
    relative_pe: ConfidenceLevel
    relative_ev_ebitda: ConfidenceLevel
    final_rating: FinalRating
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "historical_financials": self.historical_financials,
            "forecast_model": self.forecast_model,
            "tax_policy": self.tax_policy,
            "debt_schedule": self.debt_schedule,
            "dividend_schedule": self.dividend_schedule,
            "fcff_dcf": self.fcff_dcf,
            "fcfe_dcf": self.fcfe_dcf,
            "relative_pe": self.relative_pe,
            "relative_ev_ebitda": self.relative_ev_ebitda,
            "final_rating": self.final_rating,
            "reasons": self.reasons,
        }


def _min_confidence(a: ConfidenceLevel, b: ConfidenceLevel) -> ConfidenceLevel:
    """Return the lower of two confidence levels."""
    order: list[ConfidenceLevel] = ["unavailable", "low", "medium", "high"]
    ia = order.index(a) if a in order else 0
    ib = order.index(b) if b in order else 0
    return order[min(ia, ib)]


def build_valuation_confidence(
    historical_facts_validated: bool,
    forecast_assumption_status: str,
    tax_policy_source: str,
    tax_policy_approved: bool,
    debt_schedule_method: str,
    debt_schedule_approved: bool,
    dividend_method: str,
    fcff_has_warnings: bool,
    fcfe_net_borrowing_method: str,
    relative_pe_status: str,
    relative_ev_ebitda_status: str,
    gate_status: str,
) -> ValuationConfidence:
    """Build a ValuationConfidence object from artifact status strings.

    Args:
        historical_facts_validated: True if canonical facts passed DQ gate.
        forecast_assumption_status: "analyst_approved" | "default_unapproved".
        tax_policy_source: From TaxPolicy.source.
        tax_policy_approved: From TaxPolicy.approved.
        debt_schedule_method: From DebtSchedule.forecast_method.
        debt_schedule_approved: Explicit approval flag.
        dividend_method: From DividendSchedule.method.
        fcff_has_warnings: True if FCFFResult.warnings is non-empty.
        fcfe_net_borrowing_method: How net_borrowing was determined for FCFE.
        relative_pe_status: From MultiplesResult.relative_valuation_status.
        relative_ev_ebitda_status: From MultiplesResult.relative_valuation_status.
        gate_status: From AssumptionGate.status.
    """
    reasons: list[str] = []

    # Historical financials
    hist: ConfidenceLevel = "high" if historical_facts_validated else "low"
    if not historical_facts_validated:
        reasons.append("Historical financials: DQ gate not passed.")

    # Forecast model
    if forecast_assumption_status == "analyst_approved":
        forecast: ConfidenceLevel = "high"
    else:
        forecast = "medium"
        reasons.append("Forecast model: assumptions are default/unapproved.")

    # Tax policy
    if tax_policy_source == "manual_override" and tax_policy_approved:
        tax: ConfidenceLevel = "high"
    elif tax_policy_source == "historical_effective_tax_rate":
        tax = "medium"
        if not tax_policy_approved:
            reasons.append("Tax policy: historical effective rate used but not analyst-approved.")
    else:  # statutory_default
        tax = "low"
        reasons.append("Tax policy: statutory fallback used (no valid historical data).")

    # Debt schedule
    if debt_schedule_method == "zero_debt_policy":
        debt: ConfidenceLevel = "high"
    elif debt_schedule_method in ("direct_cash_flow", "manual_override") and debt_schedule_approved:
        debt = "high"
    elif debt_schedule_method == "balance_sheet_delta":
        debt = "medium"
        reasons.append("Debt schedule: approximated from balance sheet delta (missing CFS detail).")
    elif debt_schedule_method == "target_debt_ratio":
        debt = "low"
        reasons.append("Debt schedule: projected using historical median ratio (low confidence).")
    else:  # missing
        debt = "low"
        reasons.append("Debt schedule: MISSING — forecast debt unavailable. FCFE is unreliable.")

    # Dividend schedule
    if dividend_method == "manual_override":
        div: ConfidenceLevel = "medium"
    elif dividend_method == "historical_median_payout":
        div = "medium"
    else:  # missing
        div = "low"
        reasons.append("Dividend schedule: no dividend data — all earnings treated as retained.")

    # FCFF confidence = min(hist, forecast, tax) + warning check
    fcff_base = _min_confidence(_min_confidence(hist, forecast), tax)
    fcff: ConfidenceLevel = "low" if fcff_has_warnings else fcff_base
    if fcff_has_warnings:
        reasons.append("FCFF DCF: computation warnings present (missing inputs in some years).")

    # FCFE confidence = min(FCFF, debt)
    if fcfe_net_borrowing_method in ("zero_debt_policy", "direct_cash_flow", "manual_override"):
        fcfe: ConfidenceLevel = fcff
    elif fcfe_net_borrowing_method == "balance_sheet_delta":
        fcfe = _min_confidence(fcff, "medium")
    else:
        fcfe = "low"
        reasons.append("FCFE DCF: Net Borrowing is missing/assumed zero — low confidence.")

    # Relative valuation
    rel_pe: ConfidenceLevel = (
        "unavailable" if relative_pe_status == "pending_peer_dataset" else "medium"
    )
    rel_ev: ConfidenceLevel = (
        "unavailable" if relative_ev_ebitda_status == "pending_peer_dataset" else "medium"
    )
    if rel_pe == "unavailable":
        reasons.append("Relative P/E: pending — no peer group data.")
    if rel_ev == "unavailable":
        reasons.append("Relative EV/EBITDA: pending — no peer group data.")

    # Final rating from gate
    if gate_status == "approved_for_publish":
        final: FinalRating = "approved"
    elif gate_status == "blocked":
        final = "blocked"
        reasons.append("Final rating: BLOCKED — data quality gate failed.")
    else:
        final = "draft_only"

    return ValuationConfidence(
        historical_financials=hist,
        forecast_model=forecast,
        tax_policy=tax,
        debt_schedule=debt,
        dividend_schedule=div,
        fcff_dcf=fcff,
        fcfe_dcf=fcfe,
        relative_pe=rel_pe,
        relative_ev_ebitda=rel_ev,
        final_rating=final,
        reasons=reasons,
    )
