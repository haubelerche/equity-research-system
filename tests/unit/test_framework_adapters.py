from __future__ import annotations

import csv
from pathlib import Path

from backend.evaluation.framework_adapters import (
    evaluate_deepeval_cases,
    evaluate_ragas_samples,
    validate_financial_records_with_pandera,
)

ROOT = Path(__file__).resolve().parents[2]
NEGATIVE_FIXTURES = ROOT / "config" / "benchmarks" / "01_pandera_data_quality" / "negative_fixtures"


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
        "raw_label": "Revenue",
        "value": "100",
        "unit": "vnd_bn",
        "currency": "VND",
        "source_type": "financial_statement",
        "source_uri": "https://example.com/report.pdf",
        "source_title": "Annual report",
        "provider": "golden_csv",
        "confidence": "0.95",
        "validation_status": "accepted",
    }])

    assert result["framework"] == "pandera"
    assert result["execution_status"] in {"executed", "framework_unavailable"}
    if result["execution_status"] == "executed":
        assert result["passed"] is True


def _base_row(**overrides):
    row = {
        "ticker": "DHG",
        "fiscal_year": "2025",
        "period": "2025FY",
        "statement_type": "income_statement",
        "canonical_key": "revenue.net",
        "raw_label": "Revenue",
        "value": "100",
        "unit": "vnd_bn",
        "currency": "VND",
        "source_type": "financial_statement",
        "source_uri": "https://example.com/report.pdf",
        "source_title": "Annual report",
        "provider": "golden_csv",
        "confidence": "0.95",
        "validation_status": "accepted",
    }
    row.update(overrides)
    return row


def test_pandera_rejects_accepted_revenue_net_with_negative_value() -> None:
    result = validate_financial_records_with_pandera([_base_row(value="-50")])

    assert result["framework"] == "pandera"
    if result["execution_status"] == "executed":
        assert result["passed"] is False
        assert result["failure_cases"]


def test_pandera_accepts_positive_revenue_net_when_accepted() -> None:
    result = validate_financial_records_with_pandera([_base_row(value="500")])

    assert result["framework"] == "pandera"
    if result["execution_status"] == "executed":
        assert result["passed"] is True


def test_pandera_accepts_negative_value_for_non_revenue_key() -> None:
    result = validate_financial_records_with_pandera([
        _base_row(canonical_key="net_income", value="-30")
    ])

    assert result["framework"] == "pandera"
    if result["execution_status"] == "executed":
        assert result["passed"] is True


def test_pandera_rejects_confidence_outside_range() -> None:
    result = validate_financial_records_with_pandera([_base_row(confidence="1.5")])

    assert result["framework"] == "pandera"
    if result["execution_status"] == "executed":
        assert result["passed"] is False
        assert result["failure_cases"]


def test_pandera_rejects_revenue_net_with_negative_value_even_when_rejected() -> None:
    result = validate_financial_records_with_pandera([
        _base_row(validation_status="rejected", value="-50")
    ])

    assert result["framework"] == "pandera"
    if result["execution_status"] == "executed":
        assert result["passed"] is False
        assert result["failure_cases"]


def test_pandera_rejects_schema_negative_fixtures() -> None:
    fixture_names = (
        "missing_source_uri.csv",
        "negative_revenue.csv",
        "null_material_without_reason.csv",
    )
    for fixture_name in fixture_names:
        fixture_csv = NEGATIVE_FIXTURES / fixture_name
        assert fixture_csv.exists(), f"Negative fixture missing: {fixture_csv}"

        with fixture_csv.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))

        assert rows, f"{fixture_name} must not be empty"
        result = validate_financial_records_with_pandera(rows)
        if result["execution_status"] == "executed":
            assert result["passed"] is False, f"Expected pandera to reject {fixture_name}"
            assert result["failure_cases"], f"{fixture_name} should expose failure cases"
