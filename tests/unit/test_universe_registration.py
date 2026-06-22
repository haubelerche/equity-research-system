from __future__ import annotations

import pytest

from backend.universe_registration import ensure_ticker_registered_from_universe


class FakeStore:
    def __init__(self) -> None:
        self.registered: dict[str, dict] = {}

    def ensure_company_reference(self, **kwargs) -> None:
        self.registered[kwargs["ticker"]] = kwargs


def test_registers_dp3_from_configured_universe() -> None:
    store = FakeStore()

    result = ensure_ticker_registered_from_universe(store, "dp3")

    assert result["ticker"] == "DP3"
    assert result["exchange"] == "UPCOM"
    assert store.registered["DP3"]["company_name_vi"] == "Cong ty Co phan Duoc pham Trung uong 3"
    assert store.registered["DP3"]["peer_group_id"] == "vn_pharma_listed"


def test_agp_removed_from_universe_is_not_registerable() -> None:
    # AGP was dropped from the universe; it must no longer resolve from config.
    store = FakeStore()

    with pytest.raises(ValueError, match="not present"):
        ensure_ticker_registered_from_universe(store, "agp")


def test_unknown_ticker_fails_before_database_fk_violation() -> None:
    store = FakeStore()

    with pytest.raises(ValueError, match="not present"):
        ensure_ticker_registered_from_universe(store, "NO_SUCH_TICKER")


def test_non_healthcare_listing_mismatch_is_not_registerable() -> None:
    store = FakeStore()

    with pytest.raises(ValueError, match="not present"):
        ensure_ticker_registered_from_universe(store, "DGW")
