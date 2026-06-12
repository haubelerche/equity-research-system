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

from backend.analytics._entry import entry_value
from backend.facts.normalizer import FactTable

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
    mandatory_debt_repayment: float | None = None   # scheduled principal repayment
    optional_debt_repayment: float | None = None    # discretionary prepayment
    debt_repayment: float | None = None             # = mandatory + optional
    net_borrowing: float | None = None              # = new_borrowing - debt_repayment

    average_debt: float | None = None               # = (beginning + ending) / 2
    cost_of_debt: float | None = None               # rate used for interest_expense
    interest_expense: float | None = None           # = average_debt × cost_of_debt (if available)
    implied_cost_of_debt: float | None = None       # historical: abs(ie) / beginning_debt

    identity_check_passes: bool | None = None       # ending == beginning + new_borrowing - repayment

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
            "new_borrowing": self.new_borrowing,
            "mandatory_debt_repayment": self.mandatory_debt_repayment,
            "optional_debt_repayment": self.optional_debt_repayment,
            "debt_repayment": self.debt_repayment,
            "ending_interest_bearing_debt": self.ending_interest_bearing_debt,
            "net_borrowing": self.net_borrowing,
            "average_debt": round(self.average_debt, 2) if self.average_debt is not None else None,
            "cost_of_debt": round(self.cost_of_debt, 4) if self.cost_of_debt is not None else None,
            "interest_expense": round(self.interest_expense, 2) if self.interest_expense is not None else None,
            "implied_cost_of_debt": round(self.implied_cost_of_debt, 4) if self.implied_cost_of_debt is not None else None,
            "identity_check_passes": self.identity_check_passes,
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
    analyst_approved: bool = False

    # ── Publishability gates ───────────────────────────────────────────────

    @property
    def is_fcfe_publishable(self) -> bool:
        """Return True only when net_borrowing can be trusted for FCFE.

        Per plan invariant:
          if net_borrowing.confidence not in ["high", "approved"]:
              fcfe.publishable = False

        Methods with guaranteed-high confidence:
          direct_cash_flow  — sourced from CFS (high)
          zero_debt_policy  — company carries no debt (high / N/A)
        All other methods (target_debt_ratio, balance_sheet_delta,
        manual_override, missing) are medium/low → block FCFE.
        """
        _PUBLISHABLE_METHODS: set[str] = {"direct_cash_flow", "zero_debt_policy"}
        if self.forecast_method == "manual_override" and self.analyst_approved:
            _PUBLISHABLE_METHODS.add("manual_override")
        if self.forecast_method not in _PUBLISHABLE_METHODS:
            return False
        # Even within a publishable method, all rows must be high confidence
        return all(
            row.confidence == "high"
            for row in self.forecast_rows
        )

    @property
    def fcfe_block_reason(self) -> str | None:
        """Human-readable reason why FCFE is blocked, or None if publishable."""
        if self.is_fcfe_publishable:
            return None
        method_reasons = {
            "target_debt_ratio": (
                "Debt forecast uses historical_median_debt as proxy — "
                "net_borrowing is NOT sourced from CFS or maturity schedule. "
                "Analyst must provide approved debt path before publishing FCFE."
            ),
            "balance_sheet_delta": (
                "Net borrowing approximated from balance-sheet delta (medium confidence). "
                "FCFE requires high-confidence debt schedule (direct CFS data or analyst approval)."
            ),
            "manual_override": (
                "Debt path is a manual analyst override — pending approval. "
                "FCFE blocked until debt_schedule.status = approved."
            ),
            "missing": (
                "No debt schedule available — FCFE cannot be computed. "
                "Source historical borrowing/repayment data from CFS."
            ),
        }
        return method_reasons.get(
            self.forecast_method,
            f"Debt schedule method '{self.forecast_method}' does not qualify for FCFE publication.",
        )

    def net_borrowing_schedule(self) -> dict[str, float | None]:
        """Return {label: net_borrowing | None} for forecast years.

        Returns None for rows without a valid net_borrowing value, so callers
        can distinguish 'zero net borrowing' from 'net borrowing unknown'.
        Use net_borrowing_schedule_safe() for a fallback-to-zero version.
        """
        return {
            row.label: row.net_borrowing
            for row in self.forecast_rows
        }

    def net_borrowing_schedule_safe(self) -> dict[str, float]:
        """Return {label: net_borrowing} with 0.0 fallback (for diagnostics only).

        WARNING: Do NOT use in FCFE computation. Use net_borrowing_schedule()
        and check is_fcfe_publishable before trusting these values.
        """
        return {
            row.label: (row.net_borrowing or 0.0)
            for row in self.forecast_rows
        }

    @property
    def status(self) -> Literal["approved", "high", "medium", "low", "blocked"]:
        """Artifact-level status for pipeline gate decisions.

        approved  — direct_cash_flow all-high (CFS-sourced, highest trust)
        high      — same criteria; alias for approved in absence of analyst sign-off field
        medium    — balance_sheet_delta or manual_override (model approximation)
        low       — target_debt_ratio (median-anchored model)
        blocked   — missing data; FCFE cannot proceed
        """
        if self.forecast_method in ("direct_cash_flow", "zero_debt_policy"):
            if all(r.confidence == "high" for r in self.forecast_rows):
                return "high"
        if self.forecast_method == "manual_override" and self.analyst_approved:
            if all(r.confidence == "high" for r in self.forecast_rows):
                return "approved"
        if self.forecast_method in ("balance_sheet_delta", "manual_override"):
            return "medium"
        if self.forecast_method == "target_debt_ratio":
            return "low"
        return "blocked"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "forecast_method": self.forecast_method,
            "analyst_approved": self.analyst_approved,
            "status": self.status,
            "is_fcfe_publishable": self.is_fcfe_publishable,
            "fcfe_block_reason": self.fcfe_block_reason,
            "historical_rows": [r.to_dict() for r in self.historical_rows],
            "forecast_rows": [r.to_dict() for r in self.forecast_rows],
            "warnings": self.warnings,
        }


def _check_debt_identity(
    beginning: float | None,
    new_borrowing: float | None,
    debt_repayment: float | None,
    ending: float | None,
    tol: float = 0.1,
) -> bool | None:
    """Validate: ending == beginning + new_borrowing - debt_repayment.

    Returns True if identity holds within tol VND bn, False if violated,
    None if any input is missing (cannot check).
    """
    if any(v is None for v in [beginning, new_borrowing, debt_repayment, ending]):
        return None
    expected = beginning + new_borrowing - debt_repayment  # type: ignore[operator]
    return abs(expected - ending) < tol  # type: ignore[operator]


def _compute_average_debt(
    beginning: float | None,
    ending: float | None,
) -> float | None:
    """Average debt = (beginning + ending) / 2. Returns None if either input missing."""
    if beginning is None or ending is None:
        return None
    return (beginning + ending) / 2.0


def _get(table: FactTable, key: str, period: str) -> float | None:
    entry = table.get(key, {}).get(period)
    if entry is None:
        return None
    return entry_value(entry)


def interest_bearing_debt(fact_table: FactTable, period: str) -> float | None:
    """Normalize interest-bearing debt from available fact_table fields.

    Priority:
    1. total_debt.ending  (already normalized by normalizer)
    2. short_term_borrowings.ending + long_term_borrowings.ending
    3. short_term_debt.ending + long_term_debt.ending  (vnstock alias group)
    """
    total_debt = _get(fact_table, "total_debt.ending", period)
    if total_debt is not None:
        return total_debt

    # Primary component keys
    st = _get(fact_table, "short_term_borrowings.ending", period)
    lt = _get(fact_table, "long_term_borrowings.ending", period)
    if st is not None or lt is not None:
        return (st or 0.0) + (lt or 0.0)

    # Alias component keys (vnstock normalizer variant)
    st_alias = _get(fact_table, "short_term_debt.ending", period)
    lt_alias = _get(fact_table, "long_term_debt.ending", period)
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
        new_borrow = _get(fact_table, "proceeds_from_borrowings.total", period)
        repayment = _get(fact_table, "repayment_of_borrowings.total", period)
        ie = _get(fact_table, "interest_expense.total", period)

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

        debt_repayment_val = abs(repayment) if repayment is not None else None
        avg_debt = _compute_average_debt(beginning_debt, ending_debt)
        identity_ok = _check_debt_identity(beginning_debt, new_borrow, debt_repayment_val, ending_debt)

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
            mandatory_debt_repayment=debt_repayment_val,
            debt_repayment=debt_repayment_val,
            net_borrowing=net_borrow,
            average_debt=avg_debt,
            interest_expense=abs(ie) if ie is not None else None,
            implied_cost_of_debt=implied_cod,
            identity_check_passes=identity_ok,
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
    manual_debt_path_approved: bool = False,
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
        confidence: Literal["high", "medium", "low"] = "high" if manual_debt_path_approved else "medium"
        warning = (
            "Debt path provided by analyst and approved for FCFE publication."
            if manual_debt_path_approved
            else "Debt path provided by analyst - pending approval."
        )
        for label, year in zip(forecast_labels, forecast_years):
            ending = (manual_debt_path or {}).get(label, prev_debt or 0.0)
            nb = (ending - (prev_debt or 0.0)) if prev_debt is not None else None
            avg = _compute_average_debt(prev_debt, ending)
            rows.append(DebtScheduleRow(
                year=year, label=label,
                beginning_interest_bearing_debt=prev_debt,
                ending_interest_bearing_debt=ending,
                net_borrowing=nb,
                average_debt=avg,
                identity_check_passes=None,  # no new_borrowing/repayment split available
                method="manual_override", confidence=confidence,
                warning=warning,
            ))
            prev_debt = ending
        if manual_debt_path_approved:
            warnings.append("Debt forecast uses analyst-approved manual_override path for FCFE publication.")
        else:
            warnings.append("Debt forecast uses manual_override path - must be approved before publishing.")
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
                new_borrowing=0.0,
                mandatory_debt_repayment=0.0,
                debt_repayment=0.0,
                net_borrowing=0.0,
                average_debt=0.0,
                identity_check_passes=True,
                method="zero_debt_policy", confidence="high",
                warning=None,
            ))
        warnings.append("Zero-debt policy applied: historical interest-bearing debt is negligible.")
        return rows, "zero_debt_policy", warnings

    # Case 3: Target debt ratio — use median of historical ending debt as stable level
    # NOTE: net_borrowing here is balance_sheet_delta (ending - beginning), NOT
    # new_borrowing - debt_repayment. This blocks is_fcfe_publishable by design.
    if all_hist_debts:
        median_debt = statistics.median(all_hist_debts)
        rows = []
        prev_debt = last_ending if last_ending is not None else median_debt
        for label, year in zip(forecast_labels, forecast_years):
            ending = median_debt
            nb = ending - prev_debt
            avg = _compute_average_debt(prev_debt, ending)
            rows.append(DebtScheduleRow(
                year=year, label=label,
                beginning_interest_bearing_debt=prev_debt,
                ending_interest_bearing_debt=ending,
                net_borrowing=nb,
                average_debt=avg,
                identity_check_passes=None,  # new_borrowing/repayment split unknown
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
            average_debt=None,
            identity_check_passes=None,
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
    manual_debt_path_approved: bool = False,
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
        manual_debt_path_approved=manual_debt_path_approved,
    )
    return DebtSchedule(
        ticker=ticker,
        historical_rows=historical_rows,
        forecast_rows=forecast_rows,
        forecast_method=method,
        warnings=warnings,
        analyst_approved=manual_debt_path_approved and method == "manual_override",
    )
