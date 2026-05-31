"""
Tests for backend/documents/fact_promotion.py

Covers:
- can_promote() rules
- promote_candidate_facts() batch behavior
- idempotency
- critical metric restriction
- non-critical metric with missing secondary
"""
from __future__ import annotations

import pytest

from backend.documents.ocr_candidate_facts import create_candidate_fact
from backend.documents.fact_promotion import (
    CRITICAL_METRICS,
    promote_candidate_facts,
    can_promote,
)


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


def _make_promotable_fact(
    metric_id: str = "revenue.net",
    reconciliation_status: str = "matched",
    confidence: float = 0.90,
    **kwargs,
):
    """Return a CandidateFact ready for promotion (validation passed, matched)."""
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
        raw_value="4127.4",
        normalized_value=4127.4,
        unit="vnd_bn",
        confidence=confidence,
    )
    defaults.update(kwargs)
    fact = create_candidate_fact(**defaults)
    fact.validation_status = "passed"
    fact.reconciliation_status = reconciliation_status
    return fact


# ---------------------------------------------------------------------------
# Test 1: Valid matched fact is promoted
# ---------------------------------------------------------------------------


def test_valid_matched_fact_is_promoted():
    fact = _make_promotable_fact()
    fact_table, results = promote_candidate_facts([fact])

    assert len(results) == 1
    assert results[0].promoted is True
    assert results[0].reason == "promoted"
    assert fact.promotion_status == "promoted"
    assert "revenue.net" in fact_table
    assert "2022FY" in fact_table["revenue.net"]


# ---------------------------------------------------------------------------
# Test 2: Conflicted fact is NOT promoted
# ---------------------------------------------------------------------------


def test_conflicted_fact_not_promoted():
    fact = _make_promotable_fact(reconciliation_status="conflicted")
    fact_table, results = promote_candidate_facts([fact])

    assert results[0].promoted is False
    assert "conflicted" in results[0].reason
    assert fact_table == {}


# ---------------------------------------------------------------------------
# Test 3: Low confidence fact is NOT promoted
# ---------------------------------------------------------------------------


def test_low_confidence_fact_not_promoted():
    fact = _make_promotable_fact(confidence=0.5)
    fact_table, results = promote_candidate_facts([fact])

    assert results[0].promoted is False
    assert "confidence" in results[0].reason
    assert fact_table == {}


# ---------------------------------------------------------------------------
# Test 4: Promotion is idempotent — same metric/period promoted only once
# ---------------------------------------------------------------------------


def test_promotion_is_idempotent():
    fact_a = _make_promotable_fact(normalized_value=4127.4)
    fact_b = _make_promotable_fact(normalized_value=4127.4)  # same metric + FY

    fact_table, results = promote_candidate_facts([fact_a, fact_b])

    # First is promoted, second is blocked as duplicate
    assert results[0].promoted is True
    assert results[1].promoted is False
    assert "duplicate" in results[1].reason.lower()

    # FactTable has exactly 1 entry for the metric
    assert len(fact_table.get("revenue.net", {})) == 1


# ---------------------------------------------------------------------------
# Test 5: Critical metric requires "matched" reconciliation
# ---------------------------------------------------------------------------


def test_critical_metric_requires_matched():
    # revenue.net is in CRITICAL_METRICS
    assert "revenue.net" in CRITICAL_METRICS

    fact = _make_promotable_fact(
        metric_id="revenue.net",
        reconciliation_status="missing_secondary_source",
    )

    # With require_matched_for_critical=True (default)
    fact_table, results = promote_candidate_facts(
        [fact], require_matched_for_critical=True
    )

    assert results[0].promoted is False
    assert "critical" in results[0].reason.lower() or "matched" in results[0].reason.lower()


# ---------------------------------------------------------------------------
# Test 6: Non-critical metric allows missing_secondary_source
# ---------------------------------------------------------------------------


def test_non_critical_metric_allows_missing_secondary():
    # Choose a metric definitely NOT in CRITICAL_METRICS
    non_critical = "selling_expenses.total"
    assert non_critical not in CRITICAL_METRICS, (
        f"{non_critical!r} is unexpectedly in CRITICAL_METRICS"
    )

    fact = _make_promotable_fact(
        metric_id=non_critical,
        reconciliation_status="missing_secondary_source",
    )

    # With require_matched_for_critical=True (default), non-critical should still promote
    fact_table, results = promote_candidate_facts(
        [fact], require_matched_for_critical=True
    )

    assert results[0].promoted is True, (
        f"Expected promotion for non-critical metric with missing_secondary_source, "
        f"got reason={results[0].reason!r}"
    )
    assert non_critical in fact_table
