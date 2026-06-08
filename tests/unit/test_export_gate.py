"""Tests for export gate safety: SKIP must block export."""
from __future__ import annotations

import pytest

from backend.reporting.export_gate import (
    ExportGateResult,
    GateResult,
    evaluate_export_gate,
)
from backend.reporting.report_artifact import ReportArtifact


def _make_artifact(ticker: str = "TEST") -> ReportArtifact:
    return ReportArtifact(
        report_id="test_001",
        ticker=ticker,
        run_id="run_001",
        report_date="2026-06-08",
        render_mode="analyst_draft",
        sections=[],
    )


class TestGateSkipIsFail:
    """Spec §1.1: Any gate returning SKIP must have passed=false and block export."""

    def test_skip_gate_has_passed_false(self):
        g = GateResult("source_gate", "SKIP", ["no data provided"])
        assert g.passed is False, "SKIP gate must have passed=False"

    def test_skip_gate_blocks_export(self):
        artifact = _make_artifact()
        # source_manifest=None → source_gate returns SKIP
        # claim_ledger=None → citation_gate returns SKIP
        # layout_audit=None → layout_gate returns SKIP
        result = evaluate_export_gate(artifact)
        skip_gates = [
            name for name, g in result.gates.items()
            if g.status == "SKIP"
        ]
        assert len(skip_gates) > 0, "Expected at least one SKIP gate"
        assert result.is_final_exportable is False, (
            f"SKIP gates {skip_gates} must block export"
        )
        for name in skip_gates:
            assert name in result.blocking_gates, (
                f"SKIP gate {name!r} must appear in blocking_gates"
            )
        # Verify gate_skipped:{name} reason format
        assert any("gate_skipped:" in w for w in result.warnings), (
            f"Expected gate_skipped:{{name}} in warnings, got: {result.warnings}"
        )
