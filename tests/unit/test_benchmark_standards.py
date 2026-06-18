from __future__ import annotations

from backend.evaluation.benchmark_standards import evaluate_metric_threshold, standard_metric


def test_metric_registry_governs_threshold_and_explanation_contract() -> None:
    metric = standard_metric(
        metric_id="mrr_at_5",
        metric_name="MRR@5",
        value=None,
        threshold=">= 0.80",
        status="not_evaluable",
        source="golden set",
        detail="ticker mismatch",
    )

    assert metric["threshold"] == ">= 75%"
    assert metric["threshold_policy"]["profile"] == "mvp"
    assert metric["evaluator"]["framework"] == "production_retriever_golden_set"
    assert metric["sample_size"] == 0
    assert metric["failed_examples"] == [{"reason": "ticker mismatch", "source": "golden set"}]


def test_metric_threshold_evaluation_handles_ratio_percent_and_boolean_contracts() -> None:
    assert evaluate_metric_threshold(
        {"threshold": ">= 90/100", "threshold_operator": ">=", "unit": "score"},
        0.978,
    ) == "pass"
    assert evaluate_metric_threshold(
        {"threshold": ">= 90%", "threshold_operator": ">=", "unit": "score"},
        0.978,
    ) == "pass"
    assert evaluate_metric_threshold(
        {"threshold": ">= 95%", "threshold_operator": ">=", "unit": "percent"},
        0.98,
    ) == "pass"
    assert evaluate_metric_threshold(
        {"threshold": "<= 5%", "threshold_operator": "<=", "unit": "percent"},
        0.944,
    ) == "fail"
    assert evaluate_metric_threshold(
        {"threshold": "= true", "threshold_operator": "=", "unit": "boolean"},
        False,
    ) == "fail"
