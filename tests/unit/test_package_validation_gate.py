from __future__ import annotations

import backend.harness.gates as gates


def _patch_all_pass(monkeypatch):
    monkeypatch.setattr(gates, "tool_permission_gate", lambda t: gates.pass_gate("TOOL_PERMISSION_GATE"))
    monkeypatch.setattr(gates, "artifact_manifest_gate", lambda s: gates.pass_gate("ARTIFACT_MANIFEST_GATE"))
    monkeypatch.setattr(gates, "formula_trace_gate", lambda v: gates.pass_gate("FORMULA_TRACE_GATE"))
    monkeypatch.setattr(gates, "evidence_packet_gate", lambda s: gates.pass_gate("EVIDENCE_PACKET_GATE"))
    monkeypatch.setattr(gates, "workflow_export_gate", lambda s, **k: gates.pass_gate("EXPORT_GATE"))
    monkeypatch.setattr(
        "backend.evaluation.report_quality.report_quality_gate",
        lambda s: gates.pass_gate("REPORT_QUALITY_GATE", {"score": 100, "decision": "allow_export"}),
    )


def test_package_validation_gate_passes_when_all_subgates_pass(monkeypatch):
    _patch_all_pass(monkeypatch)
    result = gates.package_validation_gate({"gate_results": {}})
    assert result["gate"] == "PACKAGE_VALIDATION_GATE"
    assert result["passed"] is True


def test_package_validation_gate_aggregates_subgate_failure(monkeypatch):
    _patch_all_pass(monkeypatch)
    monkeypatch.setattr(
        gates, "evidence_packet_gate",
        lambda s: gates.fail_gate("EVIDENCE_PACKET_GATE", "evidence_packet_missing"),
    )
    result = gates.package_validation_gate({"gate_results": {}})
    assert result["passed"] is False
    assert any("evidence_packet_missing" in r for r in result["blocking_reasons"])


def test_package_validation_gate_surfaces_export_aggregation(monkeypatch):
    _patch_all_pass(monkeypatch)
    monkeypatch.setattr(
        gates, "workflow_export_gate",
        lambda s, **k: gates.fail_gate("EXPORT_GATE", "report_not_linked_to_valuation_snapshot"),
    )
    result = gates.package_validation_gate({"gate_results": {}})
    assert result["passed"] is False
    assert any("report_not_linked_to_valuation_snapshot" in r for r in result["blocking_reasons"])
