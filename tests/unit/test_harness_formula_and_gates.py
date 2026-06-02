from __future__ import annotations

from backend.harness.gates import evidence_packet_gate, financial_analyst_gate, formula_trace_gate
from backend.harness.state import FormulaTrace, ResearchGraphState
from backend.harness.tools import read_snapshot_tool, run_valuation_tool


def _trace(formula_id: str) -> dict:
    return FormulaTrace(
        trace_id=f"trace_{formula_id}",
        formula_id=formula_id,
        formula_version="valuation_v1",
        output_name=formula_id,
        output_value=1,
        unit="ratio",
        period="2025FY",
        input_fact_ids=["fact_001"],
        input_values={"input": 1},
        calculation_steps=[{"step": "deterministic calculation", "value": 1}],
    ).model_dump(mode="json")


def test_financial_analyst_gate_requires_metric_period_and_artifact_refs() -> None:
    assert not financial_analyst_gate({
        "status": "completed",
        "payload": {"metric_refs": ["revenue.net"], "period_refs": ["2025FY"]},
        "input_summary": {"input_refs": ["snapshot_fact_report"]},
    })["passed"]

    assert financial_analyst_gate({
        "status": "completed",
        "payload": {"metric_refs": ["revenue.net"], "period_refs": ["2025FY"]},
        "input_summary": {"input_refs": ["snapshot_fact_report", "ratio_artifact"]},
    })["passed"]


def test_financial_snapshot_tool_blocks_without_explicit_snapshot_id() -> None:
    result = read_snapshot_tool("DHG", None)

    assert result.status == "failed"
    assert result.blocking_reason == "snapshot_id_missing"


def test_run_valuation_tool_exposes_formula_trace_status(monkeypatch, tmp_path) -> None:
    artifact_path = tmp_path / "DHG_valuation.json"
    artifact = {
        "ticker": "DHG",
        "snapshot_id": "snap1",
        "artifact_path": str(artifact_path),
        "formula_version": "valuation_v1",
        "assumption_version": "assumptions_v1",
        "unit_policy": "VND",
        "currency": "VND",
        "period_scope": {"period_type": "FY"},
        "valuation_methods": ["fcff", "fcfe", "blend"],
        "fcff": {"target": 1},
        "fcfe": {"target": 1},
        "blend_dcf": {"target": 1},
        "sensitivity": {"fcff_wacc_g": {"matrix": [[1]]}},
        "assumptions": {"wacc": 0.1},
        "assumption_gate": {},
        "formula_traces": [_trace("fcff"), _trace("fcfe"), _trace("wacc")],
    }
    monkeypatch.setattr("scripts.run_valuation.run_valuation", lambda **kwargs: artifact)

    result = run_valuation_tool("DHG", 2021, 2025)

    assert result.summary["formula_trace_status"] == "present"
    assert result.summary["formula_trace_count"] == 3
    assert result.summary["missing_formula_trace_count"] == 0
    assert result.summary["formula_traces"]


def test_formula_and_evidence_packet_gates_block_missing_traces() -> None:
    valuation = {"snapshot_id": "snap1", "formula_trace_status": "missing", "formula_traces": []}
    state = ResearchGraphState(run_id="run_formula_gate", ticker="DHG", objective="formula gate")
    state.valuation_outputs = valuation
    state.artifact_refs.append({
        "artifact_id": "run_formula_gate_evidence_packet",
        "artifact_type": "evidence_packet_json",
        "section_key": "evidence_packet",
        "storage_path": "artifacts/evidence_packets/run_formula_gate.json",
    })

    assert not formula_trace_gate(valuation)["passed"]
    assert not evidence_packet_gate(state.model_dump(mode="json"))["passed"]
