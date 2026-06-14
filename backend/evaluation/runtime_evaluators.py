"""Deterministic runtime evaluators for the eight project evaluation plans."""
from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend.evaluation.benchmark_standards import standard_metric


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _files_named(root: Path, name: str) -> list[Path]:
    if not root.exists():
        return []
    matches: list[Path] = []
    for directory, _, filenames in os.walk(root):
        if name in filenames:
            matches.append(Path(directory) / name)
    return sorted(matches, key=lambda path: path.stat().st_mtime, reverse=True)


def _latest_named(root: Path, name: str) -> Path | None:
    matches = _files_named(root, name)
    return matches[0] if matches else None


def _latest_named_for_ticker(root: Path, name: str, ticker: str) -> Path | None:
    """Return the most recent ``name`` whose run path is scoped to ``ticker``.

    Ticker-blind lookups silently let one ticker's run satisfy another ticker's
    evaluation (e.g. a DBD evaluation grabbing DHG's valuation). Scoping by the
    run directory name keeps the multi-ticker pilot honest: a ticker without its
    own run produces ``None`` and is reported as missing rather than borrowed.
    """
    needle = ticker.lower()
    for path in _files_named(root, name):
        parts = [part.lower() for part in path.relative_to(root).parts]
        if any(needle in part for part in parts):
            return path
    return None


def _metric(
    metric_id: str,
    label: str,
    value: Any,
    threshold: str,
    status: str,
    source: str,
    detail: str = "",
) -> dict[str, Any]:
    return standard_metric(
        metric_id=metric_id,
        metric_name=label,
        value=value,
        threshold=threshold,
        status=status,
        source=source,
        detail=detail,
    )


def _ratio_status(value: float | None, target: float, comparator: str = "gte") -> str:
    if value is None:
        return "measured_only"
    passed = value >= target if comparator == "gte" else value <= target
    return "pass" if passed else "fail"


def _status(metrics: list[dict[str, Any]], *, blocked: bool = False) -> str:
    if any(item["status"] == "fail" for item in metrics):
        return "fail"
    if blocked:
        return "blocked"
    if metrics and all(item["status"] in {"measured_only", "warning"} for item in metrics):
        return "measured_only"
    return "pass"


def _blocked(metrics: list[dict[str, Any]]) -> list[str]:
    return [
        f"{item['id']}:{item.get('detail') or 'threshold_not_met'}"
        for item in metrics
        if item["status"] == "fail"
    ]


def evaluate_data_reliability(root: Path, ticker: str) -> dict[str, Any]:
    golden = root / "config" / "dataset" / "golden" / "financials" / f"{ticker}.csv"
    rows: list[dict[str, str]] = []
    if golden.is_file():
        with golden.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

    unique_keys = {
        (row.get("period"), row.get("statement_type"), row.get("canonical_key"))
        for row in rows
    }
    duplicate_rate = 0.0 if not rows else 1 - len(unique_keys) / len(rows)
    accepted = [row for row in rows if row.get("validation_status") == "accepted"]
    provenance = [
        row for row in rows
        if row.get("source_uri") and row.get("source_title") and row.get("source_type")
    ]
    core_coverage = len(accepted) / len(rows) if rows else 0.0
    provenance_coverage = len(provenance) / len(rows) if rows else 0.0

    raw_dir = root / "data" / "raw" / "bctc" / ticker
    required_statements = (
        "income_statement_year.json",
        "balance_sheet_year.json",
        "cash_flow_year.json",
    )
    present_statements = sum((raw_dir / name).is_file() for name in required_statements)
    period_completeness = present_statements / len(required_statements)

    metadata = _read_json(
        _latest_named(root / "storage" / "sources" / "ocr_artifacts" / ticker, "metadata.json")
    )
    pages = int(metadata.get("pages_processed") or 0)
    pages_failed = int(metadata.get("pages_failed") or 0)
    ocr_failure_rate = pages_failed / pages if pages else None
    ocr_candidates = int(metadata.get("candidate_row_count") or 0)
    unresolved = max(0, ocr_candidates - int(metadata.get("mapped_fact_count") or 0))
    ocr_unresolved_rate = unresolved / ocr_candidates if ocr_candidates else 0.0

    metrics = [
        _metric("core_metric_coverage", "Core metric coverage", core_coverage, ">= 95%",
                _ratio_status(core_coverage, 0.95), str(golden.relative_to(root)) if golden.exists() else "missing"),
        _metric("period_completeness", "Statement completeness", period_completeness, "100%",
                _ratio_status(period_completeness, 1.0), str(raw_dir.relative_to(root))),
        _metric("provenance_coverage", "Source provenance coverage", provenance_coverage, "100%",
                _ratio_status(provenance_coverage, 1.0), str(golden.relative_to(root)) if golden.exists() else "missing"),
        _metric("official_reconciliation_rate", "Accepted official reconciliation", core_coverage, ">= 95%",
                _ratio_status(core_coverage, 0.95), str(golden.relative_to(root)) if golden.exists() else "missing"),
        _metric("ocr_unresolved_rate", "OCR unresolved rate", ocr_unresolved_rate, "0%",
                _ratio_status(ocr_unresolved_rate, 0.0, "lte"), "latest OCR metadata"),
        _metric("duplicate_fact_rate", "Duplicate canonical fact rate", duplicate_rate, "0%",
                _ratio_status(duplicate_rate, 0.0, "lte"), str(golden.relative_to(root)) if golden.exists() else "missing"),
    ]
    return {
        "status": _status(metrics),
        "metrics": metrics,
        "blocking_issues": _blocked(metrics),
        "core_metric_coverage": core_coverage,
        "period_completeness": period_completeness,
        "provenance_coverage": provenance_coverage,
        "official_reconciliation_rate": core_coverage,
        "ocr_unresolved_rate": ocr_unresolved_rate,
        "duplicate_fact_rate": duplicate_rate,
        "ocr": metadata,
    }


def evaluate_retrieval(root: Path, ticker: str) -> dict[str, Any]:
    packet_path = _latest_named(root / "storage" / "archive", "run1_evidence_packet.json")
    packet = _read_json(packet_path)
    source_documents = packet.get("source_documents") or []
    citation_map = packet.get("citation_map") or {}
    formula_traces = packet.get("formula_traces") or []
    required_parts = (bool(source_documents), bool(citation_map), bool(formula_traces))
    evidence_completeness = sum(required_parts) / len(required_parts)
    golden_path = root / "config" / "eval" / "rag_golden_queries.yaml"
    golden_available = golden_path.is_file()
    golden_scores = _run_local_retrieval_benchmark(root, ticker, golden_path)

    semantic_metrics = [
        ("context_precision", "Context precision", ">= 0.85"),
        ("context_recall", "Context recall", ">= 0.85"),
        ("faithfulness", "Faithfulness", ">= 0.85"),
        ("response_relevancy", "Response relevancy", ">= 0.85"),
    ]
    metrics = [
        _metric(metric_id, label, None, threshold, "measured_only",
                str(golden_path.relative_to(root)) if golden_available else "golden query set missing",
                "Requires a versioned golden query set and retrieval run.")
        for metric_id, label, threshold in semantic_metrics
    ]
    metrics[0:0] = [
        _metric("hit_rate_at_5", "Hit-rate@5", golden_scores.get("hit_rate_at_5"), ">= 90%",
                _ratio_status(golden_scores.get("hit_rate_at_5"), 0.90),
                str(golden_path.relative_to(root)) if golden_available else "golden query set missing"),
        _metric("mrr_at_5", "MRR@5", golden_scores.get("mrr_at_5"), ">= 0.80",
                _ratio_status(golden_scores.get("mrr_at_5"), 0.80),
                str(golden_path.relative_to(root)) if golden_available else "golden query set missing"),
    ]
    metrics.append(
        _metric("evidence_packet_completeness", "Evidence packet completeness",
                evidence_completeness, "100%", _ratio_status(evidence_completeness, 1.0),
                str(packet_path.relative_to(root)) if packet_path else "missing",
                "Requires source documents, citation map, and formula traces.")
    )
    return {
        "status": _status(metrics, blocked=not golden_available),
        "metrics": metrics,
        "blocking_issues": _blocked(metrics) + ([] if golden_available else ["rag_golden_query_set_missing"]),
        "retrieval_backend": "not_measured",
        "query_set_version": None,
        "ragas_scores": {key: None for key in ("context_precision", "context_recall", "faithfulness", "response_relevancy")},
        "golden_scores": golden_scores,
        "evidence_packet": {
            "path": str(packet_path.relative_to(root)) if packet_path else None,
            "source_documents": len(source_documents),
            "citation_records": len(citation_map),
            "formula_traces": len(formula_traces),
        },
    }


def _run_local_retrieval_benchmark(
    root: Path, ticker: str, golden_path: Path
) -> dict[str, Any]:
    if not golden_path.is_file():
        return {"hit_rate_at_5": None, "mrr_at_5": None, "queries": []}
    try:
        import yaml

        config = yaml.safe_load(golden_path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {"hit_rate_at_5": None, "mrr_at_5": None, "queries": []}

    corpus_root = root / "storage" / "sources" / "ocr_artifacts" / ticker
    pages: list[tuple[int, str]] = []
    for directory, _, filenames in os.walk(corpus_root):
        for filename in filenames:
            match = re.fullmatch(r"page_(\d+)\.txt", filename)
            if not match:
                continue
            path = Path(directory) / filename
            pages.append((int(match.group(1)), path.read_text(encoding="utf-8", errors="ignore").lower()))

    outcomes: list[dict[str, Any]] = []
    for query in config.get("queries") or []:
        tokens = {
            token for token in re.findall(r"[a-z0-9]+", str(query.get("query") or "").lower())
            if len(token) > 2
        }
        ranked = sorted(
            (
                (page, sum(text.count(token) for token in tokens))
                for page, text in pages
            ),
            key=lambda item: (-item[1], item[0]),
        )
        top_five = [page for page, score in ranked[:5] if score > 0]
        expected = {int(page) for page in query.get("expected_pages") or []}
        first_rank = next(
            (index + 1 for index, page in enumerate(top_five) if page in expected),
            None,
        )
        outcomes.append({
            "id": query.get("id"),
            "top_5_pages": top_five,
            "expected_pages": sorted(expected),
            "hit": first_rank is not None,
            "reciprocal_rank": 0.0 if first_rank is None else 1 / first_rank,
        })
    count = len(outcomes)
    return {
        "query_set_version": config.get("version"),
        "hit_rate_at_5": sum(item["hit"] for item in outcomes) / count if count else None,
        "mrr_at_5": sum(item["reciprocal_rank"] for item in outcomes) / count if count else None,
        "queries": outcomes,
    }


def _matrix_varies(value: Any) -> bool:
    numbers: set[float] = set()
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, (int, float)) and not isinstance(current, bool):
            numbers.add(round(float(current), 6))
    return len(numbers) > 1


def evaluate_financial(root: Path, ticker: str) -> dict[str, Any]:
    valuation_path = _latest_named_for_ticker(
        root / "storage" / "runs", "valuation.json", ticker
    )
    if valuation_path is None:
        # Honest fail-closed: this ticker has no valuation run to evaluate. We do
        # not borrow another ticker's valuation, and a missing run is "blocked"
        # (cannot be measured) rather than "fail" (computed and wrong).
        metric = _metric(
            "valuation_artifact", "Valuation run artifact", None, "present",
            "blocked", f"storage/runs/*{ticker.lower()}*/valuation.json",
            "no_valuation_run_for_ticker",
        )
        return {
            "status": "blocked",
            "metrics": [metric],
            "blocking_issues": ["valuation_run_missing_for_ticker"],
            "valuation_artifact": None,
            "invariants": [],
            "critical_failures": None,
            "golden_drift_out_of_tolerance": None,
            "missing_traces": ["valuation_formula_trace"],
            "decision": "block",
        }
    valuation = _read_json(valuation_path)
    fcff = valuation.get("fcff") or {}
    fcfe = valuation.get("fcfe") or {}
    sensitivity = valuation.get("sensitivity") or {}
    formula_traces = valuation.get("formula_traces") or []

    net_bridge = fcff.get("net_debt_bridge") or {}
    expected_net_debt = (
        float(net_bridge.get("total_debt") or 0)
        - float(net_bridge.get("cash") or 0)
        - float(net_bridge.get("short_term_investments") or 0)
    )
    net_debt_pass = bool(net_bridge) and abs(expected_net_debt - float(net_bridge.get("net_debt") or 0)) <= 0.5
    fcff_rows = fcff.get("fcff_table") or []
    fcff_pass = bool(fcff_rows) and all(
        abs(
            float(row.get("fcff") or 0)
            - (
                float(row.get("ebit_after_tax") or 0)
                + float(row.get("depreciation") or 0)
                - float(row.get("capex") or 0)
                - float(row.get("delta_nwc") or 0)
            )
        ) <= 0.2
        for row in fcff_rows
    )
    fcfe_rows = fcfe.get("fcfe_table") or []
    fcfe_pass = bool(fcfe_rows) and all(row.get("fcfe") is not None for row in fcfe_rows)
    gordon_pass = (
        isinstance(fcff.get("wacc"), (int, float))
        and isinstance(fcff.get("terminal_growth"), (int, float))
        and fcff["wacc"] > fcff["terminal_growth"]
    )
    target_expected = (
        float(fcff.get("equity_value") or 0) * 1000 / float(fcff.get("shares_mn") or 1)
    )
    target_pass = bool(fcff.get("target_price_vnd")) and abs(
        target_expected - float(fcff.get("target_price_vnd") or 0)
    ) / max(abs(target_expected), 1) <= 0.005
    sensitivity_pass = _matrix_varies(sensitivity.get("fcff_wacc_g"))
    fcfe_sensitivity = _matrix_varies(sensitivity.get("fcfe_re_g"))
    blend_sensitivity = _matrix_varies(sensitivity.get("blend_grid"))
    trace_pass = bool(formula_traces)

    invariant_values = [
        ("net_debt", "Net debt reconciliation", net_debt_pass),
        ("fcff", "FCFF formula", fcff_pass),
        ("fcfe", "FCFE formula", fcfe_pass),
        ("target_price", "Target price reproduction", target_pass),
        ("gordon_growth", "Discount rate exceeds terminal growth", gordon_pass),
        ("sensitivity_varies", "FCFF sensitivity matrix varies", sensitivity_pass),
        ("fcfe_sensitivity", "FCFE sensitivity matrix varies", fcfe_sensitivity),
        ("blend_sensitivity", "Blend sensitivity matrix varies", blend_sensitivity),
        ("formula_trace", "Formula trace available", trace_pass),
    ]
    metrics = [
        _metric(metric_id, label, 1 if passed else 0, "pass", "pass" if passed else "fail",
                str(valuation_path.relative_to(root)) if valuation_path else "missing")
        for metric_id, label, passed in invariant_values
    ]
    invariants = [
        {"id": metric_id, "severity": "critical", "passed": passed, "detail": label}
        for metric_id, label, passed in invariant_values
    ]
    critical_failures = sum(not item["passed"] for item in invariants)
    return {
        "status": _status(metrics),
        "metrics": metrics,
        "blocking_issues": _blocked(metrics),
        "valuation_artifact": str(valuation_path.relative_to(root)) if valuation_path else None,
        "invariants": invariants,
        "critical_failures": critical_failures,
        "golden_drift_out_of_tolerance": None,
        "missing_traces": [] if trace_pass else ["valuation_formula_trace"],
        "decision": "pass" if critical_failures == 0 else "block",
    }


def _pdf_stats(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "exists": False, "pages": 0, "text": ""}
    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            return {"path": str(path), "exists": True, "pages": len(pdf.pages), "text": text}
    except Exception as exc:
        return {"path": str(path), "exists": True, "pages": 0, "text": "", "error": str(exc)}


def evaluate_citation(root: Path, ticker: str) -> dict[str, Any]:
    report = _pdf_stats(root / "output" / f"{ticker}_report.pdf")
    text = report.pop("text", "")
    source_mentions = len(re.findall(r"(?:Source|Nguon|Nguồn)\s*:", text, re.IGNORECASE))
    generic = len(re.findall(
        r"(?:Source|Nguon|Nguồn)\s*:\s*(?:API|System|Database|Canonical financial facts)\b",
        text,
        re.IGNORECASE,
    ))
    quant_claims = len(re.findall(r"\b\d[\d.,]*\s*(?:%|VND|x)\b", text, re.IGNORECASE))
    citation_markers = len(re.findall(r"\[\^|Nguon:|Source:", text, re.IGNORECASE))
    claim_ledger = _latest_named(root / "storage" / "archive", "claim_ledger.json")
    ledger_available = claim_ledger is not None
    metrics = [
        _metric("quantitative_citation_coverage", "Quantitative citation coverage", None, "100%",
                "measured_only", "claim ledger missing",
                "PDF-level source counts cannot prove claim-level coverage."),
        _metric("citation_key_resolution", "Citation key resolution", None, "100%", "measured_only",
                "claim ledger missing"),
        _metric("source_id_validity", "Source ID validity", None, "100%", "measured_only",
                "claim ledger missing"),
        _metric("official_source_coverage", "Official source coverage", None, "100%", "measured_only",
                "claim ledger missing"),
        _metric("generic_citations", "Generic citation labels", generic, "0",
                _ratio_status(float(generic), 0.0, "lte"), str(report["path"])),
        _metric("pdf_source_mentions", "PDF source labels", source_mentions, "> 0",
                "pass" if source_mentions > 0 else "fail", str(report["path"])),
    ]
    blockers = _blocked(metrics)
    if not ledger_available:
        blockers.append("claim_ledger_missing")
    return {
        "status": _status(metrics, blocked=not ledger_available),
        "metrics": metrics,
        "blocking_issues": blockers,
        "claim_count": None,
        "quantitative_claim_count": quant_claims,
        "citation_coverage_ratio": None,
        "source_tier_counts": {},
        "official_source_coverage": None,
        "numeric_mismatches": [],
        "generic_citations": generic,
        "citation_markers": citation_markers,
        "report": report,
        "export_blocked": True,
    }


def evaluate_agent(root: Path, ticker: str) -> dict[str, Any]:
    audit_path = _latest_named(root / "storage" / "archive", "run1_agent_effectiveness_audit.json")
    audit = _read_json(audit_path)
    packet_path = _latest_named(root / "storage" / "archive", "run1_evidence_packet.json")
    packet = _read_json(packet_path)
    gates = packet.get("gate_results") or {}
    tool_gate = gates.get("TOOL_PERMISSION_GATE") or {}
    tool_compliance = 1.0 if tool_gate.get("passed") is True else 0.0
    agent_records = audit.get("agent_execution") or []
    task_completion = (
        sum(record.get("status") == "completed" for record in agent_records) / len(agent_records)
        if agent_records else None
    )
    json_outputs = _files_named(root / "storage" / "archive" / "debug" / "agent_outputs", "run1_financial_analysis.json")
    schema_validity = 1.0 if json_outputs else 0.0
    metrics = [
        _metric("tool_permission_compliance", "Tool permission compliance", tool_compliance, "100%",
                _ratio_status(tool_compliance, 1.0), str(packet_path.relative_to(root)) if packet_path else "missing"),
        _metric("schema_validity", "Output schema validity", schema_validity, "100%",
                _ratio_status(schema_validity, 1.0), "archived agent JSON outputs"),
        _metric("role_adherence", "Role adherence", None, ">= 0.90", "measured_only",
                "calibrated LLM judge missing"),
        _metric("groundedness", "Groundedness", None, ">= 0.90", "measured_only",
                "claim-level evidence judge missing"),
        _metric("no_unauthorized_calc", "No unauthorized financial calculation", None, "100%",
                "measured_only", "agent trace classifier missing"),
        _metric("task_completion", "Task completion", task_completion, ">= 0.85",
                _ratio_status(task_completion, 0.85), str(audit_path.relative_to(root)) if audit_path else "missing"),
        _metric("plan_adherence", "Plan adherence", None, ">= 0.85", "measured_only",
                "plan trace comparison missing"),
        _metric("critic_issue_recall", "Critic issue recall", None, ">= 90%", "measured_only",
                "seeded failure dataset missing"),
    ]
    # Per evaluation plan §5.5 the LLM-judge criteria (role adherence,
    # groundedness, no-unauthorized-calc, plan adherence, critic recall) are
    # ADVISORY and must not override the deterministic gates. The judge is
    # explicitly out of P0 scope, so a missing calibrated judge is recorded as
    # an advisory finding, not a blocking failure. Deterministic agent metrics
    # (tool permission, schema validity, task completion) still gate.
    advisory_findings = [
        f"{item['id']}:calibrated_llm_judge_pending"
        for item in metrics
        if item.get("legacy_status") == "measured_only" or item["status"] == "warning"
    ]
    return {
        "status": _status(metrics),
        "metrics": metrics,
        "blocking_issues": _blocked(metrics),
        "advisory_findings": advisory_findings,
        "judge_status": "advisory_pending",
        "tool_permission_compliance": tool_compliance,
        "schema_validity": schema_validity,
        "role_adherence": None,
        "groundedness": None,
        "no_unauthorized_calc": None,
        "task_completion": task_completion,
        "plan_adherence": None,
        "critic_issue_recall": None,
        "rubric_scores": {},
    }


def evaluate_report(root: Path, ticker: str, financial: dict[str, Any]) -> dict[str, Any]:
    report = _pdf_stats(root / "output" / f"{ticker}_report.pdf")
    explanation = _pdf_stats(root / "output" / f"{ticker}_explanation.pdf")
    finance_pass = financial.get("decision") == "pass"
    metrics = [
        _metric("report_pdf_rendered", "Report PDF rendered", 1 if report["exists"] else 0, "pass",
                "pass" if report["exists"] else "fail", str(report["path"])),
        _metric("explanation_pdf_rendered", "Explanation PDF rendered", 1 if explanation["exists"] else 0,
                "pass", "pass" if explanation["exists"] else "fail", str(explanation["path"])),
        _metric("financial_gate_passed", "Deterministic finance gate", 1 if finance_pass else 0, "pass",
                "pass" if finance_pass else "fail", "financial_eval.json"),
        _metric("report_quality_score", "Report quality score", None, ">= 85", "measured_only",
                "publishable report model missing"),
        _metric("publication_readiness", "Publication readiness", 0, "pass", "fail",
                "final approval and locked publishable model missing"),
    ]
    blockers = _blocked(metrics) + ["final_report_approval_missing", "publishable_final_report_model_missing"]
    return {
        "status": _status(metrics),
        "metrics": metrics,
        "blocking_issues": sorted(set(blockers)),
        "rubric": "report_quality_v1",
        "score": None,
        "decision": "block_export",
        "failed_gates": ["financial_gate"] if not finance_pass else [],
        "section_scores": {},
        "report_artifacts": {"pdf": report, "explanation_pdf": explanation},
        "publication_readiness": {
            "passed": False,
            "blocking_reasons": sorted(set(blockers)),
        },
    }


def evaluate_observability(root: Path, ticker: str) -> dict[str, Any]:
    metadata = _read_json(
        _latest_named(root / "storage" / "sources" / "ocr_artifacts" / ticker, "metadata.json")
    )
    pages = int(metadata.get("pages_processed") or 0)
    ocr_failure_rate = int(metadata.get("pages_failed") or 0) / pages if pages else None
    report_exists = (root / "output" / f"{ticker}_report.pdf").is_file()
    metrics = [
        _metric("duration_seconds", "Full run duration", None, "<= baseline p95 + 30%",
                "measured_only", "run trace missing"),
        _metric("llm_retry_rate", "LLM retry rate", None, "<= 5%", "measured_only", "run trace missing"),
        _metric("retrieval_fallback_rate", "Retrieval fallback rate", None, "<= 20%",
                "measured_only", "retrieval trace missing"),
        _metric("ocr_failure_rate", "OCR failure rate", ocr_failure_rate, "<= 5%",
                _ratio_status(ocr_failure_rate, 0.05, "lte"), "latest OCR metadata"),
        _metric("pdf_render_failures", "PDF render failures", 0 if report_exists else 1, "0",
                "pass" if report_exists else "fail", f"output/{ticker}_report.pdf"),
        _metric("cost_per_report", "Cost per full report", None, "<= soft budget",
                "measured_only", "cost ledger missing"),
    ]
    return {
        "status": _status(metrics),
        "metrics": metrics,
        "blocking_issues": _blocked(metrics),
        "duration_seconds": None,
        "stage_durations": {},
        "llm": {"calls": None, "tokens_input": None, "tokens_output": None, "estimated_cost_usd": None, "retry_rate": None},
        "retrieval": {"queries": None, "p95_latency_ms": None, "fallback_rate": None},
        "ocr": {"pages_processed": pages, "failure_rate": ocr_failure_rate},
        "publication": {"readiness_passed": False, "render_mode": "analyst_draft"},
        "trace_url": None,
    }


def evaluate_rollout(
    test_execution: dict[str, Any],
    prior_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    test_pass = test_execution.get("status") == "pass"
    rag_scores = prior_results.get("02", {}).get("golden_scores") or {}
    rag_golden_available = rag_scores.get("hit_rate_at_5") is not None
    metrics = [
        _metric("evaluation_gates_ci", "Evaluation gate CI scope", 1 if test_pass else 0, "pass",
                "pass" if test_pass else "fail", "pytest plan scope"),
        _metric("deterministic_fail_closed", "Deterministic fail-closed policy", 1, "pass", "pass",
                "evaluation packet decision rule"),
        _metric("rag_golden_ci", "RAG golden CI", 1 if rag_golden_available else 0, "available",
                "pass" if rag_golden_available else "fail",
                "config/eval/rag_golden_queries.yaml" if rag_golden_available else "golden query set missing"),
        _metric("llm_judge_offline", "LLM judge offline CI", None, "warn then block", "measured_only",
                "calibrated judge dataset missing"),
    ]
    return {
        "status": _status(metrics),
        "metrics": metrics,
        "blocking_issues": _blocked(metrics),
        "ci_gate_matrix": {
            "unit-core": "block",
            "evaluation-gates": "block",
            "finance-regression": "block",
            "report-render-smoke": "block",
            "rag-golden": "warn",
            "llm-judge-offline": "warn",
            "integration-db": "scheduled",
        },
    }


Evaluator = Callable[[Path, str], dict[str, Any]]


def evaluate_plan(
    plan_id: str,
    *,
    root: Path,
    ticker: str,
    test_execution: dict[str, Any],
    prior_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    evaluators: dict[str, Evaluator] = {
        "01": evaluate_data_reliability,
        "02": evaluate_retrieval,
        "03": evaluate_financial,
        "04": evaluate_citation,
        "05": evaluate_agent,
        "07": evaluate_observability,
    }
    if plan_id == "06":
        return evaluate_report(root, ticker, prior_results.get("03", {}))
    if plan_id == "08":
        return evaluate_rollout(test_execution, prior_results)
    return evaluators[plan_id](root, ticker)
