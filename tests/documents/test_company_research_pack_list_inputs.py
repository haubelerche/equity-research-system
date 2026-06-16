"""Regression: build_company_research_pack must not crash on list-typed inputs.

The ANALYZE stage feeds an LLM-produced ``financial_analysis`` payload (and an
``evidence_pack``) into build_company_research_pack. When the model returns a
field that *should* be a mapping as a JSON list instead (e.g. a list of segment
objects), the old ``x or {}`` guard let the list through and the next ``.get``
raised ``'list' object has no attribute 'get'`` — failing the whole run at
ANALYZE. The builder must coerce wrong-typed inputs to empty mappings instead.
"""
from __future__ import annotations

from backend.documents.company_research_pack import build_company_research_pack


def test_list_typed_financial_analysis_fields_do_not_crash():
    financial_analysis = {
        # Model returned mappings-as-lists — the exact shape that crashed the run.
        "segment_channel_analysis": [{"name": "OTC", "share": 0.6}],
        "business_interpretation": ["branded generic player"],
        "financial_risks": [{"risk": "raw material cost"}],
    }
    pack = build_company_research_pack(
        ticker="DHG",
        evidence_pack={},
        financial_analysis=financial_analysis,
    )
    assert pack["ticker"] == "DHG"
    assert pack["archetype"] == "branded_generic_manufacturer"
    assert "coverage" in pack


def test_list_typed_evidence_pack_fields_do_not_crash():
    evidence_pack = {
        "business_evidence": [{"company_profile": "x"}],
        "pharma_catalyst_evidence": [{"event": "GMP-EU approval"}],
        "source_map": [],
    }
    pack = build_company_research_pack(
        ticker="DHG",
        evidence_pack=evidence_pack,
        financial_analysis={},
    )
    assert pack["ticker"] == "DHG"
    assert isinstance(pack["topics"], dict)
