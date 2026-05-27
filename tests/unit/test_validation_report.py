"""Unit tests for backend.facts.validation_report — Plan §19 Data Validation Report."""
import os
import tempfile
from datetime import UTC, datetime

import pytest

from backend.facts.validation_report import generate_data_validation_report, write_data_validation_report
from backend.facts.reconciliation import ReconciliationCheck, ReconciliationReport


# ---------------------------------------------------------------------------
# Helper: build minimal test data
# ---------------------------------------------------------------------------

def _minimal_fact_table() -> dict:
    """Return a minimal fact table for testing."""
    return {
        "revenue.net": {"2024FY": 1000.0, "2023FY": 950.0},
        "net_income.parent": {"2024FY": 150.0, "2023FY": 140.0},
        "total_assets.ending": {"2024FY": 800.0, "2023FY": 750.0},
    }


def _minimal_fy_report_pass() -> dict:
    """Return a fy_report where all gates pass."""
    return {
        "ticker": "DHG",
        "periods_available": ["2024FY", "2023FY", "2022FY"],
        "periods_missing": [],
        "annual_reports_collected": 3,
        "coverage_gate": "pass",
        "core_keys_gate": "pass",
        "source_validation_gate": "pass",
        "reconciliation_gate": "pass",
        "valuation_ready": True,
        "blocking_reasons": [],
    }


def _minimal_fy_report_fail() -> dict:
    """Return a fy_report where valuation is blocked."""
    return {
        "ticker": "DHG",
        "periods_available": ["2024FY"],
        "periods_missing": ["2023FY", "2022FY"],
        "annual_reports_collected": 1,
        "coverage_gate": "fail",
        "core_keys_gate": "fail",
        "source_validation_gate": "pass",
        "reconciliation_gate": "pass",
        "valuation_ready": False,
        "blocking_reasons": [
            "insufficient_annual_reports: collected 1, minimum 3",
            "missing_core_keys: revenue.net, net_income.parent",
        ],
    }


def _minimal_reconciliation_report_pass() -> ReconciliationReport:
    """Return a reconciliation report where all checks pass."""
    check = ReconciliationCheck(
        name="IS_gross_profit_check",
        period="2024FY",
        expected=400.0,
        actual=400.0,
        difference=0.0,
        tolerance_pct=0.01,
        status="pass",
        message="gross_profit reconciles within 1% of revenue",
    )
    return ReconciliationReport(
        ticker="DHG",
        periods_checked=["2024FY", "2023FY", "2022FY"],
        checks=[check],
        critical_failures=[],
        warnings=[],
        overall_status="pass",
        valuation_blocked=False,
    )


def _minimal_reconciliation_report_fail() -> ReconciliationReport:
    """Return a reconciliation report where a check fails."""
    check = ReconciliationCheck(
        name="BS_accounting_equation_check",
        period="2024FY",
        expected=800.0,
        actual=820.0,
        difference=20.0,
        tolerance_pct=0.005,
        status="fail",
        message="BS equation violated: assets=820, liabilities+equity=800, diff=20",
    )
    return ReconciliationReport(
        ticker="DHG",
        periods_checked=["2024FY"],
        checks=[check],
        critical_failures=[check],
        warnings=[],
        overall_status="fail",
        valuation_blocked=True,
    )


# ---------------------------------------------------------------------------
# Test 1: Report contains ticker header
# ---------------------------------------------------------------------------

def test_report_contains_ticker_header():
    """Generated report should start with ticker in the title."""
    table = _minimal_fact_table()
    fy_report = _minimal_fy_report_pass()
    recon_report = _minimal_reconciliation_report_pass()

    report_md = generate_data_validation_report(
        ticker="DHG",
        snapshot_id="snap-001",
        fact_table=table,
        fy_report=fy_report,
        reconciliation_report=recon_report,
    )

    assert "# Data Validation Report — DHG" in report_md


# ---------------------------------------------------------------------------
# Test 2: Report contains all six sections
# ---------------------------------------------------------------------------

def test_report_contains_all_six_sections():
    """Generated report should contain all 6 numbered sections."""
    table = _minimal_fact_table()
    fy_report = _minimal_fy_report_pass()
    recon_report = _minimal_reconciliation_report_pass()

    report_md = generate_data_validation_report(
        ticker="DHG",
        snapshot_id="snap-001",
        fact_table=table,
        fy_report=fy_report,
        reconciliation_report=recon_report,
    )

    assert "## 1. Data Snapshot" in report_md
    assert "## 2. Source Coverage" in report_md
    assert "## 3. Critical Fact Validation (Accounting Reconciliation)" in report_md
    assert "## 4. Gate Summary" in report_md
    assert "## 5. Blocking Reasons" in report_md
    assert "## 6. Valuation Readiness Decision" in report_md


# ---------------------------------------------------------------------------
# Test 3: Report shows VALUATION_BLOCKED when failed
# ---------------------------------------------------------------------------

def test_report_shows_valuation_blocked_when_failed():
    """When valuation_ready=False, section 6 should contain VALUATION_BLOCKED."""
    table = _minimal_fact_table()
    fy_report = _minimal_fy_report_fail()
    recon_report = _minimal_reconciliation_report_pass()

    report_md = generate_data_validation_report(
        ticker="DHG",
        snapshot_id="snap-001",
        fact_table=table,
        fy_report=fy_report,
        reconciliation_report=recon_report,
    )

    assert "Status: VALUATION_BLOCKED" in report_md


# ---------------------------------------------------------------------------
# Test 4: Report shows VALUATION_ALLOWED when passed
# ---------------------------------------------------------------------------

def test_report_shows_valuation_allowed_when_passed():
    """When valuation_ready=True and no reconciliation failures, section 6 should contain VALUATION_ALLOWED."""
    table = _minimal_fact_table()
    fy_report = _minimal_fy_report_pass()
    recon_report = _minimal_reconciliation_report_pass()

    report_md = generate_data_validation_report(
        ticker="DHG",
        snapshot_id="snap-001",
        fact_table=table,
        fy_report=fy_report,
        reconciliation_report=recon_report,
    )

    assert "Status: VALUATION_ALLOWED" in report_md


# ---------------------------------------------------------------------------
# Test 5: Report reconciliation checks are formatted
# ---------------------------------------------------------------------------

def test_report_reconciliation_checks_formatted():
    """Checks from reconciliation_report should appear in section 3."""
    table = _minimal_fact_table()
    fy_report = _minimal_fy_report_pass()
    recon_report = _minimal_reconciliation_report_pass()

    report_md = generate_data_validation_report(
        ticker="DHG",
        snapshot_id="snap-001",
        fact_table=table,
        fy_report=fy_report,
        reconciliation_report=recon_report,
    )

    # Check that the check name appears
    assert "IS_gross_profit_check" in report_md
    # Check that period appears
    assert "2024FY" in report_md
    # Check that status appears
    assert "✓ PASS" in report_md


# ---------------------------------------------------------------------------
# Test 6: write_data_validation_report creates file
# ---------------------------------------------------------------------------

def test_write_creates_file():
    """write_data_validation_report should create a file with the correct name."""
    table = _minimal_fact_table()
    fy_report = _minimal_fy_report_pass()
    recon_report = _minimal_reconciliation_report_pass()

    report_md = generate_data_validation_report(
        ticker="DHG",
        snapshot_id="snap-001",
        fact_table=table,
        fy_report=fy_report,
        reconciliation_report=recon_report,
    )

    # Use a temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        path = write_data_validation_report(
            report_md=report_md,
            output_dir=tmpdir,
            ticker="DHG",
            snapshot_id="snap-001",
        )

        # Verify file exists
        assert os.path.exists(path)
        # Verify filename format
        assert path.endswith("DATA_VALIDATION_REPORT_DHG_snap-001.md")
        # Verify content
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "# Data Validation Report — DHG" in content
