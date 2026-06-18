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


def _publishable_policy_fields(target: float = 100_000) -> dict:
    return {
        "current_price_vnd": target,
        "valuation_confidence": {"fcff_dcf": "high", "fcfe_dcf": "high"},
        "formula_traces": [{"method": "fcff"}, {"method": "fcfe"}],
        "sensitivity": {
            "fcff_wacc_g": {
                "wacc_0.11": {"g_0.02": target * 1.05, "g_0.03": target},
                "wacc_0.12": {"g_0.02": target, "g_0.03": target * 0.95},
            },
            "fcfe_re_g": {
                "re_0.11": {"g_0.02": target * 1.04, "g_0.03": target},
                "re_0.12": {"g_0.02": target, "g_0.03": target * 0.96},
            },
            "blend_grid": {
                str(target * 0.95): {str(target * 0.95): target * 0.95},
                str(target): {str(target): target},
            },
        },
    }


def _passing_gate_inputs() -> dict:
    val = {
        **_publishable_policy_fields(),
        "blend_dcf": {
            "price_fcff_vnd": 100_000,
            "price_fcfe_vnd": 100_000,
            "target_price_dcf_vnd": 100_000,
            "current_price_vnd": 100_000,
            "is_draft_only": False,
        },
        "fcff": {
            "shares_mn": 100,
            "target_price_vnd": 100_000,
            "wacc": 0.12,
            "terminal_growth": 0.03,
            "wacc_breakdown": {"risk_free_rate": 0.04},
            "enterprise_value": 1000,
            "equity_value": 800,
            "net_debt_bridge": {"status": "ok"},
            "ev_to_equity_bridge": {"ev": 1000},
        },
        "fcfe": {
            "target_price_vnd": 100_000,
            "fcfe_table": [{"fcfe": 100, "net_borrowing": 0}],
            "equity_value": 750,
            "cost_of_equity": 0.12,
            "cost_of_equity_breakdown": {"risk_free_rate": 0.04},
            "terminal_growth": 0.03,
        },
        "fcff_sensitivity": {
            "matrix": [
                [92_000, 96_000, 100_000],
                [96_000, 100_000, 104_000],
                [100_000, 104_000, 108_000],
            ],
            "base_wacc": 0.12,
            "base_terminal_growth": 0.03,
            "wacc_range": [0.11, 0.12, 0.13],
            "terminal_growth_range": [0.02, 0.03, 0.04],
        },
        "fcfe_sensitivity": {
            "matrix": [
                [92_000, 96_000, 100_000],
                [96_000, 100_000, 104_000],
                [100_000, 104_000, 108_000],
            ],
            "base_re": 0.12,
            "base_terminal_growth": 0.03,
            "re_range": [0.11, 0.12, 0.13],
            "terminal_growth_range": [0.02, 0.03, 0.04],
        },
        "blend_sensitivity": {
            "matrix": [
                [96_000, 98_000, 100_000],
                [98_000, 100_000, 102_000],
                [100_000, 102_000, 104_000],
            ],
            "price_fcff_range": [95_000, 100_000, 105_000],
            "price_fcfe_range": [95_000, 100_000, 105_000],
        },
    }
    forecast = {
        "forecast_years": [
            {
                "label": "FY2026E",
                "revenue": 1_000,
                "net_income": 100,
                "eps": 1000,
                "diluted_shares": 100,
            },
            {
                "label": "FY2027E",
                "revenue": 1_040,
                "net_income": 104,
                "eps": 1040,
                "diluted_shares": 100,
            },
        ],
        "working_capital_schedule": {"delta_nwc": [10, 20]},
        "debt_schedule": {"is_fcfe_publishable": True},
        "dividend_schedule": {"policy": "explicit payout", "payout_ratio": 0.30},
    }
    source_manifest = {"untraced_valuation_facts": [], "tier3_only_valuation_facts": []}
    recon = {"material_conflicts": []}
    claim_ledger = {"summary": {"unsupported": 0, "partial": 0}}

    from backend.reporting.layout_audit import LayoutRenderAudit

    layout = LayoutRenderAudit(ticker="TEST", report_id="test_001", render_mode="client_final")
    return {
        "valuation_artifact": val,
        "forecast_artifact": forecast,
        "source_manifest": source_manifest,
        "reconciliation_artifact": recon,
        "claim_ledger": claim_ledger,
        "layout_audit": layout,
        "approval_status": "approved",
    }


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
            **_publishable_policy_fields(target=5),
            "blend_dcf": {
                "price_fcff_vnd": 5,
                "price_fcfe_vnd": 5,
                "target_price_dcf_vnd": 5,
                "current_price_vnd": 5,
                "is_draft_only": False,
            },
            "fcff": {
                "shares_mn": 100,
                "target_price_vnd": 5,
                "wacc": 0.12,
                "terminal_growth": 0.03,
                "wacc_breakdown": {"risk_free_rate": 0.04},
                "enterprise_value": 1000,
                "equity_value": 800,
                "net_debt_bridge": {"status": "ok"},
                "ev_to_equity_bridge": {"ev": 1000},
            },
            "fcfe": {
                "target_price_vnd": 5,
                "fcfe_table": [{"fcfe": 1, "net_borrowing": 0}],
                "equity_value": 750,
                "cost_of_equity": 0.12,
                "cost_of_equity_breakdown": {"risk_free_rate": 0.04},
                "terminal_growth": 0.03,
            },
            "fcff_sensitivity": {
                "matrix": [[1, 2, 3], [4, 5, 6], [7, 5, 9]],
                "base_terminal_growth": 0.03,
                "base_wacc": 0.12,
                "wacc_range": [0.10, 0.11, 0.12, 0.13, 0.14],
                "terminal_growth_range": [0.02, 0.03, 0.04],
            },
            "fcfe_sensitivity": {
                "matrix": [[1, 2, 3], [4, 5, 6], [7, 5, 9]],
                "base_terminal_growth": 0.03,
                "base_re": 0.12,
                "re_range": [0.10, 0.11, 0.12, 0.13, 0.14],
                "terminal_growth_range": [0.02, 0.03, 0.04],
            },
            "blend_sensitivity": {
                "matrix": [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
                "price_fcff_range": [4, 5, 6],
                "price_fcfe_range": [4, 5, 6],
            },
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


class TestForecastAndValuationAnomalyGates:
    """Regression tests for DHG-style financial model red flags."""

    def test_profit_growth_outlier_blocks_final_export_without_margin_bridge(self):
        artifact = _make_artifact()
        inputs = _passing_gate_inputs()
        inputs["forecast_artifact"]["forecast_years"] = [
            {
                "label": "FY2025A",
                "revenue": 1_000,
                "net_income": 100,
                "eps": 1000,
                "diluted_shares": 100,
            },
            {
                "label": "FY2026E",
                "revenue": 1_040,
                "net_income": 153,
                "eps": 1530,
                "diluted_shares": 100,
            },
        ]

        result = evaluate_export_gate(artifact, **inputs)

        forecast_gate = result.gate("forecast_gate")
        assert forecast_gate is not None
        assert forecast_gate.status == "FAIL"
        assert any("net income growth" in issue for issue in forecast_gate.issues)
        assert result.is_final_exportable is False

    def test_cash_accumulation_without_dividend_policy_blocks_final_export(self):
        artifact = _make_artifact()
        inputs = _passing_gate_inputs()
        inputs["forecast_artifact"]["dividend_schedule"] = {}
        inputs["forecast_artifact"]["forecast_years"] = [
            {
                "label": "FY2026E",
                "revenue": 1_000,
                "net_income": 100,
                "cash": 800,
                "eps": 1000,
                "diluted_shares": 100,
            },
            {
                "label": "FY2027E",
                "revenue": 1_040,
                "net_income": 104,
                "cash": 950,
                "eps": 1040,
                "diluted_shares": 100,
            },
            {
                "label": "FY2028E",
                "revenue": 1_082,
                "net_income": 108,
                "cash": 1_100,
                "eps": 1080,
                "diluted_shares": 100,
            },
        ]

        result = evaluate_export_gate(artifact, **inputs)

        forecast_gate = result.gate("forecast_gate")
        assert forecast_gate is not None
        assert forecast_gate.status == "FAIL"
        assert any("cash accumulation anomaly" in issue for issue in forecast_gate.issues)
        assert result.is_final_exportable is False

    def test_sensitivity_base_cell_must_match_target_price(self):
        artifact = _make_artifact()
        inputs = _passing_gate_inputs()
        inputs["valuation_artifact"]["fcff_sensitivity"]["matrix"][1][1] = 90_000

        result = evaluate_export_gate(artifact, **inputs)

        sensitivity_gate = result.gate("sensitivity_gate")
        assert sensitivity_gate is not None
        assert sensitivity_gate.status == "FAIL"
        assert any("fcff sensitivity base cell" in issue for issue in sensitivity_gate.issues)
        assert result.is_final_exportable is False

    def test_current_sensitivity_artifact_shape_passes(self):
        artifact = _make_artifact()
        inputs = _passing_gate_inputs()
        inputs["valuation_artifact"].pop("fcff_sensitivity")
        inputs["valuation_artifact"].pop("fcfe_sensitivity")
        inputs["valuation_artifact"].pop("blend_sensitivity")
        inputs["valuation_artifact"]["sensitivity"] = {
            "fcff_wacc_g": {
                "matrix": {"0.120": {"0.030": 100_000}},
                "base_wacc": 0.12,
                "base_terminal_growth": 0.03,
                "wacc_range": [0.12],
                "g_range": [0.03],
            },
            "fcfe_re_g": {
                "matrix": {"0.120": {"0.030": 100_000}},
                "base_re": 0.12,
                "base_terminal_growth": 0.03,
                "re_range": [0.12],
                "g_range": [0.03],
            },
            "blend_grid": {
                "matrix": {"100000": {"100000": 100_000}},
                "price_fcff_range": [100_000],
                "price_fcfe_range": [100_000],
            },
        }

        result = evaluate_export_gate(artifact, **inputs)

        sensitivity_gate = result.gate("sensitivity_gate")
        assert sensitivity_gate is not None
        assert sensitivity_gate.status == "PASS"

    def test_missing_fcfe_sensitivity_blocks_final_export(self):
        artifact = _make_artifact()
        inputs = _passing_gate_inputs()
        inputs["valuation_artifact"].pop("fcfe_sensitivity")

        result = evaluate_export_gate(artifact, **inputs)

        sensitivity_gate = result.gate("sensitivity_gate")
        assert sensitivity_gate is not None
        assert sensitivity_gate.status == "FAIL"
        assert any("fcfe_sensitivity matrix missing" in issue for issue in sensitivity_gate.issues)
        assert result.is_final_exportable is False

    def test_publishability_policy_blocks_failed_method_weight(self):
        artifact = _make_artifact()
        inputs = _passing_gate_inputs()
        inputs["valuation_artifact"]["fcfe"] = {
            "target_price_vnd": None,
            "fcfe_table": [{"fcfe": None, "net_borrowing": None}],
            "equity_value": None,
        }
        inputs["valuation_artifact"]["blend_dcf"] = {
            "price_fcff_vnd": 100_000,
            "price_fcfe_vnd": None,
            "target_price_dcf_vnd": 100_000,
            "current_price_vnd": 100_000,
            "is_draft_only": False,
        }
        inputs["valuation_artifact"]["valuation_confidence"]["fcfe_dcf"] = "blocked"
        inputs["valuation_artifact"]["method_weights"] = {"FCFF": 60.0, "FCFE": 40.0}

        result = evaluate_export_gate(artifact, **inputs)

        valuation_gate = result.gate("valuation_gate")
        assert valuation_gate is not None
        assert valuation_gate.status == "FAIL"
        assert any("failed_method_has_nonzero_weight:FCFE" in issue for issue in valuation_gate.issues)
        assert result.is_final_exportable is False
