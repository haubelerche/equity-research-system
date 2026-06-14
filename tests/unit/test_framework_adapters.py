from __future__ import annotations

from backend.evaluation.framework_adapters import (
    evaluate_deepeval_cases,
    evaluate_ragas_samples,
    validate_financial_records_with_pandera,
)


def test_semantic_frameworks_do_not_fabricate_scores_without_datasets() -> None:
    ragas = evaluate_ragas_samples([])
    deepeval = evaluate_deepeval_cases([])

    assert ragas["execution_status"] == "not_executed"
    assert ragas["scores"] == {}
    assert deepeval["execution_status"] == "not_executed"
    assert deepeval["scores"] == {}


def test_ragas_adapter_scores_offline_contract_samples() -> None:
    result = evaluate_ragas_samples([
        {
            "id": "case-1",
            "question": "Revenue?",
            "expected_answer": "Revenue is sourced.",
            "contexts": ["Audited report revenue context"],
            "offline_scores": {
                "context_precision": 0.8,
                "context_recall": 0.7,
                "faithfulness": 0.9,
                "response_relevancy": 1.0,
            },
        },
        {
            "id": "case-2",
            "question": "Capex?",
            "expected_answer": "Capex is missing.",
            "contexts": ["Diagnostic missing capex context"],
            "offline_scores": {
                "context_precision": 0.6,
                "context_recall": 0.5,
                "faithfulness": 0.7,
                "response_relevancy": 0.8,
            },
        },
    ])

    assert result["framework"] == "ragas_offline_contract"
    assert result["execution_status"] == "executed_offline"
    assert result["scores"]["context_precision"] == 0.7
    assert result["scores"]["faithfulness"] == 0.8
    assert len(result["samples"]) == 2


def test_pandera_adapter_reports_dependency_or_executes_schema() -> None:
    result = validate_financial_records_with_pandera([{
        "ticker": "DHG",
        "fiscal_year": "2025",
        "period": "2025FY",
        "statement_type": "income_statement",
        "canonical_key": "revenue.net",
        "value": "100",
        "unit": "vnd_bn",
        "currency": "VND",
        "source_uri": "https://example.com/report.pdf",
        "source_title": "Annual report",
        "confidence": "0.95",
        "validation_status": "accepted",
    }])

    assert result["framework"] == "pandera"
    assert result["execution_status"] in {"executed", "framework_unavailable"}
    if result["execution_status"] == "executed":
        assert result["passed"] is True
