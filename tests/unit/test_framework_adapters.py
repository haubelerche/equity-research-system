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
