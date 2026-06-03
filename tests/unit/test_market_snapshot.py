"""Tests for the market snapshot artifact (Phase 02)."""
from __future__ import annotations

import json

import pytest

from backend.reporting import market_snapshot as ms


_DBD_OVERVIEW = {
    "current_price": 50200.0,
    "market_cap": 50200.0 * 94_489_262,
    "issue_share": 94_489_262.0,
    "highest_price1_year": 62000.0,
    "lowest_price1_year": 41000.0,
    "foreigner_percentage": 0.30,
    "free_float": 40_000_000.0,
    "average_match_volume1_month": 120000.0,
    "dividend_per_share_tsr": None,
    "target_price": 58000.0,
}


def test_fetch_market_snapshot_maps_fields(monkeypatch):
    monkeypatch.setattr(ms, "_fetch_overview_row", lambda ticker: dict(_DBD_OVERVIEW))
    snap = ms.fetch_market_snapshot("dbd")

    assert snap.ticker == "DBD"
    assert snap.shares_outstanding == 94_489_262.0
    assert snap.last_price == 50200.0
    assert snap.high_52w == 62000.0
    assert snap.low_52w == 41000.0
    assert snap.vendor_target_price == 58000.0
    # shares fact helper returns absolute count
    assert snap.shares_outstanding_fact() == 94_489_262.0
    # provenance recorded for present fields, absent for missing (dividend)
    assert snap.provenance["shares_outstanding"] == ms.SOURCE_VCI_OVERVIEW
    assert "dividend_per_share" not in snap.provenance
    # consistent market cap -> no warning
    assert snap.warnings == []


def test_consistency_warning_on_market_cap_mismatch(monkeypatch):
    bad = dict(_DBD_OVERVIEW)
    bad["market_cap"] = 1.0  # wildly inconsistent
    monkeypatch.setattr(ms, "_fetch_overview_row", lambda ticker: bad)
    snap = ms.fetch_market_snapshot("DBD")
    assert any("market_cap deviates" in w for w in snap.warnings)


def test_write_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "_fetch_overview_row", lambda ticker: dict(_DBD_OVERVIEW))
    snap = ms.fetch_market_snapshot("DBD")
    path = ms.write_snapshot_artifact(snap, base_dir=tmp_path)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["shares_outstanding"] == 94_489_262.0

    loaded = ms.load_cached_snapshot("DBD", base_dir=tmp_path)
    assert loaded is not None
    assert loaded.shares_outstanding == 94_489_262.0


def test_get_snapshot_falls_back_to_cache(tmp_path, monkeypatch):
    # First, seed a cache
    monkeypatch.setattr(ms, "_fetch_overview_row", lambda ticker: dict(_DBD_OVERVIEW))
    ms.write_snapshot_artifact(ms.fetch_market_snapshot("DBD"), base_dir=tmp_path)

    # Now make the live fetch fail -> must serve from cache
    def _boom(ticker):
        raise RuntimeError("network down")

    monkeypatch.setattr(ms, "_fetch_overview_row", _boom)
    snap = ms.get_market_snapshot("DBD", persist=False, base_dir=tmp_path)
    assert snap is not None
    assert snap.shares_outstanding == 94_489_262.0
    assert any("served from cache" in w for w in snap.warnings)


def test_get_snapshot_returns_none_when_no_data(tmp_path, monkeypatch):
    def _boom(ticker):
        raise RuntimeError("network down")

    monkeypatch.setattr(ms, "_fetch_overview_row", _boom)
    snap = ms.get_market_snapshot("ZZZ", persist=False, base_dir=tmp_path)
    assert snap is None
