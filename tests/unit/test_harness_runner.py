from __future__ import annotations

from types import SimpleNamespace

from backend.harness.runner import ResearchGraphRunner
from backend.harness.state import AgentResult, ServiceNodeResult


class FakeStore:
    def __init__(self) -> None:
        self.steps: list[dict] = []
        self.artifacts: list[dict] = []
        self.states: dict[str, str] = {}
        self.runs: dict[str, dict] = {}
        self.approvals: list[dict] = []
        self.audit_events: list[dict] = []
        self.locked_sections: list[str] = []
        self.stale_sections: list[str] = []

    def check_schema_version(self) -> None:
        return None

    def add_step(self, **kwargs):
        self.steps.append(kwargs)
        return len(self.steps)

    def close_step(self, step_id, status, **kwargs) -> None:
        self.steps[step_id - 1]["closed_status"] = status
        self.steps[step_id - 1].update(kwargs)

    def update_run_state(self, run_id, status, stage, **kwargs) -> None:
        self.states[run_id] = f"{status}:{stage}"
        self.runs.setdefault(
            run_id,
            {
                "ticker": "DHG",
                "run_type": "full_report",
                "request_json": {"objective": "test"},
                "config_snapshot_json": {},
                "flags_json": {},
            },
        )
        self.runs[run_id]["status"] = status
        self.runs[run_id]["current_stage"] = stage

    def save_artifact(self, **kwargs) -> None:
        self.artifacts.append(kwargs)

    def add_audit_event(self, **kwargs) -> None:
        self.audit_events.append(kwargs)

    def add_budget_entry(self, **kwargs) -> None:
        return None

    def run_cost_usd(self, run_id) -> float:
        return 0.0

    def get_run(self, run_id):
        return self.runs.get(
            run_id,
            {
                "ticker": "DHG",
                "run_type": "full_report",
                "request_json": {"objective": "test"},
                "config_snapshot_json": {},
                "flags_json": {},
            },
        )

    def latest_graph_state(self, run_id):
        snapshots = [
            a["payload"]
            for a in self.artifacts
            if a.get("run_id") == run_id and a.get("section_key") == "graph_state_snapshot"
        ]
        return snapshots[-1] if snapshots else None

    def add_approval(self, **kwargs):
        self.approvals.append(kwargs)

    def lock_artifacts(self, run_id, section_keys):
        self.locked_sections.extend(section_keys)
        return len(section_keys)

    def mark_artifacts_stale(self, run_id, section_keys, reason):
        self.stale_sections.extend(section_keys)
        return len(section_keys)


def _service(node_name: str, summary: dict) -> ServiceNodeResult:
    return ServiceNodeResult(node_name=node_name, status="completed", summary=summary)


def _tool_spec(tool_id: str, owner: str, impl):
    return SimpleNamespace(
        tool_id=tool_id,
        owner_agent_ids=(owner,),
        implementation=impl,
        permission_level="test",
        artifact_producer_key=tool_id.upper(),
    )


def _install_fake_tools(monkeypatch, runner_mod, overrides: dict | None = None) -> None:
    overrides = overrides or {}
    valuation_summary = {
        "snapshot_id": "snap1",
        "artifact_path": "artifacts/valuation/DHG.json",
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
        "formula_traces": [
            {
                "trace_id": "trace_fcff",
                "formula_id": "fcff_target",
                "formula_version": "valuation_v1",
                "calculation_steps": [{"step": "sum_pv_fcff"}],
            }
        ],
    }
    impls = {
        "auto_ingest": lambda ticker, from_year, to_year, ocr=False: _service(
            "AUTO_INGEST",
            {
                "web_ingest_attempted": True,
                "cafef_rows": 1,
                "pdf_rows": 0,
                "ocr_candidates": 0,
                "promoted": 0,
                "official_ready": False,
                "continued_with_tier2_or_tier3_fallback": True,
            },
        ),
        "build_facts": lambda ticker, from_year, to_year: _service(
            "BUILD_FACTS",
            {"valuation_gate": "pass", "snapshot_id": "snap1", "blocking_reasons": []},
        ),
        "build_index": lambda ticker, from_year, to_year: _service("BUILD_INDEX", {"chunks_inserted": 3}),
        "read_snapshot": lambda ticker, snapshot_id: _service(
            "READ_SNAPSHOT",
            {"snapshot_id": snapshot_id, "metric_refs": ["revenue.net"], "period_refs": ["2025FY"]},
        ),
        "read_ratio_artifact": lambda ticker, snapshot_id: _service(
            "READ_RATIO_ARTIFACT",
            {"snapshot_id": snapshot_id, "metric_refs": ["gross_margin"], "period_refs": ["2025FY"]},
        ),
        "run_valuation": lambda ticker, from_year, to_year: _service("VALUATION_DRAFT", valuation_summary),
        "read_valuation_artifact": lambda artifact_path: _service(
            "READ_VALUATION_ARTIFACT",
            {"artifact_path": artifact_path},
        ),
        "generate_report": lambda ticker, snapshot_id, from_year, to_year, mode="draft": _service(
            "REPORT_GENERATION",
            {"report_path": "reports/DHG.md", "snapshot_id": snapshot_id, "claims_count": 0, "citation_count": 0},
        ),
        "evaluate_report_quality": lambda ticker, report_path, valuation_path=None: _service(
            "QUALITY_EVALUATION",
            {"overall_status": "PASS"},
        ),
    }
    impls.update(overrides)
    owners = {
        "auto_ingest": "data_retrieval",
        "build_facts": "data_retrieval",
        "build_index": "data_retrieval",
        "read_snapshot": "financial_analyst",
        "read_ratio_artifact": "financial_analyst",
        "run_valuation": "valuation",
        "read_valuation_artifact": "valuation",
        "generate_report": "report_writer_critic",
        "evaluate_report_quality": "report_writer_critic",
    }

    def fake_get_tool(self, tool_id):
        return _tool_spec(tool_id, owners[tool_id], impls[tool_id])

    def fake_run_tool(self, state, agent_id, tool_id, *args, **kwargs):
        result = impls[tool_id](*args, **kwargs)
        result.gate_inputs.setdefault(
            "tool_permission",
            {
                "tool_id": tool_id,
                "agent_id": agent_id,
                "permission_level": "test",
                "artifact_producer_key": tool_id.upper(),
            },
        )
        return result

    monkeypatch.setattr(runner_mod.ToolRegistry, "get_tool", fake_get_tool)
    monkeypatch.setattr(runner_mod.ToolRegistry, "validate_agent_tool_policy", lambda self, configs: None)
    monkeypatch.setattr(runner_mod.ResearchGraphRunner, "_run_tool", fake_run_tool)


def _handoffs() -> list[dict]:
    return [
        {
            "agent_id": agent_id,
            "handoff_hash": f"hash_{agent_id}",
            "review_status": "completed",
        }
        for agent_id in [
            "supervisor",
            "data_retrieval",
            "financial_analyst",
            "valuation",
            "report_writer_critic",
        ]
    ]


def _required_export_gates() -> dict:
    return {
        "TOOL_PERMISSION_GATE": {"passed": True},
        "ARTIFACT_MANIFEST_GATE": {"passed": True},
        "FORMULA_TRACE_GATE": {"passed": True},
        "EVIDENCE_PACKET_GATE": {"passed": True},
        "AGENT_HANDOFF_GATE": {"passed": True},
    }


def test_runner_happy_path_stops_at_assumption_approval(monkeypatch) -> None:
    import backend.harness.runner as runner_mod
    from backend.harness.model_adapter import OpenAIModelAdapter

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(OpenAIModelAdapter, "validate_environment", lambda self: None)
    monkeypatch.setattr(
        OpenAIModelAdapter,
        "run_agent",
        lambda self, agent_config, state, task, input_refs=None: AgentResult(
            agent_id=agent_config.agent_id,
            action=task,
            status="completed",
            payload={
                "agent_id": agent_config.agent_id,
                "task": task,
                "metric_refs": ["revenue.net"],
                "period_refs": ["2025FY"],
            },
            input_summary={"input_refs": ["snapshot_fact_report", "ratio_artifact"]},
            confidence=0.9,
            confidence_breakdown={"test": 1.0},
            next_action="continue",
        ),
    )

    _install_fake_tools(monkeypatch, runner_mod)

    store = FakeStore()
    runner = ResearchGraphRunner(store=store)
    context = SimpleNamespace(
        run_id="run1",
        ticker="DHG",
        run_type="full_report",
        objective="test",
        policy={},
        flags={},
    )

    runner.execute(context)

    assert store.states["run1"] == "needs_human_review:WAITING_ASSUMPTIONS_APPROVAL"
    assert any(a["artifact_type"] == "run_log_json" and a["section_key"] == "graph_state_snapshot" for a in store.artifacts)
    assert all(step["status"] == "running" for step in store.steps)
    assert all(step["closed_status"] == "completed" for step in store.steps)
    assert {step["step_name"] for step in store.steps}.issubset(set(runner_mod.GRAPH_STAGES))
    assert any(step["step_name"] == "SUPERVISOR_PLAN" for step in store.steps)
    assert any(step["step_name"] == "DATA_RETRIEVAL_RUN" for step in store.steps)
    assert any(e["action"] == "agent_message" for e in store.audit_events)
    assert any(e["action"] == "tool_call" for e in store.audit_events)


def test_assumption_approval_resumes_to_final_approval(monkeypatch) -> None:
    import backend.harness.runner as runner_mod
    from backend.harness.model_adapter import OpenAIModelAdapter

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(OpenAIModelAdapter, "validate_environment", lambda self: None)
    monkeypatch.setattr(
        OpenAIModelAdapter,
        "run_agent",
        lambda self, agent_config, state, task, input_refs=None: AgentResult(
            agent_id=agent_config.agent_id,
            action=task,
            status="completed",
            payload={
                "agent_id": agent_config.agent_id,
                "metric_refs": ["revenue.net"],
                "period_refs": ["2025FY"],
            },
            input_summary={"input_refs": ["snapshot_fact_report", "ratio_artifact"]},
            confidence=0.9,
            confidence_breakdown={"test": 1.0},
            next_action="continue",
        ),
    )
    _install_fake_tools(monkeypatch, runner_mod)

    store = FakeStore()
    runner = ResearchGraphRunner(store=store)
    paused_state = {
        "run_id": "run1",
        "ticker": "DHG",
        "objective": "test",
        "current_stage": "WAITING_ASSUMPTIONS_APPROVAL",
        "requires_human": True,
        "valuation_outputs": {
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
                "formula_traces": [
                    {
                        "trace_id": "trace_fcff",
                        "formula_id": "fcff_target",
                        "formula_version": "valuation_v1",
                        "calculation_steps": [{"step": "sum_pv_fcff"}],
                    }
                ],
            },
            "snapshot_id": "snap1",
            "artifacts": {"agent_handoffs": _handoffs()},
            "gate_results": {
                **_required_export_gates(),
                "DATA_QUALITY_GATE": {"passed": True},
                "FINANCIAL_ANALYST_GATE": {"passed": True},
                "VALUATION_GATE": {"passed": True},
            },
    }
    store.save_artifact(run_id="run1", section_key="graph_state_snapshot", payload=paused_state)

    runner.handle_approval("run1", "assumptions", "approve", "analyst", {})

    assert "valuation_draft" in store.locked_sections
    assert store.states["run1"] == "needs_human_review:WAITING_FINAL_APPROVAL"
    assert any(step["step_name"] == "REPORT_WRITER_CRITIC_RUN" for step in store.steps)


def test_assumption_rejection_invalidates_downstream_artifacts() -> None:
    store = FakeStore()
    runner = ResearchGraphRunner(store=store)
    paused_state = {
        "run_id": "run1",
        "ticker": "DHG",
        "objective": "test",
        "current_stage": "WAITING_ASSUMPTIONS_APPROVAL",
        "requires_human": True,
    }
    store.save_artifact(run_id="run1", section_key="graph_state_snapshot", payload=paused_state)

    runner.handle_approval("run1", "valuation_assumptions", "reject", "analyst", {"reason": "revise WACC"})

    assert "valuation_draft" in store.stale_sections
    assert "full_report_draft" in store.stale_sections
    assert store.states["run1"] == "needs_human_review:NEEDS_REVIEW"
    assert any(e["action"] == "approval_rejected" for e in store.audit_events)


def test_final_approval_publishes_only_after_export_gate() -> None:
    store = FakeStore()
    runner = ResearchGraphRunner(store=store)
    paused_state = {
        "run_id": "run1",
        "ticker": "DHG",
        "objective": "test",
        "current_stage": "WAITING_FINAL_APPROVAL",
        "requires_human": True,
        "valuation_outputs": {
            "snapshot_id": "snap1",
            "formula_traces": [
                {
                    "trace_id": "trace_fcff",
                    "formula_id": "fcff_target",
                    "formula_version": "valuation_v1",
                    "calculation_steps": [{"step": "sum_pv_fcff"}],
                }
            ],
        },
        "draft_report": {"snapshot_id": "snap1"},
        "artifacts": {"valuation_lock": {"locked": True}, "agent_handoffs": _handoffs()},
        "gate_results": {
            **_required_export_gates(),
            "APPROVAL_PATH_GATE": {"passed": True},
            "DATA_QUALITY_GATE": {"passed": True},
            "FINANCIAL_ANALYST_GATE": {"passed": True},
            "VALUATION_GATE": {"passed": True},
            "CITATION_GATE": {"passed": True},
            "EXPORT_GATE": {"passed": True},
        },
    }
    store.save_artifact(run_id="run1", section_key="graph_state_snapshot", payload=paused_state)

    runner.handle_approval("run1", "final", "approved", "analyst", {})

    assert store.states["run1"] == "approved:PUBLISHED"
    assert store.approvals[-1]["stage"] == "final_report"
    assert any(
        artifact["payload"]["gate_results"]["EXPORT_GATE"]["passed"]
        for artifact in store.artifacts
        if artifact.get("section_key") == "graph_state_snapshot"
    )
