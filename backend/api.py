from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from backend.reporting.output_inventory import scan_report_inventory, load_universe

from backend.executor import RunExecutor
from backend.orchestrator import FullReportOrchestrator, RunContext
from backend.runtime_store import RuntimeStore
from backend.schemas import (
    ArtifactsResponse,
    RunStatusResponse,
    RunStatus,
    StartRunRequest,
    StartRunResponse,
)
from backend.settings import settings
from backend.universe_registration import ensure_ticker_registered_from_universe
from backend.utils import deterministic_id
from backend.runtime_store import to_public_status


def _to_status_response(run: dict[str, Any]) -> RunStatusResponse:
    return RunStatusResponse(
        run_id=run["run_id"],
        ticker=run["ticker"],
        run_type=run["run_type"],
        status=RunStatus(to_public_status(run["status"])),
        current_stage=run["current_stage"],
        flags=run.get("flags_json", {}),
        created_at=run["created_at"],
        updated_at=run["updated_at"],
        finished_at=run.get("finished_at"),
    )


def create_app(
    runtime_store: RuntimeStore | None = None,
    run_orchestrator: FullReportOrchestrator | None = None,
    run_executor: RunExecutor | None = None,
    check_schema_on_startup: bool = True,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.store is None:
            app.state.store = RuntimeStore(dsn=settings.database_url)
        if app.state.orchestrator is None:
            app.state.orchestrator = FullReportOrchestrator(store=app.state.store)
        if app.state.executor is None:
            app.state.executor = RunExecutor(store=app.state.store, orchestrator=app.state.orchestrator)
        if check_schema_on_startup:
            app.state.store.check_schema_version()
        yield

    app = FastAPI(title="Vietnam Pharma Multi-Agent Backend", version="0.1.0", lifespan=lifespan)
    app.state.store = runtime_store
    app.state.orchestrator = run_orchestrator
    app.state.executor = run_executor
    app.state.report_output_dir = None
    app.state.report_universe_csv = None

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/research/start", response_model=StartRunResponse)
    def start_research(request: StartRunRequest) -> StartRunResponse:
        store = app.state.store
        executor = app.state.executor
        run_id = deterministic_id(
            request.ticker.upper(),
            request.run_type.value,
            request.objective,
            request.requested_by or "anonymous",
        )
        initial_flags = {
            "factsChanged": False,
            "catalystChanged": False,
            "valuationChanged": False,
            "thesisNeedsRefresh": False,
            "citationsNeedRefresh": False,
        }
        policy = {
            "budget_policy": request.budget_policy or settings.default_budget_policy,
            "soft_budget_usd": settings.soft_budget_usd,
            "hard_budget_usd": settings.hard_budget_usd,
            "fallback_model": settings.fallback_model,
        }
        try:
            ensure_ticker_registered_from_universe(store, request.ticker.upper())
            store.create_run(
                run_id=run_id,
                ticker=request.ticker.upper(),
                run_type=request.run_type.value,
                objective=request.objective,
                flags=initial_flags,
                config_snapshot_json=policy,
                org_id=request.org_id,
                requested_by=request.requested_by,
            )
        except Exception:
            existing = store.get_run(run_id)
            if existing:
                return StartRunResponse(run_id=run_id, status=RunStatus(to_public_status(existing["status"])))
            raise

        executor.submit(
            RunContext(
                run_id=run_id,
                ticker=request.ticker.upper(),
                run_type=request.run_type.value,
                objective=request.objective,
                policy=policy,
                flags=initial_flags,
            )
        )
        return StartRunResponse(run_id=run_id, status=RunStatus.INIT)

    @app.get("/research/{run_id}/status", response_model=RunStatusResponse)
    def get_run_status(run_id: str) -> RunStatusResponse:
        run = app.state.store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        return _to_status_response(run)

    @app.get("/research/{run_id}/artifacts", response_model=ArtifactsResponse)
    def get_artifacts(run_id: str) -> ArtifactsResponse:
        run = app.state.store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        return ArtifactsResponse(run_id=run_id, artifacts=app.state.store.list_artifacts(run_id))

    def _output_dir() -> Path:
        return Path(getattr(app.state, "report_output_dir", None) or "output")

    def _universe_csv() -> Path:
        return Path(
            getattr(app.state, "report_universe_csv", None)
            or "config/dataset/universe/pharma_vn_universe.csv"
        )

    @app.get("/reports")
    def list_reports() -> dict:
        universe = load_universe(_universe_csv())
        items = scan_report_inventory(_output_dir(), universe)
        return {
            "items": [
                {
                    "ticker": i.ticker,
                    "company_name": i.company_name,
                    "exchange": i.exchange,
                    "segment": i.segment,
                    "is_mvp": i.is_mvp,
                    "has_report": i.has_report,
                    "has_explanation": i.has_explanation,
                    "preview_pages": i.preview_pages,
                    "report_size": i.report_size,
                    "updated_at": i.updated_at,
                }
                for i in items
            ]
        }

    @app.get("/reports/{run_id}", response_model=ArtifactsResponse)
    def get_report(run_id: str) -> ArtifactsResponse:
        run = app.state.store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        artifacts = [
            a for a in app.state.store.list_artifacts(run_id)
            if a["artifact_type"] in {"report_md", "eval_result_json", "run_log_json"}
        ]
        return ArtifactsResponse(run_id=run_id, artifacts=artifacts)

    return app


app = create_app(check_schema_on_startup=False)

