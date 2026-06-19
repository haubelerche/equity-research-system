"""Project-level evaluation harness for the eight plans in ``eval/``.

The harness evaluates repository controls and available run evidence. It never
converts a passing test suite into a passing run-specific metric: unavailable
runtime evidence remains ``not_measured`` and blocks final readiness.

Supports single-ticker mode (--ticker) and cohort mode (--cohort <name>) where
all tickers in the cohort are evaluated and results are aggregated fail-closed.
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
    evaluate_metric_threshold,
    metric_policy,
    metric_blocks_publish,
    publication_status_from_metrics,
)
from backend.evaluation.benchmark_paths import (
    BENCHMARK_COHORTS_PATH,
    BENCHMARK_CONFIG_LABEL,
    BENCHMARK_RESULTS_LABEL,
    EVALUATION_OUTPUT_ROOT,
)
from backend.evaluation.runtime_evaluators import evaluate_plan

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = EVALUATION_OUTPUT_ROOT
_COHORTS_PATH = BENCHMARK_COHORTS_PATH
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

SIDECAR_ARTIFACTS = {"publication_readiness.json"}


def _evaluation_storage_run_id() -> str:
    return (
        os.getenv("EVALUATION_STORAGE_RUN_ID")
        or os.getenv("EVAL_STORAGE_RUN_ID")
        or ""
    ).strip()


def _load_storage_json_artifact(artifact_name: str) -> dict[str, Any] | None:
    """Load production evaluation artifacts from Supabase Storage when configured.

    Railway containers should not carry local benchmark/output payloads. Production
    can set ``EVALUATION_STORAGE_RUN_ID`` to a run-scoped prefix in the private
    ``runs`` bucket, for example ``benchmark-suite-latest``. Local development
    keeps the filesystem fallback below.
    """
    run_id = _evaluation_storage_run_id()
    if not run_id:
        return None
    try:
        from backend.storage import RUNS_BUCKET, SupabaseStorageAdapter, run_artifact_key

        payload = SupabaseStorageAdapter().download_json(
            RUNS_BUCKET,
            run_artifact_key(run_id, artifact_name),
        )
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


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
        if plan.id == "06" and isinstance(runtime_result.get("publication_readiness"), dict):
            publication_payload = {
                "schema_version": STANDARD_SCHEMA_VERSION,
                "benchmark_suite_version": "benchmark_standards_v1",
                "plan_id": "06B",
                "plan_name": "Publication readiness",
                "ticker": ticker.upper(),
                "run_id": run_id,
                "generated_at": generated_at,
                "status": "pass" if runtime_result["publication_readiness"].get("passed") else "fail",
                "blocking_issues": list(
                    runtime_result["publication_readiness"].get("blocking_reasons") or []
                ),
                "checks": runtime_result["publication_readiness"].get("checks") or {},
                "metric_results": [
                    metric for metric in metric_results
                    if isinstance(metric, dict) and metric.get("id") == "publication_readiness"
                ],
            }
            _write_json(output_dir / "publication_readiness.json", publication_payload)
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
        "source": "project_audit",
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
    storage_manifest = _load_storage_json_artifact("benchmark_suite.json")
    if storage_manifest is not None:
        return storage_manifest
    storage_packet = _load_storage_json_artifact("evaluation_packet.json")
    if storage_packet is not None:
        return storage_packet

    benchmark_manifest = output_dir / "benchmark_suite" / "benchmark_suite.json"
    if benchmark_manifest.exists():
        manifest = json.loads(benchmark_manifest.read_text(encoding="utf-8"))
        return _merge_benchmark_suite_sibling_artifacts(manifest, benchmark_manifest.parent)
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


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _artifact_summary_from_payload(
    artifact_name: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    if not payload:
        return None
    plan = next((item for item in PLANS if item.artifact == artifact_name), None)
    metric_results = payload.get("metric_results")
    if not isinstance(metric_results, list):
        metric_results = []
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}
    blocking_issues = payload.get("blocking_issues")
    if not isinstance(blocking_issues, list):
        blocking_issues = []
    normalized_metric_results = _normalize_metric_results(metric_results)
    derived_blocking_issues = [
        f"{metric.get('id') or metric.get('metric_id')}:{metric.get('detail') or 'threshold_not_met'}"
        for metric in normalized_metric_results
        if isinstance(metric, dict) and metric_blocks_publish(metric)
    ]
    summary = {
        "plan_id": str(payload.get("plan_id") or (plan.id if plan else "")),
        "name": str(payload.get("name") or payload.get("plan_name") or (plan.name if plan else artifact_name)),
        "artifact": artifact_name,
        "status": _artifact_status_from_metric_results(
            str(payload.get("status") or "not_measured"),
            normalized_metric_results,
        ),
        "metrics": metrics,
        "metric_results": normalized_metric_results,
        "blocking_issues": sorted(set([*blocking_issues, *derived_blocking_issues])),
    }
    for key in ("source", "generated_at", "cohort", "tickers"):
        if key in payload:
            summary[key] = payload[key]
    return summary


def _artifact_status_from_metric_results(
    fallback_status: str,
    metric_results: list[Any],
) -> str:
    statuses = [
        str(metric.get("status") or "")
        for metric in metric_results
        if isinstance(metric, dict)
    ]
    if any(status == "fail" for status in statuses):
        return "fail"
    if any(status in {"blocked", "not_evaluable", "not_measured"} for status in statuses):
        return "blocked"
    if statuses and all(status in {"measured_only", "warning"} for status in statuses):
        return "measured_only"
    return fallback_status


def _candidate_artifact_paths(
    suite_dir: Path,
    artifact_name: str,
    manifest: dict[str, Any],
) -> list[Path]:
    paths = [suite_dir / artifact_name]
    for ticker in manifest.get("tickers") or []:
        ticker_path = suite_dir / str(ticker).upper() / artifact_name
        if ticker_path.is_file():
            paths.append(ticker_path)
    return paths


def _artifact_run_context(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    run_id = payload.get("run_id")
    generated_at = payload.get("generated_at")
    return (
        str(run_id) if isinstance(run_id, str) and run_id.strip() else None,
        str(generated_at) if isinstance(generated_at, str) and generated_at.strip() else None,
    )


def _artifact_matches_manifest_context(
    payload: dict[str, Any],
    manifest: dict[str, Any],
) -> bool:
    artifact_run_id, artifact_generated_at = _artifact_run_context(payload)
    manifest_run_id, manifest_generated_at = _artifact_run_context(manifest)
    if manifest_run_id and artifact_run_id:
        return artifact_run_id == manifest_run_id
    if manifest_generated_at and artifact_generated_at:
        return artifact_generated_at == manifest_generated_at
    return False


def _manifest_has_run_context(manifest: dict[str, Any]) -> bool:
    run_id, generated_at = _artifact_run_context(manifest)
    return bool(run_id or generated_at)


def _is_root_suite_artifact(path: Path, paths: list[Path]) -> bool:
    return bool(paths) and path == paths[0]


def _is_benchmark_suite_payload(payload: dict[str, Any]) -> bool:
    return str(payload.get("source") or "") == "benchmark_suite"


def _freshest_matching_artifact_path(
    paths: list[Path],
    manifest: dict[str, Any],
    *,
    prefer_root_suite_artifact: bool = False,
    allow_latest_suite_fallback: bool = False,
) -> Path | None:
    matching: list[tuple[Path, dict[str, Any]]] = []
    for path in paths:
        if not path.is_file():
            continue
        payload = _load_json_object(path)
        if not payload or not _artifact_matches_manifest_context(payload, manifest):
            continue
        matching.append((path, payload))
    if matching:
        if prefer_root_suite_artifact:
            for path, payload in matching:
                if _is_root_suite_artifact(path, paths) and _is_benchmark_suite_payload(payload):
                    return path
        return max((path for path, _payload in matching), key=lambda path: path.stat().st_mtime)
    if not allow_latest_suite_fallback or not paths:
        return None
    root_path = paths[0]
    if not root_path.is_file():
        return None
    root_payload = _load_json_object(root_path)
    if not root_payload or not _is_benchmark_suite_payload(root_payload):
        return None
    return root_path


def _normalize_metric_results(metrics: list[Any]) -> list[Any]:
    normalized: list[Any] = []
    for metric in metrics:
        if not isinstance(metric, dict):
            normalized.append(metric)
            continue
        metric_id = str(metric.get("metric_id") or metric.get("id") or "")
        if _is_legacy_dashboard_presentation_metric(metric):
            normalized.append(_legacy_dashboard_presentation_metric(metric))
            continue
        metric_for_threshold = _normalize_metric_threshold_contract(metric, metric_id)
        metric_for_evidence = _normalize_report_quality_evidence_contract(
            metric_for_threshold,
            metric_id,
        )
        current_status = str(metric_for_evidence.get("status") or "not_evaluable")
        if (
            current_status == "pass"
            and metric_for_evidence.get("value") in (None, "")
            and current_status != "not_applicable"
        ):
            normalized_metric = dict(metric_for_evidence)
            normalized_metric.setdefault("legacy_status", current_status)
            normalized_metric["status"] = "not_evaluable"
            normalized_metric["detail"] = normalized_metric.get("detail") or "metric_value_missing"
            evaluator = dict(normalized_metric.get("evaluator") or {})
            evaluator["execution_status"] = "not_executed"
            normalized_metric["evaluator"] = evaluator
            if not normalized_metric.get("failed_examples"):
                normalized_metric["failed_examples"] = [{
                    "reason": "metric_value_missing",
                    "source": normalized_metric.get("source"),
                }]
            normalized.append(normalized_metric)
            continue
        threshold_status = evaluate_metric_threshold(
            metric_for_evidence,
            metric_for_evidence.get("value"),
            fallback_status=current_status,
        )
        if threshold_status == current_status:
            normalized.append(metric_for_evidence)
            continue
        normalized_metric = dict(metric_for_evidence)
        normalized_metric.setdefault("legacy_status", current_status)
        normalized_metric["status"] = threshold_status
        normalized_metric["threshold_status_source"] = "benchmark_threshold_contract"
        normalized.append(normalized_metric)
    return normalized


REPORT_QUALITY_RUBRIC_METRIC_IDS = {
    "report.quality_total",
    "report_quality_score",
    "report.completeness",
    "report.thesis_specificity",
    "report.financial_analysis_depth",
    "report.forecast_rationale",
    "report.valuation_transparency",
    "report.risk_catalyst_quality",
    "report.evidence_integration",
    "report.peer_industry_context_quality",
    "report.executive_summary_actionability",
    "report.sensitivity_disclosure_completeness",
}


def _is_legacy_dashboard_presentation_metric(metric: dict[str, Any]) -> bool:
    threshold_policy = metric.get("threshold_policy")
    calculation = metric.get("calculation")
    parameters = calculation.get("parameters") if isinstance(calculation, dict) else {}
    return (
        isinstance(threshold_policy, dict)
        and threshold_policy.get("source") == "dashboard_presentation_contract"
    ) or (
        isinstance(parameters, dict)
        and parameters.get("presentation_score_policy") == "cap_passed_scores_to_85_95_band"
    )


def _legacy_dashboard_presentation_metric(metric: dict[str, Any]) -> dict[str, Any]:
    normalized_metric = dict(metric)
    normalized_metric.setdefault("legacy_status", metric.get("status"))
    normalized_metric.setdefault("legacy_value", metric.get("value"))
    normalized_metric["value"] = None
    normalized_metric["status"] = "not_evaluable"
    normalized_metric["detail"] = "legacy_presentation_score_requires_regeneration"
    normalized_metric["sample_size"] = 0
    evaluator = dict(normalized_metric.get("evaluator") or {})
    evaluator["execution_status"] = "not_executed"
    normalized_metric["evaluator"] = evaluator
    failed_examples = list(normalized_metric.get("failed_examples") or [])
    failed_examples.append({
        "reason": "legacy_presentation_score_requires_regeneration",
        "legacy_threshold": metric.get("threshold"),
        "threshold_policy": metric.get("threshold_policy"),
    })
    normalized_metric["failed_examples"] = failed_examples
    return normalized_metric


def _nested_report_quality_source_samples(sample: Any) -> list[dict[str, Any]]:
    if not isinstance(sample, dict):
        return []
    nested: list[dict[str, Any]] = []
    for item in sample.get("source_samples") or []:
        if isinstance(item, dict):
            nested.append(item)
    source_calculation = sample.get("source_calculation")
    if isinstance(source_calculation, dict):
        for item in source_calculation.get("per_sample_results") or []:
            if isinstance(item, dict):
                nested.append(item)
    return nested


def _report_quality_applicable_samples(samples: list[Any]) -> list[dict[str, Any]]:
    applicable: list[dict[str, Any]] = []
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        status = str(sample.get("status") or "").lower()
        if status == "not_applicable":
            continue
        if str(sample.get("sample_origin") or "").lower() == "benchmark_control":
            continue
        applicable.append(sample)
    return applicable


def _report_quality_structured_sample_available(sample: Any) -> bool:
    if not isinstance(sample, dict):
        return False
    if sample.get("structured_report_quality_available") is True:
        return True
    return any(
        nested.get("structured_report_quality_available") is True
        for nested in _nested_report_quality_source_samples(sample)
    )


def _report_quality_sample_value_present(sample: dict[str, Any], key: str) -> bool:
    if sample.get(key) not in (None, "", [], {}):
        return True
    return any(
        nested.get(key) not in (None, "", [], {})
        for nested in _nested_report_quality_source_samples(sample)
    )


def _normalize_report_quality_evidence_contract(
    metric: dict[str, Any],
    metric_id: str,
) -> dict[str, Any]:
    if metric_id not in REPORT_QUALITY_RUBRIC_METRIC_IDS:
        return metric
    calculation = dict(metric.get("calculation") or {})
    samples = calculation.get("per_sample_results")
    sample_list = samples if isinstance(samples, list) else []
    applicable_samples = _report_quality_applicable_samples(sample_list)
    if applicable_samples and all(
        _report_quality_structured_sample_available(sample)
        for sample in applicable_samples
    ):
        return metric
    if metric.get("detail") == "structured_report_quality_evidence_missing":
        return metric
    reason = "structured_report_quality_evidence_missing"
    normalized_metric = dict(metric)
    normalized_metric.setdefault("legacy_status", metric.get("status"))
    normalized_metric.setdefault("legacy_value", metric.get("value"))
    normalized_metric["value"] = None
    normalized_metric["status"] = "not_evaluable"
    normalized_metric["detail"] = reason
    normalized_metric["sample_size"] = 0

    claim_ledger_available = any(
        _report_quality_sample_value_present(sample, "claim_ledger_path")
        for sample in applicable_samples
    )
    evidence_packet_available = any(
        _report_quality_sample_value_present(sample, "evidence_packet_path")
        for sample in applicable_samples
    )
    missing_samples = [
        {
            "reason": reason,
            "ticker": sample.get("ticker"),
            "artifact_id": sample.get("artifact_id"),
            "source_metric_id": sample.get("source_metric_id"),
            "claim_ledger_available": _report_quality_sample_value_present(sample, "claim_ledger_path"),
            "evidence_packet_available": _report_quality_sample_value_present(sample, "evidence_packet_path"),
            "legacy_status": sample.get("status"),
            "legacy_value": sample.get("value"),
        }
        for sample in applicable_samples
        if not _report_quality_structured_sample_available(sample)
    ]
    normalized_metric["failed_examples"] = missing_samples or [{
        "reason": reason,
        "claim_ledger_available": claim_ledger_available,
        "evidence_packet_available": evidence_packet_available,
        "legacy_status": metric.get("status"),
        "legacy_value": metric.get("value"),
    }]

    evaluator = dict(normalized_metric.get("evaluator") or {})
    evaluator["execution_status"] = "not_executed"
    normalized_metric["evaluator"] = evaluator

    threshold_policy = dict(normalized_metric.get("threshold_policy") or {})
    threshold_policy["evidence_basis"] = "structured_report_quality_evaluation_required"
    normalized_metric["threshold_policy"] = threshold_policy

    if sample_list:
        calculation["per_sample_results"] = [
            {
                **sample,
                "status": "not_evaluable",
                "value": None,
                "reason": reason,
                "legacy_status": sample.get("status"),
                "legacy_value": sample.get("value"),
            }
            if isinstance(sample, dict)
            else sample
            for sample in sample_list
        ]
    calculation["numerator"] = None
    calculation["denominator"] = len(applicable_samples)
    normalized_metric["calculation"] = calculation
    return normalized_metric


def _operator_from_threshold_text(threshold: Any) -> str | None:
    if not isinstance(threshold, str):
        return None
    text = threshold.strip()
    for operator in (">=", "<=", ">", "<", "="):
        if text.startswith(operator):
            return operator
    return None


def _normalize_metric_threshold_contract(metric: dict[str, Any], metric_id: str) -> dict[str, Any]:
    if not metric_id:
        return metric
    if (metric.get("threshold_policy") or {}).get("source") == "dashboard_presentation_contract":
        return metric
    policy = metric_policy(metric_id)
    governed_threshold = policy.get("threshold")
    if not governed_threshold:
        threshold_policy = dict(metric.get("threshold_policy") or {})
        if threshold_policy.get("source"):
            return metric
        normalized_metric = dict(metric)
        threshold_policy.setdefault("source", "legacy/fallback")
        normalized_metric["threshold_policy"] = threshold_policy
        return normalized_metric
    policy_operator = policy.get("threshold_operator") or _operator_from_threshold_text(governed_threshold)
    policy_metric_type = policy.get("metric_type")
    policy_severity = policy.get("severity")
    policy_blocks_publish = policy.get("blocks_publish")
    needs_contract_update = (
        str(metric.get("threshold") or "") != str(governed_threshold)
        or (policy_operator is not None and str(metric.get("threshold_operator") or "") != policy_operator)
        or (policy_metric_type is not None and metric.get("metric_type") != policy_metric_type)
        or (policy_severity is not None and metric.get("severity") != policy_severity)
        or (policy_blocks_publish is not None and metric.get("blocks_publish") is not policy_blocks_publish)
        or (metric.get("threshold_policy") or {}).get("source") != "metric_registry_v3"
    )
    if not needs_contract_update:
        return metric
    current_threshold = metric.get("threshold")
    normalized_metric = dict(metric)
    if current_threshold not in (None, "") and str(current_threshold) != str(governed_threshold):
        normalized_metric.setdefault("legacy_threshold", current_threshold)
    normalized_metric["threshold"] = governed_threshold
    if policy_operator:
        normalized_metric["threshold_operator"] = policy_operator
    for key, value in (
        ("metric_type", policy_metric_type),
        ("severity", policy_severity),
        ("blocks_publish", policy_blocks_publish),
    ):
        if value is not None:
            normalized_metric[key] = value
    threshold_policy = dict(normalized_metric.get("threshold_policy") or {})
    if policy.get("rationale"):
        threshold_policy.setdefault("rationale", policy["rationale"])
    threshold_policy["source"] = "metric_registry_v3"
    normalized_metric["threshold_policy"] = threshold_policy
    return normalized_metric


def _normalize_artifact_summary(artifact: dict[str, Any]) -> dict[str, Any]:
    metric_results = artifact.get("metric_results")
    if not isinstance(metric_results, list):
        return artifact
    normalized_metric_results = _normalize_metric_results(metric_results)
    derived_blocking_issues = [
        f"{metric.get('id') or metric.get('metric_id')}:{metric.get('detail') or 'threshold_not_met'}"
        for metric in normalized_metric_results
        if isinstance(metric, dict) and metric_blocks_publish(metric)
    ]
    existing_blocking = artifact.get("blocking_issues")
    if not isinstance(existing_blocking, list):
        existing_blocking = []
    return {
        **artifact,
        "status": _artifact_status_from_metric_results(
            str(artifact.get("status") or "not_measured"),
            normalized_metric_results,
        ),
        "metric_results": normalized_metric_results,
        "blocking_issues": sorted(set([*existing_blocking, *derived_blocking_issues])),
    }


def _merge_benchmark_suite_sibling_artifacts(
    manifest: dict[str, Any],
    suite_dir: Path,
) -> dict[str, Any]:
    """Augment a partial suite manifest with already-written sibling artifacts.

    Focused benchmark runs may refresh only one plan and rewrite
    ``benchmark_suite.json`` with that plan. We first prefer sibling artifacts
    sharing the same benchmark run context (``run_id`` or ``generated_at``), then
    fall back to root suite artifacts that explicitly declare ``source:
    benchmark_suite`` so the dashboard remains latest-by-plan without falling
    through to ticker-local artifacts.
    """
    artifacts = [
        _normalize_artifact_summary(item) for item in manifest.get("artifacts") or []
        if isinstance(item, dict)
    ]
    existing = {
        str(item.get("artifact") or "")
        for item in artifacts
        if item.get("artifact")
    }
    additions: list[dict[str, Any]] = []
    for plan in PLANS:
        if plan.artifact in existing:
            continue
        path = _freshest_matching_artifact_path(
            _candidate_artifact_paths(suite_dir, plan.artifact, manifest),
            manifest,
            prefer_root_suite_artifact=True,
            allow_latest_suite_fallback=True,
        )
        if path is None:
            continue
        summary = _artifact_summary_from_payload(
            plan.artifact,
            _load_json_object(path),
        )
        if summary is not None:
            additions.append(summary)

    merged = {**manifest, "artifacts": [*artifacts, *additions]}
    all_metrics = [
        metric
        for artifact in merged["artifacts"]
        for metric in artifact.get("metric_results", [])
        if isinstance(metric, dict)
    ]
    if not all_metrics:
        return merged if additions else manifest
    deterministic_failures = [
        metric for metric in all_metrics if metric_blocks_publish(metric)
    ]
    merged["overall_status"] = "blocked" if deterministic_failures else (
        manifest.get("overall_status") or "pass"
    )
    merged["publication_status"] = publication_status_from_metrics(all_metrics)
    merged["client_final_authorized"] = False if deterministic_failures else manifest.get(
        "client_final_authorized",
    )
    merged["summary"] = {
        status: sum(item.get("status") == status for item in merged["artifacts"])
        for status in ("pass", "fail", "blocked", "not_measured")
    }
    plan_ids = [
        str(item.get("plan_id"))
        for item in merged["artifacts"]
        if item.get("plan_id")
    ]
    merged["plan_ids"] = list(dict.fromkeys(plan_ids))
    if "evaluation_order" in merged:
        merged["evaluation_order"] = list(dict.fromkeys(plan_ids))
    merged["merged_artifact_sources"] = {
        "runtime_results": BENCHMARK_RESULTS_LABEL,
        "benchmark_config": BENCHMARK_CONFIG_LABEL,
    }
    return merged


def load_evaluation_artifact(
    artifact_name: str, output_dir: Path = DEFAULT_OUTPUT_DIR
) -> dict[str, Any] | None:
    allowed = {plan.artifact for plan in PLANS} | SIDECAR_ARTIFACTS | {"evaluation_packet.json"}
    if artifact_name not in allowed:
        return None
    storage_payload = _load_storage_json_artifact(artifact_name)
    if storage_payload is not None:
        return _normalize_artifact_summary(storage_payload)

    benchmark_path = output_dir / "benchmark_suite" / artifact_name
    benchmark_manifest = output_dir / "benchmark_suite" / "benchmark_suite.json"
    if benchmark_manifest.exists() and artifact_name != "evaluation_packet.json":
        manifest = _load_json_object(benchmark_manifest)
        path = _freshest_matching_artifact_path(
            _candidate_artifact_paths(benchmark_manifest.parent, artifact_name, manifest),
            manifest,
            prefer_root_suite_artifact=True,
            allow_latest_suite_fallback=True,
        )
        if path is not None:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return _normalize_artifact_summary(payload) if isinstance(payload, dict) else None
        if _manifest_has_run_context(manifest):
            return None
    if benchmark_path.exists():
        payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
        return _normalize_artifact_summary(payload) if isinstance(payload, dict) else None
    path = output_dir / artifact_name
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _normalize_artifact_summary(payload) if isinstance(payload, dict) else None


def _load_cohort_config() -> dict[str, Any]:
    try:
        import yaml  # type: ignore
        return yaml.safe_load(_COHORTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _cohort_tickers(cohort_name: str) -> list[str]:
    config = _load_cohort_config()
    cohorts = config.get("cohorts", {})
    cohort = cohorts.get(cohort_name)
    if cohort is None:
        available = list(cohorts.keys())
        raise ValueError(f"Cohort '{cohort_name}' not found. Available: {available}")
    tickers = cohort.get("tickers")
    if tickers:
        return [str(t).upper() for t in tickers]
    if cohort.get("source") == "universe":
        from backend.dataset.config_io import load_universe_rows  # noqa: PLC0415
        return [
            str(r.get("ticker") or "").strip().upper()
            for r in load_universe_rows()
            if r.get("ticker")
        ]
    raise ValueError(f"Cohort '{cohort_name}' has neither 'tickers' nor 'source: universe'.")


def evaluate_cohort(
    cohort_name: str,
    *,
    root: Path = ROOT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run evaluate_project for each ticker in the cohort and aggregate fail-closed.

    Per-ticker packets are written to output_dir/by_ticker/<TICKER>/.
    The aggregate cohort packet is written to output_dir/cohort_<name>_packet.json.
    The main evaluation_packet.json is also updated to reflect the worst-case ticker
    so the frontend always has a valid packet to display.
    """
    generated_at = _utc_now()
    slug = cohort_name.replace(" ", "_").lower()
    run_id = run_id or f"cohort-{slug}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    tickers = _cohort_tickers(cohort_name)
    print(f"[cohort:{cohort_name}] tickers={tickers}", flush=True)

    by_ticker_dir = output_dir / "by_ticker"
    ticker_packets: list[dict[str, Any]] = []

    for ticker in tickers:
        ticker_out = by_ticker_dir / ticker
        ticker_out.mkdir(parents=True, exist_ok=True)
        print(f"[cohort:{cohort_name}] evaluating {ticker} …", flush=True)
        packet = evaluate_project(root=root, output_dir=ticker_out, ticker=ticker, run_id=run_id)
        ticker_packets.append(packet)

    # Fail-closed aggregate: take worst-case counts across all tickers
    def _max_status(status: str) -> int:
        return {"pass": 0, "not_measured": 1, "blocked": 2, "fail": 3}.get(status, 1)

    worst_ticker = max(ticker_packets, key=lambda p: _max_status(p.get("overall_status", "")))
    cohort_status = worst_ticker.get("overall_status", "blocked")
    cohort_publication_status = worst_ticker.get("publication_status", "NOT_EVALUATED")

    ticker_summary = {}
    for packet in ticker_packets:
        t = packet.get("ticker", "UNKNOWN")
        ticker_summary[t] = {
            "overall_status": packet.get("overall_status"),
            "publication_status": packet.get("publication_status"),
            "summary": packet.get("summary", {}),
            "blocking_issues": sorted({
                issue
                for artifact in packet.get("artifacts", [])
                for issue in (artifact.get("blocking_issues") or [])
            }),
        }

    aggregate_summary = {
        "pass": min((p.get("summary", {}).get("pass", 0) for p in ticker_packets), default=0),
        "fail": max((p.get("summary", {}).get("fail", 0) for p in ticker_packets), default=0),
        "blocked": max((p.get("summary", {}).get("blocked", 0) for p in ticker_packets), default=0),
        "not_measured": max((p.get("summary", {}).get("not_measured", 0) for p in ticker_packets), default=0),
    }

    cohort_manifest: dict[str, Any] = {
        "schema_version": STANDARD_SCHEMA_VERSION,
        "benchmark_suite_version": "benchmark_standards_v1",
        "source": "cohort_audit",
        "run_id": run_id,
        "cohort": cohort_name,
        "tickers": tickers,
        "ticker_count": len(tickers),
        "generated_at": generated_at,
        "fail_closed": True,
        "overall_status": cohort_status,
        "publication_status": cohort_publication_status,
        "aggregate_summary": aggregate_summary,
        "ticker_results": ticker_summary,
        "worst_ticker": worst_ticker.get("ticker"),
    }
    _write_json(output_dir / f"cohort_{slug}_packet.json", cohort_manifest)

    # Keep evaluation_packet.json pointing to worst-case ticker result for dashboard compatibility
    _write_json(output_dir / "evaluation_packet.json", worst_ticker)
    print(
        f"[cohort:{cohort_name}] done. status={cohort_status} worst={worst_ticker.get('ticker')}",
        flush=True,
    )
    return cohort_manifest


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run the eight project evaluation plans.")
    parser.add_argument("--ticker", default="DHG", help="Single ticker to evaluate (default: DHG)")
    parser.add_argument("--cohort", default=None, help="Cohort name from benchmark_cohorts.yaml (e.g. diversified_core)")
    parser.add_argument("--run-id")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    if args.cohort:
        result = evaluate_cohort(
            cohort_name=args.cohort,
            output_dir=args.output_dir,
            run_id=args.run_id,
        )
    else:
        result = evaluate_project(
            output_dir=args.output_dir,
            ticker=args.ticker,
            run_id=args.run_id,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
