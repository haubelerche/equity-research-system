"""Claim ledger — Phase 6: evidence-grounded claim tracking.

Every material quantitative claim in the report must trace back to:
  - a canonical fact (fact_id + source_id + metric)
  - a valuation artifact field (artifact_path + field_name)
  - a formula trace (formula_id + input_values)

A claim without any trace is recorded with status="unsupported" and
blocks the citation_gate for final export.

Claim types:
  financial_fact   — a historical or reported financial number
  valuation_output — a computed valuation result (DCF, multiple, blend)
  market_data      — current price, market cap, shares, volume
  forecast_driver  — a forecast assumption or driver value
  ratio            — a computed ratio (margins, ROE, P/E, etc.)
  qualitative      — text claim (no numeric verification; citation still required)

All arithmetic is deterministic Python — no LLM involvement.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

ClaimType = Literal[
    "financial_fact",
    "valuation_output",
    "market_data",
    "forecast_driver",
    "ratio",
    "qualitative",
]

ClaimStatus = Literal[
    "supported",       # has at least one valid trace
    "unsupported",     # no trace found → blocks citation_gate
    "partial",         # trace exists but source tier < required threshold
    "pending_review",  # trace exists but awaiting analyst confirmation
]


@dataclass
class ClaimTrace:
    """One piece of evidence supporting a claim."""
    trace_type: Literal["fact", "artifact", "formula", "source_doc"]

    # For fact traces
    fact_id: str | None = None
    source_id: str | None = None
    metric_name: str | None = None
    period: str | None = None
    value: float | None = None
    unit: str | None = None
    source_tier: int | None = None          # 0=official, 1=primary, 2=secondary, 3=convenience

    # For artifact traces
    artifact_path: str | None = None        # e.g. "artifacts/valuation/DBD_fcff.json"
    artifact_field: str | None = None       # e.g. "target_price_vnd"

    # For formula traces
    formula_id: str | None = None           # e.g. "FCFF_DCF_v1"
    formula_inputs: dict[str, Any] | None = None

    # For source doc traces
    document_url: str | None = None
    document_title: str | None = None
    excerpt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in {
            "trace_type": self.trace_type,
            "fact_id": self.fact_id,
            "source_id": self.source_id,
            "metric_name": self.metric_name,
            "period": self.period,
            "value": self.value,
            "unit": self.unit,
            "source_tier": self.source_tier,
            "artifact_path": self.artifact_path,
            "artifact_field": self.artifact_field,
            "formula_id": self.formula_id,
            "formula_inputs": self.formula_inputs,
            "document_url": self.document_url,
            "document_title": self.document_title,
            "excerpt": self.excerpt,
        }.items() if v is not None}


@dataclass
class ClaimEntry:
    """One material claim in the report."""
    claim_id: str                         # auto-generated hash
    ticker: str
    claim_type: ClaimType
    claim_text: str                       # the claim as it appears in the report
    numeric_value: float | None           # the number being claimed (if any)
    numeric_unit: str | None              # e.g. "VND bn", "VND/share", "%"
    section: str                          # report section e.g. "valuation", "financial_performance"
    status: ClaimStatus
    traces: list[ClaimTrace] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def make_id(cls, ticker: str, claim_text: str, section: str) -> str:
        raw = f"{ticker}|{section}|{claim_text[:120]}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def add_fact_trace(
        self,
        fact_id: str,
        source_id: str,
        metric_name: str,
        period: str,
        value: float | None = None,
        unit: str | None = None,
        source_tier: int | None = None,
    ) -> "ClaimEntry":
        self.traces.append(ClaimTrace(
            trace_type="fact",
            fact_id=fact_id,
            source_id=source_id,
            metric_name=metric_name,
            period=period,
            value=value,
            unit=unit,
            source_tier=source_tier,
        ))
        self._update_status()
        return self

    def add_artifact_trace(
        self,
        artifact_path: str,
        artifact_field: str,
        value: float | None = None,
    ) -> "ClaimEntry":
        self.traces.append(ClaimTrace(
            trace_type="artifact",
            artifact_path=artifact_path,
            artifact_field=artifact_field,
            value=value,
        ))
        self._update_status()
        return self

    def add_formula_trace(
        self,
        formula_id: str,
        formula_inputs: dict[str, Any] | None = None,
    ) -> "ClaimEntry":
        self.traces.append(ClaimTrace(
            trace_type="formula",
            formula_id=formula_id,
            formula_inputs=formula_inputs,
        ))
        self._update_status()
        return self

    def add_source_doc_trace(
        self,
        document_url: str,
        document_title: str,
        excerpt: str | None = None,
    ) -> "ClaimEntry":
        self.traces.append(ClaimTrace(
            trace_type="source_doc",
            document_url=document_url,
            document_title=document_title,
            excerpt=excerpt,
        ))
        self._update_status()
        return self

    def _update_status(self) -> None:
        if not self.traces:
            self.status = "unsupported"
            return
        # Check source tier quality
        tier_traces = [t for t in self.traces if t.source_tier is not None]
        if tier_traces and all(t.source_tier >= 3 for t in tier_traces):  # type: ignore[operator]
            self.status = "partial"   # tier-3 only → partial support
        else:
            self.status = "supported"

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "ticker": self.ticker,
            "claim_type": self.claim_type,
            "claim_text": self.claim_text,
            "numeric_value": self.numeric_value,
            "numeric_unit": self.numeric_unit,
            "section": self.section,
            "status": self.status,
            "traces": [t.to_dict() for t in self.traces],
            "created_at": self.created_at,
        }


@dataclass
class ClaimLedger:
    """Full claim ledger for one report run."""
    ticker: str
    report_id: str | None
    claims: list[ClaimEntry] = field(default_factory=list)

    def add_claim(
        self,
        claim_type: ClaimType,
        claim_text: str,
        section: str,
        numeric_value: float | None = None,
        numeric_unit: str | None = None,
        status: ClaimStatus = "unsupported",
    ) -> ClaimEntry:
        entry = ClaimEntry(
            claim_id=ClaimEntry.make_id(self.ticker, claim_text, section),
            ticker=self.ticker,
            claim_type=claim_type,
            claim_text=claim_text,
            numeric_value=numeric_value,
            numeric_unit=numeric_unit,
            section=section,
            status=status,
        )
        self.claims.append(entry)
        return entry

    # ── Gate checks ───────────────────────────────────────────────────────

    def unsupported_claims(self) -> list[ClaimEntry]:
        return [c for c in self.claims if c.status == "unsupported"]

    def partial_claims(self) -> list[ClaimEntry]:
        return [c for c in self.claims if c.status == "partial"]

    def citation_gate(self, require_tier_01: bool = False) -> dict[str, Any]:
        """Run citation coverage gate.

        Args:
            require_tier_01: If True, "partial" (tier-3 only) claims also fail.

        Returns:
            {"status": "PASS"|"FAIL", "unsupported_count": int,
             "partial_count": int, "total_claims": int, "issues": [...]}
        """
        issues: list[str] = []
        unsupported = self.unsupported_claims()
        partial = self.partial_claims()

        for c in unsupported:
            issues.append(
                f"[{c.section}] UNSUPPORTED: '{c.claim_text[:80]}' — no evidence trace"
            )
        if require_tier_01:
            for c in partial:
                issues.append(
                    f"[{c.section}] TIER-3-ONLY: '{c.claim_text[:80]}' — "
                    "requires official or primary source"
                )

        fail_count = len(unsupported) + (len(partial) if require_tier_01 else 0)
        status = "FAIL" if fail_count > 0 else "PASS"

        return {
            "status": status,
            "total_claims": len(self.claims),
            "unsupported_count": len(unsupported),
            "partial_count": len(partial),
            "issues": issues,
        }

    def summary(self) -> dict[str, int]:
        from collections import Counter
        c = Counter(entry.status for entry in self.claims)
        return dict(c)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "report_id": self.report_id,
            "total_claims": len(self.claims),
            "summary": self.summary(),
            "claims": [c.to_dict() for c in self.claims],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


# ── Factory helpers ───────────────────────────────────────────────────────────

def claim_from_fact(
    ledger: ClaimLedger,
    claim_text: str,
    section: str,
    fact_id: str,
    source_id: str,
    metric_name: str,
    period: str,
    value: float | None = None,
    unit: str | None = None,
    source_tier: int | None = None,
) -> ClaimEntry:
    """Create and register a claim backed by a canonical fact."""
    entry = ledger.add_claim(
        claim_type="financial_fact",
        claim_text=claim_text,
        section=section,
        numeric_value=value,
        numeric_unit=unit,
    )
    entry.add_fact_trace(
        fact_id=fact_id,
        source_id=source_id,
        metric_name=metric_name,
        period=period,
        value=value,
        unit=unit,
        source_tier=source_tier,
    )
    return entry


def claim_from_artifact(
    ledger: ClaimLedger,
    claim_text: str,
    section: str,
    artifact_path: str,
    artifact_field: str,
    claim_type: ClaimType = "valuation_output",
    value: float | None = None,
    unit: str | None = None,
) -> ClaimEntry:
    """Create and register a claim backed by a valuation/forecast artifact."""
    entry = ledger.add_claim(
        claim_type=claim_type,
        claim_text=claim_text,
        section=section,
        numeric_value=value,
        numeric_unit=unit,
    )
    entry.add_artifact_trace(
        artifact_path=artifact_path,
        artifact_field=artifact_field,
        value=value,
    )
    return entry
