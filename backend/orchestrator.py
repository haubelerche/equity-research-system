from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scripts.db.fact_store import PostgresFactStore

from backend.agents import AuditorAgent, DataAgent, DebateAgent, QuantAgent, ResearcherAgent
from backend.runtime_store import RuntimeStore
from backend.retrieval import RetrievalService
from backend.services import BudgetGuard, OfflineEvaluator, RecomputePlanner
from backend.settings import Settings, settings
from backend.utils import deterministic_id


@dataclass
class RunContext:
    run_id: str
    ticker: str
    run_type: str
    objective: str
    policy: dict[str, Any]
    flags: dict[str, Any]


class Supervisor:
    """Hybrid orchestrator: deterministic state flow + policy-guided routing."""

    def __init__(self, store: RuntimeStore, app_settings: Settings | None = None) -> None:
        self.store = store
        self.settings = app_settings or settings
        self.fact_store = PostgresFactStore(dsn=self.settings.database_url)
        self.data_agent = DataAgent(store)
        self.quant_agent = QuantAgent(self.fact_store)
        self.researcher_agent = ResearcherAgent()
        self.debate_agent = DebateAgent()
        self.auditor_agent = AuditorAgent()
        self.retrieval = RetrievalService()
        self.budget = BudgetGuard(store, self.settings)
        self.offline_eval = OfflineEvaluator()

    def _charge_or_stop(self, run_id: str, step_name: str, budget_policy: str) -> bool:
        decision = self.budget.charge(
            run_id=run_id,
            step_name=step_name,
            model_name=self.settings.default_model_name,
            prompt_tokens=1200,
            completion_tokens=400,
            budget_policy=budget_policy,
        )
        if not decision.allow:
            self.store.update_run_state(
                run_id=run_id,
                status="NEEDS_REVIEW",
                stage="NEEDS_REVIEW",
            )
            self.store.add_audit_event(
                run_id=run_id,
                actor="Supervisor",
                action="budget_stop",
                policy_reason=decision.stop_reason,
                payload={"step_name": step_name, "fallback_model": decision.fallback_model},
            )
            return False
        return True

    def _run_agent_step(
        self,
        run_id: str,
        step_name: str,
        agent_name: str,
        status: str,
        policy_reason: str,
        fn,
    ) -> Any:
        step_id = self.store.add_step(
            run_id=run_id,
            step_name=step_name,
            agent_name=agent_name,
            status="STARTED",
            policy_reason=policy_reason,
        )
        try:
            result = fn()
            self.store.close_step(step_id, "COMPLETED")
            self.store.add_audit_event(
                run_id=run_id,
                actor="Supervisor",
                action="agent_step_completed",
                policy_reason=policy_reason,
                payload={"step_name": step_name, "agent_name": agent_name},
            )
            return result
        except Exception as exc:  # noqa: BLE001
            self.store.close_step(step_id, "FAILED", metadata={"error": str(exc)})
            self.store.update_run_state(run_id=run_id, status="FAILED", stage=status, finished=True)
            self.store.add_audit_event(
                run_id=run_id,
                actor="Supervisor",
                action="agent_step_failed",
                policy_reason=policy_reason,
                payload={"step_name": step_name, "agent_name": agent_name, "error": str(exc)},
            )
            raise

    def execute(self, context: RunContext) -> None:
        budget_policy = context.policy.get("budget_policy", self.settings.default_budget_policy)
        run_id = context.run_id
        ticker = context.ticker

        self.store.update_run_state(run_id=run_id, status="INGESTING", stage="INGESTING", flags=context.flags)
        if not self._charge_or_stop(run_id=run_id, step_name="INGESTING", budget_policy=budget_policy):
            return
        data_result = self._run_agent_step(
            run_id=run_id,
            step_name="INGESTING",
            agent_name="DataAgent",
            status="INGESTING",
            policy_reason="rule:first_step_ingest",
            fn=lambda: self.data_agent.run(run_id=run_id, ticker=ticker),
        )
        self.store.save_artifact(
            artifact_id=deterministic_id(run_id, "ingestion_summary"),
            run_id=run_id,
            artifact_type="ingestion_summary",
            payload=data_result.payload,
            evidence_refs=data_result.evidence_refs,
            confidence=data_result.confidence,
            created_by_agent="DataAgent",
        )

        # Phase-3 grounding foundation: build/refresh retrieval index.
        self.store.update_run_state(run_id=run_id, status="ANALYZING", stage="INDEXING")
        index_step_id = self.store.add_step(
            run_id=run_id,
            step_name="INDEXING",
            agent_name="DataAgent",
            status="STARTED",
            policy_reason="rule:post_ingest_indexing",
        )
        indexed_chunks = self.retrieval.build_index()
        self.store.close_step(index_step_id, "COMPLETED", metadata={"indexed_chunks": indexed_chunks})
        self.store.save_artifact(
            artifact_id=deterministic_id(run_id, "retrieval_index_stats"),
            run_id=run_id,
            artifact_type="retrieval_index_stats",
            payload={"indexed_chunks": indexed_chunks},
            created_by_agent="DataAgent",
        )

        self.store.update_run_state(run_id=run_id, status="VALUATING", stage="VALUATING", flags=context.flags)
        if not self._charge_or_stop(run_id=run_id, step_name="VALUATING", budget_policy=budget_policy):
            return
        quant_result = self._run_agent_step(
            run_id=run_id,
            step_name="VALUATING",
            agent_name="QuantAgent",
            status="VALUATING",
            policy_reason="rule:post_ingest_quant",
            fn=lambda: self.quant_agent.run(ticker=ticker),
        )
        self.store.save_artifact(
            artifact_id=deterministic_id(run_id, "valuation_artifact"),
            run_id=run_id,
            artifact_type="valuation_artifact",
            payload=quant_result.payload,
            evidence_refs=quant_result.evidence_refs,
            confidence=quant_result.confidence,
            created_by_agent="QuantAgent",
        )
        if quant_result.needs_human:
            self.store.update_run_state(run_id=run_id, status="NEEDS_REVIEW", stage="NEEDS_REVIEW")
            return

        self.store.update_run_state(run_id=run_id, status="SYNTHESIZING", stage="SYNTHESIZING")
        if not self._charge_or_stop(run_id=run_id, step_name="SYNTHESIZING", budget_policy=budget_policy):
            return
        researcher_result = self._run_agent_step(
            run_id=run_id,
            step_name="SYNTHESIZING",
            agent_name="ResearcherAgent",
            status="SYNTHESIZING",
            policy_reason="rule:quant_to_research",
            fn=lambda: self.researcher_agent.run(ticker=ticker, valuation_payload=quant_result.payload),
        )
        self.store.save_artifact(
            artifact_id=deterministic_id(run_id, "research_draft"),
            run_id=run_id,
            artifact_type="research_draft",
            payload=researcher_result.payload,
            evidence_refs=quant_result.evidence_refs,
            confidence=researcher_result.confidence,
            created_by_agent="ResearcherAgent",
        )

        self.store.update_run_state(run_id=run_id, status="ANALYZING", stage="DEBATING")
        if not self._charge_or_stop(run_id=run_id, step_name="DEBATING", budget_policy=budget_policy):
            return
        debate_result = self._run_agent_step(
            run_id=run_id,
            step_name="DEBATING",
            agent_name="ResearcherAgent",
            status="DEBATING",
            policy_reason="policy:plan_and_execute_debate",
            fn=lambda: self.debate_agent.run(
                ticker=ticker,
                thesis_payload=researcher_result.payload,
                valuation_payload=quant_result.payload,
            ),
        )
        self.store.save_artifact(
            artifact_id=deterministic_id(run_id, "debate_report"),
            run_id=run_id,
            artifact_type="debate_report",
            payload=debate_result.payload,
            evidence_refs=debate_result.evidence_refs,
            confidence=debate_result.confidence,
            created_by_agent="ResearcherAgent",
        )

        if debate_result.needs_human:
            self.store.update_run_state(run_id=run_id, status="NEEDS_REVIEW", stage="NEEDS_REVIEW")
            return

        retrieved_refs = self.retrieval.evidence_for_claims(
            ticker=ticker,
            claims=researcher_result.payload.get("claims", []),
        )
        combined_refs = list(quant_result.evidence_refs) + retrieved_refs

        self.store.update_run_state(run_id=run_id, status="AUDITING", stage="AUDITING")
        if not self._charge_or_stop(run_id=run_id, step_name="AUDITING", budget_policy=budget_policy):
            return
        auditor_result = self._run_agent_step(
            run_id=run_id,
            step_name="AUDITING",
            agent_name="AuditorAgent",
            status="AUDITING",
            policy_reason="rule:research_to_audit",
            fn=lambda: self.auditor_agent.run(
                ticker=ticker,
                claims=researcher_result.payload.get("claims", []),
                evidence_refs=combined_refs,
            ),
        )
        self.store.save_artifact(
            artifact_id=deterministic_id(run_id, "audit_report"),
            run_id=run_id,
            artifact_type="audit_report",
            payload=auditor_result.payload,
            evidence_refs=auditor_result.evidence_refs,
            confidence=auditor_result.confidence,
            created_by_agent="AuditorAgent",
        )

        if not auditor_result.payload.get("passed", False):
            self.store.update_run_state(run_id=run_id, status="NEEDS_REVIEW", stage="NEEDS_REVIEW")
            return

        self.store.update_run_state(
            run_id=run_id,
            status="WAITING_ASSUMPTIONS_APPROVAL",
            stage="WAITING_ASSUMPTIONS_APPROVAL",
        )
        self.store.add_audit_event(
            run_id=run_id,
            actor="Supervisor",
            action="hitl_required",
            rule_reason="two_gate_approval_policy",
            payload={"next_stage": "assumptions"},
        )

    def handle_approval(self, run_id: str, stage: str, decision: str, reviewer: str, feedback_patch: dict[str, Any]) -> None:
        self.store.add_approval(run_id=run_id, stage=stage, decision=decision, reviewer=reviewer, feedback_patch=feedback_patch)

        if decision == "reject":
            self.store.update_run_state(run_id=run_id, status="NEEDS_REVIEW", stage="NEEDS_REVIEW")
            self.store.save_artifact(
                artifact_id=deterministic_id(run_id, "review_feedback", stage),
                run_id=run_id,
                artifact_type="review_feedback",
                payload={"stage": stage, "reviewer": reviewer, "feedback_patch": feedback_patch},
                created_by_agent="Supervisor",
            )
            return

        if stage == "assumptions":
            self.store.update_run_state(run_id=run_id, status="WAITING_FINAL_APPROVAL", stage="WAITING_FINAL_APPROVAL")
            return
        if stage == "final":
            self.store.update_run_state(run_id=run_id, status="PUBLISHED", stage="PUBLISHED", finished=True)
            self.store.save_artifact(
                artifact_id=deterministic_id(run_id, "published_report"),
                run_id=run_id,
                artifact_type="published_report",
                payload={"published_by": reviewer},
                created_by_agent="Supervisor",
            )

    def recompute_plan(self, run_id: str, event_type: str) -> dict[str, Any]:
        plan = RecomputePlanner.decide(event_type=event_type)
        run = self.store.get_run(run_id)
        merged_flags = dict((run or {}).get("flags_json", {}))
        merged_flags.update(plan["flags"])
        self.store.update_run_state(
            run_id=run_id,
            status="NEEDS_REVIEW",
            stage="NEEDS_REVIEW",
            flags=merged_flags,
        )
        self.store.save_artifact(
            artifact_id=deterministic_id(run_id, "recompute_plan", event_type),
            run_id=run_id,
            artifact_type="recompute_plan",
            payload=plan,
            created_by_agent="Supervisor",
        )
        return plan

    def run_offline_evaluation(self, run_id: str) -> dict[str, float]:
        artifacts = self.store.list_artifacts(run_id)
        result = self.offline_eval.evaluate(artifacts)
        self.store.save_artifact(
            artifact_id=deterministic_id(run_id, "offline_evaluation"),
            run_id=run_id,
            artifact_type="offline_evaluation",
            payload=result,
            created_by_agent="Supervisor",
        )
        return result

