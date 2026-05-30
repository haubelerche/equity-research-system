"""Tests for backend/agents/debate_agent.py — deterministic bull/bear challenger."""
from __future__ import annotations

import pytest

from backend.agents.debate_agent import (
    DebateAgent,
    DebateResult,
    build_debate,
    _extract_wacc,
    _extract_terminal_growth,
    _UPSIDE_DEBATE_THRESHOLD,
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _val(
    upside: float | None = 0.35,
    wacc: float = 0.12,
    tg: float = 0.03,
    rev_cagr: float = 0.08,
) -> dict:
    return {
        "blend_dcf": {"upside_pct": upside, "target_price_dcf_vnd": 130_000},
        "wacc": wacc,
        "terminal_growth": tg,
        "revenue_cagr_historical": rev_cagr,
    }


def _state(val: dict | None = None, facts: dict | None = None) -> dict:
    return {
        "ticker": "DHG",
        "artifacts": {
            "valuation": val or _val(),
            "fact_summary": facts or {},
        },
        "artifact_refs": [],
        "evidence_refs": [],
    }


# ── _extract_wacc ─────────────────────────────────────────────────────────────

class TestExtractWacc:
    def test_direct_key(self):
        assert _extract_wacc({"wacc": 0.12}) == pytest.approx(0.12)

    def test_fcff_wacc_key(self):
        assert _extract_wacc({"fcff_wacc": 0.11}) == pytest.approx(0.11)

    def test_wacc_breakdown(self):
        assert _extract_wacc({"wacc_breakdown": {"wacc": 0.13}}) == pytest.approx(0.13)

    def test_missing_returns_none(self):
        assert _extract_wacc({}) is None


# ── _extract_terminal_growth ─────────────────────────────────────────────────

class TestExtractTerminalGrowth:
    def test_terminal_growth_key(self):
        assert _extract_terminal_growth({"terminal_growth": 0.03}) == pytest.approx(0.03)

    def test_g_key(self):
        assert _extract_terminal_growth({"g": 0.025}) == pytest.approx(0.025)

    def test_missing_returns_none(self):
        assert _extract_terminal_growth({}) is None


# ── build_debate ──────────────────────────────────────────────────────────────

class TestBuildDebate:
    def test_returns_debate_result(self):
        result = build_debate("DHG", _val(), {})
        assert isinstance(result, DebateResult)

    def test_debate_triggered_when_upside_above_threshold(self):
        result = build_debate("DHG", _val(upside=0.35), {})
        assert result.has_debate is True

    def test_no_debate_when_upside_below_threshold(self):
        result = build_debate("DHG", _val(upside=0.05), {})
        assert result.has_debate is False

    def test_no_debate_when_upside_none(self):
        result = build_debate("DHG", _val(upside=None), {})
        assert result.has_debate is False

    def test_bear_and_bull_positions_produced(self):
        result = build_debate("DHG", _val(), {})
        sides = {p.side for p in result.positions}
        assert "bear" in sides
        assert "bull" in sides

    def test_wacc_position_present(self):
        result = build_debate("DHG", _val(wacc=0.12), {})
        wacc_positions = [p for p in result.positions if p.assumption == "WACC"]
        assert len(wacc_positions) >= 1

    def test_terminal_growth_position_present(self):
        result = build_debate("DHG", _val(tg=0.03), {})
        tg_positions = [p for p in result.positions if p.assumption == "terminal_growth"]
        assert len(tg_positions) >= 1

    def test_bear_wacc_higher_than_base(self):
        result = build_debate("DHG", _val(wacc=0.12), {})
        bear_wacc = next(p for p in result.positions if p.side == "bear" and p.assumption == "WACC")
        assert bear_wacc.challenged_value > bear_wacc.base_value

    def test_bull_wacc_lower_than_base(self):
        result = build_debate("DHG", _val(wacc=0.12), {})
        bull_wacc = next(p for p in result.positions if p.side == "bull" and p.assumption == "WACC")
        assert bull_wacc.challenged_value < bull_wacc.base_value

    def test_unresolved_assumptions_populated(self):
        result = build_debate("DHG", _val(), {})
        assert len(result.unresolved_assumptions) > 0

    def test_revenue_bear_from_facts(self):
        result = build_debate("DHG", _val(rev_cagr=0.10), {"revenue_cagr": 0.10})
        rev_positions = [p for p in result.positions if p.assumption == "revenue_growth"]
        assert len(rev_positions) >= 1

    def test_summary_contains_ticker_info(self):
        result = build_debate("DHG", _val(upside=0.35), {})
        assert "35" in result.summary or "upside" in result.summary.lower()

    def test_positions_serialise(self):
        result = build_debate("DHG", _val(), {})
        d = result.to_dict()
        assert "positions" in d
        assert all(isinstance(p, dict) for p in d["positions"])
        for p in d["positions"]:
            assert "side" in p and "argument" in p and "evidence_requirement" in p


# ── DebateAgent.run ───────────────────────────────────────────────────────────

class TestDebateAgentRun:
    def test_returns_agent_result(self):
        agent = DebateAgent()
        result = agent.run(_state())
        assert hasattr(result, "status")
        assert hasattr(result, "payload")

    def test_skipped_when_no_valuation(self):
        agent = DebateAgent()
        state = {"ticker": "DHG", "artifacts": {}, "artifact_refs": [], "evidence_refs": []}
        result = agent.run(state)
        assert result.status == "skipped"
        assert result.payload.get("has_debate") is False

    def test_completed_when_no_unresolved(self):
        agent = DebateAgent()
        # A val artifact with no WACC or tg → no positions → no unresolved
        val = {"blend_dcf": {"upside_pct": 0.20}}
        result = agent.run(_state(val=val))
        # With no WACC/tg, no positions → has_debate True (upside above threshold) but no unresolved
        assert result.status in ("completed", "needs_review")

    def test_needs_review_with_unresolved_assumptions(self):
        agent = DebateAgent()
        result = agent.run(_state(_val()))
        assert result.status == "needs_review"
        assert result.requires_human is True

    def test_confidence_lower_with_unresolved(self):
        agent = DebateAgent()
        result_with = agent.run(_state(_val()))
        result_without = agent.run(_state({"blend_dcf": {"upside_pct": 0.25}}))
        assert result_with.confidence < result_without.confidence

    def test_payload_contains_positions(self):
        agent = DebateAgent()
        result = agent.run(_state(_val()))
        assert "positions" in result.payload

    def test_role_is_debate_agent(self):
        assert DebateAgent.role == "DebateAgent"

    def test_warnings_list_with_unresolved(self):
        agent = DebateAgent()
        result = agent.run(_state(_val()))
        unresolved_warns = [w for w in result.warnings if "unresolved_assumption" in w]
        assert len(unresolved_warns) > 0
