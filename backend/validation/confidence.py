"""Confidence scoring formula for canonical facts (Plan Phase 5, §12.2).

Formula:
    confidence_score =
        0.35 * source_quality_score
      + 0.25 * cross_source_match_score
      + 0.20 * accounting_reconciliation_score
      + 0.10 * extraction_confidence
      + 0.10 * time_series_sanity_score

Score interpretation (Plan §12.3):
    >= 0.95  : High confidence — use
    0.85–0.95: Acceptable — use with warning if needed
    0.70–0.85: Needs review — do NOT use for material valuation fact
    < 0.70   : Reject — exclude

Hard cap (Plan §12.3):
    Tier 3 source cannot exceed 0.85 confidence without Tier 1/2 cross-check.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ConfidenceStatus = Literal["high", "acceptable", "needs_review", "reject"]

# Source quality scores by tier
_SOURCE_QUALITY: dict[int, float] = {
    1: 1.00,   # Audited annual report
    2: 0.80,   # Reviewed quarterly / official IR
    3: 0.55,   # Third-party API (vnstock, FiinPro, etc.)
    4: 0.20,   # News / unofficial
}

# Tier 3 confidence cap without Tier 1/2 cross-check
TIER3_CONFIDENCE_CAP = 0.85


@dataclass
class ConfidenceResult:
    confidence_score: float
    status: ConfidenceStatus
    source_quality_score: float
    cross_source_match_score: float
    accounting_reconciliation_score: float
    extraction_confidence: float
    time_series_sanity_score: float
    is_capped: bool
    cap_reason: str
    warnings: list[str]


def _interpret(score: float) -> ConfidenceStatus:
    if score >= 0.95:
        return "high"
    if score >= 0.85:
        return "acceptable"
    if score >= 0.70:
        return "needs_review"
    return "reject"


def compute_confidence(
    source_tier: int,
    has_tier1_or_2_cross_check: bool,
    cross_source_agreement: float,
    accounting_reconciliation_score: float,
    extraction_confidence: float,
    time_series_sanity_score: float,
) -> ConfidenceResult:
    """Compute weighted confidence score for a canonical fact.

    Args:
        source_tier: 1–4 (reliability tier of primary source)
        has_tier1_or_2_cross_check: True if fact is confirmed by ≥1 Tier 1/2 source
        cross_source_agreement: 0.0–1.0 (1.0 = perfect match across sources)
        accounting_reconciliation_score: 0.0–1.0 (1.0 = all recon checks pass)
        extraction_confidence: 0.0–1.0 (OCR/parse confidence from source extractor)
        time_series_sanity_score: 0.0–1.0 (1.0 = no time-series anomalies)

    Returns:
        ConfidenceResult with weighted score, status, and cap info.
    """
    warnings: list[str] = []

    source_quality = _SOURCE_QUALITY.get(source_tier, 0.20)

    raw_score = (
        0.35 * source_quality
        + 0.25 * max(0.0, min(1.0, cross_source_agreement))
        + 0.20 * max(0.0, min(1.0, accounting_reconciliation_score))
        + 0.10 * max(0.0, min(1.0, extraction_confidence))
        + 0.10 * max(0.0, min(1.0, time_series_sanity_score))
    )
    raw_score = round(raw_score, 4)

    # Apply Tier-3 cap
    is_capped = False
    cap_reason = ""
    if source_tier >= 3 and not has_tier1_or_2_cross_check:
        if raw_score > TIER3_CONFIDENCE_CAP:
            raw_score = TIER3_CONFIDENCE_CAP
            is_capped = True
            cap_reason = (
                f"Tier-{source_tier} source without Tier-1/2 cross-check: "
                f"confidence capped at {TIER3_CONFIDENCE_CAP}"
            )
            warnings.append(cap_reason)
        else:
            warnings.append(
                f"Tier-{source_tier} source without Tier-1/2 cross-check: "
                f"score {raw_score:.3f} — may not be suitable for material valuation facts"
            )

    if accounting_reconciliation_score < 0.5:
        warnings.append(
            f"Low accounting reconciliation score ({accounting_reconciliation_score:.2f}) "
            f"— cross-check income statement and balance sheet"
        )

    if time_series_sanity_score < 0.5:
        warnings.append(
            f"Low time-series sanity score ({time_series_sanity_score:.2f}) "
            f"— unusual YoY movements detected"
        )

    return ConfidenceResult(
        confidence_score=raw_score,
        status=_interpret(raw_score),
        source_quality_score=source_quality,
        cross_source_match_score=cross_source_agreement,
        accounting_reconciliation_score=accounting_reconciliation_score,
        extraction_confidence=extraction_confidence,
        time_series_sanity_score=time_series_sanity_score,
        is_capped=is_capped,
        cap_reason=cap_reason,
        warnings=warnings,
    )


def score_from_reconciliation_report(recon_report) -> float:
    """Derive accounting_reconciliation_score from a ReconciliationReport.

    - No failures/warnings → 1.0
    - Only warnings → 0.7
    - Critical failures → 0.0
    """
    if recon_report.valuation_blocked:
        return 0.0
    if recon_report.warnings:
        return 0.7
    return 1.0


def score_from_time_series_checks(ts_checks: list) -> float:
    """Derive time_series_sanity_score from a list of ReconciliationCheck.

    Filters for TS_ prefix checks only.
    - No TS checks or all pass → 1.0
    - Some warn → 0.6
    - Any fail → 0.0
    """
    ts = [c for c in ts_checks if c.name.startswith("TS_")]
    if not ts:
        return 1.0
    if any(c.status == "fail" for c in ts):
        return 0.0
    if any(c.status == "warn" for c in ts):
        return 0.6
    return 1.0
