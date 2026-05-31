"""
Tests for backend/harness/gates.py — ocr_export_gate()

Covers:
- Final export blocked when any fact has promotion_status="blocked" and
  reconciliation_status="conflicted"
- Final export blocked when any fact has validation_status="failed"
- Draft mode always passes
- Final export passes when all facts are promoted
- blocking_reasons includes the metric_id of the blocked fact
"""
from __future__ import annotations

import pytest

from backend.documents.ocr_candidate_facts import create_candidate_fact
from backend.harness.gates import ocr_export_gate


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


def _make_fact(
    metric_id: str = "revenue.net",
    promotion_status: str = "blocked",
    reconciliation_status: str = "not_checked",
    validation_status: str = "pending",
    warnings: list | None = None,
):
    """Create a minimal CandidateFact with the given statuses."""
    fact = create_candidate_fact(
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
        confidence=0.90,
    )
    fact.promotion_status = promotion_status
    fact.reconciliation_status = reconciliation_status
    fact.validation_status = validation_status
    if warnings:
        fact.warnings = warnings
    return fact


# ---------------------------------------------------------------------------
# Test 1: Final export blocked when conflicted facts exist
# ---------------------------------------------------------------------------


def test_final_export_blocked_when_conflicted_facts_exist():
    conflicted_fact = _make_fact(
        metric_id="revenue.net",
        promotion_status="blocked",
        reconciliation_status="conflicted",
        validation_status="passed",
    )

    result = ocr_export_gate([conflicted_fact], report_mode="final")

    assert result["passed"] is False
    assert len(result["blocking_reasons"]) > 0
    # The gate summary should report blocked=1
    assert result["summary"]["blocked"] == 1


# ---------------------------------------------------------------------------
# Test 2: Final export blocked when validation-failed facts exist
# ---------------------------------------------------------------------------


def test_final_export_blocked_when_validation_failed_facts_exist():
    failed_fact = _make_fact(
        metric_id="gross_profit.total",
        promotion_status="blocked",
        reconciliation_status="not_checked",
        validation_status="failed",
        warnings=["schema:metric_id_unknown:gross_profit.total"],
    )

    result = ocr_export_gate([failed_fact], report_mode="final")

    assert result["passed"] is False
    assert len(result["blocking_reasons"]) > 0


# ---------------------------------------------------------------------------
# Test 3: Draft mode always passes even with unresolved facts
# ---------------------------------------------------------------------------


def test_draft_mode_passes_with_unresolved_facts():
    blocked_fact = _make_fact(
        metric_id="tax_expense.total",
        promotion_status="blocked",
        reconciliation_status="conflicted",
        validation_status="failed",
    )

    result = ocr_export_gate([blocked_fact], report_mode="draft")

    assert result["passed"] is True
    assert result["gate"] == "OCR_EXPORT_GATE"
    assert result["summary"]["report_mode"] == "draft"


# ---------------------------------------------------------------------------
# Test 4: Final export passes when all facts are promoted
# ---------------------------------------------------------------------------


def test_final_export_passes_when_all_facts_promoted():
    promoted_fact = _make_fact(
        metric_id="revenue.net",
        promotion_status="promoted",
        reconciliation_status="matched",
        validation_status="passed",
    )

    result = ocr_export_gate([promoted_fact], report_mode="final")

    assert result["passed"] is True
    assert result["blocking_reasons"] == []
    assert result["summary"]["promoted"] == 1
    assert result["summary"]["blocked"] == 0


# ---------------------------------------------------------------------------
# Test 5: blocking_reasons includes the metric_id of the blocked fact
# ---------------------------------------------------------------------------


def test_blocking_reasons_include_metric_id():
    blocked_fact = _make_fact(
        metric_id="net_income.parent",
        promotion_status="blocked",
        reconciliation_status="conflicted",
        validation_status="passed",
    )

    result = ocr_export_gate([blocked_fact], report_mode="final")

    assert result["passed"] is False
    # At least one blocking reason must mention the metric_id
    reasons_str = " ".join(result["blocking_reasons"])
    assert "net_income.parent" in reasons_str, (
        f"Expected 'net_income.parent' in blocking_reasons, got: {result['blocking_reasons']}"
    )
