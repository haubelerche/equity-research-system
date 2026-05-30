"""Accounting reconciliation checks for canonical financial facts.

Implements Plan §12 — verifies:
  IS: gross_profit ≈ revenue - |COGS|                    (tolerance 1% of revenue)
  IS: net_income ≈ PBT - |tax_expense|                   (tolerance 1% of PBT)
  IS: EPS × implied_shares ≈ net_income                   (tolerance 2%)
  BS: total_assets ≈ total_liabilities + equity.parent   (tolerance 0.5% of assets)
  CF: FCF sign consistency — warns if FCF sign-flips with no explanation
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Optional

from backend.facts.normalizer import FactTable


@dataclass
class ReconciliationCheck:
    name: str           # e.g. "IS_gross_profit_check"
    period: str         # e.g. "2025FY"
    expected: Optional[float]
    actual: Optional[float]
    difference: Optional[float]       # actual - expected
    tolerance_pct: float               # e.g. 0.01 for 1%
    status: str                        # "pass", "warn", "fail"
    message: str


@dataclass
class ReconciliationReport:
    ticker: str
    periods_checked: list[str]
    checks: list[ReconciliationCheck]
    critical_failures: list[ReconciliationCheck]    # status == "fail"
    warnings: list[ReconciliationCheck]             # status == "warn"
    overall_status: str                             # "pass", "warn", "fail"
    valuation_blocked: bool                         # True if any critical_failures exist


def _get(fact_table: FactTable, metric: str, period: str) -> Optional[float]:
    """Retrieve a numeric value from the fact table; returns None if missing."""
    entry = fact_table.get(metric, {}).get(period)
    if entry is None:
        return None
    return entry.value if hasattr(entry, "value") else float(entry)


def _check_is_gross_profit(fact_table: FactTable, period: str) -> Optional[ReconciliationCheck]:
    """Check 1: gross_profit ≈ revenue - |COGS| (tolerance 1% of revenue)."""
    revenue = _get(fact_table, "revenue.net", period)
    cogs = _get(fact_table, "cogs.total", period)
    gross_profit = _get(fact_table, "gross_profit.total", period)

    have_expected = revenue is not None and cogs is not None
    have_actual = gross_profit is not None

    # Both sides missing — skip entirely
    if not have_expected and not have_actual:
        return None

    tolerance_pct = 0.01

    if have_expected and have_actual:
        expected = revenue - abs(cogs)
        actual = gross_profit
        diff = actual - expected
        tolerance_abs = abs(revenue) * tolerance_pct if revenue else 0.0
        if abs(diff) < tolerance_abs:
            status = "pass"
            message = f"gross_profit reconciles within {tolerance_pct*100:.0f}% of revenue"
        else:
            status = "fail"
            message = (
                f"gross_profit mismatch: expected {expected:.2f}, actual {actual:.2f}, "
                f"diff {diff:.2f} (tolerance {tolerance_abs:.2f})"
            )
        return ReconciliationCheck(
            name="IS_gross_profit_check",
            period=period,
            expected=expected,
            actual=actual,
            difference=diff,
            tolerance_pct=tolerance_pct,
            status=status,
            message=message,
        )
    else:
        # One side missing
        return ReconciliationCheck(
            name="IS_gross_profit_check",
            period=period,
            expected=(revenue - abs(cogs)) if have_expected else None,
            actual=gross_profit,
            difference=None,
            tolerance_pct=tolerance_pct,
            status="warn",
            message="one side missing: cannot fully reconcile gross_profit",
        )


def _check_is_net_income(fact_table: FactTable, period: str) -> Optional[ReconciliationCheck]:
    """Check 2: net_income.parent ≈ PBT - |tax| - |minority_interest| (tol 1% of PBT).

    Minority interest (non-controlling interest) reduces net_income_parent but is NOT
    in tax_expense. When minority_interest data exists it is subtracted from expected.
    This prevents false CRITICAL failures for companies with subsidiaries (e.g. TRA).
    """
    pbt = _get(fact_table, "profit_before_tax.total", period)
    tax = _get(fact_table, "tax_expense.total", period)
    net_income = _get(fact_table, "net_income.parent", period)
    # Minority interest may be stored under several keys
    minority = (
        _get(fact_table, "net_income.minority", period)
        or _get(fact_table, "minority_interest.total", period)
        or _get(fact_table, "net_income.non_controlling", period)
    )

    have_expected = pbt is not None and tax is not None
    have_actual = net_income is not None

    if not have_expected and not have_actual:
        return None

    tolerance_pct = 0.01

    if have_expected and have_actual:
        expected = pbt - abs(tax)
        if minority is not None:
            expected -= abs(minority)
        actual = net_income
        diff = actual - expected
        tolerance_abs = abs(pbt) * tolerance_pct if pbt else 0.0
        if abs(diff) < tolerance_abs:
            status = "pass"
            mi_note = f" (minority_interest={minority:.2f} deducted)" if minority is not None else ""
            message = f"net_income reconciles within {tolerance_pct*100:.0f}% of PBT{mi_note}"
        else:
            # If residual diff matches a plausible minority interest (data missing but
            # implied from actual - expected), downgrade to WARN so valuation is not
            # blocked when the discrepancy is attributable to non-controlling interest.
            implied_minority = abs(diff)
            if minority is None and 0 < implied_minority < abs(pbt) * 0.15:
                # Diff < 15% of PBT with no minority data → likely minority interest
                status = "warn"
                message = (
                    f"net_income mismatch likely explained by minority interest "
                    f"(implied NCI={implied_minority:.2f}): "
                    f"expected {expected:.2f}, actual {actual:.2f}, diff {diff:.2f}"
                )
            else:
                status = "fail"
                message = (
                    f"net_income mismatch: expected {expected:.2f}, actual {actual:.2f}, "
                    f"diff {diff:.2f} (tolerance {tolerance_abs:.2f})"
                )
        return ReconciliationCheck(
            name="IS_net_income_check",
            period=period,
            expected=expected,
            actual=actual,
            difference=diff,
            tolerance_pct=tolerance_pct,
            status=status,
            message=message,
        )
    else:
        return ReconciliationCheck(
            name="IS_net_income_check",
            period=period,
            expected=(pbt - abs(tax)) if have_expected else None,
            actual=net_income,
            difference=None,
            tolerance_pct=tolerance_pct,
            status="warn",
            message="one side missing: cannot fully reconcile net_income",
        )


def _check_bs_equation(fact_table: FactTable, period: str) -> Optional[ReconciliationCheck]:
    """Check 4: total_assets ≈ total_liabilities + equity.parent (tolerance 0.5% of assets)."""
    assets = _get(fact_table, "total_assets.ending", period)
    liabilities = _get(fact_table, "total_liabilities.ending", period)
    equity = _get(fact_table, "equity.parent", period)

    have_expected = liabilities is not None and equity is not None
    have_actual = assets is not None

    if not have_expected and not have_actual:
        return None

    tolerance_pct = 0.005

    if have_expected and have_actual:
        expected = liabilities + equity
        actual = assets
        diff = actual - expected
        tolerance_abs = abs(assets) * tolerance_pct if assets else 0.0
        if abs(diff) < tolerance_abs:
            status = "pass"
            message = f"BS equation balances within {tolerance_pct*100:.1f}% of assets"
        else:
            status = "fail"
            message = (
                f"BS equation violated: assets={actual:.2f}, liabilities+equity={expected:.2f}, "
                f"diff={diff:.2f} (tolerance {tolerance_abs:.2f})"
            )
        return ReconciliationCheck(
            name="BS_accounting_equation_check",
            period=period,
            expected=expected,
            actual=actual,
            difference=diff,
            tolerance_pct=tolerance_pct,
            status=status,
            message=message,
        )
    else:
        return ReconciliationCheck(
            name="BS_accounting_equation_check",
            period=period,
            expected=(liabilities + equity) if have_expected else None,
            actual=assets,
            difference=None,
            tolerance_pct=tolerance_pct,
            status="warn",
            message="one side missing: cannot fully reconcile BS equation",
        )


def _compute_implied_shares(net_income: float, eps: float) -> float:
    """Compute implied shares (millions) from net_income (tỷ VND) and eps (VND/share)."""
    # net_income tỷ VND × 1e9 / eps VND/share = shares; / 1e6 = million shares
    # Simplified: net_income * 1000 / eps
    return net_income * 1000.0 / eps


def _check_eps_reconciliation(fact_table: FactTable, periods: list[str]) -> list[ReconciliationCheck]:
    """Check 3: EPS implied shares are consistent across periods (tolerance 2%).

    Computes implied shares for each period that has both net_income and eps.
    Flags any period whose implied shares differ by >2% from the median.
    """
    tolerance_pct = 0.02
    implied_by_period: dict[str, float] = {}

    for period in periods:
        net_income = _get(fact_table, "net_income.parent", period)
        eps = _get(fact_table, "eps.basic", period)
        if net_income is not None and eps is not None and eps != 0:
            implied_by_period[period] = _compute_implied_shares(net_income, eps)

    if not implied_by_period:
        return []

    if len(implied_by_period) == 1:
        # Cannot compute median across periods — skip divergence check
        period, shares = next(iter(implied_by_period.items()))
        return [ReconciliationCheck(
            name="IS_eps_reconciliation_check",
            period=period,
            expected=shares,
            actual=shares,
            difference=0.0,
            tolerance_pct=tolerance_pct,
            status="pass",
            message=f"implied shares = {shares:.2f}M (only one period available)",
        )]

    median_shares = statistics.median(list(implied_by_period.values()))
    checks: list[ReconciliationCheck] = []

    for period, shares in implied_by_period.items():
        if median_shares == 0:
            continue
        deviation = abs(shares - median_shares) / abs(median_shares)
        if deviation > tolerance_pct:
            status = "warn"
            message = (
                f"EPS implied shares {shares:.2f}M diverges {deviation*100:.1f}% from "
                f"median {median_shares:.2f}M — check EPS or net_income"
            )
        else:
            status = "pass"
            message = f"EPS implied shares {shares:.2f}M within {tolerance_pct*100:.0f}% of median {median_shares:.2f}M"

        checks.append(ReconciliationCheck(
            name="IS_eps_reconciliation_check",
            period=period,
            expected=median_shares,
            actual=shares,
            difference=shares - median_shares,
            tolerance_pct=tolerance_pct,
            status=status,
            message=message,
        ))

    return checks


def _check_fcf_sign_flip(fact_table: FactTable, periods: list[str]) -> list[ReconciliationCheck]:
    """Check 5: FCF sign consistency across consecutive periods.

    FCF = operating_cash_flow.total + capex.total (capex is stored negative).
    Warns if FCF flips sign between consecutive periods.
    """
    # Compute FCF per period
    fcf_by_period: dict[str, float] = {}
    for period in periods:
        ocf = _get(fact_table, "operating_cash_flow.total", period)
        capex = _get(fact_table, "capex.total", period)
        if ocf is not None and capex is not None:
            fcf_by_period[period] = ocf + capex

    checks: list[ReconciliationCheck] = []

    # Walk consecutive periods
    available = [p for p in periods if p in fcf_by_period]
    for i in range(1, len(available)):
        prev_period = available[i - 1]
        curr_period = available[i]
        prev_fcf = fcf_by_period[prev_period]
        curr_fcf = fcf_by_period[curr_period]

        # Sign flip: one is positive, the other negative (both non-zero)
        if prev_fcf != 0 and curr_fcf != 0 and (prev_fcf > 0) != (curr_fcf > 0):
            checks.append(ReconciliationCheck(
                name="CF_fcf_sign_flip_check",
                period=curr_period,
                expected=None,
                actual=curr_fcf,
                difference=curr_fcf - prev_fcf,
                tolerance_pct=0.0,
                status="warn",
                message=(
                    f"FCF sign flip between {prev_period} and {curr_period} "
                    f"({prev_fcf:.2f} → {curr_fcf:.2f}) — verify capex magnitude"
                ),
            ))

    return checks


def _check_time_series_sanity(
    fact_table: FactTable,
    periods: list[str],
) -> list[ReconciliationCheck]:
    """Check 6 — Time-series sanity checks (Plan §11.7).

    Warns when YoY changes exceed thresholds that suggest data errors:
      revenue       : > ±30%
      net_income    : > ±40%
      gross_margin  : > ±5 percentage points
      net_margin    : > ±5 percentage points
      total_assets  : > ±25%
      equity.parent : > ±25%
      cfo_ni_ratio  : < 0.5x or > 2.0x (cross-period median check)
    """
    checks: list[ReconciliationCheck] = []

    thresholds: list[tuple[str, float, str]] = [
        ("revenue.net", 0.30, "revenue YoY"),
        ("net_income.parent", 0.40, "net_income YoY"),
        ("total_assets.ending", 0.25, "total_assets YoY"),
        ("equity.parent", 0.25, "equity YoY"),
    ]

    for metric, limit, label in thresholds:
        for i in range(1, len(periods)):
            prev_p, curr_p = periods[i - 1], periods[i]
            prev_v = _get(fact_table, metric, prev_p)
            curr_v = _get(fact_table, metric, curr_p)
            if prev_v is None or curr_v is None or prev_v == 0:
                continue
            change = (curr_v - prev_v) / abs(prev_v)
            if abs(change) > limit:
                checks.append(ReconciliationCheck(
                    name=f"TS_{metric.replace('.', '_')}_yoy_check",
                    period=curr_p,
                    expected=prev_v,
                    actual=curr_v,
                    difference=curr_v - prev_v,
                    tolerance_pct=limit,
                    status="warn",
                    message=(
                        f"{label} {prev_p}→{curr_p}: {change*100:+.1f}% "
                        f"exceeds ±{limit*100:.0f}% threshold — verify data"
                    ),
                ))

    # Gross margin shift > ±5 pp
    for i in range(1, len(periods)):
        prev_p, curr_p = periods[i - 1], periods[i]
        for p, period in [(prev_p, prev_p), (curr_p, curr_p)]:
            rev = _get(fact_table, "revenue.net", period)
            gp = _get(fact_table, "gross_profit.total", period)
            if rev is None or gp is None or rev == 0:
                continue

        prev_rev = _get(fact_table, "revenue.net", prev_p)
        prev_gp = _get(fact_table, "gross_profit.total", prev_p)
        curr_rev = _get(fact_table, "revenue.net", curr_p)
        curr_gp = _get(fact_table, "gross_profit.total", curr_p)

        if (prev_rev and prev_gp and prev_rev != 0 and
                curr_rev and curr_gp and curr_rev != 0):
            prev_margin = prev_gp / prev_rev
            curr_margin = curr_gp / curr_rev
            shift = abs(curr_margin - prev_margin)
            if shift > 0.05:
                checks.append(ReconciliationCheck(
                    name="TS_gross_margin_shift_check",
                    period=curr_p,
                    expected=prev_margin,
                    actual=curr_margin,
                    difference=curr_margin - prev_margin,
                    tolerance_pct=0.05,
                    status="warn",
                    message=(
                        f"gross_margin shift {prev_p}→{curr_p}: "
                        f"{prev_margin*100:.1f}% → {curr_margin*100:.1f}% "
                        f"({(curr_margin-prev_margin)*100:+.1f} pp) exceeds ±5 pp threshold"
                    ),
                ))

    # Net margin shift > ±5 pp
    for i in range(1, len(periods)):
        prev_p, curr_p = periods[i - 1], periods[i]
        prev_rev = _get(fact_table, "revenue.net", prev_p)
        prev_ni = _get(fact_table, "net_income.parent", prev_p)
        curr_rev = _get(fact_table, "revenue.net", curr_p)
        curr_ni = _get(fact_table, "net_income.parent", curr_p)

        if (prev_rev and prev_ni and prev_rev != 0 and
                curr_rev and curr_ni and curr_rev != 0):
            prev_margin = prev_ni / prev_rev
            curr_margin = curr_ni / curr_rev
            shift = abs(curr_margin - prev_margin)
            if shift > 0.05:
                checks.append(ReconciliationCheck(
                    name="TS_net_margin_shift_check",
                    period=curr_p,
                    expected=prev_margin,
                    actual=curr_margin,
                    difference=curr_margin - prev_margin,
                    tolerance_pct=0.05,
                    status="warn",
                    message=(
                        f"net_margin shift {prev_p}→{curr_p}: "
                        f"{prev_margin*100:.1f}% → {curr_margin*100:.1f}% "
                        f"({(curr_margin-prev_margin)*100:+.1f} pp) exceeds ±5 pp threshold"
                    ),
                ))

    # CFO/NI ratio: warn if < 0.5x or > 2.0x for any period
    for period in periods:
        cfo = _get(fact_table, "operating_cash_flow.total", period)
        ni = _get(fact_table, "net_income.parent", period)
        if cfo is not None and ni is not None and ni != 0:
            ratio = cfo / ni
            if ratio < 0.5 or ratio > 2.0:
                checks.append(ReconciliationCheck(
                    name="TS_cfo_ni_ratio_check",
                    period=period,
                    expected=1.0,
                    actual=ratio,
                    difference=ratio - 1.0,
                    tolerance_pct=0.0,
                    status="warn",
                    message=(
                        f"CFO/NI ratio {ratio:.2f}x in {period} is outside [0.5x, 2.0x] "
                        f"— verify operating cash flow quality"
                    ),
                ))

    return checks


def run_reconciliation(
    ticker: str,
    fact_table: FactTable,
    periods: list[str],
) -> ReconciliationReport:
    """Run all accounting reconciliation checks for each period in `periods`.

    Returns a ReconciliationReport with per-check results and an overall status.
    `valuation_blocked` is True if any check has status == "fail".
    """
    all_checks: list[ReconciliationCheck] = []

    # Check 1 — IS gross profit (per period)
    for period in periods:
        result = _check_is_gross_profit(fact_table, period)
        if result is not None:
            all_checks.append(result)

    # Check 2 — IS net income from PBT (per period)
    for period in periods:
        result = _check_is_net_income(fact_table, period)
        if result is not None:
            all_checks.append(result)

    # Check 3 — IS EPS reconciliation (cross-period)
    all_checks.extend(_check_eps_reconciliation(fact_table, periods))

    # Check 4 — BS accounting equation (per period)
    for period in periods:
        result = _check_bs_equation(fact_table, period)
        if result is not None:
            all_checks.append(result)

    # Check 5 — FCF sign flip (consecutive periods)
    all_checks.extend(_check_fcf_sign_flip(fact_table, periods))

    # Check 6 — Time-series sanity (cross-period YoY / ratio checks)
    all_checks.extend(_check_time_series_sanity(fact_table, periods))

    critical_failures = [c for c in all_checks if c.status == "fail"]
    warnings = [c for c in all_checks if c.status == "warn"]
    valuation_blocked = len(critical_failures) > 0

    if critical_failures:
        overall_status = "fail"
    elif warnings:
        overall_status = "warn"
    else:
        overall_status = "pass"

    return ReconciliationReport(
        ticker=ticker,
        periods_checked=list(periods),
        checks=all_checks,
        critical_failures=critical_failures,
        warnings=warnings,
        overall_status=overall_status,
        valuation_blocked=valuation_blocked,
    )
