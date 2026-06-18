"""Shared benchmark metric contract and publication-status policy.

This module implements the normalized benchmark standard described in
``BENCHMARK_STANDARDS.md`` while preserving the legacy ``id``/``label`` fields
used by existing dashboards and tests.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


PUBLICATION_STATUSES = (
    "NOT_EVALUATED",
    "BLOCKED_BY_P0",
    "NEEDS_HUMAN_REVIEW",
    "DRAFT_PUBLISHABLE",
    "APPROVED_FOR_EXPORT",
)

STANDARD_SCHEMA_VERSION = "2.1"
BENCHMARK_SUITE_VERSION = "benchmark_standards_v1"
METRIC_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "benchmarks"
    / "shared"
    / "metric_registry_v3.yaml"
)


def _load_metric_registry() -> dict[str, Any]:
    try:
        payload = yaml.safe_load(METRIC_REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, TypeError):
        return {"version": None, "profiles": {"active": "mvp"}, "metrics": {}}
    if not isinstance(payload, dict):
        return {"metrics": {}}
    raw_metrics = payload.get("metrics") or {}
    if isinstance(raw_metrics, list):
        normalized_metrics: dict[str, dict[str, Any]] = {}
        for item in raw_metrics:
            if not isinstance(item, dict):
                continue
            metric_id = str(item.get("metric_id") or "")
            if not metric_id:
                continue
            threshold = item.get("threshold")
            operator = str(item.get("threshold_operator") or "").strip()
            policy = {
                "threshold": _format_registry_threshold(
                    operator=operator,
                    threshold=threshold,
                    unit=str(item.get("unit") or ""),
                    metric_type=str(item.get("metric_type") or ""),
                ),
                "framework": item.get("framework"),
                "formula": item.get("formula"),
                "rationale": item.get("rationale") or item.get("remediation_hint"),
            }
            normalized_metrics[metric_id] = policy
            normalized_metrics[metric_id.split(".")[-1]] = policy
        payload["metrics"] = normalized_metrics
        payload["version"] = payload.get("benchmark_suite_version") or payload.get("version")
        payload.setdefault("profiles", {"active": "v3"})
    return payload


def _format_registry_threshold(
    *,
    operator: str,
    threshold: Any,
    unit: str,
    metric_type: str,
) -> str:
    unit_key = unit.strip().lower()
    metric_type_key = metric_type.strip().lower()
    if isinstance(threshold, bool):
        return f"{operator} {str(threshold).lower()}".strip()
    if threshold is None:
        return operator.strip()
    if unit_key == "percent" or (metric_type_key == "score" and unit_key == "score"):
        try:
            numeric = float(threshold)
        except (TypeError, ValueError):
            return f"{operator} {threshold}".strip()
        percent_value = numeric * 100 if abs(numeric) <= 1 else numeric
        return f"{operator} {_format_compact_number(percent_value)}%".strip()
    return f"{operator} {threshold}".strip()


def _format_compact_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


METRIC_REGISTRY = _load_metric_registry()


def metric_policy(metric_id: str) -> dict[str, Any]:
    metrics = METRIC_REGISTRY.get("metrics") or {}
    policy = metrics.get(metric_id) if isinstance(metrics, dict) else None
    return dict(policy) if isinstance(policy, dict) else {}


def metric_registry_version() -> Any:
    return METRIC_REGISTRY.get("version")


@dataclass(frozen=True)
class MetricMetadata:
    category: str
    layer: str
    metric_type: str
    scope: str
    severity: str
    blocks_publish: bool
    unit: str
    owner: str
    remediation_hint: str


PLAN_DEFAULTS: dict[str, MetricMetadata] = {
    "01": MetricMetadata(
        "data_quality",
        "release_gate",
        "coverage",
        "report_run",
        "P0",
        True,
        "percent",
        "data",
        "Inspect source provenance, period coverage, OCR promotion, and canonical fact deduplication.",
    ),
    "02": MetricMetadata(
        "rag",
        "diagnostic",
        "score",
        "benchmark_suite",
        "P2",
        False,
        "score",
        "retrieval",
        "Tune chunking, retrieval ranking, source-tier preferences, or the golden query set.",
    ),
    "03": MetricMetadata(
        "financial_model",
        "release_gate",
        "error_count",
        "report_run",
        "P0",
        True,
        "count",
        "valuation",
        "Recompute formula traces, valuation bridge, share count, and recommendation policy with deterministic code.",
    ),
    "04": MetricMetadata(
        "citation",
        "release_gate",
        "coverage",
        "report_run",
        "P0",
        True,
        "percent",
        "report",
        "Repair claim-level citation mapping, source IDs, source tiers, and numeric evidence reconciliation.",
    ),
    "05": MetricMetadata(
        "agent_llm",
        "diagnostic",
        "score",
        "report_run",
        "P2",
        False,
        "score",
        "platform",
        "Review agent traces, tool permissions, schema validation, and calibrated judge results.",
    ),
    "06": MetricMetadata(
        "report_quality",
        "release_gate",
        "score",
        "report_run",
        "P1",
        True,
        "score",
        "reviewer",
        "Improve required sections, forecast rationale, valuation transparency, and presentation quality.",
    ),
    "06B": MetricMetadata(
        "report_quality",
        "release_gate",
        "boolean",
        "report_run",
        "P0",
        True,
        "boolean",
        "reviewer",
        "Complete final approval, lock publishable artifacts, and align package validation with snapshot IDs.",
    ),
    "07": MetricMetadata(
        "operations",
        "observability",
        "error_rate",
        "system_window",
        "P3",
        False,
        "percent",
        "platform",
        "Inspect runtime traces, retry policy, fallback rates, artifact upload, and render telemetry.",
    ),
    "08": MetricMetadata(
        "operations",
        "observability",
        "boolean",
        "benchmark_suite",
        "P3",
        False,
        "boolean",
        "platform",
        "Update CI scope, rollout gates, and benchmark execution coverage.",
    ),
}


METRIC_OVERRIDES: dict[str, MetricMetadata] = {
    "data_quality_gate": PLAN_DEFAULTS["01"],
    "data_reliability_score": MetricMetadata(
        "data_quality", "release_gate", "score", "report_run", "P0", True,
        "score", "data", "Inspect weighted data reliability components and repair the weakest measured gate.",
    ),
    "snapshot_id": MetricMetadata(
        "data_quality", "release_gate", "boolean", "report_run", "P0", True,
        "boolean", "data", "Create or attach an immutable snapshot before evaluation.",
    ),
    "required_periods_completeness": PLAN_DEFAULTS["01"],
    "accepted_facts_source_coverage": PLAN_DEFAULTS["01"],
    "core_metric_coverage": PLAN_DEFAULTS["01"],
    "period_completeness": PLAN_DEFAULTS["01"],
    "provenance_coverage": PLAN_DEFAULTS["01"],
    "source_provenance_coverage": PLAN_DEFAULTS["01"],
    "official_reconciliation_rate": PLAN_DEFAULTS["01"],
    "material_ocr_error_count": MetricMetadata(
        "data_quality", "release_gate", "error_count", "report_run", "P0", True,
        "count", "data", "Resolve OCR errors that affect material numbers used in the report.",
    ),
    "ocr_unresolved_rate": MetricMetadata(
        "data_quality", "diagnostic", "error_rate", "benchmark_suite", "P2", False,
        "percent", "data", "Reduce unresolved OCR corpus errors and keep material OCR errors out of final artifacts.",
    ),
    "duplicate_fact_count": MetricMetadata(
        "data_quality", "release_gate", "error_count", "report_run", "P0", True,
        "count", "data", "Deduplicate canonical facts by ticker, period, line item, and source priority.",
    ),
    "duplicate_fact_rate": MetricMetadata(
        "data_quality", "release_gate", "error_rate", "report_run", "P0", True,
        "percent", "data", "Deduplicate canonical facts by ticker, period, line item, and source priority.",
    ),
    "dataframe_schema_validity": MetricMetadata(
        "data_quality", "release_gate", "boolean", "report_run", "P0", True,
        "boolean", "data", "Repair the connector DataFrame rows reported by Pandera before normalization.",
    ),
    "raw_bctc_non_empty": MetricMetadata(
        "data_quality", "diagnostic", "boolean", "benchmark_suite", "P2", False,
        "boolean", "data", "Refresh local raw BCTC snapshots before building canonical golden facts.",
    ),
    "valuation_method_data_readiness": MetricMetadata(
        "data_quality", "release_gate", "boolean", "report_run", "P0", True,
        "boolean", "data",
        "Complete valuation input facts, Pandera schema validation, deduplication, and official reconciliation before valuation.",
    ),
    "hit_rate_at_5": MetricMetadata(
        "rag", "diagnostic", "coverage", "benchmark_suite", "P2", False,
        "percent", "retrieval", "Inspect failed golden queries and improve retrieval ranking.",
    ),
    "mrr_at_5": PLAN_DEFAULTS["02"],
    "context_precision": PLAN_DEFAULTS["02"],
    "context_recall": PLAN_DEFAULTS["02"],
    "faithfulness": PLAN_DEFAULTS["02"],
    "response_relevancy": PLAN_DEFAULTS["02"],
    "source_tier_hit_rate": MetricMetadata(
        "rag", "diagnostic", "coverage", "benchmark_suite", "P2", False,
        "percent", "retrieval", "Tune source-tier preferences so material queries retrieve priority sources.",
    ),
    "evidence_packet_completeness": MetricMetadata(
        "rag", "release_gate", "coverage", "report_run", "P0", True,
        "percent", "retrieval", "Attach source documents, citation map, and formula traces to the evidence packet.",
    ),
    "formula_trace_count": MetricMetadata(
        "financial_model", "release_gate", "error_count", "report_run", "P0", True,
        "count", "valuation", "Generate deterministic formula traces for valuation outputs.",
    ),
    "financial_analyst_gate": PLAN_DEFAULTS["03"],
    "forecast_quality_gate": PLAN_DEFAULTS["03"],
    "valuation_gate": PLAN_DEFAULTS["03"],
    "valuation_reconciliation_gate": PLAN_DEFAULTS["03"],
    "net_debt": PLAN_DEFAULTS["03"],
    "fcff": PLAN_DEFAULTS["03"],
    "fcfe": PLAN_DEFAULTS["03"],
    "target_price": PLAN_DEFAULTS["03"],
    "gordon_growth": PLAN_DEFAULTS["03"],
    "sensitivity_varies": PLAN_DEFAULTS["03"],
    "fcfe_sensitivity": PLAN_DEFAULTS["03"],
    "blend_sensitivity": PLAN_DEFAULTS["03"],
    "formula_trace": PLAN_DEFAULTS["03"],
    "valuation_artifact": PLAN_DEFAULTS["03"],
    "valuation_publishable": PLAN_DEFAULTS["03"],
    "critical_failures": PLAN_DEFAULTS["03"],
    "sensitivity_base_cell": PLAN_DEFAULTS["03"],
    "golden_drift_out_of_tolerance": PLAN_DEFAULTS["03"],
    "accounting_invariant_violations": PLAN_DEFAULTS["03"],
    "valuation_regression_failures": PLAN_DEFAULTS["03"],
    "share_count_mismatch": PLAN_DEFAULTS["03"],
    "target_price_bridge_error": PLAN_DEFAULTS["03"],
    "wacc_terminal_growth_violation": PLAN_DEFAULTS["03"],
    "net_debt_reconciliation_error": PLAN_DEFAULTS["03"],
    "unexplained_forecast_anomalies": MetricMetadata(
        "financial_model", "release_gate", "error_count", "report_run", "P1", True,
        "count", "valuation", "Add forecast explanations, catalysts, or reviewer notes for material anomalies.",
    ),
    "recommendation_inconsistency": PLAN_DEFAULTS["03"],
    "citation_gate": PLAN_DEFAULTS["04"],
    "quantitative_citation_coverage": PLAN_DEFAULTS["04"],
    "quant_citation_coverage": PLAN_DEFAULTS["04"],
    "citation_key_resolution": PLAN_DEFAULTS["04"],
    "source_id_validity": PLAN_DEFAULTS["04"],
    "official_source_coverage": PLAN_DEFAULTS["04"],
    "numeric_mismatch_rate": MetricMetadata(
        "citation", "release_gate", "error_rate", "report_run", "P0", True,
        "percent", "report", "Reconcile reported numeric claims against evidence spans and canonical facts.",
    ),
    "numeric_citation_mismatch": MetricMetadata(
        "citation", "release_gate", "error_count", "report_run", "P0", True,
        "count", "report", "Fix cited numeric values that do not match the supporting evidence.",
    ),
    "numeric_citation_mismatch_rate": MetricMetadata(
        "citation", "release_gate", "error_rate", "report_run", "P0", True,
        "percent", "report", "Reconcile cited numeric claims against their supporting evidence spans.",
    ),
    "generic_citations": MetricMetadata(
        "citation", "release_gate", "error_count", "report_run", "P0", True,
        "count", "report", "Replace generic source labels with specific source IDs and evidence spans.",
    ),
    "tier3_only_material_claims": MetricMetadata(
        "citation", "release_gate", "error_count", "report_run", "P1", True,
        "count", "report", "Add official or reputable evidence for material claims currently supported only by low-tier sources.",
    ),
    "catalyst_without_evidence": MetricMetadata(
        "citation", "release_gate", "error_count", "report_run", "P0", True,
        "count", "report", "Attach evidence spans for catalysts used in the investment thesis.",
    ),
    "tool_permission_compliance": MetricMetadata(
        "agent_llm", "release_gate", "coverage", "report_run", "P0", True,
        "percent", "platform", "Reject or repair tool calls that lack explicit permission metadata.",
    ),
    "artifact_manifest_compliance": MetricMetadata(
        "agent_llm", "release_gate", "coverage", "report_run", "P0", True,
        "percent", "platform", "Attach storage paths for facts, index, ratios, valuation, report, and evidence packet artifacts.",
    ),
    "schema_validity": MetricMetadata(
        "agent_llm", "release_gate", "coverage", "report_run", "P0", True,
        "percent", "platform", "Validate required agent outputs against JSON schemas before downstream use.",
    ),
    "no_unauthorized_calc": MetricMetadata(
        "agent_llm", "release_gate", "coverage", "report_run", "P0", True,
        "percent", "valuation", "Move financial calculations from LLM narrative into deterministic code paths.",
    ),
    "task_completion_rate": MetricMetadata(
        "agent_llm", "diagnostic", "coverage", "report_run", "P2", False,
        "percent", "platform", "Review incomplete agent trace events and retry policy.",
    ),
    "task_completion": MetricMetadata(
        "agent_llm", "diagnostic", "score", "report_run", "P2", False,
        "score", "platform", "Review incomplete agent trace events and retry policy.",
    ),
    "role_adherence": PLAN_DEFAULTS["05"],
    "groundedness": PLAN_DEFAULTS["05"],
    "plan_adherence": PLAN_DEFAULTS["05"],
    "critic_issue_recall": MetricMetadata(
        "agent_llm", "diagnostic", "coverage", "benchmark_suite", "P2", False,
        "percent", "reviewer", "Expand seeded issue fixtures and compare critic recall against expected labels.",
    ),
    "report_quality_score": PLAN_DEFAULTS["06"],
    "report_completeness": MetricMetadata(
        "report_quality", "release_gate", "coverage", "report_run", "P1", True,
        "percent", "reviewer", "Complete required report sections or mark the report as not exportable.",
    ),
    "financial_analysis_depth": MetricMetadata(
        "report_quality", "diagnostic", "score", "report_run", "P1", False,
        "score", "reviewer", "Improve ratio analysis, trend explanation, and comparable financial interpretation.",
    ),
    "forecast_rationale": MetricMetadata(
        "report_quality", "diagnostic", "score", "report_run", "P1", False,
        "score", "reviewer", "Add explicit drivers, assumptions, and evidence for the forecast.",
    ),
    "valuation_transparency": MetricMetadata(
        "report_quality", "release_gate", "score", "report_run", "P0", True,
        "score", "valuation", "Attach valuation bridge, method weights, sensitivity grid, and formula traces.",
    ),
    "report_pdf_rendered": MetricMetadata(
        "report_quality", "release_gate", "boolean", "report_run", "P0", True,
        "boolean", "report", "Render the analyst draft and client-final artifacts from a validated report model.",
    ),
    "explanation_pdf_rendered": MetricMetadata(
        "report_quality", "release_gate", "boolean", "report_run", "P0", True,
        "boolean", "report", "Render the explanation artifact from a validated report model.",
    ),
    "financial_gate_passed": PLAN_DEFAULTS["03"],
    "publication_readiness": PLAN_DEFAULTS["06B"],
    "package_validation": MetricMetadata(
        "report_quality", "release_gate", "boolean", "report_run", "P0", True,
        "boolean", "platform", "Run package validation and attach all required artifacts before export.",
    ),
    "publishable_model_locked": MetricMetadata(
        "report_quality", "release_gate", "boolean", "report_run", "P0", True,
        "boolean", "reviewer", "Lock the publishable final report model before client-final rendering.",
    ),
    "run_approved": MetricMetadata(
        "report_quality", "release_gate", "boolean", "report_run", "P1", True,
        "boolean", "reviewer", "Move the run through human approval after deterministic gates pass.",
    ),
    "final_report_approval": MetricMetadata(
        "report_quality", "release_gate", "boolean", "report_run", "P1", True,
        "boolean", "reviewer", "Record final human approval before approving client-final export.",
    ),
    "report_quality_allow_export": PLAN_DEFAULTS["06"],
    "trace_coverage": MetricMetadata(
        "operations", "observability", "coverage", "system_window", "P3", False,
        "count", "platform", "Enable runtime trace capture for latency, cost, retry, and fallback analysis.",
    ),
    "llm_fallback_rate": PLAN_DEFAULTS["07"],
    "llm_retry_rate": PLAN_DEFAULTS["07"],
    "retrieval_fallback_rate": PLAN_DEFAULTS["07"],
    "ocr_failure_rate": PLAN_DEFAULTS["07"],
    "final_ocr_error_count": MetricMetadata(
        "operations", "release_gate", "error_count", "report_run", "P0", True,
        "count", "data", "Fix OCR errors that affect final reported numbers before export.",
    ),
    "artifact_upload_failures": MetricMetadata(
        "operations", "release_gate", "error_count", "report_run", "P0", True,
        "count", "platform", "Retry or repair final artifact storage uploads before export.",
    ),
    "pdf_render_failures": MetricMetadata(
        "operations", "release_gate", "error_count", "report_run", "P0", True,
        "count", "platform", "Fix final PDF rendering failures before export.",
    ),
    "full_run_duration": MetricMetadata(
        "operations", "observability", "latency_percentile", "system_window", "P3", False,
        "seconds", "platform", "Compare p95 runtime against warm/cold baseline and inspect slow stages.",
    ),
    "warm_full_report_p95_latency": MetricMetadata(
        "operations", "observability", "latency_percentile", "system_window", "P3", False,
        "minutes", "platform", "Inspect warm full-report p95 latency regressions.",
    ),
    "cold_full_report_p95_latency": MetricMetadata(
        "operations", "observability", "latency_percentile", "system_window", "P3", False,
        "minutes", "platform", "Inspect cold full-report p95 latency and ingest/OCR bottlenecks.",
    ),
    "render_only_p95_latency": MetricMetadata(
        "operations", "release_gate", "latency_percentile", "system_window", "P1", True,
        "minutes", "platform", "Optimize render-only PDF generation and inspect final render telemetry.",
    ),
    "flash_memo_warm_p95_latency": MetricMetadata(
        "operations", "observability", "latency_percentile", "system_window", "P3", False,
        "seconds", "platform", "Inspect warm flash memo latency regressions.",
    ),
    "flash_memo_cold_retrieval_p95_latency": MetricMetadata(
        "operations", "observability", "latency_percentile", "system_window", "P3", False,
        "minutes", "platform", "Inspect retrieval/crawl bottlenecks for flash memo generation.",
    ),
    "latency_regression_ratio": MetricMetadata(
        "operations", "observability", "score", "benchmark_suite", "P3", False,
        "score", "platform", "Compare new p95 latency against the locked baseline and investigate regressions.",
    ),
    "cost_per_report": MetricMetadata(
        "operations", "observability", "score", "system_window", "P2", False,
        "usd", "platform", "Apply budget policy, cache reuse, and model routing when report cost exceeds the soft budget.",
    ),
    "cost_per_full_report": MetricMetadata(
        "operations", "observability", "score", "system_window", "P2", False,
        "usd", "platform", "Apply budget policy, cache reuse, and model routing when report cost exceeds the soft budget.",
    ),
    "ops.cost_per_full_report_usd": MetricMetadata(
        "operations", "observability", "score", "system_window", "P2", False,
        "usd", "platform", "Apply budget policy, cache reuse, and model routing when report cost exceeds the soft budget.",
    ),
    "duration_seconds": MetricMetadata(
        "operations", "observability", "latency_percentile", "system_window", "P3", False,
        "seconds", "platform", "Compare p95 runtime against warm/cold baseline and inspect slow stages.",
    ),
}


def metadata_for(metric_id: str, plan_id: str | None = None) -> MetricMetadata:
    return METRIC_OVERRIDES.get(metric_id) or PLAN_DEFAULTS.get(plan_id or "") or MetricMetadata(
        "operations",
        "diagnostic",
        "score",
        "report_run",
        "P2",
        False,
        "score",
        "platform",
        "Inspect the owning evaluator and add a domain-specific remediation hint.",
    )


def _operator_from_threshold(threshold: str) -> str:
    normalized = threshold.strip()
    for operator in (">=", "<=", "=", ">", "<"):
        if normalized.startswith(operator):
            return operator
    return "="


def _numeric_threshold_for_value(
    threshold: Any,
    *,
    unit: str = "",
    compared_value: float | None = None,
) -> float | None:
    text = str(threshold or "").strip().lower()
    if not text:
        return None
    ratio = re.search(r"([-+]?\d+(?:\.\d+)?)\s*/\s*([-+]?\d+(?:\.\d+)?)", text)
    if ratio:
        numerator = float(ratio.group(1))
        denominator = float(ratio.group(2))
        if denominator == 0:
            return None
        if compared_value is not None and abs(compared_value) > 1:
            return numerator
        return numerator / denominator
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    value = float(match.group(0))
    is_percent = "%" in text or unit == "percent"
    if is_percent and (compared_value is None or abs(compared_value) <= 1):
        return value / 100.0
    return value


def evaluate_metric_threshold(
    metric: dict[str, Any],
    value: Any,
    *,
    fallback_status: str = "not_evaluable",
) -> str:
    """Evaluate a metric value against the metric's own threshold contract."""
    if value is None:
        return "not_evaluable"
    operator = str(
        metric.get("threshold_operator")
        or _operator_from_threshold(str(metric.get("threshold") or ""))
    )
    threshold = metric.get("threshold")
    text_threshold = str(threshold or "").strip().lower()
    if isinstance(value, bool) or text_threshold in {"true", "false", "= true", "= false"}:
        if "true" in text_threshold:
            target_bool: bool | None = True
        elif "false" in text_threshold:
            target_bool = False
        else:
            target_bool = None
        if target_bool is None or operator != "=":
            return fallback_status
        return "pass" if bool(value) is target_bool else "fail"
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return fallback_status
    target = _numeric_threshold_for_value(
        threshold,
        unit=str(metric.get("unit") or ""),
        compared_value=float(value),
    )
    if target is None:
        return fallback_status
    if operator == "<=":
        return "pass" if value <= target else "fail"
    if operator == ">=":
        return "pass" if value >= target else "fail"
    if operator == "<":
        return "pass" if value < target else "fail"
    if operator == ">":
        return "pass" if value > target else "fail"
    if operator == "=":
        return "pass" if abs(float(value) - target) <= 1e-9 else "fail"
    return fallback_status


def _standard_status(status: str) -> str:
    normalized = str(status or "").lower()
    if normalized in {"pass", "passed", "ok"}:
        return "pass"
    if normalized in {"fail", "failed"}:
        return "fail"
    if normalized in {"warning", "warn"}:
        return "warning"
    if normalized in {"not_applicable", "n/a", "na"}:
        # A gate that legitimately does not apply to this case (e.g. FCFE when the
        # model produced no usable debt schedule, or a DCF target when equity value
        # is non-positive). Distinct from not_evaluable (missing evidence): it is
        # excluded from cohort denominators rather than counted as a failure.
        return "not_applicable"
    return "not_evaluable"


def standard_metric(
    *,
    metric_id: str,
    metric_name: str,
    value: Any,
    threshold: str,
    status: str,
    source: str,
    detail: str = "",
    plan_id: str | None = None,
    sample_size: int | None = None,
    failed_examples: list[Any] | None = None,
    evaluator: dict[str, Any] | None = None,
    calculation: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    artifact_id: str | None = None,
    artifact_version: str | None = None,
    dataset_version: str | None = None,
) -> dict[str, Any]:
    metadata = metadata_for(metric_id, plan_id)
    policy = metric_policy(metric_id)
    governed_threshold = str(policy.get("threshold") or threshold)
    benchmark_status = _standard_status(status)
    examples = list(failed_examples or [])
    if benchmark_status in {"fail", "not_evaluable"} and not examples:
        examples.append({
            "reason": detail or (
                "threshold_not_met" if benchmark_status == "fail" else "evaluation_evidence_missing"
            ),
            "source": source,
        })
    calculation_payload = {
        "formula": policy.get("formula"),
        "inputs": {},
        "parameters": {},
        "aggregation": None,
        "numerator": None,
        "denominator": None,
        "per_sample_results": [],
        **(calculation or {}),
    }
    evaluator_payload = {
        "id": metric_id,
        "framework": policy.get("framework") or "custom",
        "framework_version": None,
        "implementation_version": STANDARD_SCHEMA_VERSION,
        "execution_status": "executed" if value is not None else "not_executed",
        **(evaluator or {}),
    }
    evidence_payload = {
        "artifact_ids": [artifact_id] if artifact_id else [],
        "dataset_version": dataset_version,
        "trace_url": None,
        **(evidence or {}),
    }
    return {
        # Backward-compatible fields used by existing dashboard code.
        "id": metric_id,
        "label": metric_name,
        "source": source,
        "detail": detail,
        # Normalized benchmark metric contract.
        "metric_id": metric_id,
        "metric_name": metric_name,
        "category": metadata.category,
        "layer": metadata.layer,
        "metric_type": metadata.metric_type,
        "scope": metadata.scope,
        "severity": metadata.severity,
        "blocks_publish": metadata.blocks_publish,
        "value": value,
        "threshold": governed_threshold,
        "threshold_operator": _operator_from_threshold(governed_threshold),
        "unit": metadata.unit,
        "status": benchmark_status,
        "legacy_status": status,
        "sample_size": 0 if sample_size is None and value is None else (
            1 if sample_size is None else sample_size
        ),
        "artifact_id": artifact_id,
        "artifact_version": artifact_version,
        "dataset_version": dataset_version,
        "benchmark_suite_version": BENCHMARK_SUITE_VERSION,
        "metric_registry_version": METRIC_REGISTRY.get("version"),
        "owner": metadata.owner,
        "failed_examples": examples,
        "remediation_hint": metadata.remediation_hint,
        "evaluator": evaluator_payload,
        "calculation": calculation_payload,
        "threshold_policy": {
            "profile": (METRIC_REGISTRY.get("profiles") or {}).get("active", "mvp"),
            "rationale": policy.get("rationale"),
            "registry_version": METRIC_REGISTRY.get("version"),
        },
        "evidence": evidence_payload,
        "evaluated_at": None,
    }


def metric_blocks_publish(metric: dict[str, Any]) -> bool:
    return (
        metric.get("blocks_publish") is True
        and metric.get("status") in {"fail", "not_evaluable"}
    )


def metric_needs_review(metric: dict[str, Any]) -> bool:
    return (
        metric.get("blocks_publish") is True
        and metric.get("severity") == "P1"
        and metric.get("status") in {"fail", "warning", "not_evaluable"}
    )


def publication_status_from_metrics(
    metrics: list[dict[str, Any]],
    *,
    benchmark_not_run: bool = False,
    missing_required_artifacts: bool = False,
    report_quality_score: float | None = None,
    report_quality_threshold: float = 85.0,
    human_approved: bool = False,
) -> str:
    if benchmark_not_run or missing_required_artifacts:
        return "NOT_EVALUATED"
    if any(
        metric_blocks_publish(metric) and metric.get("severity") == "P0"
        for metric in metrics
    ):
        return "BLOCKED_BY_P0"
    if (
        any(metric_needs_review(metric) for metric in metrics)
        or (
            report_quality_score is not None
            and report_quality_score < report_quality_threshold
        )
    ):
        return "NEEDS_HUMAN_REVIEW"
    return "APPROVED_FOR_EXPORT" if human_approved else "DRAFT_PUBLISHABLE"
