"""Numeric consistency evaluation gate.

Checks that report-generated financial numbers satisfy known structural invariants:
    - CAPEX values are non-negative
    - Net Debt formula: Interest-bearing debt - Cash - ST Investments (not total liabilities)
    - Terminal Value is included in Enterprise Value (PV(TV) > 0)
    - Equity roll-forward: dividends subtracted from equity in forecast
    - Sensitivity grid: values actually vary (not all identical — absolute reference bug)
    - WACC > terminal_growth (otherwise TV is undefined)
    - Re > terminal_growth (otherwise FCFE TV is undefined)

All checks are pure functions over structured artifact dicts — no LLM involvement.
"""
from __future__ import annotations

from typing import Any

from backend.harness.gates import _gate_result, pass_gate, fail_gate  # noqa: F401 — re-export pattern


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_result(
    name: str,
    issues: list[str],
    summary: dict[str, Any],
    severity: str = "critical",
) -> dict[str, Any]:
    passed = len(issues) == 0
    return _gate_result(
        name,
        passed,
        blocking_reasons=issues if not passed else [],
        summary=summary,
        severity="none" if passed else severity,
    )


# ── individual checks ──────────────────────────────────────────────────────────

def check_capex_non_negative(
    capex_series: dict[str, float],
) -> dict[str, Any]:
    """Return gate_result. FAIL if any capex value < 0."""
    issues: list[str] = []
    for year, value in capex_series.items():
        if value is not None and value < 0:
            issues.append(f"capex[{year}]={value:.2f} is negative (should be non-negative outflow)")
    return _make_result(
        "CAPEX_NON_NEGATIVE",
        issues,
        {"checked_years": len(capex_series), "negative_count": len(issues)},
    )


def check_net_debt_formula(
    interest_bearing_debt: float,
    cash: float,
    st_investments: float,
    reported_net_debt: float | None,
    tolerance: float = 5.0,
) -> dict[str, Any]:
    """Check: net_debt = debt - cash - st_investments (not total_liabilities).
    Return gate_result FAIL if reported differs by > tolerance."""
    expected = interest_bearing_debt - cash - st_investments
    if reported_net_debt is None:
        return _make_result(
            "NET_DEBT_FORMULA",
            [],
            {
                "expected_net_debt": expected,
                "reported_net_debt": None,
                "note": "reported_net_debt not provided; formula check skipped",
            },
            severity="none",
        )
    diff = abs(reported_net_debt - expected)
    issues: list[str] = []
    if diff > tolerance:
        issues.append(
            f"net_debt mismatch: reported={reported_net_debt:.2f}, "
            f"expected={expected:.2f} (debt={interest_bearing_debt:.2f} "
            f"- cash={cash:.2f} - st_inv={st_investments:.2f}), diff={diff:.2f} > tol={tolerance:.2f}"
        )
    return _make_result(
        "NET_DEBT_FORMULA",
        issues,
        {
            "expected_net_debt": expected,
            "reported_net_debt": reported_net_debt,
            "diff": diff,
            "tolerance": tolerance,
        },
    )


def check_terminal_value_in_ev(
    pv_terminal_value: float | None,
    enterprise_value: float | None,
) -> dict[str, Any]:
    """Return gate_result FAIL if pv_terminal_value is None, 0, or equals sum_pv_fcff
    (which would indicate TV was not added to EV)."""
    issues: list[str] = []
    if pv_terminal_value is None:
        issues.append("pv_terminal_value is None — terminal value was not recorded in artifact")
    elif pv_terminal_value == 0:
        issues.append("pv_terminal_value=0 — terminal value appears absent from enterprise value")
    elif enterprise_value is not None and pv_terminal_value >= enterprise_value:
        # If TV >= EV that means FCF PV sum is ≤ 0, which is suspicious
        issues.append(
            f"pv_terminal_value={pv_terminal_value:.2f} >= enterprise_value={enterprise_value:.2f}; "
            "likely terminal value equals entire EV (FCF PV sum missing)"
        )

    return _make_result(
        "TERMINAL_VALUE_IN_EV",
        issues,
        {
            "pv_terminal_value": pv_terminal_value,
            "enterprise_value": enterprise_value,
        },
    )


def check_equity_roll_forward_dividends(
    equity_forecast: dict[str, float],
    net_income_forecast: dict[str, float],
    dividends_forecast: dict[str, float],
    tolerance: float = 10.0,
) -> dict[str, Any]:
    """For each consecutive year pair: check that equity_t ≈ equity_t-1 + ni_t - div_t.
    FAIL if any year exceeds tolerance and no equity issuance explains it."""
    issues: list[str] = []
    years = sorted(equity_forecast.keys())
    checked = 0
    for i in range(1, len(years)):
        prev_year = years[i - 1]
        curr_year = years[i]
        eq_prev = equity_forecast.get(prev_year)
        eq_curr = equity_forecast.get(curr_year)
        ni = net_income_forecast.get(curr_year)
        div = dividends_forecast.get(curr_year)
        if any(v is None for v in (eq_prev, eq_curr, ni, div)):
            continue
        checked += 1
        expected = eq_prev + ni - div
        diff = abs(eq_curr - expected)
        if diff > tolerance:
            issues.append(
                f"equity roll-forward mismatch at {curr_year}: "
                f"eq={eq_curr:.2f}, expected={expected:.2f} "
                f"(eq_prev={eq_prev:.2f} + ni={ni:.2f} - div={div:.2f}), diff={diff:.2f} > tol={tolerance:.2f}"
            )

    return _make_result(
        "EQUITY_ROLL_FORWARD",
        issues,
        {"checked_periods": checked, "violations": len(issues), "tolerance": tolerance},
    )


def check_sensitivity_grid_varies(
    matrix: dict[str, dict[str, float | None]],
) -> dict[str, Any]:
    """Check that the sensitivity matrix has at least 2 distinct non-None values.
    FAIL if all cells are identical (absolute reference bug)."""
    all_values: list[float] = []
    for row in matrix.values():
        for v in row.values():
            if v is not None:
                all_values.append(v)

    issues: list[str] = []
    if not all_values:
        issues.append("sensitivity matrix contains no non-None values")
    elif len(set(all_values)) < 2:
        issues.append(
            f"sensitivity matrix has only one distinct value ({all_values[0]:.4f}); "
            "likely an absolute reference bug — all cells show the base case value"
        )

    return _make_result(
        "SENSITIVITY_GRID_VARIES",
        issues,
        {
            "total_cells": len(all_values),
            "distinct_values": len(set(all_values)) if all_values else 0,
        },
    )


def check_discount_rate_exceeds_growth(
    wacc: float | None,
    re: float | None,
    terminal_growth: float | None,
) -> dict[str, Any]:
    """FAIL if WACC <= terminal_growth or Re <= terminal_growth."""
    issues: list[str] = []
    checked = 0

    if wacc is not None and terminal_growth is not None:
        checked += 1
        if wacc <= terminal_growth:
            issues.append(
                f"WACC={wacc:.4f} <= terminal_growth={terminal_growth:.4f}; "
                "terminal value is undefined (Gordon Growth denominator ≤ 0)"
            )

    if re is not None and terminal_growth is not None:
        checked += 1
        if re <= terminal_growth:
            issues.append(
                f"Re={re:.4f} <= terminal_growth={terminal_growth:.4f}; "
                "FCFE terminal value is undefined (Gordon Growth denominator ≤ 0)"
            )

    return _make_result(
        "DISCOUNT_RATE_EXCEEDS_GROWTH",
        issues,
        {
            "wacc": wacc,
            "re": re,
            "terminal_growth": terminal_growth,
            "checks_run": checked,
        },
    )


# ── aggregate gate ─────────────────────────────────────────────────────────────

def run_numeric_consistency_gate(
    valuation_artifact: dict,
) -> dict[str, Any]:
    """Run all checks against a valuation artifact dict. Return aggregate gate result.

    Expected keys in valuation_artifact (all optional, checks skipped if missing):
        fcff.capex_series: dict[str, float]
        fcff.net_debt: float (reported)
        fcff.interest_bearing_debt: float
        fcff.cash: float
        fcff.st_investments: float
        fcff.pv_terminal_value: float
        fcff.enterprise_value: float
        fcff.wacc: float
        fcff.terminal_growth: float
        fcfe.re: float (= cost_of_equity)
        fcfe.terminal_growth: float
        sensitivity.matrix: dict[str, dict[str, float|None]]
        equity_forecast: dict[str, float]
        net_income_forecast: dict[str, float]
        dividends_forecast: dict[str, float]

    Returns gate result with status "pass" | "warn" | "fail" and list of issues.
    """
    sub_results: list[dict[str, Any]] = []
    all_issues: list[str] = []

    fcff = valuation_artifact.get("fcff") or {}
    fcfe = valuation_artifact.get("fcfe") or {}
    sensitivity = valuation_artifact.get("sensitivity") or {}

    # 1. CAPEX non-negative
    capex_series = fcff.get("capex_series")
    if capex_series:
        r = check_capex_non_negative(capex_series)
        sub_results.append(r)
        all_issues.extend(r["blocking_reasons"])

    # 2. Net debt formula
    ibd = fcff.get("interest_bearing_debt")
    cash = fcff.get("cash")
    st_inv = fcff.get("st_investments")
    if ibd is not None and cash is not None and st_inv is not None:
        r = check_net_debt_formula(
            interest_bearing_debt=ibd,
            cash=cash,
            st_investments=st_inv,
            reported_net_debt=fcff.get("net_debt"),
        )
        sub_results.append(r)
        all_issues.extend(r["blocking_reasons"])

    # 3. Terminal value in EV
    pv_tv = fcff.get("pv_terminal_value")
    ev = fcff.get("enterprise_value")
    if pv_tv is not None or ev is not None:
        r = check_terminal_value_in_ev(pv_tv, ev)
        sub_results.append(r)
        all_issues.extend(r["blocking_reasons"])

    # 4. Discount rate > growth
    wacc = fcff.get("wacc")
    re_val = fcfe.get("re")
    tg_fcff = fcff.get("terminal_growth")
    tg_fcfe = fcfe.get("terminal_growth")
    terminal_growth = tg_fcff or tg_fcfe
    if wacc is not None or re_val is not None:
        r = check_discount_rate_exceeds_growth(wacc, re_val, terminal_growth)
        sub_results.append(r)
        all_issues.extend(r["blocking_reasons"])

    # 5. Sensitivity grid varies
    matrix = sensitivity.get("matrix")
    if matrix:
        r = check_sensitivity_grid_varies(matrix)
        sub_results.append(r)
        all_issues.extend(r["blocking_reasons"])

    # 6. Equity roll-forward
    eq_fc = valuation_artifact.get("equity_forecast")
    ni_fc = valuation_artifact.get("net_income_forecast")
    div_fc = valuation_artifact.get("dividends_forecast")
    if eq_fc and ni_fc and div_fc:
        r = check_equity_roll_forward_dividends(eq_fc, ni_fc, div_fc)
        sub_results.append(r)
        all_issues.extend(r["blocking_reasons"])

    passed = len(all_issues) == 0
    return _gate_result(
        "NUMERIC_CONSISTENCY",
        passed,
        blocking_reasons=all_issues if not passed else [],
        summary={
            "checks_run": len(sub_results),
            "checks_passed": sum(1 for r in sub_results if r["passed"]),
            "checks_failed": sum(1 for r in sub_results if not r["passed"]),
            "sub_results": [r["gate"] for r in sub_results],
        },
        severity="none" if passed else "critical",
    )
