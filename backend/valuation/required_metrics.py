"""Minimum metric contracts for the MVP valuation stack.

These sets define the facts that valuation modules need from reported financial
statements. Market, peer, debt-policy, corporate-action, WACC, tax, and working
capital assumptions intentionally live outside this module in the
ValuationInputPack.
"""
from __future__ import annotations

RATIO_REQUIRED: set[str] = {
    "revenue.net",
    "gross_profit.total",
    "net_income.parent",
    "total_assets.ending",
    "equity.parent",
    "short_term_debt.ending",
    "long_term_debt.ending",
    "cash_and_equivalents.ending",
    "short_term_investments.ending",
    "interest_expense.total",
    "operating_cash_flow.total",
    "capex.total",
    "eps.basic",
}

FCFF_REQUIRED: set[str] = {
    "profit_before_tax.total",
    "interest_expense.total",
    "tax_expense.total",
    "depreciation.total",
    "capex.total",
    "cash_and_equivalents.ending",
    "short_term_investments.ending",
    "short_term_debt.ending",
    "long_term_debt.ending",
}

FCFE_REQUIRED: set[str] = {
    "net_income.parent",
    "depreciation.total",
    "capex.total",
    "proceeds_from_borrowings.total",
    "repayment_of_borrowings.total",
}

PE_SANITY_REQUIRED: set[str] = {
    "eps.basic",
}

EV_EBITDA_REQUIRED: set[str] = {
    "profit_before_tax.total",
    "depreciation.total",
    "cash_and_equivalents.ending",
    "short_term_debt.ending",
    "long_term_debt.ending",
}

# Core facts that should block a reportable valuation run when absent. The first
# tuple represents an OR requirement.
HARD_BLOCK_FACTS: tuple[str | tuple[str, ...], ...] = (
    "revenue.net",
    "net_income.parent",
    ("operating_cash_flow.total", "profit_before_tax.total"),
    "capex.total",
    "cash_and_equivalents.ending",
    "short_term_debt.ending",
)

MARKET_REQUIRED: set[str] = {
    "price",
    "shares_outstanding",
}
