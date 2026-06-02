from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.dataset.dqf import stages_to_invalidate

from backend.runtime_store import RuntimeStore
from backend.settings import Settings


@dataclass(frozen=True)
class BudgetDecision:
    allow: bool
    stop_reason: str | None = None
    fallback_model: str | None = None


class BudgetGuard:
    def __init__(self, store: RuntimeStore, settings: Settings) -> None:
        self.store = store
        self.settings = settings

    def charge(
        self,
        run_id: str,
        step_name: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        budget_policy: str,
    ) -> BudgetDecision:
        # Conservative approximation. Replace with provider billing in production.
        cost_usd = ((prompt_tokens * 0.2) + (completion_tokens * 0.8)) / 1_000_000
        run_total = self.store.run_cost_usd(run_id) + cost_usd
        fallback_model: str | None = None
        stop_reason: str | None = None

        if run_total > self.settings.hard_budget_usd:
            stop_reason = "hard_budget_exceeded"
        elif run_total > self.settings.soft_budget_usd:
            fallback_model = self.settings.fallback_model

        self.store.add_budget_entry(
            run_id=run_id,
            step_name=step_name,
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            budget_policy=budget_policy,
            fallback_model=fallback_model,
            stop_reason=stop_reason,
        )

        if stop_reason:
            return BudgetDecision(allow=False, stop_reason=stop_reason, fallback_model=fallback_model)
        return BudgetDecision(allow=True, fallback_model=fallback_model)


class RecomputePlanner:
    @staticmethod
    def decide(event_type: str) -> dict[str, Any]:
        invalidates = stages_to_invalidate(event_type)
        flags = {
            "factsChanged": "VALUATING" in invalidates or "NORMALIZING" in invalidates,
            "catalystChanged": True,
            "valuationChanged": "VALUATING" in invalidates,
            "thesisNeedsRefresh": True,
            "citationsNeedRefresh": "SYNTHESIZING" in invalidates or "ANALYZING" in invalidates,
        }
        return {"invalidates_stages": invalidates, "flags": flags}


class OfflineEvaluator:
    """Minimal offline gate scaffolding for phase-5."""

    def evaluate(self, artifacts: list[dict[str, Any]]) -> dict[str, float]:
        if not artifacts:
            return {
                "grounding": 0.0,
                "accuracy": 0.0,
                "logicality": 0.0,
                "storytelling": 0.0,
            }

        citation_artifacts = [
            a for a in artifacts
            if a["artifact_type"] == "eval_result_json"
            or a.get("section_key") in {"audit_review", "quality", "citation_gate"}
        ]
        coverage = 1.0 if citation_artifacts else 0.5
        return {
            "grounding": coverage,
            "accuracy": 0.9 if coverage >= 1 else 0.7,
            "logicality": 0.85,
            "storytelling": 0.8,
        }

