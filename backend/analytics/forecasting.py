"""Deterministic financial forecast engine — driver-based 3-statement model.

Generates 5-year income statement + balance sheet projections from historical
canonical facts using driver-based methods.

Revenue driver:   historical CAGR (capped ±25%), overridable
Cost drivers:     ratio-to-revenue (historical median margin)
Interest expense: average_debt × cost_of_debt (not revenue-based)
  — avg_debt sourced from debt_schedule.py per forecast year
  — cost_of_debt = median historical implied_cost_of_debt from debt_schedule
Debt roll-forward: delegated entirely to debt_schedule.py
Retained earnings: delegated entirely to dividend_schedule.retained_earnings_schedule()

Two-pass structure:
  Pass 1 (loop): income statement → net_income per year
  Post-loop:     build dividend_schedule → retained_earnings_schedule
  Pass 2 (loop): equity += retained_earnings; update BVPS, total_assets, dividend fields

No LLM involvement — all arithmetic is explicit Python.

Output artifact: ForecastArtifact (to_dict() → JSON-serializable)
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from backend.analytics.tax_policy import TaxPolicy, build_tax_policy
from backend.analytics.dividend_schedule import build_dividend_schedule
from backend.analytics.debt_schedule import build_debt_schedule, DebtSchedule, interest_bearing_debt
from backend.analytics.shares import explicit_shares_mn
from backend.analytics.working_capital_schedule import (
    build_working_capital_schedule,
    WorkingCapitalSchedule,
)
from backend.analytics.share_rollforward import CorporateAction, build_share_rollforward, ShareRollForward
from backend.analytics.cash_sweep import (
    CashSweepArtifact,
    MinimumCashPolicy,
    build_cash_sweep_artifact,
)

from backend.analytics._entry import entry_value
from backend.facts.normalizer import FactTable

_FORECAST_YEARS = [2026, 2027, 2028, 2029, 2030]
_MAX_REVENUE_GROWTH = 0.25
_MIN_REVENUE_GROWTH = -0.10


def _get(table: FactTable, key: str, period: str) -> float | None:
    entry = table.get(key, {}).get(period)
    if entry is None:
        return None
    return entry_value(entry)


def _cagr(start: float, end: float, years: int) -> float | None:
    if years <= 0 or start is None or end is None or start <= 0:
        return None
    return (end / start) ** (1.0 / years) - 1.0


def _median_ratio(
    numerator_key: str,
    denominator_key: str,
    table: FactTable,
    periods: list[str],
) -> float | None:
    """Compute median of numerator/denominator across available FY periods."""
    ratios = []
    for p in periods:
        num = _get(table, numerator_key, p)
        den = _get(table, denominator_key, p)
        if num is not None and den is not None and den != 0:
            ratios.append(num / den)
    if not ratios:
        return None
    return statistics.median(ratios)


def reconcile_pnl(row: dict[str, float], tol: float = 0.01) -> dict[str, Any]:
    """Closed-form P&L reconciliation (audit NUMERIC-03).

    Every line item is explicit; EBIT, PBT and net income are recomputed so the
    table is internally consistent (no large unexplained gap between EBIT,
    interest, tax and net income).

    Sign convention: revenue positive; cogs, selling, admin, financial_expense,
    tax are negative; financial_income, other positive.

        EBIT = revenue + cogs + selling + admin
        PBT  = EBIT + financial_income + financial_expense + other
        NI   = PBT + tax

    Returns {ebit, pbt, net_income, reconciles}. ``reconciles`` is True when the
    recomputed net income matches a supplied ``net_income`` (if any) within tol.
    """
    ebit = (
        row.get("revenue", 0.0)
        + row.get("cogs", 0.0)
        + row.get("selling", 0.0)
        + row.get("admin", 0.0)
    )
    pbt = (
        ebit
        + row.get("financial_income", 0.0)
        + row.get("financial_expense", 0.0)
        + row.get("other", 0.0)
    )
    net_income = pbt + row.get("tax", 0.0)
    reported = row.get("net_income")
    if reported is None:
        reconciles = True
    else:
        denom = abs(reported) if reported else 1.0
        reconciles = abs(net_income - reported) / denom <= tol
    return {"ebit": ebit, "pbt": pbt, "net_income": net_income, "reconciles": reconciles}


@dataclass
class ForecastAssumptions:
    revenue_growth_override: float | None = None   # None → use historical CAGR
    gross_margin_override: float | None = None      # None → use historical median
    net_margin_override: float | None = None        # None → derive from other lines
    sga_to_revenue_override: float | None = None
    tax_rate_override: float | None = None
    capex_to_revenue_override: float | None = None
    depreciation_to_revenue_override: float | None = None
    dividend_payout_ratio_override: float | None = None  # None → use historical median payout
    cost_of_debt_override: float | None = None      # None → use historical implied CoD median
    manual_debt_path: dict[str, float] | None = None
    debt_schedule_approved: bool = False
    debt_policy_method: str | None = None
    # PDF-disclosed borrowing plan [{year, amount(net borrowing tỷ VND), ...}] from the
    # annual report. When present (and no explicit manual_debt_path), it is rolled into
    # an approved manual_debt_path — the company's own stated plan is authoritative.
    pdf_debt_plan: list[dict] | None = None
    corporate_actions: list[CorporateAction] | None = None
    corporate_action_status: str | None = None
    assumption_status: str = "default_unapproved"   # or "analyst_approved"


@dataclass
class ForecastYear:
    year: int
    label: str          # e.g. "2026F"
    revenue: float | None
    cogs: float | None
    gross_profit: float | None
    gross_margin: float | None
    sga: float | None
    ebit: float | None
    ebit_margin: float | None
    depreciation: float | None
    ebitda: float | None
    interest_expense: float | None
    profit_before_tax: float | None
    tax_expense: float | None
    net_income: float | None
    net_margin: float | None
    capex: float | None
    # Balance sheet highlights
    total_assets: float | None
    equity: float | None
    total_debt: float | None        # = ending_debt (backward-compatible alias)
    other_liabilities: float | None
    # Per-share
    eps: float | None
    bvps: float | None
    cash: float | None = None       # ending cash from cash sweep, VND bn
    # Non-operating line (PBT gap): dividends from subs, forex, financial income, etc.
    other_items: float | None = None
    # Debt detail — sourced from debt_schedule per forecast year
    beginning_debt: float | None = None
    ending_debt: float | None = None
    net_borrowing: float | None = None
    cost_of_debt: float | None = None   # rate applied to avg_debt for interest_expense
    # Dividend / retained earnings — sourced from dividend_schedule per forecast year
    cash_dividend: float | None = None
    payout_ratio: float | None = None
    retained_earnings_addition: float | None = None
    # Working capital — sourced from working_capital_schedule per forecast year
    delta_nwc: float | None = None              # positive = cash consumed by NWC increase
    net_working_capital: float | None = None    # AR + Inventory - AP
    # Diluted shares — sourced from share_rollforward per forecast year
    diluted_shares: float | None = None         # mn shares, after ESOP/placement/buyback


@dataclass
class ForecastArtifact:
    ticker: str
    historical_periods: list[str]
    forecast_periods: list[str]
    assumptions: ForecastAssumptions
    revenue_cagr: float | None
    drivers: dict[str, Any]
    forecast_years: list[ForecastYear]
    warnings: list[str] = field(default_factory=list)
    tax_policy: TaxPolicy | None = None
    dividend_schedule: Any | None = None   # DividendSchedule (avoid circular import)
    debt_schedule: DebtSchedule | None = None
    working_capital_schedule: WorkingCapitalSchedule | None = None
    share_rollforward: ShareRollForward | None = None
    cash_sweep_artifact: CashSweepArtifact | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "historical_periods": self.historical_periods,
            "forecast_periods": self.forecast_periods,
            "revenue_cagr_historical": round(self.revenue_cagr, 4) if self.revenue_cagr else None,
            "drivers": self.drivers,
            "assumption_status": self.assumptions.assumption_status,
            "forecast_years": [
                {
                    "year": fy.year,
                    "label": fy.label,
                    "revenue": round(fy.revenue, 1) if fy.revenue is not None else None,
                    "cogs": round(fy.cogs, 1) if fy.cogs is not None else None,
                    "gross_profit": round(fy.gross_profit, 1) if fy.gross_profit is not None else None,
                    "gross_margin": round(fy.gross_margin, 4) if fy.gross_margin is not None else None,
                    "sga": round(fy.sga, 1) if fy.sga is not None else None,
                    "ebit": round(fy.ebit, 1) if fy.ebit is not None else None,
                    "ebit_margin": round(fy.ebit_margin, 4) if fy.ebit_margin is not None else None,
                    "depreciation": round(fy.depreciation, 1) if fy.depreciation is not None else None,
                    "ebitda": round(fy.ebitda, 1) if fy.ebitda is not None else None,
                    "interest_expense": round(fy.interest_expense, 1) if fy.interest_expense is not None else None,
                    "other_items": round(fy.other_items, 1) if fy.other_items is not None else None,
                    "profit_before_tax": round(fy.profit_before_tax, 1) if fy.profit_before_tax is not None else None,
                    "tax_expense": round(fy.tax_expense, 1) if fy.tax_expense is not None else None,
                    "net_income": round(fy.net_income, 1) if fy.net_income is not None else None,
                    "net_margin": round(fy.net_margin, 4) if fy.net_margin is not None else None,
                    "capex": round(fy.capex, 1) if fy.capex is not None else None,
                    "total_assets": round(fy.total_assets, 1) if fy.total_assets is not None else None,
                    "equity": round(fy.equity, 1) if fy.equity is not None else None,
                    "total_debt": round(fy.total_debt, 1) if fy.total_debt is not None else None,
                    "cash": round(fy.cash, 1) if fy.cash is not None else None,
                    "other_liabilities": round(fy.other_liabilities, 1) if fy.other_liabilities is not None else None,
                    "eps": round(fy.eps, 0) if fy.eps is not None else None,
                    "bvps": round(fy.bvps, 0) if fy.bvps is not None else None,
                    # Debt detail
                    "beginning_debt": round(fy.beginning_debt, 1) if fy.beginning_debt is not None else None,
                    "ending_debt": round(fy.ending_debt, 1) if fy.ending_debt is not None else None,
                    "net_borrowing": round(fy.net_borrowing, 1) if fy.net_borrowing is not None else None,
                    "cost_of_debt": round(fy.cost_of_debt, 4) if fy.cost_of_debt is not None else None,
                    # Dividend detail
                    "cash_dividend": round(fy.cash_dividend, 1) if fy.cash_dividend is not None else None,
                    "payout_ratio": round(fy.payout_ratio, 4) if fy.payout_ratio is not None else None,
                    "retained_earnings_addition": round(fy.retained_earnings_addition, 1) if fy.retained_earnings_addition is not None else None,
                    # Working capital
                    "delta_nwc": round(fy.delta_nwc, 2) if fy.delta_nwc is not None else None,
                    "net_working_capital": round(fy.net_working_capital, 1) if fy.net_working_capital is not None else None,
                    # Diluted shares
                    "diluted_shares": round(fy.diluted_shares, 3) if fy.diluted_shares is not None else None,
                }
                for fy in self.forecast_years
            ],
            "warnings": self.warnings,
            "tax_policy": self.tax_policy.to_dict() if self.tax_policy else None,
            "dividend_schedule": self.dividend_schedule.to_dict() if self.dividend_schedule else None,
            "debt_schedule": self.debt_schedule.to_dict() if self.debt_schedule else None,
            "working_capital_schedule": self.working_capital_schedule.to_dict() if self.working_capital_schedule else None,
            "share_rollforward": self.share_rollforward.to_dict() if self.share_rollforward else None,
            "cash_sweep_artifact": self.cash_sweep_artifact.to_dict() if self.cash_sweep_artifact else None,
        }


def run_forecast(
    ticker: str,
    fact_table: FactTable,
    forecast_years: list[int] | None = None,
    n_years: int | None = None,
    assumptions: ForecastAssumptions | None = None,
    shares_mn: float | None = None,
) -> ForecastArtifact:
    """Run deterministic driver-based income statement + balance sheet forecast.

    Args:
        forecast_years: Explicit list of calendar years to forecast (e.g. [2026, 2027, 2028]).
        n_years: Simple count of years to forecast (auto-generates years from latest_fy + 1).
            Ignored when forecast_years is also provided.

    Interest expense uses avg_debt × cost_of_debt (driver-based), not revenue ratios.
    Debt roll-forward is sourced from debt_schedule.py.
    Retained earnings are sourced from dividend_schedule.retained_earnings_schedule().
    """
    if assumptions is None:
        assumptions = ForecastAssumptions()

    warnings: list[str] = []

    fy_periods = sorted(
        p for p in {p for vals in fact_table.values() for p in vals} if p.endswith("FY")
    )
    if not fy_periods:
        return ForecastArtifact(
            ticker=ticker, historical_periods=[], forecast_periods=[],
            assumptions=assumptions, revenue_cagr=None, drivers={},
            forecast_years=[], warnings=["No FY periods available for forecast"],
        )

    # Resolve forecast year list
    if forecast_years is None:
        if n_years is not None and n_years > 0:
            latest_cal = int(fy_periods[-1].replace("FY", ""))
            forecast_years = list(range(latest_cal + 1, latest_cal + 1 + n_years))
        else:
            forecast_years = _FORECAST_YEARS

    # Pre-compute forecast labels (needed by debt_schedule before the main loop)
    forecast_labels_order = [f"{y}F" for y in forecast_years]

    # ── Historical revenue CAGR ────────────────────────────────────────────
    rev_vals = [_get(fact_table, "revenue.net", p) for p in fy_periods]
    rev_vals = [v for v in rev_vals if v is not None]

    if assumptions.revenue_growth_override is not None:
        rev_growth = assumptions.revenue_growth_override
        revenue_cagr = None
    elif len(rev_vals) >= 2:
        revenue_cagr = _cagr(rev_vals[0], rev_vals[-1], len(rev_vals) - 1)
        rev_growth = max(_MIN_REVENUE_GROWTH, min(_MAX_REVENUE_GROWTH, revenue_cagr or 0.05))
        if revenue_cagr is not None and revenue_cagr != rev_growth:
            warnings.append(
                f"Revenue CAGR {revenue_cagr:.1%} capped to {rev_growth:.1%} for forecast"
            )
    else:
        rev_growth = 0.05
        revenue_cagr = None
        warnings.append("Insufficient revenue history — assuming 5% growth")

    # ── Historical margin drivers ──────────────────────────────────────────
    gross_margin = (
        assumptions.gross_margin_override
        or _median_ratio("gross_profit.total", "revenue.net", fact_table, fy_periods)
    )
    if gross_margin is None:
        gross_margin = 0.40
        warnings.append("No gross margin history — using default 40%")

    sga_ratios = []
    for p in fy_periods:
        sga = _get(fact_table, "sga.total", p)
        rev = _get(fact_table, "revenue.net", p)
        if sga is not None and rev and rev > 0:
            sga_ratios.append(abs(sga) / rev)
    sga_to_rev = (
        assumptions.sga_to_revenue_override
        or (statistics.median(sga_ratios) if sga_ratios else 0.20)
    )

    dep_to_rev = (
        assumptions.depreciation_to_revenue_override
        or _median_ratio("depreciation.total", "revenue.net", fact_table, fy_periods)
        or 0.04
    )

    capex_ratios = []
    for p in fy_periods:
        capex = _get(fact_table, "capex.total", p)
        rev = _get(fact_table, "revenue.net", p)
        if capex is not None and rev and rev > 0:
            capex_ratios.append(abs(capex) / rev)
    capex_to_rev = (
        assumptions.capex_to_revenue_override
        or (statistics.median(capex_ratios) if capex_ratios else 0.03)
    )

    # Effective tax rate — unified TaxPolicy module
    tax_policy = build_tax_policy(
        ticker=ticker,
        fact_table=fact_table,
        fy_periods=fy_periods,
        valuation_year=int(fy_periods[-1].replace("FY", "")) if fy_periods else 2025,
        manual_override=assumptions.tax_rate_override,
    )
    tax_rate = tax_policy.effective_tax_rate
    if tax_policy.excluded_observations:
        warnings.append(
            f"TaxPolicy: {len(tax_policy.excluded_observations)} FY period(s) excluded "
            f"from tax rate calculation — see tax_policy.excluded_observations"
        )

    # Interest/revenue ratio — kept only as fallback when no debt data is available
    interest_ratios = []
    for p in fy_periods:
        ie = _get(fact_table, "interest_expense.total", p)
        rev = _get(fact_table, "revenue.net", p)
        if ie is not None and rev and rev > 0:
            interest_ratios.append(abs(ie) / rev)
    interest_to_rev_fallback = statistics.median(interest_ratios) if interest_ratios else 0.01

    # ── Other items driver (PBT gap = PBT - EBIT - interest) ──────────────
    other_items_ratios: list[float] = []
    for p in fy_periods:
        pbt_h = _get(fact_table, "profit_before_tax.total", p)
        gp_h  = _get(fact_table, "gross_profit.total", p)
        sga_h = _get(fact_table, "sga.total", p)
        ie_h  = _get(fact_table, "interest_expense.total", p)
        rev_h = _get(fact_table, "revenue.net", p)
        if all(v is not None for v in [pbt_h, gp_h, sga_h, ie_h, rev_h]) and rev_h > 0:
            ebit_model = gp_h + sga_h
            gap = pbt_h - (ebit_model + ie_h)
            other_items_ratios.append(gap / rev_h)

    other_items_to_rev: float = (
        round(statistics.median(other_items_ratios), 4)
        if other_items_ratios else 0.0
    )
    if other_items_ratios and abs(other_items_to_rev) > 0.001:
        min_r = min(other_items_ratios)
        max_r = max(other_items_ratios)
        warnings.append(
            f"Non-operating items (PBT gap) detected: ranged from "
            f"{min_r:.1%} to {max_r:.1%} of revenue; median {other_items_to_rev:.1%} applied to forecast."
        )

    # ── Starting balance sheet values ─────────────────────────────────────
    latest_fy = fy_periods[-1]
    start_assets = _get(fact_table, "total_assets.ending", latest_fy) or 0.0
    start_equity = _get(fact_table, "equity.parent", latest_fy) or 0.0
    start_debt = _get(fact_table, "total_debt.ending", latest_fy) or 0.0
    # Non-debt liabilities: carry forward as constant (trade payables, accruals, etc.)
    other_liabilities = max(0.0, start_assets - start_equity - start_debt)

    # Shares outstanding. Use explicit share-count facts only; EPS-implied shares
    # are too unstable for forecast EPS/BVPS and target-price arithmetic.
    if shares_mn is None:
        shares_mn = explicit_shares_mn(fact_table, latest_fy)
        if shares_mn is None:
            warnings.append(
                "Shares outstanding fact missing — forecast EPS/BVPS omitted to avoid EPS-implied share-count error."
            )

    # ── Convergence note ──────────────────────────────────────────────────────
    # This forecast is single-pass (no iteration). The feedback loop
    # Debt → Interest → PBT → Tax → NI → CFO → Cash → MinCash → Debt
    # is NOT resolved. For zero-debt or stable-debt companies this error is
    # negligible. For companies with large net borrowing or mandatory minimum-
    # cash triggers, the interest expense estimate may require up to N iterations
    # to converge (plan §5 — TODO: implement convergence loop, max_iterations=10,
    # tol=0.1 VND bn on ending_debt and interest_expense).

    # ── Build debt schedule (before main loop — determines interest expense) ──
    manual_debt_path = assumptions.manual_debt_path
    manual_debt_path_approved = assumptions.debt_schedule_approved
    # PDF-disclosed borrowing plan → approved manual debt path (authoritative source).
    # Lets FCFE publish for a company that still carries debt but has stated a plan,
    # without inventing a path (debt_plan_to_manual_path returns None if unusable).
    if manual_debt_path is None and assumptions.pdf_debt_plan:
        from backend.analytics.debt_schedule import debt_plan_to_manual_path

        pdf_path = debt_plan_to_manual_path(
            assumptions.pdf_debt_plan,
            interest_bearing_debt(fact_table, latest_fy),
            forecast_labels_order,
            forecast_years,
        )
        if pdf_path is not None:
            manual_debt_path = pdf_path
            manual_debt_path_approved = True
            warnings.append(
                "DebtPolicy: forecast debt path sourced from the company's disclosed "
                "borrowing plan (annual report) — treated as approved for FCFE."
            )
    if (
        manual_debt_path is None
        and assumptions.debt_policy_method == "cfs_net_borrowing"
        and assumptions.debt_schedule_approved
    ):
        has_cfs_borrowing = any(
            _get(fact_table, "proceeds_from_borrowings.total", period) is not None
            and _get(fact_table, "repayment_of_borrowings.total", period) is not None
            for period in fy_periods
        )
        total_debt_latest = _get(fact_table, "total_debt.ending", latest_fy)
        short_debt_latest = _get(fact_table, "short_term_debt.ending", latest_fy)
        long_debt_latest = _get(fact_table, "long_term_debt.ending", latest_fy)
        if total_debt_latest is not None:
            latest_debt = total_debt_latest
        elif short_debt_latest is not None or long_debt_latest is not None:
            latest_debt = (short_debt_latest or 0.0) + (long_debt_latest or 0.0)
        else:
            latest_debt = None
        if has_cfs_borrowing and latest_debt is not None:
            manual_debt_path = {label: latest_debt for label in forecast_labels_order}
            warnings.append(
                "DebtPolicy: approved cfs_net_borrowing policy applied; forecast debt path "
                "is anchored to latest reported interest-bearing debt."
            )
        else:
            warnings.append(
                "DebtPolicy: cfs_net_borrowing requested but historical borrowing/repayment "
                "facts or latest debt balance are missing; FCFE remains draft-only."
            )

    debt_sched = build_debt_schedule(
        ticker=ticker,
        fact_table=fact_table,
        fy_periods=fy_periods,
        forecast_labels=forecast_labels_order,
        forecast_years=forecast_years,
        manual_debt_path=manual_debt_path,
        manual_debt_path_approved=manual_debt_path_approved,
    )
    # NOTE: An approval flag alone must NOT upgrade a model-generated debt path
    # (e.g. target_debt_ratio) into an "approved manual_override". Approval is only
    # meaningful against a concrete analyst-supplied manual_debt_path. Laundering the
    # model's own output back in as approved fabricated an FCFE-publishable debt path
    # with no source — it bypassed the high-confidence/HITL gate. Removed by design:
    # without a real manual_debt_path, the schedule stays target_debt_ratio (low) and
    # FCFE remains correctly blocked.
    debt_row_by_label = {row.label: row for row in debt_sched.forecast_rows}
    for w in debt_sched.warnings:
        warnings.append(f"[DebtSchedule] {w}")

    if not debt_sched.is_fcfe_publishable:
        warnings.append(
            "[ForecastWarning] Interest expense is single-pass (no convergence iteration). "
            f"Debt method = '{debt_sched.forecast_method}' — FCFE is blocked; "
            "analyst must supply approved debt path before publishing."
        )

    # ── Derive cost of debt ────────────────────────────────────────────────
    hist_cods = [
        r.implied_cost_of_debt
        for r in debt_sched.historical_rows
        if r.implied_cost_of_debt is not None
    ]
    if assumptions.cost_of_debt_override is not None:
        cost_of_debt = assumptions.cost_of_debt_override
        cod_method = "manual_override"
    elif hist_cods:
        cost_of_debt = statistics.median(hist_cods)
        cod_method = "historical_implied_cod"
    else:
        cost_of_debt = interest_to_rev_fallback
        cod_method = "fallback_interest_to_revenue"
        warnings.append(
            "Cost of debt not derivable from debt schedule (no historical interest/debt pairs). "
            "Falling back to interest_expense/revenue ratio as proxy. Interest expense confidence: low."
        )

    # ── Store drivers ──────────────────────────────────────────────────────
    drivers = {
        "revenue_growth": {y: round(rev_growth, 4) for y in forecast_years},
        "gross_margin": {"method": "historical_median", "value": round(gross_margin, 4)},
        "sga_to_revenue": {"method": "historical_median", "value": round(sga_to_rev, 4)},
        "depreciation_to_revenue": {"method": "historical_median", "value": round(dep_to_rev, 4)},
        "capex_to_revenue": {"method": "historical_median", "value": round(capex_to_rev, 4)},
        "effective_tax_rate": {"method": "historical_median", "value": round(tax_rate, 4)},
        "cost_of_debt": {"method": cod_method, "value": round(cost_of_debt, 4)},
        "other_items_to_revenue": {"method": "historical_median", "value": other_items_to_rev},
    }

    # ── PASS 1: Forecast income statement per year ────────────────────────
    latest_rev = _get(fact_table, "revenue.net", latest_fy) or 0.0
    current_rev = latest_rev

    forecast_year_objects: list[ForecastYear] = []
    forecast_period_labels: list[str] = []
    forecast_net_incomes: dict[str, float] = {}

    for year in forecast_years:
        label = f"{year}F"
        forecast_period_labels.append(label)

        # Revenue → EBIT
        revenue = current_rev * (1 + rev_growth)
        cogs = -revenue * (1 - gross_margin)
        gross_profit = revenue + cogs
        sga = -revenue * sga_to_rev
        depreciation = revenue * dep_to_rev
        ebit = gross_profit + sga
        ebitda = ebit + depreciation
        ebit_margin = ebit / revenue if revenue else None

        # Debt levels for this year (from pre-built debt schedule)
        debt_row = debt_row_by_label.get(label)
        beginning_debt_y: float | None = (
            debt_row.beginning_interest_bearing_debt if debt_row else start_debt
        )
        ending_debt_y: float | None = (
            debt_row.ending_interest_bearing_debt if debt_row else start_debt
        )
        net_borrowing_y: float | None = (
            debt_row.net_borrowing if debt_row else 0.0
        )

        # Average debt → interest expense (driver-based)
        if beginning_debt_y is not None and ending_debt_y is not None:
            avg_debt: float | None = (beginning_debt_y + ending_debt_y) / 2.0
        elif ending_debt_y is not None:
            avg_debt = ending_debt_y
        elif beginning_debt_y is not None:
            avg_debt = beginning_debt_y
        else:
            avg_debt = None

        if avg_debt is not None:
            # Negative sign convention: interest_expense is a cost
            interest_expense = -avg_debt * cost_of_debt
            cod_applied = cost_of_debt
        else:
            # Fallback when no debt data at all
            interest_expense = -revenue * interest_to_rev_fallback
            cod_applied = None

        # Write cost_of_debt + interest_expense back to debt schedule row so
        # the artifact is self-contained: ie = avg_debt × cost_of_debt auditable.
        if debt_row is not None and cod_applied is not None:
            debt_row.cost_of_debt = cod_applied
            debt_row.interest_expense = abs(interest_expense)

        other_items = revenue * other_items_to_rev
        pbt = ebit + interest_expense + other_items
        tax_expense = -max(0, pbt) * tax_rate
        net_income = pbt + tax_expense
        net_margin = net_income / revenue if revenue else None

        capex = -revenue * capex_to_rev
        forecast_net_incomes[label] = net_income

        eps = (net_income * 1_000) / shares_mn if shares_mn else None

        # equity/total_assets/bvps are placeholder — updated in Pass 2
        forecast_year_objects.append(ForecastYear(
            year=year,
            label=label,
            revenue=revenue,
            cogs=cogs,
            gross_profit=gross_profit,
            gross_margin=gross_margin,
            sga=sga,
            ebit=ebit,
            ebit_margin=ebit_margin,
            depreciation=depreciation,
            ebitda=ebitda,
            interest_expense=interest_expense,
            profit_before_tax=pbt,
            tax_expense=tax_expense,
            net_income=net_income,
            net_margin=net_margin,
            capex=capex,
            total_assets=None,
            equity=None,
            total_debt=ending_debt_y,
            cash=None,
            other_liabilities=other_liabilities,
            eps=eps,
            bvps=None,
            other_items=other_items,
            beginning_debt=beginning_debt_y,
            ending_debt=ending_debt_y,
            net_borrowing=net_borrowing_y,
            cost_of_debt=cod_applied,
        ))

        current_rev = revenue

    # ── Build dividend schedule from Pass 1 net incomes ───────────────────
    div_schedule = build_dividend_schedule(
        ticker=ticker,
        fact_table=fact_table,
        fy_periods=fy_periods,
        forecast_net_incomes=forecast_net_incomes,
        manual_payout_ratio=assumptions.dividend_payout_ratio_override,
    )
    for w in div_schedule.warnings:
        warnings.append(f"[DividendSchedule] {w}")

    retained_sched = div_schedule.retained_earnings_schedule()
    div_row_by_label = {r.label: r for r in div_schedule.forecast_rows}

    # ── Build working capital schedule (uses Pass 1 revenues + COGS) ─────
    _rev_by_label  = {fy.label: fy.revenue for fy in forecast_year_objects if fy.revenue is not None}
    _cogs_by_label = {fy.label: fy.cogs    for fy in forecast_year_objects if fy.cogs is not None}
    wc_schedule = build_working_capital_schedule(
        ticker=ticker,
        fact_table=fact_table,
        fy_periods=fy_periods,
        forecast_labels=forecast_labels_order,
        forecast_revenues=_rev_by_label,
        forecast_cogs=_cogs_by_label,
    )
    for w in wc_schedule.warnings:
        warnings.append(f"[WorkingCapital] {w}")
    wc_by_label = {row.label: row for row in wc_schedule.forecast_rows}

    # ── Build share roll-forward ───────────────────────────────────────────
    sr = build_share_rollforward(
        ticker=ticker,
        fact_table=fact_table,
        fy_periods=fy_periods,
        forecast_labels=forecast_labels_order,
        corporate_actions=assumptions.corporate_actions,
        base_shares_override_mn=shares_mn,
        no_action_recorded=assumptions.corporate_action_status == "no_action_recorded",
    )
    for w in sr.warnings:
        warnings.append(f"[ShareRollForward] {w}")
    diluted_by_label = sr.diluted_shares_schedule()

    # ── Update forecast objects with NWC and diluted shares ───────────────
    for fy in forecast_year_objects:
        wc_row = wc_by_label.get(fy.label)
        if wc_row:
            fy.delta_nwc = wc_row.delta_nwc
            fy.net_working_capital = wc_row.net_working_capital

        diluted = diluted_by_label.get(fy.label)
        fy.diluted_shares = diluted
        # Prefer diluted shares for EPS when available
        if diluted and diluted > 0 and fy.net_income is not None:
            fy.eps = (fy.net_income * 1_000) / diluted

    # ── PASS 2: Update equity, BVPS, total_assets, dividend fields ────────
    running_equity = start_equity
    for fy in forecast_year_objects:
        retained = retained_sched.get(fy.label, fy.net_income or 0.0)
        running_equity += retained
        ending_debt = fy.ending_debt if fy.ending_debt is not None else 0.0
        fy.equity = running_equity
        fy.total_assets = running_equity + ending_debt + other_liabilities
        bvps_shares = fy.diluted_shares if (fy.diluted_shares and fy.diluted_shares > 0) else shares_mn
        fy.bvps = (running_equity / bvps_shares) * 1_000 if bvps_shares else None

        div_row = div_row_by_label.get(fy.label)
        if div_row:
            fy.cash_dividend = div_row.cash_dividend
            fy.payout_ratio = div_row.payout_ratio
            fy.retained_earnings_addition = div_row.retained_earnings_addition

    # ── Build CashSweepArtifact (approximate CFO = NI + D&A - ΔNWC) ─────────
    # CFO is approximated via the indirect method; no convergence loop is applied
    # (single-pass). This is sufficient for gate status checks but should not be
    # used to derive publishable net_borrowing unless all three of NI/D&A/ΔNWC
    # are driven by confirmed data.
    # TODO: Implement convergence loop (plan §5) — Debt→Interest→PBT→NI→CFO→Cash→Debt
    opening_cash_hist = _get(fact_table, "cash_and_equivalents.ending", latest_fy) or 0.0
    sweep_inputs: list[dict] = []
    opening_cash_iter = opening_cash_hist
    for fy in forecast_year_objects:
        if fy.net_income is None or fy.depreciation is None:
            break
        cfo_approx = fy.net_income + fy.depreciation - (fy.delta_nwc or 0.0)
        capex_pos = abs(fy.capex) if fy.capex is not None else 0.0
        dividends = (fy.cash_dividend or 0.0)

        debt_row_sweep = debt_row_by_label.get(fy.label)
        new_debt_y = debt_row_sweep.new_borrowing if debt_row_sweep and debt_row_sweep.new_borrowing is not None else 0.0
        debt_repaid_y = debt_row_sweep.debt_repayment if debt_row_sweep and debt_row_sweep.debt_repayment is not None else 0.0

        sweep_inputs.append({
            "year_label": fy.label,
            "opening_cash": opening_cash_iter,
            "cfo": cfo_approx,
            "capex_positive": capex_pos,
            "dividends_paid": dividends,
            "new_debt": new_debt_y,
            "debt_repaid": debt_repaid_y,
            # reported_ending_cash not available for forecast years → status = pending
        })
        # Advance opening cash for next year using computed ending cash
        opening_cash_iter = (
            opening_cash_iter
            + cfo_approx
            - capex_pos
            - dividends
            + new_debt_y
            - debt_repaid_y
        )

    min_cash_policy = MinimumCashPolicy()
    cash_sweep = build_cash_sweep_artifact(
        ticker=ticker,
        year_inputs=sweep_inputs,
        minimum_cash_policy=min_cash_policy,
    ) if sweep_inputs else None

    if cash_sweep:
        for w in cash_sweep.warnings:
            warnings.append(f"[CashSweep] {w}")
        cash_by_label = {
            result.year_label: result.computed_ending_cash
            for result in cash_sweep.year_results
        }
        for fy in forecast_year_objects:
            fy.cash = cash_by_label.get(fy.label)

    return ForecastArtifact(
        ticker=ticker,
        historical_periods=fy_periods,
        forecast_periods=forecast_period_labels,
        assumptions=assumptions,
        revenue_cagr=revenue_cagr,
        drivers=drivers,
        forecast_years=forecast_year_objects,
        warnings=warnings,
        tax_policy=tax_policy,
        dividend_schedule=div_schedule,
        debt_schedule=debt_sched,
        working_capital_schedule=wc_schedule,
        share_rollforward=sr,
        cash_sweep_artifact=cash_sweep,
    )
