"""Run the five benchmark plans across a diversified ticker cohort.

This runner exists to stop benchmarking the system through a single ticker
proxy. It executes the core benchmark plans 01, 02, 03, 05, and 07 across a
configurable cohort and writes both per-ticker packets and an aggregate suite
summary.

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
    metric_blocks_publish,
    publication_status_from_metrics,
    standard_metric,
)
from backend.evaluation.project_evaluator import (  # noqa: E402
    DEFAULT_OUTPUT_DIR,
    PLANS,
    _run_plan_tests,
    _runtime_evidence,
    _write_json,
)
from backend.evaluation.runtime_evaluators import evaluate_plan  # noqa: E402


DEFAULT_PLAN_IDS = ("01", "02", "03", "05", "07")


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

    metric_results = runtime_result.get("metrics", [])
    for metric in metric_results:
        if isinstance(metric, dict):
            metric["evaluated_at"] = generated_at

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
    }
    return order.get(str(status), 3)


def _aggregate_metric_group(metric_id: str, samples: list[dict[str, Any]], generated_at: str) -> dict[str, Any]:
    prototype = samples[0]["metric"]
    statuses = [str(sample["metric"].get("status") or "not_evaluable") for sample in samples]
    status = max(statuses, key=_metric_status_rank)
    numeric_values = [
        metric.get("value")
        for metric in (sample["metric"] for sample in samples)
        if isinstance(metric.get("value"), (int, float)) and not isinstance(metric.get("value"), bool)
    ]
    metric_type = str(prototype.get("metric_type") or "")
    unit = str(prototype.get("unit") or "")
    if metric_type == "error_count" or unit == "count":
        value = sum(numeric_values)
    elif len(numeric_values) == len(samples):
        value = sum(numeric_values) / len(numeric_values) if numeric_values else None
    else:
        # Cohort dashboard metrics must remain numeric even when some tickers
        # lack runtime evidence. Treat non-evaluable/failing samples as zero so
        # the aggregate value is an honest readiness/compliance rate, while the
        # failed_examples retain the exact missing-evidence reason per ticker.
        pass_equivalents = [
            1.0 if str(sample["metric"].get("status") or "") == "pass" else 0.0
            for sample in samples
        ]
        value = sum(pass_equivalents) / len(pass_equivalents) if pass_equivalents else None

    failed_examples = [
        {
            "ticker": sample["ticker"],
            "metric_id": metric_id,
            "status": sample["metric"].get("status"),
            "value": sample["metric"].get("value"),
            "detail": sample["metric"].get("detail") or "",
            "source": sample["metric"].get("source"),
            "failed_examples": sample["metric"].get("failed_examples") or [],
        }
        for sample in samples
        if str(sample["metric"].get("status") or "") in {"fail", "blocked", "not_evaluable"}
    ]
    calculation = dict(prototype.get("calculation") or {})
    calculation.update({
        "aggregation": (
            "cohort_sum"
            if metric_type == "error_count" or unit == "count"
            else ("cohort_mean" if len(numeric_values) == len(samples) else "cohort_pass_rate")
        ),
        "numerator": (
            value
            if metric_type == "error_count" or unit == "count" or len(numeric_values) == len(samples)
            else sum(1 for sample in samples if str(sample["metric"].get("status") or "") == "pass")
        ),
        "denominator": len(samples),
        "per_sample_results": [
            {
                "ticker": sample["ticker"],
                "status": sample["metric"].get("status"),
                "value": sample["metric"].get("value"),
                "detail": sample["metric"].get("detail") or "",
            }
            for sample in samples
        ],
    })
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
        "evaluated_at": generated_at,
    }
    aggregate["id"] = metric_id
    aggregate["metric_id"] = metric_id
    return aggregate


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
        statuses: list[str] = []
        blocking_issues: list[str] = []
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
            blocking_issues.extend(str(item) for item in artifact.get("blocking_issues") or [])
            for metric in artifact.get("metric_results") or []:
                if not isinstance(metric, dict):
                    continue
                metric_id = _normalize_metric_key(metric)
                if not metric_id:
                    continue
                samples_by_metric.setdefault(metric_id, []).append({
                    "ticker": ticker,
                    "metric": metric,
                })

        metric_results = [
            _aggregate_metric_group(metric_id, samples, generated_at)
            for metric_id, samples in sorted(samples_by_metric.items())
            if samples
        ]
        if plan_id == "03":
            _append_financial_dashboard_metrics(metric_results, samples_by_metric, generated_at)
        status = max(statuses or ["not_measured"], key=_metric_status_rank)
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
    args = parser.parse_args()
    plan_ids = tuple(str(plan).zfill(2) for plan in args.plans)

    tickers = resolve_benchmark_tickers(
        cohort=args.cohort,
        tickers=args.tickers if args.tickers else None,
        validate_against_universe=not bool(args.tickers),
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    packets = [
        _run_for_ticker(
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
