from __future__ import annotations

import os
from pathlib import Path

from backend.evaluation import project_evaluator, runtime_evaluators
from backend.evaluation.benchmark_paths import (
    BENCHMARK_COHORTS_PATH,
    BENCHMARK_CONFIG_ROOT,
    BENCHMARK_SUITE_OUTPUT_DIR,
    GOLDEN_FINANCIALS_DIR,
    RAG_GOLDEN_QUERY_DIR,
)
from scripts import export_db_to_golden_csv, generate_rag_golden_queries, validate_data


def test_benchmark_inputs_have_single_canonical_config_root() -> None:
    configured = os.environ.get("BENCHMARK_CONFIG_ROOT", "config/benchmarks")
    canonical = str(Path(configured).as_posix())

    paths = [
        BENCHMARK_CONFIG_ROOT,
        BENCHMARK_COHORTS_PATH,
        GOLDEN_FINANCIALS_DIR,
        RAG_GOLDEN_QUERY_DIR,
        validate_data.GOLDEN_DIR,
        export_db_to_golden_csv.GOLDEN_DIR,
        export_db_to_golden_csv.COHORTS_PATH,
        generate_rag_golden_queries.OUTPUT_DIR,
    ]

    for path in paths:
        normalized = path.as_posix()
        assert normalized.endswith(canonical) or canonical in normalized
        assert "config/dataset/benchmarks" not in normalized


def test_evaluation_outputs_are_separate_from_benchmark_inputs() -> None:
    assert project_evaluator.DEFAULT_OUTPUT_DIR.as_posix().endswith(
        "output/evaluation/eval_result"
    )
    assert BENCHMARK_SUITE_OUTPUT_DIR.as_posix().endswith(
        "output/evaluation/eval_result/benchmark_suite"
    )
    assert runtime_evaluators.BENCHMARK_DATA_ROOT.as_posix().endswith("config/benchmarks")
