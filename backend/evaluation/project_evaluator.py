"""Project-level evaluation harness for the eight plans in ``eval/``.

The harness evaluates repository controls and available run evidence. It never
converts a passing test suite into a passing run-specific metric: unavailable
runtime evidence remains ``not_measured`` and blocks final readiness.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.evaluation.benchmark_standards import (
    STANDARD_SCHEMA_VERSION,
    metric_blocks_publish,
    publication_status_from_metrics,
)
from backend.evaluation.runtime_evaluators import evaluate_plan

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "output" / "evaluation" / "eval_result"
SUMMARY_RE = re.compile(
    r"(?P<count>\d+)\s+(?P<kind>passed|failed|error|errors|skipped|xfailed|xpassed)"
)


@dataclass(frozen=True)
class PlanDefinition:
    id: str
    name: str
    artifact: str
    test_targets: tuple[str, ...]
    runtime_evidence: tuple[str, ...] = ()


PLANS: tuple[PlanDefinition, ...] = (
    PlanDefinition(
        "01",
        "Data reliability",
        "data_quality.json",
        (
            "tests/reconciliation",
            "tests/official_sources",
            "tests/sources",
            "tests/unit/test_data_quality.py",
            "tests/unit/test_golden_provenance_required.py",
            "tests/unit/test_ocr_promotion_gate.py",
            "tests/unit/test_ocr_reconciliation_gate.py",
            "tests/unit/test_source_provenance_gate.py",
        ),
        ("data_quality.json",),
    ),
    PlanDefinition(
        "02",
        "RAG and evidence",
        "retrieval_eval.json",
        (
            "tests/unit/test_retrieval.py",
            "tests/unit/test_citation_map.py",
            "tests/unit/test_driver_evidence.py",
            "tests/unit/test_news_relevance.py",
            "tests/citations",
        ),
        ("retrieval_eval.json", "evidence_packet.json"),
    ),
    PlanDefinition(
        "03",
        "Financial calculation",
        "financial_eval.json",
        (
            "tests/analytics",
            "tests/reconciliation",
            "tests/unit/test_dcf.py",
            "tests/unit/test_ratios.py",
            "tests/unit/test_debt_schedule.py",
            "tests/unit/test_dividend_schedule.py",
            "tests/unit/test_sensitivity.py",
            "tests/unit/test_export_gate.py",
            "tests/unit/test_valuation_workings.py",
            "tests/evaluation/test_client_final_governance.py",
        ),
        ("financial_eval.json", "valuation.json", "formula_trace.json"),
    ),
    PlanDefinition(
        "04",
        "Citation and source provenance",
        "citation_eval.json",
        (
            "tests/citations",
            "tests/evaluation/test_final_source_gates.py",
            "tests/evaluation/test_numeric_claim_gates.py",
            "tests/evaluation/test_catalyst_evidence_gates.py",
            "tests/unit/test_citation_coverage.py",
            "tests/unit/test_claim_ledger.py",
        ),
        ("citation_eval.json",),
    ),
    PlanDefinition(
        "05",
        "Agent workflow and LLM judge",
        "agent_eval.json",
        (
            "tests/harness",
            "tests/unit/test_six_agent_workflow.py",
            "tests/unit/test_tool_registry.py",
            "tests/unit/test_agent_lineage_injection.py",
            "tests/unit/test_package_validation_gate.py",
        ),
        ("agent_eval.json", "run_log.json"),
    ),
    PlanDefinition(
        "06",
        "Report quality",
        "report_eval.json",
        (
            "tests/evaluation/test_report_quality.py",
            "tests/unit/test_publication_readiness.py",
            "tests/unit/test_post_render_audit.py",
            "tests/unit/test_report_assembler.py",
            "tests/unit/test_report_export_blocks_unresolved_facts.py",
            "tests/unit/test_package_validation_gate.py",
        ),
        ("report_eval.json", "publication_readiness.json"),
    ),
    PlanDefinition(
        "07",
        "Observability, cost, and latency",
        "observability_eval.json",
        (
            "tests/unit/test_model_adapter_diagnostics.py",
            "tests/unit/test_progress_reporter.py",
            "tests/unit/test_progress_integration.py",
            "tests/unit/test_run_status_semantics.py",
        ),
        ("observability_eval.json",),
    ),
    PlanDefinition(
        "08",
        "Rollout and CI",
        "rollout_ci_eval.json",
        (
            "tests/unit/test_package_validation_gate.py",
            "tests/unit/test_publication_readiness.py",
            "tests/evaluation",
            "tests/citations",
            "tests/reconciliation",
        ),
    ),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _existing_targets(plan: PlanDefinition, root: Path) -> list[str]:
    return [target for target in plan.test_targets if (root / target).exists()]


def _parse_summary(output: str) -> dict[str, int]:
    summary: dict[str, int] = {}
    for match in SUMMARY_RE.finditer(output):
        key = match.group("kind")
        if key == "error":
            key = "errors"
        summary[key] = summary.get(key, 0) + int(match.group("count"))
    return summary


def _run_plan_tests(plan: PlanDefinition, root: Path) -> dict[str, Any]:
    targets = _existing_targets(plan, root)
    if not targets:
        return {
            "status": "not_measured",
            "targets": [],
            "exit_code": None,
            "duration_seconds": 0.0,
            "summary": {},
            "output_tail": ["No configured test targets exist."],
        }
    command = [sys.executable, "-m", "pytest", "-q", *targets]
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=root,
        env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    duration = round(time.perf_counter() - started, 3)
    combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    return {
        "status": "pass" if completed.returncode == 0 else "fail",
        "targets": targets,
        "exit_code": completed.returncode,
        "duration_seconds": duration,
        "summary": _parse_summary(combined),
        "output_tail": combined.splitlines()[-30:],
    }


def _runtime_evidence(
    plan: PlanDefinition, root: Path, excluded_output_dir: Path = DEFAULT_OUTPUT_DIR
) -> dict[str, Any]:
    excluded_output_dir = excluded_output_dir.resolve()
    search_roots = (root / "storage" / "runs", root / "output", root / "artifacts")
    found: dict[str, list[str]] = {}
    for name in plan.runtime_evidence:
        matches: list[str] = []
        for search_root in search_roots:
            if search_root.exists():
                for directory, _, filenames in os.walk(search_root):
                    if name not in filenames:
                        continue
                    path = Path(directory) / name
                    if excluded_output_dir not in path.resolve().parents:
                        matches.append(str(path.relative_to(root)))
        found[name] = sorted(set(matches))[:20]
    missing = [name for name, paths in found.items() if not paths]
    return {
        "required": list(plan.runtime_evidence),
        "found": found,
        "missing": missing,
        "status": "pass" if plan.runtime_evidence and not missing else (
            "blocked" if plan.runtime_evidence else "not_applicable"
        ),
    }


def _artifact_payload(
    plan: PlanDefinition,
    *,
    run_id: str,
    ticker: str,
    generated_at: str,
    test_execution: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    runtime_blocked = evidence["status"] == "blocked"
    status = "fail" if test_execution["status"] == "fail" else (
        "blocked" if runtime_blocked else test_execution["status"]
    )
    return {
        "schema_version": STANDARD_SCHEMA_VERSION,
        "benchmark_suite_version": "benchmark_standards_v1",
        "plan_id": plan.id,
        "plan_name": plan.name,
        "ticker": ticker,
        "run_id": run_id,
        "generated_at": generated_at,
        "status": status,
        "test_execution": test_execution,
        "runtime_evidence": evidence,
        "blocking_issues": [
            f"missing_runtime_evidence:{name}" for name in evidence.get("missing", [])
        ] + (
            ["plan_test_suite_failed"] if test_execution["status"] == "fail" else []
        ),
        "metrics": {
            "test_suite_status": test_execution["status"],
            "tests_passed": test_execution.get("summary", {}).get("passed", 0),
            "tests_failed": test_execution.get("summary", {}).get("failed", 0)
            + test_execution.get("summary", {}).get("errors", 0),
            "runtime_evidence_coverage": (
                None
                if not plan.runtime_evidence
                else (len(plan.runtime_evidence) - len(evidence["missing"]))
                / len(plan.runtime_evidence)
            ),
        },
        "measurement_note": (
            "Run-specific quality metrics are not inferred from repository tests. "
            "Missing runtime artifacts remain blocked."
        ),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


def evaluate_project(
    *,
    root: Path = ROOT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    ticker: str = "DHG",
    run_id: str | None = None,
) -> dict[str, Any]:
    generated_at = _utc_now()
    run_id = run_id or f"project-eval-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    artifacts: list[dict[str, Any]] = []
    prior_results: dict[str, dict[str, Any]] = {}
    for plan in PLANS:
        test_execution = _run_plan_tests(plan, root)
        evidence = _runtime_evidence(plan, root, output_dir)
        runtime_result = evaluate_plan(
            plan.id,
            root=root,
            ticker=ticker.upper(),
            test_execution=test_execution,
            prior_results=prior_results,
        )
        status = runtime_result["status"]
        blocking_issues = list(runtime_result.get("blocking_issues") or [])
        if test_execution["status"] == "fail":
            status = "fail"
            blocking_issues.append("plan_test_suite_failed")
        metrics = {
            "test_suite_status": test_execution["status"],
            "tests_passed": test_execution.get("summary", {}).get("passed", 0),
            "tests_failed": test_execution.get("summary", {}).get("failed", 0)
            + test_execution.get("summary", {}).get("errors", 0),
            "runtime_evidence_coverage": (
                None
                if not plan.runtime_evidence
                else (len(plan.runtime_evidence) - len(evidence["missing"]))
                / len(plan.runtime_evidence)
            ),
        }
        domain_payload = {
            key: value
            for key, value in runtime_result.items()
            if key not in {"status", "blocking_issues", "metrics"}
        }
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
            "metrics": metrics,
            "metric_results": metric_results,
            **domain_payload,
        }
        _write_json(output_dir / plan.artifact, payload)
        prior_results[plan.id] = payload
        artifacts.append(
            {
                "plan_id": plan.id,
                "name": plan.name,
                "artifact": plan.artifact,
                "status": payload["status"],
                "metrics": payload["metrics"],
                "metric_results": payload["metric_results"],
                "blocking_issues": payload["blocking_issues"],
            }
        )

    all_metrics = [
        metric
        for item in artifacts
        for metric in item.get("metric_results", [])
        if isinstance(metric, dict)
    ]
    deterministic_failures = [
        metric for metric in all_metrics if metric_blocks_publish(metric)
    ]
    explicit_p0_failure = any(
        metric_blocks_publish(metric)
        and metric.get("severity") == "P0"
        and metric.get("status") == "fail"
        for metric in all_metrics
    )
    missing_required_artifacts = any(
        metric.get("status") == "not_evaluable"
        and metric.get("layer") == "release_gate"
        for metric in all_metrics
    ) and not explicit_p0_failure
    report_score = prior_results.get("06", {}).get("score")
    publication_status = publication_status_from_metrics(
        all_metrics,
        missing_required_artifacts=missing_required_artifacts,
        report_quality_score=(
            float(report_score) if isinstance(report_score, (int, float)) else None
        ),
        human_approved=False,
    )
    manifest = {
        "schema_version": STANDARD_SCHEMA_VERSION,
        "benchmark_suite_version": "benchmark_standards_v1",
        "run_id": run_id,
        "ticker": ticker.upper(),
        "generated_at": generated_at,
        "evaluation_order": [plan.id for plan in PLANS],
        "fail_closed": True,
        "overall_status": "blocked" if deterministic_failures else "pass",
        "publication_status": publication_status,
        "client_final_authorized": False if deterministic_failures else None,
        "artifacts": artifacts,
        "summary": {
            "pass": sum(item["status"] == "pass" for item in artifacts),
            "fail": sum(item["status"] == "fail" for item in artifacts),
            "blocked": sum(item["status"] == "blocked" for item in artifacts),
            "not_measured": sum(item["status"] == "not_measured" for item in artifacts),
        },
    }
    _write_json(output_dir / "evaluation_packet.json", manifest)
    return manifest


def load_latest_evaluation(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    manifest_path = output_dir / "evaluation_packet.json"
    if not manifest_path.exists():
        return {
            "schema_version": "1.0",
            "overall_status": "not_measured",
            "fail_closed": True,
            "artifacts": [],
            "summary": {},
            "message": "No evaluation packet has been generated.",
        }
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def load_evaluation_artifact(
    artifact_name: str, output_dir: Path = DEFAULT_OUTPUT_DIR
) -> dict[str, Any] | None:
    allowed = {plan.artifact for plan in PLANS} | {"evaluation_packet.json"}
    if artifact_name not in allowed:
        return None
    path = output_dir / artifact_name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the eight project evaluation plans.")
    parser.add_argument("--ticker", default="DHG")
    parser.add_argument("--run-id")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    result = evaluate_project(
        output_dir=args.output_dir,
        ticker=args.ticker,
        run_id=args.run_id,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
