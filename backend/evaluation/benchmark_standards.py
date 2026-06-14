"""Shared benchmark metric contract and publication-status policy.

This module implements the normalized benchmark standard described in
``BENCHMARK_STANDARDS.md`` while preserving the legacy ``id``/``label`` fields
used by existing dashboards and tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PUBLICATION_STATUSES = (
    "NOT_EVALUATED",
    "BLOCKED_BY_P0",
    "NEEDS_HUMAN_REVIEW",
    "DRAFT_PUBLISHABLE",
    "APPROVED_FOR_EXPORT",
)

STANDARD_SCHEMA_VERSION = "2.1"
BENCHMARK_SUITE_VERSION = "benchmark_standards_v1"


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
    "snapshot_id": MetricMetadata(
        "data_quality", "release_gate", "boolean", "report_run", "P0", True,
        "boolean", "data", "Create or attach an immutable snapshot before evaluation.",
    ),
    "required_periods_completeness": PLAN_DEFAULTS["01"],
    "core_metric_coverage": PLAN_DEFAULTS["01"],
    "period_completeness": PLAN_DEFAULTS["01"],
    "provenance_coverage": PLAN_DEFAULTS["01"],
    "source_provenance_coverage": PLAN_DEFAULTS["01"],
    "official_reconciliation_rate": PLAN_DEFAULTS["01"],
    "ocr_unresolved_rate": MetricMetadata(
        "data_quality", "release_gate", "error_rate", "report_run", "P0", True,
        "percent", "data", "Resolve material OCR candidates before promoting facts into the final report.",
    ),
    "duplicate_fact_rate": MetricMetadata(
        "data_quality", "release_gate", "error_rate", "report_run", "P0", True,
        "percent", "data", "Deduplicate canonical facts by ticker, period, line item, and source priority.",
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
    "critical_failures": PLAN_DEFAULTS["03"],
    "golden_drift_out_of_tolerance": PLAN_DEFAULTS["03"],
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
    "generic_citations": MetricMetadata(
        "citation", "release_gate", "error_count", "report_run", "P0", True,
        "count", "report", "Replace generic source labels with specific source IDs and evidence spans.",
    ),
    "tier3_only_material_claims": MetricMetadata(
        "citation", "release_gate", "error_count", "report_run", "P1", True,
        "count", "report", "Add official or reputable evidence for material claims currently supported only by low-tier sources.",
    ),
    "tool_permission_compliance": MetricMetadata(
        "agent_llm", "release_gate", "coverage", "report_run", "P0", True,
        "percent", "platform", "Reject or repair tool calls that lack explicit permission metadata.",
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


def _standard_status(status: str) -> str:
    normalized = str(status or "").lower()
    if normalized in {"pass", "passed", "ok"}:
        return "pass"
    if normalized in {"fail", "failed"}:
        return "fail"
    if normalized in {"warning", "warn", "measured_only"}:
        return "warning"
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
) -> dict[str, Any]:
    metadata = metadata_for(metric_id, plan_id)
    benchmark_status = _standard_status(status)
    examples = list(failed_examples or [])
    if benchmark_status in {"fail", "not_evaluable"} and detail and not examples:
        examples.append({"reason": detail, "source": source})
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
        "threshold": threshold,
        "threshold_operator": _operator_from_threshold(threshold),
        "unit": metadata.unit,
        "status": benchmark_status,
        "legacy_status": status,
        "sample_size": 1 if sample_size is None else sample_size,
        "artifact_id": None,
        "artifact_version": None,
        "dataset_version": None,
        "benchmark_suite_version": BENCHMARK_SUITE_VERSION,
        "owner": metadata.owner,
        "failed_examples": examples,
        "remediation_hint": metadata.remediation_hint,
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
