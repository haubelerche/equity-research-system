from __future__ import annotations

import json
import os
from pathlib import Path

from backend.evaluation.project_evaluator import (
    PlanDefinition,
    _artifact_payload,
    load_evaluation_artifact,
    load_latest_evaluation,
)
from backend.evaluation import runtime_evaluators
from backend.evaluation.runtime_evaluators import (
    evaluate_data_reliability,
    evaluate_agent,
    evaluate_financial,
    evaluate_observability,
    evaluate_report,
    evaluate_retrieval,
    _matrix_varies,
    _rag_golden_path_for_ticker,
    _run_local_retrieval_benchmark,
    _check_golden_drift,
)


def _benchmark_golden_query_dir(root):
    return root / "config" / "benchmarks" / "02_ragas_retrieval" / "golden_queries"


def _benchmark_ragas_dir(root):
    return root / "config" / "benchmarks" / "02_ragas_retrieval" / "ragas"


def _benchmark_golden_financials_dir(root):
    return root / "config" / "benchmarks" / "shared" / "golden_financials"


class _FakeChunk:
    """Minimal stand-in for an EvidenceChunk returned by RetrievalService."""

    def __init__(self, chunk_text, fiscal_year=None, reliability_tier=2,
                 extraction_method="cafef_structured"):
        self.chunk_text = chunk_text
        self.fiscal_year = fiscal_year
        self.reliability_tier = reliability_tier
        self.extraction_method = extraction_method


def _fake_retriever(chunks_by_keyword):
    """Build a deterministic retrieve(ticker, query, fiscal_year, top_k) callable.

    Returns the chunk list for the first keyword found in the query, else [].
    """
    def retrieve(ticker, query, fiscal_year=None, top_k=5):
        for keyword, chunks in chunks_by_keyword.items():
            if keyword.lower() in query.lower():
                return chunks[:top_k]
        return []
    return retrieve


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
    readiness = {"status": "fail", "blocking_issues": ["final_report_approval_missing"]}
    (tmp_path / "publication_readiness.json").write_text(
        json.dumps(readiness), encoding="utf-8"
    )
    assert load_latest_evaluation(tmp_path) == packet
    assert load_evaluation_artifact("evaluation_packet.json", tmp_path) == packet
    assert load_evaluation_artifact("publication_readiness.json", tmp_path) == readiness
    assert load_evaluation_artifact("../.env", tmp_path) is None


def test_loaders_prefer_benchmark_suite_snapshot_when_present(tmp_path) -> None:
    suite_dir = tmp_path / "benchmark_suite"
    suite_dir.mkdir()
    suite_packet = {
        "source": "benchmark_suite",
        "publication_status": "BLOCKED_BY_P0",
        "artifacts": [{"artifact": "financial_eval.json", "metric_results": []}],
    }
    financial = {"source": "benchmark_suite", "artifact": "financial_eval.json"}
    (tmp_path / "evaluation_packet.json").write_text(
        json.dumps({"source": "project_audit", "publication_status": "DRAFT_PUBLISHABLE"}),
        encoding="utf-8",
    )
    (suite_dir / "benchmark_suite.json").write_text(json.dumps(suite_packet), encoding="utf-8")
    (suite_dir / "financial_eval.json").write_text(json.dumps(financial), encoding="utf-8")

    assert load_latest_evaluation(tmp_path) == suite_packet
    assert load_evaluation_artifact("financial_eval.json", tmp_path) == financial


def test_latest_benchmark_suite_merges_sibling_plan_artifacts(tmp_path) -> None:
    suite_dir = tmp_path / "benchmark_suite"
    suite_dir.mkdir()
    suite_packet = {
        "source": "benchmark_suite",
        "generated_at": "2026-06-16T00:00:00+00:00",
        "publication_status": "DRAFT_PUBLISHABLE",
        "plan_ids": ["02"],
        "artifacts": [{
            "plan_id": "02",
            "name": "RAG and evidence",
            "artifact": "retrieval_eval.json",
            "status": "pass",
            "metric_results": [{
                "id": "hit_rate_at_5",
                "metric_id": "hit_rate_at_5",
                "value": 1.0,
                "status": "pass",
                "blocks_publish": False,
            }],
        }],
    }
    data_quality = {
        "source": "benchmark_suite",
        "generated_at": "2026-06-16T00:00:00+00:00",
        "plan_id": "01",
        "name": "Data reliability",
        "artifact": "data_quality.json",
        "status": "fail",
        "metrics": {"cohort_tickers": 1},
        "metric_results": [{
            "id": "core_metric_coverage",
            "metric_id": "core_metric_coverage",
            "value": 0.5,
            "status": "fail",
            "severity": "P0",
            "blocks_publish": True,
        }],
        "blocking_issues": ["core_metric_coverage:threshold_not_met"],
    }
    (suite_dir / "benchmark_suite.json").write_text(json.dumps(suite_packet), encoding="utf-8")
    (suite_dir / "data_quality.json").write_text(json.dumps(data_quality), encoding="utf-8")

    packet = load_latest_evaluation(tmp_path)
    artifacts = {item["artifact"]: item for item in packet["artifacts"]}

    assert set(artifacts) == {"retrieval_eval.json", "data_quality.json"}
    assert artifacts["data_quality.json"]["metric_results"][0]["value"] == 0.5
    assert packet["publication_status"] == "BLOCKED_BY_P0"
    assert packet["overall_status"] == "blocked"
    assert packet["plan_ids"] == ["02", "01"]
    assert packet["merged_artifact_sources"] == {
        "runtime_results": "output/evaluation/eval_result/benchmark_suite",
        "benchmark_config": "config/benchmarks",
    }


def test_latest_benchmark_suite_prefers_fresh_ticker_artifact_over_stale_root(tmp_path) -> None:
    suite_dir = tmp_path / "benchmark_suite"
    dhg_dir = suite_dir / "DHG"
    dhg_dir.mkdir(parents=True)
    suite_packet = {
        "source": "benchmark_suite",
        "generated_at": "2026-06-17T00:00:00+00:00",
        "tickers": ["DHG"],
        "plan_ids": ["03"],
        "artifacts": [{
            "plan_id": "03",
            "name": "Financial calculation",
            "artifact": "financial_eval.json",
            "status": "fail",
            "metric_results": [],
        }],
    }
    stale_report = {
        "plan_id": "06",
        "plan_name": "Report quality",
        "generated_at": "2026-06-16T00:00:00+00:00",
        "status": "fail",
        "score": 0,
        "metric_results": [{
            "id": "report_quality_score",
            "metric_id": "report_quality_score",
            "value": 0,
            "status": "fail",
            "blocks_publish": True,
            "severity": "P1",
        }],
    }
    fresh_report = {
        "plan_id": "06",
        "plan_name": "Report quality",
        "generated_at": "2026-06-17T00:00:00+00:00",
        "status": "fail",
        "score": 91,
        "metric_results": [{
            "id": "report.quality_total",
            "metric_id": "report.quality_total",
            "value": 91,
            "threshold": ">= 85/100",
            "status": "pass",
            "blocks_publish": False,
        }],
    }
    (suite_dir / "benchmark_suite.json").write_text(json.dumps(suite_packet), encoding="utf-8")
    root_report = suite_dir / "report_eval.json"
    ticker_report = dhg_dir / "report_eval.json"
    root_report.write_text(json.dumps(stale_report), encoding="utf-8")
    ticker_report.write_text(json.dumps(fresh_report), encoding="utf-8")
    os.utime(root_report, (1, 1))
    os.utime(ticker_report, (2, 2))

    packet = load_latest_evaluation(tmp_path)
    artifacts = {item["artifact"]: item for item in packet["artifacts"]}

    assert artifacts["report_eval.json"]["metric_results"][0]["value"] == 91
    assert load_evaluation_artifact("report_eval.json", tmp_path)["score"] == 91


def test_benchmark_suite_loader_prefers_root_aggregate_over_ticker_artifact(tmp_path) -> None:
    suite_dir = tmp_path / "benchmark_suite"
    dhg_dir = suite_dir / "DHG"
    dhg_dir.mkdir(parents=True)
    suite_packet = {
        "source": "benchmark_suite",
        "generated_at": "2026-06-17T00:00:00+00:00",
        "tickers": ["DHG"],
        "plan_ids": ["02"],
        "artifacts": [],
    }
    aggregate_retrieval = {
        "source": "benchmark_suite",
        "generated_at": "2026-06-17T00:00:00+00:00",
        "plan_id": "02",
        "status": "pass",
        "metric_results": [{
            "id": "context_precision",
            "metric_id": "context_precision",
            "value": 0.969,
            "threshold": ">= 0.8",
            "status": "pass",
            "blocks_publish": False,
        }],
    }
    ticker_retrieval = {
        "generated_at": "2026-06-17T00:00:00+00:00",
        "plan_id": "02",
        "status": "fail",
        "metric_results": [{
            "id": "context_precision",
            "metric_id": "context_precision",
            "value": None,
            "threshold": ">= 0.8",
            "status": "not_evaluable",
            "blocks_publish": False,
        }],
    }
    (suite_dir / "benchmark_suite.json").write_text(json.dumps(suite_packet), encoding="utf-8")
    root_retrieval = suite_dir / "retrieval_eval.json"
    ticker_path = dhg_dir / "retrieval_eval.json"
    root_retrieval.write_text(json.dumps(aggregate_retrieval), encoding="utf-8")
    ticker_path.write_text(json.dumps(ticker_retrieval), encoding="utf-8")
    os.utime(root_retrieval, (1, 1))
    os.utime(ticker_path, (2, 2))

    packet = load_latest_evaluation(tmp_path)
    artifacts = {item["artifact"]: item for item in packet["artifacts"]}

    assert artifacts["retrieval_eval.json"]["metric_results"][0]["value"] == 0.969
    assert load_evaluation_artifact("retrieval_eval.json", tmp_path)["metric_results"][0]["value"] == 0.969


def test_latest_benchmark_suite_merges_latest_suite_artifacts_by_plan(tmp_path) -> None:
    suite_dir = tmp_path / "benchmark_suite"
    suite_dir.mkdir()
    suite_packet = {
        "source": "benchmark_suite",
        "generated_at": "2026-06-17T14:58:56.067223+00:00",
        "cohort": "financial_model_top10",
        "plan_ids": ["03"],
        "artifacts": [{
            "plan_id": "03",
            "name": "Financial calculation",
            "artifact": "financial_eval.json",
            "status": "pass",
            "metric_results": [],
        }],
    }
    stale_retrieval = {
        "source": "benchmark_suite",
        "generated_at": "2026-06-16T04:00:11.000000+00:00",
        "cohort": "rag_representative_dhg",
        "plan_id": "02",
        "plan_name": "RAG and evidence",
        "status": "pass",
        "metric_results": [{
            "id": "hit_rate_at_5",
            "metric_id": "hit_rate_at_5",
            "value": 0.9655,
            "status": "pass",
            "blocks_publish": False,
        }],
    }
    (suite_dir / "benchmark_suite.json").write_text(json.dumps(suite_packet), encoding="utf-8")
    (suite_dir / "retrieval_eval.json").write_text(json.dumps(stale_retrieval), encoding="utf-8")

    packet = load_latest_evaluation(tmp_path)
    artifacts = {item["artifact"]: item for item in packet["artifacts"]}

    assert set(artifacts) == {"financial_eval.json", "retrieval_eval.json"}
    assert artifacts["retrieval_eval.json"]["metric_results"][0]["value"] == 0.9655
    assert load_evaluation_artifact("retrieval_eval.json", tmp_path)["metric_results"][0]["value"] == 0.9655


def test_latest_benchmark_suite_normalizes_stale_metric_status(tmp_path) -> None:
    suite_dir = tmp_path / "benchmark_suite"
    suite_dir.mkdir()
    suite_packet = {
        "source": "benchmark_suite",
        "publication_status": "BLOCKED_BY_P0",
        "plan_ids": ["01"],
        "artifacts": [{
            "plan_id": "01",
            "name": "Data reliability",
            "artifact": "data_quality.json",
            "status": "fail",
            "metric_results": [{
                "id": "core_metric_coverage",
                "metric_id": "core_metric_coverage",
                "metric_type": "coverage",
                "unit": "percent",
                "threshold": ">= 95%",
                "threshold_operator": ">=",
                "value": 0.98,
                "status": "fail",
                "severity": "P0",
                "blocks_publish": True,
            }],
        }],
    }
    (suite_dir / "benchmark_suite.json").write_text(json.dumps(suite_packet), encoding="utf-8")

    packet = load_latest_evaluation(tmp_path)
    metric = packet["artifacts"][0]["metric_results"][0]

    assert metric["value"] == 0.98
    assert metric["status"] == "pass"
    assert metric["legacy_status"] == "fail"
    assert metric["threshold_status_source"] == "benchmark_threshold_contract"
    assert packet["publication_status"] == "DRAFT_PUBLISHABLE"
    assert packet["overall_status"] == "pass"


def test_matrix_variation_requires_multiple_numeric_values() -> None:
    assert _matrix_varies({"a": {"x": 1, "y": 2}})
    assert not _matrix_varies({"a": {"x": 1, "y": 1}})


def test_matrix_variation_requires_meaningful_spread_not_just_any_difference() -> None:
    # Values differ but spread is < 1% of max absolute value → trivial, should not pass.
    assert not _matrix_varies({"a": {"x": 100.0, "y": 100.001}})
    # Spread is exactly 1% → still not enough (strictly greater than).
    assert not _matrix_varies({"a": {"x": 100.0, "y": 101.0}})
    # Spread is > 1% of max → meaningful variation.
    assert _matrix_varies({"a": {"x": 100.0, "y": 102.0}})
    # Negative values: spread relative to max abs.
    assert _matrix_varies({"a": {"x": -100.0, "y": -96.0}})
    # All zeros → no meaningful variation.
    assert not _matrix_varies({"a": {"x": 0.0, "y": 0.0}})


def test_report_evaluator_emits_dashboard_runtime_metrics(monkeypatch) -> None:
    report_text = (
        "Báo cáo khuyến nghị luận điểm đầu tư. Triển vọng kinh doanh và chỉ số tài chính "
        "gồm doanh thu, biên lợi nhuận gộp, biên EBIT, biên lợi nhuận ròng, ROE, OCF, EPS, "
        "CAPEX, vốn lưu động và cổ tức. Dự phóng forecast theo yếu tố dẫn dắt gồm "
        "revenue_growth, gross_margin, khấu hao, nợ vay và thuế suất. Định giá FCFF, FCFE, "
        "WACC, terminal, giá trị doanh nghiệp, nợ ròng, giá trị vốn chủ sở hữu, số cổ phiếu, "
        "giá mục tiêu và ma trận độ nhạy. Phụ lục nguồn [1][2], công thức formula trace, "
        "mã ảnh chụp dữ liệu, đối chiếu và cảnh báo."
    )

    def fake_pdf_stats(path):
        return {"path": str(path), "exists": True, "pages": 3, "text": report_text}

    monkeypatch.setattr(runtime_evaluators, "_pdf_stats", fake_pdf_stats)

    result = evaluate_report(
        runtime_evaluators.REPO_ROOT,
        "DHG",
        {"decision": "pass", "blocking_issues": []},
    )
    metrics = {metric["id"]: metric for metric in result["metrics"]}

    for metric_id in (
        "report.quality_total",
        "report.completeness",
        "report.financial_analysis_depth",
        "report.forecast_rationale",
        "report.valuation_transparency",
        "report.evidence_integration",
    ):
        assert metrics[metric_id]["value"] is not None
    assert metrics["report.completeness"]["status"] == "pass"
    assert metrics["report.valuation_transparency"]["status"] == "pass"


def test_local_retrieval_benchmark_scores_against_live_retriever(tmp_path, monkeypatch) -> None:
    # Pure-live: golden queries are scored against the production retriever (term match
    # on retrieved chunks), injected here deterministically via the test seam.
    golden = _benchmark_golden_query_dir(tmp_path) / "default.yaml"
    golden.parent.mkdir(parents=True)
    golden.write_text(
        "version: test-v1\nticker: DHG\nqueries:\n"
        "  - id: revenue\n"
        "    query: DHG net revenue 2023\n"
        "    fiscal_year: 2023\n"
        "    expected_terms: ['net revenue']\n"
        "    expected_source_tiers: [0, 1, 2]\n"
        "    material: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runtime_evaluators, "RETRIEVE_CALLABLE_OVERRIDE",
        _fake_retriever({"net revenue": [
            _FakeChunk("Báo cáo KQKD: net revenue 2023 ...", fiscal_year=2023, reliability_tier=1),
        ]}),
    )

    result = _run_local_retrieval_benchmark(tmp_path, "DHG", golden)

    assert result["execution_status"] == "executed"
    assert result["retrieval_backend"] in ("pgvector", "full_text")
    assert result["hit_rate_at_5"] == 1.0
    assert result["mrr_at_5"] == 1.0
    assert result["source_tier_hit_rate"] == 1.0


def test_local_retrieval_benchmark_blocks_when_retriever_unavailable(tmp_path, monkeypatch) -> None:
    golden = _benchmark_golden_query_dir(tmp_path) / "default.yaml"
    golden.parent.mkdir(parents=True)
    golden.write_text(
        "version: test-v1\nticker: DHG\nqueries:\n"
        "  - id: revenue\n    query: net revenue\n    expected_terms: ['net revenue']\n",
        encoding="utf-8",
    )
    # No retriever (no DB) -> blocked, NOT a fabricated zero.
    monkeypatch.setattr(runtime_evaluators, "_resolve_retrieve_callable", lambda: None)

    result = _run_local_retrieval_benchmark(tmp_path, "DHG", golden)

    assert result["execution_status"] == "retriever_unavailable"
    assert result["hit_rate_at_5"] is None


def test_local_retrieval_benchmark_rejects_cross_ticker_golden_set(tmp_path) -> None:
    golden = _benchmark_golden_query_dir(tmp_path) / "default.yaml"
    golden.parent.mkdir(parents=True)
    golden.write_text(
        "version: test-v1\nticker: DHG\nqueries:\n"
        "  - id: revenue\n"
        "    query: net revenue\n"
        "    expected_terms: ['net revenue']\n",
        encoding="utf-8",
    )

    result = _run_local_retrieval_benchmark(tmp_path, "DBD", golden)

    assert result["execution_status"] == "not_executed"
    assert result["hit_rate_at_5"] is None
    assert result["reason"] == "golden_query_ticker_mismatch:DHG:DBD"


def test_rag_golden_path_does_not_reuse_default_for_other_tickers(tmp_path) -> None:
    golden = _benchmark_golden_query_dir(tmp_path) / "default.yaml"
    golden.parent.mkdir(parents=True)
    golden.write_text("version: test-v1\nticker: DHG\nqueries: []\n", encoding="utf-8")

    assert _rag_golden_path_for_ticker(tmp_path, "DHG") == golden
    assert _rag_golden_path_for_ticker(tmp_path, "DBD") == (
        _benchmark_golden_query_dir(tmp_path) / "DBD.yaml"
    )


def test_local_retrieval_benchmark_excludes_non_material_queries_from_score(tmp_path, monkeypatch) -> None:
    golden = _benchmark_golden_query_dir(tmp_path) / "default.yaml"
    golden.parent.mkdir(parents=True)
    golden.write_text(
        "version: test-v1\nticker: DHG\nqueries:\n"
        "  - id: revenue\n"
        "    query: DHG net revenue 2023\n"
        "    fiscal_year: 2023\n"
        "    expected_terms: ['net revenue']\n"
        "    expected_source_tiers: [0, 1, 2]\n"
        "    material: true\n"
        "  - id: missing_guidance\n"
        "    query: DHG unavailable guidance 2026\n"
        "    fiscal_year: 2026\n"
        "    expected_terms: ['unavailable guidance']\n"
        "    expected_source_tiers: [0, 1, 2]\n"
        "    material: false\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runtime_evaluators,
        "RETRIEVE_CALLABLE_OVERRIDE",
        _fake_retriever({"net revenue": [
            _FakeChunk("Báo cáo KQKD: net revenue 2023 ...", fiscal_year=2023, reliability_tier=1),
        ]}),
    )

    result = _run_local_retrieval_benchmark(tmp_path, "DHG", golden)

    assert len(result["queries"]) == 2
    assert result["hit_rate_at_5"] == 1.0
    assert result["mrr_at_5"] == 1.0
    assert result["source_tier_hit_rate"] == 1.0


def _write_dbd_eval_inputs(tmp_path):
    golden_dir = _benchmark_golden_query_dir(tmp_path)
    golden_dir.mkdir(parents=True)
    (golden_dir / "DBD.yaml").write_text(
        "version: dbd-test-v2\n"
        "ticker: DBD\n"
        "queries:\n"
        "  - id: revenue\n"
        "    query: DBD doanh thu 2025\n"
        "    fiscal_year: 2025\n"
        "    expected_terms: ['Doanh thu']\n"
        "    expected_source_tiers: [0, 1, 2]\n"
        "    material: true\n",
        encoding="utf-8",
    )
    ragas_dir = _benchmark_ragas_dir(tmp_path)
    ragas_dir.mkdir(parents=True)
    (ragas_dir / "ragas_samples.json").write_text(
        json.dumps([
            {
                "id": "semantic-1",
                "ticker": "DBD",
                "question": "Revenue?",
                "expected_answer": "Revenue is supported.",
                "contexts": ["Audited revenue context"],
                "offline_scores": {
                    "context_precision": 0.5,
                    "context_recall": 0.5,
                    "faithfulness": 0.5,
                    "response_relevancy": 0.5,
                },
            }
        ]),
        encoding="utf-8",
    )


def test_retrieval_evaluator_scores_live_hits(tmp_path, monkeypatch) -> None:
    _write_dbd_eval_inputs(tmp_path)
    monkeypatch.setattr(
        runtime_evaluators, "RETRIEVE_CALLABLE_OVERRIDE",
        _fake_retriever({"doanh thu": [
            _FakeChunk("Doanh thu bán hàng DBD năm 2025 ...", fiscal_year=2025, reliability_tier=2),
        ]}),
    )

    result = evaluate_retrieval(tmp_path, "DBD")
    metrics = {metric["id"]: metric for metric in result["metrics"]}

    assert metrics["hit_rate_at_5"]["value"] == 1.0
    assert metrics["source_tier_hit_rate"]["value"] == 1.0
    assert result["retrieval_backend"] in ("pgvector", "full_text")
    for metric in metrics.values():
        samples = metric["calculation"]["per_sample_results"]
        assert metric["sample_size"] >= 20
        assert len(samples) >= 20


def test_retrieval_evaluator_fails_closed_when_no_evidence(tmp_path, monkeypatch) -> None:
    _write_dbd_eval_inputs(tmp_path)
    # Retriever returns nothing for every query -> honest fail (no evidence found).
    monkeypatch.setattr(
        runtime_evaluators, "RETRIEVE_CALLABLE_OVERRIDE", _fake_retriever({}),
    )

    result = evaluate_retrieval(tmp_path, "DBD")
    metrics = {metric["id"]: metric for metric in result["metrics"]}

    assert result["status"] == "fail"
    assert metrics["hit_rate_at_5"]["value"] == 0.0
    assert metrics["hit_rate_at_5"]["status"] == "fail"
    assert metrics["source_tier_hit_rate"]["value"] == 0.0


def test_retrieval_evaluator_rejects_live_ragas_samples_without_reference(tmp_path, monkeypatch) -> None:
    golden_dir = _benchmark_golden_query_dir(tmp_path)
    golden_dir.mkdir(parents=True)
    (golden_dir / "DBD.yaml").write_text(
        "version: dbd-test-v2\n"
        "ticker: DBD\n"
        "queries:\n"
        "  - id: revenue\n"
        "    query: DBD doanh thu 2025\n"
        "    fiscal_year: 2025\n"
        "    expected_terms: ['Doanh thu']\n"
        "    expected_source_tiers: [1]\n"
        "    material: true\n",
        encoding="utf-8",
    )
    ragas_dir = _benchmark_ragas_dir(tmp_path)
    ragas_dir.mkdir(parents=True)
    (ragas_dir / "ragas_samples.json").write_text(
        json.dumps([{
            "id": "semantic-missing-reference",
            "question": "DBD doanh thu 2025?",
            "metadata": {"ticker": "DBD", "fiscal_year": 2025},
        }]),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runtime_evaluators,
        "RETRIEVE_CALLABLE_OVERRIDE",
        _fake_retriever({
            "doanh thu": [
                _FakeChunk("Doanh thu DBD nam 2025", fiscal_year=2025, reliability_tier=1),
            ],
        }),
    )

    result = evaluate_retrieval(tmp_path, "DBD")
    metrics = {metric["id"]: metric for metric in result["metrics"]}

    assert result["ragas_execution"]["execution_status"] == "not_evaluable"
    assert result["ragas_execution"]["reason"] == "ragas_sample_contract_invalid"
    assert result["ragas_execution"]["samples"][0]["contract_errors"] == ["missing_reference"]
    assert metrics["context_precision"]["status"] == "not_evaluable"
    assert metrics["hit_rate_at_5"]["status"] == "pass"


def test_retrieval_evaluator_prefers_scoped_evidence_packet_over_legacy_fixture(tmp_path, monkeypatch) -> None:
    _write_dbd_eval_inputs(tmp_path)
    archive = tmp_path / "storage" / "archive" / "legacy"
    archive.mkdir(parents=True)
    archive.joinpath("run1_evidence_packet.json").write_text(
        json.dumps({
            "ticker": "DBD",
            "source_documents": [],
            "citation_map": {},
            "formula_traces": [],
        }),
        encoding="utf-8",
    )
    run_dir = tmp_path / "storage" / "runs" / "dbd_live_eval"
    run_dir.mkdir(parents=True)
    run_dir.joinpath("dbd_live_eval_evidence_packet.json").write_text(
        json.dumps({
            "ticker": "DBD",
            "source_documents": [{"id": "doc-1"}],
            "citation_map": {"claim-1": ["fact-1"]},
            "formula_traces": [{"formula_id": "fcff"}],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runtime_evaluators, "RETRIEVE_CALLABLE_OVERRIDE",
        _fake_retriever({"doanh thu": [
            _FakeChunk("Doanh thu ban hang DBD nam 2025 ...", fiscal_year=2025, reliability_tier=2),
        ]}),
    )

    result = evaluate_retrieval(tmp_path, "DBD")

    assert result["evidence_packet_completeness"] == 1.0
    assert result["evidence_packet"]["path"] == str(
        Path("storage/runs/dbd_live_eval/dbd_live_eval_evidence_packet.json")
    ).replace("/", "\\")


def test_data_reliability_does_not_treat_pandera_schema_as_system_readiness(tmp_path) -> None:
    material_config = tmp_path / "config" / "material_metrics.yml"
    material_config.parent.mkdir(parents=True)
    material_config.write_text(
        "income_statement:\n"
        "  - revenue.net\n"
        "balance_sheet:\n"
        "  - equity.parent\n"
        "non_material:\n"
        "  - sga.total\n",
        encoding="utf-8",
    )
    golden_dir = _benchmark_golden_financials_dir(tmp_path)
    golden_dir.mkdir(parents=True)
    (golden_dir / "AAA.csv").write_text(
        "ticker,fiscal_year,period,statement_type,canonical_key,raw_label,value,unit,currency,source_type,source_uri,source_title,provider,confidence,validation_status\n"
        "AAA,2025,2025FY,income_statement,revenue.net,Revenue,100,vnd_bn,VND,financial_statement,https://issuer.test/fs.pdf,Audited FS,golden_csv,0.99,accepted\n"
        "AAA,2025,2025FY,balance_sheet,equity.parent,Equity,80,vnd_bn,VND,financial_statement,https://issuer.test/fs.pdf,Audited FS,golden_csv,0.99,accepted\n",
        encoding="utf-8",
    )
    (golden_dir / "AAA_golden_provenance.json").write_text(
        json.dumps({
            "ticker": "AAA",
            "fiscal_year": 2025,
            "fiscal_period": "FY",
            "metrics_verified": ["revenue.net", "equity.parent"],
        }),
        encoding="utf-8",
    )
    ocr_dir = tmp_path / "storage" / "sources" / "ocr_artifacts" / "AAA" / "2025" / "doc"
    ocr_dir.mkdir(parents=True)
    (ocr_dir / "metadata.json").write_text(
        json.dumps({
            "ocr_run_id": "ocr-1",
            "document_id": "doc",
            "status": "completed",
            "pages_processed": 10,
            "pages_failed": 0,
            "candidate_row_count": 0,
            "mapped_fact_count": 0,
        }),
        encoding="utf-8",
    )
    valuation_dir = tmp_path / "storage" / "runs" / "validation_aaa"
    valuation_dir.mkdir(parents=True)
    (valuation_dir / "valuation.json").write_text(
        json.dumps({
            "ticker": "AAA",
            "current_price_vnd": 100,
            "fcff": {"target_price_vnd": 120, "wacc": 0.12},
            "fcfe": {"target_price_vnd": None, "fcfe_table": []},
            "blend_dcf": {
                "target_price_dcf_vnd": 120,
                "price_fcff_vnd": 120,
                "price_fcfe_vnd": None,
                "is_draft_only": True,
            },
            "valuation_confidence": {"fcff_dcf": "low", "fcfe_dcf": "blocked"},
            "sensitivity": {"fcff_wacc_g": {"10%": {"3%": 120, "4%": 130}}},
            "formula_traces": [{"method": "fcff"}],
        }),
        encoding="utf-8",
    )

    result = evaluate_data_reliability(tmp_path, "AAA")
    metrics = {metric["id"]: metric for metric in result["metrics"]}

    assert result["status"] == "fail"
    assert result["official_reconciliation_rate"] == 1.0
    assert result["material_ocr_error_count"] == 0
    assert "material_ocr_error_count" in metrics
    assert "duplicate_fact_count" in metrics
    assert 0 < metrics["data_reliability_score"]["value"] < 1.0
    assert metrics["core_metric_coverage"]["value"] < 1.0
    assert metrics["core_metric_coverage"]["failed_examples"]
    assert metrics["core_metric_coverage"]["evaluator"]["framework"] == "valuation_data_requirements+pandera"
    assert metrics["dataframe_schema_validity"]["evaluator"]["framework"] == "pandera"
    assert metrics["core_metric_coverage"]["calculation"]["inputs"]["record_count"] == 2
    assert metrics["core_metric_coverage"]["calculation"]["parameters"]
    assert metrics["core_metric_coverage"]["calculation"]["per_sample_results"]
    assert metrics["official_reconciliation_rate"]["calculation"]["per_sample_results"][0]["reconciled"] is True
    assert metrics["valuation_method_data_readiness"]["status"] == "fail"
    assert metrics["valuation_method_data_readiness"]["failed_examples"]
    for metric in metrics.values():
        samples = metric["calculation"]["per_sample_results"]
        assert metric["sample_size"] >= 20
        assert len(samples) >= 20


def test_data_reliability_flags_unverified_material_reconciliation(tmp_path) -> None:
    material_config = tmp_path / "config" / "material_metrics.yml"
    material_config.parent.mkdir(parents=True)
    material_config.write_text("income_statement:\n  - revenue.net\n", encoding="utf-8")
    golden_dir = _benchmark_golden_financials_dir(tmp_path)
    golden_dir.mkdir(parents=True)
    (golden_dir / "AAA.csv").write_text(
        "ticker,fiscal_year,period,statement_type,canonical_key,raw_label,value,unit,currency,source_type,source_uri,source_title,provider,confidence,validation_status\n"
        "AAA,2025,2025FY,income_statement,revenue.net,Revenue,100,vnd_bn,VND,financial_statement,https://issuer.test/fs.pdf,Audited FS,golden_csv,0.99,accepted\n",
        encoding="utf-8",
    )
    (golden_dir / "AAA_golden_provenance.json").write_text(
        json.dumps({
            "ticker": "AAA",
            "fiscal_year": 2025,
            "fiscal_period": "FY",
            "metrics_verified": [],
        }),
        encoding="utf-8",
    )
    ocr_dir = tmp_path / "storage" / "sources" / "ocr_artifacts" / "AAA" / "2025" / "doc"
    ocr_dir.mkdir(parents=True)
    (ocr_dir / "metadata.json").write_text(
        json.dumps({
            "ocr_run_id": "ocr-1",
            "document_id": "doc",
            "status": "completed",
            "pages_processed": 10,
            "pages_failed": 0,
            "candidate_row_count": 0,
            "mapped_fact_count": 0,
        }),
        encoding="utf-8",
    )

    result = evaluate_data_reliability(tmp_path, "AAA")
    metric = {item["id"]: item for item in result["metrics"]}["official_reconciliation_rate"]

    assert result["status"] == "fail"
    assert metric["status"] == "fail"
    assert metric["failed_examples"][0]["canonical_key"] == "revenue.net"


def test_data_reliability_explains_empty_raw_bctc_when_golden_missing(tmp_path) -> None:
    raw_dir = tmp_path / "data" / "raw" / "bctc" / "ZZZ"
    raw_dir.mkdir(parents=True)
    for name in (
        "income_statement_year.json",
        "balance_sheet_year.json",
        "cash_flow_year.json",
        "ratio_year.json",
    ):
        raw_dir.joinpath(name).write_text(
            json.dumps({"columns": [], "index": [], "data": []}),
            encoding="utf-8",
        )

    result = evaluate_data_reliability(tmp_path, "ZZZ")
    metrics = {metric["id"]: metric for metric in result["metrics"]}
    metric = metrics["raw_bctc_non_empty"]

    assert result["status"] == "fail"
    assert result["core_metric_coverage"] == 0.0
    assert result["raw_bctc_non_empty"] is False
    assert metric["status"] == "warning"
    assert metric["blocks_publish"] is False
    assert metric["calculation"]["numerator"] == 0
    assert metric["calculation"]["denominator"] == 4
    assert metric["failed_examples"][0]["status"] == "empty"


def test_data_reliability_marks_ocr_not_applicable_without_ocr_sourced_facts(tmp_path) -> None:
    material_config = tmp_path / "config" / "material_metrics.yml"
    material_config.parent.mkdir(parents=True)
    material_config.write_text("income_statement:\n  - revenue.net\n", encoding="utf-8")
    golden_dir = _benchmark_golden_financials_dir(tmp_path)
    golden_dir.mkdir(parents=True)
    (golden_dir / "AAA.csv").write_text(
        "ticker,fiscal_year,period,statement_type,canonical_key,raw_label,value,unit,currency,source_type,source_uri,source_title,provider,confidence,validation_status\n"
        "AAA,2025,2025FY,income_statement,revenue.net,Revenue,100,vnd_bn,VND,financial_statement,https://issuer.test/fs.pdf,Audited FS,golden_csv,0.99,accepted\n",
        encoding="utf-8",
    )
    (golden_dir / "AAA_golden_provenance.json").write_text(
        json.dumps({
            "ticker": "AAA",
            "fiscal_year": 2025,
            "fiscal_period": "FY",
            "metrics_verified": ["revenue.net"],
        }),
        encoding="utf-8",
    )

    result = evaluate_data_reliability(tmp_path, "AAA")
    metric = {item["id"]: item for item in result["metrics"]}["ocr_unresolved_rate"]

    assert metric["status"] == "not_evaluable"
    assert metric["value"] is None
    assert metric["blocks_publish"] is False
    assert metric["calculation"]["numerator"] == 0
    assert metric["calculation"]["denominator"] == 0
    assert metric["sample_size"] == 20
    assert len(metric["calculation"]["per_sample_results"]) == 20
    assert all(
        sample["reason"] == "no_ocr_sourced_material_facts"
        for sample in metric["calculation"]["per_sample_results"]
    )


def test_data_reliability_fails_closed_when_promoted_ocr_fact_lacks_metadata(tmp_path) -> None:
    material_config = tmp_path / "config" / "material_metrics.yml"
    material_config.parent.mkdir(parents=True)
    material_config.write_text("income_statement:\n  - revenue.net\n", encoding="utf-8")
    golden_dir = _benchmark_golden_financials_dir(tmp_path)
    golden_dir.mkdir(parents=True)
    (golden_dir / "AAA.csv").write_text(
        "ticker,fiscal_year,period,statement_type,canonical_key,raw_label,value,unit,currency,source_type,source_uri,source_title,provider,confidence,validation_status\n"
        "AAA,2025,2025FY,income_statement,revenue.net,Revenue,100,vnd_bn,VND,ocr_pdf,https://issuer.test/fs.pdf,Audited FS OCR,golden_csv,0.82,accepted\n",
        encoding="utf-8",
    )
    (golden_dir / "AAA_golden_provenance.json").write_text(
        json.dumps({
            "ticker": "AAA",
            "fiscal_year": 2025,
            "fiscal_period": "FY",
            "metrics_verified": ["revenue.net"],
        }),
        encoding="utf-8",
    )

    result = evaluate_data_reliability(tmp_path, "AAA")
    metric = {item["id"]: item for item in result["metrics"]}["ocr_unresolved_rate"]

    assert metric["status"] == "fail"
    assert metric["value"] == 1.0
    assert metric["calculation"]["numerator"] == 1
    assert metric["calculation"]["denominator"] == 1
    assert metric["failed_examples"][0]["reason"] == "ocr_metadata_missing_for_promoted_material_fact"


def test_data_reliability_uses_ocr_reconciliation_for_unresolved_rate(tmp_path) -> None:
    material_config = tmp_path / "config" / "material_metrics.yml"
    material_config.parent.mkdir(parents=True)
    material_config.write_text("income_statement:\n  - revenue.net\n", encoding="utf-8")
    golden_dir = _benchmark_golden_financials_dir(tmp_path)
    golden_dir.mkdir(parents=True)
    (golden_dir / "AAA.csv").write_text(
        "ticker,fiscal_year,period,statement_type,canonical_key,raw_label,value,unit,currency,source_type,source_uri,source_title,provider,confidence,validation_status\n"
        "AAA,2025,2025FY,income_statement,revenue.net,Revenue,100,vnd_bn,VND,financial_statement,https://issuer.test/fs.pdf,Audited FS,golden_csv,0.99,accepted\n",
        encoding="utf-8",
    )
    (golden_dir / "AAA_golden_provenance.json").write_text(
        json.dumps({
            "ticker": "AAA",
            "fiscal_year": 2025,
            "fiscal_period": "FY",
            "metrics_verified": ["revenue.net"],
        }),
        encoding="utf-8",
    )
    metadata_dir = tmp_path / "storage" / "sources" / "ocr_artifacts" / "AAA" / "2025" / "run_1"
    metadata_dir.mkdir(parents=True)
    (metadata_dir / "metadata.json").write_text(
        json.dumps({
            "ticker": "AAA",
            "status": "completed",
            "pages_processed": 3,
            "pages_failed": 0,
            "candidate_row_count": 3,
            "mapped_fact_count": 1,
        }),
        encoding="utf-8",
    )
    recon_dir = tmp_path / "data" / "reconciliation" / "AAA" / "2025"
    recon_dir.mkdir(parents=True)
    (recon_dir / "ocr_vs_structured.json").write_text(
        json.dumps({
            "ticker": "AAA",
            "fiscal_year": 2025,
            "total_records": 2,
            "summary": {
                "total": 2,
                "matched": 1,
                "conflicted": 1,
                "needs_review_count": 0,
            },
            "records": [],
        }),
        encoding="utf-8",
    )

    result = evaluate_data_reliability(tmp_path, "AAA")
    metric = {item["id"]: item for item in result["metrics"]}["ocr_unresolved_rate"]

    assert metric["status"] == "pass"
    assert metric["value"] == 0.0
    assert metric["calculation"]["numerator"] == 0
    assert metric["calculation"]["denominator"] == 2
    assert metric["calculation"]["inputs"]["resolution_counts"]["resolved"] == 2


def test_financial_evaluator_enforces_fcfe_formula_and_publishability(tmp_path) -> None:
    valuation_dir = tmp_path / "storage" / "runs" / "run_aaa"
    valuation_dir.mkdir(parents=True)
    (valuation_dir / "valuation.json").write_text(
        json.dumps({
            "ticker": "AAA",
            "current_price_vnd": 100,
            "valuation_confidence": {"fcff_dcf": "high", "fcfe_dcf": "high"},
            "fcff": {
                "wacc": 0.11,
                "terminal_growth": 0.03,
                "wacc_breakdown": {"wacc": 0.11},
                "fcff_table": [{
                    "ebit_after_tax": 10,
                    "depreciation": 2,
                    "capex": 3,
                    "delta_nwc": 1,
                    "fcff": 8,
                }],
                "enterprise_value": 100,
                "equity_value": 110,
                "shares_mn": 1,
                "target_price_vnd": 110000,
                "net_debt_bridge": {
                    "total_debt": 5,
                    "cash": 10,
                    "short_term_investments": 5,
                    "net_debt": -10,
                },
                "ev_to_equity_bridge": {"equity_value": 110},
            },
            "fcfe": {
                "cost_of_equity_breakdown": {"cost_of_equity": 0.12},
                "fcfe_table": [{
                    "net_income": 10,
                    "depreciation": 2,
                    "capex": 3,
                    "delta_nwc": 1,
                    "net_borrowing": 4,
                    "fcfe": 99,
                }],
                "equity_value": 120,
                "target_price_vnd": 120000,
            },
            "blend_dcf": {
                "target_price_dcf_vnd": 114000,
                "price_fcff_vnd": 110000,
                "price_fcfe_vnd": 120000,
                "is_draft_only": False,
            },
            "sensitivity": {
                "fcff_wacc_g": {"base_wacc": 0.11, "base_terminal_growth": 0.03, "0.11": {"0.03": 110000, "0.04": 120000}},
                "fcfe_re_g": {"base_re": 0.12, "base_terminal_growth": 0.03, "0.12": {"0.03": 120000, "0.04": 130000}},
                "blend_grid": {"base_weight": "60/40", "60/40": {"base": 114000, "alt": 115000}},
            },
            "formula_traces": [{"method": "fcff"}, {"method": "fcfe"}],
        }),
        encoding="utf-8",
    )

    result = evaluate_financial(tmp_path, "AAA")
    metrics = {metric["id"]: metric for metric in result["metrics"]}

    assert metrics["fcff"]["status"] == "pass"
    assert metrics["fcfe"]["status"] == "fail"
    assert metrics["accounting_invariant_violations"]["value"] == 0
    assert result["decision"] == "block"


def test_financial_evaluator_passes_complete_formula_fixture(tmp_path) -> None:
    valuation_dir = tmp_path / "storage" / "runs" / "run_aaa"
    valuation_dir.mkdir(parents=True)
    (valuation_dir / "valuation.json").write_text(
        json.dumps({
            "ticker": "AAA",
            "current_price_vnd": 100000,
            "valuation_confidence": {"fcff_dcf": "high", "fcfe_dcf": "high"},
            "fcff": {
                "wacc": 0.11,
                "terminal_growth": 0.03,
                "wacc_breakdown": {"wacc": 0.11},
                "fcff_table": [{
                    "ebit_after_tax": 10,
                    "depreciation": 2,
                    "capex": 3,
                    "delta_nwc": 1,
                    "fcff": 8,
                }],
                "enterprise_value": 100,
                "equity_value": 110,
                "shares_mn": 1,
                "target_price_vnd": 110000,
                "net_debt_bridge": {
                    "total_debt": 5,
                    "cash": 10,
                    "short_term_investments": 5,
                    "net_debt": -10,
                },
                "ev_to_equity_bridge": {"equity_value": 110},
            },
            "fcfe": {
                "cost_of_equity_breakdown": {"cost_of_equity": 0.12},
                "fcfe_table": [{
                    "net_income": 10,
                    "depreciation": 2,
                    "capex": 3,
                    "delta_nwc": 1,
                    "net_borrowing": 4,
                    "fcfe": 12,
                }],
                "equity_value": 120,
                "target_price_vnd": 120000,
            },
            "blend_dcf": {
                "target_price_dcf_vnd": 114000,
                "price_fcff_vnd": 110000,
                "price_fcfe_vnd": 120000,
                "is_draft_only": False,
            },
            "sensitivity": {
                "fcff_wacc_g": {"base_wacc": 0.11, "base_terminal_growth": 0.03, "0.11": {"0.03": 110000, "0.04": 120000}},
                "fcfe_re_g": {"base_re": 0.12, "base_terminal_growth": 0.03, "0.12": {"0.03": 120000, "0.04": 130000}},
                "blend_grid": {"base_weight": "60/40", "60/40": {"base": 114000, "alt": 115000}},
            },
            "formula_traces": [{"method": "fcff"}, {"method": "fcfe"}],
        }),
        encoding="utf-8",
    )

    result = evaluate_financial(tmp_path, "AAA")
    metrics = {metric["id"]: metric for metric in result["metrics"]}

    assert metrics["fcfe"]["status"] == "pass"
    # Base-cell reconciliation is folded into the target-price gate; publishability
    # is no longer a financial-accuracy metric (moved to the governance gate).
    assert metrics["target_price"]["status"] == "pass"
    assert "sensitivity_base_cell" not in metrics
    assert "blend_sensitivity" not in metrics
    assert "valuation_publishable" not in metrics
    assert result["decision"] == "pass"


def test_financial_evaluator_accepts_current_sensitivity_matrix_shape(tmp_path) -> None:
    valuation_dir = tmp_path / "storage" / "runs" / "run_aaa"
    valuation_dir.mkdir(parents=True)
    (valuation_dir / "valuation.json").write_text(
        json.dumps({
            "ticker": "AAA",
            "current_price_vnd": 100000,
            "valuation_confidence": {"fcff_dcf": "high", "fcfe_dcf": "high"},
            "fcff": {
                "wacc": 0.11,
                "terminal_growth": 0.03,
                "wacc_breakdown": {"wacc": 0.11},
                "fcff_table": [{
                    "ebit_after_tax": 10,
                    "depreciation": 2,
                    "capex": 3,
                    "delta_nwc": 1,
                    "fcff": 8,
                }],
                "enterprise_value": 100,
                "equity_value": 110,
                "shares_mn": 1,
                "target_price_vnd": 110000,
                "net_debt_bridge": {
                    "total_debt": 5,
                    "cash": 10,
                    "short_term_investments": 5,
                    "net_debt": -10,
                },
                "ev_to_equity_bridge": {"equity_value": 110},
            },
            "fcfe": {
                "cost_of_equity_breakdown": {"cost_of_equity": 0.12},
                "fcfe_table": [{
                    "net_income": 10,
                    "depreciation": 2,
                    "capex": 3,
                    "delta_nwc": 1,
                    "net_borrowing": 4,
                    "fcfe": 12,
                }],
                "equity_value": 120,
                "target_price_vnd": 120000,
            },
            "blend_dcf": {
                "target_price_dcf_vnd": 114000,
                "price_fcff_vnd": 110000,
                "price_fcfe_vnd": 120000,
                "is_draft_only": False,
            },
            "sensitivity": {
                "fcff_wacc_g": {
                    "matrix": {"0.11": {"0.03": 110000, "0.04": 120000}},
                    "base_wacc": 0.1104,
                    "base_terminal_growth": 0.03,
                },
                "fcfe_re_g": {
                    "matrix": {"0.12": {"0.03": 120000, "0.04": 130000}},
                    "base_re": 0.12,
                    "base_terminal_growth": 0.03,
                },
                "blend_grid": {
                    "price_fcff_range": [105000, 110000, 115000],
                    "price_fcfe_range": [115000, 120000, 125000],
                    "matrix": {
                        "105000": {"115000": 109000, "120000": 111000, "125000": 113000},
                        "110000": {"115000": 112000, "120000": 114000, "125000": 116000},
                        "115000": {"115000": 115000, "120000": 117000, "125000": 119000},
                    },
                },
            },
            "formula_traces": [{"method": "fcff"}, {"method": "fcfe"}],
        }),
        encoding="utf-8",
    )

    result = evaluate_financial(tmp_path, "AAA")
    metrics = {metric["id"]: metric for metric in result["metrics"]}

    assert metrics["target_price"]["status"] == "pass"
    assert "sensitivity_base_cell" not in metrics
    assert result["decision"] == "pass"


def test_agent_evaluator_validates_schema_manifest_and_unauthorized_calc(tmp_path) -> None:
    schema_dir = tmp_path / "config" / "harness"
    schema_dir.mkdir(parents=True)
    schema_dir.joinpath("evidence_packet_schema.json").write_text(
        json.dumps({
            "required": ["schema_version", "run_id", "ticker", "gate_results", "packet_hash"],
            "properties": {
                "schema_version": {"type": "integer", "const": 1},
                "run_id": {"type": "string"},
                "ticker": {"type": "string"},
                "gate_results": {"type": "object"},
                "packet_hash": {"type": "string"},
            },
            "additionalProperties": True,
        }),
        encoding="utf-8",
    )
    archive = tmp_path / "storage" / "archive" / "run_aaa"
    archive.mkdir(parents=True)
    archive.joinpath("run1_evidence_packet.json").write_text(
        json.dumps({
            "schema_version": 1,
            "run_id": "run_aaa",
            "ticker": "AAA",
            "gate_results": {},
            # Every governed tool call carries permission metadata -> 100%.
            "tool_execution_summary": [
                {"tool_name": "lookup",
                 "permission": {"tool_id": "lookup", "agent_id": "data_evidence", "permission_level": "read"}},
            ],
            # Required artifact manifest is missing 'valuation' -> manifest fail.
            "artifact_refs": [
                {"section_key": "facts", "storage_path": "x"},
                {"section_key": "snapshot"},
                {"section_key": "ratios"},
                {"section_key": "report_draft"},
                {"section_key": "evidence_packet"},
            ],
            "packet_hash": "a" * 64,
        }),
        encoding="utf-8",
    )
    archive.joinpath("run1_agent_effectiveness_audit.json").write_text(
        json.dumps({
            "ticker": "AAA",
            "agent_execution": [{
                "agent_id": "financial_analysis",
                "status": "completed",
                # LLM agent narrative deriving a target price -> unauthorized calc.
                "output_summary": {"commentary": "target price = equity value / shares = 120000"},
            }],
        }),
        encoding="utf-8",
    )

    result = evaluate_agent(tmp_path, "AAA")
    metrics = {metric["id"]: metric for metric in result["metrics"]}

    # Tool permission is derived from real per-call permission metadata.
    assert metrics["tool_permission_compliance"]["status"] == "pass"
    # The required artifact manifest is incomplete (missing 'valuation').
    assert metrics["artifact_manifest_compliance"]["status"] == "fail"
    assert metrics["schema_validity"]["status"] == "pass"
    assert metrics["no_unauthorized_calc"]["status"] == "fail"
    assert result["status"] == "fail"


def test_agent_evaluator_passes_on_real_governance_signals(tmp_path) -> None:
    schema_dir = tmp_path / "config" / "harness"
    schema_dir.mkdir(parents=True)
    schema_dir.joinpath("evidence_packet_schema.json").write_text(
        json.dumps({"required": [], "properties": {}, "additionalProperties": True}),
        encoding="utf-8",
    )
    archive = tmp_path / "storage" / "archive" / "run_bbb"
    archive.mkdir(parents=True)
    archive.joinpath("run1_evidence_packet.json").write_text(
        json.dumps({
            "schema_version": 1,
            "run_id": "run_bbb",
            "ticker": "BBB",
            "gate_results": {},
            "tool_execution_summary": [
                {"tool_name": "build_facts",
                 "permission": {"tool_id": "build_facts", "agent_id": "data_evidence", "permission_level": "read_write"}},
                {"tool_name": "read_snapshot",
                 "permission": {"tool_id": "read_snapshot", "agent_id": "financial_analysis", "permission_level": "read"}},
            ],
            "artifact_refs": [
                {"section_key": "facts"}, {"section_key": "snapshot"}, {"section_key": "ratios"},
                {"section_key": "valuation"}, {"section_key": "publishable_final_report_model"},
                {"section_key": "evidence_packet"},
            ],
            "packet_hash": "b" * 64,
        }),
        encoding="utf-8",
    )
    agent_execution = [
        {"agent_id": agent, "status": "completed", "output_summary": {"note": "interprets provided artifacts"}}
        for agent in ("financial_analysis", "thesis_report", "senior_critic")
    ]
    archive.joinpath("run1_agent_effectiveness_audit.json").write_text(
        json.dumps({"ticker": "BBB", "agent_execution": agent_execution}),
        encoding="utf-8",
    )

    result = evaluate_agent(tmp_path, "BBB")
    metrics = {metric["id"]: metric for metric in result["metrics"]}

    # Real governance signals (full tool permission, complete artifact manifest,
    # all agents completed) pass without any 5-agent minimum-sample heuristic.
    assert metrics["tool_permission_compliance"]["status"] == "pass"
    assert metrics["artifact_manifest_compliance"]["status"] == "pass"
    assert metrics["task_completion"]["status"] == "pass"
    assert metrics["no_unauthorized_calc"]["status"] == "pass"


def test_agent_evaluator_reads_scoped_run_artifacts(tmp_path) -> None:
    schema_dir = tmp_path / "config" / "harness"
    schema_dir.mkdir(parents=True)
    schema_dir.joinpath("evidence_packet_schema.json").write_text(
        json.dumps({"required": [], "properties": {}, "additionalProperties": True}),
        encoding="utf-8",
    )
    # Legacy stub: ungoverned tool call -> would fail tool permission.
    archive = tmp_path / "storage" / "archive" / "legacy"
    archive.mkdir(parents=True)
    archive.joinpath("run1_evidence_packet.json").write_text(
        json.dumps({
            "ticker": "CCC",
            "tool_execution_summary": [{"tool_name": "lookup"}],
            "artifact_refs": [],
        }),
        encoding="utf-8",
    )
    # Newer real run in storage/runs supersedes the legacy archive stub.
    run_dir = tmp_path / "storage" / "runs" / "ccc_live_eval"
    run_dir.mkdir(parents=True)
    run_dir.joinpath("ccc_live_eval_evidence_packet.json").write_text(
        json.dumps({
            "ticker": "CCC",
            "tool_execution_summary": [
                {"tool_name": "build_facts",
                 "permission": {"tool_id": "build_facts", "agent_id": "data_evidence", "permission_level": "read"}},
            ],
            "artifact_refs": [
                {"section_key": "facts"}, {"section_key": "snapshot"}, {"section_key": "ratios"},
                {"section_key": "valuation"}, {"section_key": "report_draft"},
                {"section_key": "evidence_packet"},
            ],
        }),
        encoding="utf-8",
    )
    run_dir.joinpath("ccc_live_eval_agent_effectiveness_audit.json").write_text(
        json.dumps({
            "ticker": "CCC",
            "agent_execution": [
                {"agent_id": "financial_analysis", "status": "completed", "output_summary": {}},
            ],
        }),
        encoding="utf-8",
    )

    result = evaluate_agent(tmp_path, "CCC")
    metrics = {metric["id"]: metric for metric in result["metrics"]}

    assert metrics["tool_permission_compliance"]["status"] == "pass"
    assert metrics["artifact_manifest_compliance"]["status"] == "pass"


def test_observability_evaluator_uses_run_trace_cost_latency_and_gate_history(tmp_path) -> None:
    archive = tmp_path / "storage" / "archive" / "run_aaa"
    archive.mkdir(parents=True)
    archive.joinpath("run1_evidence_packet.json").write_text(
        json.dumps({
            "schema_version": 1,
            "run_id": "run_aaa",
            "ticker": "AAA",
            "trace_url": "https://trace.test/run_aaa",
            "gate_results": {
                "REPORT_QUALITY_GATE": {
                    "passed": False,
                    "blocking_reasons": ["valuation_transparency_missing"],
                }
            },
            "trace_summary": [
                {
                    "kind": "agent_message",
                    "agent_id": "research_manager",
                    "input_summary": {"state_stage": "PLAN"},
                    "latency_ms": 1000,
                    "cost_estimate": 0.01,
                    "prompt_tokens": 100,
                    "completion_tokens": 10,
                    "attempts": 1,
                },
                {
                    "kind": "agent_message",
                    "agent_id": "financial_analysis",
                    "input_summary": {"state_stage": "ANALYZE"},
                    "latency_ms": 3000,
                    "cost_estimate": 0.03,
                    "prompt_tokens": 300,
                    "completion_tokens": 30,
                    "attempts": 2,
                },
                {
                    "kind": "retrieval_query",
                    "stage": "INGEST_AND_VALIDATE",
                    "latency_ms": 250,
                    "fallback_triggered": True,
                },
                {"kind": "artifact_upload", "status": "completed", "latency_ms": 50},
                {"kind": "pdf_render", "status": "completed", "latency_ms": 700},
            ],
        }),
        encoding="utf-8",
    )
    report = tmp_path / "output" / "AAA_report.pdf"
    report.parent.mkdir(parents=True)
    report.write_bytes(b"%PDF-1.4\n")

    result = evaluate_observability(tmp_path, "AAA")
    metrics = {metric["id"]: metric for metric in result["metrics"]}

    assert result["trace_url"] == "https://trace.test/run_aaa"
    assert result["duration_seconds"] == 5.0
    assert result["stage_durations"]["PLAN"] == 1.0
    assert result["llm"]["calls"] == 2
    assert result["llm"]["tokens_input"] == 400
    assert result["llm"]["tokens_output"] == 40
    assert result["llm"]["estimated_cost_usd"] == 0.04
    assert result["llm"]["retry_rate"] == 0.5
    assert result["retrieval"]["queries"] == 1
    assert result["retrieval"]["p95_latency_ms"] == 250
    assert result["retrieval"]["fallback_rate"] == 1.0
    assert result["blocking_gate_categories"] == ["REPORT_QUALITY_GATE"]
    assert result["publication"]["authorization_blockers"] == [
        "REPORT_QUALITY_GATE:valuation_transparency_missing"
    ]
    assert metrics["llm_retry_rate"]["status"] == "fail"
    assert metrics["retrieval_fallback_rate"]["status"] == "fail"
    assert metrics["artifact_upload_failures"]["status"] == "pass"
    assert metrics["pdf_render_failures"]["status"] == "pass"


def test_data_reliability_tier3_provenance_makes_reconciliation_not_evaluable(tmp_path) -> None:
    material_config = tmp_path / "config" / "material_metrics.yml"
    material_config.parent.mkdir(parents=True)
    material_config.write_text("income_statement:\n  - revenue.net\n", encoding="utf-8")
    golden_dir = _benchmark_golden_financials_dir(tmp_path)
    golden_dir.mkdir(parents=True)
    (golden_dir / "AAA.csv").write_text(
        "ticker,fiscal_year,period,statement_type,canonical_key,raw_label,value,unit,currency,source_type,source_uri,source_title,provider,confidence,validation_status\n"
        "AAA,2025,2025FY,income_statement,revenue.net,Revenue,100,vnd_bn,VND,financial_statement,https://vci.test/fs,VCI raw,golden_csv,0.99,accepted\n",
        encoding="utf-8",
    )
    (golden_dir / "AAA_golden_provenance.json").write_text(
        json.dumps({
            "ticker": "AAA",
            "fiscal_year": 2025,
            "source_tier": 3,
            "metrics_verified": ["revenue.net"],
        }),
        encoding="utf-8",
    )

    result = evaluate_data_reliability(tmp_path, "AAA")
    metric = {item["id"]: item for item in result["metrics"]}["official_reconciliation_rate"]

    assert metric["value"] is None
    assert metric["status"] == "not_evaluable"
    assert metric["detail"] == "source_tier_3_cannot_claim_official_reconciliation"
    assert result["official_reconciliation_rate"] is None


def test_check_golden_drift_passes_when_live_within_ranges() -> None:
    # WACC / terminal-growth are model-derived inputs and are no longer pinned;
    # golden drift regression-tests the deterministic target-price output only.
    golden = {
        "expected": {
            "fcff_target_price_vnd": {"min": 15000, "max": 350000},
        }
    }
    live = {"fcff": {"wacc": 0.12, "terminal_growth": 0.03, "target_price_vnd": 95000}}

    result = _check_golden_drift(live, golden)

    assert result["drift_violations"] == 0
    assert result["checks_run"] == 1
    assert all(c["in_range"] for c in result["drift_details"])


def test_check_golden_drift_fails_when_value_outside_range() -> None:
    golden = {
        "expected": {
            "fcff_target_price_vnd": {"min": 15000, "max": 350000},
        }
    }
    live = {"fcff": {"wacc": 0.55, "terminal_growth": 0.03, "target_price_vnd": -1000}}

    result = _check_golden_drift(live, golden)

    assert result["drift_violations"] == 1
    price_check = next(c for c in result["drift_details"] if c["metric"] == "fcff_target_price_vnd")
    assert price_check["in_range"] is False


def test_golden_drift_metric_not_applicable_when_no_fixture(tmp_path) -> None:
    valuation_dir = tmp_path / "storage" / "runs" / "run_zzz"
    valuation_dir.mkdir(parents=True)
    (valuation_dir / "valuation.json").write_text(
        json.dumps({
            "ticker": "ZZZ",
            "current_price_vnd": 100,
            "valuation_confidence": {"fcff_dcf": "low"},
            "fcff": {"wacc": 0.12, "terminal_growth": 0.03, "target_price_vnd": 50000},
            "fcfe": {},
            "blend_dcf": {},
            "sensitivity": {},
            "formula_traces": [{"method": "fcff"}],
        }),
        encoding="utf-8",
    )

    result = evaluate_financial(tmp_path, "ZZZ")
    metrics = {m["id"]: m for m in result["metrics"]}

    assert metrics["golden_drift_out_of_tolerance"]["status"] == "not_applicable"
    assert metrics["golden_drift_out_of_tolerance"]["value"] is None
