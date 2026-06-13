"""Phase 7 — numeric & citation-coverage gates (no DB)."""
from __future__ import annotations

from backend.citations.citation_map import CitationMap, CitationRecord
from backend.evaluation.source_provenance_gates import (
    gate_citation_coverage,
    gate_numeric_consistency,
)


def _rec(metric="revenue.net", value=5015.4) -> CitationRecord:
    return CitationRecord(
        key=f"DHG/2023FY/{metric}", ticker="DHG", period="2023FY", fiscal_year=2023,
        metric=metric, metric_label=metric, value=value, value_display="",
        unit="vnd_bn", fact_id="f1", source_id="s1", source_uri="",
        source_title="BCTC", source_tier=0, tier_label="", published_at="",
        reliability_tier=2, official_document_id=5, reconciliation_status="matched_official",
    )


# 3. Report with missing citation fails (coverage).
def test_missing_citation_fails_coverage():
    cmap: CitationMap = {}  # no citations at all
    claims = [{"claim_type": "quantitative", "ticker": "DHG", "period": "2023FY",
               "metric": "revenue.net", "value": 5015.4}]
    res = gate_citation_coverage(claims, cmap)
    assert res.status == "fail"
    assert res.issues


def test_full_coverage_passes():
    cmap = {"DHG/2023FY/revenue.net": _rec()}
    claims = [{"claim_type": "quantitative", "ticker": "DHG", "period": "2023FY",
               "metric": "revenue.net", "value": 5015.4}]
    assert gate_citation_coverage(claims, cmap).status == "pass"


def test_production_quantitative_boolean_is_checked():
    claims = [{
        "claim_type": "fact",
        "quantitative": True,
        "ticker": "DHG",
        "period": "2023FY",
        "metric": "revenue.net",
        "value": 5015.4,
    }]
    assert gate_citation_coverage(claims, {}).status == "fail"


# 4. Report with numeric mismatch fails.
def test_numeric_mismatch_fails():
    cmap = {"DHG/2023FY/revenue.net": _rec(value=5015.4)}
    report_claims = [{"claim_type": "quantitative", "ticker": "DHG", "period": "2023FY",
                      "metric": "revenue.net", "value_mentioned": 9999.9}]
    res = gate_numeric_consistency(report_claims, cmap, tolerance_pct=1.0)
    assert res.status == "fail"
    assert any("vs fact" in i for i in res.issues)


def test_numeric_within_tolerance_passes():
    cmap = {"DHG/2023FY/revenue.net": _rec(value=5015.4)}
    report_claims = [{"claim_type": "quantitative", "ticker": "DHG", "period": "2023FY",
                      "metric": "revenue.net", "value_mentioned": 5020.0}]  # ~0.09%
    assert gate_numeric_consistency(report_claims, cmap, tolerance_pct=1.0).status == "pass"
