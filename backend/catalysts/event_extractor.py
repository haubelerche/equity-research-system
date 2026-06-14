"""Catalyst event extraction + validation — Source-Provenance Rebuild, Phase 5.

The controlled event taxonomy and the validation rules that make a catalyst event
admissible. Extraction itself (turning a document into candidate events) can be done by
connectors or, later, an LLM — but EVERY candidate must pass `validate_event` before it
is stored. The rules guarantee provenance: no event without a concrete source document
and evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Controlled event taxonomy (plan Phase 5). Unknown event_type is rejected.
EVENT_TYPES: frozenset[str] = frozenset({
    "financial_disclosure", "annual_report", "earnings_explanation",
    "drug_recall", "drug_registration", "bidding_result", "hospital_tender",
    "bhyt_policy", "regulatory_notice", "factory_gmp", "capacity_expansion",
    "dividend_resolution", "management_change", "broker_report", "media_article",
})

# Causality levels (mirror migration 010 fact.catalyst_events.causality_level).
CAUSALITY_LEVELS: frozenset[str] = frozenset({
    "contextual_event", "potential_driver",
    "management_disclosed_driver", "validated_driver",
})

TICKER_MAPPING_LEVELS: frozenset[str] = frozenset({"explicit", "sector_level"})


@dataclass
class CatalystEvent:
    event_title: str
    event_type: str
    source_document_id: int | None
    event_date: str | None = None
    published_date: str | None = None
    evidence_quote: str | None = None
    evidence_span: str | None = None
    ticker: str | None = None
    ticker_mapping_level: str = "explicit"
    event_summary: str = ""
    impact_direction: str | None = None
    impact_area: str | None = None
    causality_level: str = "contextual_event"
    confidence: float | None = None
    revenue_impact_pct: float | None = None
    margin_impact_bps: float | None = None
    capex_impact_pct: float | None = None
    governance_impact_score: float | None = None
    dividend_impact_pct: float | None = None

    def to_dict(self) -> dict:
        return {
            "event_title": self.event_title, "event_type": self.event_type,
            "source_document_id": self.source_document_id,
            "event_date": self.event_date, "published_date": self.published_date,
            "evidence_quote": self.evidence_quote, "evidence_span": self.evidence_span,
            "ticker": self.ticker, "ticker_mapping_level": self.ticker_mapping_level,
            "event_summary": self.event_summary, "impact_direction": self.impact_direction,
            "impact_area": self.impact_area, "causality_level": self.causality_level,
            "confidence": self.confidence,
            "revenue_impact_pct": self.revenue_impact_pct,
            "margin_impact_bps": self.margin_impact_bps,
            "capex_impact_pct": self.capex_impact_pct,
            "governance_impact_score": self.governance_impact_score,
            "dividend_impact_pct": self.dividend_impact_pct,
        }


@dataclass
class ValidationOutcome:
    valid: bool
    reasons: list[str] = field(default_factory=list)


def validate_event(event: CatalystEvent | dict) -> ValidationOutcome:
    """Validate a candidate catalyst event against the provenance rules.

    A valid event requires: event_title, event_type in taxonomy, a source_document_id,
    an event_date OR published_date, evidence_quote OR evidence_span, and an explicit or
    sector_level ticker mapping. Causality level must be in the controlled set.
    """
    e = event if isinstance(event, CatalystEvent) else CatalystEvent(**{
        k: v for k, v in event.items() if k in CatalystEvent.__dataclass_fields__
    })
    reasons: list[str] = []

    if not (e.event_title or "").strip():
        reasons.append("missing event_title")
    if e.event_type not in EVENT_TYPES:
        reasons.append(f"unknown event_type '{e.event_type}' (not in controlled taxonomy)")
    if e.source_document_id is None:
        reasons.append("missing source_document_id — catalyst events require a concrete source")
    if not (e.event_date or e.published_date):
        reasons.append("missing event_date and published_date")
    if not ((e.evidence_quote or "").strip() or (e.evidence_span or "").strip()):
        reasons.append("missing evidence_quote/evidence_span")
    if e.ticker_mapping_level not in TICKER_MAPPING_LEVELS:
        reasons.append(f"ticker_mapping_level must be one of {sorted(TICKER_MAPPING_LEVELS)}")
    elif e.ticker_mapping_level == "explicit" and not (e.ticker or "").strip():
        reasons.append("explicit ticker mapping requires a ticker")
    if e.causality_level not in CAUSALITY_LEVELS:
        reasons.append(f"unknown causality_level '{e.causality_level}'")

    return ValidationOutcome(valid=not reasons, reasons=reasons)


def extract_events(candidates: list[dict]) -> tuple[list[CatalystEvent], list[dict]]:
    """Split raw candidate dicts into (valid_events, rejected).

    Each rejected entry is {"candidate": <dict>, "reasons": [...]}.
    """
    valid: list[CatalystEvent] = []
    rejected: list[dict] = []
    for c in candidates:
        ev = CatalystEvent(**{k: v for k, v in c.items() if k in CatalystEvent.__dataclass_fields__})
        outcome = validate_event(ev)
        if outcome.valid:
            valid.append(ev)
        else:
            rejected.append({"candidate": c, "reasons": outcome.reasons})
    return valid, rejected
