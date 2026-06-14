from __future__ import annotations

from backend.evaluation.run_evaluation import (
    RUNTIME_EVALUATION_ARTIFACTS,
    build_run_evaluation_artifacts,
)
from backend.harness.gates import pass_gate
from backend.harness.runner import ResearchGraphRunner
from backend.harness.state import ResearchGraphState


def test_run_evaluation_writes_all_required_artifacts_and_fails_closed() -> None:
    state = ResearchGraphState(run_id="run-eval", ticker="DHG", objective="test")

    artifacts, packet = build_run_evaluation_artifacts(state)

    assert set(artifacts) == set(RUNTIME_EVALUATION_ARTIFACTS)
    assert packet["overall_status"] == "blocked"
    assert packet["publication_status"] == "NOT_EVALUATED"
    assert packet["client_final_authorized"] is False
    assert packet["summary"]["blocked"] > 0


def test_runtime_metrics_follow_benchmark_standards_schema() -> None:
    state = ResearchGraphState(run_id="run-schema-eval", ticker="DHG", objective="test")

    artifacts, packet = build_run_evaluation_artifacts(state)
    metric = artifacts["data_quality.json"]["metric_results"][0]

    assert packet["schema_version"] == "2.1"
    for required in (
        "metric_id",
        "metric_name",
        "category",
        "layer",
        "metric_type",
        "scope",
        "severity",
        "blocks_publish",
        "threshold_operator",
        "unit",
        "sample_size",
        "failed_examples",
        "remediation_hint",
        "evaluated_at",
    ):
        assert required in metric


def test_runtime_evaluation_preserves_failed_deterministic_gate() -> None:
    state = ResearchGraphState(
        run_id="run-failed-eval",
        ticker="DHG",
        objective="test",
        snapshot_id="snapshot-1",
    )
    state.data_inventory = {"snapshot_id": "snapshot-1"}
    state.gate_results["DATA_QUALITY_GATE"] = {
        "gate": "DATA_QUALITY_GATE",
        "passed": False,
        "blocking_reasons": ["reconciliation_failed"],
    }

    artifacts, packet = build_run_evaluation_artifacts(state)

    assert artifacts["data_quality.json"]["status"] == "fail"
    assert packet["overall_status"] == "blocked"
    assert packet["publication_status"] == "BLOCKED_BY_P0"


def test_runtime_evaluation_exposes_frontend_metric_shape() -> None:
    state = ResearchGraphState(
        run_id="run-shaped-eval",
        ticker="DHG",
        objective="test",
        snapshot_id="snapshot-1",
    )
    state.data_inventory = {"snapshot_id": "snapshot-1"}
    state.gate_results["DATA_QUALITY_GATE"] = pass_gate("DATA_QUALITY_GATE")

    _, packet = build_run_evaluation_artifacts(state)

    assert all("metric_results" in artifact for artifact in packet["artifacts"])
    assert all("blocking_issues" in artifact for artifact in packet["artifacts"])


def test_runner_persists_run_scoped_evaluation_artifacts(monkeypatch) -> None:
    uploads: list[str] = []

    class FakeAdapter:
        def upload_json(self, bucket, path, payload, *, upsert=False):
            assert upsert is True
            uploads.append(path)
            return {}

    class FakeStore:
        def __init__(self):
            self.saved: list[dict] = []

        def save_artifact(self, **kwargs):
            self.saved.append(kwargs)

    monkeypatch.setattr("backend.storage.SupabaseStorageAdapter", FakeAdapter)
    store = FakeStore()
    runner = ResearchGraphRunner(store=store)  # type: ignore[arg-type]
    state = ResearchGraphState(run_id="run-persist-eval", ticker="DHG", objective="test")

    runner._write_evaluation_artifacts(state)

    assert len(uploads) == len(RUNTIME_EVALUATION_ARTIFACTS) + 1
    assert len(store.saved) == len(uploads)
    assert any(ref["section_key"] == "evaluation_packet" for ref in state.artifact_refs)
