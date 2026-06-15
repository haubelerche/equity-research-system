"""Optional professional evaluation-framework adapters.

Adapters return explicit execution metadata. A missing dependency, dataset, or
model credential is ``not_executed`` rather than a fabricated score.
"""
from __future__ import annotations

import importlib.util
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

RAGAS_METRICS = (
    "context_precision",
    "context_recall",
    "faithfulness",
    "response_relevancy",
)


def _version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def _load_benchmark_01_validator() -> Any:
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "config"
        / "benchmarks"
        / "01_pandera_data_quality"
        / "pandera_schema.py"
    )
    spec = importlib.util.spec_from_file_location("benchmark_01_pandera_schema", schema_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load benchmark schema from {schema_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_facts


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

    try:
        validate_facts = _load_benchmark_01_validator()
        validate_facts(pd.DataFrame.from_records(records))
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
            "samples": [],
            "reason": "ragas_dataset_missing",
        }
    offline_scored = [
        sample for sample in samples
        if isinstance(sample.get("offline_scores"), dict)
    ]
    if len(offline_scored) == len(samples):
        per_metric: dict[str, list[float]] = {name: [] for name in RAGAS_METRICS}
        per_sample_results: list[dict[str, Any]] = []
        for index, sample in enumerate(samples, start=1):
            raw_scores = sample.get("offline_scores") or {}
            normalized_scores: dict[str, float] = {}
            for name in RAGAS_METRICS:
                if name not in raw_scores:
                    continue
                score = max(0.0, min(1.0, float(raw_scores[name])))
                normalized_scores[name] = score
                per_metric[name].append(score)
            per_sample_results.append({
                "sample_index": index,
                "sample_origin": "ragas_offline_contract",
                "id": sample.get("id"),
                "question": sample.get("question"),
                "expected_answer": sample.get("expected_answer"),
                "contexts": sample.get("contexts") or [],
                "source_tier": sample.get("source_tier"),
                "scores": normalized_scores,
                "label_rationale": sample.get("label_rationale"),
            })
        return {
            "execution_status": "executed_offline",
            "framework": "ragas_offline_contract",
            "framework_version": "offline_label_v1",
            "sample_size": len(samples),
            "scores": {
                name: sum(values) / len(values) for name, values in per_metric.items() if values
            },
            "samples": per_sample_results,
            "reason": None,
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
            "samples": [],
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
            "samples": samples,
            "reason": None,
        }
    except Exception as exc:  # Framework/model-provider errors must remain visible.
        return {
            "execution_status": "execution_error",
            "framework": "ragas",
            "framework_version": _version("ragas"),
            "sample_size": len(samples),
            "scores": {},
            "samples": [],
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
