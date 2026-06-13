"""Regression tests for deterministic observation winner selection.

When two observations share source_tier and confidence (e.g. DHG
short_term_investments: a stale legacy_import 0 and a fresh api_structured 2024 bn,
both tier 3 / confidence 0.98), the winner must be deterministic and the fresher
observation must supersede the stale one — otherwise promotion could resurrect the
stale 0.
"""
from __future__ import annotations

from datetime import UTC, datetime

from backend.database.canonical.fact_promotion import select_winner


def _obs(value, *, tier=3, conf=0.98, created):
    return {
        "value": value,
        "source_tier": tier,
        "confidence": conf,
        "created_at": datetime(*created, tzinfo=UTC),
    }


def test_fresher_observation_wins_on_tier_confidence_tie():
    stale = _obs(0.0, created=(2026, 5, 30))
    fresh = _obs(2024.0, created=(2026, 6, 13))
    assert select_winner([stale, fresh])["value"] == 2024.0
    # Order-independent.
    assert select_winner([fresh, stale])["value"] == 2024.0


def test_lower_tier_beats_fresher_higher_tier():
    official = _obs(100.0, tier=0, conf=0.90, created=(2026, 1, 1))
    api_fresh = _obs(110.0, tier=3, conf=0.99, created=(2026, 6, 13))
    assert select_winner([api_fresh, official])["value"] == 100.0


def test_higher_confidence_beats_fresher_lower_confidence_same_tier():
    high_conf_old = _obs(50.0, tier=3, conf=0.95, created=(2026, 1, 1))
    low_conf_new = _obs(60.0, tier=3, conf=0.80, created=(2026, 6, 13))
    assert select_winner([low_conf_new, high_conf_old])["value"] == 50.0


def test_missing_created_at_does_not_crash():
    a = {"value": 1.0, "source_tier": 3, "confidence": 0.9, "created_at": None}
    b = _obs(2.0, created=(2026, 6, 13))
    assert select_winner([a, b])["value"] == 2.0
