"""Run the financial-calculation and agent-workflow benchmark plans.

Usage:
    python scripts/run_financial_agent_benchmark.py --ticker DBD
    python scripts/run_financial_agent_benchmark.py --ticker DBD --skip-tests
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

from backend.evaluation.benchmark_standards import (  # noqa: E402
    STANDARD_SCHEMA_VERSION,
    metric_blocks_publish,
    publication_status_from_metrics,
)
from backend.evaluation.project_evaluator import (  # noqa: E402
    DEFAULT_OUTPUT_DIR,
    PLANS,
    _run_plan_tests,
    _runtime_evidence,
    _write_json,
)
from backend.evaluation.runtime_evaluators import evaluate_plan  # noqa: E402


PLAN_IDS = ("03", "05")


def _not_measured_tests(plan: Any) -> dict[str, Any]:
    return {
        "status": "not_measured",
        "targets": list(plan.test_targets),
        "exit_code": None,
        "duration_seconds": 0.0,
        "summary": {},
        "output_tail": ["Skipped by --skip-tests."],
    }


def run_benchmark(
    *,
    ticker: str,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    run_id: str | None = None,
    skip_tests: bool = False,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    run_id = run_id or f"finance-agent-benchmark-{ticker.upper()}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    by_id = {plan.id: plan for plan in PLANS}
    artifacts: list[dict[str, Any]] = []
    prior_results: dict[str, dict[str, Any]] = {}

    for plan_id in PLAN_IDS:
        plan = by_id[plan_id]
        test_execution = _not_measured_tests(plan) if skip_tests else _run_plan_tests(plan, ROOT)
        evidence = _runtime_evidence(plan, ROOT, output_dir)
        runtime_result = evaluate_plan(
            plan.id,
            root=ROOT,
            ticker=ticker.upper(),
            test_execution=test_execution,
            prior_results=prior_results,
        )
        status = runtime_result["status"]
        blocking_issues = list(runtime_result.get("blocking_issues") or [])
        if test_execution["status"] == "fail":
            status = "fail"
            blocking_issues.append("plan_test_suite_failed")
        metric_results = runtime_result.get("metrics", [])
        for metric in metric_results:
            if isinstance(metric, dict):
                metric["evaluated_at"] = generated_at
        payload = {
            "schema_version": STANDARD_SCHEMA_VERSION,
            "benchmark_suite_version": "benchmark_standards_v1",
            "plan_id": plan.id,
            "plan_name": plan.name,
            "ticker": ticker.upper(),
            "run_id": run_id,
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
            **{
                key: value
                for key, value in runtime_result.items()
                if key not in {"status", "blocking_issues", "metrics"}
            },
        }
        _write_json(output_dir / plan.artifact, payload)
        prior_results[plan.id] = payload
        artifacts.append({
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
        for artifact in artifacts
        for metric in artifact.get("metric_results", [])
        if isinstance(metric, dict)
    ]
    blocking = [metric for metric in all_metrics if metric_blocks_publish(metric)]
    packet = {
        "schema_version": STANDARD_SCHEMA_VERSION,
        "benchmark_suite_version": "benchmark_standards_v1",
        "source": "financial_agent_benchmark",
        "run_id": run_id,
        "ticker": ticker.upper(),
        "generated_at": generated_at,
        "evaluation_order": list(PLAN_IDS),
        "fail_closed": True,
        "overall_status": "blocked" if blocking else "pass",
        "publication_status": publication_status_from_metrics(all_metrics),
        "client_final_authorized": False,
        "artifacts": artifacts,
        "summary": {
            status: sum(item["status"] == status for item in artifacts)
            for status in ("pass", "fail", "blocked", "not_measured")
        },
    }
    _write_json(output_dir / "financial_agent_benchmark_packet.json", packet)
    return packet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="DBD")
    parser.add_argument("--run-id")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    packet = run_benchmark(
        ticker=args.ticker,
        output_dir=args.output_dir,
        run_id=args.run_id,
        skip_tests=args.skip_tests,
    )
    print(json.dumps(packet, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
