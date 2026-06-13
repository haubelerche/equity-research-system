"""Tests for backend.citations.claim_ledger (Phase 6)."""
from __future__ import annotations

import json
import pytest
from backend.citations.claim_ledger import (
    ClaimLedger,
    ClaimEntry,
    ClaimTrace,
    claim_from_fact,
    claim_from_artifact,
)


def _ledger(ticker: str = "DBD") -> ClaimLedger:
    return ClaimLedger(ticker=ticker, report_id="run_001")


class TestClaimEntry:
    def test_new_claim_is_unsupported(self):
        ledger = _ledger()
        entry = ledger.add_claim(
            claim_type="financial_fact",
            claim_text="Doanh thu 2025 đạt 1,865 tỷ VND",
            section="financial_performance",
            numeric_value=1865.0,
            numeric_unit="VND bn",
        )
        assert entry.status == "unsupported"

    def test_add_fact_trace_sets_supported(self):
        ledger = _ledger()
        entry = ledger.add_claim(
            claim_type="financial_fact",
            claim_text="Doanh thu 2025 đạt 1,865 tỷ VND",
            section="financial_performance",
        )
        entry.add_fact_trace(
            fact_id="f001", source_id="s001",
            metric_name="revenue.net", period="2025FY",
            value=1865.0, unit="VND bn", source_tier=0,
        )
        assert entry.status == "supported"

    def test_tier3_only_sets_partial(self):
        ledger = _ledger()
        entry = ledger.add_claim(
            claim_type="financial_fact",
            claim_text="Some fact",
            section="overview",
        )
        entry.add_fact_trace(
            fact_id="f001", source_id="s001",
            metric_name="revenue.net", period="2025FY",
            source_tier=3,  # convenience API only
        )
        assert entry.status == "partial"

    def test_artifact_trace_sets_supported(self):
        ledger = _ledger()
        entry = ledger.add_claim(
            claim_type="valuation_output",
            claim_text="Giá mục tiêu DCF 30,409 VND/cp",
            section="valuation",
            numeric_value=30409.0,
            numeric_unit="VND/share",
        )
        entry.add_artifact_trace(
            artifact_path="artifacts/valuation/DBD_blend.json",
            artifact_field="target_price_dcf",
            value=30409.0,
        )
        assert entry.status == "supported"

    def test_claim_id_is_deterministic(self):
        id1 = ClaimEntry.make_id("DBD", "Doanh thu 2025", "overview")
        id2 = ClaimEntry.make_id("DBD", "Doanh thu 2025", "overview")
        assert id1 == id2

    def test_claim_id_differs_by_section(self):
        id1 = ClaimEntry.make_id("DBD", "same text", "valuation")
        id2 = ClaimEntry.make_id("DBD", "same text", "overview")
        assert id1 != id2


class TestClaimLedger:
    def test_unsupported_claims_listed(self):
        ledger = _ledger()
        ledger.add_claim("financial_fact", "Unsupported fact", "overview")
        ledger.add_claim("financial_fact", "Another unsupported", "valuation")
        assert len(ledger.unsupported_claims()) == 2

    def test_citation_gate_fails_when_unsupported(self):
        ledger = _ledger()
        ledger.add_claim("financial_fact", "claim without trace", "overview")
        gate = ledger.citation_gate()
        assert gate["status"] == "FAIL"
        assert gate["unsupported_count"] == 1

    def test_citation_gate_passes_when_all_supported(self):
        ledger = _ledger()
        entry = ledger.add_claim(
            claim_type="financial_fact",
            claim_text="Revenue 1865 bn",
            section="financial_performance",
        )
        entry.add_fact_trace("f1", "s1", "revenue.net", "2025FY", source_tier=0)
        gate = ledger.citation_gate()
        assert gate["status"] == "PASS"

    def test_citation_gate_fails_tier3_when_strict(self):
        ledger = _ledger()
        entry = ledger.add_claim("financial_fact", "Tier-3 only claim", "overview")
        entry.add_fact_trace("f1", "s1", "revenue.net", "2025FY", source_tier=3)
        gate = ledger.citation_gate(require_tier_01=True)
        assert gate["status"] == "FAIL"
        assert gate["partial_count"] == 1

    def test_citation_gate_passes_tier3_when_not_strict(self):
        ledger = _ledger()
        entry = ledger.add_claim("financial_fact", "Tier-3 claim", "overview")
        entry.add_fact_trace("f1", "s1", "revenue.net", "2025FY", source_tier=3)
        gate = ledger.citation_gate(require_tier_01=False)
        assert gate["status"] == "PASS"  # partial passes in non-strict mode

    def test_summary_counts_by_status(self):
        ledger = _ledger()
        ledger.add_claim("financial_fact", "unsupported 1", "overview")
        e = ledger.add_claim("valuation_output", "supported 1", "valuation")
        e.add_artifact_trace("path", "field")
        summary = ledger.summary()
        assert summary.get("unsupported", 0) == 1
        assert summary.get("supported", 0) == 1

    def test_to_dict_serializable(self):
        ledger = _ledger()
        entry = ledger.add_claim("financial_fact", "Revenue 1865 bn", "financial_performance",
                                  numeric_value=1865.0, numeric_unit="VND bn")
        entry.add_fact_trace("f1", "s1", "revenue.net", "2025FY", source_tier=0)
        json.dumps(ledger.to_dict())

    def test_to_json_valid(self):
        ledger = _ledger()
        j = ledger.to_json()
        obj = json.loads(j)
        assert obj["ticker"] == "DBD"


class TestFactoryHelpers:
    def test_claim_from_fact_creates_supported_entry(self):
        ledger = _ledger()
        entry = claim_from_fact(
            ledger=ledger,
            claim_text="Net income 292 tỷ",
            section="financial_performance",
            fact_id="f002",
            source_id="s002",
            metric_name="net_income.parent",
            period="2025FY",
            value=292.0,
            unit="VND bn",
            source_tier=0,
        )
        assert entry.status == "supported"
        assert len(ledger.claims) == 1

    def test_claim_from_artifact_creates_supported_entry(self):
        ledger = _ledger()
        entry = claim_from_artifact(
            ledger=ledger,
            claim_text="Target price DCF 30,409 VND/cp",
            section="valuation",
            artifact_path="artifacts/valuation/DBD_blend.json",
            artifact_field="target_price_dcf",
            value=30409.0,
            unit="VND/share",
        )
        assert entry.status == "supported"
        assert entry.traces[0].trace_type == "artifact"
