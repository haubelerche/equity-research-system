from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.harness.runner import ResearchGraphRunner
from backend.period_scope import DEFAULT_FROM_YEAR, DEFAULT_TO_YEAR
from backend.runtime_store import RuntimeStore
from backend.settings import Settings, settings


@dataclass
class RunContext:
    run_id: str
    ticker: str
    run_type: str
    objective: str
    policy: dict[str, Any]
    flags: dict[str, Any]
    from_year: int = DEFAULT_FROM_YEAR
    to_year: int = DEFAULT_TO_YEAR
    ocr: bool = False


class FullReportOrchestrator:
    """Lifecycle-only orchestrator for the single v1 production workflow."""

    def __init__(self, store: RuntimeStore, app_settings: Settings | None = None, progress=None) -> None:
        self.store = store
        self.settings = app_settings or settings
        self.runner = ResearchGraphRunner(store=store, app_settings=self.settings, progress=progress)

    def execute(self, context: RunContext):
        if context.run_type != "full_report":
            raise ValueError("v1 supports only run_type='full_report'")
        return self.runner.execute(context)

