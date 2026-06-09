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


class TestExportGateControlsRender:
    """Spec §2.9: export gate result determines whether HTML/PDF are created."""

    def test_failed_gate_means_no_final_export(self):
        artifact = _make_artifact()
        # No approval → human_review_gate FAIL
        result = evaluate_export_gate(artifact, approval_status=None)
        assert result.is_final_exportable is False
        assert result.render_mode == "analyst_draft"

    def test_all_pass_means_client_final(self):
        artifact = _make_artifact()
        val = {
            "blend_dcf": {},
            "fcff": {"shares_mn": 100, "wacc": 0.12, "terminal_growth": 0.03, "enterprise_value": 1000, "equity_value": 800},
            "fcfe": {"equity_value": 750, "cost_of_equity": 0.12, "terminal_growth": 0.03},
            "fcff_sensitivity": {
                "matrix": [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
                "base_wacc": 0.12,
                "wacc_range": [0.10, 0.11, 0.12, 0.13, 0.14]
            }
        }
        forecast = {
            "forecast_years": [
                {"label": "FY2026E", "eps": 1000, "net_income": 100, "diluted_shares": 100},
                {"label": "FY2027E", "eps": 1100, "net_income": 110, "diluted_shares": 100},
                {"label": "FY2028E", "eps": 1200, "net_income": 120, "diluted_shares": 100},
            ],
            "working_capital_schedule": {
                "delta_nwc": [10, 20, 30]
            },
            "debt_schedule": {
                "is_fcfe_publishable": True
            }
        }
        source_manifest = {"untraced_valuation_facts": [], "tier3_only_valuation_facts": []}
        recon = {"material_conflicts": []}
        claim_ledger = {"summary": {"unsupported": 0, "partial": 0}}

        from backend.reporting.layout_audit import LayoutRenderAudit
        layout = LayoutRenderAudit(ticker="TEST", report_id="test_001", render_mode="client_final")

        result = evaluate_export_gate(
            artifact,
            valuation_artifact=val,
            forecast_artifact=forecast,
            source_manifest=source_manifest,
            reconciliation_artifact=recon,
            claim_ledger=claim_ledger,
            layout_audit=layout,
            approval_status="approved",
        )
        assert result.is_final_exportable is True
        assert result.render_mode == "client_final"
