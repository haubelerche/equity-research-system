"""Optional professional evaluation-framework adapters.

Adapters return explicit execution metadata. A missing dependency, dataset, or
model credential is ``not_executed`` rather than a fabricated score.
"""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any


def _version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def validate_financial_records_with_pandera(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    if not records:
        return {
            "execution_status": "not_executed",
            "framework": "pandera",
            "framework_version": _version("pandera"),
            "sample_size": 0,
            "passed": None,
            "failure_cases": [],
            "reason": "financial_records_missing",
        }
    try:
        import pandas as pd
        import pandera.pandas as pa
    except Exception as exc:
        return {
            "execution_status": "framework_unavailable",
            "framework": "pandera",
            "framework_version": _version("pandera"),
            "sample_size": len(records),
            "passed": None,
            "failure_cases": [],
            "reason": str(exc),
        }

    schema = pa.DataFrameSchema(
        {
            "ticker": pa.Column(str, nullable=False),
            "fiscal_year": pa.Column(int, pa.Check.in_range(2000, 2100), nullable=False),
            "period": pa.Column(str, pa.Check.str_matches(r"^\d{4}(FY|Q[1-4])$"), nullable=False),
            "statement_type": pa.Column(str, pa.Check.isin(
                ["income_statement", "balance_sheet", "cash_flow", "capital_structure"]
            ), nullable=False),
            "canonical_key": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
            "value": pa.Column(float, nullable=False, coerce=True),
            "unit": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
            "currency": pa.Column(str, nullable=False),
            "source_uri": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
            "source_title": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
            "confidence": pa.Column(float, pa.Check.in_range(0, 1), nullable=False, coerce=True),
            "validation_status": pa.Column(str, pa.Check.isin(
                ["accepted", "rejected", "manual_review"]
            ), nullable=False),
        },
        strict=False,
        coerce=True,
    )
    try:
        schema.validate(pd.DataFrame.from_records(records), lazy=True)
        return {
            "execution_status": "executed",
            "framework": "pandera",
            "framework_version": _version("pandera"),
            "sample_size": len(records),
            "passed": True,
            "failure_cases": [],
            "reason": None,
        }
    except pa.errors.SchemaErrors as exc:
        cases = exc.failure_cases.fillna("").to_dict(orient="records")
        return {
            "execution_status": "executed",
            "framework": "pandera",
            "framework_version": _version("pandera"),
            "sample_size": len(records),
            "passed": False,
            "failure_cases": cases[:100],
            "reason": "pandera_schema_validation_failed",
        }


def evaluate_ragas_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Execute Ragas only when a complete semantic benchmark dataset exists."""
    if not samples:
        return {
            "execution_status": "not_executed",
            "framework": "ragas",
            "framework_version": _version("ragas"),
            "sample_size": 0,
            "scores": {},
            "reason": "ragas_dataset_missing",
        }
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
    except Exception as exc:
        return {
            "execution_status": "framework_unavailable",
            "framework": "ragas",
            "framework_version": _version("ragas"),
            "sample_size": len(samples),
            "scores": {},
            "reason": str(exc),
        }
    try:
        result = evaluate(
            Dataset.from_list(samples),
            metrics=[context_precision, context_recall, faithfulness, answer_relevancy],
        )
        scores = dict(result)
        if "answer_relevancy" in scores:
            scores["response_relevancy"] = scores.pop("answer_relevancy")
        return {
            "execution_status": "executed",
            "framework": "ragas",
            "framework_version": _version("ragas"),
            "sample_size": len(samples),
            "scores": scores,
            "reason": None,
        }
    except Exception as exc:  # Framework/model-provider errors must remain visible.
        return {
            "execution_status": "execution_error",
            "framework": "ragas",
            "framework_version": _version("ragas"),
            "sample_size": len(samples),
            "scores": {},
            "reason": str(exc),
        }


def evaluate_deepeval_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Execute configured DeepEval G-Eval rubrics for agent/report cases."""
    if not cases:
        return {
            "execution_status": "not_executed",
            "framework": "deepeval",
            "framework_version": _version("deepeval"),
            "sample_size": 0,
            "scores": {},
            "reason": "deepeval_dataset_missing",
        }
    try:
        from deepeval.metrics import GEval
        from deepeval.test_case import LLMTestCase, LLMTestCaseParams
    except Exception as exc:
        return {
            "execution_status": "framework_unavailable",
            "framework": "deepeval",
            "framework_version": _version("deepeval"),
            "sample_size": len(cases),
            "scores": {},
            "reason": str(exc),
        }

    rubrics = {
        "role_adherence": "Evaluate whether the output stayed within the assigned role and responsibilities.",
        "groundedness": "Evaluate whether material conclusions are supported by the supplied evidence.",
        "task_completion": "Evaluate whether all required task outputs were materially completed.",
        "plan_adherence": "Evaluate whether required plan steps and constraints were followed.",
    }
    per_metric: dict[str, list[float]] = {name: [] for name in rubrics}
    try:
        for case in cases:
            test_case = LLMTestCase(
                input=str(case.get("input") or ""),
                actual_output=str(case.get("actual_output") or ""),
                expected_output=str(case.get("expected_output") or ""),
                retrieval_context=list(case.get("retrieval_context") or []),
            )
            for name, criteria in rubrics.items():
                metric = GEval(
                    name=name,
                    criteria=criteria,
                    evaluation_params=[
                        LLMTestCaseParams.INPUT,
                        LLMTestCaseParams.ACTUAL_OUTPUT,
                        LLMTestCaseParams.EXPECTED_OUTPUT,
                        LLMTestCaseParams.RETRIEVAL_CONTEXT,
                    ],
                )
                metric.measure(test_case)
                per_metric[name].append(float(metric.score))
        return {
            "execution_status": "executed",
            "framework": "deepeval",
            "framework_version": _version("deepeval"),
            "sample_size": len(cases),
            "scores": {
                name: sum(values) / len(values) for name, values in per_metric.items() if values
            },
            "reason": None,
        }
    except Exception as exc:
        return {
            "execution_status": "execution_error",
            "framework": "deepeval",
            "framework_version": _version("deepeval"),
            "sample_size": len(cases),
            "scores": {},
            "reason": str(exc),
        }
