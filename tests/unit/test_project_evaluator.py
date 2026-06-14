from __future__ import annotations

import json

from backend.evaluation.project_evaluator import (
    PlanDefinition,
    _artifact_payload,
    load_evaluation_artifact,
    load_latest_evaluation,
)
from backend.evaluation.runtime_evaluators import (
    evaluate_data_reliability,
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


def test_local_retrieval_benchmark_rejects_cross_ticker_golden_set(tmp_path) -> None:
    golden = tmp_path / "config" / "eval" / "rag_golden_queries.yaml"
    golden.parent.mkdir(parents=True)
    golden.write_text(
        "version: test-v1\nticker: DHG\nqueries:\n"
        "  - id: revenue\n"
        "    query: net revenue\n"
        "    expected_pages: [2]\n",
        encoding="utf-8",
    )

    result = _run_local_retrieval_benchmark(tmp_path, "DBD", golden)

    assert result["execution_status"] == "not_executed"
    assert result["hit_rate_at_5"] is None
    assert result["reason"] == "golden_query_ticker_mismatch:DHG:DBD"


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
    golden_dir = tmp_path / "config" / "dataset" / "golden" / "financials"
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
    golden_dir = tmp_path / "config" / "dataset" / "golden" / "financials"
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


def test_data_reliability_fails_closed_when_ocr_metadata_is_missing(tmp_path) -> None:
    material_config = tmp_path / "config" / "material_metrics.yml"
    material_config.parent.mkdir(parents=True)
    material_config.write_text("income_statement:\n  - revenue.net\n", encoding="utf-8")
    golden_dir = tmp_path / "config" / "dataset" / "golden" / "financials"
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

    assert metric["status"] == "fail"
    assert metric["value"] == 1.0
    assert metric["calculation"]["numerator"] == 20
    assert metric["calculation"]["denominator"] == 20
    assert metric["sample_size"] == 20
    assert len(metric["calculation"]["per_sample_results"]) == 20
    assert all(
        sample["reason"] == "ocr_metadata_missing_for_ticker"
        for sample in metric["failed_examples"]
    )
