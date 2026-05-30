from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.harness.runner import ResearchGraphRunner
from backend.runtime_store import RuntimeStore
from backend.services import OfflineEvaluator, RecomputePlanner
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
    """Backward-compatible facade over the LangGraph harness runner."""

    def __init__(self, store: RuntimeStore, app_settings: Settings | None = None) -> None:
        self.store = store
        self.settings = app_settings or settings
        self.runner = ResearchGraphRunner(store=store, app_settings=self.settings)
        self.offline_eval = OfflineEvaluator()

    def execute(self, context: RunContext) -> None:
        self.runner.execute(context)

    def handle_approval(self, run_id: str, stage: str, decision: str, reviewer: str, feedback_patch: dict[str, Any]) -> None:
        self.runner.handle_approval(
            run_id=run_id,
            stage=stage,
            decision=decision,
            reviewer=reviewer,
            feedback_patch=feedback_patch,
        )

    def recompute_plan(self, run_id: str, event_type: str) -> dict[str, Any]:
        plan = RecomputePlanner.decide(event_type=event_type)
        run = self.store.get_run(run_id)
        merged_flags = dict((run or {}).get("flags_json", {}))
        merged_flags.update(plan["flags"])
        self.store.update_run_state(
            run_id=run_id,
            status="needs_human_review",
            stage="NEEDS_REVIEW",
            flags=merged_flags,
        )
        self.store.save_artifact(
            artifact_id=deterministic_id(run_id, "recompute_plan", event_type),
            run_id=run_id,
            artifact_type="run_log_json",
            section_key="recompute_plan",
            payload={"kind": "recompute_plan", **plan},
            created_by_agent="Supervisor",
        )
        return plan

    def run_offline_evaluation(self, run_id: str) -> dict[str, float]:
        artifacts = self.store.list_artifacts(run_id)
        result = self.offline_eval.evaluate(artifacts)
        self.store.save_artifact(
            artifact_id=deterministic_id(run_id, "offline_evaluation"),
            run_id=run_id,
            artifact_type="eval_result_json",
            section_key="offline_evaluation",
            payload={"kind": "offline_evaluation", **result},
            created_by_agent="Supervisor",
        )
        return result
