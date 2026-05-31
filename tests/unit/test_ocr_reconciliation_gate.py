"""
Tests for backend/documents/ocr_reconciliation.py

Covers:
- reconcile_candidate_facts() with matched/conflicted/missing outcomes
- save/load reconciliation report roundtrip
- only validated facts are reconciled
- conflicted fact has decision="blocked_conflict"
"""
from __future__ import annotations

import json

import pytest

from backend.documents.ocr_candidate_facts import create_candidate_fact
from backend.documents.ocr_reconciliation import (
    ReconciliationRecord,
    load_reconciliation_report,
    reconcile_candidate_facts,
    save_reconciliation_report,
)


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


def _make_passed_fact(metric_id: str = "revenue.net", value: float = 4127.4, **kwargs):
    """Return a CandidateFact with validation_status='passed'."""
    defaults = dict(
        ocr_run_id="run-001",
        document_id="doc-001",
        ticker="DHG",
        fiscal_year=2022,
        page_number=5,
        statement_type="income_statement",
        raw_label="Doanh thu thuần",
        normalized_label="revenue_net",
        metric_id=metric_id,
        raw_value=str(value),
        normalized_value=value,
        unit="vnd_bn",
        confidence=0.90,
    )
    defaults.update(kwargs)
    fact = create_candidate_fact(**defaults)
    fact.validation_status = "passed"
    return fact


# ---------------------------------------------------------------------------
# Test 1: Matched within tolerance
# ---------------------------------------------------------------------------


def test_matched_within_tolerance():
    fact = _make_passed_fact(value=4127.4)
    secondary = {("DHG", 2022, "FY", "revenue.net"): 4130.0}

    records = reconcile_candidate_facts([fact], secondary, secondary_source_name="cafef")

    assert len(records) == 1
    assert records[0].status == "matched"
    assert records[0].decision == "promote_eligible"
    assert fact.reconciliation_status == "matched"


# ---------------------------------------------------------------------------
# Test 2: Conflicted outside tolerance
# ---------------------------------------------------------------------------


def test_conflicted_outside_tolerance():
    fact = _make_passed_fact(value=4127.4)
    secondary = {("DHG", 2022, "FY", "revenue.net"): 5000.0}

    records = reconcile_candidate_facts([fact], secondary, secondary_source_name="cafef")

    assert len(records) == 1
    assert records[0].status == "conflicted"
    assert records[0].decision == "blocked_conflict"
    assert fact.reconciliation_status == "conflicted"


# ---------------------------------------------------------------------------
# Test 3: Missing secondary source
# ---------------------------------------------------------------------------


def test_missing_secondary_source():
    fact = _make_passed_fact(metric_id="gross_profit.total", value=1500.0)
    # Secondary has no entry for gross_profit.total
    secondary: dict = {}

    records = reconcile_candidate_facts([fact], secondary, secondary_source_name="vnstock")

    assert len(records) == 1
    assert records[0].status == "missing_secondary_source"
    assert records[0].decision == "needs_review"
    assert records[0].secondary_value is None
    assert fact.reconciliation_status == "missing_secondary_source"


# ---------------------------------------------------------------------------
# Test 4: Facts with validation_status != "passed" are NOT reconciled
# ---------------------------------------------------------------------------


def test_only_validated_facts_reconciled():
    passed_fact = _make_passed_fact(value=4127.4)
    failed_fact = _make_passed_fact(metric_id="gross_profit.total", value=1000.0)
    failed_fact.validation_status = "failed"  # override

    secondary = {("DHG", 2022, "FY", "revenue.net"): 4127.4}

    records = reconcile_candidate_facts(
        [passed_fact, failed_fact], secondary, secondary_source_name="cafef"
    )

    # Only the passed fact should produce a record
    assert len(records) == 1
    assert records[0].metric_id == "revenue.net"
    # The failed fact's reconciliation_status should remain "not_checked"
    assert failed_fact.reconciliation_status == "not_checked"


# ---------------------------------------------------------------------------
# Test 5: Save and load reconciliation report roundtrip
# ---------------------------------------------------------------------------


def test_save_load_reconciliation_report_roundtrip(tmp_path):
    record = ReconciliationRecord(
        ticker="DHG",
        fiscal_year=2022,
        metric_id="revenue.net",
        period_type="FY",
        ocr_value=4127.4,
        secondary_value=4130.0,
        absolute_diff=2.6,
        relative_diff=2.6 / 4130.0,
        ocr_source="doc-001",
        secondary_source="cafef",
        status="matched",
        decision="promote_eligible",
    )

    saved_path = save_reconciliation_report(
        [record], ticker="DHG", fiscal_year=2022, base_dir=tmp_path
    )
    assert saved_path.exists()

    loaded = load_reconciliation_report(ticker="DHG", fiscal_year=2022, base_dir=tmp_path)
    assert len(loaded) == 1
    r = loaded[0]
    assert r.ticker == "DHG"
    assert r.fiscal_year == 2022
    assert r.metric_id == "revenue.net"
    assert r.status == "matched"
    assert r.decision == "promote_eligible"
    assert abs(r.ocr_value - 4127.4) < 0.01


# ---------------------------------------------------------------------------
# Test 6: Conflicted ReconciliationRecord decision is "blocked_conflict"
# ---------------------------------------------------------------------------


def test_conflicted_fact_decision_is_blocked():
    fact = _make_passed_fact(value=4127.4)
    secondary = {("DHG", 2022, "FY", "revenue.net"): 9000.0}

    records = reconcile_candidate_facts([fact], secondary, secondary_source_name="cafef")

    assert records[0].decision == "blocked_conflict"
    assert records[0].status == "conflicted"
