"""Tests for AssumptionGate.evaluate() blocking logic."""
from __future__ import annotations

import pytest

from backend.analytics.approval_gate import AssumptionGate


def _all_approved() -> AssumptionGate:
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


class TestApprovalGateBlocking:
    def test_all_approved_is_publishable(self):
        gate = _all_approved()
        assert gate.status == "approved_for_publish"
        assert gate.blocking_reasons == []

    def test_missing_dividend_blocks_publish(self):
        gate = AssumptionGate(
            data_quality_passed=True,
            tax_policy_approved=True,
            wacc_approved=True,
            cost_of_equity_approved=True,
            terminal_growth_approved=True,
            forecast_assumptions_approved=True,
            debt_schedule_approved=True,
            dividend_schedule_approved=False,
            peer_multiples_approved=True,
            final_recommendation_approved=True,
        ).evaluate()
        assert gate.status == "draft_needs_analyst_review"
        assert any("dividend" in r.lower() for r in gate.blocking_reasons)

    def test_missing_peer_blocks_publish(self):
        gate = AssumptionGate(
            data_quality_passed=True,
            tax_policy_approved=True,
            wacc_approved=True,
            cost_of_equity_approved=True,
            terminal_growth_approved=True,
            forecast_assumptions_approved=True,
            debt_schedule_approved=True,
            dividend_schedule_approved=True,
            peer_multiples_approved=False,
            final_recommendation_approved=True,
        ).evaluate()
        assert gate.status == "draft_needs_analyst_review"
        assert any("peer" in r.lower() or "multiples" in r.lower() for r in gate.blocking_reasons)

    def test_data_quality_fail_causes_blocked(self):
        gate = AssumptionGate(
            data_quality_passed=False,
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
        assert gate.status == "blocked"

    def test_recommendation_not_allowed_when_draft(self):
        gate = AssumptionGate(
            data_quality_passed=True,
            tax_policy_approved=True,
            wacc_approved=True,
            cost_of_equity_approved=True,
            terminal_growth_approved=True,
            forecast_assumptions_approved=True,
            debt_schedule_approved=True,
            dividend_schedule_approved=False,
            peer_multiples_approved=False,
            final_recommendation_approved=True,
        ).evaluate()
        assert not gate.recommendation_allowed
