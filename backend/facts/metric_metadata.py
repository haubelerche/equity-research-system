"""Metric metadata registry — canonical unit semantics derived from metric_id.

FactEntry carries NO unit field. All unit/scale semantics are determined
by looking up the metric_id in METRIC_METADATA. Raw ``unit`` strings from
CSV/DB are used at ingestion time to normalize values, then discarded.

Canonical contracts:
  monetary   → absolute VND (e.g. 1.865 tỷ → 1_865_000_000_000)
  per_share  → VND/share   (e.g. 2000 đồng/cp → 2000)
  share_count→ absolute shares (e.g. 94.4 triệu cp → 94_400_000)
  percentage → decimal ratio   (e.g. 18.5% → 0.185)
  ratio      → dimensionless decimal
  multiple   → dimensionless multiplier (x)
  days       → integer days
  operational→ pass-through (no normalization)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Semantic types
# ---------------------------------------------------------------------------

class SemanticType(str, Enum):
    MONETARY = "monetary"
    PER_SHARE = "per_share"
    SHARE_COUNT = "share_count"
    PERCENTAGE = "percentage"
    RATIO = "ratio"
    MULTIPLE = "multiple"
    DAYS = "days"
    OPERATIONAL = "operational"


# Types where a missing raw unit makes the value ambiguous and must block.
SCALE_SENSITIVE_TYPES: frozenset[SemanticType] = frozenset({
    SemanticType.MONETARY,
    SemanticType.PER_SHARE,
    SemanticType.SHARE_COUNT,
    SemanticType.PERCENTAGE,
})


# ---------------------------------------------------------------------------
# Per-type valid raw units and their normalization multipliers
# ---------------------------------------------------------------------------

# monetary: canonical = absolute VND
_MONETARY_UNITS: dict[str, float] = {
    "vnd": 1.0,
    "dong": 1.0,
    "đồng": 1.0,
    "nghìn": 1_000.0,
    "nghin": 1_000.0,
    "nghìn đồng": 1_000.0,
    "nghin dong": 1_000.0,
    "triệu": 1_000_000.0,
    "trieu": 1_000_000.0,
    "triệu đồng": 1_000_000.0,
    "trieu dong": 1_000_000.0,
    "vnd_mn": 1_000_000.0,
    "tỷ": 1_000_000_000.0,
    "ty": 1_000_000_000.0,
    "tỷ đồng": 1_000_000_000.0,
    "ty dong": 1_000_000_000.0,
    "vnd_bn": 1_000_000_000.0,
}

# per_share: canonical = VND/share (đồng/cổ phiếu)
_PER_SHARE_UNITS: dict[str, float] = {
    "vnd": 1.0,
    "dong": 1.0,
    "đồng": 1.0,
    "đồng/cp": 1.0,
    "dong/cp": 1.0,
    "vnd/share": 1.0,
    "nghìn đồng/cp": 1_000.0,
    "nghin dong/cp": 1_000.0,
    "nghìn": 1_000.0,
    "nghin": 1_000.0,
}

# share_count: canonical = absolute shares
_SHARE_COUNT_UNITS: dict[str, float] = {
    "shares": 1.0,
    "cp": 1.0,
    "cổ phiếu": 1.0,
    "co phieu": 1.0,
    "nghìn cp": 1_000.0,
    "nghin cp": 1_000.0,
    "triệu cp": 1_000_000.0,
    "trieu cp": 1_000_000.0,
    "mn": 1_000_000.0,
    "million": 1_000_000.0,
}

# percentage: canonical = decimal ratio (18.5% → 0.185)
_PERCENTAGE_UNITS: dict[str, float] = {
    "%": 0.01,       # 18.5 → 0.185
    "percent": 0.01,
    "phan_tram": 0.01,
    "ratio": 1.0,    # already decimal
    "decimal": 1.0,
}

# ratio: dimensionless — no normalization needed
_RATIO_UNITS: dict[str, float] = {
    "ratio": 1.0,
    "decimal": 1.0,
}

# multiple: dimensionless multiplier (P/E, P/B, EV/EBITDA etc.)
_MULTIPLE_UNITS: dict[str, float] = {
    "x": 1.0,
    "times": 1.0,
    "lần": 1.0,
    "lan": 1.0,
}

# days: integer days
_DAYS_UNITS: dict[str, float] = {
    "days": 1.0,
    "ngày": 1.0,
    "ngay": 1.0,
}

# operational: pass-through
_OPERATIONAL_UNITS: dict[str, float] = {}

_VALID_UNITS_BY_TYPE: dict[SemanticType, dict[str, float]] = {
    SemanticType.MONETARY: _MONETARY_UNITS,
    SemanticType.PER_SHARE: _PER_SHARE_UNITS,
    SemanticType.SHARE_COUNT: _SHARE_COUNT_UNITS,
    SemanticType.PERCENTAGE: _PERCENTAGE_UNITS,
    SemanticType.RATIO: _RATIO_UNITS,
    SemanticType.MULTIPLE: _MULTIPLE_UNITS,
    SemanticType.DAYS: _DAYS_UNITS,
    SemanticType.OPERATIONAL: _OPERATIONAL_UNITS,
}


# ---------------------------------------------------------------------------
# Metric metadata registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MetricMeta:
    semantic_type: SemanticType


def _m(st: SemanticType) -> MetricMeta:
    return MetricMeta(semantic_type=st)


METRIC_METADATA: dict[str, MetricMeta] = {
    # --- Income statement (monetary) ---
    "revenue.net": _m(SemanticType.MONETARY),
    "revenue.total": _m(SemanticType.MONETARY),
    "cogs.total": _m(SemanticType.MONETARY),
    "gross_profit.total": _m(SemanticType.MONETARY),
    "selling_expense.total": _m(SemanticType.MONETARY),
    "admin_expense.total": _m(SemanticType.MONETARY),
    "operating_expense.total": _m(SemanticType.MONETARY),
    "operating_profit.total": _m(SemanticType.MONETARY),
    "ebit.total": _m(SemanticType.MONETARY),
    "ebitda.total": _m(SemanticType.MONETARY),
    "financial_income.total": _m(SemanticType.MONETARY),
    "financial_expense.total": _m(SemanticType.MONETARY),
    "interest_expense.total": _m(SemanticType.MONETARY),
    "profit_before_tax.total": _m(SemanticType.MONETARY),
    "tax_expense.total": _m(SemanticType.MONETARY),
    "net_income.total": _m(SemanticType.MONETARY),
    "net_income.parent": _m(SemanticType.MONETARY),
    "net_income.minority": _m(SemanticType.MONETARY),
    "depreciation.total": _m(SemanticType.MONETARY),
    "amortization.total": _m(SemanticType.MONETARY),
    "da.total": _m(SemanticType.MONETARY),

    # --- Balance sheet (monetary) ---
    "total_assets.total": _m(SemanticType.MONETARY),
    "total_assets.ending": _m(SemanticType.MONETARY),
    "current_assets.total": _m(SemanticType.MONETARY),
    "non_current_assets.total": _m(SemanticType.MONETARY),
    "cash_and_equivalents.total": _m(SemanticType.MONETARY),
    "cash_and_equivalents.ending": _m(SemanticType.MONETARY),
    "short_term_investments.ending": _m(SemanticType.MONETARY),
    "inventories.total": _m(SemanticType.MONETARY),
    "receivables.total": _m(SemanticType.MONETARY),
    "fixed_assets.total": _m(SemanticType.MONETARY),
    # Working-capital line items use the canonical ".ending" suffix everywhere
    # (taxonomy, fact.production_facts, working_capital_schedule, PDF extractor catalog).
    # Without registering them, validate_and_normalize rejected them as "unknown metric"
    # and build_fact_table dropped AR/inventory/AP → working capital read 0 (the
    # misleading "no historical AR data" WARN). Same fix as the liability ".ending" keys.
    "accounts_receivable.ending": _m(SemanticType.MONETARY),
    "inventory.ending": _m(SemanticType.MONETARY),
    "accounts_payable.ending": _m(SemanticType.MONETARY),
    # Canonical balance-sheet liability keys use the ".ending" suffix everywhere
    # (taxonomy, fact.production_facts, reconciliation, ratios, golden CSV). The
    # ".total" form here was a mismatch that made validate_and_normalize reject
    # these facts as "unknown metric" — silently dropping total/current liabilities
    # from every fact table and report. Keep them ".ending".
    "total_liabilities.ending": _m(SemanticType.MONETARY),
    "current_liabilities.ending": _m(SemanticType.MONETARY),
    "non_current_liabilities.ending": _m(SemanticType.MONETARY),
    "short_term_debt.ending": _m(SemanticType.MONETARY),
    "long_term_debt.ending": _m(SemanticType.MONETARY),
    "borrowings.total": _m(SemanticType.MONETARY),
    "equity.total": _m(SemanticType.MONETARY),
    "equity.parent": _m(SemanticType.MONETARY),
    "equity.minority": _m(SemanticType.MONETARY),
    "net_debt.total": _m(SemanticType.MONETARY),
    "working_capital.total": _m(SemanticType.MONETARY),

    # --- Cash flow (monetary) ---
    "operating_cash_flow.total": _m(SemanticType.MONETARY),
    "investing_cash_flow.total": _m(SemanticType.MONETARY),
    "financing_cash_flow.total": _m(SemanticType.MONETARY),
    "capex.total": _m(SemanticType.MONETARY),
    "dividends_paid.total": _m(SemanticType.MONETARY),
    "net_borrowing.total": _m(SemanticType.MONETARY),
    # Gross CFS financing lines — required for high-confidence FCFE net borrowing.
    # debt_schedule.build_historical_debt_schedule() reads these to reach
    # method="direct_cash_flow"; without them it falls back to balance_sheet_delta
    # (medium) and FCFE is blocked from publication.
    "proceeds_from_borrowings.total": _m(SemanticType.MONETARY),
    "repayment_of_borrowings.total": _m(SemanticType.MONETARY),
    "change_in_working_capital.total": _m(SemanticType.MONETARY),

    # --- Valuation aggregates (monetary) ---
    "market_cap.total": _m(SemanticType.MONETARY),
    "enterprise_value.total": _m(SemanticType.MONETARY),

    # --- Per-share metrics ---
    "eps.basic": _m(SemanticType.PER_SHARE),
    "eps.diluted": _m(SemanticType.PER_SHARE),
    "eps.forward": _m(SemanticType.PER_SHARE),
    "eps.core": _m(SemanticType.PER_SHARE),
    "dividends_per_share.cash": _m(SemanticType.PER_SHARE),
    "dividends_per_share.total": _m(SemanticType.PER_SHARE),
    "book_value_per_share.total": _m(SemanticType.PER_SHARE),
    "net_cash_per_share.total": _m(SemanticType.PER_SHARE),
    "current_price.close": _m(SemanticType.PER_SHARE),
    "target_price.total": _m(SemanticType.PER_SHARE),

    # --- Share counts ---
    "shares_outstanding.ending": _m(SemanticType.SHARE_COUNT),
    "shares_outstanding.diluted": _m(SemanticType.SHARE_COUNT),
    "shares_outstanding.total": _m(SemanticType.SHARE_COUNT),
    "shares_outstanding.weighted_avg": _m(SemanticType.SHARE_COUNT),
    "treasury_shares.ending": _m(SemanticType.SHARE_COUNT),

    # --- Percentage / ratio metrics ---
    "gross_margin.total": _m(SemanticType.PERCENTAGE),
    "ebit_margin.total": _m(SemanticType.PERCENTAGE),
    "ebitda_margin.total": _m(SemanticType.PERCENTAGE),
    "net_margin.total": _m(SemanticType.PERCENTAGE),
    "roe.total": _m(SemanticType.PERCENTAGE),
    "roa.total": _m(SemanticType.PERCENTAGE),
    "roic.total": _m(SemanticType.PERCENTAGE),
    "dividend_yield.total": _m(SemanticType.PERCENTAGE),
    "revenue_growth.yoy": _m(SemanticType.PERCENTAGE),
    "net_income_growth.yoy": _m(SemanticType.PERCENTAGE),
    "tax_rate.effective": _m(SemanticType.PERCENTAGE),
    "wacc.total": _m(SemanticType.PERCENTAGE),
    "terminal_growth.total": _m(SemanticType.PERCENTAGE),
    "cost_of_equity.total": _m(SemanticType.PERCENTAGE),
    "cost_of_debt.total": _m(SemanticType.PERCENTAGE),
    "upside.total": _m(SemanticType.PERCENTAGE),
    "debt_to_equity.total": _m(SemanticType.RATIO),
    "current_ratio.total": _m(SemanticType.RATIO),
    "quick_ratio.total": _m(SemanticType.RATIO),
    "interest_coverage.total": _m(SemanticType.RATIO),

    # --- Multiples ---
    "pe.trailing": _m(SemanticType.MULTIPLE),
    "pe.forward": _m(SemanticType.MULTIPLE),
    "pe.target": _m(SemanticType.MULTIPLE),
    "pe.core": _m(SemanticType.MULTIPLE),
    "pb.trailing": _m(SemanticType.MULTIPLE),
    "ev_ebitda.trailing": _m(SemanticType.MULTIPLE),
    "ev_ebit.trailing": _m(SemanticType.MULTIPLE),

    # --- Days ---
    "days_receivable.total": _m(SemanticType.DAYS),
    "days_inventory.total": _m(SemanticType.DAYS),
    "days_payable.total": _m(SemanticType.DAYS),
    "cash_conversion_cycle.total": _m(SemanticType.DAYS),
}


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def get_semantic_type(metric_id: str) -> SemanticType | None:
    meta = METRIC_METADATA.get(metric_id)
    return meta.semantic_type if meta else None


def is_known_metric(metric_id: str) -> bool:
    return metric_id in METRIC_METADATA


# ---------------------------------------------------------------------------
# Validate + normalize (single entry point)
# ---------------------------------------------------------------------------

class NormResult(NamedTuple):
    """Result of validate_and_normalize."""
    value: float
    status: str       # "ok" | "reject"
    reason: str       # empty on ok; internal log reason on reject


def validate_and_normalize(
    metric_id: str,
    raw_value: float,
    raw_unit: str | None,
) -> NormResult:
    """Validate raw_unit against metric_id and normalize value to canonical scale.

    Returns NormResult with:
      status="ok"     — value is normalized to canonical scale, safe for FactTable
      status="reject" — fact must NOT enter FactTable (unknown metric, missing
                         unit on scale-sensitive type, or invalid unit)

    This is the ONLY function that should be called at ingestion time.
    Do NOT call a separate validate then normalize — this function does both
    atomically so invalid units never silently produce a normalized value.
    """
    meta = METRIC_METADATA.get(metric_id)
    if meta is None:
        return NormResult(
            value=raw_value,
            status="reject",
            reason=f"unknown metric_id {metric_id!r}",
        )

    sem = meta.semantic_type
    valid_units = _VALID_UNITS_BY_TYPE[sem]

    # Operational metrics: no normalization, pass through
    if sem is SemanticType.OPERATIONAL:
        return NormResult(value=raw_value, status="ok", reason="")

    unit_key = raw_unit.strip().lower() if raw_unit else ""

    # Missing or empty unit
    if not unit_key:
        if sem in SCALE_SENSITIVE_TYPES:
            return NormResult(
                value=raw_value,
                status="reject",
                reason=f"missing unit for scale-sensitive metric {metric_id!r}",
            )
        # Non-scale-sensitive (ratio, multiple, days): pass through
        return NormResult(value=raw_value, status="ok", reason="")

    # Look up multiplier
    multiplier = valid_units.get(unit_key)
    if multiplier is None:
        return NormResult(
            value=raw_value,
            status="reject",
            reason=f"invalid unit {raw_unit!r} for metric {metric_id!r}",
        )

    return NormResult(
        value=raw_value * multiplier,
        status="ok",
        reason="",
    )


# ---------------------------------------------------------------------------
# Display formatting (canonical → report-ready strings)
# ---------------------------------------------------------------------------

_TY = 1_000_000_000.0   # 1 tỷ = 1e9 VND
_TRIEU = 1_000_000.0     # 1 triệu = 1e6 VND


def format_monetary(value: float | None, *, unit_label: bool = True) -> str:
    """Format absolute VND value for report display as tỷ đồng.

    >>> format_monetary(5_000_000_000_000)
    '5,000 tỷ đồng'
    >>> format_monetary(250_000_000, unit_label=False)
    '0.25'
    """
    if value is None:
        return "—"
    scaled = value / _TY
    text = f"{scaled:,.0f}" if abs(scaled) >= 1 else f"{scaled:,.2f}"
    return f"{text} tỷ đồng" if unit_label else text
