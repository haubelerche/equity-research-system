from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from backend.harness.runner import ResearchGraphRunner
from backend.period_scope import DEFAULT_FROM_YEAR, DEFAULT_TO_YEAR
from backend.runtime_store import RuntimeStore
from backend.settings import Settings, settings

_log = logging.getLogger(__name__)

# DB statuses for which a downloadable report can be rendered from run artifacts.
_RENDERABLE_STATUSES = {"auto_exported", "approved", "report_ready"}


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
        mode = (context.flags or {}).get("generate_mode", "full_pipeline")
        if mode == "fast_render":
            return self._fast_render(context)
        final = self.runner.execute(context)
        self._render_after_run(context)
        return final

    def _fast_render(self, context: RunContext):
        """Render + store a report from an existing run's artifacts (~30s).

        No pipeline, no LLM calls. Used when the ticker already has renderable
        artifacts (e.g. the "Cập nhật" button).
        """
        source_run_id = (context.flags or {}).get("source_run_id") or context.run_id
        self.store.update_run_state(context.run_id, "report_ready", "PUBLISH")
        self.store.update_run_progress(
            context.run_id, substep="rendering", detail="Đang dựng file báo cáo…"
        )
        try:
            from backend.reporting.report_delivery import render_and_store

            render_and_store(context.ticker, source_run_id)
        except Exception as exc:  # noqa: BLE001
            self.store.update_run_progress(
                context.run_id,
                blocking_reason=f"Không dựng được file báo cáo cho {context.ticker}.",
            )
            self.store.update_run_state(context.run_id, "failed", "PUBLISH", finished=True)
            _log.warning("fast render failed for %s run=%s: %s", context.ticker, context.run_id, exc)
            return None
        self.store.update_run_state(context.run_id, "auto_exported", "PUBLISH", finished=True)
        return None

    def _render_after_run(self, context: RunContext) -> None:
        """After a full pipeline run reaches a publishable state, render + store.

        Non-fatal: rendering problems must not flip an otherwise-successful run.
        """
        run = self.store.get_run(context.run_id)
        if run is None or run["status"] not in _RENDERABLE_STATUSES:
            return
        try:
            from backend.reporting.report_delivery import render_and_store

            render_and_store(context.ticker, context.run_id)
        except Exception as exc:  # noqa: BLE001
            _log.warning("post-run render failed for %s run=%s: %s", context.ticker, context.run_id, exc)

