from __future__ import annotations

from unittest.mock import MagicMock

from backend.harness.agent_registry import AgentRegistry
from backend.harness.graph import GRAPH_STAGES
from backend.harness.gates import pass_gate
from backend.harness.runner import ResearchGraphRunner
from backend.harness.state import ResearchGraphState, ServiceNodeResult


def test_registry_contains_exactly_six_typed_agents() -> None:
    configs = AgentRegistry().load()
    assert set(configs) == {
        "research_manager",
        "data_evidence",
        "financial_analysis",
        "forecast_valuation",
        "thesis_report",
        "senior_critic",
    }
    assert all(config.output_schema != "AgentResult" for config in configs.values())


def test_graph_has_exactly_nine_stages() -> None:
    assert GRAPH_STAGES == [
        "PREFLIGHT",
        "PLAN",
        "INGEST_AND_VALIDATE",
        "ANALYZE",
        "FORECAST_AND_VALUE",
        "WRITE_REPORT",
        "REVIEW",
        "EXPORT_GATES",
        "PUBLISH",
    ]
    assert "SUPERVISOR_PLAN" not in GRAPH_STAGES
    assert "PUBLISHED" not in GRAPH_STAGES
    assert "WAITING_ASSUMPTION_APPROVAL" not in GRAPH_STAGES
    assert "WAITING_FINAL_APPROVAL" not in GRAPH_STAGES


def test_agent_context_includes_actual_artifact_content() -> None:
    runner = ResearchGraphRunner(store=MagicMock())
    state = ResearchGraphState(run_id="run1", ticker="DHG", objective="test")
    state.current_stage = "ANALYZE"
    state.artifacts["evidence_pack"] = {"limitations": ["sample"]}

    context = runner._build_agent_context(state, "financial_analysis", "analyze")

    assert context.input_artifacts["evidence_pack"]["limitations"] == ["sample"]


def test_structured_evidence_followup_is_limited_to_one() -> None:
    runner = ResearchGraphRunner(store=MagicMock())
    state = ResearchGraphState(run_id="run1", ticker="DHG", objective="test")
    request = {"evidence_request": {"request_id": "r1", "critical": False}}

    runner._handle_evidence_request(state, "financial_analysis", request)
    runner._handle_evidence_request(state, "financial_analysis", request)

    assert state.evidence_followups["financial_analysis"] == 1
    assert len(state.artifacts["structured_evidence_requests"]) == 1
    assert len(state.artifacts["insufficient_evidence"]) == 1


def test_run_until_pause_keeps_the_actual_failed_stage(monkeypatch) -> None:
    runner = ResearchGraphRunner(store=MagicMock())
    state = ResearchGraphState(run_id="run_failed_stage", ticker="DHG", objective="test")

    def fake_run_stage(current, stage):
        if stage == "PLAN":
            current.status = "failed"
            current.blocking_reason = "research_manager_failed"
        return current

    monkeypatch.setattr(runner, "_run_stage", fake_run_stage)
    monkeypatch.setattr(runner, "_write_evidence_packet", lambda current: None)
    monkeypatch.setattr(runner, "_write_run_manifest", lambda current: None)

    result = runner.run_until_pause(state)

    assert result.current_stage == "PLAN"
    assert result.status == "failed"


def test_finalize_publish_locks_model_without_rendering() -> None:
    store = MagicMock()
    runner = ResearchGraphRunner(store=store)
    state = ResearchGraphState(run_id="run_render", ticker="DHG", objective="test")
    state.artifacts["publishable_final_report_model"] = {
        "ticker": "DHG",
        "sections": {"cover_investment_summary": {"text": "x"}},
    }

    result = runner._finalize_publish(state)

    assert result is True
    # No rendered_report artifact — rendering is an explicit user action.
    assert "rendered_report" not in state.artifacts


def test_finalize_publish_blocks_when_model_missing() -> None:
    store = MagicMock()
    runner = ResearchGraphRunner(store=store)
    state = ResearchGraphState(run_id="run_no_model", ticker="DHG", objective="test")

    result = runner._finalize_publish(state)

    assert result is False
    assert state.status == "blocked"
    assert "publishable_final_report_model_missing" in state.blocking_reason
    store.update_run_state.assert_called_once_with("run_no_model", "blocked", "PUBLISH")


def test_report_artifact_lifecycle_promotes_locked_models() -> None:
    store = MagicMock()
    runner = ResearchGraphRunner(store=store)
    state = ResearchGraphState(run_id="run_lifecycle", ticker="DHG", objective="test")
    state.artifacts["report_candidate_model"] = {"run_id": "run_lifecycle", "ticker": "DHG"}

    runner._promote_report_model(
        state,
        source_key="report_candidate_model",
        target_key="review_passed_report_model",
        producer="review_gate_promotion",
        locked=True,
    )

    assert "final_report_model" not in state.artifacts
    assert state.artifacts["review_passed_report_model"] == state.artifacts["report_candidate_model"]
    assert state.artifact_refs[-1]["section_key"] == "review_passed_report_model"
    assert state.artifact_refs[-1]["is_locked"] is True


def test_draft_forecast_stage_uses_deterministic_fast_path(monkeypatch) -> None:
    runner = ResearchGraphRunner(store=MagicMock())
    state = ResearchGraphState(
        run_id="run_fast_draft",
        ticker="DHG",
        objective="draft export",
        policy={"draft_mode": True},
        snapshot_id="snap-001",
    )
    state.current_stage = "FORECAST_AND_VALUE"

    tool_calls: list[str] = []

    def fake_run_tool(current, agent_id, tool_id, *args, **kwargs):
        tool_calls.append(tool_id)
        if tool_id == "run_forecast":
            return ServiceNodeResult(
                node_name="FORECAST_MODEL",
                status="completed",
                summary={
                    "ticker": "DHG",
                    "snapshot_id": "snap-001",
                    "forecast_horizon": {"start_year": 2026, "end_year": 2030},
                    "forecast_quality_checks": {"driver_support_check": True},
                    "limitations": [],
                },
            )
        if tool_id == "run_valuation":
            return ServiceNodeResult(
                node_name="VALUATION_DRAFT",
                status="completed",
                summary={
                    "ticker": "DHG",
                    "snapshot_id": "snap-001",
                    "storage_path": "run_fast_draft/valuation.json",
                    "formula_traces": [{"formula_id": "fcff", "formula_version": "1", "calculation_steps": [{"step": "ok"}]}],
                },
            )
        if tool_id == "read_valuation_artifact":
            return ServiceNodeResult(
                node_name="READ_VALUATION_ARTIFACT",
                status="completed",
                summary={
                    "ticker": "DHG",
                    "snapshot_id": "snap-001",
                    "storage_path": "run_fast_draft/valuation.json",
                    "formula_trace_status": "present",
                    "formula_traces": [{"formula_id": "fcff", "formula_version": "1", "calculation_steps": [{"step": "ok"}]}],
                },
            )
        raise AssertionError(f"unexpected tool: {tool_id}")

    monkeypatch.setattr(runner, "_run_tool", fake_run_tool)
    monkeypatch.setattr(
        runner,
        "_run_agent",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("forecast LLM should be skipped in draft mode")),
    )
    monkeypatch.setattr("backend.harness.runner.forecast_quality_gate", lambda forecast: pass_gate("FORECAST_QUALITY_GATE"))
    monkeypatch.setattr("backend.harness.runner.valuation_gate", lambda valuation: pass_gate("VALUATION_GATE"))
    monkeypatch.setattr(
        "backend.harness.runner.valuation_reconciliation_gate",
        lambda valuation, market_snapshot: pass_gate("VALUATION_RECONCILIATION_GATE"),
    )

    result = runner._execute_stage(state, "FORECAST_AND_VALUE")

    assert tool_calls == ["run_forecast", "run_valuation", "read_valuation_artifact"]
    assert result.artifacts["forecast_narrative"]["mode"] == "draft_fast_path"
    assert "valuation_proposal" not in result.artifacts
    assert result.artifacts["research_lock"]["locked"] is True


def test_publish_sets_auto_exported_status(monkeypatch) -> None:
    store = MagicMock()
    runner = ResearchGraphRunner(store=store)
    state = ResearchGraphState(run_id="run_pub", ticker="DHG", objective="test")
    monkeypatch.setattr(runner, "_finalize_publish", lambda s: True)

    result = runner._execute_stage(state, "PUBLISH")

    assert result.status == "auto_exported"
    store.update_run_state.assert_any_call("run_pub", "auto_exported", "PUBLISH", finished=True)


def test_review_does_not_auto_revise(monkeypatch) -> None:
    from backend.harness.gates import pass_gate

    runner = ResearchGraphRunner(store=MagicMock())
    state = ResearchGraphState(run_id="run_rev", ticker="DHG", objective="test")
    state.current_stage = "REVIEW"
    state.draft_report = {"claims": [], "storage_path": "runs/run_rev/report.json"}

    agent_calls: list[str] = []

    class FakeAgentResult:
        def __init__(self, agent_id, payload):
            self.agent_id = agent_id
            self.payload = payload
            self.artifact_refs = []
            self.evidence_refs = []

    def fake_run_agent(s, agent_id, task):
        agent_calls.append(agent_id)
        # Critic asks for a revision — the old code would have triggered a rewrite.
        return FakeAgentResult(agent_id, {"decision": "revision_required", "scorecard": {}, "findings": []})

    def fake_run_tool(s, agent_id, tool_id, *a, **k):
        return ServiceNodeResult(node_name="QUALITY", status="completed", summary={})

    monkeypatch.setattr(runner, "_run_agent", fake_run_agent)
    monkeypatch.setattr(runner, "_run_tool", fake_run_tool)
    monkeypatch.setattr(runner, "_merge_agent_result", lambda s, r: None)
    monkeypatch.setattr(runner, "_merge_result", lambda s, r: None)
    monkeypatch.setattr("backend.harness.runner.report_completeness_gate", lambda r: pass_gate("REPORT_COMPLETENESS_GATE"))
    monkeypatch.setattr("backend.harness.runner.senior_critic_gate", lambda c: pass_gate("SENIOR_CRITIC_GATE"))
    monkeypatch.setattr("backend.harness.runner.citation_gate", lambda r: pass_gate("CITATION_GATE"))

    result = runner._execute_stage(state, "REVIEW")

    # Only the senior critic runs; the thesis writer is NOT re-invoked for a revision.
    assert agent_calls == ["senior_critic"]
    assert "revised_report_draft" not in result.artifacts
    assert result.report_revision_count == 0


def test_plan_stage_is_deterministic_no_llm(monkeypatch) -> None:
    from backend.harness.contracts import validate_agent_artifact

    runner = ResearchGraphRunner(store=MagicMock())
    state = ResearchGraphState(run_id="run_plan", ticker="DHG", objective="test")
    monkeypatch.setattr(
        runner, "_run_agent",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("PLAN must not call the LLM")),
    )

    result = runner._execute_stage(state, "PLAN")

    assert result.plan["producer"] == "research_manager_agent"
    assert result.plan["run_id"] == "run_plan"
    assert "deterministic" in result.plan["known_constraints"][0]
    # Must satisfy the same contract the LLM artifact did.
    validate_agent_artifact("ResearchManagerArtifact", result.plan)
