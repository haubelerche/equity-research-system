from __future__ import annotations

from backend.harness.evidence_packet import (
    build_agent_effectiveness_audit,
    write_agent_effectiveness_audit,
)
from backend.harness.state import ResearchGraphState


def _state_with_trace() -> ResearchGraphState:
    state = ResearchGraphState(
        run_id="run_dhg_001",
        ticker="DHG",
        objective="full report",
        current_stage="REVIEW",
        status="blocked",
        blocking_reason="senior_critic_gate:data_gap",
        snapshot_id="snap_dhg",
    )
    # Five distinct agents — matches the runner's fixed stage roster and the
    # evaluator's MIN_GATE_SAMPLE=5 requirement for gate compliance.
    for agent_id, action in (
        ("research_manager", "plan"),
        ("data_evidence", "ingest"),
        ("financial_analysis", "analyze"),
        ("forecast_valuation", "value"),
        ("thesis_report", "write"),
        ("senior_critic", "review"),
    ):
        state.trace.append({
            "kind": "agent_message",
            "agent_id": agent_id,
            "agent_role": agent_id,
            "action": action,
            "status": "completed",
            "confidence": 0.9,
            "latency_ms": 1200,
            "cost_estimate": 0.01,
            "warnings": [],
            "output_summary": {"note": f"{agent_id} done"},
        })
    state.trace.append({
        "kind": "tool_call",
        "agent_role": "data_evidence",
        "tool_name": "build_facts",
        "output_hash": "abc",
        "output_summary": {"facts": 42},
        "gate_inputs": {"tool_permission": {"granted": True}},
    })
    return state


def test_audit_derives_agent_and_tool_execution_from_trace() -> None:
    audit = build_agent_effectiveness_audit(_state_with_trace())

    assert audit["ticker"] == "DHG"
    assert audit["run_id"] == "run_dhg_001"
    assert audit["schema_version"] == 1
    assert audit["status"] == "blocked"
    assert audit["requires_human"] is True

    agents = audit["agent_execution"]
    assert len(agents) == 6  # >= MIN_GATE_SAMPLE (5)
    assert all(record["status"] == "completed" for record in agents)
    assert {record["agent_id"] for record in agents} >= {
        "research_manager", "financial_analysis", "senior_critic",
    }

    tools = audit["tool_execution"]
    assert len(tools) == 1
    assert tools[0]["tool_name"] == "build_facts"


def test_write_audit_produces_resolvable_filename(tmp_path) -> None:
    path = write_agent_effectiveness_audit(_state_with_trace(), tmp_path)
    assert path.name.endswith("_agent_effectiveness_audit.json")
    assert path.is_file()


def test_empty_run_yields_empty_agent_execution() -> None:
    state = ResearchGraphState(run_id="r0", ticker="DHG", objective="x")
    audit = build_agent_effectiveness_audit(state)
    assert audit["agent_execution"] == []
    assert audit["tool_execution"] == []
    assert audit["ticker"] == "DHG"
