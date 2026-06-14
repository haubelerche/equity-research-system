from __future__ import annotations

import json

from backend.evaluation.project_evaluator import (
    PlanDefinition,
    _artifact_payload,
    load_evaluation_artifact,
    load_latest_evaluation,
)
from backend.evaluation.runtime_evaluators import (
    _matrix_varies,
    _run_local_retrieval_benchmark,
)


def test_missing_runtime_evidence_blocks_plan() -> None:
    plan = PlanDefinition("01", "Data", "data_quality.json", (), ("data_quality.json",))
    payload = _artifact_payload(
        plan,
        run_id="run-1",
        ticker="DHG",
        generated_at="2026-06-14T00:00:00+00:00",
        test_execution={"status": "pass", "summary": {"passed": 10}},
        evidence={
            "status": "blocked",
            "required": ["data_quality.json"],
            "found": {"data_quality.json": []},
            "missing": ["data_quality.json"],
        },
    )
    assert payload["schema_version"] == "2.1"
    assert payload["status"] == "blocked"
    assert payload["metrics"]["runtime_evidence_coverage"] == 0


def test_loaders_only_read_allowlisted_artifacts(tmp_path) -> None:
    packet = {"overall_status": "pass", "artifacts": []}
    (tmp_path / "evaluation_packet.json").write_text(json.dumps(packet), encoding="utf-8")
    assert load_latest_evaluation(tmp_path) == packet
    assert load_evaluation_artifact("evaluation_packet.json", tmp_path) == packet
    assert load_evaluation_artifact("../.env", tmp_path) is None


def test_matrix_variation_requires_multiple_numeric_values() -> None:
    assert _matrix_varies({"a": {"x": 1, "y": 2}})
    assert not _matrix_varies({"a": {"x": 1, "y": 1}})


def test_local_retrieval_benchmark_calculates_hit_rate_and_mrr(tmp_path) -> None:
    golden = tmp_path / "config" / "eval" / "rag_golden_queries.yaml"
    golden.parent.mkdir(parents=True)
    golden.write_text(
        "version: test-v1\nqueries:\n"
        "  - id: revenue\n"
        "    query: net revenue\n"
        "    expected_pages: [2]\n",
        encoding="utf-8",
    )
    pages = (
        tmp_path / "storage" / "sources" / "ocr_artifacts" / "DHG" / "doc" / "pages"
    )
    pages.mkdir(parents=True)
    (pages / "page_001.txt").write_text("unrelated note", encoding="utf-8")
    (pages / "page_002.txt").write_text("net revenue net revenue", encoding="utf-8")

    result = _run_local_retrieval_benchmark(tmp_path, "DHG", golden)

    assert result["hit_rate_at_5"] == 1.0
    assert result["mrr_at_5"] == 1.0
