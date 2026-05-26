"""Tests for valuation readiness gate and reconciliation integration in completeness.py."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.facts.completeness import (
    build_fy_validation_report,
    valuation_readiness_gate,
    CORE_FY_KEYS,
)
from backend.facts.normalizer import FactTable

PERIODS = ["2021FY", "2022FY", "2023FY", "2024FY", "2025FY"]


def _make_full_table(status: str = "accepted") -> tuple[FactTable, dict]:
    """Return (fact_table, validation_status_table) fully populated — no accounting failures.

    Values chosen to satisfy all reconciliation checks:
      IS:  gross_profit = revenue - |cogs|    => 1000 - 200 = 800  (pass)
      IS:  net_income   = PBT - |tax|         => 600 - 100  = 500  (pass)
      BS:  assets       = liabilities + equity => 5000 = 3000 + 2000 (pass)
    """
    table: FactTable = {
        "revenue.net": {p: 1000.0 for p in PERIODS},
        "cogs.total": {p: 200.0 for p in PERIODS},
        "gross_profit.total": {p: 800.0 for p in PERIODS},
        "profit_before_tax.total": {p: 600.0 for p in PERIODS},
        "tax_expense.total": {p: 100.0 for p in PERIODS},
        "net_income.parent": {p: 500.0 for p in PERIODS},
        "total_assets.ending": {p: 5000.0 for p in PERIODS},
        "equity.parent": {p: 2000.0 for p in PERIODS},
        "operating_cash_flow.total": {p: 400.0 for p in PERIODS},
        "total_liabilities.ending": {p: 3000.0 for p in PERIODS},
    }
    vstatus = {key: {p: status for p in PERIODS} for key in CORE_FY_KEYS}
    return table, vstatus


def _call_report(
    table: FactTable,
    vstatus: dict,
    periods_available: list[str] | None = None,
    periods_missing: list[str] | None = None,
) -> dict:
    if periods_available is None:
        periods_available = list(PERIODS)
    if periods_missing is None:
        periods_missing = []
    return build_fy_validation_report(
        ticker="DHG",
        table=table,
        raw_facts=[],
        required_periods=PERIODS,
        periods_available=periods_available,
        periods_missing=periods_missing,
        forbidden_periods=[],
        generated_at=datetime.now(UTC),
        validation_status_table=vstatus,
    )


# ---------------------------------------------------------------------------
# 1. valuation_readiness_gate passes when DQ gate passes and no recon failures
# ---------------------------------------------------------------------------

def test_valuation_readiness_gate_pass():
    table, vstatus = _make_full_table("accepted")
    fy_report = _call_report(table, vstatus)
    assert fy_report["valuation_gate"] == "pass"

    gate = valuation_readiness_gate(
        ticker="DHG",
        fact_table=table,
        fy_validation_report=fy_report,
        periods_available=list(PERIODS),
    )

    assert gate["overall_status"] == "pass"
    assert gate["valuation_allowed"] is True
    assert gate["blocked_by_dq"] is False
    assert gate["blocked_by_reconciliation"] is False
    assert gate["reconciliation_critical_failures"] == []


# ---------------------------------------------------------------------------
# 2. valuation_readiness_gate fails when DQ gate fails
# ---------------------------------------------------------------------------

def test_valuation_readiness_gate_blocked_by_dq():
    # Only 2 periods — coverage gate will fail
    two_periods = ["2023FY", "2024FY"]
    table: FactTable = {key: {p: 1000.0 for p in two_periods} for key in CORE_FY_KEYS}
    vstatus = {key: {p: "accepted" for p in two_periods} for key in CORE_FY_KEYS}

    fy_report = build_fy_validation_report(
        ticker="DHG",
        table=table,
        raw_facts=[],
        required_periods=PERIODS,
        periods_available=two_periods,
        periods_missing=["2021FY", "2022FY", "2025FY"],
        forbidden_periods=[],
        generated_at=datetime.now(UTC),
        validation_status_table=vstatus,
    )
    assert fy_report["valuation_gate"] == "fail"

    gate = valuation_readiness_gate(
        ticker="DHG",
        fact_table=table,
        fy_validation_report=fy_report,
        periods_available=two_periods,
    )

    assert gate["overall_status"] == "fail"
    assert gate["valuation_allowed"] is False
    assert gate["blocked_by_dq"] is True


# ---------------------------------------------------------------------------
# 3. valuation_readiness_gate fails when reconciliation has a critical failure
# ---------------------------------------------------------------------------

def test_valuation_readiness_gate_blocked_by_reconciliation():
    # Gross profit deliberately wrong: revenue=1000, cogs=200 => expected=800, but we put 100
    table: FactTable = {
        "revenue.net": {p: 1000.0 for p in PERIODS},
        "cogs.total": {p: 200.0 for p in PERIODS},
        "gross_profit.total": {p: 100.0 for p in PERIODS},   # intentional mismatch
        "net_income.parent": {p: 500.0 for p in PERIODS},
        "total_assets.ending": {p: 5000.0 for p in PERIODS},
        "equity.parent": {p: 2000.0 for p in PERIODS},
        "operating_cash_flow.total": {p: 400.0 for p in PERIODS},
        "total_liabilities.ending": {p: 3000.0 for p in PERIODS},
    }
    vstatus = {key: {p: "accepted" for p in PERIODS} for key in CORE_FY_KEYS}

    fy_report = _call_report(table, vstatus)
    # The DQ three-tier gate should pass (coverage, core_keys, source_validation all fine)
    # but reconciliation gate inside build_fy_validation_report should fail
    assert fy_report["reconciliation_gate"] == "fail"

    gate = valuation_readiness_gate(
        ticker="DHG",
        fact_table=table,
        fy_validation_report=fy_report,
        periods_available=list(PERIODS),
    )

    assert gate["overall_status"] == "fail"
    assert gate["valuation_allowed"] is False
    assert gate["blocked_by_reconciliation"] is True
    assert len(gate["reconciliation_critical_failures"]) > 0


# ---------------------------------------------------------------------------
# 4. build_fy_validation_report now includes reconciliation_gate key
# ---------------------------------------------------------------------------

def test_build_fy_validation_report_includes_reconciliation_gate():
    table, vstatus = _make_full_table("accepted")
    report = _call_report(table, vstatus)

    assert "reconciliation_gate" in report
    assert "reconciliation_critical_failures" in report
    assert "reconciliation_warnings" in report
    assert isinstance(report["reconciliation_gate"], str)
    assert report["reconciliation_gate"] in ("pass", "warn", "fail")
    assert isinstance(report["reconciliation_critical_failures"], list)
    assert isinstance(report["reconciliation_warnings"], list)
