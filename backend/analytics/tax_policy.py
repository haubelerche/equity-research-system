"""Unified tax policy module.

Derives effective tax rate from historical canonical facts and exposes
a TaxPolicy dataclass that can be shared between the forecast P&L
(forecasting.py) and the FCFF valuation engine (fcff.py).

All arithmetic is deterministic Python — no LLM involvement.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Literal

from backend.analytics._entry import entry_value
from backend.facts.normalizer import FactTable


def _get(table: FactTable, key: str, period: str) -> float | None:
    entry = table.get(key, {}).get(period)
    if entry is None:
        return None
    return entry_value(entry)


_STATUTORY_TAX_RATE = 0.20
_MAX_VALID_RATE = 0.35


@dataclass
class TaxPolicy:
    ticker: str
    valuation_year: int
    effective_tax_rate: float
    statutory_tax_rate: float = _STATUTORY_TAX_RATE
    source: Literal[
        "historical_effective_tax_rate",
        "statutory_default",
        "manual_override",
    ] = "historical_effective_tax_rate"
    confidence: Literal["high", "medium", "low"] = "medium"
    historical_observations: list[dict] = field(default_factory=list)
    excluded_observations: list[dict] = field(default_factory=list)
    fallback_reason: str | None = None
    approved: bool = False
    source_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "valuation_year": self.valuation_year,
            "effective_tax_rate": round(self.effective_tax_rate, 4),
            "statutory_tax_rate": self.statutory_tax_rate,
            "source": self.source,
            "confidence": self.confidence,
            "historical_observations": self.historical_observations,
            "excluded_observations": self.excluded_observations,
            "fallback_reason": self.fallback_reason,
            "approved": self.approved,
            "source_refs": self.source_refs,
        }


def build_tax_policy(
    ticker: str,
    fact_table: FactTable,
    fy_periods: list[str],
    valuation_year: int = 2025,
    manual_override: float | None = None,
) -> TaxPolicy:
    """Build TaxPolicy from historical facts.

    Logic:
    1. Calculate effective_tax_rate = income_tax_expense / profit_before_tax
       for each FY period, where:
         - income_tax_expense = pbt - net_income  (derived)
       Only include observations where:
         - pbt > 0
         - tax_expense >= 0
         - 0.0 <= rate <= 0.35
       Observations that fail any filter go to excluded_observations with
       a reason string.
    2. Use the median of valid observations.
    3. If no valid data: fall back to statutory 0.20, confidence="low".
    4. If manual_override is provided: source="manual_override",
       confidence="high", rate = manual_override.
    """
    if manual_override is not None:
        return TaxPolicy(
            ticker=ticker,
            valuation_year=valuation_year,
            effective_tax_rate=manual_override,
            source="manual_override",
            confidence="high",
        )

    valid_observations: list[dict] = []
    excluded_observations: list[dict] = []

    for period in fy_periods:
        pbt = _get(fact_table, "profit_before_tax.total", period)
        ni = _get(fact_table, "net_income.parent", period)

        if pbt is None or ni is None:
            excluded_observations.append({
                "period": period,
                "reason": "missing profit_before_tax or net_income",
                "pbt": pbt,
                "ni": ni,
            })
            continue

        if pbt <= 0:
            excluded_observations.append({
                "period": period,
                "reason": f"pbt={pbt:.1f} <= 0 (loss year)",
                "pbt": pbt,
                "ni": ni,
            })
            continue

        tax_expense = pbt - ni
        if tax_expense < 0:
            excluded_observations.append({
                "period": period,
                "reason": f"derived tax_expense={tax_expense:.1f} < 0 (abnormal)",
                "pbt": pbt,
                "ni": ni,
                "tax_expense": tax_expense,
            })
            continue

        rate = tax_expense / pbt
        if rate > _MAX_VALID_RATE:
            excluded_observations.append({
                "period": period,
                "reason": f"rate={rate:.1%} > {_MAX_VALID_RATE:.0%} threshold (abnormal)",
                "pbt": pbt,
                "ni": ni,
                "tax_expense": tax_expense,
                "rate": rate,
            })
            continue

        valid_observations.append({
            "period": period,
            "pbt": pbt,
            "ni": ni,
            "tax_expense": tax_expense,
            "rate": round(rate, 6),
        })

    if not valid_observations:
        return TaxPolicy(
            ticker=ticker,
            valuation_year=valuation_year,
            effective_tax_rate=_STATUTORY_TAX_RATE,
            source="statutory_default",
            confidence="low",
            historical_observations=valid_observations,
            excluded_observations=excluded_observations,
            fallback_reason=(
                "No valid FY observations found; "
                "falling back to statutory tax rate"
            ),
        )

    median_rate = statistics.median(obs["rate"] for obs in valid_observations)

    return TaxPolicy(
        ticker=ticker,
        valuation_year=valuation_year,
        effective_tax_rate=median_rate,
        source="historical_effective_tax_rate",
        confidence="medium",
        historical_observations=valid_observations,
        excluded_observations=excluded_observations,
    )
