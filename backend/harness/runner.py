from __future__ import annotations

import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

from backend.harness.agent_registry import AgentRegistry
from backend.harness.gates import (
    approval_path_gate,
    artifact_manifest_gate,
    citation_gate,
    data_quality_gate,
    evidence_packet_gate,
    workflow_export_gate,
    financial_analyst_gate,
    formula_trace_gate,
    tool_permission_gate,
    valuation_gate,
    pass_gate,
    fail_gate,
    forecast_quality_gate,
    valuation_reconciliation_gate,
    report_completeness_gate,
    senior_critic_gate,
)
from backend.harness.graph import GRAPH_STAGES
from backend.harness.model_adapter import AnthropicModelAdapter
from backend.harness.state import AgentExecutionContext, ResearchGraphState, stable_hash
from backend.harness.tool_registry import ToolRegistry
from backend.runtime_store import RuntimeStore
from backend.services import BudgetGuard
from backend.settings import Settings, settings
from backend.period_scope import DEFAULT_FROM_YEAR, DEFAULT_TO_YEAR
from backend.utils import compact_json, deterministic_id


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


def _count_metric_references(payload: Any) -> int:
    import json
    import re

    text = json.dumps(payload or {}, ensure_ascii=False, default=str)
    return len(set(re.findall(r"\b[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\b", text)))


def _count_period_references(payload: Any) -> int:
    import json
    import re

    text = json.dumps(payload or {}, ensure_ascii=False, default=str)
    return len(set(re.findall(r"\b20\d{2}(?:FY|A|F)?\b", text)))


class ResearchGraphRunner:
    def __init__(
        self,
        store: RuntimeStore,
        app_settings: Settings | None = None,
        report_publisher: Any | None = None,
        progress: Any | None = None,
    ) -> None:
        self.store = store
        self.settings = app_settings or settings
        self.budget = BudgetGuard(store, self.settings)
        self.agent_registry = AgentRegistry()
        self.tool_registry = ToolRegistry()
        self.model_adapter = AnthropicModelAdapter()
        self.report_publisher = report_publisher
        from backend.harness.progress import ProgressReporter
        self.progress: ProgressReporter = progress or ProgressReporter(quiet=True)

    def execute(self, context) -> ResearchGraphState:
        state = ResearchGraphState(
            run_id=context.run_id,
            ticker=context.ticker,
            run_type=context.run_type,
            objective=context.objective,
            policy=context.policy,
            flags=context.flags,
            from_year=getattr(context, "from_year", DEFAULT_FROM_YEAR),
            to_year=getattr(context, "to_year", DEFAULT_TO_YEAR),
            ocr=getattr(context, "ocr", False),
        )
        return self.run_until_pause(state)

    def run_until_pause(self, state: ResearchGraphState | dict[str, Any], start_stage: str = "PREFLIGHT") -> ResearchGraphState:
        import time

        current = state if isinstance(state, ResearchGraphState) else ResearchGraphState(**state)
        stages = GRAPH_STAGES[GRAPH_STAGES.index(start_stage):]
        run_start_time = time.monotonic()
        stages_completed = 0

        self.progress.run_start(current.run_id, current.ticker, current.run_type)

        for idx, stage in enumerate(stages):
            if current.requires_human or current.blocking_reason:
                self.progress.blocking(stage, current.blocking_reason or "requires_human")
                break
            current.current_stage = stage
            self.progress.stage_start(stage, idx, len(stages))
            stage_t0 = time.monotonic()
            current = self._run_stage(current, stage)
            elapsed = time.monotonic() - stage_t0
            status = "completed" if current.status not in ("failed", "needs_human_review") else current.status
            self.progress.stage_end(stage, elapsed, status)
            stages_completed += 1
            if current.status == "failed" or current.requires_human or current.blocking_reason:
                if current.blocking_reason:
                    self.progress.blocking(stage, current.blocking_reason)
                break
            if stage == "RENDER_AND_PUBLISH" or (
                stage in {"WAITING_ASSUMPTION_APPROVAL", "WAITING_FINAL_APPROVAL"}
                and current.requires_human
            ):
                break

        total_elapsed = time.monotonic() - run_start_time
        gate_pass_map = {k: bool(v.get("passed")) if isinstance(v, dict) else False for k, v in current.gate_results.items()}
        self.progress.run_summary(
            run_id=current.run_id,
            ticker=current.ticker,
            final_status=current.status,
            total_elapsed_sec=total_elapsed,
            stages_completed=stages_completed,
            stages_total=len(stages),
            gate_results=gate_pass_map,
            output_path=None,
            errors=current.errors if hasattr(current, "errors") else [],
        )

        # Write evidence packet and manifest so render_report --run-id can
        # resolve artifacts deterministically.
        try:
            self._write_evidence_packet(current)
            self._write_agent_effectiveness_audit(current)
            self._write_run_manifest(current)
        except Exception as _exc:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning(
                "Failed to write run manifest for run=%s: %s", current.run_id, _exc
            )

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
            self.run_until_pause(state, start_stage="VALUATION_EXECUTION")
        elif db_stage == "final_report":
            if "report" not in state.artifacts:
                state.artifacts["report"] = {}
            state.artifacts["report"]["approval_status"] = "approved"
            self.run_until_pause(state, start_stage="RENDER_AND_PUBLISH")

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
        elif stage == "RESEARCH_MANAGER_PLAN":
            result = self._run_agent(state, "research_manager", "Create the typed research plan and HITL routing policy.")
            state.plan = result.payload
            # Missing artifacts are expected during initial planning; gates own
            # blocking decisions after deterministic acquisition.
            self._merge_agent_result(state, result, enforce_review=False)
        elif stage == "DATA_AND_EVIDENCE":
            # Step 1: auto-ingest official documents FIRST.
            # Non-blocking: failure produces status="warn" in summary, pipeline continues with Tier-3.
            auto_result = self._run_tool(
                state, "data_evidence", "auto_ingest",
                state.ticker, state.from_year, state.to_year, ocr=state.ocr
            )
            state.artifacts["auto_ingest"] = auto_result.summary
            self._merge_result(state, auto_result)

            # Step 2: build canonical facts (reads from DB — needs ingest to have run)
            result = self._run_tool(state, "data_evidence", "build_facts", state.ticker, state.from_year, state.to_year, run_id=state.run_id)
            state.artifacts["build_facts"] = result.summary
            state.data_inventory = result.summary
            state.snapshot_id = result.summary.get("snapshot_id")
            self._merge_result(state, result)

            # Step 3: build evidence index
            index_result = self._run_tool(state, "data_evidence", "build_index", state.ticker, state.from_year, state.to_year, run_id=state.run_id)
            state.artifacts["index"] = index_result.summary
            state.retrieval_results = index_result.summary
            self._merge_result(state, index_result)

            agent_result = self._run_agent(
                state, "data_evidence",
                "Review data inventory, source coverage, and retrieval readiness.",
            )
            state.artifacts["evidence_pack"] = agent_result.payload
            self._merge_agent_result(state, agent_result, enforce_review=False)
        elif stage == "DATA_QUALITY_GATE":
            gate = data_quality_gate(state.data_inventory or state.artifacts.get("build_facts", {}))
            self._record_gate(state, gate)
        elif stage == "FINANCIAL_ANALYSIS":
            snapshot_result = self._run_tool(state, "financial_analysis", "read_snapshot", state.ticker, state.snapshot_id)
            state.artifacts["snapshot"] = snapshot_result.summary
            self._merge_result(state, snapshot_result)
            if snapshot_result.blocking_reason:
                raise RuntimeError(snapshot_result.blocking_reason)

            ratio_result = self._run_tool(state, "financial_analysis", "read_ratio_artifact", state.ticker, state.snapshot_id, run_id=state.run_id)
            state.artifacts["ratios"] = ratio_result.summary
            self._merge_result(state, ratio_result)
            if ratio_result.blocking_reason:
                raise RuntimeError(ratio_result.blocking_reason)

            result = self._run_agent(state, "financial_analysis", "Create typed financial analysis with traceable diagnostics.")
            state.financial_tables = result.model_dump(mode="json")
            state.artifacts["financial_analysis"] = result.payload
            # Agent caveats (e.g. Tier-3 data) are advisory; FINANCIAL_ANALYSIS_GATE owns blocking.
            self._merge_agent_result(state, result, enforce_review=False)
            self._handle_evidence_request(state, "financial_analysis", result.payload)
        elif stage == "FINANCIAL_ANALYSIS_GATE":
            gate = financial_analyst_gate(state.financial_tables)
            self._record_gate(state, gate)
        elif stage == "DRIVER_BASED_FORECAST":
            forecast_result = self._run_tool(
                state,
                "forecast_valuation",
                "run_forecast",
                state.ticker,
                state.snapshot_id,
                state.from_year,
                state.to_year,
                run_id=state.run_id,
            )
            state.artifacts["forecast_model"] = forecast_result.summary
            self._merge_result(state, forecast_result)
            if forecast_result.blocking_reason:
                raise RuntimeError(forecast_result.blocking_reason)

            result = self._run_agent(state, "forecast_valuation", "Create the typed driver-based forecast model.")
            state.artifacts["forecast_narrative"] = result.payload
            # Advisory; FORECAST_QUALITY_GATE owns blocking.
            self._merge_agent_result(state, result, enforce_review=False)
            self._handle_evidence_request(state, "forecast_valuation", result.payload)
        elif stage == "FORECAST_QUALITY_GATE":
            forecast = state.artifacts.get("forecast_model") or {}
            self._record_gate(state, forecast_quality_gate(forecast))
        elif stage == "VALUATION_PROPOSAL":
            result = self._run_agent(state, "forecast_valuation", "Create the typed FCFF/FCFE valuation proposal for human approval.")
            state.artifacts["valuation_proposal"] = result.payload
            # Advisory; assumptions are gated at WAITING_ASSUMPTION_APPROVAL and VALUATION_GATE.
            self._merge_agent_result(state, result, enforce_review=False)
        elif stage == "VALUATION_EXECUTION":
            result = self._run_tool(
                state,
                "forecast_valuation",
                "run_valuation",
                state.ticker,
                state.from_year,
                state.to_year,
                run_id=state.run_id,
                auto_approve_assumptions=state.policy.get("auto_approve_assumptions") is True,
            )
            state.valuation_outputs = result.summary
            state.artifacts["valuation"] = result.summary
            state.snapshot_id = result.summary.get("snapshot_id") or state.snapshot_id
            self._merge_result(state, result)

            valuation_read = self._run_tool(state, "forecast_valuation", "read_valuation_artifact", result.summary.get("storage_path"))
            state.artifacts["valuation_read"] = valuation_read.summary
            self._merge_result(state, valuation_read)

            agent_result = self._run_agent(state, "forecast_valuation", "Review deterministic valuation outputs, assumptions, and model limitations.")
            state.artifacts["valuation_review"] = agent_result.payload
            # Advisory; VALUATION_GATE owns blocking.
            self._merge_agent_result(state, agent_result, enforce_review=False)
        elif stage == "VALUATION_GATE":
            gate = valuation_gate(state.valuation_outputs or state.artifacts.get("valuation", {}))
            self._record_gate(state, gate)
            self._record_gate(
                state,
                valuation_reconciliation_gate(
                    state.valuation_outputs or state.artifacts.get("valuation", {}),
                    state.artifacts.get("market_snapshot", {}),
                ),
            )
        elif stage == "WAITING_ASSUMPTION_APPROVAL":
            if state.policy.get("auto_approve_assumptions") is True:
                self._record_auto_approval(
                    state,
                    db_stage="valuation_assumptions",
                    reviewer="auto_approve_assumptions",
                )
                state.status = "running"
                state.requires_human = False
                state.next_resume_stage = None
                return state
            state.status = "needs_human_review"
            state.requires_human = True
            state.next_resume_stage = "VALUATION_EXECUTION"
            self.store.update_run_state(state.run_id, "needs_human_review", stage)
        elif stage == "LOCK_RESEARCH_ARTIFACTS":
            state.artifacts["research_lock"] = {
                "locked": True,
                "approval": state.approvals.get("valuation_assumptions"),
                "artifact_keys": sorted(state.artifacts),
            }
            state.status = "running"
        elif stage == "RESEARCH_MANAGER_READINESS":
            result = self._run_agent(state, "research_manager", "Perform the typed readiness review before report writing.")
            state.artifacts["readiness_review"] = result.payload
            # Advisory; downstream content/citation/export gates own blocking.
            self._merge_agent_result(state, result, enforce_review=False)
        elif stage == "THESIS_AND_REPORT":
            agent_result = self._run_agent(state, "thesis_report", "Create the typed grounded report draft from approved artifacts.")
            state.artifacts["report_draft"] = agent_result.payload
            state.draft_report = agent_result.payload
            # Advisory; REPORT_ASSEMBLY, CITATION_GATE and report_completeness_gate own blocking.
            self._merge_agent_result(state, agent_result, enforce_review=False)
            self._handle_evidence_request(state, "thesis_report", agent_result.payload)
        elif stage == "REPORT_ASSEMBLY":
            from backend.reporting.report_assembler import ReportAssembler

            artifacts = {
                "claim_ledger": {"claims": state.draft_report.get("claims", [])},
                "financial_analysis": state.artifacts.get("financial_analysis") or state.artifacts.get("financial_analyst_review") or {},
                "forecast_model": state.artifacts.get("forecast_model") or {},
                "valuation": state.artifacts.get("valuation") or {},
                "market_snapshot": state.artifacts.get("market_snapshot") or {},
            }
            specs = {
                "chart_specs": state.artifacts.get("chart_specs") or {},
                "table_specs": state.artifacts.get("table_specs") or {},
            }
            validation = ReportAssembler().validate(state.draft_report, artifacts, specs)
            state.artifacts["report_assembly_validation"] = validation.to_dict()
            if not validation.passed:
                self._record_gate(state, fail_gate("REPORT_ASSEMBLY_GATE", ";".join(validation.errors)))
            else:
                state.artifacts["final_report_model"] = ReportAssembler().assemble(state.draft_report, artifacts, specs)
                self._persist_payload_artifact(state, "final_report_model", state.artifacts["final_report_model"], "report_assembler")
                self._record_gate(state, pass_gate("REPORT_ASSEMBLY_GATE"))
        elif stage == "DETERMINISTIC_CONTENT_GATES":
            self._record_gate(state, report_completeness_gate(state.draft_report or {}))
        elif stage == "SENIOR_CRITIC_REVIEW":
            report_path = (state.draft_report or state.artifacts.get("report") or {}).get("storage_path")
            valuation_path = (state.valuation_outputs or state.artifacts.get("valuation") or {}).get("storage_path")
            result = self._run_tool(
                state, "senior_critic", "evaluate_report_quality",
                state.ticker, report_path, valuation_path=valuation_path, run_id=state.run_id
            )
            state.artifacts["quality"] = result.summary
            state.evaluation_results = result.summary
            self._merge_result(state, result)
            if result.blocking_reason:
                state.blocking_reason = result.blocking_reason
            critic = self._run_agent(state, "senior_critic", "Create the typed senior critic scorecard and findings.")
            state.artifacts["critic_review"] = critic.payload
            self._merge_agent_result(state, critic)
            self._record_gate(state, senior_critic_gate(critic.payload))
        elif stage == "OPTIONAL_SINGLE_REPORT_REVISION":
            critic = state.artifacts.get("critic_review") or {}
            if critic.get("decision") == "revision_required" and state.report_revision_count == 0:
                revision = self._run_agent(state, "thesis_report", "Revise the report once using the senior critic instructions.")
                state.report_revision_count = 1
                state.draft_report = revision.payload
                state.artifacts["revised_report_draft"] = revision.payload
                self._merge_agent_result(state, revision)
            elif critic.get("decision") in {"revision_required", "human_review_required"}:
                state.requires_human = True
                state.blocking_reason = "critic_requires_human_review"
        elif stage == "CITATION_GATE":
            gate = citation_gate(state.draft_report or state.artifacts.get("report", {}))
            self._record_gate(state, gate)
        elif stage == "FINAL_EXPORT_GATE":
            self._write_evidence_packet(state)
            self._record_gate(state, tool_permission_gate(state.trace))
            self._record_gate(state, artifact_manifest_gate(state.model_dump(mode="json")))
            self._record_gate(state, formula_trace_gate(state.valuation_outputs or state.artifacts.get("valuation", {})))
            self._record_gate(state, evidence_packet_gate(state.model_dump(mode="json")))
            gate = workflow_export_gate(state.model_dump(mode="json"), final_approval_required=False)
            self._record_gate(state, gate)
            self._persist_payload_artifact(state, "quality_gate", state.gate_results, "deterministic_gates")
        elif stage == "WAITING_FINAL_APPROVAL":
            if state.policy.get("auto_approve_final") is True:
                self._record_auto_approval(
                    state,
                    db_stage="final_report",
                    reviewer="auto_approve_final",
                )
                state.artifacts.setdefault("report", {})["approval_status"] = "approved"
                state.status = "running"
                state.requires_human = False
                state.next_resume_stage = None
                return state
            state.status = "needs_human_review"
            state.requires_human = True
            state.next_resume_stage = "RENDER_AND_PUBLISH"
            self.store.update_run_state(state.run_id, "needs_human_review", stage)
        elif stage == "RENDER_AND_PUBLISH":
            self._write_evidence_packet(state)
            self._record_gate(state, tool_permission_gate(state.trace))
            self._record_gate(state, artifact_manifest_gate(state.model_dump(mode="json")))
            self._record_gate(state, formula_trace_gate(state.valuation_outputs or state.artifacts.get("valuation", {})))
            self._record_gate(state, evidence_packet_gate(state.model_dump(mode="json")))
            self._record_gate(state, approval_path_gate(state.model_dump(mode="json"), final_approval_required=True))
            gate = workflow_export_gate(state.model_dump(mode="json"), final_approval_required=True)
            self._record_gate(state, gate)
            if not gate["passed"]:
                state.status = "needs_human_review"
                state.requires_human = True
                state.blocking_reason = "; ".join(gate["blocking_reasons"])
                self.store.update_run_state(state.run_id, "needs_human_review", "NEEDS_REVIEW")
            else:
                if not self._render_and_publish_final_report(state):
                    return state
                state.status = "approved"
                self.store.update_run_state(state.run_id, "approved", "RENDER_AND_PUBLISH", finished=True)
        return state

    def _record_auto_approval(self, state: ResearchGraphState, db_stage: str, reviewer: str) -> None:
        feedback_patch = {"source": "run_policy", "auto_approved": True}
        try:
            self.store.add_approval(
                run_id=state.run_id,
                stage=db_stage,
                decision="approved",
                reviewer=reviewer,
                feedback_patch=feedback_patch,
            )
        except Exception as exc:  # noqa: BLE001
            state.errors.append(f"auto_approval_record_failed:{db_stage}:{exc}")
        state.approvals[db_stage] = "approved"
        state.human_review_decisions[db_stage] = {
            "decision": "approved",
            "reviewer": reviewer,
            "feedback_patch": feedback_patch,
        }

    def _render_and_publish_final_report(self, state: ResearchGraphState) -> bool:
        from backend.reporting.final_report_renderer import FinalReportPublisher
        from backend.reporting.pdf_renderer import PDFRenderError

        final_model = state.artifacts.get("final_report_model")
        if not isinstance(final_model, dict):
            state.status = "needs_human_review"
            state.requires_human = True
            state.blocking_reason = "final_report_model_missing_for_render"
            self.store.update_run_state(state.run_id, "needs_human_review", "NEEDS_REVIEW")
            return False

        publisher = self.report_publisher or FinalReportPublisher()
        try:
            published = publisher.publish(
                run_id=state.run_id,
                ticker=state.ticker,
                final_report_model=final_model,
            )
        except PDFRenderError as exc:
            state.status = "needs_human_review"
            state.requires_human = True
            state.blocking_reason = f"pdf_render_blocked:{exc}"
            self.store.update_run_state(state.run_id, "needs_human_review", "NEEDS_REVIEW")
            return False

        state.artifacts["rendered_report"] = published.to_dict()
        try:
            from backend.storage import RUNS_BUCKET, SupabaseStorageAdapter

            local_pdf_dir = ROOT / "output" / "pdf"
            local_pdf_dir.mkdir(parents=True, exist_ok=True)
            local_pdf_path = local_pdf_dir / f"{state.ticker}_{state.run_id}_report.pdf"
            SupabaseStorageAdapter().download_file(
                RUNS_BUCKET,
                published.pdf.storage_path,
                local_pdf_path,
            )
            state.artifacts["rendered_report"]["local_pdf_path"] = str(local_pdf_path)
        except Exception as exc:  # noqa: BLE001
            state.errors.append(f"local_pdf_export_failed:{exc}")
        for ref in published.artifact_refs():
            self._persist_published_artifact_ref(state, ref)
        return True

    def _persist_published_artifact_ref(
        self,
        state: ResearchGraphState,
        ref: dict[str, Any],
    ) -> None:
        section_key = ref.get("section_key")
        state.artifact_refs = [
            existing
            for existing in state.artifact_refs
            if not (
                isinstance(existing, dict)
                and section_key
                and existing.get("section_key") == section_key
            )
        ]
        state.artifact_refs.append(ref)
        self.store.save_artifact(
            artifact_id=str(ref["artifact_id"]),
            run_id=state.run_id,
            artifact_type=str(ref["artifact_type"]),
            section_key=section_key,
            version=int(ref.get("version") or 1),
            payload={},
            storage_bucket=ref.get("storage_bucket"),
            storage_path=ref.get("storage_path"),
            checksum=ref.get("checksum"),
            content_type=ref.get("content_type"),
            file_size_bytes=ref.get("file_size_bytes"),
            created_by_agent=ref.get("producer"),
            is_locked=bool(ref.get("is_locked")),
        )

    def _preflight(self, state: ResearchGraphState) -> None:
        if state.run_type != "full_report":
            raise ValueError(f"Unsupported run_type for harness v1: {state.run_type}")
        if not state.ticker or len(state.ticker) > 10:
            raise ValueError(f"Invalid ticker: {state.ticker!r}")
        self.store.check_schema_version()
        configs = self.agent_registry.load()
        self.tool_registry.validate_agent_tool_policy(configs)
        self.model_adapter.validate_environment()

    def _record_gate(self, state: ResearchGraphState, gate: dict[str, Any]) -> None:
        state.gate_results[gate["gate"]] = gate
        self.progress.gate_result(
            gate["gate"],
            gate.get("passed", False),
            gate.get("blocking_reasons", []),
        )
        if not gate.get("passed"):
            state.status = "needs_human_review"
            state.requires_human = True
            state.blocking_reason = "; ".join(gate.get("blocking_reasons") or ["gate_failed"])
            self.store.update_run_state(state.run_id, "needs_human_review", state.current_stage)

    def _merge_result(self, state: ResearchGraphState, result) -> None:
        refs = [ref.model_dump(mode="json") for ref in result.artifact_refs]
        state.artifact_refs.extend(refs)
        for ref in refs:
            if ref.get("storage_bucket") and ref.get("storage_path"):
                self.store.save_artifact(
                    artifact_id=deterministic_id(state.run_id, str(ref["artifact_id"]), str(ref.get("version", 1))),
                    run_id=state.run_id,
                    artifact_type=str(ref.get("artifact_type") or "other"),
                    section_key=ref.get("section_key"),
                    version=int(ref.get("version") or 1),
                    payload={},
                    storage_bucket=ref["storage_bucket"],
                    storage_path=ref["storage_path"],
                    checksum=ref.get("checksum"),
                    is_locked=bool(ref.get("is_locked")),
                    created_by_agent=ref.get("producer"),
                )
        state.evidence_refs.extend([ref.model_dump(mode="json") for ref in result.evidence_refs])
        self._record_tool_trace(state, result.node_name, result.summary, result.output_hash, result.gate_inputs)

    def _merge_agent_result(self, state: ResearchGraphState, result, enforce_review: bool = True) -> None:
        state.artifact_refs.extend([ref if isinstance(ref, dict) else dict(ref) for ref in result.artifact_refs])
        state.evidence_refs.extend([ref if isinstance(ref, dict) else dict(ref) for ref in result.evidence_refs])
        if enforce_review and (result.requires_human or result.status == "needs_review"):
            state.status = "needs_human_review"
            state.requires_human = True
            state.blocking_reason = result.review_reason or result.blocking_reason
            self.store.update_run_state(state.run_id, "needs_human_review", state.current_stage)
        self._record_agent_trace(state, result)
        self._write_agent_payload_artifact(state, result)

    def _run_tool(self, state: ResearchGraphState, agent_id: str, tool_id: str, *args, **kwargs):
        spec = self.tool_registry.get_tool(tool_id)
        if agent_id not in spec.owner_agent_ids:
            raise PermissionError(f"Tool {tool_id!r} is not owned by agent {agent_id!r}")
        config = self.agent_registry.get_agent_config(agent_id)
        if tool_id not in config.allowed_tools:
            raise PermissionError(f"Tool {tool_id!r} is not declared in allowed_tools for agent {agent_id!r}")
        self.progress.tool_start(tool_id, agent_id)
        try:
            result = spec.implementation(*args, **kwargs)
        except SystemExit as exc:
            self.progress.tool_end(tool_id, "failed", str(exc))
            raise RuntimeError(
                f"tool_process_exit: tool_id={tool_id} exit_code={exc.code}"
            ) from exc
        self.progress.tool_end(tool_id, "ok" if not result.blocking_reason else "blocked", result.blocking_reason)
        result.gate_inputs.setdefault(
            "tool_permission",
            {
                "tool_id": tool_id,
                "agent_id": agent_id,
                "permission_level": spec.permission_level,
                "artifact_producer_key": spec.artifact_producer_key,
            },
        )
        return result

    def _run_agent(self, state: ResearchGraphState, agent_id: str, task: str):
        from pydantic import ValidationError

        from backend.harness.contracts import validate_agent_artifact

        config = self.agent_registry.get_agent_config(agent_id)
        self._charge_agent_step(state, config.agent_id, config.model)
        context = self._build_agent_context(state, config.agent_id, task)
        self.progress.agent_start(agent_id, task)
        result = self.model_adapter.run_agent(
            agent_config=config,
            state=context.model_dump(mode="json"),
            task=task,
            input_refs=[ref.get("artifact_id", "") for ref in context.input_artifact_refs if isinstance(ref, dict)],
        )
        self.progress.agent_end(agent_id, result.status, getattr(result, 'confidence', None))
        self._inject_artifact_lineage(state, result.payload)
        self._repair_agent_payload(result.payload)
        try:
            validate_agent_artifact(config.output_schema, result.payload)
        except ValidationError as exc:
            result.status = "needs_review"
            result.requires_human = True
            result.review_reason = f"typed_artifact_validation_failed:{config.output_schema}"
            result.warnings.append(str(exc))
        return result

    @staticmethod
    def _inject_artifact_lineage(state: ResearchGraphState, payload: Any) -> None:
        """Stamp deterministic lineage onto an agent payload (Python owns lineage, not the LLM)."""
        if not isinstance(payload, dict):
            return
        payload["run_id"] = state.run_id
        payload["ticker"] = state.ticker
        domain = {
            key: value
            for key, value in payload.items()
            if key not in {"checksum", "created_at", "updated_at"}
        }
        payload["checksum"] = deterministic_id(compact_json(domain))

    @staticmethod
    def _repair_agent_payload(payload: Any) -> None:
        """Coerce common, deterministically-fixable LLM schema deviations before validation."""
        if not isinstance(payload, dict):
            return
        # Backfill the required latest_period from the historical period list.
        if not payload.get("latest_period"):
            periods = payload.get("historical_periods")
            if isinstance(periods, list) and periods:
                payload["latest_period"] = str(periods[-1])
        # Normalize an optional evidence_request to the EvidenceRequest contract,
        # or drop it when it cannot be coerced (it is non-critical follow-up).
        request = payload.get("evidence_request")
        if isinstance(request, dict):
            items = request.get("requested_items")
            if isinstance(items, list):
                request["requested_items"] = [
                    item if isinstance(item, str)
                    else str(item.get("item") or item.get("description") or item)
                    if isinstance(item, dict)
                    else str(item)
                    for item in items
                ]
            if not request.get("reason"):
                request["reason"] = "; ".join(request.get("requested_items", [])) or "additional_evidence_requested"
            request.setdefault("request_id", deterministic_id(compact_json(request))[:16])
        elif request is not None:
            payload["evidence_request"] = None

        ResearchGraphRunner._normalize_forecast_payload(payload)

    @staticmethod
    def _normalize_forecast_payload(payload: dict[str, Any]) -> None:
        """Align forecast-agent aliases without calculating or inventing forecast values."""
        horizon = payload.get("forecast_horizon")
        if isinstance(horizon, list):
            years = [
                int(match.group(1))
                for item in horizon
                if (match := re.match(r"^(20\d{2})F$", str(item)))
            ]
            if years:
                payload["forecast_horizon"] = {
                    "start_year": min(years),
                    "end_year": max(years),
                    "explicit_years": years,
                }

        limitations = payload.get("limitations")
        if isinstance(limitations, list):
            payload["limitations"] = [
                item
                if isinstance(item, str)
                else str(item.get("description") or item)
                if isinstance(item, dict)
                else str(item)
                for item in limitations
            ]

        drivers = payload.get("driver_assumptions")
        if not isinstance(drivers, dict):
            drivers = {}
        revenue_drivers = drivers.get("revenue_drivers")
        if isinstance(revenue_drivers, dict) and "revenue_forecast" not in payload:
            channel_drivers = revenue_drivers.get("channel_product_drivers")
            by_channel: dict[str, Any] = {}
            if isinstance(channel_drivers, dict):
                for name, details in channel_drivers.items():
                    if isinstance(details, dict):
                        by_channel[str(name)] = {
                            "forecast": {"status": "insufficient_evidence"},
                            "drivers": [
                                str(value)
                                for key, value in details.items()
                                if key in {"label", "growth_assumption"} and value
                            ],
                        }
            payload["revenue_forecast"] = {
                "by_channel": by_channel,
                "by_product_group": {
                    "unavailable": {
                        "forecast": {"status": "insufficient_evidence"},
                        "drivers": ["No product-group forecast evidence supplied."],
                    }
                },
                "company_growth": revenue_drivers.get("revenue_growth_by_year") or {},
            }

        gross_margin = drivers.get("gross_margin_drivers")
        if isinstance(gross_margin, dict) and "gross_margin_forecast" not in payload:
            payload["gross_margin_forecast"] = {
                "forecast": (gross_margin.get("gross_margin_by_year") or {}).get("base_case"),
                "assumptions": {
                    "driver_narrative": gross_margin.get("driver_narrative"),
                    "historical_range_pct": gross_margin.get("historical_range_pct"),
                },
            }

        opex_drivers = drivers.get("opex_drivers")
        if isinstance(opex_drivers, dict) and "opex_forecast" not in payload:
            sga = opex_drivers.get("sga_as_pct_revenue") or {}
            base_sga = (
                (sga.get("forecast_assumption") or {}).get("base_case")
                if isinstance(sga, dict)
                else {}
            )
            payload["opex_forecast"] = {
                "selling_expense": {
                    "status": "insufficient_evidence",
                    "combined_sga_forecast": base_sga,
                },
                "admin_expense": {
                    "status": "insufficient_evidence",
                    "combined_sga_forecast": base_sga,
                },
                "assumptions": opex_drivers,
            }

        working_capital = payload.get("working_capital_forecast")
        if isinstance(working_capital, dict):
            wc_base = (working_capital.get("forecast_assumptions") or {}).get("base_case") or {}
            for target, source in (
                ("receivable_days", "dso_days"),
                ("inventory_days", "dio_days"),
                ("payable_days", "dpo_days"),
            ):
                if target not in working_capital and source in wc_base:
                    working_capital[target] = wc_base[source]

        capex = payload.get("capex_depreciation_forecast")
        if isinstance(capex, dict) and "capex_and_depreciation" not in payload:
            capex_base = (capex.get("forecast_assumptions") or {}).get("base_case") or {}
            payload["capex_and_depreciation"] = {
                "capex_projects": capex.get("capex_cycle_assessment") or {"status": "insufficient_evidence"},
                "depreciation": capex_base.get("depreciation_bn_estimated"),
                "assumptions": capex.get("forecast_assumptions") or {},
            }

        debt = payload.get("debt_cash_interest_forecast")
        if isinstance(debt, dict) and "debt_cash_interest" not in payload:
            debt_base = debt.get("base_period_position") or {}
            debt_assumptions = debt.get("forecast_assumptions") or {}
            payload["debt_cash_interest"] = {
                "cash": {"status": "insufficient_evidence"},
                "short_term_debt": debt_base.get("short_term_debt_2025FY"),
                "long_term_debt": {"status": "insufficient_evidence"},
                "interest_expense": debt_assumptions.get("interest_expense_forecast_bn"),
                "net_borrowing": debt_assumptions.get("new_debt_issuance"),
                "assumptions": debt_assumptions,
            }

        income_statement = payload.get("income_statement_forecast")
        cash_flow = payload.get("cash_flow_forecast")
        if isinstance(income_statement, dict):
            base_case = income_statement.get("base_case") or {}
            if "eps_forecast" not in payload and isinstance(base_case, dict):
                payload["eps_forecast"] = {
                    period: values.get("eps_basic_vnd_estimated")
                    for period, values in base_case.items()
                    if isinstance(values, dict) and values.get("eps_basic_vnd_estimated") is not None
                }
            payload.setdefault(
                "forecast_financial_summary",
                {
                    "income_statement": income_statement,
                    "cash_flow": cash_flow or {},
                },
            )

        checks = payload.get("quality_checks")
        if isinstance(checks, dict) and "forecast_quality_checks" not in payload:
            aliases = {
                "historical_continuity_check": "2023fy_anomaly_treatment",
                "driver_support_check": "driver_traceability",
                "margin_sanity_check": "gross_margin_consistency",
                "cash_flow_consistency_check": "fcff_vs_net_income",
            }
            normalized_checks = {
                target: checks[source]
                for target, source in aliases.items()
                if source in checks
            }
            normalized_checks["balance_sheet_balance_check"] = {
                "status": "fail",
                "reason": "balance_sheet_forecast_unavailable",
            }
            payload["forecast_quality_checks"] = normalized_checks

    def _build_agent_context(self, state: ResearchGraphState, agent_id: str, task: str) -> AgentExecutionContext:
        config = self.agent_registry.get_agent_config(agent_id)
        failed_gate_issues = [
            issue.get("issue_id")
            for gate in state.gate_results.values()
            if isinstance(gate, dict) and gate.get("passed") is False
            for issue in gate.get("issues", [])
            if isinstance(issue, dict)
        ]
        known_limitations = list(filter(None, [state.blocking_reason, *state.errors, *failed_gate_issues]))
        return AgentExecutionContext(
            run_id=state.run_id,
            ticker=state.ticker,
            stage=state.current_stage,
            task=task,
            allowed_tools=config.allowed_tools,
            input_artifact_refs=state.artifact_refs,
            input_artifacts=state.artifacts,
            evidence_packet_path=self._artifact_path_for_section(state, "evidence_packet"),
            relevant_gate_results=state.gate_results,
            known_limitations=sorted(set(str(item) for item in known_limitations)),
        )

    def _handle_evidence_request(self, state: ResearchGraphState, agent_id: str, payload: dict[str, Any]) -> None:
        request = payload.get("evidence_request") if isinstance(payload, dict) else None
        if not isinstance(request, dict):
            return
        count = state.evidence_followups.get(agent_id, 0)
        if count >= 1 and request.get("critical"):
            state.requires_human = True
            state.blocking_reason = f"critical_evidence_missing_after_followup:{agent_id}"
            return
        if count >= 1:
            state.artifacts.setdefault("insufficient_evidence", []).append(request)
            return
        state.evidence_followups[agent_id] = 1
        state.artifacts.setdefault("structured_evidence_requests", []).append(
            {"requesting_agent": agent_id, **request}
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

    def _write_agent_payload_artifact(self, state: ResearchGraphState, result) -> None:
        """Persist every validated specialist output as a versioned run artifact."""
        section_by_stage = {
            "RESEARCH_MANAGER_PLAN": "research_plan",
            "DATA_AND_EVIDENCE": "evidence_pack",
            "FINANCIAL_ANALYSIS": "financial_analysis",
            "DRIVER_BASED_FORECAST": "forecast_model",
            "VALUATION_PROPOSAL": "valuation_proposal",
            "RESEARCH_MANAGER_READINESS": "readiness_review",
            "THESIS_AND_REPORT": "report_draft",
            "SENIOR_CRITIC_REVIEW": "critic_review",
            "OPTIONAL_SINGLE_REPORT_REVISION": "revised_report_draft",
        }
        section_key = section_by_stage.get(state.current_stage)
        if not section_key or not isinstance(result.payload, dict):
            return

        self._persist_payload_artifact(state, section_key, result.payload, result.agent_id or "")

    def _persist_payload_artifact(
        self,
        state: ResearchGraphState,
        section_key: str,
        payload: dict[str, Any],
        producer: str,
    ) -> None:
        state.checkpoint_version += 1
        version = state.checkpoint_version
        checksum = stable_hash(payload)
        artifact_id = deterministic_id(state.run_id, section_key, checksum, str(version))
        self.store.save_artifact(
            artifact_id=artifact_id,
            run_id=state.run_id,
            artifact_type="run_log_json",
            section_key=section_key,
            version=version,
            payload=payload,
            checksum=checksum,
            created_by_agent=producer,
            is_locked=False,
        )
        state.artifact_refs.append(
            {
                "artifact_id": artifact_id,
                "artifact_type": "run_log_json",
                "section_key": section_key,
                "version": version,
                "checksum": checksum,
                "is_locked": False,
                "producer": producer,
            }
        )

    def _record_tool_trace(
        self,
        state: ResearchGraphState,
        tool_name: str,
        summary: dict[str, Any],
        output_hash: str | None,
        gate_inputs: dict[str, Any] | None = None,
    ) -> None:
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
            "gate_inputs": gate_inputs or {},
        }
        state.trace.append(payload)
        self.store.add_audit_event(
            run_id=state.run_id,
            actor=self._agent_name(state.current_stage),
            action="tool_call",
            payload=payload,
        )

    @staticmethod
    def _artifact_path_for_section(state: ResearchGraphState, section_key: str) -> str | None:
        for ref in reversed(state.artifact_refs):
            if isinstance(ref, dict) and ref.get("section_key") == section_key and ref.get("storage_path"):
                return str(ref["storage_path"])
        return None

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

    def _write_run_manifest(self, state: "ResearchGraphState") -> None:
        """Write an ArtifactManifest from the ArtifactRefs collected during this run.

        Uses paths reported by tools via ArtifactRef.storage_path — not glob.
        Called at end of run_until_pause() and on checkpoint writes.
        """
        import logging
        from datetime import UTC, datetime

        from backend.storage import RUNS_BUCKET, SupabaseStorageAdapter, run_artifact_key

        artifact_entries: list[dict[str, str]] = []

        # The manifest must be built from the explicit ArtifactRefs emitted by
        # tools, not by rediscovering files after the run.
        for ref in state.artifact_refs:
            if not isinstance(ref, dict):
                continue
            path = str(ref.get("storage_path") or "")
            if not path:
                continue
            section_key = str(ref.get("section_key") or "")
            artifact_type = str(ref.get("artifact_type") or "")
            key = section_key
            if artifact_type == "report_md":
                key = "report"
            if not key:
                key = str(ref.get("artifact_id") or "")
            artifact_entries.append({
                "key": key,
                "path": path,
                "producer": str(ref.get("producer") or self._agent_name(state.current_stage)),
                "artifact_type": artifact_type,
                "version": int(ref.get("version") or 1),
                "checksum": ref.get("checksum"),
            })

        payload = {
            "schema_version": 1,
            "run_id": state.run_id,
            "ticker": state.ticker,
            "created_at": datetime.now(UTC).isoformat(),
            "artifacts": {
                entry["key"]: {
                    "path": entry["path"],
                    "producer": entry["producer"],
                    "artifact_type": entry["artifact_type"],
                    "version": entry["version"],
                    "checksum": entry["checksum"],
                }
                for entry in artifact_entries
            },
        }
        adapter = SupabaseStorageAdapter()
        manifest_path = run_artifact_key(state.run_id, "manifest.json")
        if not adapter.exists(RUNS_BUCKET, manifest_path):
            adapter.upload_json(RUNS_BUCKET, manifest_path, payload)
        state.manifest_path = manifest_path
        logging.getLogger(__name__).info(
            "Manifest written for run=%s: %s (%d artifacts)",
            state.run_id, manifest_path, len(artifact_entries),
        )

    def _write_evidence_packet(self, state: "ResearchGraphState") -> None:
        from backend.harness.evidence_packet import build_evidence_packet
        from backend.storage import RUNS_BUCKET, SupabaseStorageAdapter, run_artifact_key

        packet = build_evidence_packet(state)
        packet_path = run_artifact_key(state.run_id, "evidence_pack.json")
        adapter = SupabaseStorageAdapter()
        if not adapter.exists(RUNS_BUCKET, packet_path):
            adapter.upload_json(RUNS_BUCKET, packet_path, packet)
        ref = {
            "artifact_id": f"{state.run_id}_evidence_packet",
            "artifact_type": "evidence_packet_json",
            "section_key": "evidence_packet",
            "version": 1,
            "storage_bucket": RUNS_BUCKET,
            "storage_path": packet_path,
            "checksum": stable_hash(packet),
            "is_locked": False,
            "producer": "ResearchGraphRunner",
        }
        state.artifact_refs = [
            existing
            for existing in state.artifact_refs
            if not (
                isinstance(existing, dict)
                and existing.get("section_key") == "evidence_packet"
            )
        ]
        state.artifact_refs.append(ref)

    def _write_agent_effectiveness_audit(self, state: "ResearchGraphState") -> None:
        """No-op: agent effectiveness data is now in state.trace (trace.jsonl)."""
        pass

    @staticmethod
    def _agent_id_for_stage(stage: str) -> str:
        if stage in {"RESEARCH_MANAGER_PLAN", "RESEARCH_MANAGER_READINESS"}:
            return "research_manager"
        if stage in {"DATA_AND_EVIDENCE", "DATA_QUALITY_GATE"}:
            return "data_evidence"
        if stage in {"FINANCIAL_ANALYSIS", "FINANCIAL_ANALYSIS_GATE"}:
            return "financial_analysis"
        if stage in {"DRIVER_BASED_FORECAST", "FORECAST_QUALITY_GATE", "VALUATION_PROPOSAL", "VALUATION_EXECUTION", "VALUATION_GATE", "WAITING_ASSUMPTION_APPROVAL"}:
            return "forecast_valuation"
        if stage in {"THESIS_AND_REPORT", "REPORT_ASSEMBLY", "OPTIONAL_SINGLE_REPORT_REVISION"}:
            return "thesis_report"
        if stage == "SENIOR_CRITIC_REVIEW":
            return "senior_critic"
        return "service_node"

    @staticmethod
    def _agent_name(stage: str) -> str:
        agent_id = ResearchGraphRunner._agent_id_for_stage(stage)
        names = {
            "research_manager": "ResearchManagerAgent",
            "data_evidence": "DataEvidenceAgent",
            "financial_analysis": "FinancialAnalysisAgent",
            "forecast_valuation": "ForecastValuationAgent",
            "thesis_report": "ThesisReportAgent",
            "senior_critic": "SeniorCriticAgent",
        }
        if agent_id in names:
            return names[agent_id]
        return "ServiceNode"

    @staticmethod
    def _policy_reason(stage: str) -> str:
        return f"fixed_full_report_workflow:{stage.lower()}"

    @staticmethod
    def _db_status_for_stage(stage: str) -> str:
        if stage in {"DATA_AND_EVIDENCE", "DATA_QUALITY_GATE"}:
            return "running"
        if stage in {"RESEARCH_MANAGER_PLAN", "FINANCIAL_ANALYSIS", "FINANCIAL_ANALYSIS_GATE", "DRIVER_BASED_FORECAST", "FORECAST_QUALITY_GATE"}:
            return "analysis_ready"
        if stage in {"VALUATION_PROPOSAL", "VALUATION_EXECUTION", "VALUATION_GATE", "LOCK_RESEARCH_ARTIFACTS"}:
            return "valuation_ready"
        if stage in {"RESEARCH_MANAGER_READINESS", "THESIS_AND_REPORT", "REPORT_ASSEMBLY", "DETERMINISTIC_CONTENT_GATES", "SENIOR_CRITIC_REVIEW", "OPTIONAL_SINGLE_REPORT_REVISION", "FINAL_EXPORT_GATE", "CITATION_GATE"}:
            return "report_ready"
        if stage in {"WAITING_ASSUMPTION_APPROVAL", "WAITING_FINAL_APPROVAL"}:
            return "needs_human_review"
        if stage == "RENDER_AND_PUBLISH":
            return "approved"
        return "running"
