from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
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
    GenerateReportResponse,
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
    progress = run.get("progress_json", {}) or {}
    return RunStatusResponse(
        run_id=run["run_id"],
        ticker=run["ticker"],
        run_type=run["run_type"],
        status=RunStatus(to_public_status(run["status"])),
        current_stage=run["current_stage"],
        progress=progress,
        blocking_reason=progress.get("blocking_reason"),
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

    eval_artifacts_route = "/eval/" + "artifacts" + "/{artifact_name}"

    @app.get(eval_artifacts_route)
    def get_evaluation_artifact(artifact_name: str) -> dict[str, Any]:
        payload = load_evaluation_artifact(artifact_name)
        if payload is None:
            raise HTTPException(status_code=404, detail="Evaluation artifact not found")
        return payload

    @app.get("/reports")
    def list_reports() -> dict:
        universe = load_universe(_universe_csv())
        items = scan_report_inventory(_output_dir(), universe)
        try:
            from scripts.generate_fast_report import _latest_report_run_ids
        except Exception:  # noqa: BLE001 - report inventory must keep local fallback alive
            _latest_report_run_ids = None

        def _renderable_run_ids(ticker: str) -> list[str]:
            if _latest_report_run_ids is None:
                return []
            try:
                return list(_latest_report_run_ids(ticker, mode="analyst_draft"))
            except Exception:  # noqa: BLE001 - DB lineage is additive, local files are fallback
                return []

        def _report_item_payload(item) -> dict[str, Any]:
            renderable_run_ids = _renderable_run_ids(item.ticker)
            return {
                "ticker": item.ticker,
                "company_name": item.company_name,
                "exchange": item.exchange,
                "segment": item.segment,
                "is_mvp": item.is_mvp,
                "has_report": item.has_report,
                "has_explanation": item.has_explanation,
                "preview_pages": item.preview_pages,
                "report_size": item.report_size,
                "updated_at": item.updated_at,
                "renderable_run_ids": renderable_run_ids,
                "lineage_source": "manifest" if renderable_run_ids else "local_files",
            }

        return {
            "items": [_report_item_payload(i) for i in items]
        }

    _FILE_KINDS = {"report": "_report.pdf", "explanation": "_explanation.pdf"}
    _EXPORT_NAMES = {"report": "report.pdf", "explanation": "explanation.pdf"}

    def _export_storage():
        """Supabase exports adapter, or None when storage is unconfigured (dev)."""
        try:
            from backend.storage import SupabaseStorageAdapter

            return SupabaseStorageAdapter()
        except Exception:
            return None

    def _serve_from_exports(ticker: str, kind: str) -> Response | None:
        """Stream the durable PDF from Supabase exports, or None to fall back."""
        export_name = _EXPORT_NAMES.get(kind)
        if export_name is None:
            return None
        storage = _export_storage()
        if storage is None:
            return None
        try:
            from backend.storage import EXPORTS_BUCKET, client_report_key

            data = storage.download_bytes(EXPORTS_BUCKET, client_report_key(ticker, export_name))
        except Exception:
            return None
        return Response(
            content=data,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{ticker}_{export_name}"'},
        )

    @app.get("/reports/{ticker}/file/{kind}")
    def get_report_file(ticker: str, kind: str):
        ticker = ticker.upper()
        if ticker not in _universe_index():
            raise HTTPException(status_code=404, detail="Unknown ticker")
        suffix = _FILE_KINDS.get(kind)
        if suffix is None:
            raise HTTPException(status_code=404, detail="Unknown file kind")
        # Prefer the durable copy in Supabase exports (survives ephemeral disk);
        # fall back to a locally rendered file for dev / same-box renders.
        served = _serve_from_exports(ticker, kind)
        if served is not None:
            return served
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

    @app.post("/reports/{ticker}/generate", response_model=GenerateReportResponse)
    def generate_report(ticker: str) -> GenerateReportResponse:
        ticker = ticker.upper()
        if ticker not in _universe_index():
            raise HTTPException(status_code=404, detail="Unknown ticker")
        store = app.state.store
        executor = app.state.executor

        # Route fast (render from existing artifacts) vs full pipeline. Any error
        # here just means "no renderable run yet" -> run the full pipeline.
        source_run_id: str | None = None
        try:
            from backend.dataops.snapshot_freshness import latest_ready_snapshot
            from backend.reporting.report_delivery import latest_renderable_run_id

            if latest_ready_snapshot(ticker) is not None:
                source_run_id = latest_renderable_run_id(ticker)
        except Exception:
            source_run_id = None
        mode = "fast_render" if source_run_id else "full_pipeline"

        objective = f"Generate full equity research report for {ticker}"
        # Fresh run per click (a uuid component) so "Cập nhật"/re-render always
        # produces a new pollable run instead of returning a stale one.
        run_id = deterministic_id(ticker, mode, objective, uuid.uuid4().hex)
        policy = {
            "budget_policy": settings.default_budget_policy,
            "soft_budget_usd": settings.soft_budget_usd,
            "hard_budget_usd": settings.hard_budget_usd,
            "fallback_model": settings.fallback_model,
        }
        flags: dict[str, Any] = {
            "factsChanged": False,
            "catalystChanged": False,
            "valuationChanged": False,
            "thesisNeedsRefresh": False,
            "citationsNeedRefresh": False,
            "generate_mode": mode,
        }
        if source_run_id:
            flags["source_run_id"] = source_run_id

        ensure_ticker_registered_from_universe(store, ticker)
        store.create_run(
            run_id=run_id,
            ticker=ticker,
            run_type="full_report",
            objective=objective,
            flags=flags,
            config_snapshot_json=policy,
        )
        executor.submit(
            RunContext(
                run_id=run_id,
                ticker=ticker,
                run_type="full_report",
                objective=objective,
                policy=policy,
                flags=flags,
            )
        )
        return GenerateReportResponse(run_id=run_id, mode=mode)

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

