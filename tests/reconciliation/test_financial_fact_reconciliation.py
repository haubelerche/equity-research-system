"""Phase 4 — Financial fact reconciliation (pure core, no DB)."""
from __future__ import annotations

from backend.reconciliation.financial_fact_reconciler import (
    PROMOTABLE_STATUSES,
    is_promotable,
    reconcile_one,
    reconcile_pair,
)


# 1. API value equals official value -> matched_official
def test_equal_values_matched():
    status, diff_abs, diff_pct = reconcile_one(5015.4, 5015.4)
    assert status == "matched_official"
    assert diff_abs == 0
    assert diff_pct == 0.0


# 2. API value differs within tolerance -> matched_official
def test_within_tolerance_matched():
    # 0.3% difference, tolerance 0.5%
    status, _, diff_pct = reconcile_one(1000.0, 1003.0)
    assert status == "matched_official"
    assert diff_pct <= 0.5


# 3. API value differs outside tolerance -> manual_review_required
def test_outside_tolerance_manual_review():
    status, _, diff_pct = reconcile_one(1000.0, 1100.0)  # 9.09% off official
    assert status == "manual_review_required"
    assert diff_pct > 0.5


# 4. API exists but official fact missing -> missing_official
def test_missing_official():
    status, diff_abs, diff_pct = reconcile_one(1000.0, None)
    assert status == "missing_official"
    assert diff_abs is None


# 5. Official fact exists but API missing -> missing_api
def test_missing_api():
    status, _, _ = reconcile_one(None, 1000.0)
    assert status == "missing_api"


# 6. Only matched_official / manual_reviewed facts are promotable
def test_promotion_rule():
    assert is_promotable("matched_official") is True
    assert is_promotable("manual_reviewed") is True
    assert is_promotable("manual_review_required") is False
    assert is_promotable("missing_official") is False
    assert is_promotable("mismatch") is False
    assert is_promotable("missing_api") is False
    assert PROMOTABLE_STATUSES == {"matched_official", "manual_reviewed"}


# 7. Unreviewed mismatch cannot be used in final report (not promotable)
def test_unreviewed_mismatch_not_promoted():
    r = reconcile_pair("DHG", 2023, "revenue.net", api_value=1000.0, official_value=2000.0)
    assert r.status == "manual_review_required"
    assert r.promotable is False
    assert "tolerance" in r.notes.lower()


def test_zero_official_value_edge():
    # Official zero, API non-zero -> infinite diff -> needs review
    status, _, diff_pct = reconcile_one(5.0, 0.0)
    assert status == "manual_review_required"
    assert diff_pct == float("inf")
    # Both zero -> matched
    status2, _, _ = reconcile_one(0.0, 0.0)
    assert status2 == "matched_official"


def test_reconcile_pair_carries_official_doc_id():
    r = reconcile_pair("DHG", 2023, "revenue.net", api_value=1000.0,
                       official_value=1000.0, official_document_id=42)
    assert r.status == "matched_official"
    assert r.promotable is True
    assert r.official_document_id == 42
