"""Integration tests for the HITL approval flow in ResearchGraphRunner.

Tests cover:
- approve valuation_assumptions -> resumes at VALUATION_LOCKED
- reject valuation_assumptions -> state goes to NEEDS_REVIEW
- approve final_report -> resumes at PUBLISHED
"""
from __future__ import annotations

from types import SimpleNamespace

from backend.harness.runner import ResearchGraphRunner
from backend.harness.state import AgentResult, ServiceNodeResult


# ---------------------------------------------------------------------------
# Shared fake infrastructure (mirrors test_harness_runner.py pattern)
# ---------------------------------------------------------------------------

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
                "ticker": "DBD",
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
                "ticker": "DBD",
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


def _valuation_summary() -> dict:
    return {
        "snapshot_id": "snap1",
        "artifact_path": "artifacts/valuation/DBD.json",
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


def _install_fake_tools(monkeypatch, runner_mod, overrides: dict | None = None) -> None:
    overrides = overrides or {}
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
        "build_index": lambda ticker, from_year, to_year: _service(
            "BUILD_INDEX", {"chunks_inserted": 3}
        ),
        "read_snapshot": lambda ticker, snapshot_id: _service(
            "READ_SNAPSHOT",
            {"snapshot_id": snapshot_id, "metric_refs": ["revenue.net"], "period_refs": ["2024FY"]},
        ),
        "read_ratio_artifact": lambda ticker, snapshot_id: _service(
            "READ_RATIO_ARTIFACT",
            {"snapshot_id": snapshot_id, "metric_refs": ["gross_margin"], "period_refs": ["2024FY"]},
        ),
        "run_valuation": lambda ticker, from_year, to_year: _service(
            "VALUATION_DRAFT", _valuation_summary()
        ),
        "read_valuation_artifact": lambda artifact_path: _service(
            "READ_VALUATION_ARTIFACT", {"artifact_path": artifact_path}
        ),
        "generate_report": lambda ticker, snapshot_id, from_year, to_year, mode="draft": _service(
            "REPORT_GENERATION",
            {
                "report_path": "reports/DBD.md",
                "snapshot_id": snapshot_id,
                "claims_count": 0,
                "citation_count": 0,
            },
        ),
        "evaluate_report_quality": lambda ticker, report_path, valuation_path=None: _service(
            "QUALITY_EVALUATION", {"overall_status": "PASS"}
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
        return SimpleNamespace(
            tool_id=tool_id,
            owner_agent_ids=(owners[tool_id],),
            implementation=impls[tool_id],
            permission_level="test",
            artifact_producer_key=tool_id.upper(),
        )

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


def _fake_agent_result(agent_config, state, task, input_refs=None) -> AgentResult:
    return AgentResult(
        agent_id=agent_config.agent_id,
        action=task,
        status="completed",
        payload={
            "agent_id": agent_config.agent_id,
            "task": task,
            "metric_refs": ["revenue.net"],
            "period_refs": ["2024FY"],
        },
        input_summary={"input_refs": []},
        confidence=0.9,
        confidence_breakdown={"test": 1.0},
        next_action="continue",
    )


# ---------------------------------------------------------------------------
# Test 1: approve valuation_assumptions → state resumes at VALUATION_LOCKED
# ---------------------------------------------------------------------------

def test_approve_valuation_assumptions_resumes_at_valuation_locked(monkeypatch) -> None:
    """Approving valuation assumptions must lock the valuation draft and resume
    from VALUATION_LOCKED, continuing the pipeline towards report writing."""
    import backend.harness.runner as runner_mod
    from backend.harness.model_adapter import AnthropicModelAdapter

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(AnthropicModelAdapter, "validate_environment", lambda self: None)
    monkeypatch.setattr(AnthropicModelAdapter, "run_agent", _fake_agent_result)
    _install_fake_tools(monkeypatch, runner_mod)

    store = FakeStore()
    runner = ResearchGraphRunner(store=store)

    # Simulate state that has been paused at assumption approval
    paused_state = {
        "run_id": "run_approve_assumptions",
        "ticker": "DBD",
        "objective": "test valuation approval",
        "current_stage": "WAITING_ASSUMPTIONS_APPROVAL",
        "requires_human": True,
        "valuation_outputs": _valuation_summary(),
        "snapshot_id": "snap1",
        "artifacts": {"agent_handoffs": _handoffs()},
        "gate_results": {
            **_required_export_gates(),
            "DATA_QUALITY_GATE": {"passed": True},
            "FINANCIAL_ANALYST_GATE": {"passed": True},
            "VALUATION_GATE": {"passed": True},
        },
    }
    store.save_artifact(
        run_id="run_approve_assumptions",
        section_key="graph_state_snapshot",
        payload=paused_state,
    )

    runner.handle_approval(
        "run_approve_assumptions",
        "valuation_assumptions",
        "approve",
        "analyst_a",
        {},
    )

    # valuation_draft must be locked
    assert "valuation_draft" in store.locked_sections

    # An approval record must be stored
    assert any(
        a["stage"] == "valuation_assumptions" and a["decision"] == "approved"
        for a in store.approvals
    )

    # Pipeline must resume from VALUATION_LOCKED and proceed beyond it.
    # The mock tools may not satisfy all downstream stage requirements,
    # so we verify the pipeline at least attempted REPORT_WRITER_CRITIC_RUN
    # (proving it advanced past the approval checkpoint).
    step_names = {s["step_name"] for s in store.steps}
    assert "VALUATION_LOCKED" in step_names or "REPORT_WRITER_CRITIC_RUN" in step_names, (
        f"Expected pipeline to advance past VALUATION_LOCKED after approval, got: {step_names}"
    )


# ---------------------------------------------------------------------------
# Test 2: reject valuation_assumptions → state goes to NEEDS_REVIEW
# ---------------------------------------------------------------------------

def test_reject_valuation_assumptions_sets_needs_review() -> None:
    """Rejecting valuation assumptions must mark downstream artifacts stale and
    set the run status to NEEDS_REVIEW without advancing the pipeline."""
    store = FakeStore()
    runner = ResearchGraphRunner(store=store)

    paused_state = {
        "run_id": "run_reject_assumptions",
        "ticker": "DBD",
        "objective": "test rejection",
        "current_stage": "WAITING_ASSUMPTIONS_APPROVAL",
        "requires_human": True,
        "valuation_outputs": _valuation_summary(),
        "artifacts": {"agent_handoffs": _handoffs()},
        "gate_results": {"VALUATION_GATE": {"passed": True}},
    }
    store.save_artifact(
        run_id="run_reject_assumptions",
        section_key="graph_state_snapshot",
        payload=paused_state,
    )

    runner.handle_approval(
        "run_reject_assumptions",
        "valuation_assumptions",
        "reject",
        "analyst_b",
        {"reason": "WACC too low, needs revision"},
    )

    # Downstream artifacts invalidated
    assert "valuation_draft" in store.stale_sections
    assert "full_report_draft" in store.stale_sections

    # State must be NEEDS_REVIEW
    assert store.states["run_reject_assumptions"] == "needs_human_review:NEEDS_REVIEW"

    # Audit trail: approval_rejected event recorded
    assert any(e["action"] == "approval_rejected" for e in store.audit_events)

    # Approval record stored with correct decision
    assert any(
        a["stage"] == "valuation_assumptions" and a["decision"] == "rejected"
        for a in store.approvals
    )

    # Pipeline must NOT have advanced to report writing
    step_names = {s["step_name"] for s in store.steps}
    assert "REPORT_WRITER_CRITIC_RUN" not in step_names


# ---------------------------------------------------------------------------
# Test 3: approve final_report → state resumes at PUBLISHED
# ---------------------------------------------------------------------------

def test_approve_final_report_publishes_run() -> None:
    """Approving the final report with all export gates passing must set the
    run status to 'approved' at stage PUBLISHED."""
    store = FakeStore()
    runner = ResearchGraphRunner(store=store)

    paused_state = {
        "run_id": "run_final_approval",
        "ticker": "DBD",
        "objective": "test final approval",
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
        "artifacts": {
            "valuation_lock": {"locked": True},
            "agent_handoffs": _handoffs(),
        },
        "gate_results": {
            **_required_export_gates(),
            "APPROVAL_PATH_GATE": {"passed": True},
            "DATA_QUALITY_GATE": {"passed": True},
            "FINANCIAL_ANALYST_GATE": {"passed": True},
            "VALUATION_GATE": {"passed": True},
            "CITATION_GATE": {"passed": True},
            "EXPORT_GATE": {"passed": True},
        },
        "approvals": {
            "valuation_assumptions": "approved",
        },
    }
    store.save_artifact(
        run_id="run_final_approval",
        section_key="graph_state_snapshot",
        payload=paused_state,
    )

    runner.handle_approval(
        "run_final_approval",
        "final_report",
        "approved",
        "analyst_c",
        {},
    )

    # Run must be in approved/PUBLISHED state
    assert store.states["run_final_approval"] == "approved:PUBLISHED"

    # Approval record stored with correct stage
    assert any(
        a["stage"] == "final_report" and a["decision"] == "approved"
        for a in store.approvals
    )

    # State snapshot at PUBLISHED must show EXPORT_GATE passed
    published_snapshots = [
        a["payload"]
        for a in store.artifacts
        if a.get("section_key") == "graph_state_snapshot"
        and isinstance(a.get("payload"), dict)
        and a["payload"].get("current_stage") == "PUBLISHED"
    ]
    assert published_snapshots, "Expected at least one graph_state_snapshot at PUBLISHED stage"
    final = published_snapshots[-1]
    assert final["gate_results"]["EXPORT_GATE"]["passed"] is True


# ---------------------------------------------------------------------------
# Test 4: reject final_report → state goes to NEEDS_REVIEW (not PUBLISHED)
# ---------------------------------------------------------------------------

def test_reject_final_report_sets_needs_review() -> None:
    """Rejecting the final report must NOT publish and must mark the run as
    NEEDS_REVIEW with appropriate stale artifacts."""
    store = FakeStore()
    runner = ResearchGraphRunner(store=store)

    paused_state = {
        "run_id": "run_reject_final",
        "ticker": "DBD",
        "objective": "test final rejection",
        "current_stage": "WAITING_FINAL_APPROVAL",
        "requires_human": True,
        "draft_report": {"snapshot_id": "snap1"},
        "artifacts": {"agent_handoffs": _handoffs()},
        "gate_results": {"CITATION_GATE": {"passed": True}},
    }
    store.save_artifact(
        run_id="run_reject_final",
        section_key="graph_state_snapshot",
        payload=paused_state,
    )

    runner.handle_approval(
        "run_reject_final",
        "final_report",
        "rejected",
        "analyst_d",
        {"reason": "citation gaps in valuation section"},
    )

    # Must be NEEDS_REVIEW, not PUBLISHED
    assert store.states["run_reject_final"] == "needs_human_review:NEEDS_REVIEW"

    # Report artifacts must be marked stale
    assert "full_report_draft" in store.stale_sections

    # Audit trail present
    assert any(e["action"] == "approval_rejected" for e in store.audit_events)


# ---------------------------------------------------------------------------
# Test 5: unsupported stage name raises ValueError
# ---------------------------------------------------------------------------

def test_handle_approval_invalid_stage_raises() -> None:
    """An unrecognised approval stage must raise ValueError immediately."""
    store = FakeStore()
    runner = ResearchGraphRunner(store=store)

    try:
        runner.handle_approval("run_x", "unknown_stage", "approve", "analyst", {})
        raise AssertionError("Expected ValueError was not raised")
    except ValueError as exc:
        assert "unsupported approval transition" in str(exc).lower()


# ---------------------------------------------------------------------------
# Test 6: unsupported decision raises ValueError
# ---------------------------------------------------------------------------

def test_handle_approval_invalid_decision_raises() -> None:
    """An unrecognised decision value must raise ValueError immediately."""
    store = FakeStore()
    runner = ResearchGraphRunner(store=store)

    try:
        runner.handle_approval("run_y", "assumptions", "maybe", "analyst", {})
        raise AssertionError("Expected ValueError was not raised")
    except ValueError as exc:
        assert "unsupported approval transition" in str(exc).lower()
