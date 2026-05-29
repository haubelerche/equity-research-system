"""Debt schedule and forecasting module (P0-02).

Provides:
- DebtScheduleRow: per-year debt roll-forward data
- MissingValueReason: structured N/A classification
- build_historical_debt_schedule(): derive from fact_table
- build_forecast_debt_schedule(): project forward years
- interest_bearing_debt(): normalize debt from balance sheet

All arithmetic is deterministic Python — no LLM involvement.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Literal

FactTable = dict[str, dict[str, float]]

NAStatus = Literal[
    "available",
    "missing_source_data",
    "not_applicable",
    "not_yet_implemented",
    "blocked_by_data_quality",
]

DebtForecastMethod = Literal[
    "direct_cash_flow",
    "balance_sheet_delta",
    "target_debt_ratio",
    "manual_override",
    "zero_debt_policy",
    "missing",
]


@dataclass
class MissingValueReason:
    field: str
    status: NAStatus
    explanation: str
    required_for_publish: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "status": self.status,
            "explanation": self.explanation,
            "required_for_publish": self.required_for_publish,
        }


@dataclass
class DebtScheduleRow:
    year: int                                    # e.g. 2024 for historical, 2026 for forecast
    label: str                                   # e.g. "2024FY" or "2026F"
    beginning_interest_bearing_debt: float | None
    ending_interest_bearing_debt: float | None

    new_borrowing: float | None = None
    debt_repayment: float | None = None
    net_borrowing: float | None = None

    interest_expense: float | None = None
    implied_cost_of_debt: float | None = None

    method: DebtForecastMethod = "missing"
    confidence: Literal["high", "medium", "low"] = "low"
    warning: str | None = None
    source_refs: list[str] = field(default_factory=list)

    missing_fields: list[MissingValueReason] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "year": self.year,
            "label": self.label,
            "beginning_interest_bearing_debt": self.beginning_interest_bearing_debt,
            "ending_interest_bearing_debt": self.ending_interest_bearing_debt,
            "new_borrowing": self.new_borrowing,
            "debt_repayment": self.debt_repayment,
            "net_borrowing": self.net_borrowing,
            "interest_expense": self.interest_expense,
            "implied_cost_of_debt": round(self.implied_cost_of_debt, 4) if self.implied_cost_of_debt is not None else None,
            "method": self.method,
            "confidence": self.confidence,
            "warning": self.warning,
            "source_refs": self.source_refs,
        }
        if self.missing_fields:
            d["missing_fields"] = [m.to_dict() for m in self.missing_fields]
        return d


@dataclass
class DebtSchedule:
    ticker: str
    historical_rows: list[DebtScheduleRow]
    forecast_rows: list[DebtScheduleRow]
    forecast_method: DebtForecastMethod
    warnings: list[str] = field(default_factory=list)

    def net_borrowing_schedule(self) -> dict[str, float]:
        """Return {label: net_borrowing} for forecast years (for FCFE engine)."""
        return {
            row.label: (row.net_borrowing or 0.0)
            for row in self.forecast_rows
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "forecast_method": self.forecast_method,
            "historical_rows": [r.to_dict() for r in self.historical_rows],
            "forecast_rows": [r.to_dict() for r in self.forecast_rows],
            "warnings": self.warnings,
        }


def interest_bearing_debt(fact_table: FactTable, period: str) -> float | None:
    """Normalize interest-bearing debt from available fact_table fields.

    Priority:
    1. total_debt.ending  (already normalized by normalizer)
    2. short_term_borrowings.ending + long_term_borrowings.ending
    3. short_term_debt.ending + long_term_debt.ending  (vnstock alias group)
    """
    total_debt = fact_table.get("total_debt.ending", {}).get(period)
    if total_debt is not None:
        return total_debt

    # Primary component keys
    st = fact_table.get("short_term_borrowings.ending", {}).get(period)
    lt = fact_table.get("long_term_borrowings.ending", {}).get(period)
    if st is not None or lt is not None:
        return (st or 0.0) + (lt or 0.0)

    # Alias component keys (vnstock normalizer variant)
    st_alias = fact_table.get("short_term_debt.ending", {}).get(period)
    lt_alias = fact_table.get("long_term_debt.ending", {}).get(period)
    if st_alias is not None or lt_alias is not None:
        return (st_alias or 0.0) + (lt_alias or 0.0)

    return None


def build_historical_debt_schedule(
    ticker: str,
    fact_table: FactTable,
    fy_periods: list[str],
) -> list[DebtScheduleRow]:
    """Build historical debt schedule from canonical facts.

    Uses balance_sheet_delta method: net_borrowing = ending - beginning debt.
    If direct borrowing/repayment data is available in CFS, uses direct_cash_flow.
    """
    rows: list[DebtScheduleRow] = []
    sorted_periods = sorted(fy_periods)

    for i, period in enumerate(sorted_periods):
        try:
            year = int(period.replace("FY", ""))
        except ValueError:
            year = 0

        ending_debt = interest_bearing_debt(fact_table, period)
        beginning_debt = (
            interest_bearing_debt(fact_table, sorted_periods[i - 1])
            if i > 0 else None
        )

        # Try direct CFS data first
        new_borrow = fact_table.get("proceeds_from_borrowings.total", {}).get(period)
        repayment = fact_table.get("repayment_of_borrowings.total", {}).get(period)
        ie = fact_table.get("interest_expense.total", {}).get(period)

        if new_borrow is not None and repayment is not None:
            net_borrow = new_borrow - abs(repayment)
            method: DebtForecastMethod = "direct_cash_flow"
            confidence: Literal["high", "medium", "low"] = "high"
            warning = None
        elif ending_debt is not None and beginning_debt is not None:
            net_borrow = ending_debt - beginning_debt
            method = "balance_sheet_delta"
            confidence = "medium"
            warning = (
                "Net borrowing approximated from change in interest-bearing debt "
                "due to missing direct borrowing/repayment detail in CFS."
            )
        else:
            net_borrow = None
            method = "missing"
            confidence = "low"
            warning = "Insufficient data to compute net borrowing for this period."

        implied_cod: float | None = None
        if ie is not None and beginning_debt and beginning_debt > 0:
            implied_cod = abs(ie) / beginning_debt

        missing: list[MissingValueReason] = []
        if ending_debt is None:
            missing.append(MissingValueReason(
                field="ending_interest_bearing_debt",
                status="missing_source_data",
                explanation=f"No total_debt.ending or borrowing components found for {period}",
                required_for_publish=True,
            ))

        rows.append(DebtScheduleRow(
            year=year,
            label=period,
            beginning_interest_bearing_debt=beginning_debt,
            ending_interest_bearing_debt=ending_debt,
            new_borrowing=new_borrow,
            debt_repayment=abs(repayment) if repayment is not None else None,
            net_borrowing=net_borrow,
            interest_expense=abs(ie) if ie is not None else None,
            implied_cost_of_debt=implied_cod,
            method=method,
            confidence=confidence,
            warning=warning,
            missing_fields=missing,
        ))

    return rows


def build_forecast_debt_schedule(
    ticker: str,
    fact_table: FactTable,
    historical_rows: list[DebtScheduleRow],
    forecast_labels: list[str],
    forecast_years: list[int],
    method_override: DebtForecastMethod | None = None,
    manual_debt_path: dict[str, float] | None = None,
) -> tuple[list[DebtScheduleRow], DebtForecastMethod, list[str]]:
    """Build forecast debt schedule.

    Method selection hierarchy:
    1. manual_override — if manual_debt_path is provided
    2. zero_debt_policy — if historical debt is zero/None across all years
    3. target_debt_ratio — use historical median debt/ending to project forward
    4. missing — if neither is defensible

    Returns: (forecast_rows, method_used, warnings)
    """
    warnings: list[str] = []

    # Determine last known ending debt
    last_ending = None
    for row in reversed(historical_rows):
        if row.ending_interest_bearing_debt is not None:
            last_ending = row.ending_interest_bearing_debt
            break

    # Case 1: Manual override
    if manual_debt_path is not None or method_override == "manual_override":
        rows: list[DebtScheduleRow] = []
        prev_debt = last_ending
        for label, year in zip(forecast_labels, forecast_years):
            ending = (manual_debt_path or {}).get(label, prev_debt or 0.0)
            nb = (ending - (prev_debt or 0.0)) if prev_debt is not None else None
            rows.append(DebtScheduleRow(
                year=year, label=label,
                beginning_interest_bearing_debt=prev_debt,
                ending_interest_bearing_debt=ending,
                net_borrowing=nb,
                method="manual_override", confidence="medium",
                warning="Debt path provided by analyst — pending approval.",
            ))
            prev_debt = ending
        warnings.append("Debt forecast uses manual_override path — must be approved before publishing.")
        return rows, "manual_override", warnings

    # Case 2: Zero-debt policy (historical debt is zero or trivially small)
    all_hist_debts = [r.ending_interest_bearing_debt for r in historical_rows if r.ending_interest_bearing_debt is not None]
    if all_hist_debts and max(all_hist_debts) < 1.0:  # < 1 VND bn threshold
        rows = []
        for label, year in zip(forecast_labels, forecast_years):
            rows.append(DebtScheduleRow(
                year=year, label=label,
                beginning_interest_bearing_debt=0.0,
                ending_interest_bearing_debt=0.0,
                net_borrowing=0.0,
                method="zero_debt_policy", confidence="high",
                warning=None,
            ))
        warnings.append("Zero-debt policy applied: historical interest-bearing debt is negligible.")
        return rows, "zero_debt_policy", warnings

    # Case 3: Target debt ratio — use median of historical ending debt as stable level
    if all_hist_debts:
        median_debt = statistics.median(all_hist_debts)
        rows = []
        prev_debt = last_ending if last_ending is not None else median_debt
        for label, year in zip(forecast_labels, forecast_years):
            ending = median_debt
            nb = ending - prev_debt
            rows.append(DebtScheduleRow(
                year=year, label=label,
                beginning_interest_bearing_debt=prev_debt,
                ending_interest_bearing_debt=ending,
                net_borrowing=nb,
                method="target_debt_ratio", confidence="low",
                warning=(
                    f"Forecast debt held at historical median {median_debt:.1f} VND bn. "
                    "This is a simplifying assumption — analyst review required."
                ),
            ))
            prev_debt = ending
        warnings.append(
            f"Debt forecast uses target_debt_ratio: median historical debt = {median_debt:.1f} VND bn. "
            "Low confidence — recommend analyst review."
        )
        return rows, "target_debt_ratio", warnings

    # Case 4: Missing
    rows = []
    for label, year in zip(forecast_labels, forecast_years):
        rows.append(DebtScheduleRow(
            year=year, label=label,
            beginning_interest_bearing_debt=None,
            ending_interest_bearing_debt=None,
            net_borrowing=None,
            method="missing", confidence="low",
            warning="Debt forecast unavailable — insufficient historical data.",
            missing_fields=[
                MissingValueReason(
                    field="ending_interest_bearing_debt",
                    status="missing_source_data",
                    explanation="No historical debt data to anchor forecast.",
                    required_for_publish=True,
                )
            ],
        ))
    warnings.append(
        "Debt forecast is MISSING for all years — no historical debt data available. "
        "FCFE confidence will be low. Final recommendation is blocked pending analyst review."
    )
    return rows, "missing", warnings


def build_debt_schedule(
    ticker: str,
    fact_table: FactTable,
    fy_periods: list[str],
    forecast_labels: list[str],
    forecast_years: list[int],
    manual_debt_path: dict[str, float] | None = None,
) -> DebtSchedule:
    """Main entry point: build full historical + forecast debt schedule."""
    historical_rows = build_historical_debt_schedule(ticker, fact_table, fy_periods)
    forecast_rows, method, warnings = build_forecast_debt_schedule(
        ticker=ticker,
        fact_table=fact_table,
        historical_rows=historical_rows,
        forecast_labels=forecast_labels,
        forecast_years=forecast_years,
        manual_debt_path=manual_debt_path,
    )
    return DebtSchedule(
        ticker=ticker,
        historical_rows=historical_rows,
        forecast_rows=forecast_rows,
        forecast_method=method,
        warnings=warnings,
    )
