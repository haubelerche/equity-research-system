"""Canonical benchmark data and result paths.

Benchmark inputs live under ``config/benchmarks``. Evaluation outputs live under
``output/evaluation/eval_result`` and must not be treated as benchmark fixtures.
"""
from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
"""Repository root for local relative lookups."""


def _resolve_benchmark_root() -> Path:
    """Resolve benchmark config directory with optional external override.

    Set ``BENCHMARK_CONFIG_ROOT`` environment variable to point to a benchmark
    directory outside repository root when needed.
    """
    configured_root = os.environ.get("BENCHMARK_CONFIG_ROOT")
    if configured_root:
        candidate = Path(configured_root).expanduser()
        return (candidate if candidate.is_absolute() else ROOT / candidate).resolve()
    return (ROOT / "config" / "benchmarks").resolve()


def _resolve_benchmark_label() -> str:
    configured_root = os.environ.get("BENCHMARK_CONFIG_ROOT")
    if configured_root:
        candidate = Path(configured_root).expanduser()
        if candidate.is_absolute():
            return candidate.as_posix()
        return (ROOT / candidate).as_posix()
    return "config/benchmarks"

BENCHMARK_CONFIG_RELATIVE = Path("config") / "benchmarks"
BENCHMARK_SHARED_RELATIVE = BENCHMARK_CONFIG_RELATIVE / "shared"
GOLDEN_FINANCIALS_RELATIVE = BENCHMARK_SHARED_RELATIVE / "golden_financials"
RAG_GOLDEN_QUERY_RELATIVE = (
    BENCHMARK_CONFIG_RELATIVE / "02_ragas_retrieval" / "golden_queries"
)
RAG_GOLDEN_CHUNK_RELATIVE = (
    BENCHMARK_CONFIG_RELATIVE / "02_ragas_retrieval" / "golden_chunks"
)
RAGAS_SAMPLE_RELATIVE = (
    BENCHMARK_CONFIG_RELATIVE / "02_ragas_retrieval" / "ragas" / "ragas_samples.json"
)
DEEPEVAL_CASE_RELATIVE = (
    BENCHMARK_CONFIG_RELATIVE
    / "04_deepeval_agent"
    / "deepeval_cases"
    / "agent_cases.json"
)
GOLDEN_VALUATION_CASES_RELATIVE = (
    BENCHMARK_CONFIG_RELATIVE
    / "03_financial_benchmarks"
    / "golden_valuation"
    / "valuation_cases.json"
)

BENCHMARK_CONFIG_ROOT = _resolve_benchmark_root()
BENCHMARK_SHARED_ROOT = BENCHMARK_CONFIG_ROOT / "shared"
BENCHMARK_COHORTS_PATH = BENCHMARK_SHARED_ROOT / "benchmark_cohorts.yaml"
GOLDEN_FINANCIALS_DIR = BENCHMARK_SHARED_ROOT / "golden_financials"
RAG_GOLDEN_QUERY_DIR = (
    BENCHMARK_CONFIG_ROOT / "02_ragas_retrieval" / "golden_queries"
)
RAG_GOLDEN_CHUNK_DIR = (
    BENCHMARK_CONFIG_ROOT / "02_ragas_retrieval" / "golden_chunks"
)
RAGAS_SAMPLE_PATH = (
    BENCHMARK_CONFIG_ROOT / "02_ragas_retrieval" / "ragas" / "ragas_samples.json"
)
DEEPEVAL_CASE_PATH = (
    BENCHMARK_CONFIG_ROOT
    / "04_deepeval_agent"
    / "deepeval_cases"
    / "agent_cases.json"
)
GOLDEN_VALUATION_CASES_PATH = (
    BENCHMARK_CONFIG_ROOT
    / "03_financial_benchmarks"
    / "golden_valuation"
    / "valuation_cases.json"
)

EVALUATION_OUTPUT_ROOT = ROOT / "output" / "evaluation" / "eval_result"
BENCHMARK_SUITE_OUTPUT_DIR = EVALUATION_OUTPUT_ROOT / "benchmark_suite"

BENCHMARK_CONFIG_LABEL = _resolve_benchmark_label()
BENCHMARK_RESULTS_LABEL = "output/evaluation/eval_result/benchmark_suite"
