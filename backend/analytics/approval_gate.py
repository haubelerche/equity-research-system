"""Assumption approval gate — blocks BUY/HOLD/SELL when key assumptions are pending (P0-03).

No valuation recommendation may be published as BUY/HOLD/SELL unless all
critical assumption gates are approved.

When assumptions are pending, the report must display:
    "Draft / Needs Analyst Review"
    "Model-implied valuation range"
NOT a final BUY/HOLD/SELL label.

All logic is deterministic Python — no LLM involvement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

GateStatus = Literal[
    "approved_for_publish",
    "draft_needs_analyst_review",
    "blocked",
]


@dataclass
class AssumptionGate:
    data_quality_passed: bool = False
    tax_policy_approved: bool = False
    wacc_approved: bool = False
    cost_of_equity_approved: bool = False
    terminal_growth_approved: bool = False
    forecast_assumptions_approved: bool = False
    debt_schedule_approved: bool = False
    dividend_schedule_approved: bool = False
    peer_multiples_approved: bool = False
    final_recommendation_approved: bool = False

    status: GateStatus = "draft_needs_analyst_review"
    blocking_reasons: list[str] = field(default_factory=list)

    def evaluate(self) -> "AssumptionGate":
        """Evaluate gate status from individual flags. Returns self for chaining."""
        reasons: list[str] = []

        # Critical — block valuation entirely if data is bad
        if not self.data_quality_passed:
            reasons.append("Data quality gate has not passed.")

        # Required for any DCF-based conclusion
        if not self.tax_policy_approved:
            reasons.append("Tax policy has not been approved — tax rate source uncertain.")
        if not self.wacc_approved:
            reasons.append("WACC assumptions are default/unapproved.")
        if not self.cost_of_equity_approved:
            reasons.append("Cost of equity (Re) assumptions are default/unapproved.")
        if not self.terminal_growth_approved:
            reasons.append("Terminal growth rate has not been approved.")
        if not self.forecast_assumptions_approved:
            reasons.append("Forecast model assumptions (revenue growth, margins) not approved.")

        # Required for FCFE
        if not self.debt_schedule_approved:
            reasons.append("Debt schedule not approved — FCFE net borrowing is unverified.")

        # Required for accurate FCFE equity projection
        if not self.dividend_schedule_approved:
            reasons.append(
                "Dividend schedule not approved — retained earnings and equity forecast may be overstated."
            )

        # Required for relative valuation cross-check
        if not self.peer_multiples_approved:
            reasons.append(
                "Peer multiples not approved — relative valuation (P/E, EV/EBITDA) is pending verified peer dataset."
            )

        # Required for final recommendation
        if not self.final_recommendation_approved:
            reasons.append("Final recommendation has not been explicitly approved by analyst.")

        self.blocking_reasons = reasons

        if self.data_quality_passed and not reasons:
            self.status = "approved_for_publish"
        elif not self.data_quality_passed:
            self.status = "blocked"
        else:
            self.status = "draft_needs_analyst_review"

        return self

    @property
    def recommendation_allowed(self) -> bool:
        """True only if ALL critical gates are approved and final_recommendation_approved."""
        return self.status == "approved_for_publish"

    @property
    def valuation_allowed(self) -> bool:
        """True if at least data quality passed — valuation can be computed as draft."""
        return self.data_quality_passed

    def recommendation_label(
        self,
        model_upside_pct: float | None = None,
    ) -> str:
        """Return the correct recommendation text.

        If approved, returns e.g. 'BUY', 'HOLD', 'SELL'.
        Otherwise returns 'Draft / Needs Analyst Review' with model-implied info.
        """
        if not self.recommendation_allowed:
            if model_upside_pct is not None:
                direction = (
                    "model-implied upside" if model_upside_pct > 0
                    else "model-implied downside"
                )
                return (
                    f"Draft / Needs Analyst Review "
                    f"({direction}: {model_upside_pct:+.1%})"
                )
            return "Draft / Needs Analyst Review"

        # Only reach here if fully approved
        if model_upside_pct is None:
            return "Model-implied valuation — no price signal"
        if model_upside_pct >= 0.20:
            return "BUY"
        if model_upside_pct <= -0.10:
            return "SELL"
        return "HOLD"

    def to_dict(self) -> dict[str, Any]:
        return {
            "data_quality_passed": self.data_quality_passed,
            "tax_policy_approved": self.tax_policy_approved,
            "wacc_approved": self.wacc_approved,
            "cost_of_equity_approved": self.cost_of_equity_approved,
            "terminal_growth_approved": self.terminal_growth_approved,
            "forecast_assumptions_approved": self.forecast_assumptions_approved,
            "debt_schedule_approved": self.debt_schedule_approved,
            "dividend_schedule_approved": self.dividend_schedule_approved,
            "peer_multiples_approved": self.peer_multiples_approved,
            "final_recommendation_approved": self.final_recommendation_approved,
            "status": self.status,
            "blocking_reasons": self.blocking_reasons,
            "recommendation_allowed": self.recommendation_allowed,
            "valuation_allowed": self.valuation_allowed,
        }


def build_gate_from_artifacts(
    data_quality_passed: bool,
    wacc_assumption_status: str,
    cost_of_equity_status: str,
    forecast_assumption_status: str,
    debt_schedule_method: str,
    tax_policy_approved: bool = False,
    dividend_schedule_approved: bool = False,
    peer_multiples_approved: bool = False,
    terminal_growth_approved: bool = False,
    final_recommendation_approved: bool = False,
) -> AssumptionGate:
    """Build and evaluate an AssumptionGate from artifact status strings.

    Args:
        wacc_assumption_status: From WACCAssumptions.assumption_status
            "analyst_approved" → approved, otherwise not.
        cost_of_equity_status: From CostOfEquityAssumptions.assumption_status.
        forecast_assumption_status: From ForecastAssumptions.assumption_status.
        debt_schedule_method: From DebtSchedule.forecast_method.
            "zero_debt_policy" (if historically zero) or "analyst_approved" → approved.
            "missing" → not approved.
        tax_policy_approved: Explicit override (TaxPolicy.approved field).
    """
    wacc_approved = wacc_assumption_status == "analyst_approved"
    coe_approved = cost_of_equity_status == "analyst_approved"
    forecast_approved = forecast_assumption_status == "analyst_approved"
    debt_approved = debt_schedule_method in (
        "zero_debt_policy",
        "direct_cash_flow",
        "analyst_approved",
        "manual_override",
    )

    gate = AssumptionGate(
        data_quality_passed=data_quality_passed,
        tax_policy_approved=tax_policy_approved,
        wacc_approved=wacc_approved,
        cost_of_equity_approved=coe_approved,
        terminal_growth_approved=terminal_growth_approved,
        forecast_assumptions_approved=forecast_approved,
        debt_schedule_approved=debt_approved,
        dividend_schedule_approved=dividend_schedule_approved,
        peer_multiples_approved=peer_multiples_approved,
        final_recommendation_approved=final_recommendation_approved,
    )
    return gate.evaluate()
