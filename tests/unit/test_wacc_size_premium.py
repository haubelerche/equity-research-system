"""Size premium must scale with market cap — large caps should not carry one.

A size premium compensates for small-cap risk (Fama-French SMB). Applying a flat
2% to every issuer over-discounts large, liquid blue-chips (e.g. DHG, market cap
~12,300 VND bn), pushing their DCF well below market/analyst targets. The premium
must be 0 for large caps, modest for mid caps, and full for small caps.
"""
from __future__ import annotations

import pytest

from backend.analytics.fcff import vn_size_premium


def test_large_cap_has_no_size_premium():
    # DHG ~12,300 VND bn — large cap, defensive blue-chip.
    assert vn_size_premium(12_300.0) == pytest.approx(0.0)
    assert vn_size_premium(10_000.0) == pytest.approx(0.0)


def test_mid_cap_has_modest_premium():
    assert vn_size_premium(5_000.0) == pytest.approx(0.01)
    assert vn_size_premium(1_000.0) == pytest.approx(0.01)


def test_small_cap_keeps_full_premium():
    assert vn_size_premium(500.0) == pytest.approx(0.02)
    assert vn_size_premium(50.0) == pytest.approx(0.02)


def test_unknown_market_cap_falls_back_to_default_premium():
    # No market cap → keep the conservative default rather than zero it out.
    assert vn_size_premium(None) == pytest.approx(0.02)
