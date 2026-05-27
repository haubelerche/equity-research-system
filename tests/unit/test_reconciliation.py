"""Unit tests for backend.facts.reconciliation — Plan §12 accounting gates."""
import pytest

from backend.facts.reconciliation import run_reconciliation, ReconciliationReport, ReconciliationCheck


# ---------------------------------------------------------------------------
# Helper: build a minimal self-consistent fact table for one period
# ---------------------------------------------------------------------------

def _consistent_table(period: str = "2024FY") -> dict:
    """Return a fact table whose numbers are fully consistent."""
    revenue = 1000.0
    cogs = -600.0           # stored NEGATIVE
    gross_profit = 400.0    # revenue - |cogs| = 1000 - 600 = 400

    pbt = 200.0
    tax = -50.0             # stored NEGATIVE
    net_income = 150.0      # pbt - |tax| = 200 - 50 = 150

    eps = 5000.0            # VND/share
    # implied shares = net_income * 1000 / eps = 150 * 1000 / 5000 = 30 (million)

    assets = 800.0
    liabilities = 500.0
    equity = 300.0          # assets = liabilities + equity = 800

    ocf = 200.0
    capex = -50.0           # stored NEGATIVE

    return {
        "revenue.net":             {period: revenue},
        "cogs.total":              {period: cogs},
        "gross_profit.total":      {period: gross_profit},
        "profit_before_tax.total": {period: pbt},
        "tax_expense.total":       {period: tax},
        "net_income.parent":       {period: net_income},
        "eps.basic":               {period: eps},
        "total_assets.ending":     {period: assets},
        "total_liabilities.ending":{period: liabilities},
        "equity.parent":           {period: equity},
        "operating_cash_flow.total":{period: ocf},
        "capex.total":             {period: capex},
    }


# ---------------------------------------------------------------------------
# Test 1: All checks pass with internally consistent numbers
# ---------------------------------------------------------------------------

def test_pass_when_accounting_checks_out():
    """All reconciliation checks should pass for consistent numbers."""
    table = _consistent_table("2024FY")
    report = run_reconciliation("TEST", table, ["2024FY"])

    assert report.overall_status == "pass", (
        f"Expected 'pass', got '{report.overall_status}'. "
        f"Failures: {[c.message for c in report.critical_failures]}"
    )
    assert report.valuation_blocked is False
    assert len(report.critical_failures) == 0
    assert len(report.warnings) == 0


# ---------------------------------------------------------------------------
# Test 2: BS equation violated → fail
# ---------------------------------------------------------------------------

def test_fail_when_bs_equation_violated():
    """total_assets ≠ liabilities + equity by >0.5% → fail."""
    table = _consistent_table("2024FY")
    # Corrupt assets: correct would be 800, set to 820 (2.5% off)
    table["total_assets.ending"]["2024FY"] = 820.0

    report = run_reconciliation("TEST", table, ["2024FY"])

    assert report.overall_status == "fail"
    assert report.valuation_blocked is True
    bs_fails = [c for c in report.critical_failures if c.name == "BS_accounting_equation_check"]
    assert len(bs_fails) >= 1, "Expected BS check failure"


# ---------------------------------------------------------------------------
# Test 3: Gross profit wrong → fail
# ---------------------------------------------------------------------------

def test_fail_when_gross_profit_wrong():
    """gross_profit differs from revenue - |COGS| by >1% → fail."""
    table = _consistent_table("2024FY")
    # revenue=1000, |cogs|=600 → expected gross_profit=400
    # Set gross_profit to 380 (5% deviation from 400, and 2% of revenue)
    table["gross_profit.total"]["2024FY"] = 380.0

    report = run_reconciliation("TEST", table, ["2024FY"])

    assert report.overall_status == "fail"
    assert report.valuation_blocked is True
    gp_fails = [c for c in report.critical_failures if c.name == "IS_gross_profit_check"]
    assert len(gp_fails) >= 1, "Expected gross_profit check failure"


# ---------------------------------------------------------------------------
# Test 4: EPS implied shares diverge >2% from median → warn (not fail)
# ---------------------------------------------------------------------------

def test_warn_eps_share_divergence():
    """One period's implied shares differ >2% from median → warn, not fail."""
    # Three periods; 2022FY and 2023FY are consistent, 2024FY has diverged eps
    periods = ["2022FY", "2023FY", "2024FY"]

    # Consistent: net_income=150, eps=5000 → shares=30M
    table: dict = {
        "net_income.parent": {
            "2022FY": 150.0,
            "2023FY": 150.0,
            "2024FY": 150.0,
        },
        "eps.basic": {
            "2022FY": 5000.0,
            "2023FY": 5000.0,
            "2024FY": 3000.0,  # diverged: implies 50M shares vs median 30M
        },
    }

    report = run_reconciliation("TEST", table, periods)

    # Should warn but NOT fail (EPS rounding is common)
    eps_warns = [c for c in report.warnings if c.name == "IS_eps_reconciliation_check"]
    assert len(eps_warns) >= 1, "Expected EPS divergence warning"
    assert report.valuation_blocked is False  # warns never block
    # No critical failures for EPS
    eps_fails = [c for c in report.critical_failures if c.name == "IS_eps_reconciliation_check"]
    assert len(eps_fails) == 0


# ---------------------------------------------------------------------------
# Test 5: FCF sign flip between periods → warn
# ---------------------------------------------------------------------------

def test_fcf_sign_flip_produces_warn():
    """FCF flips from positive to negative between consecutive periods → warn."""
    periods = ["2023FY", "2024FY"]
    table: dict = {
        "operating_cash_flow.total": {
            "2023FY": 200.0,    # OCF positive
            "2024FY": 100.0,    # OCF positive but capex large negative
        },
        "capex.total": {
            "2023FY": -50.0,    # FCF 2023 = 200 - 50 = +150
            "2024FY": -300.0,   # FCF 2024 = 100 - 300 = -200 (sign flip)
        },
    }

    report = run_reconciliation("TEST", table, periods)

    fcf_warns = [c for c in report.warnings if c.name == "CF_fcf_sign_flip_check"]
    assert len(fcf_warns) >= 1, "Expected FCF sign flip warning"
    assert report.valuation_blocked is False  # sign flip is never a hard fail


# ---------------------------------------------------------------------------
# Test 6: Any fail → valuation_blocked = True
# ---------------------------------------------------------------------------

def test_valuation_blocked_on_fail():
    """valuation_blocked must be True whenever any check status is 'fail'."""
    table = _consistent_table("2024FY")
    # Make BS equation severely wrong (>0.5% of assets)
    table["total_assets.ending"]["2024FY"] = 900.0  # should be 800

    report = run_reconciliation("TEST", table, ["2024FY"])

    assert report.valuation_blocked is True
    assert report.overall_status == "fail"
    assert len(report.critical_failures) > 0


# ---------------------------------------------------------------------------
# Test 7: Warn-only → valuation NOT blocked
# ---------------------------------------------------------------------------

def test_valuation_not_blocked_on_warn_only():
    """valuation_blocked must be False when there are only warnings, no failures."""
    periods = ["2023FY", "2024FY"]
    # Only provide FCF data → triggers sign flip warn, no other checks
    table: dict = {
        "operating_cash_flow.total": {
            "2023FY": 200.0,
            "2024FY": 100.0,
        },
        "capex.total": {
            "2023FY": -50.0,
            "2024FY": -300.0,
        },
    }

    report = run_reconciliation("TEST", table, periods)

    assert len(report.critical_failures) == 0
    assert report.valuation_blocked is False
    # Should still have at least the FCF sign flip warn
    assert len(report.warnings) >= 1
    assert report.overall_status == "warn"
