from __future__ import annotations

import json
from typing import Any

from backend.agents import AuditAgent, ResearchAgent
from backend.harness.gates import citation_gate, data_quality_gate, export_gate, valuation_gate
from backend.harness.graph import GRAPH_STAGES, build_langgraph
from backend.harness.state import ResearchGraphState, stable_hash
from backend.harness.tools import (
    build_facts_tool,
    build_index_tool,
    evaluate_quality_tool,
    generate_report_tool,
    run_valuation_tool,
)
from backend.runtime_store import RuntimeStore
from backend.services import BudgetGuard
from backend.settings import Settings, settings
from backend.utils import deterministic_id


PUBLIC_TO_DB_APPROVAL_STAGE = {
    "assumptions": "valuation_assumptions",
    "valuation_assumptions": "valuation_assumptions",
    "report_draft": "report_draft",
    "final": "final_report",
    "final_report": "final_report",
}
PUBLIC_TO_DB_APPROVAL_DECISION = {
    "approve": "approved",
    "approved": "approved",
    "reject": "rejected",
    "rejected": "rejected",
    "needs_revision": "needs_revision",
}


class ResearchGraphRunner:
    def __init__(self, store: RuntimeStore, app_settings: Settings | None = None) -> None:
        self.store = store
        self.settings = app_settings or settings
        self.budget = BudgetGuard(store, self.settings)
        self.research_agent = ResearchAgent()
        self.audit_agent = AuditAgent()
        self._compiled_graph = build_langgraph(self._node_map())

    def execute(self, context) -> None:
        state = ResearchGraphState(
            run_id=context.run_id,
            ticker=context.ticker,
            run_type=context.run_type,
            objective=context.objective,
            policy=context.policy,
            flags=context.flags,
        )
        self.run_until_pause(state)

    def run_until_pause(self, state: ResearchGraphState | dict[str, Any], start_stage: str = "PREFLIGHT") -> ResearchGraphState:
        current = state if isinstance(state, ResearchGraphState) else ResearchGraphState(**state)
        if self._compiled_graph is not None and start_stage == "PREFLIGHT":
            # We still use explicit node execution for pause-aware checkpoints; this
            # compiled graph is retained as a validation artifact for LangGraph wiring.
            current.artifacts.setdefault("langgraph_compiled", {"available": True})

        stages = GRAPH_STAGES[GRAPH_STAGES.index(start_stage):]
        for stage in stages:
            current.current_stage = stage
            if current.requires_human or current.blocking_reason:
                break
            current = self._run_stage(current, stage)
            if stage in {"WAITING_ASSUMPTIONS_APPROVAL", "WAITING_FINAL_APPROVAL", "PUBLISHED"}:
                break
        return current

    def handle_approval(self, run_id: str, stage: str, decision: str, reviewer: str, feedback_patch: dict[str, Any]) -> None:
        db_stage = PUBLIC_TO_DB_APPROVAL_STAGE.get(stage)
        db_decision = PUBLIC_TO_DB_APPROVAL_DECISION.get(decision)
        if db_stage is None or db_decision is None:
            raise ValueError(f"Unsupported approval transition: stage={stage!r}, decision={decision!r}")

        self.store.add_approval(
            run_id=run_id,
            stage=db_stage,
            decision=db_decision,
            reviewer=reviewer,
            feedback_patch=feedback_patch,
        )

        run = self.store.get_run(run_id)
        if run is None:
            raise ValueError(f"Run not found: {run_id}")

        if db_decision != "approved":
            self.store.update_run_state(run_id=run_id, status="needs_human_review", stage="NEEDS_REVIEW")
            self.store.add_audit_event(
                run_id=run_id,
                actor="ResearchGraphRunner",
                action="approval_rejected",
                payload={"stage": db_stage, "reviewer": reviewer, "feedback_patch": feedback_patch},
            )
            return

        latest = self.store.latest_graph_state(run_id)
        state = ResearchGraphState(**latest) if latest else ResearchGraphState(
            run_id=run_id,
            ticker=run["ticker"],
            run_type=run["run_type"],
            objective=(run.get("request_json") or {}).get("objective", "Resume approved research run."),
            policy=run.get("config_snapshot_json") or {},
            flags=run.get("flags_json") or {},
        )
        state.requires_human = False
        state.blocking_reason = None
        state.approvals[db_stage] = "approved"

        if db_stage == "valuation_assumptions":
            self.run_until_pause(state, start_stage="VALUATION_LOCKED")
        elif db_stage == "final_report":
            self.run_until_pause(state, start_stage="PUBLISHED")

    def _node_map(self):
        return {stage: (lambda state, s=stage: self._run_stage(ResearchGraphState(**state), s).model_dump(mode="json")) for stage in GRAPH_STAGES}

    def _run_stage(self, state: ResearchGraphState, stage: str) -> ResearchGraphState:
        input_hash = state.stable_hash()
        step_id = self.store.add_step(
            run_id=state.run_id,
            step_name=stage,
            agent_name=self._agent_name(stage),
            status="running",
            policy_reason=self._policy_reason(stage),
            input_hash=input_hash,
        )
        try:
            state = self._execute_stage(state, stage)
            output_hash = state.stable_hash()
            self.store.close_step(step_id, "completed", output_hash=output_hash)
            self._checkpoint(state)
            return state
        except Exception as exc:  # noqa: BLE001
            state.status = "needs_human_review" if state.requires_human else "failed"
            state.blocking_reason = f"{stage}: {exc}"
            state.errors.append(str(exc))
            self.store.close_step(step_id, "failed", error_message=str(exc), metadata={"stage": stage})
            self.store.update_run_state(
                state.run_id,
                "needs_human_review" if state.requires_human else "failed",
                stage,
                finished=not state.requires_human,
            )
            self._checkpoint(state)
            return state

    def _execute_stage(self, state: ResearchGraphState, stage: str) -> ResearchGraphState:
        self.store.update_run_state(state.run_id, self._db_status_for_stage(stage), stage)

        if stage == "PREFLIGHT":
            self._preflight(state)
        elif stage == "BUILD_FACTS":
            result = build_facts_tool(state.ticker, state.from_year, state.to_year)
            state.artifacts["build_facts"] = result.summary
            state.snapshot_id = result.summary.get("snapshot_id")
            self._merge_result(state, result)
        elif stage == "DATA_QUALITY_GATE":
            gate = data_quality_gate(state.artifacts.get("build_facts", {}))
            self._record_gate(state, gate)
        elif stage == "BUILD_INDEX":
            result = build_index_tool(state.ticker, state.from_year, state.to_year)
            state.artifacts["index"] = result.summary
            self._merge_result(state, result)
        elif stage == "VALUATION_DRAFT":
            result = run_valuation_tool(state.ticker, state.from_year, state.to_year)
            state.artifacts["valuation"] = result.summary
            state.snapshot_id = result.summary.get("snapshot_id") or state.snapshot_id
            self._merge_result(state, result)
        elif stage == "VALUATION_GATE":
            gate = valuation_gate(state.artifacts.get("valuation", {}))
            self._record_gate(state, gate)
        elif stage == "WAITING_ASSUMPTIONS_APPROVAL":
            state.status = "needs_human_review"
            state.requires_human = True
            state.next_resume_stage = "VALUATION_LOCKED"
            self.store.update_run_state(state.run_id, "needs_human_review", stage)
        elif stage == "VALUATION_LOCKED":
            state.artifacts.setdefault("valuation_lock", {"locked": True, "approval": state.approvals.get("valuation_assumptions")})
            state.status = "running"
        elif stage == "REPORT_GENERATION":
            result = generate_report_tool(state.ticker, state.snapshot_id, state.from_year, state.to_year, mode="draft")
            state.artifacts["report"] = result.summary
            self._merge_result(state, result)
        elif stage == "QUALITY_EVALUATION":
            report_path = (state.artifacts.get("report") or {}).get("report_path")
            result = evaluate_quality_tool(state.ticker, report_path)
            state.artifacts["quality"] = result.summary
            self._merge_result(state, result)
            if result.blocking_reason:
                state.blocking_reason = result.blocking_reason
        elif stage == "CITATION_GATE":
            gate = citation_gate(state.artifacts.get("report", {}))
            self._record_gate(state, gate)
        elif stage == "RESEARCH_REVIEW":
            self._charge_agent_step(state, stage)
            result = self.research_agent.run(state.model_dump(mode="json"))
            state.artifacts["research_review"] = result.payload
            self._merge_agent_result(state, result)
        elif stage == "AUDIT_REVIEW":
            self._charge_agent_step(state, stage)
            result = self.audit_agent.run(state.model_dump(mode="json"))
            state.artifacts["audit_review"] = result.payload
            self._merge_agent_result(state, result)
        elif stage == "EXPORT_GATE":
            gate = export_gate(state.model_dump(mode="json"), final_approval_required=False)
            self._record_gate(state, gate)
        elif stage == "WAITING_FINAL_APPROVAL":
            state.status = "needs_human_review"
            state.requires_human = True
            state.next_resume_stage = "PUBLISHED"
            self.store.update_run_state(state.run_id, "needs_human_review", stage)
        elif stage == "PUBLISHED":
            gate = export_gate(state.model_dump(mode="json"), final_approval_required=True)
            self._record_gate(state, gate)
            if not gate["passed"]:
                state.status = "needs_human_review"
                state.requires_human = True
                state.blocking_reason = "; ".join(gate["blocking_reasons"])
                self.store.update_run_state(state.run_id, "needs_human_review", "NEEDS_REVIEW")
            else:
                state.status = "approved"
                self.store.update_run_state(state.run_id, "approved", "PUBLISHED", finished=True)
        return state

    def _preflight(self, state: ResearchGraphState) -> None:
        if state.run_type != "full_report":
            raise ValueError(f"Unsupported run_type for harness v1: {state.run_type}")
        if not state.ticker or len(state.ticker) > 10:
            raise ValueError(f"Invalid ticker: {state.ticker!r}")
        self.store.check_schema_version()

    def _record_gate(self, state: ResearchGraphState, gate: dict[str, Any]) -> None:
        state.gate_results[gate["gate"]] = gate
        if not gate.get("passed"):
            state.status = "needs_human_review"
            state.requires_human = True
            state.blocking_reason = "; ".join(gate.get("blocking_reasons") or ["gate_failed"])
            self.store.update_run_state(state.run_id, "needs_human_review", state.current_stage)

    def _merge_result(self, state: ResearchGraphState, result) -> None:
        state.artifact_refs.extend([ref.model_dump(mode="json") for ref in result.artifact_refs])
        state.evidence_refs.extend([ref.model_dump(mode="json") for ref in result.evidence_refs])

    def _merge_agent_result(self, state: ResearchGraphState, result) -> None:
        state.artifact_refs.extend([ref if isinstance(ref, dict) else dict(ref) for ref in result.artifact_refs])
        state.evidence_refs.extend([ref if isinstance(ref, dict) else dict(ref) for ref in result.evidence_refs])
        if result.requires_human or result.status == "needs_review":
            state.status = "needs_human_review"
            state.requires_human = True
            state.blocking_reason = result.review_reason or result.blocking_reason
            self.store.update_run_state(state.run_id, "needs_human_review", state.current_stage)

    def _charge_agent_step(self, state: ResearchGraphState, stage: str) -> None:
        decision = self.budget.charge(
            run_id=state.run_id,
            step_name=stage,
            model_name=self.settings.default_model_name,
            prompt_tokens=1200,
            completion_tokens=400,
            budget_policy=state.policy.get("budget_policy", self.settings.default_budget_policy),
        )
        if not decision.allow:
            state.status = "needs_human_review"
            state.requires_human = True
            state.blocking_reason = decision.stop_reason or "budget_stop"
            raise RuntimeError(state.blocking_reason)

    def _checkpoint(self, state: ResearchGraphState) -> None:
        state.checkpoint_version += 1
        payload = state.model_dump(mode="json")
        checksum = stable_hash(payload)
        self.store.save_artifact(
            artifact_id=deterministic_id(state.run_id, "graph_state_snapshot", str(state.checkpoint_version)),
            run_id=state.run_id,
            artifact_type="run_log_json",
            section_key="graph_state_snapshot",
            version=state.checkpoint_version,
            payload=payload,
            checksum=checksum,
            created_by_agent="ResearchGraphRunner",
            is_locked=False,
        )
        self.store.add_audit_event(
            run_id=state.run_id,
            actor="ResearchGraphRunner",
            action="graph_checkpoint",
            payload={"stage": state.current_stage, "version": state.checkpoint_version, "checksum": checksum},
        )

    @staticmethod
    def _agent_name(stage: str) -> str:
        if stage in {"RESEARCH_REVIEW"}:
            return "ResearchAgent"
        if stage in {"AUDIT_REVIEW"}:
            return "AuditAgent"
        return "ServiceNode"

    @staticmethod
    def _policy_reason(stage: str) -> str:
        return f"langgraph_harness:{stage.lower()}"

    @staticmethod
    def _db_status_for_stage(stage: str) -> str:
        if stage in {"BUILD_FACTS", "DATA_QUALITY_GATE"}:
            return "running"
        if stage in {"BUILD_INDEX", "RESEARCH_REVIEW", "DEBATE_REVIEW", "AUDIT_REVIEW"}:
            return "analysis_ready"
        if stage in {"VALUATION_DRAFT", "VALUATION_GATE", "VALUATION_LOCKED"}:
            return "valuation_ready"
        if stage in {"REPORT_GENERATION", "QUALITY_EVALUATION", "CITATION_GATE", "EXPORT_GATE"}:
            return "report_ready"
        if stage in {"WAITING_ASSUMPTIONS_APPROVAL", "WAITING_FINAL_APPROVAL"}:
            return "needs_human_review"
        if stage == "PUBLISHED":
            return "approved"
        return "running"
