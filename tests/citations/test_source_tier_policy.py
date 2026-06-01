"""Phase 2 — Source-tier policy gate tests (no DB)."""
from __future__ import annotations

from backend.citations.citation_map import CitationMap, CitationRecord
from backend.citations.source_tier_policy import evaluate_source_tier_gate


def _rec(
    key: str,
    metric: str = "revenue.net",
    *,
    source_title: str,
    source_tier: int | None,
    official_document_id: int | None = None,
    is_derived: bool = False,
) -> CitationRecord:
    return CitationRecord(
        key=key,
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
        source_title=source_title,
        source_tier=source_tier,
        tier_label="",
        published_at="",
        reliability_tier=2,
        is_derived=is_derived,
        official_document_id=official_document_id,
    )


def _cmap(rec: CitationRecord) -> CitationMap:
    return {rec.key: rec}


# 1. "Balance Sheet (VCI) [Tier 3]" fails final export.
def test_balance_sheet_vci_fails_final():
    cmap = _cmap(_rec("DHG/2023FY/total_assets.ending", metric="total_assets.ending",
                      source_title="Balance Sheet (VCI) [Tier 3 — API tổng hợp]", source_tier=3))
    res = evaluate_source_tier_gate(cmap, mode="final")
    assert res.export_decision == "BLOCKED"
    assert any("VCI" in r or "(vci)" in r.lower() or "Tier-3" in r for r in res.blocking_reasons)


# 2. "Income Statement (KBS) [Tier 3]" fails final export.
def test_income_statement_kbs_fails_final():
    cmap = _cmap(_rec("DHG/2023FY/revenue.net",
                      source_title="Income Statement (KBS) [Tier 3]", source_tier=3))
    res = evaluate_source_tier_gate(cmap, mode="final")
    assert res.export_decision == "BLOCKED"


# 4. Quantitative claim with official_document_id passes source-tier gate.
def test_official_document_passes_final():
    cmap = _cmap(_rec("DHG/2023FY/revenue.net",
                      source_title="BCTC kiểm toán DHG 2023", source_tier=0,
                      official_document_id=42))
    res = evaluate_source_tier_gate(cmap, mode="final")
    assert res.export_decision == "PASS"
    assert res.passed is True


# 6. Unknown/generic source fails in BOTH draft approval and final export.
def test_unknown_source_fails_draft_and_final():
    cmap = _cmap(_rec("DHG/2023FY/revenue.net",
                      source_title="Nguồn không xác định", source_tier=None))
    res_final = evaluate_source_tier_gate(cmap, mode="final")
    res_draft = evaluate_source_tier_gate(cmap, mode="draft")
    assert res_final.export_decision == "BLOCKED"
    assert res_draft.export_decision == "BLOCKED"
    assert res_final.tier_counts["unknown"] == 1


def test_bad_label_draft_warns_not_blocks():
    """Bad provider label in draft mode should warn, not block."""
    cmap = _cmap(_rec("DHG/2023FY/total_assets.ending", metric="total_assets.ending",
                      source_title="Balance Sheet (VCI)", source_tier=3))
    res = evaluate_source_tier_gate(cmap, mode="draft")
    assert res.export_decision == "PASS_WITH_WARNINGS", (
        f"Expected PASS_WITH_WARNINGS in draft mode for bad label, got {res.export_decision}"
    )
    assert res.blocking_reasons == [], (
        f"Draft mode bad label should not produce blocking_reasons, got {res.blocking_reasons}"
    )


def test_tier_counts_reported():
    cmap = {
        "a": _rec("a", metric="revenue.net", source_title="BCTC", source_tier=0, official_document_id=1),
        "b": _rec("b", metric="net_income.parent", source_title="Income Statement", source_tier=3),
    }
    res = evaluate_source_tier_gate(cmap, mode="draft")
    assert res.tier_counts[0] == 1
    assert res.tier_counts[3] == 1
    assert res.checked == 2
