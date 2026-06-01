"""Phase 7 — final source-provenance gates (no DB)."""
from __future__ import annotations

from backend.citations.citation_map import CitationMap, CitationRecord
from backend.evaluation.source_provenance_gates import run_all_gates


def _rec(metric="revenue.net", *, tier, official_document_id=None,
         reconciliation_status="missing_official", source_title="Income Statement") -> CitationRecord:
    return CitationRecord(
        key=f"DHG/2023FY/{metric}", ticker="DHG", period="2023FY", fiscal_year=2023,
        metric=metric, metric_label=metric, value=5015.4, value_display="5,015.4 tỷ VND",
        unit="vnd_bn", fact_id="f1", source_id="s1",
        source_uri="vnstock://vci/finance/income_statement/DHG?period=year",
        source_title=source_title, source_tier=tier, tier_label="", published_at="",
        reliability_tier=2, official_document_id=official_document_id,
        reconciliation_status=reconciliation_status,
    )


def _cmap(*recs: CitationRecord) -> CitationMap:
    return {r.key: r for r in recs}


def _claims(cmap: CitationMap) -> list[dict]:
    return [{"claim_type": "quantitative", "ticker": "DHG", "period": "2023FY",
             "metric": r.metric, "value": r.value} for r in cmap.values()]


# 1. Report with Tier 3-only quantitative claim fails final.
def test_tier3_only_fails_final():
    cmap = _cmap(_rec(tier=3))
    res = run_all_gates(claims=_claims(cmap), cmap=cmap, mode="final")
    assert res["final_approved"] is False
    assert res["export_blocked"] is True
    assert res["summary"]["source_tier_validity"] == "fail"


# 2. Report with official verified quantitative claim passes.
def test_official_verified_passes_final():
    cmap = _cmap(_rec(tier=0, official_document_id=9, reconciliation_status="matched_official",
                      source_title="BCTC kiểm toán DHG 2023"))
    res = run_all_gates(claims=_claims(cmap), cmap=cmap, mode="final")
    assert res["final_approved"] is True
    assert res["export_blocked"] is False
    assert all(s in ("pass",) for s in [
        res["summary"]["source_tier_validity"],
        res["summary"]["official_source_requirement"],
        res["summary"]["reconciliation_status"],
    ])


# 5. Report with unreviewed reconciliation mismatch fails.
def test_unreviewed_reconciliation_fails():
    cmap = _cmap(_rec(tier=0, official_document_id=9, reconciliation_status="manual_review_required",
                      source_title="BCTC kiểm toán DHG 2023"))
    res = run_all_gates(claims=_claims(cmap), cmap=cmap, mode="final")
    assert res["summary"]["reconciliation_status"] == "fail"
    assert res["export_blocked"] is True


# 8. Draft report may contain warnings but cannot be marked final-approved.
def test_draft_cannot_be_final_approved():
    cmap = _cmap(_rec(tier=3))
    res = run_all_gates(claims=_claims(cmap), cmap=cmap, mode="draft")
    assert res["final_approved"] is False
    assert res["summary"]["final_export_approval"] == "warn"
    # Tier 3 in draft is a warning on the tier gate, not a hard fail
    assert res["summary"]["source_tier_validity"] in ("warn", "pass")
