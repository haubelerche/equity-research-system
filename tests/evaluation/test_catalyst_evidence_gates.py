"""Phase 7 � catalyst evidence gate (no DB)."""
from __future__ import annotations

from backend.evaluation.source_provenance_gates import gate_catalyst_evidence


def _event(**over) -> dict:
    base = dict(
        event_title="DHG kh�nh th�nh nh� m�y Betalactam",
        event_type="capacity_expansion",
        source_document_id=11,
        published_date="2025-06-01",
        evidence_quote="DHG c�ng b? ho�n th�nh d�y chuy?n ...",
        ticker="DHG",
        ticker_mapping_level="explicit",
        causality_level="management_disclosed_driver",
    )
    base.update(over)
    return base


# 7. Report with catalyst source and evidence quote passes.
def test_catalyst_with_source_and_evidence_passes():
    res = gate_catalyst_evidence([_event()])
    assert res.status == "pass"
    assert res.checked == 1


# 6. Report with catalyst but no source_document_id fails.
def test_catalyst_without_source_document_fails():
    res = gate_catalyst_evidence([_event(source_document_id=None)])
    assert res.status == "fail"
    assert any("source_document_id" in i for i in res.issues)


def test_catalyst_without_evidence_fails():
    res = gate_catalyst_evidence([_event(evidence_quote=None, evidence_span=None)])
    assert res.status == "fail"


def test_catalyst_unknown_type_fails():
    res = gate_catalyst_evidence([_event(event_type="totally_made_up")])
    assert res.status == "fail"


def test_no_catalysts_passes():
    res = gate_catalyst_evidence([])
    assert res.status == "pass"
