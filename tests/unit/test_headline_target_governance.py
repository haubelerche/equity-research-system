from __future__ import annotations

import pytest

from backend.valuation.headline_target_governance import build_headline_target_governance


def test_raw_target_inside_band_is_preserved():
    result = build_headline_target_governance(
        current_price_vnd=100_000,
        raw_model_target_vnd=105_000,
        raw_model_target_source="FCFF",
    )

    assert result.headline_target_vnd == 105_000
    assert result.target_adjustment == "none"
    assert result.raw_model_target_vnd == 105_000
    assert result.raw_model_target_source == "FCFF"


def test_raw_target_above_band_is_clamped_to_upper_bound():
    result = build_headline_target_governance(
        current_price_vnd=100_000,
        raw_model_target_vnd=150_000,
    )

    assert result.headline_target_vnd == 140_000
    assert result.target_adjustment == "clamped_high"
    assert result.raw_upside == pytest.approx(0.50)
    assert result.headline_upside == pytest.approx(0.40)


def test_raw_target_below_band_is_clamped_to_lower_bound():
    result = build_headline_target_governance(
        current_price_vnd=100_000,
        raw_model_target_vnd=30_000,
    )

    assert result.headline_target_vnd == 60_000
    assert result.target_adjustment == "clamped_low"
    assert result.raw_upside == pytest.approx(-0.70)
    assert result.headline_upside == pytest.approx(-0.40)


def test_target_within_forty_percent_band_is_preserved_not_flattened():
    # The ±40% band must let a real ±30% target reach the cover page (it used to be
    # clamped to ±10%, flattening every valuation back to the market price).
    up = build_headline_target_governance(current_price_vnd=100_000, raw_model_target_vnd=130_000)
    assert up.headline_target_vnd == 130_000
    assert up.target_adjustment == "none"
    assert up.headline_upside == pytest.approx(0.30)
    down = build_headline_target_governance(current_price_vnd=100_000, raw_model_target_vnd=72_000)
    assert down.headline_target_vnd == 72_000
    assert down.target_adjustment == "none"
    assert down.headline_upside == pytest.approx(-0.28)


def test_missing_raw_target_uses_neutral_market_anchor():
    result = build_headline_target_governance(
        current_price_vnd=93_400,
        raw_model_target_vnd=None,
    )

    assert result.headline_target_vnd == 93_400
    assert result.target_adjustment == "market_anchor_neutral"
    assert result.raw_model_target_vnd is None
    assert result.headline_upside == pytest.approx(0.0)


def test_dhg_like_modest_downside_target_is_preserved():
    # Previously clamped at the −5% floor; under the ±40% band a modest −5% model
    # target is now shown truthfully rather than pinned to the band edge.
    result = build_headline_target_governance(
        current_price_vnd=93_600,
        raw_model_target_vnd=88_877,
    )

    assert result.headline_target_vnd == 88_877
    assert result.target_adjustment == "none"
    assert result.headline_upside == pytest.approx(-0.0505, abs=1e-3)


def test_missing_current_price_blocks_headline_target():
    result = build_headline_target_governance(
        current_price_vnd=None,
        raw_model_target_vnd=100_000,
    )

    assert result.headline_target_vnd is None
    assert result.target_adjustment == "missing_current_price"
    assert "headline_target_missing_current_price" in result.warnings
