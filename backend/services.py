from __future__ import annotations

from dataclasses import dataclass
from backend.harness.model_adapter import _INPUT_COST_PER_M, _OUTPUT_COST_PER_M

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
        in_rate = _INPUT_COST_PER_M.get(model_name, 0.75)
        out_rate = _OUTPUT_COST_PER_M.get(model_name, 4.50)
        cost_usd = (prompt_tokens * in_rate + completion_tokens * out_rate) / 1_000_000
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

