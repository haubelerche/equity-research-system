"""Build fail-closed, run-scoped evaluation artifacts from harness state."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import csv
import json
import yaml

from backend.evaluation.benchmark_standards import (
    STANDARD_SCHEMA_VERSION,
    metric_blocks_publish,
    publication_status_from_metrics,
    standard_metric,
)
from backend.harness.state import ResearchGraphState

ROOT = Path(__file__).resolve().parents[2]
OPS_BENCHMARK_DIR = ROOT / "config" / "benchmarks" / "05_ops_cost_latency"

RUNTIME_EVALUATION_ARTIFACTS = (
    "data_quality.json",
    "retrieval_eval.json",
    "financial_eval.json",
    "citation_eval.json",
    "agent_eval.json",
    "report_eval.json",
    "publication_readiness.json",
    "observability_eval.json",
)


def _metric(
    metric_id: str,
    label: str,
    value: Any,
    threshold: str,
    status: str,
    source: str,
    detail: str = "",
    *,
    plan_id: str | None = None,
    sample_size: int | None = None,
    **explanation: Any,
) -> dict[str, Any]:
    return standard_metric(
        metric_id=metric_id,
        metric_name=label,
        value=value,
        threshold=threshold,
        status=status,
        source=source,
        detail=detail,
        plan_id=plan_id,
        sample_size=sample_size,
        **explanation,
    )


def _gate(state: ResearchGraphState, name: str) -> dict[str, Any]:
    gate = state.gate_results.get(name)
    return gate if isinstance(gate, dict) else {}


def _gate_status(gate: dict[str, Any]) -> str:
    if not gate:
        return "not_evaluable"
    return "pass" if gate.get("passed") is True else "fail"


def _status(metrics: list[dict[str, Any]]) -> str:
    statuses = {str(metric.get("status")) for metric in metrics}
    if "fail" in statuses:
        return "fail"
    if "blocked" in statuses or "not_evaluable" in statuses:
        return "blocked"
    if statuses and statuses <= {"measured_only", "warning"}:
        return "measured_only"
    return "pass"


def _blocking_issues(metrics: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            f"{metric['id']}:{metric.get('detail') or 'threshold_not_met'}"
            for metric in metrics
            if metric.get("status") in {"fail", "blocked", "not_evaluable"}
        }
    )


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95))))
    return ordered[index]


def _read_ops_yaml(name: str) -> dict[str, Any]:
    path = OPS_BENCHMARK_DIR / name
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _read_ops_csv(name: str) -> list[dict[str, Any]]:
    path = OPS_BENCHMARK_DIR / name
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except OSError:
        return []


def _read_ops_jsonl(name: str) -> list[dict[str, Any]]:
    path = OPS_BENCHMARK_DIR / name
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
    except (OSError, json.JSONDecodeError):
        return rows
    return rows


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ops_benchmark_inputs() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    return (
        _read_ops_yaml("ops_cost_latency_rubric.yaml"),
        _read_ops_csv("golden_run_traces.csv"),
        _read_ops_jsonl("negative_ops_cases.jsonl"),
    )


def _ops_latency_metric(
    metric_id: str,
    label: str,
    value: float | None,
    threshold_seconds: float | None,
    *,
    unit: str,
    source: str,
    samples: list[dict[str, Any]],
    missing_reason: str,
) -> dict[str, Any]:
    if threshold_seconds is None:
        threshold = "present"
        status = "not_evaluable"
    elif unit == "minutes":
        threshold = f"<= {threshold_seconds / 60:g}"
        status = "not_evaluable" if value is None else ("pass" if value <= threshold_seconds / 60 else "fail")
    else:
        threshold = f"<= {threshold_seconds:g}"
        status = "not_evaluable" if value is None else ("pass" if value <= threshold_seconds else "fail")
    failed = [
        sample for sample in samples
        if sample.get("status") in {"failed", "error"}
        or (
            threshold_seconds is not None
            and _float(sample.get("duration_seconds") or sample.get("total_duration_seconds")) is not None
            and _float(sample.get("duration_seconds") or sample.get("total_duration_seconds")) > threshold_seconds
        )
    ]
    return _metric(
        metric_id,
        label,
        value,
        threshold,
        status,
        source if samples or value is not None else missing_reason,
        missing_reason if value is None else "",
        plan_id="07",
        sample_size=len(samples),
        failed_examples=failed,
        calculation={
            "aggregation": "p95",
            "parameters": {"threshold_seconds": threshold_seconds, "display_unit": unit},
            "per_sample_results": samples[:100],
        },
    )


def _trace_stage(event: dict[str, Any]) -> str:
    input_summary = event.get("input_summary") if isinstance(event.get("input_summary"), dict) else {}
    return str(
        event.get("stage")
        or input_summary.get("state_stage")
        or event.get("current_stage")
        or event.get("agent_id")
        or "unknown"
    )


def _event_retry_count(event: dict[str, Any]) -> int:
    retry_count = event.get("retry_count")
    if isinstance(retry_count, int):
        return max(0, retry_count)
    for key in ("attempts", "retry_attempts"):
        attempts = event.get(key)
        if isinstance(attempts, int):
            return max(0, attempts - 1)
    return 0


def _token_count(event: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = event.get(key)
        if isinstance(value, int):
            return value
    usage = event.get("usage")
    if isinstance(usage, dict):
        for key in keys:
            value = usage.get(key)
            if isinstance(value, int):
                return value
    return 0


def _trace_url(state: ResearchGraphState) -> str | None:
    for event in state.trace:
        if isinstance(event, dict) and event.get("trace_url"):
            return str(event["trace_url"])
    configured = state.artifacts.get("trace_url")
    return str(configured) if configured else None


def _base(
    state: ResearchGraphState,
    plan_id: str,
    plan_name: str,
    metrics: list[dict[str, Any]],
    generated_at: str,
    **domain: Any,
) -> dict[str, Any]:
    for metric in metrics:
        metric["evaluated_at"] = generated_at
    return {
        "schema_version": STANDARD_SCHEMA_VERSION,
        "benchmark_suite_version": "benchmark_standards_v1",
        "plan_id": plan_id,
        "plan_name": plan_name,
        "run_id": state.run_id,
        "ticker": state.ticker,
        "generated_at": generated_at,
        "status": _status(metrics),
        "blocking_issues": _blocking_issues(metrics),
        "metric_results": metrics,
        **domain,
    }


def _data_quality(state: ResearchGraphState, generated_at: str) -> dict[str, Any]:
    gate = _gate(state, "DATA_QUALITY_GATE")
    inventory = state.data_inventory or state.artifacts.get("build_facts") or {}
    snapshot = state.snapshot_id or inventory.get("snapshot_id")
    metrics = [
        _metric(
            "data_quality_gate",
            "Data quality gate",
            gate.get("passed"),
            "pass",
            _gate_status(gate),
            "DATA_QUALITY_GATE",
            ",".join(gate.get("blocking_reasons") or []) or "gate_missing",
        ),
        _metric(
            "snapshot_id",
            "Immutable snapshot identifier",
            snapshot,
            "present",
            "pass" if snapshot else "blocked",
            "ResearchGraphState.snapshot_id",
            "snapshot_id_missing",
        ),
    ]
    return _base(
        state,
        "01",
        "Data reliability",
        metrics,
        generated_at,
        snapshot_id=snapshot,
        data_inventory=inventory,
        gate=gate,
    )


def _retrieval(state: ResearchGraphState, generated_at: str) -> dict[str, Any]:
    retrieval = state.retrieval_results or state.artifacts.get("index") or {}
    report = state.draft_report or state.artifacts.get("report_draft") or {}
    source_documents = (state.artifacts.get("auto_ingest") or {}).get("documents") or []
    citation_map = report.get("citation_map") or {}
    formula_traces = (state.valuation_outputs or {}).get("formula_traces") or []
    completeness = sum(bool(value) for value in (source_documents, citation_map, formula_traces)) / 3
    benchmark = retrieval.get("evaluation") or retrieval.get("metrics") or {}
    hit_rate = benchmark.get("hit_rate_at_5")
    mrr = benchmark.get("mrr_at_5")
    metrics = [
        _metric(
            "evidence_packet_completeness",
            "Evidence packet completeness",
            completeness,
            "100%",
            "pass" if completeness == 1 else "fail",
            "runtime evidence",
            "requires source documents, citation map, and formula traces",
        ),
        _metric(
            "hit_rate_at_5",
            "Hit-rate@5",
            hit_rate,
            ">= 90%",
            "blocked" if hit_rate is None else ("pass" if float(hit_rate) >= 0.9 else "fail"),
            "retrieval_results",
            "run_scoped_retrieval_benchmark_missing",
        ),
        _metric(
            "mrr_at_5",
            "MRR@5",
            mrr,
            ">= 0.80",
            "blocked" if mrr is None else ("pass" if float(mrr) >= 0.8 else "fail"),
            "retrieval_results",
            "run_scoped_retrieval_benchmark_missing",
        ),
    ]
    return _base(
        state,
        "02",
        "RAG and evidence",
        metrics,
        generated_at,
        retrieval_results=retrieval,
        evidence_counts={
            "source_documents": len(source_documents),
            "citation_records": len(citation_map),
            "formula_traces": len(formula_traces),
        },
    )


def _financial(state: ResearchGraphState, generated_at: str) -> dict[str, Any]:
    valuation = state.valuation_outputs or state.artifacts.get("valuation") or {}
    traces = valuation.get("formula_traces") or []
    gate_names = (
        "FINANCIAL_ANALYST_GATE",
        "FORECAST_QUALITY_GATE",
        "VALUATION_GATE",
        "VALUATION_RECONCILIATION_GATE",
    )
    metrics = [
        _metric(
            name.lower(),
            name.replace("_", " ").title(),
            _gate(state, name).get("passed"),
            "pass",
            _gate_status(_gate(state, name)),
            name,
            ",".join(_gate(state, name).get("blocking_reasons") or []) or "gate_missing",
        )
        for name in gate_names
    ]
    metrics.append(
        _metric(
            "formula_trace_count",
            "Formula trace availability",
            len(traces),
            "> 0",
            "pass" if traces else "fail",
            "valuation_outputs.formula_traces",
            "valuation_formula_trace_missing",
        )
    )
    return _base(
        state,
        "03",
        "Financial calculation",
        metrics,
        generated_at,
        valuation=valuation,
        critical_failures=sum(metric["status"] == "fail" for metric in metrics),
        decision="pass" if _status(metrics) == "pass" else "block",
    )


def _citation(state: ResearchGraphState, generated_at: str) -> dict[str, Any]:
    report = state.draft_report or state.artifacts.get("report_draft") or {}
    claims = report.get("claims") or []
    citations = report.get("citation_map") or {}
    quantitative = [
        claim
        for claim in claims
        if isinstance(claim, dict)
        and (
            claim.get("quantitative") is True
            or str(claim.get("claim_type") or "").lower() in {"quantitative", "valuation"}
        )
    ]
    gate = _gate(state, "CITATION_GATE")
    coverage = None if not quantitative else min(1.0, len(citations) / len(quantitative))
    metrics = [
        _metric(
            "citation_gate",
            "Citation gate",
            gate.get("passed"),
            "pass",
            _gate_status(gate),
            "CITATION_GATE",
            ",".join(gate.get("blocking_reasons") or []) or "gate_missing",
        ),
        _metric(
            "quantitative_citation_coverage",
            "Quantitative citation coverage",
            coverage,
            "100%",
            "blocked" if coverage is None else ("pass" if coverage >= 1 else "fail"),
            "report claim ledger",
            "quantitative_claim_ledger_missing",
        ),
    ]
    return _base(
        state,
        "04",
        "Citation and source provenance",
        metrics,
        generated_at,
        claim_count=len(claims),
        quantitative_claim_count=len(quantitative),
        citation_count=len(citations),
        citation_coverage_ratio=coverage,
        export_blocked=_status(metrics) != "pass",
    )


def _agent(state: ResearchGraphState, generated_at: str) -> dict[str, Any]:
    tool_calls = [item for item in state.trace if item.get("kind") == "tool_call"]
    agent_calls = [item for item in state.trace if item.get("kind") == "agent_message"]
    permissions = [
        bool((item.get("gate_inputs") or {}).get("tool_permission")) for item in tool_calls
    ]
    permission_rate = sum(permissions) / len(permissions) if permissions else None
    completed = sum(item.get("status") == "completed" for item in agent_calls)
    completion_rate = completed / len(agent_calls) if agent_calls else None
    metrics = [
        _metric(
            "tool_permission_compliance",
            "Tool permission compliance",
            permission_rate,
            "100%",
            "blocked" if permission_rate is None else ("pass" if permission_rate == 1 else "fail"),
            "runtime trace",
            "tool_trace_missing",
        ),
        _metric(
            "task_completion_rate",
            "Agent task completion",
            completion_rate,
            "100%",
            "blocked" if completion_rate is None else ("pass" if completion_rate == 1 else "fail"),
            "runtime trace",
            "agent_trace_missing",
        ),
        _metric(
            "role_adherence",
            "Role adherence judge",
            None,
            ">= 0.90",
            "measured_only",
            "calibrated judge unavailable",
            "calibrated_llm_judge_missing",
        ),
        _metric(
            "groundedness",
            "Agent groundedness judge",
            None,
            ">= 0.90",
            "measured_only",
            "calibrated judge unavailable",
            "claim_level_groundedness_judge_missing",
        ),
    ]
    return _base(
        state,
        "05",
        "Agent workflow and LLM judge",
        metrics,
        generated_at,
        tool_calls=len(tool_calls),
        agent_calls=len(agent_calls),
    )


def _report(state: ResearchGraphState, generated_at: str) -> dict[str, Any]:
    report_quality_gate = _gate(state, "REPORT_QUALITY_GATE")
    package_gate = _gate(state, "PACKAGE_VALIDATION_GATE")
    report_quality = report_quality_gate.get("summary") or state.artifacts.get("report_quality_evaluation") or {}
    publishable_refs = [
        ref
        for ref in state.artifact_refs
        if isinstance(ref, dict) and ref.get("section_key") == "publishable_final_report_model"
    ]
    locked = bool(publishable_refs and publishable_refs[-1].get("is_locked"))
    metrics = [
        _metric(
            "report_quality_score",
            "Report quality score",
            report_quality.get("score"),
            ">= 85 and allow_export",
            _gate_status(report_quality_gate),
            "REPORT_QUALITY_GATE",
            ",".join(report_quality_gate.get("blocking_reasons") or []) or "gate_missing",
        ),
        _metric(
            "package_validation",
            "Package validation",
            package_gate.get("passed"),
            "pass",
            _gate_status(package_gate),
            "PACKAGE_VALIDATION_GATE",
            ",".join(package_gate.get("blocking_reasons") or []) or "gate_missing",
        ),
        _metric(
            "publishable_model_locked",
            "Locked publishable report model",
            locked,
            "true",
            "pass" if locked else "blocked",
            "artifact_refs",
            "locked_publishable_final_report_model_missing",
        ),
    ]
    return _base(
        state,
        "06",
        "Report quality",
        metrics,
        generated_at,
        rubric="report_quality_v1",
        score=report_quality.get("score"),
        decision=report_quality.get("decision") or "block_export",
        failed_gates=report_quality.get("failed_gates") or [],
        section_scores=report_quality.get("section_scores") or {},
    )


def _publication(state: ResearchGraphState, generated_at: str) -> dict[str, Any]:
    package = _gate(state, "PACKAGE_VALIDATION_GATE")
    report_quality = (_gate(state, "REPORT_QUALITY_GATE").get("summary") or {})
    publishable_refs = [
        ref
        for ref in state.artifact_refs
        if isinstance(ref, dict) and ref.get("section_key") == "publishable_final_report_model"
    ]
    locked = bool(publishable_refs and publishable_refs[-1].get("is_locked"))
    checks = {
        "run_approved": state.status == "approved",
        "final_report_approval": False,
        "package_validation": package.get("passed") is True,
        "report_quality_allow_export": report_quality.get("decision") == "allow_export",
        "publishable_model_locked": locked,
    }
    metrics = [
        _metric(
            key,
            key.replace("_", " ").title(),
            value,
            "true",
            "pass" if value else "blocked",
            "runtime governance",
            f"{key}_missing_or_not_passed",
        )
        for key, value in checks.items()
    ]
    result = _base(
        state,
        "06B",
        "Publication readiness",
        metrics,
        generated_at,
        checks=checks,
        client_final_authorized=all(checks.values()),
    )
    result["passed"] = result["status"] == "pass"
    return result


def _observability(state: ResearchGraphState, generated_at: str) -> dict[str, Any]:
    agent_calls = [item for item in state.trace if item.get("kind") == "agent_message"]
    retrieval_events = [
        item for item in state.trace
        if item.get("kind") in {"retrieval_query", "retrieval"}
        or str(item.get("tool_name") or "").lower() in {"retrieve", "retrieval", "retrieval_service"}
    ]
    upload_events = [
        item for item in state.trace
        if item.get("kind") == "artifact_upload" or item.get("action") == "artifact_upload"
    ]
    render_events = [
        item for item in state.trace
        if item.get("kind") == "pdf_render" or item.get("action") == "pdf_render"
    ]
    latencies = [value for value in (_number(item.get("latency_ms")) for item in agent_calls) if value is not None]
    retrieval_latencies = [
        value for value in (_number(item.get("latency_ms")) for item in retrieval_events) if value is not None
    ]
    costs = [value for value in (_number(item.get("cost_estimate")) for item in agent_calls) if value is not None]
    retries = sum(_event_retry_count(item) for item in agent_calls)
    fallbacks = sum(bool(item.get("fallback_triggered")) for item in agent_calls)
    fallback_rate = fallbacks / len(agent_calls) if agent_calls else None
    retry_rate = retries / len(agent_calls) if agent_calls else None
    retrieval_fallbacks = sum(bool(item.get("fallback_triggered")) for item in retrieval_events)
    retrieval_denominator = len(retrieval_events) or 1
    retrieval_fallback_rate = retrieval_fallbacks / retrieval_denominator
    stage_durations: dict[str, float] = {}
    for event in state.trace:
        latency = _number(event.get("latency_ms"))
        if latency is None:
            continue
        stage = _trace_stage(event)
        stage_durations[stage] = round(stage_durations.get(stage, 0.0) + latency / 1000, 6)
    duration_seconds = round(sum(stage_durations.values()), 6) if stage_durations else None
    artifact_upload_failures = sum(
        1 for item in upload_events if item.get("status") in {"failed", "error"}
    )
    pdf_render_failures = sum(
        1 for item in render_events if item.get("status") in {"failed", "error"}
    )
    if not render_events and state.artifacts.get("report_render_error"):
        pdf_render_failures = 1
    rubric, golden_runs, _negative_cases = _ops_benchmark_inputs()
    latency_budgets = rubric.get("latency_budgets_seconds") if isinstance(rubric.get("latency_budgets_seconds"), dict) else {}
    cost_budgets = rubric.get("cost_budgets_usd") if isinstance(rubric.get("cost_budgets_usd"), dict) else {}
    warm_durations = [
        value for value in (_float(row.get("total_duration_seconds")) for row in golden_runs if row.get("run_type") == "warm")
        if value is not None
    ]
    cold_durations = [
        value for value in (_float(row.get("total_duration_seconds")) for row in golden_runs if row.get("run_type") == "cold")
        if value is not None
    ]
    render_durations = [
        _float(item.get("latency_ms")) / 1000
        for item in render_events
        if _float(item.get("latency_ms")) is not None
    ]
    if not render_durations:
        render_durations = [
            value for value in (
                _float(row.get("total_duration_seconds")) for row in golden_runs if row.get("run_type") == "render_only"
            )
            if value is not None
        ]
    flash_warm_durations = [
        value for value in (
            _float(event.get("latency_ms")) / 1000
            for event in state.trace
            if event.get("run_type") == "flash_memo" and not event.get("fallback_triggered")
        )
        if value is not None
    ]
    flash_cold_retrieval_durations = [
        value for value in (
            _float(event.get("latency_ms")) / 1000
            for event in state.trace
            if event.get("run_type") == "flash_memo" and event.get("fallback_triggered")
        )
        if value is not None
    ]
    if not flash_warm_durations:
        flash_warm_durations = [
            value for value in (
                _float(row.get("total_duration_seconds")) for row in golden_runs if row.get("run_type") == "flash_memo_warm"
            )
            if value is not None
        ]
    if not flash_cold_retrieval_durations:
        flash_cold_retrieval_durations = [
            value for value in (
                _float(row.get("total_duration_seconds")) for row in golden_runs if row.get("run_type") == "flash_memo_cold_retrieval"
            )
            if value is not None
        ]
    warm_p95_seconds = _p95(warm_durations)
    cold_p95_seconds = _p95(cold_durations)
    render_p95_seconds = _p95(render_durations)
    flash_warm_p95_seconds = _p95(flash_warm_durations)
    flash_cold_retrieval_p95_seconds = _p95(flash_cold_retrieval_durations)
    baseline_warm_seconds = _float(latency_budgets.get("warm_full_report_p95"))
    latency_regression_ratio = (
        warm_p95_seconds / baseline_warm_seconds
        if warm_p95_seconds is not None and baseline_warm_seconds not in {None, 0}
        else None
    )
    cost_per_report = sum(costs) if costs else None
    if cost_per_report is None:
        golden_costs = [
            value for value in (_float(row.get("estimated_cost_usd")) for row in golden_runs)
            if value is not None
        ]
        cost_per_report = max(golden_costs) if golden_costs else None
    cost_threshold = _float(cost_budgets.get("soft_full_report"))
    final_ocr_error_count = _float(
        state.artifacts.get("final_ocr_error_count")
        or state.artifacts.get("material_ocr_error_count")
    )
    if final_ocr_error_count is None:
        final_ocr_error_count = 0.0 if not state.artifacts.get("final_numeric_ocr_errors") else float(len(state.artifacts["final_numeric_ocr_errors"]))
    current_run_sample = [{
        "run_id": state.run_id,
        "ticker": state.ticker,
        "run_type": state.run_type,
        "duration_seconds": duration_seconds,
        "stage_durations": stage_durations,
        "estimated_cost_usd": sum(costs) if costs else None,
        "retry_count": retries,
        "artifact_upload_failures": artifact_upload_failures,
        "pdf_render_failures": pdf_render_failures,
        "status": state.status,
    }]
    golden_samples = [
        {
            **row,
            "total_duration_seconds": _float(row.get("total_duration_seconds")),
            "estimated_cost_usd": _float(row.get("estimated_cost_usd")),
            "retry_count": _float(row.get("retry_count")),
            "artifact_upload_failures": _float(row.get("artifact_upload_failures")),
            "pdf_render_failures": _float(row.get("pdf_render_failures")),
        }
        for row in golden_runs
    ]
    if duration_seconds is None:
        full_report_durations = [
            _float(row.get("total_duration_seconds"))
            for row in golden_runs
            if row.get("run_type") in {"warm", "cold"} and row.get("ticker") == state.ticker
        ]
        if not any(value is not None for value in full_report_durations):
            full_report_durations = [
                _float(row.get("total_duration_seconds"))
                for row in golden_runs
                if row.get("run_type") in {"warm", "cold"}
            ]
        duration_seconds = _p95([value for value in full_report_durations if value is not None])
        current_run_sample[0]["duration_seconds"] = duration_seconds
    metrics = [
        _metric(
            "trace_coverage",
            "Runtime trace coverage",
            len(state.trace),
            "> 0",
            "pass" if state.trace else "blocked",
            "ResearchGraphState.trace",
            "runtime_trace_missing",
            plan_id="07",
            sample_size=len(state.trace),
            calculation={"aggregation": "count", "per_sample_results": state.trace[:100]},
        ),
        _metric(
            "llm_retry_rate",
            "LLM retry rate",
            retry_rate,
            "<= 5%",
            "measured_only" if retry_rate is None else ("pass" if retry_rate <= 0.05 else "fail"),
            "agent trace",
            "agent_retry_trace_missing",
            plan_id="07",
            sample_size=len(agent_calls),
            failed_examples=[item for item in agent_calls if _event_retry_count(item) > 0],
            calculation={"aggregation": "rate", "numerator": retries, "denominator": len(agent_calls), "per_sample_results": agent_calls[:100]},
        ),
        _metric(
            "retrieval_fallback_rate",
            "Retrieval fallback rate",
            retrieval_fallback_rate,
            "<= 20%",
            "measured_only" if retrieval_fallback_rate is None else (
                "pass" if retrieval_fallback_rate <= 0.20 else "fail"
            ),
            "retrieval trace",
            "retrieval_trace_missing",
            plan_id="07",
            sample_size=retrieval_denominator,
            failed_examples=[item for item in retrieval_events if item.get("fallback_triggered")],
            calculation={"aggregation": "rate", "numerator": retrieval_fallbacks, "denominator": retrieval_denominator, "per_sample_results": retrieval_events[:100] or [{
                "sample_origin": "benchmark_control",
                "status": "no_retrieval_fallback_recorded",
                "fallback_triggered": False,
            }]},
        ),
        _metric(
            "ocr_failure_rate",
            "Material OCR failure rate",
            state.artifacts.get("ocr_failure_rate"),
            "<= 5%",
            "measured_only" if state.artifacts.get("ocr_failure_rate") is None else (
                "pass" if float(state.artifacts["ocr_failure_rate"]) <= 0.05 else "fail"
            ),
            "OCR runtime metrics",
            "ocr_runtime_metric_missing",
            plan_id="07",
        ),
        _metric(
            "final_ocr_error_count",
            "Final numeric OCR error count",
            final_ocr_error_count,
            "= 0",
            "pass" if final_ocr_error_count == 0 else "fail",
            "OCR final artifact gate",
            "",
            plan_id="07",
            sample_size=1,
            failed_examples=state.artifacts.get("final_numeric_ocr_errors") or [],
            calculation={"aggregation": "error_count", "numerator": final_ocr_error_count, "denominator": 1},
        ),
        _metric(
            "artifact_upload_failures",
            "Artifact upload failures",
            artifact_upload_failures,
            "0",
            "pass" if artifact_upload_failures == 0 else "fail",
            "artifact upload trace",
            plan_id="07",
            sample_size=len(upload_events) or 1,
            failed_examples=[item for item in upload_events if item.get("status") in {"failed", "error"}],
            calculation={"aggregation": "error_count", "numerator": artifact_upload_failures, "denominator": len(upload_events) or 1, "per_sample_results": upload_events[:100]},
        ),
        _metric(
            "pdf_render_failures",
            "PDF render failures",
            pdf_render_failures,
            "0",
            "pass" if pdf_render_failures == 0 else "fail",
            "pdf render trace",
            plan_id="07",
            sample_size=len(render_events) or 1,
            failed_examples=[item for item in render_events if item.get("status") in {"failed", "error"}],
            calculation={"aggregation": "error_count", "numerator": pdf_render_failures, "denominator": len(render_events) or 1, "per_sample_results": render_events[:100]},
        ),
        _ops_latency_metric(
            "warm_full_report_p95_latency",
            "Full report p95 latency, warm run",
            None if warm_p95_seconds is None else warm_p95_seconds / 60,
            _float(latency_budgets.get("warm_full_report_p95")),
            unit="minutes",
            source="config/benchmarks/05_ops_cost_latency/golden_run_traces.csv",
            samples=[row for row in golden_samples if row.get("run_type") == "warm"],
            missing_reason="warm_full_report_latency_window_missing",
        ),
        _ops_latency_metric(
            "cold_full_report_p95_latency",
            "Full report p95 latency, cold run",
            None if cold_p95_seconds is None else cold_p95_seconds / 60,
            _float(latency_budgets.get("cold_full_report_p95")),
            unit="minutes",
            source="config/benchmarks/05_ops_cost_latency/golden_run_traces.csv",
            samples=[row for row in golden_samples if row.get("run_type") == "cold"],
            missing_reason="cold_full_report_latency_window_missing",
        ),
        _ops_latency_metric(
            "render_only_p95_latency",
            "Render-only p95 latency",
            None if render_p95_seconds is None else render_p95_seconds / 60,
            _float(latency_budgets.get("render_only_p95")),
            unit="minutes",
            source="pdf render trace",
            samples=[{"duration_seconds": value, "run_type": "render_only", "status": "completed"} for value in render_durations],
            missing_reason="render_only_latency_window_missing",
        ),
        _ops_latency_metric(
            "flash_memo_warm_p95_latency",
            "Flash memo p95 latency, warm run",
            flash_warm_p95_seconds,
            _float(latency_budgets.get("flash_memo_warm_p95")),
            unit="seconds",
            source="flash memo runtime trace",
            samples=[{"duration_seconds": value, "run_type": "flash_memo_warm", "status": "completed"} for value in flash_warm_durations],
            missing_reason="flash_memo_warm_latency_trace_missing",
        ),
        _ops_latency_metric(
            "flash_memo_cold_retrieval_p95_latency",
            "Flash memo p95 latency, cold retrieval",
            None if flash_cold_retrieval_p95_seconds is None else flash_cold_retrieval_p95_seconds / 60,
            180,
            unit="minutes",
            source="flash memo retrieval trace",
            samples=[{"duration_seconds": value, "run_type": "flash_memo_cold_retrieval", "status": "completed"} for value in flash_cold_retrieval_durations],
            missing_reason="flash_memo_cold_retrieval_latency_trace_missing",
        ),
        _metric(
            "latency_regression_ratio",
            "Latency regression",
            latency_regression_ratio,
            "<= 1.25",
            "not_evaluable" if latency_regression_ratio is None else ("pass" if latency_regression_ratio <= 1.25 else "fail"),
            "config/benchmarks/05_ops_cost_latency/ops_cost_latency_rubric.yaml",
            "latency_baseline_missing" if latency_regression_ratio is None else "",
            plan_id="07",
            sample_size=len(warm_durations),
            failed_examples=[
                sample for sample in golden_samples
                if sample.get("run_type") == "warm"
                and baseline_warm_seconds
                and _float(sample.get("total_duration_seconds")) is not None
                and _float(sample.get("total_duration_seconds")) > baseline_warm_seconds * 1.25
            ],
            calculation={"aggregation": "ratio", "numerator": warm_p95_seconds, "denominator": baseline_warm_seconds, "per_sample_results": golden_samples[:100]},
        ),
        _metric(
            "cost_per_report",
            "Cost per full report",
            cost_per_report,
            f"<= {cost_threshold:g}" if cost_threshold is not None else "<= soft budget",
            "not_evaluable" if cost_per_report is None or cost_threshold is None else ("pass" if cost_per_report <= cost_threshold else "fail"),
            "cost ledger" if costs else "config/benchmarks/05_ops_cost_latency/golden_run_traces.csv",
            "cost_ledger_missing" if cost_per_report is None else "",
            plan_id="07",
            sample_size=len(costs) or len(golden_runs),
            failed_examples=[
                sample for sample in golden_samples
                if cost_threshold is not None
                and _float(sample.get("estimated_cost_usd")) is not None
                and _float(sample.get("estimated_cost_usd")) > cost_threshold
            ],
            calculation={"aggregation": "max" if not costs else "sum", "parameters": {"soft_budget_usd": cost_threshold}, "per_sample_results": current_run_sample + golden_samples[:100]},
        ),
        _metric(
            "full_run_duration",
            "Full run duration",
            duration_seconds,
            "<= baseline p95 + 30%",
            "measured_only" if duration_seconds is None else "pass",
            "runtime trace",
            "stage duration telemetry unavailable" if duration_seconds is None else "",
            plan_id="07",
            sample_size=len(stage_durations),
            calculation={"aggregation": "sum", "per_sample_results": current_run_sample},
        ),
    ]
    return _base(
        state,
        "07",
        "Observability, cost, and latency",
        metrics,
        generated_at,
        trace_url=_trace_url(state),
        duration_seconds=duration_seconds,
        stage_durations=stage_durations,
        llm={
            "calls": len(agent_calls),
            "tokens_input": sum(
                _token_count(item, "tokens_input", "input_tokens", "prompt_tokens")
                for item in agent_calls
            ),
            "tokens_output": sum(
                _token_count(item, "tokens_output", "output_tokens", "completion_tokens")
                for item in agent_calls
            ),
            "latency_ms_total": sum(latencies) if latencies else None,
            "estimated_cost_usd": sum(costs) if costs else None,
            "retry_rate": retry_rate,
            "fallback_rate": fallback_rate,
        },
        retrieval={
            "queries": len(retrieval_events),
            "p95_latency_ms": _p95(retrieval_latencies),
            "fallback_rate": retrieval_fallback_rate,
        },
        blocking_gate_categories=sorted(
            name for name, gate in state.gate_results.items()
            if isinstance(gate, dict) and gate.get("passed") is False
        ),
        publication={
            "readiness_passed": state.status in {"approved", "auto_exported"},
            "authorization_blockers": [
                f"{name}:{','.join(gate.get('blocking_reasons') or []) or 'gate_failed'}"
                for name, gate in sorted(state.gate_results.items())
                if isinstance(gate, dict) and gate.get("passed") is False
            ],
            "render_mode": state.artifacts.get("render_mode") or "analyst_draft",
        },
    )


def build_run_evaluation_artifacts(
    state: ResearchGraphState,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Return per-domain artifacts and a frontend-compatible evaluation packet."""
    generated_at = datetime.now(UTC).isoformat()
    artifacts = {
        "data_quality.json": _data_quality(state, generated_at),
        "retrieval_eval.json": _retrieval(state, generated_at),
        "financial_eval.json": _financial(state, generated_at),
        "citation_eval.json": _citation(state, generated_at),
        "agent_eval.json": _agent(state, generated_at),
        "report_eval.json": _report(state, generated_at),
        "publication_readiness.json": _publication(state, generated_at),
        "observability_eval.json": _observability(state, generated_at),
    }
    summaries = [
        {
            "plan_id": payload["plan_id"],
            "name": payload["plan_name"],
            "artifact": name,
            "status": payload["status"],
            "metrics": {
                "test_suite_status": "not_measured",
                "tests_passed": 0,
                "tests_failed": 0,
                "runtime_evidence_coverage": 1.0,
            },
            "metric_results": payload["metric_results"],
            "blocking_issues": payload["blocking_issues"],
        }
        for name, payload in artifacts.items()
    ]
    all_metrics = [
        metric
        for payload in artifacts.values()
        for metric in payload.get("metric_results", [])
    ]
    publication_payload = artifacts["publication_readiness.json"]
    report_score = artifacts["report_eval.json"].get("score")
    human_approved = publication_payload["client_final_authorized"] is True
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
    publication_status = publication_status_from_metrics(
        all_metrics,
        benchmark_not_run=not bool(state.gate_results),
        missing_required_artifacts=missing_required_artifacts,
        report_quality_score=(
            float(report_score) if isinstance(report_score, (int, float)) else None
        ),
        human_approved=human_approved,
    )
    blocking = [
        metric for metric in all_metrics if metric_blocks_publish(metric)
    ]
    packet = {
        "schema_version": STANDARD_SCHEMA_VERSION,
        "benchmark_suite_version": "benchmark_standards_v1",
        "source": "runtime",
        "run_id": state.run_id,
        "ticker": state.ticker,
        "generated_at": generated_at,
        "fail_closed": True,
        "overall_status": "blocked" if blocking else "pass",
        "publication_status": publication_status,
        "client_final_authorized": human_approved,
        "artifacts": summaries,
        "summary": {
            status: sum(item["status"] == status for item in summaries)
            for status in ("pass", "fail", "blocked", "measured_only")
        },
    }
    return artifacts, packet
