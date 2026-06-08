from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.harness.runner import ResearchGraphRunner
from backend.harness.state import AgentResult, ResearchGraphState


def test_run_agent_receives_bounded_execution_context(monkeypatch) -> None:
    runner = ResearchGraphRunner(store=MagicMock())
    captured: dict = {}
    config = SimpleNamespace(
        agent_id="financial_analyst",
        model="gpt-test",
        allowed_tools=["read_snapshot", "read_ratio_artifact"],
    )
    state = ResearchGraphState(
        run_id="run_context",
        ticker="DHG",
        objective="context test",
        current_stage="FINANCIAL_ANALYST_RUN",
    )
    state.valuation_outputs = {"should_not": "be exposed as raw state"}
    state.artifact_refs.append({
        "artifact_id": "DHG_fact_report",
        "artifact_type": "fact_report_json",
        "section_key": "facts",
        "storage_path": "artifacts/facts/DHG.json",
    })

    monkeypatch.setattr(runner.agent_registry, "get_agent_config", lambda agent_id: config)
    monkeypatch.setattr(runner, "_charge_agent_step", lambda *args, **kwargs: None)

    def fake_run_agent(**kwargs):
        captured.update(kwargs)
        return AgentResult(
            agent_id="financial_analyst",
            action=kwargs["task"],
            status="completed",
            payload={"metric_refs": ["revenue.net"], "period_refs": ["2025FY"]},
            input_summary={"input_refs": ["DHG_fact_report"]},
            confidence=0.9,
        )

    monkeypatch.setattr(runner.model_adapter, "run_agent", fake_run_agent)

    runner._run_agent(state, "financial_analyst", "Review deterministic tables.")

    context = captured["state"]
    assert context["run_id"] == "run_context"
    assert context["stage"] == "FINANCIAL_ANALYST_RUN"
    assert context["allowed_tools"] == ["read_snapshot", "read_ratio_artifact"]
    assert context["input_artifact_refs"][0]["artifact_id"] == "DHG_fact_report"
    assert "required_handoff_fields" in context
    assert "valuation_outputs" not in context


def test_agent_stage_writes_handoff_artifact_and_manifest_ref(tmp_path, monkeypatch) -> None:
    import backend.harness.runner as runner_mod

    runner = ResearchGraphRunner(store=MagicMock())
    monkeypatch.setattr(runner_mod, "ROOT", tmp_path, raising=False)
    state = ResearchGraphState(
        run_id="run_handoff",
        ticker="DHG",
        objective="handoff test",
        current_stage="SUPERVISOR_PLAN",
    )
    state.artifact_refs.append({
        "artifact_id": "input_packet",
        "artifact_type": "run_log_json",
        "section_key": "input",
        "storage_path": "artifacts/input.json",
    })
    result = AgentResult(
        agent_id="supervisor",
        action="plan",
        status="completed",
        payload={"next": "DATA_RETRIEVAL_RUN"},
        input_summary={"input_refs": ["input_packet"]},
        artifact_refs=[{
            "artifact_id": "supervisor_plan",
            "artifact_type": "run_log_json",
            "section_key": "plan",
            "storage_path": "artifacts/plan.json",
        }],
        confidence=0.9,
        next_action="DATA_RETRIEVAL_RUN",
    )

    runner._merge_agent_result(state, result)

    handoffs = state.artifacts["agent_handoffs"]
    assert len(handoffs) == 1
    assert handoffs[0]["agent_id"] == "supervisor"
    assert handoffs[0]["handoff_hash"]
    handoff_ref = next(ref for ref in state.artifact_refs if ref.get("section_key") == "handoff_supervisor")
    handoff_path = handoff_ref["storage_path"]
    written = json.loads(open(handoff_path, encoding="utf-8").read())
    assert written["run_id"] == "run_handoff"
    assert written["recommended_next_stage"] == "DATA_RETRIEVAL_RUN"


def test_financial_analyst_payload_is_manifestable(tmp_path, monkeypatch) -> None:
    import backend.harness.runner as runner_mod

    runner = ResearchGraphRunner(store=MagicMock())
    monkeypatch.setattr(runner_mod, "ROOT", tmp_path, raising=False)
    state = ResearchGraphState(
        run_id="run_financial_analysis",
        ticker="DBD",
        objective="narrative test",
        current_stage="FINANCIAL_ANALYST_RUN",
    )
    result = AgentResult(
        agent_id="financial_analyst",
        action="analyze",
        status="completed",
        payload={"financial_narrative": "Traceable narrative"},
        confidence=0.9,
    )

    runner._merge_agent_result(state, result)

    ref = next(ref for ref in state.artifact_refs if ref.get("section_key") == "financial_analysis")
    artifact = json.loads(open(ref["storage_path"], encoding="utf-8").read())
    assert artifact["payload"]["financial_narrative"] == "Traceable narrative"
