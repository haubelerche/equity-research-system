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
        "evaluator",
        "calculation",
        "threshold_policy",
        "evidence",
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


def test_observability_artifact_measures_cost_latency_retry_and_publication_blockers() -> None:
    state = ResearchGraphState(
        run_id="run-obs-eval",
        ticker="DHG",
        objective="test",
        status="blocked",
        artifacts={"trace_url": "https://trace.test/run-obs-eval", "render_mode": "client_final"},
    )
    state.trace = [
        {
            "kind": "agent_message",
            "agent_id": "research_manager",
            "input_summary": {"state_stage": "PLAN"},
            "latency_ms": 1000,
            "cost_estimate": 0.01,
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "attempts": 1,
        },
        {
            "kind": "agent_message",
            "agent_id": "financial_analysis",
            "input_summary": {"state_stage": "ANALYZE"},
            "latency_ms": 2000,
            "cost_estimate": 0.02,
            "prompt_tokens": 200,
            "completion_tokens": 40,
            "attempts": 2,
        },
        {
            "kind": "retrieval_query",
            "stage": "INGEST_AND_VALIDATE",
            "latency_ms": 250,
            "fallback_triggered": True,
        },
        {"kind": "artifact_upload", "status": "completed", "latency_ms": 50},
        {"kind": "pdf_render", "status": "completed", "latency_ms": 500},
    ]
    state.gate_results["PACKAGE_VALIDATION_GATE"] = {
        "passed": False,
        "blocking_reasons": ["artifact_missing:report"],
    }

    artifacts, _ = build_run_evaluation_artifacts(state)
    observability = artifacts["observability_eval.json"]
    metrics = {metric["id"]: metric for metric in observability["metric_results"]}

    assert observability["trace_url"] == "https://trace.test/run-obs-eval"
    assert observability["duration_seconds"] == 3.8
    assert observability["stage_durations"]["PLAN"] == 1.0
    assert observability["llm"]["calls"] == 2
    assert observability["llm"]["tokens_input"] == 300
    assert observability["llm"]["tokens_output"] == 60
    assert observability["llm"]["estimated_cost_usd"] == 0.03
    assert observability["llm"]["retry_rate"] == 0.5
    assert observability["retrieval"]["queries"] == 1
    assert observability["retrieval"]["fallback_rate"] == 1.0
    assert observability["publication"]["authorization_blockers"] == [
        "PACKAGE_VALIDATION_GATE:artifact_missing:report"
    ]
    assert metrics["llm_retry_rate"]["status"] == "fail"
    assert metrics["artifact_upload_failures"]["status"] == "pass"
    assert metrics["pdf_render_failures"]["status"] == "pass"


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
