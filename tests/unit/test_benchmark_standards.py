from __future__ import annotations

from backend.evaluation.benchmark_standards import standard_metric


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

    assert metric["threshold"] == ">= 0.75"
    assert metric["threshold_policy"]["profile"] == "mvp"
    assert metric["evaluator"]["framework"] == "production_retriever_golden_set"
    assert metric["sample_size"] == 0
    assert metric["failed_examples"] == [{"reason": "ticker mismatch", "source": "golden set"}]
