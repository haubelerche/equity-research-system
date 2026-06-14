from __future__ import annotations

import json

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
    evaluate_retrieval,
    _matrix_varies,
    _run_local_retrieval_benchmark,
)


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
    assert load_latest_evaluation(tmp_path) == packet
    assert load_evaluation_artifact("evaluation_packet.json", tmp_path) == packet
    assert load_evaluation_artifact("../.env", tmp_path) is None


def test_matrix_variation_requires_multiple_numeric_values() -> None:
    assert _matrix_varies({"a": {"x": 1, "y": 2}})
    assert not _matrix_varies({"a": {"x": 1, "y": 1}})


def test_local_retrieval_benchmark_scores_against_live_retriever(tmp_path, monkeypatch) -> None:
    # Pure-live: golden queries are scored against the production retriever (term match
    # on retrieved chunks), injected here deterministically via the test seam.
    golden = tmp_path / "config" / "eval" / "rag_golden_queries.yaml"
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
    golden = tmp_path / "config" / "eval" / "rag_golden_queries.yaml"
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
    golden = tmp_path / "config" / "eval" / "rag_golden_queries.yaml"
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


def _write_dbd_eval_inputs(tmp_path):
    golden_dir = tmp_path / "config" / "eval" / "rag_golden_queries"
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
    ragas_dir = tmp_path / "config" / "eval" / "ragas"
    ragas_dir.mkdir(parents=True)
    (ragas_dir / "DBD.json").write_text(
        json.dumps([
            {
                "id": "semantic-1",
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
    assert metrics["accounting_invariant_violations"]["value"] >= 1
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
    assert metrics["sensitivity_base_cell"]["status"] == "pass"
    assert metrics["valuation_publishable"]["status"] == "pass"
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
            "gate_results": {
                "TOOL_PERMISSION_GATE": {"passed": True},
                "ARTIFACT_MANIFEST_GATE": {"passed": False, "blocking_reasons": ["artifact_storage_path_missing:valuation"]},
            },
            "tool_execution_summary": [{"tool_name": "lookup", "status": "completed"}],
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
                "output_summary": {"commentary": "target price = equity value / shares = 120000"},
            }],
        }),
        encoding="utf-8",
    )

    result = evaluate_agent(tmp_path, "AAA")
    metrics = {metric["id"]: metric for metric in result["metrics"]}

    assert metrics["tool_permission_compliance"]["status"] == "pass"
    assert metrics["artifact_manifest_compliance"]["status"] == "fail"
    assert metrics["schema_validity"]["status"] == "pass"
    assert metrics["no_unauthorized_calc"]["status"] == "fail"
    assert result["status"] == "fail"
