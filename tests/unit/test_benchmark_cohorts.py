from __future__ import annotations

from types import SimpleNamespace

from backend.evaluation.benchmark_cohorts import (
    available_benchmark_cohorts,
    resolve_benchmark_tickers,
)
from scripts import run_benchmark_suite


def test_default_benchmark_cohort_is_diverse_and_not_single_ticker() -> None:
    tickers = resolve_benchmark_tickers()

    assert tickers[0] == "DHG"
    assert len(tickers) == 42
    assert len(set(tickers)) == len(tickers)
    assert tickers != ["DBD"]
    assert "DBD" in tickers
    assert "CON" not in tickers


def test_available_benchmark_cohorts_expose_more_than_one_archetype() -> None:
    cohorts = available_benchmark_cohorts()

    assert len(cohorts["full_universe"]) == 42
    assert cohorts["diversified_core"] == ["DHG", "IMP", "DMC", "TRA", "TNH"]
    assert cohorts["diversified_healthcare"] == ["DHG", "IMP", "DMC", "TRA", "JVC", "DBD"]
    assert cohorts["financial_model_top10"] == [
        "DHG",
        "DBD",
        "IMP",
        "DMC",
        "TRA",
        "OPC",
        "TNH",
        "JVC",
        "DGW",
        "AMV",
    ]
    assert cohorts["agent_llm_judge_top10"] == cohorts["financial_model_top10"]


def test_resolve_benchmark_tickers_deduplicates_and_normalizes_explicit_inputs() -> None:
    tickers = resolve_benchmark_tickers(tickers=[" dhg ", "DBD", "dhg", "IMP"])

    assert tickers == ["DHG", "DBD", "IMP"]


def test_resolve_benchmark_tickers_allows_ad_hoc_dataset_when_requested() -> None:
    tickers = resolve_benchmark_tickers(
        tickers=[" con "],
        validate_against_universe=False,
    )

    assert tickers == ["CON"]


def test_benchmark_suite_aggregate_counts_statuses() -> None:
    packets = [
        {
            "ticker": "DHG",
            "overall_status": "pass",
            "publication_status": "DRAFT_PUBLISHABLE",
            "artifacts": [{"plan_id": "01", "status": "pass"}, {"plan_id": "02", "status": "pass"}],
        },
        {
            "ticker": "DBD",
            "overall_status": "blocked",
            "publication_status": "BLOCKED_BY_P0",
            "artifacts": [{"plan_id": "01", "status": "blocked"}, {"plan_id": "02", "status": "fail"}],
        },
    ]

    summary = run_benchmark_suite._aggregate_summary(
        cohort_name="diversified_core",
        tickers=["DHG", "DBD"],
        packets=packets,
        generated_at="2026-06-15T00:00:00+00:00",
    )

    assert summary["cohort"] == "diversified_core"
    assert summary["plan_stats"]["01"]["pass"] == 1
    assert summary["plan_stats"]["01"]["blocked"] == 1
    assert summary["plan_stats"]["02"]["pass"] == 1
    assert summary["plan_stats"]["02"]["fail"] == 1


def test_benchmark_suite_aggregate_metric_exposes_numeric_cohort_rate() -> None:
    packets = [
        {
            "ticker": "DHG",
            "artifacts": [{
                "plan_id": "05",
                "status": "pass",
                "metric_results": [{
                    "id": "tool_permission_compliance",
                    "metric_id": "tool_permission_compliance",
                    "metric_type": "coverage",
                    "unit": "percent",
                    "status": "pass",
                    "value": 1.0,
                    "calculation": {"aggregation": "coverage"},
                }],
            }],
        },
        {
            "ticker": "DBD",
            "artifacts": [{
                "plan_id": "05",
                "status": "blocked",
                "metric_results": [{
                    "id": "tool_permission_compliance",
                    "metric_id": "tool_permission_compliance",
                    "metric_type": "coverage",
                    "unit": "percent",
                    "status": "not_evaluable",
                    "value": None,
                    "source": "missing",
                    "failed_examples": [{"reason": "evaluation_evidence_missing"}],
                    "calculation": {"aggregation": "coverage"},
                }],
            }],
        },
    ]

    summary = run_benchmark_suite._aggregate_summary(
        cohort_name="agent_llm_judge_top10",
        tickers=["DHG", "DBD"],
        packets=packets,
        generated_at="2026-06-15T00:00:00+00:00",
        plan_ids=("05",),
    )
    artifact = summary["artifacts"][0]
    metric = artifact["metric_results"][0]

    assert artifact["artifact"] == "agent_eval.json"
    assert metric["value"] == 0.5
    assert metric["calculation"]["aggregation"] == "cohort_pass_rate"
    assert metric["calculation"]["numerator"] == 1
    assert metric["calculation"]["denominator"] == 2
    assert metric["failed_examples"][0]["ticker"] == "DBD"


def test_benchmark_suite_writes_per_ticker_packets(monkeypatch, tmp_path) -> None:
    fake_plans = [
        SimpleNamespace(id="01", name="Data reliability", artifact="data_quality.json", test_targets=("tests/unit",)),
    ]
    writes: list[tuple[str, dict]] = []

    monkeypatch.setattr(run_benchmark_suite, "_selected_plans", lambda *args, **kwargs: fake_plans)
    monkeypatch.setattr(run_benchmark_suite, "_run_plan_tests", lambda plan, root: {
        "status": "pass",
        "targets": list(plan.test_targets),
        "exit_code": 0,
        "duration_seconds": 0.01,
        "summary": {"passed": 1},
        "output_tail": [],
    })
    monkeypatch.setattr(run_benchmark_suite, "_runtime_evidence", lambda plan, root, excluded_output_dir=None: {
        "required": [],
        "found": {},
        "missing": [],
        "status": "not_applicable",
    })
    monkeypatch.setattr(run_benchmark_suite, "evaluate_plan", lambda *args, **kwargs: {
        "status": "pass",
        "metrics": [{"id": "sample", "value": 1, "status": "pass"}],
        "blocking_issues": [],
        "sample": True,
    })
    monkeypatch.setattr(run_benchmark_suite, "_write_json", lambda path, payload: writes.append((str(path), payload)))

    packet = run_benchmark_suite._run_for_ticker(
        ticker="DHG",
        output_dir=tmp_path,
        generated_at="2026-06-15T00:00:00+00:00",
        skip_tests=False,
        plan_ids=("01",),
    )

    assert packet["ticker"] == "DHG"
    assert writes[0][0].endswith("DHG\\data_quality.json")
    assert writes[-1][0].endswith("DHG\\evaluation_packet.json")
