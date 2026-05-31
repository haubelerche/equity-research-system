from __future__ import annotations

from backend.harness.gates import citation_gate, data_quality_gate, export_gate, valuation_gate
from backend.harness.runner import PUBLIC_TO_DB_APPROVAL_DECISION, PUBLIC_TO_DB_APPROVAL_STAGE
from backend.harness.state import AgentResult, ArtifactRef, EvidenceRef, ResearchGraphState, ServiceNodeResult
from backend.runtime_store import to_db_status, to_db_step_status, to_public_status


def test_research_graph_state_hash_is_stable() -> None:
    state = ResearchGraphState(run_id="run1", ticker="DHG", objective="test")
    assert state.stable_hash() == state.stable_hash()


def test_agent_and_service_contracts_accept_required_fields() -> None:
    artifact = ArtifactRef(artifact_id="a1", artifact_type="run_log_json")
    evidence = EvidenceRef(evidence_type="financial_fact", evidence_id="1")
    service = ServiceNodeResult(
        node_name="PREFLIGHT",
        status="completed",
        artifact_refs=[artifact],
        evidence_refs=[evidence],
    )
    agent = AgentResult(status="completed", confidence=0.9)

    assert service.artifact_refs[0].artifact_type == "run_log_json"
    assert agent.confidence == 0.9


def test_status_and_approval_mappings_are_db_safe() -> None:
    assert to_db_status("WAITING_FINAL_APPROVAL") == "needs_human_review"
    assert to_public_status("approved") == "PUBLISHED"
    assert PUBLIC_TO_DB_APPROVAL_STAGE["assumptions"] == "valuation_assumptions"
    assert PUBLIC_TO_DB_APPROVAL_STAGE["final"] == "final_report"
    assert PUBLIC_TO_DB_APPROVAL_DECISION["approve"] == "approved"
    assert PUBLIC_TO_DB_APPROVAL_DECISION["reject"] == "rejected"
    assert to_db_step_status("STARTED") == "running"
    assert to_db_step_status("COMPLETED") == "completed"


def test_data_quality_gate_requires_pass_and_snapshot() -> None:
    assert not data_quality_gate({"valuation_gate": "fail"})["passed"]
    assert not data_quality_gate({"valuation_gate": "pass"})["passed"]
    assert data_quality_gate({"valuation_gate": "pass", "snapshot_id": "snap1"})["passed"]
    assert not data_quality_gate({"valuation_gate": "pass", "snapshot_id": "snap1", "source_tier_coverage_status": "fail"})["passed"]


def test_valuation_gate_requires_core_components() -> None:
    summary = {
        "snapshot_id": "snap1",
        "formula_version": "valuation_v1",
        "assumption_version": "assumptions_v1",
        "unit_policy": "VND",
        "currency": "VND",
        "period_scope": {"period_type": "FY"},
        "valuation_methods": ["fcff", "fcfe", "blend"],
        "has_fcff": True,
        "has_fcfe": True,
        "has_blend": True,
        "has_sensitivity": True,
        "sensitivity_summary": {"fcff_wacc_g": {"matrix": [[1]]}},
        "assumptions": {"wacc": 0.1},
        "assumption_gate": {},
    }
    assert valuation_gate(summary)["passed"]
    summary["has_fcfe"] = False
    assert not valuation_gate(summary)["passed"]


def test_citation_and_export_gates_block_missing_approval() -> None:
    assert not citation_gate({"claims_count": 1, "citation_count": 0})["passed"]
    assert not citation_gate({"claims_count": 1, "citation_count": 1, "tier3_only_material_count": 1})["passed"]
    assert not export_gate({"gate_results": {}, "approvals": {}}, final_approval_required=True)["passed"]
    assert export_gate({"gate_results": {}, "approvals": {"final_report": "approved"}}, final_approval_required=True)["passed"]
    assert not export_gate(
        {
            "gate_results": {},
            "approvals": {"final_report": "approved"},
            "valuation_outputs": {"snapshot_id": "snap1"},
            "draft_report": {"snapshot_id": "snap2"},
            "artifacts": {"valuation_lock": {"locked": True}},
        },
        final_approval_required=True,
    )["passed"]
