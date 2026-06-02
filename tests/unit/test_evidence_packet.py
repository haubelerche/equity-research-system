from __future__ import annotations

import json

from backend.harness.evidence_packet import build_evidence_packet, write_evidence_packet
from backend.harness.state import ResearchGraphState


def test_evidence_packet_contains_required_harness_sections(tmp_path) -> None:
    state = ResearchGraphState(
        run_id="run_packet_test",
        ticker="DHG",
        objective="test evidence packet",
        from_year=2021,
        to_year=2025,
    )
    state.artifact_refs.append({
        "artifact_id": "DHG_valuation",
        "artifact_type": "valuation_result_json",
        "section_key": "valuation",
        "storage_path": str(tmp_path / "valuation.json"),
    })
    state.evidence_refs.append({
        "evidence_type": "financial_fact",
        "evidence_id": "fact_001",
        "source_tier": 1,
    })
    state.gate_results["EXPORT_GATE"] = {
        "gate": "EXPORT_GATE",
        "passed": False,
        "blocking_reasons": ["missing_formula_trace"],
    }

    packet = build_evidence_packet(state)

    assert packet["schema_version"] == 1
    assert packet["run_id"] == "run_packet_test"
    assert packet["periods"] == ["2021FY", "2022FY", "2023FY", "2024FY", "2025FY"]
    assert packet["artifact_refs"]
    assert packet["evidence_refs"]
    assert "missing_formula_trace" in packet["known_limitations"]
    assert len(packet["packet_hash"]) == 64

    path = write_evidence_packet(state, tmp_path)
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["packet_hash"] == packet["packet_hash"]
