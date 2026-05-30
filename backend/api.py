from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from backend.executor import RunExecutor
from backend.orchestrator import RunContext, Supervisor
from backend.runtime_store import RuntimeStore
from backend.schemas import (
    ApprovalRequest,
    ArtifactsResponse,
    RecomputeRequest,
    RunStatusResponse,
    RunStatus,
    StartRunRequest,
    StartRunResponse,
)
from backend.settings import settings
from backend.utils import deterministic_id
from backend.runtime_store import to_public_status


store = RuntimeStore(dsn=settings.database_url)
store.check_schema_version()
supervisor = Supervisor(store=store)
executor = RunExecutor(store=store, supervisor=supervisor)

app = FastAPI(title="Vietnam Pharma Multi-Agent Backend", version="0.1.0")


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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/research/start", response_model=StartRunResponse)
def start_research(request: StartRunRequest) -> StartRunResponse:
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
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return _to_status_response(run)


@app.get("/research/{run_id}/artifacts", response_model=ArtifactsResponse)
def get_artifacts(run_id: str) -> ArtifactsResponse:
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return ArtifactsResponse(run_id=run_id, artifacts=store.list_artifacts(run_id))


@app.get("/reports/{run_id}", response_model=ArtifactsResponse)
def get_report(run_id: str) -> ArtifactsResponse:
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    artifacts = [
        a for a in store.list_artifacts(run_id)
        if a["artifact_type"] in {"report_md", "eval_result_json", "run_log_json"}
    ]
    return ArtifactsResponse(run_id=run_id, artifacts=artifacts)


@app.post("/research/{run_id}/approve", response_model=RunStatusResponse)
def approve_run(run_id: str, request: ApprovalRequest) -> RunStatusResponse:
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    supervisor.handle_approval(
        run_id=run_id,
        stage=request.stage,
        decision=request.decision,
        reviewer=request.reviewer,
        feedback_patch=request.feedback_patch,
    )
    updated = store.get_run(run_id)
    if updated is None:
        raise HTTPException(status_code=500, detail="Run disappeared after approval handling")
    return _to_status_response(updated)


@app.post("/research/{run_id}/recompute")
def recompute_run(run_id: str, request: RecomputeRequest) -> dict[str, Any]:
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return supervisor.recompute_plan(run_id=run_id, event_type=request.event_type)


@app.post("/research/{run_id}/evaluate")
def evaluate_run(run_id: str) -> dict[str, float]:
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return supervisor.run_offline_evaluation(run_id)

