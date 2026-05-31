from __future__ import annotations

from typing import Any

from backend.harness.agent_registry import AgentRegistry
from backend.harness.gates import citation_gate, data_quality_gate, export_gate, financial_analyst_gate, valuation_gate
from backend.harness.graph import GRAPH_STAGES, build_langgraph
from backend.harness.model_adapter import OpenAIModelAdapter
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
        self.agent_registry = AgentRegistry()
        self.model_adapter = OpenAIModelAdapter()
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
            self._invalidate_after_rejection(run_id, db_stage, reviewer, feedback_patch)
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
        state.human_review_decisions[db_stage] = {
            "decision": "approved",
            "reviewer": reviewer,
            "feedback_patch": feedback_patch,
        }

        if db_stage == "valuation_assumptions":
            self.store.lock_artifacts(run_id, ["valuation_draft"])
            self.run_until_pause(state, start_stage="VALUATION_LOCKED")
        elif db_stage == "final_report":
            self.run_until_pause(state, start_stage="PUBLISHED")

    def _node_map(self):
        return {stage: (lambda state, s=stage: self._run_stage(ResearchGraphState(**state), s).model_dump(mode="json")) for stage in GRAPH_STAGES}

    def _invalidate_after_rejection(
        self,
        run_id: str,
        db_stage: str,
        reviewer: str,
        feedback_patch: dict[str, Any],
    ) -> None:
        invalidation_map = {
            "valuation_assumptions": ["valuation_draft", "full_report_draft", "quality", "citation_gate"],
            "report_draft": ["full_report_draft", "quality", "citation_gate"],
            "final_report": ["full_report_draft", "quality", "citation_gate"],
        }
        section_keys = invalidation_map.get(db_stage, [])
        stale_count = self.store.mark_artifacts_stale(
            run_id=run_id,
            section_keys=section_keys,
            reason=f"{db_stage}_rejected",
        )
        latest = self.store.latest_graph_state(run_id)
        if latest:
            state = ResearchGraphState(**latest)
            state.status = "needs_human_review"
            state.requires_human = True
            state.current_stage = "NEEDS_REVIEW"
            state.blocking_reason = f"{db_stage}_rejected"
            state.human_review_decisions[db_stage] = {
                "decision": "rejected",
                "reviewer": reviewer,
                "feedback_patch": feedback_patch,
                "invalidated_sections": section_keys,
                "stale_artifacts_count": stale_count,
            }
            self._checkpoint(state)

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
        elif stage == "SUPERVISOR_PLAN":
            result = self._run_agent(state, "supervisor", "Create execution plan and HITL routing policy.")
            state.plan = result.payload
            self._merge_agent_result(state, result)
        elif stage == "DATA_RETRIEVAL_RUN":
            result = build_facts_tool(state.ticker, state.from_year, state.to_year)
            state.artifacts["build_facts"] = result.summary
            state.data_inventory = result.summary
            state.snapshot_id = result.summary.get("snapshot_id")
            self._merge_result(state, result)

            index_result = build_index_tool(state.ticker, state.from_year, state.to_year)
            state.artifacts["index"] = index_result.summary
            state.retrieval_results = index_result.summary
            self._merge_result(state, index_result)

            agent_result = self._run_agent(state, "data_retrieval", "Review data inventory, source coverage, and retrieval readiness.")
            state.artifacts["data_retrieval_review"] = agent_result.payload
            self._merge_agent_result(state, agent_result)
        elif stage == "DATA_QUALITY_GATE":
            gate = data_quality_gate(state.data_inventory or state.artifacts.get("build_facts", {}))
            self._record_gate(state, gate)
        elif stage == "FINANCIAL_ANALYST_RUN":
            result = self._run_agent(state, "financial_analyst", "Interpret deterministic financial tables and identify traceable diagnostics.")
            state.financial_tables = result.model_dump(mode="json")
            state.artifacts["financial_analyst_review"] = result.payload
            self._merge_agent_result(state, result)
        elif stage == "FINANCIAL_ANALYST_GATE":
            gate = financial_analyst_gate(state.financial_tables)
            self._record_gate(state, gate)
        elif stage == "VALUATION_RUN":
            result = run_valuation_tool(state.ticker, state.from_year, state.to_year)
            state.valuation_outputs = result.summary
            state.artifacts["valuation"] = result.summary
            state.snapshot_id = result.summary.get("snapshot_id") or state.snapshot_id
            self._merge_result(state, result)

            agent_result = self._run_agent(state, "valuation", "Review deterministic valuation outputs, assumptions, and model limitations.")
            state.artifacts["valuation_review"] = agent_result.payload
            self._merge_agent_result(state, agent_result)
        elif stage == "VALUATION_GATE":
            gate = valuation_gate(state.valuation_outputs or state.artifacts.get("valuation", {}))
            self._record_gate(state, gate)
        elif stage == "WAITING_ASSUMPTIONS_APPROVAL":
            state.status = "needs_human_review"
            state.requires_human = True
            state.next_resume_stage = "VALUATION_LOCKED"
            self.store.update_run_state(state.run_id, "needs_human_review", stage)
        elif stage == "VALUATION_LOCKED":
            state.artifacts.setdefault("valuation_lock", {"locked": True, "approval": state.approvals.get("valuation_assumptions")})
            state.status = "running"
        elif stage == "REPORT_WRITER_CRITIC_RUN":
            result = generate_report_tool(state.ticker, state.snapshot_id, state.from_year, state.to_year, mode="draft")
            state.artifacts["report"] = result.summary
            state.draft_report = result.summary
            self._merge_result(state, result)

            agent_result = self._run_agent(state, "report_writer_critic", "Review draft report for grounded narrative, citations, numeric consistency, and final readiness.")
            state.artifacts["report_writer_critic_review"] = agent_result.payload
            self._merge_agent_result(state, agent_result)
        elif stage == "QUALITY_EVALUATION":
            report_path = (state.draft_report or state.artifacts.get("report") or {}).get("report_path")
            result = evaluate_quality_tool(state.ticker, report_path)
            state.artifacts["quality"] = result.summary
            state.evaluation_results = result.summary
            self._merge_result(state, result)
            if result.blocking_reason:
                state.blocking_reason = result.blocking_reason
        elif stage == "CITATION_GATE":
            gate = citation_gate(state.draft_report or state.artifacts.get("report", {}))
            self._record_gate(state, gate)
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
        self.agent_registry.validate()
        self.model_adapter.validate_environment()

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
        self._record_tool_trace(state, result.node_name, result.summary, result.output_hash)

    def _merge_agent_result(self, state: ResearchGraphState, result) -> None:
        state.artifact_refs.extend([ref if isinstance(ref, dict) else dict(ref) for ref in result.artifact_refs])
        state.evidence_refs.extend([ref if isinstance(ref, dict) else dict(ref) for ref in result.evidence_refs])
        if result.requires_human or result.status == "needs_review":
            state.status = "needs_human_review"
            state.requires_human = True
            state.blocking_reason = result.review_reason or result.blocking_reason
            self.store.update_run_state(state.run_id, "needs_human_review", state.current_stage)
        self._record_agent_trace(state, result)

    def _run_agent(self, state: ResearchGraphState, agent_id: str, task: str):
        config = self.agent_registry.get_agent_config(agent_id)
        self._charge_agent_step(state, config.agent_id, config.model)
        return self.model_adapter.run_agent(
            agent_config=config,
            state=state.model_dump(mode="json"),
            task=task,
            input_refs=[ref.get("artifact_id", "") for ref in state.artifact_refs if isinstance(ref, dict)],
        )

    def _charge_agent_step(self, state: ResearchGraphState, step_name: str, model_name: str) -> None:
        decision = self.budget.charge(
            run_id=state.run_id,
            step_name=step_name,
            model_name=model_name,
            prompt_tokens=1200,
            completion_tokens=400,
            budget_policy=state.policy.get("budget_policy", self.settings.default_budget_policy),
        )
        if not decision.allow:
            state.status = "needs_human_review"
            state.requires_human = True
            state.blocking_reason = decision.stop_reason or "budget_stop"
            raise RuntimeError(state.blocking_reason)

    def _record_agent_trace(self, state: ResearchGraphState, result) -> None:
        payload = {
            "kind": "agent_message",
            "run_id": state.run_id,
            "agent_id": result.agent_id,
            "agent_role": result.agent_id,
            "action": result.action,
            "input_summary": result.input_summary,
            "output_summary": result.output_summary,
            "confidence": result.confidence,
            "confidence_breakdown": result.confidence_breakdown,
            "status": result.status,
            "latency_ms": result.latency_ms,
            "cost_estimate": result.cost_estimate,
            "sources_used": result.sources_used,
            "fallback_triggered": result.fallback_triggered,
            "requires_human": result.requires_human,
            "next_action": result.next_action,
            "warnings": result.warnings,
        }
        state.trace.append(payload)
        self.store.add_audit_event(
            run_id=state.run_id,
            actor=result.agent_id or "agent",
            action="agent_message",
            payload=payload,
        )

    def _record_tool_trace(self, state: ResearchGraphState, tool_name: str, summary: dict[str, Any], output_hash: str | None) -> None:
        payload = {
            "kind": "tool_call",
            "run_id": state.run_id,
            "agent_role": self._agent_name(state.current_stage),
            "tool_name": tool_name,
            "arguments_json": {"ticker": state.ticker, "from_year": state.from_year, "to_year": state.to_year},
            "expected_output_schema": "ServiceNodeResult",
            "timeout_policy": "default",
            "retry_policy": "no_retry",
            "output_hash": output_hash,
            "output_summary": summary,
        }
        state.trace.append(payload)
        self.store.add_audit_event(
            run_id=state.run_id,
            actor=self._agent_name(state.current_stage),
            action="tool_call",
            payload=payload,
        )

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
        if stage == "SUPERVISOR_PLAN":
            return "SupervisorAgent"
        if stage in {"DATA_RETRIEVAL_RUN", "DATA_QUALITY_GATE"}:
            return "DataRetrievalAgent"
        if stage in {"FINANCIAL_ANALYST_RUN", "FINANCIAL_ANALYST_GATE"}:
            return "FinancialAnalystAgent"
        if stage in {"VALUATION_RUN", "VALUATION_GATE", "WAITING_ASSUMPTIONS_APPROVAL", "VALUATION_LOCKED"}:
            return "ValuationAgent"
        if stage in {"REPORT_WRITER_CRITIC_RUN", "QUALITY_EVALUATION", "CITATION_GATE", "EXPORT_GATE", "WAITING_FINAL_APPROVAL", "PUBLISHED"}:
            return "ReportWriterCriticAgent"
        return "ServiceNode"

    @staticmethod
    def _policy_reason(stage: str) -> str:
        return f"langgraph_harness:{stage.lower()}"

    @staticmethod
    def _db_status_for_stage(stage: str) -> str:
        if stage in {"DATA_RETRIEVAL_RUN", "DATA_QUALITY_GATE"}:
            return "running"
        if stage in {"SUPERVISOR_PLAN", "FINANCIAL_ANALYST_RUN", "FINANCIAL_ANALYST_GATE"}:
            return "analysis_ready"
        if stage in {"VALUATION_RUN", "VALUATION_GATE", "VALUATION_LOCKED"}:
            return "valuation_ready"
        if stage in {"REPORT_WRITER_CRITIC_RUN", "QUALITY_EVALUATION", "CITATION_GATE", "EXPORT_GATE"}:
            return "report_ready"
        if stage in {"WAITING_ASSUMPTIONS_APPROVAL", "WAITING_FINAL_APPROVAL"}:
            return "needs_human_review"
        if stage == "PUBLISHED":
            return "approved"
        return "running"
