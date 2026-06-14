"""Per-method data requirement registry.

Declares, for each valuation method, the canonical facts / assumptions / market
data it needs BEFORE it may run. Field names are the project's canonical metric
keys (see backend/facts/metric_metadata.py), not generic placeholders.

BLEND is intentionally absent: it is a composite gated AFTER valuation by
backend/valuation_method_policy.build_valuation_publishability_policy (blend is
publishable only from already-publishable sub-methods). Duplicating that here
would create two sources of truth.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MethodRequirement:
    method: str
    required_facts: tuple[str, ...]
    required_assumptions: tuple[str, ...] = field(default_factory=tuple)
    required_market_data: tuple[str, ...] = field(default_factory=tuple)


VALUATION_DATA_REQUIREMENTS: dict[str, MethodRequirement] = {
    "fcff_dcf": MethodRequirement(
        method="fcff_dcf",
        # Stored canonical facts the method genuinely needs. EBIT is derived from
        # profit_before_tax + interest (not stored as ebit.total); ΔNWC is derived
        # from the forecast working-capital schedule (not a stored CFS fact); D&A
        # is stored as depreciation.total. Requiring the derived/idealised keys
        # produced false "blocked" readings while FCFF actually computed.
        required_facts=(
            "revenue.net",
            "profit_before_tax.total",
            "tax_expense.total",
            "depreciation.total",
            "capex.total",
            "cash_and_equivalents.ending",
            "short_term_debt.ending",
            "long_term_debt.ending",
            "shares_outstanding.ending",
        ),
        required_assumptions=("wacc", "terminal_growth", "forecast_years"),
        required_market_data=("market_price",),
    ),
    "fcfe_dcf": MethodRequirement(
        method="fcfe_dcf",
        required_facts=(
            "operating_cash_flow.total",
            "capex.total",
            "proceeds_from_borrowings.total",
            "repayment_of_borrowings.total",
            "shares_outstanding.ending",
        ),
        required_assumptions=("cost_of_equity", "terminal_growth", "forecast_years"),
        required_market_data=("market_price",),
    ),
    "pe": MethodRequirement(
        method="pe",
        required_facts=(
            "eps.basic",
            "shares_outstanding.ending",
        ),
        required_market_data=("market_price", "peer_pe_median", "peer_group"),
    ),
    "ev_ebitda": MethodRequirement(
        method="ev_ebitda",
        # EBITDA derived from profit_before_tax (+ interest) + depreciation; neither
        # ebit.total nor da.total is stored. Net debt from balance-sheet debt/cash.
        required_facts=(
            "profit_before_tax.total",
            "depreciation.total",
            "cash_and_equivalents.ending",
            "short_term_debt.ending",
            "long_term_debt.ending",
            "shares_outstanding.ending",
        ),
        required_market_data=("market_price", "peer_ev_ebitda_median", "peer_group"),
    ),
}


def get_requirement(method: str) -> MethodRequirement:
    """Return the requirement for a method, or raise KeyError if unknown."""
    return VALUATION_DATA_REQUIREMENTS[method]
