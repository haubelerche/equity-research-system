"""Debate agent — structured bull/bear challenge for valuation assumptions.

The DebateAgent is a deterministic challenger: it takes the valuation artifact and
report facts, then generates structured bear and bull counterarguments for each key
assumption. It does not compute new numbers — it surfaces uncertainty bounds and
identifies which assumptions most affect the target price.

Roles:
  - BEAR: challenges growth assumptions (lower revenue CAGR, margin compression,
    higher WACC, terminal growth capped at 0)
  - BULL: challenges conservatism (higher margin leverage, lower cost of capital,
    faster recovery post-investment)

The output is deterministic: each position is derived from the valuation artifact's
sensitivity table and assumption set — no LLM calls. An LLM may later narrate
these positions, but the underlying argument structure is code-driven.

Integration: called after RESEARCH_REVIEW stage; feeds into AUDIT_REVIEW so the
AuditAgent can check that key risks are addressed in the final report.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.harness.state import AgentResult


# Thresholds that define a "material" assumption gap worth debating.
_WACC_BEAR_DELTA = 0.02      # +200bps on WACC
_WACC_BULL_DELTA = -0.015    # -150bps on WACC
_GROWTH_BEAR_FACTOR = 0.60   # 60% of base growth rate
_GROWTH_BULL_FACTOR = 1.30   # 130% of base growth rate
_MARGIN_BEAR_DELTA = -0.03   # -3pp gross margin compression
_MARGIN_BULL_DELTA = 0.02    # +2pp gross margin improvement
_UPSIDE_DEBATE_THRESHOLD = 0.15  # Debate only when base upside > 15%


@dataclass
class DebatePosition:
    """One side of a structured valuation debate."""
    side: str                          # "bear" | "bull"
    assumption: str                    # which assumption is being challenged
    base_value: float | None           # base-case value of that assumption
    challenged_value: float | None     # challenger's proposed value
    implied_price_impact: str          # qualitative impact (not re-computed)
    argument: str                      # hedged, evidence-referenced argument text
    evidence_requirement: str          # what evidence would resolve this debate

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "assumption": self.assumption,
            "base_value": self.base_value,
            "challenged_value": self.challenged_value,
            "implied_price_impact": self.implied_price_impact,
            "argument": self.argument,
            "evidence_requirement": self.evidence_requirement,
        }


@dataclass
class DebateResult:
    ticker: str
    has_debate: bool
    base_upside_pct: float | None
    positions: list[DebatePosition] = field(default_factory=list)
    unresolved_assumptions: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "has_debate": self.has_debate,
            "base_upside_pct": self.base_upside_pct,
            "positions": [p.to_dict() for p in self.positions],
            "unresolved_assumptions": self.unresolved_assumptions,
            "summary": self.summary,
        }


def _extract_wacc(val_artifact: dict) -> float | None:
    """Extract WACC from valuation artifact — try multiple paths."""
    for key in ("wacc", "fcff_wacc", "blend_wacc"):
        v = val_artifact.get(key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    wacc_block = val_artifact.get("wacc_breakdown", {})
    if wacc_block:
        v = wacc_block.get("wacc") or wacc_block.get("wacc_pct")
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    # Try inside fcff block
    fcff = val_artifact.get("fcff", {}) or {}
    return fcff.get("wacc") or fcff.get("assumptions", {}).get("wacc")


def _extract_terminal_growth(val_artifact: dict) -> float | None:
    for key in ("terminal_growth", "g", "tg"):
        v = val_artifact.get(key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


def build_debate(ticker: str, val_artifact: dict, facts: dict) -> DebateResult:
    """Build a structured bull/bear debate from the valuation artifact.

    Deterministic: reads WACC, growth, upside from the artifact; derives
    qualitative arguments from sensitivity table if present.
    No LLM calls — argument text is template-driven from assumption values.

    Args:
        ticker: Ticker symbol.
        val_artifact: Valuation artifact dict from run_valuation.py.
        facts: Canonical fact summary (ratios, margins) for context.

    Returns:
        DebateResult with positioned arguments and unresolved assumptions list.
    """
    blend_block = val_artifact.get("blend_dcf", {}) or {}
    upside = blend_block.get("upside_pct") or val_artifact.get("upside_pct")
    base_upside: float | None = None
    if upside is not None:
        try:
            base_upside = float(upside)
        except (TypeError, ValueError):
            pass

    # Only debate when there's a meaningful position to challenge
    if base_upside is None or abs(base_upside) < _UPSIDE_DEBATE_THRESHOLD:
        return DebateResult(
            ticker=ticker,
            has_debate=False,
            base_upside_pct=base_upside,
            summary=(
                f"Upside {base_upside:.1%} is below debate threshold "
                f"({_UPSIDE_DEBATE_THRESHOLD:.0%}). No material debate required."
            ) if base_upside is not None else "Upside unavailable — skip debate.",
        )

    wacc = _extract_wacc(val_artifact)
    tg = _extract_terminal_growth(val_artifact)
    positions: list[DebatePosition] = []
    unresolved: list[str] = []

    # ── WACC challenge ──────────────────────────────────────────────────────────
    if wacc is not None:
        bear_wacc = wacc + _WACC_BEAR_DELTA
        positions.append(DebatePosition(
            side="bear",
            assumption="WACC",
            base_value=round(wacc, 4),
            challenged_value=round(bear_wacc, 4),
            implied_price_impact="negative — higher discount rate compresses present value",
            argument=(
                f"If risk-free rate rises 200bps or beta re-rates higher post-expansion "
                f"(GMP factory leverage), WACC could reach {bear_wacc:.1%}. "
                f"At current base WACC {wacc:.1%}, the model is sensitive to credit conditions. "
                f"Check: rising interest rates in Vietnam 2024–2025 vs. company's floating debt."
            ),
            evidence_requirement=(
                "Current D/E ratio, floating vs. fixed interest cost breakdown from "
                "latest financial statements. Credit rating / cost of debt history."
            ),
        ))
        bull_wacc = wacc + _WACC_BULL_DELTA
        if bull_wacc > 0:
            positions.append(DebatePosition(
                side="bull",
                assumption="WACC",
                base_value=round(wacc, 4),
                challenged_value=round(bull_wacc, 4),
                implied_price_impact="positive — lower discount rate inflates present value",
                argument=(
                    f"If the company's low-leverage balance sheet and stable BHYT cash flows "
                    f"justify a lower equity risk premium, WACC could compress to {bull_wacc:.1%}. "
                    f"Peer pharma companies with similar coverage ratios trade at tighter spreads."
                ),
                evidence_requirement=(
                    "Peer WACC benchmarks from broker reports (same sector, same exchange). "
                    "Company's debt-service coverage ratio for last 3 years."
                ),
            ))
        unresolved.append("WACC sensitivity requires peer WACC data — currently using model default")

    # ── Terminal growth challenge ────────────────────────────────────────────────
    if tg is not None:
        positions.append(DebatePosition(
            side="bear",
            assumption="terminal_growth",
            base_value=round(tg, 4),
            challenged_value=0.0,
            implied_price_impact="negative — capping terminal growth reduces terminal value",
            argument=(
                f"Terminal growth at {tg:.1%} assumes perpetual growth above Vietnam's "
                f"long-run GDP trend for the pharma generic sector. If BHYT procurement "
                f"shifts to lowest-bid import, terminal growth for domestic generics could "
                f"approach 0%. The generic segment faces structural margin pressure."
            ),
            evidence_requirement=(
                "Ministry of Health BHYT tender results for last 3 cycles. "
                "Domestic vs. imported drug market share trend (Cục Quản lý Dược data)."
            ),
        ))
        positions.append(DebatePosition(
            side="bull",
            assumption="terminal_growth",
            base_value=round(tg, 4),
            challenged_value=round(min(tg * _GROWTH_BULL_FACTOR, 0.05), 4),
            implied_price_impact="positive — higher terminal growth increases terminal value",
            argument=(
                f"If the company's R&D pipeline produces Tier 1 drug registrations "
                f"(non-generic) or export volumes ramp to ASEAN markets post-GMP upgrade, "
                f"terminal growth could exceed the base {tg:.1%}. "
                f"The new factory adds capacity headroom not yet modeled."
            ),
            evidence_requirement=(
                "Drug registration pipeline (DAV approval list). "
                "Export revenue trend 2021–2025 from BCTC breakdown."
            ),
        ))
        unresolved.append("Terminal growth requires drug-pipeline visibility — currently generic sector assumption")

    # ── Revenue growth challenge (from facts) ───────────────────────────────────
    rev_cagr = facts.get("revenue_cagr") or val_artifact.get("revenue_cagr_historical")
    if rev_cagr is not None:
        try:
            rev_cagr = float(rev_cagr)
        except (TypeError, ValueError):
            rev_cagr = None
    if rev_cagr is not None:
        bear_growth = rev_cagr * _GROWTH_BEAR_FACTOR
        positions.append(DebatePosition(
            side="bear",
            assumption="revenue_growth",
            base_value=round(rev_cagr, 4),
            challenged_value=round(bear_growth, 4),
            implied_price_impact="negative — lower revenue CAGR reduces FCF and terminal base",
            argument=(
                f"Historical revenue CAGR of {rev_cagr:.1%} may not persist: BHYT "
                f"contract renewals could slow, generic price pressure intensifies, and "
                f"hospital channel concentration creates renewal risk. Bear case applies "
                f"{_GROWTH_BEAR_FACTOR:.0%} haircut → {bear_growth:.1%} CAGR."
            ),
            evidence_requirement=(
                "BHYT contract breakdown by hospital tier (A/B/C). "
                "Revenue by channel (hospital vs. retail vs. export) from BCTN."
            ),
        ))
        unresolved.append("Revenue channel mix unverified — BCTN breakdown required")

    direction = "UNDERVALUED" if base_upside > 0 else "OVERVALUED"
    summary = (
        f"Base case implies {base_upside:.1%} upside ({direction}). "
        f"{len([p for p in positions if p.side == 'bear'])} bear challenge(s), "
        f"{len([p for p in positions if p.side == 'bull'])} bull challenge(s). "
        f"{len(unresolved)} assumption(s) require additional evidence before final export."
    )

    return DebateResult(
        ticker=ticker,
        has_debate=True,
        base_upside_pct=base_upside,
        positions=positions,
        unresolved_assumptions=unresolved,
        summary=summary,
    )


class DebateAgent:
    """Deterministic bull/bear challenge agent for valuation assumptions.

    Called after ResearchAgent and before AuditAgent. Surfaces uncertainty bounds
    without making new numerical claims. The output feeds the risk section of the
    final report and the AuditAgent's completeness check.
    """

    role = "DebateAgent"

    def run(self, state: dict[str, Any]) -> AgentResult:
        ticker = state.get("ticker", "")
        val_artifact = (state.get("artifacts") or {}).get("valuation", {})
        facts = (state.get("artifacts") or {}).get("fact_summary", {})
        warnings: list[str] = []

        if not val_artifact:
            warnings.append("valuation_artifact_missing — debate skipped")
            return AgentResult(
                status="skipped",
                payload={"ticker": ticker, "has_debate": False, "reason": "no_valuation_artifact"},
                artifact_refs=list(state.get("artifact_refs") or []),
                evidence_refs=list(state.get("evidence_refs") or []),
                confidence=0.0,
                confidence_breakdown={},
                requires_human=False,
                warnings=warnings,
            )

        result = build_debate(ticker, val_artifact, facts or {})

        if result.unresolved_assumptions:
            warnings.extend([f"unresolved_assumption:{a}" for a in result.unresolved_assumptions])

        return AgentResult(
            status="needs_review" if result.unresolved_assumptions else "completed",
            payload=result.to_dict(),
            artifact_refs=list(state.get("artifact_refs") or []),
            evidence_refs=list(state.get("evidence_refs") or []),
            confidence=0.72 if result.unresolved_assumptions else 0.85,
            confidence_breakdown={
                "debate_coverage": 0.9 if result.has_debate else 0.5,
                "assumption_resolution": 1.0 - (
                    len(result.unresolved_assumptions) / max(len(result.positions), 1) * 0.4
                ),
            },
            requires_human=bool(result.unresolved_assumptions),
            review_reason=(
                f"{len(result.unresolved_assumptions)} debate assumption(s) need evidence"
                if result.unresolved_assumptions else None
            ),
            warnings=warnings,
        )
