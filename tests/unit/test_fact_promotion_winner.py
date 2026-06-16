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


# ── vnstock-primary contract (2026-06-16) ──────────────────────────────────
# Locked data-source contract: vnstock is the PRIMARY source for fundamentals;
# PDF/OCR/CafeF are additive-only (fill gaps, never override vnstock). A partial
# tier-0 PDF-table figure (e.g. rounded DHG revenue=5200) must NOT outrank the
# precise, internally-consistent vnstock income statement.

def _src_obs(value, *, method, tier, conf=0.95, created=(2026, 6, 1)):
    return {
        "value": value,
        "source_tier": tier,
        "confidence": conf,
        "extraction_method": method,
        "created_at": datetime(*created, tzinfo=UTC),
    }


def test_vnstock_beats_tier0_pdf_table():
    vnstock = _src_obs(4885.0, method="api_structured", tier=3)
    pdf = _src_obs(5200.0, method="pdf_table", tier=0)
    assert select_winner([pdf, vnstock])["value"] == 4885.0
    assert select_winner([vnstock, pdf])["value"] == 4885.0


def test_vnstock_beats_cafef():
    vnstock = _src_obs(100.0, method="api_structured", tier=3)
    cafef = _src_obs(120.0, method="cafef_api", tier=2)
    assert select_winner([cafef, vnstock])["value"] == 100.0


def test_pdf_fills_gap_when_no_vnstock():
    # Additive-only still works: with no vnstock obs, tier ordering picks the PDF.
    pdf = _src_obs(5200.0, method="pdf_table", tier=0)
    cafef = _src_obs(5100.0, method="cafef_api", tier=2)
    assert select_winner([cafef, pdf])["value"] == 5200.0
