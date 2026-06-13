"""Dividend schedule and payout policy module (P1-03).

Models dividend payouts to correctly compute retained earnings in the forecast.
Without this, the forecast implicitly retains all earnings (zero dividend),
which overstates equity and cash for companies with regular cash dividends.

All arithmetic is deterministic Python — no LLM involvement.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Literal

from backend.analytics._entry import entry_value
from backend.analytics.shares import explicit_shares_mn
from backend.facts.normalizer import FactTable


def _get(table: FactTable, key: str, period: str) -> float | None:
    entry = table.get(key, {}).get(period)
    if entry is None:
        return None
    return entry_value(entry)


DividendMethod = Literal[
    "historical_median_payout",
    "manual_override",
    "missing",
]


@dataclass
class DividendScheduleRow:
    year: int
    label: str
    net_income: float | None
    payout_ratio: float | None
    cash_dividend: float | None
    retained_earnings_addition: float | None  # = net_income - cash_dividend
    method: DividendMethod
    confidence: Literal["high", "medium", "low"]
    warning: str | None = None
    source_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "label": self.label,
            "net_income": round(self.net_income, 1) if self.net_income is not None else None,
            "payout_ratio": round(self.payout_ratio, 4) if self.payout_ratio is not None else None,
            "cash_dividend": round(self.cash_dividend, 1) if self.cash_dividend is not None else None,
            "retained_earnings_addition": round(self.retained_earnings_addition, 1) if self.retained_earnings_addition is not None else None,
            "method": self.method,
            "confidence": self.confidence,
            "warning": self.warning,
        }


@dataclass
class DividendSchedule:
    ticker: str
    method: DividendMethod
    historical_payout_ratio: float | None
    forecast_rows: list[DividendScheduleRow]
    warnings: list[str] = field(default_factory=list)

    def retained_earnings_schedule(self) -> dict[str, float]:
        """Return {label: retained_earnings_addition} for use in balance sheet forecast."""
        return {
            row.label: (row.retained_earnings_addition or 0.0)
            for row in self.forecast_rows
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "method": self.method,
            "historical_payout_ratio": (
                round(self.historical_payout_ratio, 4)
                if self.historical_payout_ratio is not None else None
            ),
            "forecast_rows": [r.to_dict() for r in self.forecast_rows],
            "warnings": self.warnings,
        }


def _compute_historical_payout_ratio(
    fact_table: FactTable,
    fy_periods: list[str],
) -> float | None:
    """Derive historical median payout ratio from fact_table.

    payout_ratio = cash_dividend / net_income
    Uses fact keys: dividends_paid.total (CFS) and net_income.parent
    """
    ratios: list[float] = []
    for period in fy_periods:
        div = _get(fact_table, "dividends_paid.total", period)
        if div is None:
            dps = _get(fact_table, "dividends_per_share.cash", period)
            shares_mn = explicit_shares_mn(fact_table, period)
            if dps is not None and dps >= 0 and shares_mn is not None:
                # VND/share * million shares / 1,000 = VND billion.
                div = dps * shares_mn / 1_000.0
        ni = _get(fact_table, "net_income.parent", period)
        if div is not None and ni is not None and ni > 0:
            ratio = abs(div) / ni
            if 0.0 <= ratio <= 1.0:
                ratios.append(ratio)
    if not ratios:
        return None
    return statistics.median(ratios)


def build_dividend_schedule(
    ticker: str,
    fact_table: FactTable,
    fy_periods: list[str],
    forecast_net_incomes: dict[str, float],  # {label: net_income_vnd_bn}
    manual_payout_ratio: float | None = None,
) -> DividendSchedule:
    """Build dividend schedule for forecast years.

    Args:
        ticker: Company ticker.
        fact_table: Historical canonical facts.
        fy_periods: Historical FY period labels.
        forecast_net_incomes: {label: net_income} for forecast years.
        manual_payout_ratio: Override payout ratio (0.0–1.0).

    Returns:
        DividendSchedule with per-year payout and retained earnings rows.
    """
    warnings: list[str] = []

    # Determine payout ratio
    if manual_payout_ratio is not None:
        payout_ratio = manual_payout_ratio
        method: DividendMethod = "manual_override"
        confidence: Literal["high", "medium", "low"] = "medium"
    else:
        payout_ratio = _compute_historical_payout_ratio(fact_table, fy_periods)
        if payout_ratio is not None:
            method = "historical_median_payout"
            confidence = "medium"
        else:
            method = "missing"
            confidence = "low"
            payout_ratio = None
            warnings.append(
                "Dividend data not found in fact_table (dividends_paid.total missing). "
                "Forecast assumes zero dividend payout — equity may be overstated. "
                "Recommend analyst review and explicit payout assumption."
            )

    rows: list[DividendScheduleRow] = []
    for label, ni in forecast_net_incomes.items():
        try:
            year = int(label.replace("F", ""))
        except ValueError:
            year = 0

        if payout_ratio is not None and ni is not None:
            cash_div = ni * payout_ratio
            retained = ni - cash_div
            row_warning = None
            if method == "missing":
                row_warning = "Zero dividend assumed — no historical payout data available."
        else:
            cash_div = None
            retained = ni  # fallback: all retained
            row_warning = "Dividend unknown — treating all net income as retained earnings."

        rows.append(DividendScheduleRow(
            year=year,
            label=label,
            net_income=ni,
            payout_ratio=payout_ratio,
            cash_dividend=cash_div,
            retained_earnings_addition=retained,
            method=method,
            confidence=confidence,
            warning=row_warning,
        ))

    return DividendSchedule(
        ticker=ticker,
        method=method,
        historical_payout_ratio=payout_ratio,
        forecast_rows=rows,
        warnings=warnings,
    )
