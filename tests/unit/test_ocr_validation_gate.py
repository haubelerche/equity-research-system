"""
Tests for backend/documents/ocr_validation.py

Covers:
- validate_candidate_facts() for single and batch facts
- check_required_metric_coverage()
- load_known_metric_ids() fallback via explicit frozenset
"""
from __future__ import annotations

import math

import pytest

from backend.documents.ocr_candidate_facts import create_candidate_fact
from backend.documents.ocr_validation import (
    check_required_metric_coverage,
    validate_candidate_facts,
)

# ---------------------------------------------------------------------------
# Shared known_metric_ids fixture
# ---------------------------------------------------------------------------

KNOWN = frozenset({
    "revenue.net",
    "gross_profit.total",
    "profit_before_tax.total",
    "tax_expense.total",
    "net_income.parent",
    "total_assets.total",
    "liabilities.total",
    "equity.total",
    "eps.basic",
    "selling_expenses.total",
})


def _make_fact(**kwargs):
    """Helper — creates a minimal valid CandidateFact, overriding any fields via kwargs."""
    defaults = dict(
        ocr_run_id="run-001",
        document_id="doc-001",
        ticker="DHG",
        fiscal_year=2022,
        page_number=5,
        statement_type="income_statement",
        raw_label="Doanh thu thuần",
        normalized_label="revenue_net",
        metric_id="revenue.net",
        raw_value="4127.4",
        normalized_value=4127.4,
        unit="vnd_bn",
        confidence=0.90,
        mapping_rule_id="rule-001",
        period_type="FY",
        parser_version="1.0.0",
    )
    defaults.update(kwargs)
    return create_candidate_fact(**defaults)


# ---------------------------------------------------------------------------
# Test 1: Valid fact passes
# ---------------------------------------------------------------------------


def test_valid_fact_passes():
    fact = _make_fact()
    results = validate_candidate_facts([fact], known_metric_ids=KNOWN)
    assert len(results) == 1
    assert results[0].passed is True
    assert fact.validation_status == "passed"


# ---------------------------------------------------------------------------
# Test 2: Unknown metric_id fails
# ---------------------------------------------------------------------------


def test_unknown_metric_id_fails():
    fact = _make_fact(metric_id="nonexistent.metric")
    results = validate_candidate_facts([fact], known_metric_ids=KNOWN)
    assert results[0].passed is False
    assert fact.validation_status == "failed"
    failures_str = " ".join(results[0].failures)
    assert "metric_id_unknown" in failures_str


# ---------------------------------------------------------------------------
# Test 3: NaN value fails
# ---------------------------------------------------------------------------


def test_nan_value_fails():
    fact = _make_fact(normalized_value=float("nan"))
    results = validate_candidate_facts([fact], known_metric_ids=KNOWN)
    assert results[0].passed is False
    assert fact.validation_status == "failed"
    failures_str = " ".join(results[0].failures)
    assert "normalized_value_not_finite" in failures_str


# ---------------------------------------------------------------------------
# Test 4: Unreasonable fiscal year fails
# ---------------------------------------------------------------------------


def test_unreasonable_fiscal_year_fails():
    fact = _make_fact(fiscal_year=1800)
    results = validate_candidate_facts([fact], known_metric_ids=KNOWN)
    assert results[0].passed is False
    assert fact.validation_status == "failed"
    failures_str = " ".join(results[0].failures)
    assert "fiscal_year_out_of_range" in failures_str


# ---------------------------------------------------------------------------
# Test 5: Duplicate metric conflicting values — both fail
# ---------------------------------------------------------------------------


def test_duplicate_metric_conflicting_values_fails():
    fact_a = _make_fact(normalized_value=4127.4)
    fact_b = _make_fact(normalized_value=9999.9)  # same metric_id, different value

    results = validate_candidate_facts([fact_a, fact_b], known_metric_ids=KNOWN)
    # Both should fail
    assert fact_a.validation_status == "failed"
    assert fact_b.validation_status == "failed"
    # Both should carry the duplicate_metric_conflict warning
    assert "duplicate_metric_conflict" in fact_a.warnings
    assert "duplicate_metric_conflict" in fact_b.warnings


# ---------------------------------------------------------------------------
# Test 6: Duplicate metric same value — one passes, one redundant/blocked
# ---------------------------------------------------------------------------


def test_duplicate_metric_same_value_redundant():
    fact_a = _make_fact(normalized_value=4127.4)
    fact_b = _make_fact(normalized_value=4127.4)  # identical

    results = validate_candidate_facts([fact_a, fact_b], known_metric_ids=KNOWN)
    # First should pass, second should be blocked as redundant
    assert fact_a.validation_status == "passed"
    assert fact_b.validation_status == "failed"
    assert "duplicate_metric_redundant" in fact_b.warnings


# ---------------------------------------------------------------------------
# Test 7: tax_expense == net_income → regression check
# ---------------------------------------------------------------------------


def test_tax_expense_equals_net_income_fails():
    """Critical regression: OCR confusion where tax_expense and net_income share value."""
    shared_value = 250.0

    tax_fact = _make_fact(
        metric_id="tax_expense.total",
        normalized_value=shared_value,
        raw_label="Chi phí thuế TNDN",
        normalized_label="tax_expense_total",
        statement_type="income_statement",
    )
    ni_fact = _make_fact(
        metric_id="net_income.parent",
        normalized_value=shared_value,
        raw_label="Lợi nhuận sau thuế",
        normalized_label="net_income_parent",
        statement_type="income_statement",
    )

    results = validate_candidate_facts([tax_fact, ni_fact], known_metric_ids=KNOWN)

    # At least one of them must fail with the confusion check
    failed_facts = [f for f in [tax_fact, ni_fact] if f.validation_status == "failed"]
    assert len(failed_facts) >= 1, (
        "Expected at least one of tax_expense/net_income to fail when values are equal"
    )
    all_failures = " ".join(f for r in results for f in r.failures)
    assert "confusion" in all_failures


# ---------------------------------------------------------------------------
# Test 8: check_required_metric_coverage returns missing when not all present
# ---------------------------------------------------------------------------


def test_check_required_metric_coverage_returns_missing():
    # Only revenue.net present, other income_statement metrics absent
    fact = _make_fact(metric_id="revenue.net")
    fact.validation_status = "passed"

    missing = check_required_metric_coverage([fact])
    # income_statement should list the missing metrics
    income_missing = missing.get("income_statement", [])
    assert len(income_missing) > 0
    assert "gross_profit.total" in income_missing


# ---------------------------------------------------------------------------
# Test 9: check_required_metric_coverage passes when all present
# ---------------------------------------------------------------------------


def test_check_required_metric_coverage_passes_when_all_present():
    required_income = [
        "revenue.net",
        "gross_profit.total",
        "profit_before_tax.total",
        "tax_expense.total",
        "net_income.parent",
    ]
    required_balance = [
        "total_assets.total",
        "liabilities.total",
        "equity.total",
    ]

    facts = []
    for mid in required_income:
        f = _make_fact(
            metric_id=mid,
            normalized_value=100.0,
            statement_type="income_statement",
        )
        f.validation_status = "passed"
        facts.append(f)

    for mid in required_balance:
        f = _make_fact(
            metric_id=mid,
            normalized_value=500.0,
            statement_type="balance_sheet",
        )
        f.validation_status = "passed"
        facts.append(f)

    missing = check_required_metric_coverage(facts)
    assert missing["income_statement"] == []
    assert missing["balance_sheet"] == []
