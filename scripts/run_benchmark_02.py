"""Run benchmark 02 (RAG / RAGAS) for one ticker and write retrieval_eval.json.

Focused runner: executes only plan 02 (pure-live retrieval + live RAGAS) instead of the
full eight-plan suite, so a single benchmark can be refreshed cheaply.

Usage:
    python scripts/run_benchmark_02.py --ticker DBD
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_env = _ROOT / ".env"
if _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from backend.evaluation.project_evaluator import (  # noqa: E402
    DEFAULT_OUTPUT_DIR,
    PLANS,
    STANDARD_SCHEMA_VERSION,
    _run_plan_tests,
    _runtime_evidence,
    _write_json,
)
from backend.evaluation.runtime_evaluators import evaluate_plan  # noqa: E402


def _sync_evaluation_packet(payload: dict) -> None:
    """Patch the plan-02 entry in evaluation_packet.json so the dashboard (which reads
    /eval/framework -> evaluation_packet.json) reflects this fresh run without needing a
    full eight-plan re-run. No-op if the packet does not exist yet.
    """
    packet_path = DEFAULT_OUTPUT_DIR / "evaluation_packet.json"
    if not packet_path.exists():
        return
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    artifacts = packet.get("artifacts") or []
    entry = next((a for a in artifacts if a.get("artifact") == "retrieval_eval.json"), None)
    fields = {
        "plan_id": payload["plan_id"],
        "name": payload["plan_name"],
        "artifact": "retrieval_eval.json",
        "status": payload["status"],
        "metrics": payload["metrics"],
        "metric_results": payload["metric_results"],
        "blocking_issues": payload["blocking_issues"],
    }
    if entry is None:
        artifacts.append(fields)
    else:
        entry.update(fields)
    packet["artifacts"] = artifacts
    packet["summary"] = {
        status: sum(a.get("status") == status for a in artifacts)
        for status in ("pass", "fail", "blocked", "not_measured")
    }
    _write_json(packet_path, packet)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="DBD")
    parser.add_argument("--run-id")
    args = parser.parse_args()

    plan = next(p for p in PLANS if p.id == "02")
    generated_at = datetime.now(timezone.utc).isoformat()
    run_id = args.run_id or f"benchmark-02-live-{args.ticker.upper()}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"

    test_execution = _run_plan_tests(plan, _ROOT)
    evidence = _runtime_evidence(plan, _ROOT, DEFAULT_OUTPUT_DIR)
    runtime_result = evaluate_plan(
        plan.id, root=_ROOT, ticker=args.ticker.upper(),
        test_execution=test_execution, prior_results={},
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
    domain_payload = {
        k: v for k, v in runtime_result.items()
        if k not in {"status", "blocking_issues", "metrics"}
    }
    payload = {
        "schema_version": STANDARD_SCHEMA_VERSION,
        "benchmark_suite_version": "benchmark_standards_v1",
        "plan_id": plan.id,
        "plan_name": plan.name,
        "ticker": args.ticker.upper(),
        "run_id": run_id,
        "generated_at": generated_at,
        "status": status,
        "test_execution": test_execution,
        "runtime_evidence_inventory": evidence,
        "blocking_issues": sorted(set(blocking_issues)),
        "metrics": {
            "test_suite_status": test_execution["status"],
            "tests_passed": test_execution.get("summary", {}).get("passed", 0),
        },
        "metric_results": metric_results,
        **domain_payload,
    }
    _write_json(DEFAULT_OUTPUT_DIR / plan.artifact, payload)
    _sync_evaluation_packet(payload)

    summary = {m["id"]: {"value": m.get("value"), "status": m.get("status")}
               for m in metric_results if isinstance(m, dict)}
    print(json.dumps({
        "run_id": run_id, "status": status,
        "retrieval_backend": payload.get("retrieval_backend"),
        "ragas_execution": (payload.get("ragas_execution") or {}).get("execution_status"),
        "metrics": summary,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
