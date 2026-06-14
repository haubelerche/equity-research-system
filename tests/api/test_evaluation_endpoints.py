from __future__ import annotations

from fastapi.testclient import TestClient

import backend.api as api_module
from backend.api import create_app


class FakeStore:
    def __init__(self) -> None:
        self.runs = {
            "run-1": {
                "run_id": "run-1",
                "ticker": "DHG",
                "run_type": "full_report",
                "status": "approved",
                "current_stage": "done",
                "flags_json": {},
                "created_at": "2026-06-14T00:00:00+00:00",
                "updated_at": "2026-06-14T00:00:00+00:00",
                "finished_at": "2026-06-14T00:00:00+00:00",
            }
        }
        self.artifacts = [
            {
                "artifact_type": "eval_result_json",
                "section_key": "evaluation_packet",
                "payload": {"run_id": "run-1", "publication_status": "DRAFT_PUBLISHABLE"},
            },
            {
                "artifact_type": "eval_result_json",
                "section_key": "financial_eval",
                "payload": {"plan_id": "03", "status": "pass"},
            },
        ]

    def get_run(self, run_id: str):
        return self.runs.get(run_id)

    def list_artifacts(self, run_id: str):
        return list(self.artifacts) if run_id in self.runs else []


def test_project_evaluation_endpoints_use_allowlisted_loader(monkeypatch) -> None:
    monkeypatch.setattr(
        api_module,
        "load_latest_evaluation",
        lambda: {"publication_status": "BLOCKED_BY_P0", "artifacts": []},
    )
    monkeypatch.setattr(
        api_module,
        "load_evaluation_artifact",
        lambda name: {"artifact": name} if name == "financial_eval.json" else None,
    )
    client = TestClient(create_app(check_schema_on_startup=False))

    assert client.get("/eval/framework").json()["publication_status"] == "BLOCKED_BY_P0"
    assert client.get("/eval/results/financial_eval.json").json()["artifact"] == "financial_eval.json"
    assert client.get("/eval/artifacts/financial_eval.json").json()["artifact"] == "financial_eval.json"
    assert client.get("/eval/results/..%2f.env").status_code == 404
    assert client.get("/eval/artifacts/..%2f.env").status_code == 404


def test_run_evaluation_endpoints_read_eval_result_artifacts() -> None:
    client = TestClient(create_app(runtime_store=FakeStore(), check_schema_on_startup=False))

    packet = client.get("/research/run-1/evaluation")
    assert packet.status_code == 200
    assert packet.json()["publication_status"] == "DRAFT_PUBLISHABLE"

    artifact = client.get("/research/run-1/evaluation/financial_eval.json")
    assert artifact.status_code == 200
    assert artifact.json()["plan_id"] == "03"

    assert client.get("/research/run-1/evaluation/unknown.json").status_code == 404
    assert client.get("/research/missing/evaluation").status_code == 404
