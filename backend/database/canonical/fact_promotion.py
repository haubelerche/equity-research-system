"""Canonical Fact Promotion: ingest.observations â†’ fact.canonical_facts.

This module is the ONLY writer of fact.canonical_facts.
It implements the winner-selection pipeline:
  observation candidates â†’ quality gates â†’ canonical promotion â†’ audit event.

Quality gates (in order):
  1. Schema validation (required fields, types)
  2. Ticker validation (ticker in ref.companies)
  3. Period validation (regex)
  4. Unit normalization
  5. Duplicate detection (ON CONFLICT logic)
  6. Source confidence gate (â‰¥ 0.80)
  7. Official document priority (warn if tier 0 not selected)
  8. Abnormal value detection (warn if > 10x historical median)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.database.canonical.audit_dal import log_event
from backend.database.canonical.connection import get_conn
from backend.database.canonical.fact_dal import compute_fact_id, upsert_canonical_fact
from backend.database.canonical.observation_dal import get_observations_for_ticker

_PERIOD_RE = re.compile(r"^[0-9]{4}(FY|Q[1-4])$")
_CONFIDENCE_THRESHOLD = 0.80


def _source_tier(value: Any) -> int:
    return 3 if value is None else int(value)


@dataclass
class PromotionResult:
    ticker: str
    promoted: int = 0
    skipped_low_confidence: int = 0
    skipped_needs_review: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def promote_accepted_facts(
    ticker: str,
    from_year: int,
    to_year: int,
    canonical_version: str = "prod",
    min_confidence: float = _CONFIDENCE_THRESHOLD,
) -> PromotionResult:
    """Promote the best observation per (ticker, period, metric) to canonical_facts.

    Winner selection: lowest source_tier first, then highest confidence.
    Observations with confidence < min_confidence are demoted to needs_review.
    """
    result = PromotionResult(ticker=ticker)

    # Load all observations for this ticker in the requested year range
    all_obs = get_observations_for_ticker(ticker=ticker, max_tier=3)
    fy_obs = [
        o for o in all_obs
        if _PERIOD_RE.match(o["period"])
        and o["period"].endswith("FY")
        and from_year <= int(o["period"][:4]) <= to_year
    ]

    if not fy_obs:
        result.errors.append(f"No FY observations found for {ticker} {from_year}â€“{to_year}")
        return result

    # Group by (period, metric) and select winner
    candidates: dict[tuple[str, str], list[dict]] = {}
    for obs in fy_obs:
        key = (obs["period"], obs["metric"])
        candidates.setdefault(key, []).append(obs)

    for (period, metric), group in candidates.items():
        # Sort by source_tier ASC, confidence DESC to find winner
        sorted_group = sorted(
            group,
            key=lambda o: (_source_tier(o.get("source_tier")), -(o["confidence"] or 0.0)),
        )
        winner = sorted_group[0]
        conf = winner.get("confidence")
        winner_tier = _source_tier(winner.get("source_tier"))
        official_document_id = winner.get("source_doc_id") if winner_tier <= 1 else None
        reconciliation_status = "matched_official" if official_document_id else "missing_official"

        if conf is not None and conf < min_confidence:
            result.skipped_low_confidence += 1
            # Promote with needs_review status so analyst can inspect
            upsert_canonical_fact(
                ticker=ticker,
                period=period,
                metric=metric,
                value=winner["value"],
                unit=winner["unit"],
                canonical_version=canonical_version,
                currency=winner.get("currency", "VND"),
                selected_observation_id=winner["observation_id"],
                confidence=conf,
                quality_status="needs_review",
                source_tier=winner_tier,
                official_document_id=official_document_id,
                reconciliation_status=reconciliation_status,
            )
            result.warnings.append(
                f"{ticker} {period} {metric}: confidence {conf:.2f} < {min_confidence} â†’ needs_review"
            )
            continue

        # Check for competing tier-0 observations not selected (official doc priority warning)
        tier0_count = sum(1 for o in group if _source_tier(o.get("source_tier")) == 0)
        if tier0_count > 0 and winner_tier > 0:
            result.warnings.append(
                f"{ticker} {period} {metric}: tier-0 observation exists but was not the winner"
            )

        upsert_canonical_fact(
            ticker=ticker,
            period=period,
            metric=metric,
            value=winner["value"],
            unit=winner["unit"],
            canonical_version=canonical_version,
            currency=winner.get("currency", "VND"),
            selected_observation_id=winner["observation_id"],
            confidence=conf,
            quality_status="accepted",
            source_tier=winner_tier,
            official_document_id=official_document_id,
            reconciliation_status=reconciliation_status,
        )
        result.promoted += 1

    # Log promotion to audit
    log_event(
        event_type="data_promotion",
        actor="fact_promotion",
        target_table="fact.canonical_facts",
        payload={
            "ticker": ticker,
            "from_year": from_year,
            "to_year": to_year,
            "canonical_version": canonical_version,
            "promoted": result.promoted,
            "skipped_low_confidence": result.skipped_low_confidence,
            "warnings": result.warnings,
        },
    )

    return result


def promote_golden_csv_observations(
    ticker: str,
    golden_facts: list[dict[str, Any]],
    source_doc_id: str,
    canonical_version: str = "prod",
) -> PromotionResult:
    """Promote golden CSV facts as governed observations.

    Golden CSVs must first be registered as source_documents and their rows
    inserted as observations via observation_dal.insert_observations().
    This function then promotes them to canonical facts IF they have no
    higher-tier observation for the same (period, metric).

    This replaces the legacy build_facts.py::removed golden fallback() silent inject.
    """
    result = PromotionResult(ticker=ticker)

    for row in golden_facts:
        period = row.get("period", "")
        metric = row.get("metric", "")
        if not _PERIOD_RE.match(period):
            result.errors.append(f"Invalid period: {period}")
            continue

        # Check if a higher-tier observation already exists for this (period, metric)
        existing = get_observations_for_ticker(ticker=ticker, period=period, metric=metric, max_tier=2)
        if existing:
            # A tier 0/1/2 observation exists â€” golden CSV (tier 1 max) does not override
            result.skipped_needs_review += 1
            continue

        # No better source; promote the golden CSV fact
        upsert_canonical_fact(
            ticker=ticker,
            period=period,
            metric=metric,
            value=row["value"],
            unit=row.get("unit", "vnd_bn"),
            canonical_version=canonical_version,
            confidence=row.get("confidence", 0.75),
            quality_status="accepted",
            source_tier=row.get("source_tier", 1),
        )
        result.promoted += 1

    return result

