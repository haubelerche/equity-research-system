"""Tests for backend.analytics.approval_gate (P0-03)."""
from __future__ import annotations

import pytest
from backend.analytics.approval_gate import AssumptionGate, build_gate_from_artifacts


class TestAssumptionGateEvaluation:
    def _all_approved_gate(self) -> AssumptionGate:
        return AssumptionGate(
            data_quality_passed=True,
            tax_policy_approved=True,
            wacc_approved=True,
            cost_of_equity_approved=True,
            terminal_growth_approved=True,
            forecast_assumptions_approved=True,
            debt_schedule_approved=True,
            dividend_schedule_approved=True,
            peer_multiples_approved=True,
            final_recommendation_approved=True,
        ).evaluate()

    def test_fully_approved_gate_is_approved_for_publish(self):
        gate = self._all_approved_gate()
        assert gate.status == "approved_for_publish"
        assert gate.recommendation_allowed is True
        assert gate.blocking_reasons == []

    def test_wacc_pending_blocks_recommendation(self):
        gate = AssumptionGate(
            data_quality_passed=True,
            tax_policy_approved=True,
            wacc_approved=False,  # pending
            cost_of_equity_approved=True,
            terminal_growth_approved=True,
            forecast_assumptions_approved=True,
            debt_schedule_approved=True,
            final_recommendation_approved=False,
        ).evaluate()
        assert gate.recommendation_allowed is False
        assert gate.status == "draft_needs_analyst_review"
        assert any("WACC" in r for r in gate.blocking_reasons)

    def test_debt_schedule_missing_blocks_recommendation(self):
        gate = AssumptionGate(
            data_quality_passed=True,
            tax_policy_approved=True,
            wacc_approved=True,
            cost_of_equity_approved=True,
            terminal_growth_approved=True,
            forecast_assumptions_approved=True,
            debt_schedule_approved=False,  # missing
            final_recommendation_approved=False,
        ).evaluate()
        assert gate.recommendation_allowed is False
        assert any("debt" in r.lower() or "Debt" in r for r in gate.blocking_reasons)

    def test_data_quality_failed_sets_blocked_status(self):
        gate = AssumptionGate(data_quality_passed=False).evaluate()
        assert gate.status == "blocked"
        assert gate.recommendation_allowed is False
        assert gate.valuation_allowed is False

    def test_final_recommendation_not_approved_blocks(self):
        gate = AssumptionGate(
            data_quality_passed=True,
            tax_policy_approved=True,
            wacc_approved=True,
            cost_of_equity_approved=True,
            terminal_growth_approved=True,
            forecast_assumptions_approved=True,
            debt_schedule_approved=True,
            final_recommendation_approved=False,  # not approved
        ).evaluate()
        assert gate.recommendation_allowed is False


class TestRecommendationLabel:
    def test_draft_label_when_not_approved(self):
        gate = AssumptionGate(data_quality_passed=True).evaluate()
        label = gate.recommendation_label(model_upside_pct=0.30)
        assert "Draft" in label
        assert "Needs Analyst Review" in label
        # Must NOT contain BUY/HOLD/SELL as a standalone word
        assert "BUY" not in label
        assert "HOLD" not in label
        assert "SELL" not in label

    def test_draft_label_includes_model_implied_direction(self):
        gate = AssumptionGate(data_quality_passed=True).evaluate()
        label = gate.recommendation_label(model_upside_pct=0.25)
        assert "upside" in label.lower() or "25" in label

    def test_buy_label_when_fully_approved_and_high_upside(self):
        gate = AssumptionGate(
            data_quality_passed=True,
            tax_policy_approved=True,
            wacc_approved=True,
            cost_of_equity_approved=True,
            terminal_growth_approved=True,
            forecast_assumptions_approved=True,
            debt_schedule_approved=True,
            dividend_schedule_approved=True,
            peer_multiples_approved=True,
            final_recommendation_approved=True,
        ).evaluate()
        label = gate.recommendation_label(model_upside_pct=0.30)
        assert label == "BUY"

    def test_sell_label_when_approved_and_negative_upside(self):
        gate = AssumptionGate(
            data_quality_passed=True,
            tax_policy_approved=True,
            wacc_approved=True,
            cost_of_equity_approved=True,
            terminal_growth_approved=True,
            forecast_assumptions_approved=True,
            debt_schedule_approved=True,
            dividend_schedule_approved=True,
            peer_multiples_approved=True,
            final_recommendation_approved=True,
        ).evaluate()
        label = gate.recommendation_label(model_upside_pct=-0.20)
        assert label == "SELL"

    def test_hold_label_when_approved_and_neutral(self):
        gate = AssumptionGate(
            data_quality_passed=True,
            tax_policy_approved=True,
            wacc_approved=True,
            cost_of_equity_approved=True,
            terminal_growth_approved=True,
            forecast_assumptions_approved=True,
            debt_schedule_approved=True,
            dividend_schedule_approved=True,
            peer_multiples_approved=True,
            final_recommendation_approved=True,
        ).evaluate()
        label = gate.recommendation_label(model_upside_pct=0.05)
        assert label == "HOLD"


class TestBuildGateFromArtifacts:
    def test_default_unapproved_wacc_yields_draft(self):
        gate = build_gate_from_artifacts(
            data_quality_passed=True,
            wacc_assumption_status="default_unapproved",
            cost_of_equity_status="default_unapproved",
            forecast_assumption_status="default_unapproved",
            debt_schedule_method="target_debt_ratio",
        )
        assert gate.status == "draft_needs_analyst_review"
        assert gate.recommendation_allowed is False

    def test_analyst_approved_status_strings_allow_publish(self):
        gate = build_gate_from_artifacts(
            data_quality_passed=True,
            wacc_assumption_status="analyst_approved",
            cost_of_equity_status="analyst_approved",
            forecast_assumption_status="analyst_approved",
            debt_schedule_method="zero_debt_policy",
            tax_policy_approved=True,
            terminal_growth_approved=True,
            dividend_schedule_approved=True,
            peer_multiples_approved=True,
            final_recommendation_approved=True,
        )
        assert gate.status == "approved_for_publish"

    def test_missing_debt_schedule_keeps_draft_status(self):
        gate = build_gate_from_artifacts(
            data_quality_passed=True,
            wacc_assumption_status="analyst_approved",
            cost_of_equity_status="analyst_approved",
            forecast_assumption_status="analyst_approved",
            debt_schedule_method="missing",
            tax_policy_approved=True,
            terminal_growth_approved=True,
            final_recommendation_approved=True,
        )
        assert gate.recommendation_allowed is False
        assert any("debt" in r.lower() or "Debt" in r for r in gate.blocking_reasons)

    def test_to_dict_is_complete(self):
        gate = build_gate_from_artifacts(
            data_quality_passed=True,
            wacc_assumption_status="default_unapproved",
            cost_of_equity_status="default_unapproved",
            forecast_assumption_status="default_unapproved",
            debt_schedule_method="missing",
        )
        d = gate.to_dict()
        assert "status" in d
        assert "blocking_reasons" in d
        assert "recommendation_allowed" in d
        assert isinstance(d["blocking_reasons"], list)
