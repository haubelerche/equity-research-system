from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.harness.state import ResearchGraphState, stable_hash

SCHEMA_VERSION = 1


def build_evidence_packet(state: ResearchGraphState) -> dict[str, Any]:
    periods = [f"{year}FY" for year in range(state.from_year, state.to_year + 1)]
    artifacts = state.artifacts or {}
    report = state.draft_report or artifacts.get("report", {})
    packet = {
        "schema_version": SCHEMA_VERSION,
        "run_id": state.run_id,
        "ticker": state.ticker,
        "periods": periods,
        "source_documents": _as_list(artifacts.get("auto_ingest", {}).get("documents")),
        "canonical_facts": _as_list(artifacts.get("build_facts", {}).get("facts")),
        "reconciliation_results": _as_list(artifacts.get("build_facts", {}).get("reconciliation_results")),
        "formula_traces": _as_list((state.valuation_outputs or {}).get("formula_traces")),
        "forecast_assumptions": _as_list((state.valuation_outputs or {}).get("assumptions")),
        "valuation_outputs": state.valuation_outputs or artifacts.get("valuation", {}),
        "citation_map": report.get("citation_map", {}),
        "artifact_refs": state.artifact_refs,
        "evidence_refs": state.evidence_refs,
        "gate_results": state.gate_results,
        "quality_gate_results": state.evaluation_results or artifacts.get("quality", {}),
        "known_limitations": _known_limitations(state),
        "tool_execution_summary": _tool_execution_summary(state.trace),
        "trace_summary": _trace_summary(state.trace),
        "created_at": datetime.now(UTC).isoformat(),
    }
    packet["packet_hash"] = stable_hash({k: v for k, v in packet.items() if k not in ("packet_hash", "created_at")})
    return packet


def write_evidence_packet(state: ResearchGraphState, base_dir: Path) -> Path:
    packet = build_evidence_packet(state)
    target_dir = Path(base_dir) / "evidence_packets"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{state.run_id}_evidence_packet.json"
    path.write_text(json.dumps(packet, indent=2, default=str), encoding="utf-8")
    return path


def build_agent_effectiveness_audit(state: ResearchGraphState) -> dict[str, Any]:
    """Derive the agent-effectiveness audit from a real run's trace and state.

    Benchmark plan 05 ("Agent workflow and LLM judge") scores tool-permission
    compliance, artifact-manifest compliance, task completion and unauthorized
    financial calculation from this audit. Historically it had no producer and
    was scored against a hand-made stub; this builder makes it a real, governed
    by-product of every run so the benchmark measures the actual pipeline.
    """
    trace = state.trace or []
    agent_messages = [item for item in trace if item.get("kind") == "agent_message"]
    tool_calls = [item for item in trace if item.get("kind") == "tool_call"]

    agent_execution = [
        {
            "agent_id": item.get("agent_id") or item.get("agent_role"),
            "action": item.get("action"),
            "status": item.get("status"),
            "latency_ms": item.get("latency_ms"),
            "cost_estimate": item.get("cost_estimate"),
            "confidence": item.get("confidence"),
            "warnings": list(item.get("warnings") or []),
            "requires_human": item.get("next_action") in {"request_human_review", "human_review"},
            "fallback_triggered": bool(item.get("fallback_triggered")),
            "output_summary": item.get("output_summary") or {},
        }
        for item in agent_messages
    ]
    tool_execution = [
        {
            "tool_name": item.get("tool_name"),
            "agent_role": item.get("agent_role"),
            "output_hash": item.get("output_hash"),
            "output_summary": item.get("output_summary") or {},
        }
        for item in tool_calls
    ]

    audit = {
        "schema_version": SCHEMA_VERSION,
        "run_id": state.run_id,
        "ticker": state.ticker,
        "generated_at": datetime.now(UTC).isoformat(),
        "current_stage": state.current_stage,
        "status": state.status,
        "requires_human": state.status == "blocked",
        "blocking_reason": state.blocking_reason,
        "tool_execution": tool_execution,
        "agent_execution": agent_execution,
        "data_retrieval_effectiveness": _data_retrieval_effectiveness(state),
        "financial_analyst_effectiveness": _financial_analyst_effectiveness(state),
        "report_writer_effectiveness": _report_writer_effectiveness(state),
    }
    return audit


def write_agent_effectiveness_audit(state: ResearchGraphState, base_dir: Path) -> Path:
    audit = build_agent_effectiveness_audit(state)
    target_dir = Path(base_dir) / "audits"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{state.run_id}_agent_effectiveness_audit.json"
    path.write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")
    return path


def _data_retrieval_effectiveness(state: ResearchGraphState) -> dict[str, Any]:
    auto_ingest = (state.artifacts or {}).get("auto_ingest") or {}
    facts = (state.artifacts or {}).get("build_facts") or {}
    return {
        "documents": len(_as_list(auto_ingest.get("documents"))),
        "canonical_facts": len(_as_list(facts.get("facts"))),
        "official_ready": bool(auto_ingest.get("official_ready")),
    }


def _financial_analyst_effectiveness(state: ResearchGraphState) -> dict[str, Any]:
    tables = state.financial_tables or {}
    return {
        "payload_keys": sorted(str(key) for key in tables),
        "snapshot_id": state.snapshot_id,
    }


def _report_writer_effectiveness(state: ResearchGraphState) -> dict[str, Any]:
    report = state.draft_report or (state.artifacts or {}).get("report") or {}
    quality = state.evaluation_results or {}
    return {
        "claims_count": len(_as_list(report.get("claims"))),
        "citation_count": len(report.get("citation_map") or {}),
        "quality_status": quality.get("decision") or quality.get("overall_status"),
        "blocking_reason": state.blocking_reason,
    }


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _known_limitations(state: ResearchGraphState) -> list[str]:
    limitations: list[str] = []
    if state.blocking_reason:
        limitations.append(state.blocking_reason)
    limitations.extend(str(err) for err in state.errors)
    for gate in state.gate_results.values():
        if isinstance(gate, dict) and gate.get("passed") is False:
            limitations.extend(str(reason) for reason in gate.get("blocking_reasons", []))
    return sorted(set(limitations))


def _trace_summary(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for item in trace:
        summary.append({
            "kind": item.get("kind"),
            "agent_role": item.get("agent_role") or item.get("agent_id"),
            "tool_name": item.get("tool_name"),
            "status": item.get("status"),
            "output_hash": item.get("output_hash"),
        })
    return summary


def _tool_execution_summary(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "tool_name": item.get("tool_name"),
            "agent_role": item.get("agent_role"),
            "output_hash": item.get("output_hash"),
            "permission": (item.get("gate_inputs") or {}).get("tool_permission", {}),
        }
        for item in trace
        if item.get("kind") == "tool_call"
    ]
