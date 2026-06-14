from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request


def _load_dotenv() -> None:
    """Load .env before importing backend.settings (which reads os.environ at
    import time), so `uvicorn backend.api:app` works without manually exporting
    variables — matching the CLI scripts' behaviour."""
    import os

    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

from backend.reporting.output_inventory import scan_report_inventory, load_universe
from backend.evaluation.project_evaluator import (
    load_evaluation_artifact,
    load_latest_evaluation,
)

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
    if settings.cors_allow_origins or settings.cors_allow_origin_regex:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_allow_origins),
            allow_origin_regex=settings.cors_allow_origin_regex or None,
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=False,
        )
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

    def _run_eval_artifact(run_id: str, artifact_name: str) -> dict[str, Any] | None:
        section_key = artifact_name.removesuffix(".json")
        for artifact in app.state.store.list_artifacts(run_id):
            if artifact.get("artifact_type") != "eval_result_json":
                continue
            if artifact.get("section_key") == section_key:
                payload = artifact.get("payload")
                return payload if isinstance(payload, dict) else {}
        return None

    @app.get("/research/{run_id}/evaluation")
    def get_run_evaluation(run_id: str) -> dict[str, Any]:
        run = app.state.store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        payload = _run_eval_artifact(run_id, "evaluation_packet.json")
        if payload is None:
            raise HTTPException(status_code=404, detail="Run evaluation packet not found")
        return payload

    @app.get("/research/{run_id}/evaluation/{artifact_name}")
    def get_run_evaluation_artifact(run_id: str, artifact_name: str) -> dict[str, Any]:
        from backend.evaluation.run_evaluation import RUNTIME_EVALUATION_ARTIFACTS

        allowed = set(RUNTIME_EVALUATION_ARTIFACTS) | {"evaluation_packet.json"}
        if artifact_name not in allowed:
            raise HTTPException(status_code=404, detail="Evaluation artifact not found")
        run = app.state.store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        payload = _run_eval_artifact(run_id, artifact_name)
        if payload is None:
            raise HTTPException(status_code=404, detail="Run evaluation artifact not found")
        return payload

    def _output_dir() -> Path:
        return Path(getattr(app.state, "report_output_dir", None) or settings.report_output_dir)

    def _universe_csv() -> Path:
        return Path(
            getattr(app.state, "report_universe_csv", None)
            or settings.report_universe_csv
        )

    def _universe_index() -> dict[str, dict]:
        return {r["ticker"]: r for r in load_universe(_universe_csv())}

    @app.get("/eval/framework")
    def get_evaluation_framework() -> dict[str, Any]:
        return load_latest_evaluation()

    @app.get("/eval/results/{artifact_name}")
    def get_evaluation_result(artifact_name: str) -> dict[str, Any]:
        payload = load_evaluation_artifact(artifact_name)
        if payload is None:
            raise HTTPException(status_code=404, detail="Evaluation artifact not found")
        return payload

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

    _FILE_KINDS = {"report": "_report.pdf", "explanation": "_explanation.pdf"}

    @app.get("/reports/{ticker}/file/{kind}")
    def get_report_file(ticker: str, kind: str):
        ticker = ticker.upper()
        if ticker not in _universe_index():
            raise HTTPException(status_code=404, detail="Unknown ticker")
        suffix = _FILE_KINDS.get(kind)
        if suffix is None:
            raise HTTPException(status_code=404, detail="Unknown file kind")
        path = (_output_dir() / f"{ticker}{suffix}").resolve()
        out_root = _output_dir().resolve()
        if out_root not in path.parents or not path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(
            path,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{ticker}{suffix}"'},
        )

    @app.get("/reports/{ticker}/preview/{page}")
    def get_report_preview(ticker: str, page: int):
        ticker = ticker.upper()
        if ticker not in _universe_index():
            raise HTTPException(status_code=404, detail="Unknown ticker")
        path = (_output_dir() / "pdf_preview" / f"{ticker}_report_page_{page}.png").resolve()
        out_root = (_output_dir() / "pdf_preview").resolve()
        if out_root not in path.parents or not path.is_file():
            raise HTTPException(status_code=404, detail="Preview not found")
        return FileResponse(path, media_type="image/png")

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


def mount_frontend(app: FastAPI, dist_dir: Path) -> None:
    """Serve a built Vite SPA. Call AFTER all API routes are registered."""
    dist_dir = Path(dist_dir)
    if not (dist_dir / "index.html").is_file():
        return
    assets = dist_dir / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str, request: Request):
        candidate = (dist_dir / full_path).resolve()
        if candidate.is_file() and dist_dir.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(dist_dir / "index.html")


app = create_app(check_schema_on_startup=False)
if (Path("frontend/dist") / "index.html").is_file():
    mount_frontend(app, Path("frontend/dist"))

