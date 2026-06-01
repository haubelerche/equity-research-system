"""Phase 2 — Tier-3-only claims cannot pass final export (no DB)."""
from __future__ import annotations

from backend.citations.citation_map import CitationMap, CitationRecord
from backend.citations.source_tier_policy import evaluate_source_tier_gate


def _vnstock_rec(metric: str = "revenue.net", official_document_id: int | None = None) -> CitationRecord:
    return CitationRecord(
        key=f"DHG/2023FY/{metric}",
        ticker="DHG",
        period="2023FY",
        fiscal_year=2023,
        metric=metric,
        metric_label=metric,
        value=5015.4,
        value_display="5,015.4 tỷ VND",
        unit="vnd_bn",
        fact_id="f1",
        source_id="s1",
        source_uri="vnstock://vci/finance/income_statement/DHG?period=year",
        source_title="Income Statement",  # not a bad label, but Tier 3 + vnstock URI
        source_tier=3,
        tier_label="",
        published_at="",
        reliability_tier=2,
        official_document_id=official_document_id,
    )


# 3. Quantitative claim with only vnstock source fails final export.
def test_vnstock_only_fails_final():
    cmap: CitationMap = {"k": _vnstock_rec()}
    res = evaluate_source_tier_gate(cmap, mode="final")
    assert res.export_decision == "BLOCKED"
    assert res.status == "fail"


# 5. Draft report MAY contain Tier 3 with "unverified" status (warn, not block).
def test_tier3_allowed_in_draft_as_unverified():
    cmap: CitationMap = {"k": _vnstock_rec()}
    res = evaluate_source_tier_gate(cmap, mode="draft")
    assert res.export_decision == "PASS_WITH_WARNINGS"
    assert res.passed is True
    assert any("unverified" in w.lower() for w in res.warnings)


# Once the same fact is reconciled against an official document, final passes.
def test_tier3_with_official_link_passes_final():
    cmap: CitationMap = {"k": _vnstock_rec(official_document_id=7)}
    res = evaluate_source_tier_gate(cmap, mode="final")
    assert res.export_decision == "PASS"
