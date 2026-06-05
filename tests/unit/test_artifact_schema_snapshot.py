"""Artifact schema snapshot tests (Phase 8).

Verifies that key artifact dataclasses produce to_dict() output with all
expected top-level keys. Any removal or rename of a key will fail these tests
immediately, catching silent schema regressions.

Tests use minimal synthetic inputs — no golden CSV, no DB, no network.
All tests run in < 0.5s each.
"""
from __future__ import annotations

import pytest


# ── ForecastArtifact schema ───────────────────────────────────────────────────

class TestForecastArtifactSchema:
    def _make(self):
        from backend.analytics.forecasting import run_forecast
        ft = {
            "revenue.net": {"2024FY": 1700.0, "2025FY": 1865.0},
            "gross_profit.total": {"2024FY": 780.0, "2025FY": 884.0},
            "sga.total": {"2024FY": -380.0, "2025FY": -418.0},
            "depreciation.total": {"2024FY": 44.0, "2025FY": 48.0},
            "capex.total": {"2024FY": -90.0, "2025FY": -100.0},
            "total_debt.ending": {"2025FY": 43.0},
            "cash_and_equivalents.ending": {"2025FY": 120.0},
            "equity.parent": {"2025FY": 1500.0},
            "total_assets.ending": {"2025FY": 2500.0},
            "profit_before_tax.total": {"2024FY": 320.0, "2025FY": 346.0},
            "tax_expense.total": {"2024FY": -55.0, "2025FY": -54.0},
            "net_income.parent": {"2024FY": 265.0, "2025FY": 292.0},
        }
        return run_forecast("TST", ft, shares_mn=94.45)

    def test_top_level_keys(self):
        d = self._make().to_dict()
        required = [
            "ticker", "historical_periods", "forecast_periods",
            "revenue_cagr_historical", "drivers", "assumption_status",
            "forecast_years", "warnings", "tax_policy",
            "dividend_schedule", "debt_schedule",
            "working_capital_schedule", "share_rollforward",
        ]
        for key in required:
            assert key in d, f"Missing key: {key}"

    def test_forecast_year_keys(self):
        d = self._make().to_dict()
        fy = d["forecast_years"][0]
        required = [
            "year", "label", "revenue", "cogs", "gross_profit",
            "gross_margin", "sga", "ebit", "ebit_margin",
            "depreciation", "ebitda", "interest_expense",
            "profit_before_tax", "tax_expense", "net_income",
            "net_margin", "capex", "eps",
            "beginning_debt", "ending_debt", "net_borrowing",
            "cash_dividend", "payout_ratio", "retained_earnings_addition",
            "delta_nwc", "net_working_capital", "diluted_shares",
        ]
        for key in required:
            assert key in fy, f"Missing forecast_year key: {key}"


# ── FCFFResult schema ─────────────────────────────────────────────────────────

class TestFCFFResultSchema:
    def _make(self):
        from backend.analytics.forecasting import run_forecast
        from backend.analytics.fcff import compute_fcff, WACCAssumptions
        ft = {
            "revenue.net": {"2024FY": 1700.0, "2025FY": 1865.0},
            "gross_profit.total": {"2024FY": 780.0, "2025FY": 884.0},
            "sga.total": {"2024FY": -380.0, "2025FY": -418.0},
            "depreciation.total": {"2025FY": 48.0},
            "capex.total": {"2025FY": -100.0},
            "total_debt.ending": {"2025FY": 43.0},
            "cash_and_equivalents.ending": {"2025FY": 120.0},
            "equity.parent": {"2025FY": 1500.0},
            "total_assets.ending": {"2025FY": 2500.0},
            "profit_before_tax.total": {"2025FY": 346.0},
            "tax_expense.total": {"2025FY": -54.0},
            "net_income.parent": {"2025FY": 292.0},
        }
        forecast = run_forecast("TST", ft, shares_mn=94.45)
        return compute_fcff("TST", forecast, ft, shares_mn=94.45,
                            wacc_assumptions=WACCAssumptions(wacc_override=0.13))

    def test_top_level_keys(self):
        d = self._make().to_dict()
        required = [
            "ticker", "wacc", "terminal_growth", "assumption_status",
            "wacc_breakdown", "fcff_table",
            "sum_pv_fcff", "terminal_value", "pv_terminal_value",
            "enterprise_value", "net_debt", "equity_value",
            "shares_mn", "target_price_vnd", "upside_pct",
            "net_debt_bridge", "warnings",
        ]
        for key in required:
            assert key in d, f"Missing FCFF key: {key}"

    def test_wacc_breakdown_keys(self):
        d = self._make().to_dict()
        wb = d["wacc_breakdown"]
        for k in ["risk_free_rate", "beta", "cost_of_equity", "cost_of_debt", "tax_rate"]:
            assert k in wb

    def test_net_debt_bridge_keys(self):
        d = self._make().to_dict()
        ndb = d["net_debt_bridge"]
        assert ndb is not None
        for k in ["status", "net_debt", "total_debt", "cash", "formula"]:
            assert k in ndb


# ── BlendResult schema ────────────────────────────────────────────────────────

class TestBlendResultSchema:
    def test_top_level_keys(self):
        from backend.analytics.blend import blend_dcf
        result = blend_dcf("TST", 60_000.0, 55_000.0, 50_000.0)
        d = result.to_dict()
        required = [
            "ticker", "price_fcff_vnd", "price_pe_forward_vnd",
            "target_price_dcf_vnd", "current_price_vnd",
            "upside_pct", "is_draft_only", "valuation_gap_pct", "warnings",
        ]
        for key in required:
            assert key in d, f"Missing blend key: {key}"


# ── DebtSchedule schema ───────────────────────────────────────────────────────

class TestDebtScheduleSchema:
    def test_top_level_keys(self):
        from backend.analytics.debt_schedule import build_debt_schedule
        ft = {"total_debt.ending": {"2024FY": 50.0, "2025FY": 43.0}}
        ds = build_debt_schedule("TST", ft, ["2024FY", "2025FY"],
                                 ["2026F", "2027F"], [2026, 2027])
        d = ds.to_dict()
        required = [
            "ticker", "forecast_method", "is_fcfe_publishable",
            "fcfe_block_reason", "historical_rows", "forecast_rows", "warnings",
        ]
        for key in required:
            assert key in d, f"Missing DebtSchedule key: {key}"


# ── NetDebtBridge schema ──────────────────────────────────────────────────────

class TestNetDebtBridgeSchema:
    def test_schema_keys(self):
        from backend.analytics.net_debt_bridge import build_net_debt_bridge
        ft = {
            "total_debt.ending": {"2025FY": 175.0},
            "cash_and_equivalents.ending": {"2025FY": 200.0},
        }
        d = build_net_debt_bridge(ft, "2025FY").to_dict()
        required = ["period", "total_debt", "cash", "net_debt",
                    "status", "warnings", "missing_fields", "formula"]
        for key in required:
            assert key in d, f"Missing NetDebtBridge key: {key}"


# ── ReportArtifact schema ─────────────────────────────────────────────────────

class TestReportArtifactSchema:
    def test_schema_keys(self):
        from backend.reporting.report_artifact import ReportArtifact
        art = ReportArtifact(
            report_id="r1", ticker="TST", run_id="ts",
            report_date="2026-06-04", render_mode="analyst_draft", sections=[],
        )
        d = art.to_dict()
        required = [
            "report_id", "ticker", "run_id", "report_date", "render_mode",
            "recommendation", "target_price_vnd", "total_word_count",
            "missing_sections", "sections", "charts",
            "gate_results", "is_final_exportable", "all_missing_data_flags",
            "created_at", "warnings",
        ]
        for key in required:
            assert key in d, f"Missing ReportArtifact key: {key}"


# ── ExportGateResult schema ───────────────────────────────────────────────────

class TestExportGateResultSchema:
    def test_schema_keys(self):
        from backend.reporting.report_artifact import ReportArtifact
        from backend.reporting.export_gate import evaluate_export_gate
        art = ReportArtifact(
            report_id="r1", ticker="TST", run_id="ts",
            report_date="2026-06-04", render_mode="analyst_draft", sections=[],
        )
        result = evaluate_export_gate(art)
        d = result.to_dict()
        required = [
            "ticker", "report_id", "render_mode", "is_final_exportable",
            "blocking_gates", "gate_summary", "gates", "created_at", "warnings",
        ]
        for key in required:
            assert key in d, f"Missing ExportGateResult key: {key}"

    def test_all_9_gates_present(self):
        from backend.reporting.report_artifact import ReportArtifact
        from backend.reporting.export_gate import evaluate_export_gate, GATE_NAMES
        art = ReportArtifact(
            report_id="r1", ticker="TST", run_id="ts",
            report_date="2026-06-04", render_mode="analyst_draft", sections=[],
        )
        result = evaluate_export_gate(art)
        for name in GATE_NAMES:
            assert name in result.gates, f"Gate missing: {name}"


# ── ClaimLedger schema ────────────────────────────────────────────────────────

class TestClaimLedgerSchema:
    def test_schema_keys(self):
        from backend.citations.claim_ledger import ClaimLedger, claim_from_fact
        ledger = ClaimLedger(ticker="TST", report_id="r1")
        claim_from_fact(ledger, "Revenue 1865 bn", "financial_performance",
                        "f1", "s1", "revenue.net", "2025FY", 1865.0, "VND bn", 0)
        d = ledger.to_dict()
        required = ["ticker", "report_id", "total_claims", "summary", "claims"]
        for key in required:
            assert key in d, f"Missing ClaimLedger key: {key}"

    def test_citation_gate_result_keys(self):
        from backend.citations.claim_ledger import ClaimLedger
        ledger = ClaimLedger(ticker="TST", report_id="r1")
        ledger.add_claim("financial_fact", "unsupported claim", "overview")
        gate = ledger.citation_gate()
        for key in ["status", "total_claims", "unsupported_count", "partial_count", "issues"]:
            assert key in gate, f"Missing citation_gate key: {key}"


# ── WorkingCapitalSchedule schema ─────────────────────────────────────────────

class TestWorkingCapitalScheduleSchema:
    def test_schema_keys(self):
        from backend.analytics.working_capital_schedule import build_working_capital_schedule
        ft = {
            "accounts_receivable.ending": {"2025FY": 500.0},
            "inventory.ending": {"2025FY": 400.0},
            "accounts_payable.ending": {"2025FY": 150.0},
            "revenue.net": {"2025FY": 1865.0},
            "cogs.total": {"2025FY": -981.0},
        }
        sched = build_working_capital_schedule(
            "TST", ft, ["2025FY"], ["2026F"],
            {"2026F": 2000.0}, {"2026F": -1050.0},
        )
        d = sched.to_dict()
        for key in ["ticker", "ar_days", "inv_days", "ap_days",
                    "historical_rows", "forecast_rows", "warnings"]:
            assert key in d, f"Missing WC schedule key: {key}"


# ── ShareRollForward schema ───────────────────────────────────────────────────

class TestShareRollForwardSchema:
    def test_schema_keys(self):
        from backend.analytics.share_rollforward import build_share_rollforward
        ft = {"shares_outstanding.ending": {"2025FY": {"value": 94_400_000.0}}}
        sr = build_share_rollforward("TST", ft, ["2025FY"], ["2026F"])
        d = sr.to_dict()
        for key in ["ticker", "base_shares_mn", "forecast_rows", "warnings"]:
            assert key in d, f"Missing ShareRollForward key: {key}"

    def test_forecast_row_keys(self):
        from backend.analytics.share_rollforward import build_share_rollforward
        ft = {"shares_outstanding.ending": {"2025FY": {"value": 94_400_000.0}}}
        sr = build_share_rollforward("TST", ft, ["2025FY"], ["2026F"])
        row = sr.to_dict()["forecast_rows"][0]
        for key in ["label", "beginning_shares_mn", "ending_shares_mn",
                    "diluted_shares_mn", "method"]:
            assert key in row, f"Missing ShareRollRow key: {key}"


# ── ScenarioSummary schema ────────────────────────────────────────────────────

class TestScenarioSummarySchema:
    def test_schema_keys(self):
        from backend.analytics.scenario_runner import run_scenarios
        ft = {
            "revenue.net": {"2024FY": 1700.0, "2025FY": 1865.0},
            "gross_profit.total": {"2024FY": 780.0, "2025FY": 884.0},
            "sga.total": {"2024FY": -380.0, "2025FY": -418.0},
            "depreciation.total": {"2025FY": 48.0},
            "capex.total": {"2025FY": -100.0},
            "total_debt.ending": {"2025FY": 43.0},
            "cash_and_equivalents.ending": {"2025FY": 120.0},
            "equity.parent": {"2025FY": 1500.0},
            "total_assets.ending": {"2025FY": 2500.0},
            "profit_before_tax.total": {"2025FY": 346.0},
            "tax_expense.total": {"2025FY": -54.0},
            "net_income.parent": {"2025FY": 292.0},
        }
        summary = run_scenarios("TST", ft, shares_mn=94.45)
        d = summary.to_dict()
        for key in ["ticker", "bear", "base", "bull"]:
            assert key in d, f"Missing ScenarioSummary key: {key}"
        pr = summary.price_range()
        for key in ["min_price", "max_price", "base_price"]:
            assert key in pr, f"Missing price_range key: {key}"
