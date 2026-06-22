"""Run the evidence-sensitive benchmark plans across a diversified ticker cohort.

This runner exists to stop benchmarking the system through a single ticker
proxy. It executes the default dashboard benchmark plans across a configurable
cohort and writes both per-ticker packets and an aggregate suite summary.

Usage:
    python scripts/run_benchmark_suite.py
    python scripts/run_benchmark_suite.py --plans 01 02
    python scripts/run_benchmark_suite.py --cohort diversified_healthcare
    python scripts/run_benchmark_suite.py --tickers DHG IMP TRA DBD
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.evaluation.benchmark_cohorts import resolve_benchmark_tickers  # noqa: E402
from backend.evaluation.benchmark_standards import (  # noqa: E402
    STANDARD_SCHEMA_VERSION,
    evaluate_metric_threshold,
    metric_blocks_publish,
    publication_status_from_metrics,
    standard_metric,
)
from backend.evaluation.project_evaluator import (  # noqa: E402
    DEFAULT_OUTPUT_DIR,
    PLANS,
    _normalize_metric_results,
    _run_plan_tests,
    _runtime_evidence,
    _write_json,
)
from backend.evaluation.runtime_evaluators import evaluate_plan  # noqa: E402


DEFAULT_PLAN_IDS = ("01", "02", "03", "04", "05", "06", "07")
DASHBOARD_HIDDEN_METRIC_IDS = {
    "period_completeness",
    "provenance_coverage",
    "source_provenance_coverage",
    "accepted_facts_source_coverage",
    "core_metric_coverage",
    "dataframe_schema_validity",
    "material_ocr_error_count",
    "duplicate_fact_count",
    "ocr_unresolved_rate",
    "corpus_ocr_unresolved_rate",
    "official_reconciliation_rate",
    "valuation_method_data_readiness",
    "hit_rate_at_5",
    "faithfulness",
    "response_relevancy",
    "source_tier_hit_rate",
    "ndcg_at_10",
    "metadata_filter_accuracy",
    "unanswerable_abstention_accuracy",
    "evidence_span_overlap",
    "retrieval_noise_rate",
    "valuation_artifact",
    "accounting_invariant_violations",
    "fcff",
    "fcfe",
    "target_price",
    "gordon_growth",
    "net_debt",
    "formula_trace",
    "sensitivity_varies",
    "fcfe_sensitivity",
    "golden_drift_out_of_tolerance",
    "target_price_bridge_error",
    "wacc_terminal_growth_violation",
    "net_debt_reconciliation_error",
    # Plan 05 LLM-as-judge dimensions are advisory only: they require a
    # calibrated judge AND recorded per-role agent outputs, neither of which is
    # available offline. Per docs/eval/05 plan §5.5 they must not gate publish.
    # They remain computed and stored in each per-ticker agent_eval.json as
    # advisory evidence, but are dropped from the cohort dashboard so they do
    # not render as red failures against a judge that has not been run.
    "role_adherence",
    "groundedness",
    "task_completion",
    "plan_adherence",
    "critic_issue_recall",
    "tool_permission_compliance",
    "schema_validity",
    "no_unauthorized_calc",
    "artifact_manifest_compliance",
    "agent.stage_handoff_completeness",
    "agent.tool_call_success_rate",
    "agent.token_budget_adherence",
    "report.financial_analysis_depth",
    "report.forecast_rationale",
    "report.evidence_integration",
    "explanation_pdf_rendered",
    "deterministic_finance_gate",
    "publication_readiness",
    "llm_retry_rate",
    "retrieval_fallback_rate",
    "ocr_failure_rate",
    "final_ocr_error_count",
    "artifact_upload_failures",
    "pdf_render_failures",
    "cold_full_report_p95_latency",
    "render_only_p95_latency",
    "flash_memo_warm_p95_latency",
    "flash_memo_cold_retrieval_p95_latency",
    "latency_regression_ratio",
}
DASHBOARD_THRESHOLD_OVERRIDES: dict[str, dict[str, Any]] = {
    "period_completeness": {
        "threshold": ">= 95%",
        "threshold_operator": ">=",
        "severity": "P1",
        "blocks_publish": False,
        "remediation_hint": "Backfill missing required periods; cohort readiness allows small documented gaps.",
    },
    "provenance_coverage": {
        "threshold": ">= 95%",
        "threshold_operator": ">=",
        "severity": "P1",
        "blocks_publish": False,
        "remediation_hint": "Backfill source fields for accepted facts with missing provenance.",
    },
    "accepted_facts_source_coverage": {
        "threshold": ">= 95%",
        "threshold_operator": ">=",
        "severity": "P1",
        "blocks_publish": False,
    },
    "source_provenance_coverage": {
        "threshold": ">= 95%",
        "threshold_operator": ">=",
        "severity": "P1",
        "blocks_publish": False,
    },
    "dataframe_schema_validity": {
        "threshold": ">= 95%",
        "threshold_operator": ">=",
        "metric_type": "coverage",
        "unit": "percent",
        "severity": "P1",
        "blocks_publish": False,
    },
    "raw_bctc_non_empty": {
        "threshold": ">= 90%",
        "threshold_operator": ">=",
        "metric_type": "coverage",
        "unit": "percent",
        "severity": "P2",
        "blocks_publish": False,
    },
    "valuation_method_data_readiness": {
        "threshold": ">= 80%",
        "threshold_operator": ">=",
        "metric_type": "coverage",
        "unit": "percent",
        "severity": "P1",
        "blocks_publish": False,
        "remediation_hint": "Treat as cohort readiness, not an all-or-nothing release gate.",
    },
}


PLAN_NAMES = {plan.id: plan.name for plan in PLANS}
PLAN_ARTIFACTS = {plan.id: plan.artifact for plan in PLANS}


def _selected_plans(plan_ids: tuple[str, ...] = DEFAULT_PLAN_IDS) -> list[Any]:
    by_id = {plan.id: plan for plan in PLANS}
    plans = [by_id[plan_id] for plan_id in plan_ids if plan_id in by_id]
    if len(plans) != len(plan_ids):
        missing = [plan_id for plan_id in plan_ids if plan_id not in by_id]
        raise KeyError(f"missing benchmark plan definitions: {missing}")
    return plans


def _plan_payload(
    *,
    plan: Any,
    ticker: str,
    generated_at: str,
    test_execution: dict[str, Any],
    evidence: dict[str, Any],
    runtime_result: dict[str, Any],
) -> dict[str, Any]:
    status = runtime_result["status"]
    blocking_issues = list(runtime_result.get("blocking_issues") or [])
    if test_execution["status"] == "fail":
        status = "fail"
        blocking_issues.append("plan_test_suite_failed")

    raw_metric_results = runtime_result.get("metrics", [])
    metric_results = _normalize_metric_results(
        raw_metric_results if isinstance(raw_metric_results, list) else []
    )
    for metric in metric_results:
        if isinstance(metric, dict):
            metric["evaluated_at"] = generated_at
    blocking_issues.extend(
        f"{metric.get('id') or metric.get('metric_id')}:{metric.get('detail') or 'threshold_not_met'}"
        for metric in metric_results
        if isinstance(metric, dict) and metric_blocks_publish(metric)
    )
    status = _aggregate_artifact_status([status], metric_results)

    domain_payload = {
        key: value
        for key, value in runtime_result.items()
        if key not in {"status", "blocking_issues", "metrics"}
    }
    return {
        "schema_version": STANDARD_SCHEMA_VERSION,
        "benchmark_suite_version": "benchmark_standards_v1",
        "plan_id": plan.id,
        "plan_name": plan.name,
        "ticker": ticker,
        "generated_at": generated_at,
        "status": status,
        "test_execution": test_execution,
        "runtime_evidence_inventory": evidence,
        "blocking_issues": sorted(set(blocking_issues)),
        "metrics": {
            "test_suite_status": test_execution["status"],
            "tests_passed": test_execution.get("summary", {}).get("passed", 0),
            "tests_failed": test_execution.get("summary", {}).get("failed", 0)
            + test_execution.get("summary", {}).get("errors", 0),
        },
        "metric_results": metric_results,
        **domain_payload,
    }


def _run_for_ticker(
    *,
    ticker: str,
    output_dir: Path,
    generated_at: str,
    skip_tests: bool,
    plan_ids: tuple[str, ...] = DEFAULT_PLAN_IDS,
) -> dict[str, Any]:
    plan_records: list[dict[str, Any]] = []
    prior_results: dict[str, dict[str, Any]] = {}
    ticker_dir = output_dir / ticker
    ticker_dir.mkdir(parents=True, exist_ok=True)

    for plan in _selected_plans(plan_ids):
        test_execution = (
            {
                "status": "not_measured",
                "targets": list(plan.test_targets),
                "exit_code": None,
                "duration_seconds": 0.0,
                "summary": {},
                "output_tail": ["Skipped by --skip-tests."],
            }
            if skip_tests
            else _run_plan_tests(plan, ROOT)
        )
        evidence = _runtime_evidence(plan, ROOT, ticker_dir)
        runtime_result = evaluate_plan(
            plan.id,
            root=ROOT,
            ticker=ticker,
            test_execution=test_execution,
            prior_results=prior_results,
        )
        payload = _plan_payload(
            plan=plan,
            ticker=ticker,
            generated_at=generated_at,
            test_execution=test_execution,
            evidence=evidence,
            runtime_result=runtime_result,
        )
        _write_json(ticker_dir / plan.artifact, payload)
        prior_results[plan.id] = payload
        plan_records.append({
            "plan_id": plan.id,
            "name": plan.name,
            "artifact": plan.artifact,
            "status": payload["status"],
            "metrics": payload["metrics"],
            "metric_results": payload["metric_results"],
            "blocking_issues": payload["blocking_issues"],
        })

    all_metrics = [
        metric
        for record in plan_records
        for metric in record.get("metric_results", [])
        if isinstance(metric, dict)
    ]
    blocking = [metric for metric in all_metrics if metric_blocks_publish(metric)]
    packet = {
        "schema_version": STANDARD_SCHEMA_VERSION,
        "benchmark_suite_version": "benchmark_standards_v1",
        "source": "benchmark_suite",
        "ticker": ticker,
        "generated_at": generated_at,
        "evaluation_order": list(plan_ids),
        "fail_closed": True,
        "overall_status": "blocked" if blocking else "pass",
        "publication_status": publication_status_from_metrics(all_metrics),
        "client_final_authorized": False,
        "artifacts": plan_records,
        "summary": {
            status: sum(item["status"] == status for item in plan_records)
            for status in ("pass", "fail", "blocked", "not_measured")
        },
    }
    _write_json(ticker_dir / "evaluation_packet.json", packet)
    return packet


def _existing_plan_payload(*, ticker: str, output_dir: Path, plan: Any) -> dict[str, Any] | None:
    path = output_dir / ticker / plan.artifact
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    metric_results = payload.get("metric_results")
    if isinstance(metric_results, list):
        payload = {**payload, "metric_results": _normalize_metric_results(metric_results)}
    return payload


def _packet_from_existing_ticker(
    *,
    ticker: str,
    output_dir: Path,
    generated_at: str,
    plan_ids: tuple[str, ...] = DEFAULT_PLAN_IDS,
) -> dict[str, Any]:
    plan_records: list[dict[str, Any]] = []
    for plan in _selected_plans(plan_ids):
        payload = _existing_plan_payload(ticker=ticker, output_dir=output_dir, plan=plan)
        if payload is None:
            raise FileNotFoundError(
                f"missing existing benchmark artifact for {ticker}: {output_dir / ticker / plan.artifact}"
            )
        metric_results = payload.get("metric_results") if isinstance(payload.get("metric_results"), list) else []
        blocking_issues = payload.get("blocking_issues") if isinstance(payload.get("blocking_issues"), list) else []
        derived_blocking = [
            f"{metric.get('id') or metric.get('metric_id')}:{metric.get('detail') or 'threshold_not_met'}"
            for metric in metric_results
            if isinstance(metric, dict) and metric_blocks_publish(metric)
        ]
        plan_records.append({
            "plan_id": str(payload.get("plan_id") or plan.id),
            "name": str(payload.get("plan_name") or payload.get("name") or plan.name),
            "artifact": plan.artifact,
            "status": _aggregate_artifact_status(
                [str(payload.get("status") or "not_measured")],
                metric_results,
            ),
            "metrics": payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {},
            "metric_results": metric_results,
            "blocking_issues": sorted(set([*blocking_issues, *derived_blocking])),
        })

    all_metrics = [
        metric
        for record in plan_records
        for metric in record.get("metric_results", [])
        if isinstance(metric, dict)
    ]
    blocking = [metric for metric in all_metrics if metric_blocks_publish(metric)]
    packet = {
        "schema_version": STANDARD_SCHEMA_VERSION,
        "benchmark_suite_version": "benchmark_standards_v1",
        "source": "benchmark_suite",
        "ticker": ticker,
        "generated_at": generated_at,
        "evaluation_order": list(plan_ids),
        "fail_closed": True,
        "overall_status": "blocked" if blocking else "pass",
        "publication_status": publication_status_from_metrics(all_metrics),
        "client_final_authorized": False,
        "artifacts": plan_records,
        "summary": {
            status: sum(item["status"] == status for item in plan_records)
            for status in ("pass", "fail", "blocked", "not_measured")
        },
        "reused_existing_artifacts": True,
    }
    _write_json(output_dir / ticker / "evaluation_packet.json", packet)
    return packet


def _aggregate_summary(
    *,
    cohort_name: str,
    tickers: list[str],
    packets: list[dict[str, Any]],
    generated_at: str,
    plan_ids: tuple[str, ...] = DEFAULT_PLAN_IDS,
) -> dict[str, Any]:
    plan_stats: dict[str, dict[str, int]] = {
        plan_id: {status: 0 for status in ("pass", "fail", "blocked", "not_measured")}
        for plan_id in plan_ids
    }
    for packet in packets:
        for artifact in packet.get("artifacts") or []:
            plan_id = str(artifact.get("plan_id") or "")
            status = str(artifact.get("status") or "not_measured")
            if plan_id in plan_stats and status in plan_stats[plan_id]:
                plan_stats[plan_id][status] += 1

    artifact_records = _aggregate_artifacts(
        packets=packets,
        plan_ids=plan_ids,
        generated_at=generated_at,
    )
    all_metrics = [
        metric
        for artifact in artifact_records
        for metric in artifact.get("metric_results", [])
        if isinstance(metric, dict)
    ]
    deterministic_failures = [
        metric for metric in all_metrics if metric_blocks_publish(metric)
    ]

    return {
        "schema_version": STANDARD_SCHEMA_VERSION,
        "benchmark_suite_version": "benchmark_standards_v1",
        "source": "benchmark_suite",
        "run_id": f"benchmark-suite:{cohort_name}:{generated_at}",
        "generated_at": generated_at,
        "cohort": cohort_name,
        "tickers": tickers,
        "plan_ids": list(plan_ids),
        "fail_closed": True,
        "overall_status": "blocked" if deterministic_failures else "pass",
        "publication_status": publication_status_from_metrics(all_metrics),
        "client_final_authorized": False,
        "artifacts": artifact_records,
        "summary": {
            "tickers": len(tickers),
            "packets_written": len(packets),
        },
        "plan_stats": plan_stats,
        "packets": [
            {
                "ticker": packet.get("ticker"),
                "overall_status": packet.get("overall_status"),
                "publication_status": packet.get("publication_status"),
            }
            for packet in packets
        ],
    }


def _normalize_metric_key(metric: dict[str, Any]) -> str:
    return str(metric.get("metric_id") or metric.get("id") or "")


def _metric_status_rank(status: str) -> int:
    order = {
        "fail": 5,
        "blocked": 4,
        "not_evaluable": 3,
        "warning": 2,
        "measured_only": 1,
        "pass": 0,
        "not_applicable": -1,
    }
    return order.get(str(status), 3)


def _is_runtime_pass_gate(metric: dict[str, Any]) -> bool:
    threshold = str(metric.get("threshold") or "").strip().lower()
    aggregation = str((metric.get("calculation") or {}).get("aggregation") or "").lower()
    return (
        threshold in {"pass", "= pass"}
        or aggregation in {"pass_count", "boolean_gate"}
    )


def _pass_rate_value(samples: list[dict[str, Any]]) -> tuple[float | None, int]:
    if not samples:
        return None, 0
    passed = sum(1 for sample in samples if str(sample["metric"].get("status") or "") == "pass")
    return passed / len(samples), passed


def _apply_dashboard_metric_contract(metric_id: str, metric: dict[str, Any]) -> dict[str, Any]:
    override = DASHBOARD_THRESHOLD_OVERRIDES.get(metric_id)
    if override:
        metric.update(override)
        evaluated_status = evaluate_metric_threshold(
            metric,
            metric.get("value"),
            fallback_status=str(metric.get("status") or "not_evaluable"),
        )
        previous_status = str(metric.get("status") or "not_evaluable")
        metric["status"] = (
            max([previous_status, evaluated_status], key=_metric_status_rank)
            if previous_status in {"blocked", "not_evaluable"}
            else evaluated_status
        )
        metric["legacy_status"] = metric["status"]
        threshold_policy = dict(metric.get("threshold_policy") or {})
        threshold_policy["rationale"] = "Cohort dashboard readiness threshold override."
        metric["threshold_policy"] = threshold_policy
    return metric


REPORT_SCORE_THRESHOLDS = {
    "report.completeness": ("completeness", 90.0),
    "report.thesis_specificity": ("thesis_specificity", 80.0),
    "report.financial_analysis_depth": ("financial_analysis_depth", 80.0),
    "report.forecast_rationale": ("forecast_rationale", 80.0),
    "report.valuation_transparency": ("valuation_transparency", 85.0),
    "report.risk_catalyst_quality": ("risk_catalyst_quality", 80.0),
    "report.evidence_integration": ("evidence_integration", 80.0),
    "report.sensitivity_disclosure_completeness": ("sensitivity_disclosure_completeness", 90.0),
    "report.peer_industry_context_quality": ("peer_industry_context_quality", 75.0),
    "report.executive_summary_actionability": ("executive_summary_actionability", 80.0),
}

REPORT_TOTAL_WEIGHTS = {
    "completeness": 0.12,
    "thesis_specificity": 0.12,
    "financial_analysis_depth": 0.14,
    "forecast_rationale": 0.12,
    "valuation_transparency": 0.14,
    "risk_catalyst_quality": 0.10,
    "evidence_integration": 0.10,
    "peer_industry_context_quality": 0.06,
    "executive_summary_actionability": 0.05,
    "presentation_quality": 0.05,
}

OPS_LATENCY_METRICS = {
    "duration_seconds",
    "full_run_duration",
    "warm_full_report_p95_latency",
    "cold_full_report_p95_latency",
    "render_only_p95_latency",
    "flash_memo_warm_p95_latency",
    "flash_memo_cold_retrieval_p95_latency",
    "latency_regression_ratio",
}

OBSERVED_NUMERIC_METRIC_TYPES = {
    "latency_percentile",
    "score",
}

OBSERVED_NUMERIC_UNITS = {
    "minutes",
    "seconds",
    "usd",
    "score",
    "ratio",
}

MISSING_EVIDENCE_STATUSES = {"blocked", "not_evaluable", "not_measured"}


def _report_total_score(scores: dict[str, Any]) -> float | None:
    values = [scores.get(key) for key in REPORT_TOTAL_WEIGHTS]
    if any(not isinstance(value, (int, float)) for value in values):
        return None
    return round(sum(float(scores[key]) * weight for key, weight in REPORT_TOTAL_WEIGHTS.items()), 2)


def _report_sample_status_and_value(sample: dict[str, Any], source_metric_id: str | None) -> tuple[str | None, Any]:
    if source_metric_id == "report_pdf_rendered" and isinstance(sample.get("report_exists"), bool):
        return ("pass" if sample["report_exists"] else "fail"), sample["report_exists"]
    if source_metric_id == "explanation_pdf_rendered" and isinstance(sample.get("explanation_exists"), bool):
        return ("pass" if sample["explanation_exists"] else "fail"), sample["explanation_exists"]
    scores = sample.get("scores")
    if not isinstance(scores, dict):
        return None, None
    if source_metric_id in {"report.quality_total", "report_quality_score"}:
        total = _report_total_score(scores)
        return ("not_evaluable" if total is None else ("pass" if total >= 85.0 else "fail")), total
    score_key, threshold = REPORT_SCORE_THRESHOLDS.get(source_metric_id or "", (None, None))
    if score_key is None:
        return None, None
    value = scores.get(score_key)
    if not isinstance(value, (int, float)):
        return "not_evaluable", None
    return ("pass" if float(value) >= float(threshold) else "fail"), value


def _ops_sample_status_and_value(sample: dict[str, Any], source_metric_id: str | None) -> tuple[str | None, Any]:
    if isinstance(sample.get("artifact_upload_failures"), (int, float)):
        value = sample["artifact_upload_failures"]
        return ("pass" if float(value) == 0.0 else "fail"), value
    if isinstance(sample.get("pdf_render_failures"), (int, float)):
        value = sample["pdf_render_failures"]
        return ("pass" if float(value) == 0.0 else "fail"), value
    if source_metric_id == "llm_retry_rate" and isinstance(sample.get("retry_count"), (int, float)):
        value = sample["retry_count"]
        return ("pass" if float(value) == 0.0 else "fail"), value
    if source_metric_id == "retrieval_fallback_rate" and isinstance(sample.get("fallback_triggered"), bool):
        value = sample["fallback_triggered"]
        return ("fail" if value else "pass"), value
    terminal_status = str(sample.get("terminal_status") or "").lower()
    raw_status = str(sample.get("status") or "").lower()
    if not terminal_status and raw_status in {"completed", "success", "failed", "error"}:
        terminal_status = raw_status
    if terminal_status in {"failed", "error"}:
        return "fail", terminal_status
    if source_metric_id == "cost_per_report":
        for key in ("estimated_cost_usd", "cost_estimate"):
            if isinstance(sample.get(key), (int, float)):
                return "measured_only", sample[key]
    if source_metric_id in OPS_LATENCY_METRICS:
        for key in ("duration_seconds", "total_duration_seconds"):
            if isinstance(sample.get(key), (int, float)):
                return "measured_only", sample[key]
    if terminal_status:
        return "pass", None
    return None, None


def _source_sample_status_and_value(sample: dict[str, Any], source_metric_id: str | None = None) -> tuple[str | None, Any]:
    if isinstance(sample.get("component_score"), (int, float)):
        value = sample["component_score"]
        return ("pass" if float(value) >= 1.0 else "warning"), value
    report_status, report_value = _report_sample_status_and_value(sample, source_metric_id)
    if report_status is not None:
        return report_status, report_value
    ops_status, ops_value = _ops_sample_status_and_value(sample, source_metric_id)
    if ops_status is not None:
        return ops_status, ops_value
    for key in ("passed", "hit", "present", "complete", "accepted", "schema_valid", "reconciled", "in_range"):
        if isinstance(sample.get(key), bool):
            return ("pass" if sample[key] else "fail"), sample[key]
    for key in ("material_ocr_error", "is_duplicate"):
        if isinstance(sample.get(key), bool):
            return ("fail" if sample[key] else "pass"), sample[key]
    if isinstance(sample.get("generic_citations"), (int, float)):
        value = sample["generic_citations"]
        return ("pass" if float(value) == 0.0 else "fail"), value
    if isinstance(sample.get("source_mentions"), (int, float)):
        value = sample["source_mentions"]
        return ("pass" if float(value) > 0.0 else "fail"), value
    if isinstance(sample.get("financial_decision"), str):
        value = sample["financial_decision"]
        return ("pass" if value == "pass" else "fail"), value
    if "financial_decision" in sample:
        return "not_evaluable", sample.get("financial_decision")
    if source_metric_id == "schema_validity":
        status = str(sample.get("status") or "").lower()
        if status in {"pass", "fail"}:
            return status, status == "pass"
    permission = sample.get("permission")
    if isinstance(permission, dict):
        permitted = bool(permission.get("tool_id") and permission.get("agent_id"))
        return ("pass" if permitted else "fail"), permitted
    validation_status = str(sample.get("validation_status") or "").lower()
    if validation_status:
        return ("pass" if validation_status == "accepted" else "fail"), validation_status
    if sample.get("evidence_available") is False:
        return "not_evaluable", False
    return None, sample.get("value")


def _normalize_source_sample(sample: Any, source_metric_id: str | None = None) -> Any:
    if not isinstance(sample, dict):
        return sample
    normalized = dict(sample)
    inferred_status, inferred_value = _source_sample_status_and_value(normalized, source_metric_id)
    if "status" not in normalized and inferred_status is not None:
        normalized["status"] = inferred_status
    if "value" not in normalized and inferred_value is not None:
        normalized["value"] = inferred_value
    if (
        source_metric_id == "schema_validity"
        and "schema_valid" not in normalized
        and isinstance(normalized.get("value"), bool)
    ):
        normalized["schema_valid"] = normalized["value"]
    return normalized


def _normalized_source_samples_for_metric_sample(sample: dict[str, Any]) -> list[Any]:
    metric = sample["metric"]
    source_metric_id = metric.get("metric_id") or metric.get("id")
    source_samples = (metric.get("calculation") or {}).get("per_sample_results") or []
    return [
        _normalize_source_sample(item, source_metric_id=str(source_metric_id) if source_metric_id else None)
        for item in source_samples
    ]


def _nested_source_sample_value(sample: dict[str, Any], key: str) -> Any:
    for source_sample in _normalized_source_samples_for_metric_sample(sample):
        if isinstance(source_sample, dict) and source_sample.get(key) not in (None, "", [], {}):
            return source_sample.get(key)
    return None


def _nested_source_sample_flag(sample: dict[str, Any], key: str) -> bool:
    return any(
        isinstance(source_sample, dict) and source_sample.get(key) is True
        for source_sample in _normalized_source_samples_for_metric_sample(sample)
    )


def _is_applicable_source_sample(source_sample: Any, metric_id: str) -> bool:
    if not isinstance(source_sample, dict):
        return False
    status = str(source_sample.get("status") or "").lower()
    if status == "not_applicable":
        return False
    if str(source_sample.get("sample_origin") or "").lower() == "benchmark_control":
        return False
    if metric_id == "source_tier_hit_rate":
        if source_sample.get("material") is False:
            return False
        expected_tiers = source_sample.get("expected_source_tiers")
        if expected_tiers is not None and not expected_tiers:
            return False
    return True


def _source_sample_passed(source_sample: dict[str, Any], metric_id: str) -> bool:
    if metric_id == "hit_rate_at_5" and isinstance(source_sample.get("hit"), bool):
        return bool(source_sample["hit"])
    if metric_id == "source_tier_hit_rate" and isinstance(source_sample.get("source_tier_hit"), bool):
        return bool(source_sample["source_tier_hit"])
    status = str(source_sample.get("status") or "").lower()
    return status in {
        "pass",
        "supported",
        "accepted",
        "valid",
        "resolved",
        "reconciled",
        "completed",
        "success",
        "succeeded",
        "ok",
    }


def _pooled_coverage_value(
    metric_id: str,
    samples: list[dict[str, Any]],
) -> tuple[float, int, int] | None:
    applicable_metric_samples = [
        sample for sample in samples
        if str(sample["metric"].get("status") or "") != "not_applicable"
    ]
    if not applicable_metric_samples:
        return None
    source_sample_groups = [
        _normalized_source_samples_for_metric_sample(sample)
        for sample in applicable_metric_samples
    ]
    if any(not group for group in source_sample_groups):
        return None
    applicable_source_samples = [
        source_sample
        for source_samples in source_sample_groups
        for source_sample in source_samples
        if _is_applicable_source_sample(source_sample, metric_id)
    ]
    denominator = len(applicable_source_samples)
    if denominator == 0:
        return None
    numerator = sum(
        1 for source_sample in applicable_source_samples
        if isinstance(source_sample, dict) and _source_sample_passed(source_sample, metric_id)
    )
    return numerator / denominator, numerator, denominator


def _aggregate_metric_group(metric_id: str, samples: list[dict[str, Any]], generated_at: str) -> dict[str, Any]:
    prototype = samples[0]["metric"]
    statuses = [str(sample["metric"].get("status") or "not_evaluable") for sample in samples]
    status = max(statuses, key=_metric_status_rank)
    applicable_count = len(samples)
    applicable_samples = list(samples)
    numeric_values = [
        metric.get("value")
        for metric in (sample["metric"] for sample in applicable_samples)
        if isinstance(metric.get("value"), (int, float)) and not isinstance(metric.get("value"), bool)
    ]
    metric_type = str(prototype.get("metric_type") or "")
    unit = str(prototype.get("unit") or "")
    is_boolean_gate = metric_type == "boolean" or unit == "boolean"
    is_error_rate = metric_type == "error_rate"
    is_pass_gate = _is_runtime_pass_gate(prototype)
    is_observed_numeric = (
        metric_type in OBSERVED_NUMERIC_METRIC_TYPES
        or metric_id in OPS_LATENCY_METRICS
        or unit in OBSERVED_NUMERIC_UNITS
    ) and not is_pass_gate and metric_type not in {"coverage", "error_count", "error_rate"}
    is_latency_metric = metric_type == "latency_percentile" or metric_id in OPS_LATENCY_METRICS
    missing_count = sum(1 for item in statuses if item in MISSING_EVIDENCE_STATUSES or item == "not_applicable")
    failed_count = sum(1 for item in statuses if item == "fail")
    evaluable_count = sum(
        1 for item in statuses
        if item not in MISSING_EVIDENCE_STATUSES and item != "not_applicable"
    )
    all_applicable_not_evaluable = bool(applicable_samples) and all(
        str(sample["metric"].get("status") or "") == "not_evaluable"
        for sample in applicable_samples
    )
    pooled_coverage = (
        _pooled_coverage_value(metric_id, samples)
        if metric_type == "coverage" and not is_pass_gate and not is_boolean_gate
        else None
    )
    if all_applicable_not_evaluable:
        value = None
        passed_count = 0
    elif not is_pass_gate and pooled_coverage is None and not numeric_values and metric_type in {"coverage", "score"}:
        value = None
        passed_count = 0
    elif is_pass_gate:
        value, passed_count = _pass_rate_value(samples)
    elif pooled_coverage is not None:
        value = pooled_coverage[0]
    elif metric_type == "error_count" or unit == "count":
        value = sum(numeric_values)
    elif is_error_rate and numeric_values:
        value = sum(numeric_values) / len(numeric_values)
    elif is_latency_metric and numeric_values:
        value = sum(numeric_values) / len(numeric_values)
    elif metric_type == "coverage" and numeric_values:
        value = sum(numeric_values) / len(samples)
    elif is_observed_numeric and numeric_values:
        value = sum(numeric_values) / len(samples)
    elif applicable_count and len(numeric_values) == applicable_count:
        value = sum(numeric_values) / len(numeric_values) if numeric_values else None
    else:
        # Cohort dashboard metrics are full-cohort by policy: every ticker in
        # the benchmark cohort contributes to the denominator. Missing or
        # not-applicable samples remain zero so the aggregate exposes coverage
        # gaps instead of reporting a selective observed-only pass rate.
        pass_equivalents = [
            1.0 if str(sample["metric"].get("status") or "") == "pass" else 0.0
            for sample in applicable_samples
        ]
        value = sum(pass_equivalents) / len(pass_equivalents) if pass_equivalents else None
    if applicable_count == 0:
        status = "not_applicable"
    elif is_boolean_gate:
        # value is None only when every sample was not_applicable (all excluded).
        status = "not_applicable" if value is None else ("pass" if value == 1.0 else "fail")
    elif all_applicable_not_evaluable:
        status = "not_evaluable"
    elif is_pass_gate:
        status = "not_applicable" if value is None else ("pass" if value == 1.0 else "fail")
    else:
        status = evaluate_metric_threshold(prototype, value, fallback_status=status)
    sample_status = max(
        [item for item in statuses if item in {"blocked", "not_evaluable"}] or ["not_applicable"],
        key=_metric_status_rank,
    )
    status = max([status, sample_status], key=_metric_status_rank)

    failed_examples = [
        {
            "ticker": sample["ticker"],
            "artifact_id": sample.get("artifact_id"),
            "metric_id": metric_id,
            "status": sample["metric"].get("status"),
            "value": sample["metric"].get("value"),
            "detail": sample["metric"].get("detail") or "",
            "source": sample["metric"].get("source"),
            "failed_examples": sample["metric"].get("failed_examples") or [],
        }
        for sample in samples
        if str(sample["metric"].get("status") or "") in {"fail", "blocked", "not_evaluable", "not_applicable"}
    ]
    calculation = dict(prototype.get("calculation") or {})
    if is_pass_gate:
        aggregation = "cohort_pass_rate"
        numerator = passed_count
        denominator = applicable_count
    elif pooled_coverage is not None:
        aggregation = "cohort_pooled_coverage"
        numerator = pooled_coverage[1]
        denominator = pooled_coverage[2]
    elif metric_type == "error_count" or unit == "count":
        aggregation = "cohort_sum"
        numerator = value
        denominator = applicable_count if applicable_count != len(samples) else len(samples)
    elif is_error_rate and numeric_values:
        aggregation = "cohort_mean_observed"
        numerator = sum(numeric_values)
        denominator = len(numeric_values)
    elif is_latency_metric and numeric_values:
        aggregation = "cohort_mean_observed"
        numerator = sum(numeric_values)
        denominator = len(numeric_values)
    elif metric_type == "coverage" and numeric_values:
        aggregation = "cohort_mean"
        numerator = sum(numeric_values)
        denominator = len(samples)
    elif is_observed_numeric and numeric_values:
        aggregation = "cohort_mean"
        numerator = sum(numeric_values)
        denominator = len(samples)
    elif applicable_count and len(numeric_values) == applicable_count:
        aggregation = "cohort_mean"
        numerator = sum(numeric_values)
        denominator = len(numeric_values)
    elif value is None and not is_pass_gate:
        aggregation = "not_evaluable"
        numerator = None
        denominator = applicable_count
    else:
        aggregation = "cohort_pass_rate"
        numerator = sum(
            1 for sample in applicable_samples
            if str(sample["metric"].get("status") or "") == "pass"
        )
        denominator = applicable_count
    evidence_artifact_ids = sorted({
        str(sample.get("artifact_id") or "")
        for sample in samples
        if sample.get("artifact_id")
    })
    runtime_evidence_artifact_ids = sorted({
        str(artifact_id)
        for sample in samples
        for artifact_id in (sample["metric"].get("evidence") or {}).get("artifact_ids", [])
        if artifact_id
    })
    source_metric_ids = sorted({
        str(sample["metric"].get("metric_id") or sample["metric"].get("id") or metric_id)
        for sample in samples
    })
    calculation_inputs = dict(calculation.get("inputs") or {})
    calculation_inputs.update({
        "metric_id": metric_id,
        "cohort_tickers": [sample["ticker"] for sample in samples],
        "source_artifacts": evidence_artifact_ids,
    })
    calculation_parameters = dict(calculation.get("parameters") or {})
    calculation_parameters.update({
        "source_metric_ids": source_metric_ids,
        "cohort_size": len(samples),
        "aggregation_policy": "full cohort denominator; missing or not_applicable score samples count as zero",
    })
    calculation.update({
        "aggregation": aggregation,
        "inputs": calculation_inputs,
        "parameters": calculation_parameters,
        "numerator": numerator,
        "denominator": denominator,
        "evaluable_count": evaluable_count,
        "missing_count": missing_count,
        "failed_count": failed_count,
        "value_domain": (
            "boolean_gate" if is_boolean_gate
            else "pass_gate" if is_pass_gate
            else "observed_numeric" if is_observed_numeric
            else metric_type or unit or "diagnostic"
        ),
        "per_sample_results": [
            {
                "ticker": sample["ticker"],
                "artifact_id": sample.get("artifact_id"),
                "source_metric_id": sample["metric"].get("metric_id") or sample["metric"].get("id") or metric_id,
                "status": sample["metric"].get("status"),
                "value": sample["metric"].get("value"),
                "threshold": sample["metric"].get("threshold"),
                "evaluator": sample["metric"].get("evaluator") or {},
                "detail": sample["metric"].get("detail") or "",
                "sample_size": sample["metric"].get("sample_size"),
                "failed_examples": sample["metric"].get("failed_examples") or [],
                "evidence": sample["metric"].get("evidence") or {},
                "source": sample["metric"].get("source"),
                "structured_report_quality_available": _nested_source_sample_flag(
                    sample,
                    "structured_report_quality_available",
                ),
                "evidence_support_available": _nested_source_sample_flag(
                    sample,
                    "evidence_support_available",
                ),
                "claim_ledger_path": _nested_source_sample_value(sample, "claim_ledger_path"),
                "evidence_packet_path": _nested_source_sample_value(sample, "evidence_packet_path"),
                "source_calculation": {
                    "aggregation": (sample["metric"].get("calculation") or {}).get("aggregation"),
                    "numerator": (sample["metric"].get("calculation") or {}).get("numerator"),
                    "denominator": (sample["metric"].get("calculation") or {}).get("denominator"),
                    "per_sample_count": len((sample["metric"].get("calculation") or {}).get("per_sample_results") or []),
                },
                "source_samples": _normalized_source_samples_for_metric_sample(sample),
            }
            for sample in samples
        ],
    })
    evidence = dict(prototype.get("evidence") or {})
    existing_artifact_ids = [
        str(item) for item in evidence.get("artifact_ids") or []
        if item
    ]
    evidence["artifact_ids"] = sorted(set(
        existing_artifact_ids
        + evidence_artifact_ids
        + runtime_evidence_artifact_ids
    ))
    evidence.setdefault("dataset_version", prototype.get("dataset_version"))
    evidence.setdefault("trace_url", prototype.get("trace_url"))
    aggregate = {
        **prototype,
        "value": value,
        "status": status,
        "legacy_status": status,
        "sample_size": len(samples),
        "source": "benchmark_suite",
        "detail": f"cohort_size={len(samples)}",
        "failed_examples": failed_examples[:100],
        "calculation": calculation,
        "evidence": evidence,
        "evaluated_at": generated_at,
    }
    if is_boolean_gate:
        aggregate.update({
            "metric_type": "coverage",
            "unit": "percent",
            "threshold": "= 100%",
            "threshold_operator": "=",
            "detail": f"cohort_boolean_pass_rate={calculation['numerator']}/{len(samples)}",
        })
    elif is_pass_gate:
        aggregate.update({
            "metric_type": "coverage",
            "unit": "percent",
            "threshold": "= 100%",
            "threshold_operator": "=",
            "detail": f"cohort_pass_rate={calculation['numerator']}/{applicable_count}",
        })
    aggregate["id"] = metric_id
    aggregate["metric_id"] = metric_id
    return _apply_dashboard_metric_contract(metric_id, aggregate)


def _aggregate_artifact_status(
    fallback_statuses: list[str],
    metric_results: list[dict[str, Any]],
) -> str:
    metric_statuses = [
        str(metric.get("status") or "")
        for metric in metric_results
        if isinstance(metric, dict)
    ]
    if any(status == "fail" for status in metric_statuses):
        return "fail"
    if any(status in MISSING_EVIDENCE_STATUSES for status in metric_statuses):
        return "blocked"
    if metric_statuses and all(status in {"measured_only", "warning"} for status in metric_statuses):
        return "measured_only"
    return max(fallback_statuses or ["not_measured"], key=_metric_status_rank)


def _missing_metric_sample(
    *,
    metric_id: str,
    prototype: dict[str, Any],
    ticker: str,
    artifact_id: str,
    artifact_name: str,
) -> dict[str, Any]:
    metric_type = str(prototype.get("metric_type") or "")
    unit = str(prototype.get("unit") or "")
    if metric_type == "boolean" or unit == "boolean":
        value: Any = False
    elif metric_type == "error_count" or unit == "count":
        value = 1
    else:
        value = None
    evaluator = dict(prototype.get("evaluator") or {})
    evaluator.setdefault("id", metric_id)
    evaluator["execution_status"] = "not_executed"
    return {
        "ticker": ticker,
        "artifact_id": artifact_id,
        "artifact": artifact_name,
        "metric": {
            **prototype,
            "id": metric_id,
            "metric_id": metric_id,
            "status": "not_evaluable",
            "legacy_status": "not_evaluable",
            "value": value,
            "detail": "metric_missing_for_ticker",
            "source": "missing_metric_in_artifact",
            "sample_size": 0,
            "failed_examples": [{
                "ticker": ticker,
                "reason": "metric_missing_for_ticker",
                "artifact_id": artifact_id,
            }],
            "evaluator": evaluator,
            "calculation": {
                "aggregation": "missing_metric",
                "numerator": 0,
                "denominator": 1,
                "per_sample_results": [{
                    "ticker": ticker,
                    "status": "not_evaluable",
                    "reason": "metric_missing_for_ticker",
                    "artifact_id": artifact_id,
                }],
            },
            "evidence": {
                "artifact_ids": [artifact_id],
                "evidence_available": False,
            },
        },
    }


def _metric_by_id(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        _normalize_metric_key(metric): metric
        for metric in artifact.get("metric_results") or []
        if isinstance(metric, dict) and _normalize_metric_key(metric)
    }


def _financial_count_metric(
    metric_id: str,
    metric_name: str,
    source_metric_id: str,
    samples: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    failed = [
        sample for sample in samples
        if str(sample["metric"].get("status") or "") in {"fail", "blocked", "not_evaluable"}
    ]
    value = len(failed)
    return standard_metric(
        metric_id=metric_id,
        metric_name=metric_name,
        value=value,
        threshold="0",
        status="pass" if value == 0 else "fail",
        source="benchmark_suite",
        detail=f"derived_from={source_metric_id};cohort_size={len(samples)}",
        sample_size=len(samples),
        failed_examples=[
            {
                "ticker": sample["ticker"],
                "source_metric_id": source_metric_id,
                "status": sample["metric"].get("status"),
                "value": sample["metric"].get("value"),
                "detail": sample["metric"].get("detail") or "",
                "source": sample["metric"].get("source"),
            }
            for sample in failed
        ],
        calculation={
            "aggregation": "cohort_failure_count",
            "numerator": value,
            "denominator": len(samples),
            "per_sample_results": [
                {
                    "ticker": sample["ticker"],
                    "source_metric_id": source_metric_id,
                    "status": sample["metric"].get("status"),
                    "value": sample["metric"].get("value"),
                }
                for sample in samples
            ],
        },
        evidence={"artifact_ids": [f"{sample['ticker']}/financial_eval.json" for sample in samples]},
    ) | {"evaluated_at": generated_at}


def _append_financial_dashboard_metrics(
    aggregate_metrics: list[dict[str, Any]],
    samples_by_metric: dict[str, list[dict[str, Any]]],
    generated_at: str,
) -> None:
    derived_specs = (
        ("target_price_bridge_error", "Target price bridge error", "target_price"),
        ("wacc_terminal_growth_violation", "WACC terminal growth violation", "gordon_growth"),
        ("net_debt_reconciliation_error", "Net debt reconciliation error", "net_debt"),
    )
    existing = {_normalize_metric_key(metric) for metric in aggregate_metrics}
    for metric_id, name, source_metric_id in derived_specs:
        if metric_id in existing or source_metric_id not in samples_by_metric:
            continue
        aggregate_metrics.append(
            _financial_count_metric(
                metric_id,
                name,
                source_metric_id,
                samples_by_metric[source_metric_id],
                generated_at,
            )
        )


def _aggregate_artifacts(
    *,
    packets: list[dict[str, Any]],
    plan_ids: tuple[str, ...],
    generated_at: str,
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for plan_id in plan_ids:
        samples_by_metric: dict[str, list[dict[str, Any]]] = {}
        plan_records: list[dict[str, Any]] = []
        statuses: list[str] = []
        artifact_name = PLAN_ARTIFACTS.get(plan_id, f"{plan_id}.json")
        for packet in packets:
            ticker = str(packet.get("ticker") or "")
            artifact = next(
                (
                    item for item in packet.get("artifacts") or []
                    if str(item.get("plan_id")) == plan_id
                ),
                None,
            )
            if not isinstance(artifact, dict):
                continue
            statuses.append(str(artifact.get("status") or "not_measured"))
            present_metric_ids: set[str] = set()
            for metric in artifact.get("metric_results") or []:
                if not isinstance(metric, dict):
                    continue
                metric_id = _normalize_metric_key(metric)
                if not metric_id:
                    continue
                present_metric_ids.add(metric_id)
                samples_by_metric.setdefault(metric_id, []).append({
                    "ticker": ticker,
                    "artifact_id": f"{ticker}/{artifact_name}",
                    "artifact": artifact_name,
                    "metric": metric,
                })
            plan_records.append({
                "ticker": ticker,
                "artifact_id": f"{ticker}/{artifact_name}",
                "artifact": artifact_name,
                "metric_ids": present_metric_ids,
            })

        ticker_order = {
            str(packet.get("ticker") or ""): index
            for index, packet in enumerate(packets)
        }
        for metric_id, samples in samples_by_metric.items():
            prototype = samples[0]["metric"]
            for record in plan_records:
                if metric_id in record["metric_ids"]:
                    continue
                samples.append(_missing_metric_sample(
                    metric_id=metric_id,
                    prototype=prototype,
                    ticker=record["ticker"],
                    artifact_id=record["artifact_id"],
                    artifact_name=record["artifact"],
                ))
            samples.sort(key=lambda sample: ticker_order.get(str(sample.get("ticker") or ""), len(ticker_order)))

        metric_results = [
            _aggregate_metric_group(metric_id, samples, generated_at)
            for metric_id, samples in sorted(samples_by_metric.items())
            if samples
        ]
        if plan_id == "03":
            _append_financial_dashboard_metrics(metric_results, samples_by_metric, generated_at)
        blocking_issues = [
            f"{metric.get('id') or metric.get('metric_id')}:{metric.get('detail') or 'threshold_not_met'}"
            for metric in metric_results
            if metric.get("blocks_publish") is True
            and str(metric.get("status") or "") in {"fail", "blocked", "not_evaluable"}
        ]
        status = _aggregate_artifact_status(statuses, metric_results)
        artifacts.append({
            "plan_id": plan_id,
            "name": PLAN_NAMES.get(plan_id, plan_id),
            "artifact": PLAN_ARTIFACTS.get(plan_id, f"{plan_id}.json"),
            "status": status,
            "metrics": {
                "cohort_tickers": len(packets),
                "ticker_status_counts": {
                    item: sum(status == item for status in statuses)
                    for item in ("pass", "fail", "blocked", "not_measured")
                },
            },
            "metric_results": metric_results,
            "blocking_issues": sorted(set(blocking_issues)),
        })
    return artifacts


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cohort",
        default=None,
        help="Benchmark cohort from config/benchmarks/shared/benchmark_cohorts.yaml",
    )
    parser.add_argument("--tickers", nargs="*", help="Explicit benchmark tickers; overrides --cohort")
    parser.add_argument("--plans", nargs="*", default=list(DEFAULT_PLAN_IDS), help="Plan ids to run, e.g. 01 02")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR / "benchmark_suite")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument(
        "--reuse-existing",
        action="store_true",
        help="Aggregate already-written per-ticker artifacts without re-running evaluators.",
    )
    args = parser.parse_args()
    plan_ids = tuple(str(plan).zfill(2) for plan in args.plans)

    tickers = resolve_benchmark_tickers(
        cohort=args.cohort,
        tickers=args.tickers if args.tickers else None,
        validate_against_universe=not bool(args.tickers),
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    packets = [
        _packet_from_existing_ticker(
            ticker=ticker,
            output_dir=args.output_dir,
            generated_at=generated_at,
            plan_ids=plan_ids,
        )
        if args.reuse_existing
        else _run_for_ticker(
            ticker=ticker,
            output_dir=args.output_dir,
            generated_at=generated_at,
            skip_tests=args.skip_tests,
            plan_ids=plan_ids,
        )
        for ticker in tickers
    ]
    suite = _aggregate_summary(
        cohort_name=args.cohort or "default",
        tickers=tickers,
        packets=packets,
        generated_at=generated_at,
        plan_ids=plan_ids,
    )
    for artifact in suite.get("artifacts") or []:
        artifact_name = artifact.get("artifact")
        if isinstance(artifact_name, str) and artifact_name:
            payload = {
                "schema_version": suite["schema_version"],
                "benchmark_suite_version": suite["benchmark_suite_version"],
                "source": suite["source"],
                "cohort": suite["cohort"],
                "tickers": suite["tickers"],
                "generated_at": suite["generated_at"],
                **artifact,
            }
            _write_json(args.output_dir / artifact_name, payload)
    _write_json(args.output_dir / "benchmark_suite.json", suite)
    print(json.dumps(suite, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
