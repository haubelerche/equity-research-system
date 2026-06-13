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


def test_render_publish_creates_html_pdf_artifact_refs() -> None:
    store = MagicMock()
    runner = ResearchGraphRunner(store=store)
    state = ResearchGraphState(run_id="run_render", ticker="DHG", objective="test")
    state.artifacts["final_report_model"] = {
        "ticker": "DHG",
        "sections": {
            "cover_investment_summary": {"text": "Investment summary"},
            "valuation_and_recommendation": {"text": "Valuation"},
        },
    }

    class FakePublisher:
        def publish(self, *, run_id, ticker, mode="client_final"):
            assert run_id == "run_render"
            assert ticker == "DHG"
            assert mode == "client_final"

            class Published:
                def to_dict(self):
                    return {
                        "html": {"storage_path": "runs/run_render/report.html"},
                        "pdf": {"storage_path": "runs/run_render/report.pdf"},
                    }

                def artifact_refs(self):
                    return [
                        {
                            "artifact_id": "html",
                            "artifact_type": "report_html",
                            "section_key": "report_html",
                            "storage_bucket": "runs",
                            "storage_path": "runs/run_render/report.html",
                            "checksum": "checksum-html",
                            "content_type": "text/html; charset=utf-8",
                            "file_size_bytes": 100,
                            "is_locked": True,
                            "producer": "render_and_publish:DHG",
                        },
                        {
                            "artifact_id": "pdf",
                            "artifact_type": "report_pdf",
                            "section_key": "report_pdf",
                            "storage_bucket": "runs",
                            "storage_path": "runs/run_render/report.pdf",
                            "checksum": "checksum-pdf",
                            "content_type": "application/pdf",
                            "file_size_bytes": 100,
                            "is_locked": True,
                            "producer": "render_and_publish:DHG",
                        },
                    ]

            return Published()

    runner.report_publisher = FakePublisher()

    runner._render_and_publish_final_report(state)

    assert state.artifacts["rendered_report"]["html"]["storage_path"] == "runs/run_render/report.html"
    assert state.artifacts["rendered_report"]["pdf"]["storage_path"] == "runs/run_render/report.pdf"
    assert {ref["section_key"] for ref in state.artifact_refs} >= {"report_html", "report_pdf"}
    assert store.save_artifact.call_count == 2


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
    monkeypatch.setattr(runner, "_render_and_publish_final_report", lambda s: True)

    result = runner._execute_stage(state, "PUBLISH")

    assert result.status == "auto_exported"
    store.update_run_state.assert_any_call("run_pub", "auto_exported", "PUBLISH", finished=True)
