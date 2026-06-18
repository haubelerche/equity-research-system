from __future__ import annotations

import json
from types import SimpleNamespace

from backend.dataset.config_io import load_universe_tickers
from backend.evaluation.benchmark_cohorts import (
    available_benchmark_cohorts,
    resolve_benchmark_tickers,
)
from scripts import run_benchmark_suite


def test_default_benchmark_cohort_is_diverse_and_not_single_ticker() -> None:
    tickers = resolve_benchmark_tickers()
    universe_tickers = load_universe_tickers()

    assert tickers[0] == "DHG"
    assert len(tickers) == len(universe_tickers)
    assert len(set(tickers)) == len(tickers)
    assert tickers != ["DBD"]
    assert "DBD" in tickers


def test_available_benchmark_cohorts_expose_more_than_one_archetype() -> None:
    cohorts = available_benchmark_cohorts()

    assert len(cohorts["full_universe"]) == len(load_universe_tickers())
    assert cohorts["diversified_core"] == ["DHG", "IMP", "DMC", "TRA", "TNH"]
    assert cohorts["diversified_healthcare"] == ["DHG", "IMP", "DMC", "TRA", "JVC", "DBD"]
    assert cohorts["rag_representative_dhg"] == ["DHG"]
    assert cohorts["financial_model_top10"] == [
        "DHG",
        "DBD",
        "IMP",
        "DMC",
        "TRA",
        "OPC",
        "TNH",
        "JVC",
        "DHT",
        "AMV",
    ]
    assert cohorts["agent_llm_judge_top10"] == cohorts["financial_model_top10"]


def test_benchmark_suite_default_plan_ids_focus_evidence_sensitive_plans() -> None:
    assert run_benchmark_suite.DEFAULT_PLAN_IDS == ("01", "03", "04", "05", "06", "07")


def test_resolve_benchmark_tickers_deduplicates_and_normalizes_explicit_inputs() -> None:
    tickers = resolve_benchmark_tickers(tickers=[" dhg ", "DBD", "dhg", "IMP"])

    assert tickers == ["DHG", "DBD", "IMP"]


def test_resolve_benchmark_tickers_allows_ad_hoc_dataset_when_requested() -> None:
    tickers = resolve_benchmark_tickers(
        tickers=[" zzz "],
        validate_against_universe=False,
    )

    assert tickers == ["ZZZ"]


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
        plan_ids=("01", "02"),
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
                    "evidence": {"artifact_ids": ["storage/runs/DHG/evidence_packet.json"]},
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
                    "evidence": {"artifact_ids": ["storage/runs/DBD/evidence_packet.json"]},
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
    assert metric["calculation"]["inputs"]["source_artifacts"] == [
        "DBD/agent_eval.json",
        "DHG/agent_eval.json",
    ]
    assert metric["calculation"]["parameters"]["source_metric_ids"] == ["tool_permission_compliance"]
    assert metric["evidence"]["artifact_ids"] == [
        "DBD/agent_eval.json",
        "DHG/agent_eval.json",
        "storage/runs/DBD/evidence_packet.json",
        "storage/runs/DHG/evidence_packet.json",
    ]
    assert metric["calculation"]["per_sample_results"][0]["artifact_id"] == "DHG/agent_eval.json"
    assert metric["calculation"]["per_sample_results"][0]["source_metric_id"] == "tool_permission_compliance"
    assert metric["calculation"]["per_sample_results"][1]["failed_examples"] == [
        {"reason": "evaluation_evidence_missing"}
    ]
    assert metric["failed_examples"][0]["ticker"] == "DBD"
    assert metric["failed_examples"][0]["artifact_id"] == "DBD/agent_eval.json"


def test_benchmark_suite_aggregate_keeps_full_cohort_sample_details() -> None:
    tickers = [f"T{i:02d}" for i in range(45)]
    packets = [
        {
            "ticker": ticker,
            "artifacts": [{
                "plan_id": "03",
                "status": "pass",
                "metric_results": [{
                    "id": "fcff",
                    "metric_id": "fcff",
                    "metric_type": "boolean",
                    "unit": "boolean",
                    "threshold": "= true",
                    "threshold_operator": "=",
                    "status": "pass",
                    "value": True,
                    "detail": "fcff formula reconciled",
                    "calculation": {
                        "aggregation": "boolean_gate",
                        "per_sample_results": [{
                            "ticker": ticker,
                            "canonical_key": "fcff",
                            "status": "pass",
                        }],
                    },
                }],
            }],
        }
        for ticker in tickers
    ]

    summary = run_benchmark_suite._aggregate_summary(
        cohort_name="full_universe",
        tickers=tickers,
        packets=packets,
        generated_at="2026-06-15T00:00:00+00:00",
        plan_ids=("03",),
    )
    metric = summary["artifacts"][0]["metric_results"][0]
    per_ticker_samples = metric["calculation"]["per_sample_results"]

    assert metric["sample_size"] == 45
    assert len(per_ticker_samples) == 45
    assert metric["calculation"]["denominator"] == 45
    assert per_ticker_samples[0]["artifact_id"] == "T00/financial_eval.json"
    assert per_ticker_samples[0]["source_samples"] == [{
        "ticker": "T00",
        "canonical_key": "fcff",
        "status": "pass",
    }]


def test_benchmark_suite_aggregate_keeps_missing_metric_tickers_in_denominator() -> None:
    tickers = [f"T{i:02d}" for i in range(45)]
    packets = []
    for index, ticker in enumerate(tickers):
        metric_results = []
        if index < 9:
            metric_results.append({
                "id": "fcff",
                "metric_id": "fcff",
                "metric_type": "boolean",
                "unit": "boolean",
                "threshold": "= true",
                "threshold_operator": "=",
                "status": "pass",
                "value": True,
                "calculation": {
                    "aggregation": "boolean_gate",
                    "per_sample_results": [{
                        "ticker": ticker,
                        "canonical_key": "fcff",
                        "status": "pass",
                    }],
                },
            })
        packets.append({
            "ticker": ticker,
            "artifacts": [{
                "plan_id": "03",
                "status": "pass" if metric_results else "blocked",
                "metric_results": metric_results,
            }],
        })

    summary = run_benchmark_suite._aggregate_summary(
        cohort_name="full_universe",
        tickers=tickers,
        packets=packets,
        generated_at="2026-06-15T00:00:00+00:00",
        plan_ids=("03",),
    )
    metric = summary["artifacts"][0]["metric_results"][0]
    per_ticker_samples = metric["calculation"]["per_sample_results"]

    assert metric["sample_size"] == 45
    assert metric["value"] == 0.2
    assert metric["status"] == "fail"
    assert len(per_ticker_samples) == 45
    assert per_ticker_samples[8]["status"] == "pass"
    assert per_ticker_samples[9]["status"] == "not_evaluable"
    assert per_ticker_samples[9]["source_samples"] == [{
        "ticker": "T09",
        "status": "not_evaluable",
        "reason": "metric_missing_for_ticker",
        "artifact_id": "T09/financial_eval.json",
    }]


def test_benchmark_suite_aggregate_does_not_pass_when_ops_samples_are_not_evaluable() -> None:
    packets = [
        {
            "ticker": "DHG",
            "artifacts": [{
                "plan_id": "07",
                "status": "pass",
                "metric_results": [{
                    "id": "warm_full_report_p95_latency",
                    "metric_id": "warm_full_report_p95_latency",
                    "metric_type": "latency_percentile",
                    "unit": "seconds",
                    "threshold": "<= 600",
                    "threshold_operator": "<=",
                    "status": "pass",
                    "value": 500.0,
                    "calculation": {"aggregation": "p95"},
                }],
            }],
        },
        {
            "ticker": "AMP",
            "artifacts": [{
                "plan_id": "07",
                "status": "blocked",
                "metric_results": [{
                    "id": "warm_full_report_p95_latency",
                    "metric_id": "warm_full_report_p95_latency",
                    "metric_type": "latency_percentile",
                    "unit": "seconds",
                    "threshold": "<= 600",
                    "threshold_operator": "<=",
                    "status": "not_evaluable",
                    "value": None,
                    "source": "latency trace missing",
                    "failed_examples": [{"reason": "latency_trace_missing"}],
                    "calculation": {
                        "aggregation": "p95",
                        "per_sample_results": [{
                            "status": "not_evaluable",
                            "reason": "latency_trace_missing",
                        }],
                    },
                }],
            }],
        },
    ]

    summary = run_benchmark_suite._aggregate_summary(
        cohort_name="ops",
        tickers=["DHG", "AMP"],
        packets=packets,
        generated_at="2026-06-15T00:00:00+00:00",
        plan_ids=("07",),
    )
    metric = summary["artifacts"][0]["metric_results"][0]

    assert metric["value"] == 0.5
    assert metric["status"] == "not_evaluable"
    assert metric["sample_size"] == 2
    assert len(metric["calculation"]["per_sample_results"]) == 2
    assert metric["failed_examples"][0]["ticker"] == "AMP"


def test_benchmark_suite_boolean_metric_aggregates_as_percent_gate() -> None:
    packets = [
        {
            "ticker": "DHG",
            "artifacts": [{
                "plan_id": "01",
                "status": "pass",
                "metric_results": [{
                    "id": "raw_bctc_non_empty",
                    "metric_id": "raw_bctc_non_empty",
                    "metric_type": "boolean",
                    "unit": "boolean",
                    "threshold": "= true",
                    "threshold_operator": "=",
                    "status": "pass",
                    "value": True,
                    "calculation": {
                        "aggregation": "boolean_gate",
                        "per_sample_results": [
                            {"file": "income_statement_year.json", "status": "non_empty"},
                            {"file": "balance_sheet_year.json", "status": "non_empty"},
                        ],
                    },
                }],
            }],
        },
        {
            "ticker": "IMP",
            "artifacts": [{
                "plan_id": "01",
                "status": "fail",
                "metric_results": [{
                    "id": "raw_bctc_non_empty",
                    "metric_id": "raw_bctc_non_empty",
                    "metric_type": "boolean",
                    "unit": "boolean",
                    "threshold": "= true",
                    "threshold_operator": "=",
                    "status": "warning",
                    "value": False,
                    "failed_examples": [{"file": "ratio_year.json", "status": "missing"}],
                    "calculation": {"aggregation": "boolean_gate"},
                }],
            }],
        },
    ]

    summary = run_benchmark_suite._aggregate_summary(
        cohort_name="data_quality",
        tickers=["DHG", "IMP"],
        packets=packets,
        generated_at="2026-06-15T00:00:00+00:00",
        plan_ids=("01",),
    )
    metric = summary["artifacts"][0]["metric_results"][0]

    assert metric["value"] == 0.5
    assert metric["status"] == "fail"
    assert metric["metric_type"] == "coverage"
    assert metric["unit"] == "percent"
    assert metric["threshold"] == ">= 90%"
    assert metric["calculation"]["aggregation"] == "cohort_pass_rate"
    assert metric["calculation"]["numerator"] == 1
    assert metric["calculation"]["denominator"] == 2
    assert metric["calculation"]["per_sample_results"][0]["source_calculation"]["per_sample_count"] == 2
    assert metric["calculation"]["per_sample_results"][0]["source_samples"] == [
        {"file": "income_statement_year.json", "status": "non_empty"},
        {"file": "balance_sheet_year.json", "status": "non_empty"},
    ]


def test_benchmark_suite_aggregate_metric_status_follows_displayed_threshold_value() -> None:
    packets = [
        {
            "ticker": "DHG",
            "artifacts": [{
                "plan_id": "01",
                "status": "pass",
                "metric_results": [{
                    "id": "data_reliability_score",
                    "metric_id": "data_reliability_score",
                    "metric_type": "score",
                    "unit": "score",
                    "threshold": ">= 90/100",
                    "threshold_operator": ">=",
                    "status": "pass",
                    "value": 1.0,
                    "calculation": {"aggregation": "weighted_score"},
                }],
            }],
        },
        {
            "ticker": "IMP",
            "artifacts": [{
                "plan_id": "01",
                "status": "fail",
                "metric_results": [{
                    "id": "data_reliability_score",
                    "metric_id": "data_reliability_score",
                    "metric_type": "score",
                    "unit": "score",
                    "threshold": ">= 90/100",
                    "threshold_operator": ">=",
                    "status": "fail",
                    "value": 0.956,
                    "failed_examples": [{"component": "ocr_resolution_health"}],
                    "calculation": {"aggregation": "weighted_score"},
                }],
            }],
        },
    ]

    summary = run_benchmark_suite._aggregate_summary(
        cohort_name="data_quality",
        tickers=["DHG", "IMP"],
        packets=packets,
        generated_at="2026-06-15T00:00:00+00:00",
        plan_ids=("01",),
    )
    metric = summary["artifacts"][0]["metric_results"][0]

    assert metric["value"] == 0.978
    assert metric["threshold"] == ">= 90/100"
    assert metric["status"] == "pass"
    assert metric["failed_examples"][0]["ticker"] == "IMP"


def test_benchmark_suite_hides_corpus_ocr_unresolved_rate_from_dashboard() -> None:
    packets = [
        {
            "ticker": "DHG",
            "artifacts": [{
                "plan_id": "01",
                "status": "fail",
                "metric_results": [{
                    "id": "ocr_unresolved_rate",
                    "metric_id": "ocr_unresolved_rate",
                    "metric_type": "error_rate",
                    "unit": "percent",
                    "threshold": "<= 5%",
                    "threshold_operator": "<=",
                    "status": "fail",
                    "value": 0.9444444444444444,
                    "calculation": {"aggregation": "error_rate"},
                }],
            }],
        },
        {
            "ticker": "IMP",
            "artifacts": [{
                "plan_id": "01",
                "status": "blocked",
                "metric_results": [{
                    "id": "ocr_unresolved_rate",
                    "metric_id": "ocr_unresolved_rate",
                    "metric_type": "error_rate",
                    "unit": "percent",
                    "threshold": "<= 5%",
                    "threshold_operator": "<=",
                    "status": "not_evaluable",
                    "value": None,
                    "calculation": {"aggregation": "error_rate"},
                }],
            }],
        },
    ]

    summary = run_benchmark_suite._aggregate_summary(
        cohort_name="data_quality",
        tickers=["DHG", "IMP"],
        packets=packets,
        generated_at="2026-06-15T00:00:00+00:00",
        plan_ids=("01",),
    )
    metric_ids = {metric["metric_id"] for metric in summary["artifacts"][0]["metric_results"]}

    assert "ocr_unresolved_rate" not in metric_ids


def test_benchmark_suite_period_completeness_uses_cohort_readiness_threshold() -> None:
    packets = [
        {
            "ticker": "DHG",
            "artifacts": [{
                "plan_id": "01",
                "status": "pass",
                "metric_results": [{
                    "id": "period_completeness",
                    "metric_id": "period_completeness",
                    "metric_type": "coverage",
                    "unit": "percent",
                    "threshold": "100%",
                    "threshold_operator": "=",
                    "status": "pass",
                    "value": 1.0,
                    "calculation": {"aggregation": "coverage"},
                }],
            }],
        },
        {
            "ticker": "IMP",
            "artifacts": [{
                "plan_id": "01",
                "status": "fail",
                "metric_results": [{
                    "id": "period_completeness",
                    "metric_id": "period_completeness",
                    "metric_type": "coverage",
                    "unit": "percent",
                    "threshold": "100%",
                    "threshold_operator": "=",
                    "status": "fail",
                    "value": 0.95,
                    "failed_examples": [{"period": "2021FY"}],
                    "calculation": {"aggregation": "coverage"},
                }],
            }],
        },
    ]

    summary = run_benchmark_suite._aggregate_summary(
        cohort_name="data_quality",
        tickers=["DHG", "IMP"],
        packets=packets,
        generated_at="2026-06-15T00:00:00+00:00",
        plan_ids=("01",),
    )
    metric = summary["artifacts"][0]["metric_results"][0]

    assert metric["value"] == 0.975
    assert metric["threshold"] == ">= 95%"
    assert metric["status"] == "pass"
    assert metric["blocks_publish"] is False


def test_benchmark_suite_finance_pass_count_aggregates_as_pass_rate() -> None:
    packets = [
        {
            "ticker": "DHG",
            "artifacts": [{
                "plan_id": "03",
                "status": "fail",
                "metric_results": [{
                    "id": "fcfe",
                    "metric_id": "fcfe",
                    "metric_type": "error_count",
                    "unit": "count",
                    "threshold": "pass",
                    "threshold_operator": "=",
                    "status": "pass",
                    "value": 1,
                }],
            }],
        },
        {
            "ticker": "IMP",
            "artifacts": [{
                "plan_id": "03",
                "status": "fail",
                "metric_results": [{
                    "id": "fcfe",
                    "metric_id": "fcfe",
                    "metric_type": "error_count",
                    "unit": "count",
                    "threshold": "pass",
                    "threshold_operator": "=",
                    "status": "fail",
                    "value": 0,
                }],
            }],
        },
    ]

    summary = run_benchmark_suite._aggregate_summary(
        cohort_name="financial_model_top10",
        tickers=["DHG", "IMP"],
        packets=packets,
        generated_at="2026-06-15T00:00:00+00:00",
        plan_ids=("03",),
    )
    metric = summary["artifacts"][0]["metric_results"][0]

    assert metric["value"] == 0.5
    assert metric["status"] == "fail"
    assert metric["metric_type"] == "coverage"
    assert metric["unit"] == "percent"
    assert metric["threshold"] == "= 100%"
    assert metric["calculation"]["aggregation"] == "cohort_pass_rate"
    assert metric["calculation"]["numerator"] == 1
    assert metric["calculation"]["denominator"] == 2


def test_benchmark_suite_finance_error_count_keeps_error_semantics() -> None:
    packets = [
        {
            "ticker": "DHG",
            "artifacts": [{
                "plan_id": "03",
                "status": "fail",
                "metric_results": [{
                    "id": "accounting_invariant_violations",
                    "metric_id": "accounting_invariant_violations",
                    "metric_type": "error_count",
                    "unit": "count",
                    "threshold": "= 0",
                    "threshold_operator": "=",
                    "status": "fail",
                    "value": 2,
                }],
            }],
        },
        {
            "ticker": "IMP",
            "artifacts": [{
                "plan_id": "03",
                "status": "fail",
                "metric_results": [{
                    "id": "accounting_invariant_violations",
                    "metric_id": "accounting_invariant_violations",
                    "metric_type": "error_count",
                    "unit": "count",
                    "threshold": "= 0",
                    "threshold_operator": "=",
                    "status": "fail",
                    "value": 4,
                }],
            }],
        },
    ]

    summary = run_benchmark_suite._aggregate_summary(
        cohort_name="financial_model_top10",
        tickers=["DHG", "IMP"],
        packets=packets,
        generated_at="2026-06-15T00:00:00+00:00",
        plan_ids=("03",),
    )
    metric = summary["artifacts"][0]["metric_results"][0]

    assert metric["value"] == 6
    assert metric["status"] == "fail"
    assert metric["metric_type"] == "error_count"
    assert metric["unit"] == "count"
    assert metric["calculation"]["aggregation"] == "cohort_sum"
    assert metric["calculation"]["numerator"] == 6
    assert metric["calculation"]["denominator"] == 2


def test_benchmark_suite_missing_valuation_artifact_aggregates_as_fail_rate() -> None:
    packets = [
        {
            "ticker": "DHG",
            "artifacts": [{
                "plan_id": "03",
                "status": "blocked",
                "metric_results": [{
                    "id": "valuation_artifact",
                    "metric_id": "valuation_artifact",
                    "metric_type": "error_count",
                    "unit": "count",
                    "threshold": "pass",
                    "threshold_operator": "=",
                    "status": "blocked",
                    "value": 0,
                }],
            }],
        },
        {
            "ticker": "IMP",
            "artifacts": [{
                "plan_id": "03",
                "status": "blocked",
                "metric_results": [{
                    "id": "valuation_artifact",
                    "metric_id": "valuation_artifact",
                    "metric_type": "error_count",
                    "unit": "count",
                    "threshold": "pass",
                    "threshold_operator": "=",
                    "status": "blocked",
                    "value": 0,
                }],
            }],
        },
    ]

    summary = run_benchmark_suite._aggregate_summary(
        cohort_name="financial_model_top10",
        tickers=["DHG", "IMP"],
        packets=packets,
        generated_at="2026-06-15T00:00:00+00:00",
        plan_ids=("03",),
    )
    metric = summary["artifacts"][0]["metric_results"][0]

    assert metric["value"] == 0
    assert metric["status"] == "fail"
    assert metric["metric_type"] == "coverage"
    assert metric["unit"] == "percent"
    assert metric["calculation"]["aggregation"] == "cohort_pass_rate"
    assert metric["calculation"]["numerator"] == 0
    assert metric["calculation"]["denominator"] == 2


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


def test_benchmark_suite_reuses_existing_per_ticker_artifact_for_dashboard(monkeypatch, tmp_path) -> None:
    fake_plans = [
        SimpleNamespace(id="02", name="RAG and evidence", artifact="retrieval_eval.json"),
    ]
    ticker_dir = tmp_path / "DHG"
    ticker_dir.mkdir()
    ticker_dir.joinpath("retrieval_eval.json").write_text(
        json.dumps({
            "plan_id": "02",
            "plan_name": "RAG and evidence",
            "ticker": "DHG",
            "status": "fail",
            "metrics": {"test_suite_status": "not_measured"},
            "metric_results": [{
                "id": "hit_rate_at_5",
                "metric_id": "hit_rate_at_5",
                "value": 0.9655,
                "status": "pass",
                "blocks_publish": False,
            }],
            "blocking_issues": [],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(run_benchmark_suite, "_selected_plans", lambda *args, **kwargs: fake_plans)

    packet = run_benchmark_suite._packet_from_existing_ticker(
        ticker="DHG",
        output_dir=tmp_path,
        generated_at="2026-06-16T00:00:00+00:00",
        plan_ids=("02",),
    )
    summary = run_benchmark_suite._aggregate_summary(
        cohort_name="default",
        tickers=["DHG"],
        packets=[packet],
        generated_at="2026-06-16T00:00:00+00:00",
        plan_ids=("02",),
    )

    metric = summary["artifacts"][0]["metric_results"][0]
    assert packet["reused_existing_artifacts"] is True
    assert packet["artifacts"][0]["artifact"] == "retrieval_eval.json"
    assert metric["metric_id"] == "hit_rate_at_5"
    assert metric["value"] == 0.9655
    assert metric["calculation"]["aggregation"] == "cohort_mean"
    assert metric["calculation"]["per_sample_results"][0]["artifact_id"] == "DHG/retrieval_eval.json"
    assert metric["evidence"]["artifact_ids"] == ["DHG/retrieval_eval.json"]
