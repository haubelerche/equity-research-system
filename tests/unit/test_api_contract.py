from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api import create_app


class FakeStore:
    def __init__(self) -> None:
        self.runs: dict[str, dict] = {}
        self.artifacts: dict[str, list[dict]] = {}
        self.companies: dict[str, dict] = {}

    def check_schema_version(self) -> None:
        return None

    def ensure_company_reference(
        self,
        *,
        ticker,
        company_name_vi,
        company_name_en,
        exchange,
        sector,
        subsector,
        universe_id,
        universe_name,
        peer_group,
        enabled_methods,
    ) -> None:
        self.companies[ticker] = {
            "ticker": ticker,
            "company_name_vi": company_name_vi,
            "exchange": exchange,
            "sector": sector,
            "universe_id": universe_id,
            "enabled_methods": enabled_methods,
        }

    def create_run(
        self,
        run_id,
        ticker,
        run_type,
        objective,
        flags,
        org_id=None,
        requested_by=None,
        idempotency_key=None,
        request_json=None,
        config_snapshot_json=None,
    ) -> None:
        self.runs[run_id] = {
            "run_id": run_id,
            "ticker": ticker,
            "run_type": run_type,
            "status": "initialized",
            "current_stage": "initialized",
            "flags_json": flags,
            "request_json": request_json or {"objective": objective},
            "config_snapshot_json": config_snapshot_json or {},
            "created_at": "2026-05-31T00:00:00+00:00",
            "updated_at": "2026-05-31T00:00:00+00:00",
            "finished_at": None,
        }

    def get_run(self, run_id):
        return self.runs.get(run_id)

    def list_artifacts(self, run_id):
        return self.artifacts.get(run_id, [])


class FakeSupervisor:
    def __init__(self, store: FakeStore) -> None:
        self.store = store
        self.approvals: list[dict] = []

    def handle_approval(self, run_id, stage, decision, reviewer, feedback_patch) -> None:
        self.approvals.append(
            {
                "run_id": run_id,
                "stage": stage,
                "decision": decision,
                "reviewer": reviewer,
                "feedback_patch": feedback_patch,
            }
        )
        self.store.runs[run_id]["status"] = "approved" if stage in {"final", "final_report"} and decision in {"approve", "approved"} else "needs_human_review"
        self.store.runs[run_id]["current_stage"] = "PUBLISHED" if self.store.runs[run_id]["status"] == "approved" else "NEEDS_REVIEW"

    def recompute_plan(self, run_id, event_type):
        return {"invalidates_stages": ["SYNTHESIZING"], "flags": {"citationsNeedRefresh": True}}

    def run_offline_evaluation(self, run_id):
        return {"grounding": 1.0, "accuracy": 0.9, "logicality": 0.85, "storytelling": 0.8}


class FakeExecutor:
    def __init__(self) -> None:
        self.submitted = []

    def submit(self, context) -> None:
        self.submitted.append(context)


def _client():
    store = FakeStore()
    supervisor = FakeSupervisor(store)
    executor = FakeExecutor()
    app = create_app(
        runtime_store=store,
        run_supervisor=supervisor,
        run_executor=executor,
        check_schema_on_startup=False,
    )
    return TestClient(app), store, supervisor, executor


def test_research_start_status_and_artifacts_endpoints() -> None:
    client, store, _, executor = _client()

    response = client.post(
        "/research/start",
        json={"ticker": "dhg", "run_type": "full_report", "objective": "api contract", "requested_by": "tester"},
    )
    assert response.status_code == 200
    body = response.json()
    run_id = body["run_id"]
    assert body["status"] == "INIT"
    assert executor.submitted[0].ticker == "DHG"

    status_response = client.get(f"/research/{run_id}/status")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "INIT"

    store.artifacts[run_id] = [
        {
            "artifact_id": "a1",
            "artifact_type": "run_log_json",
            "section_key": "graph_state_snapshot",
            "payload": {"kind": "graph_state_snapshot"},
            "confidence": None,
            "created_by_agent": "ResearchGraphRunner",
            "created_at": "2026-05-31T00:00:00+00:00",
        }
    ]
    artifacts_response = client.get(f"/research/{run_id}/artifacts")
    assert artifacts_response.status_code == 200
    assert artifacts_response.json()["artifacts"][0]["section_key"] == "graph_state_snapshot"


def test_research_start_registers_non_mvp_universe_ticker() -> None:
    client, store, _, executor = _client()

    response = client.post(
        "/research/start",
        json={"ticker": "dp3", "run_type": "full_report", "objective": "api contract", "requested_by": "tester"},
    )

    assert response.status_code == 200
    assert executor.submitted[0].ticker == "DP3"
    assert store.companies["DP3"]["exchange"] == "UPCOM"
    assert store.companies["DP3"]["sector"] == "pharma"


def test_approval_endpoint_preserves_public_aliases() -> None:
    client, store, supervisor, _ = _client()
    store.create_run("run1", "DHG", "full_report", "test", flags={})

    response = client.post(
        "/research/run1/approve",
        json={"stage": "final", "decision": "approve", "reviewer": "analyst", "feedback_patch": {}},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "PUBLISHED"
    assert supervisor.approvals[-1]["stage"] == "final"
    assert supervisor.approvals[-1]["decision"] == "approve"
