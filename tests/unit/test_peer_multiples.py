"""Task 3: peer-multiples for relative valuation (P/E, EV/EBITDA) from vnstock.

Pure logic + injectable loaders so it's tested without network/DB. peer_pe = price/EPS,
peer_ev_ebitda = (market_cap + debt - cash)/EBITDA; medians require >=3 valid peers
(no fabrication — relative valuation stays pending below that).
"""
from __future__ import annotations

import pytest

from backend.valuation import peer_multiples as pm


def test_peer_pe_and_ev_ebitda_pure():
    assert pm._peer_pe(price=90_000.0, eps=6_000.0) == pytest.approx(15.0)
    assert pm._peer_pe(price=90_000.0, eps=0.0) is None      # no division by zero
    assert pm._peer_pe(price=90_000.0, eps=-100.0) is None   # negative EPS dropped
    # EV = market_cap + debt - cash; EV/EBITDA
    ev_ebitda = pm._peer_ev_ebitda(market_cap=1000.0, total_debt=200.0, cash_sti=100.0, ebitda=110.0)
    assert ev_ebitda == pytest.approx((1000 + 200 - 100) / 110)


def test_median_requires_three_valid():
    assert pm._median([10.0, 12.0, 14.0]) == pytest.approx(12.0)
    assert pm._median([10.0, 20.0]) is None          # < 3 → not enough peers
    assert pm._median([10.0, None, 12.0, 14.0]) == pytest.approx(12.0)  # drops None


def test_build_peer_pack_from_injected_loaders():
    peers = ["IMP", "OPC", "TRA", "PMC"]
    # price/market_cap (live overview surrogate) + financials (production surrogate)
    prices = {"IMP": (46150.0, 7107.0), "OPC": (40000.0, 2000.0), "TRA": (90000.0, 3000.0), "PMC": (50000.0, 1000.0)}
    facts = {
        "IMP": {"eps": 4000.0, "ebitda": 500.0, "total_debt": 100.0, "cash_sti": 200.0},
        "OPC": {"eps": 3500.0, "ebitda": 250.0, "total_debt": 50.0, "cash_sti": 80.0},
        "TRA": {"eps": 6000.0, "ebitda": 400.0, "total_debt": 0.0, "cash_sti": 300.0},
        "PMC": {"eps": 5000.0, "ebitda": 150.0, "total_debt": 0.0, "cash_sti": 120.0},
    }
    pack = pm.build_peer_pack(
        "DHG",
        peer_tickers=peers,
        price_loader=lambda t: prices.get(t),
        fact_loader=lambda t: facts.get(t),
    )
    assert pack["peer_pe_median"] is not None
    assert pack["peer_ev_ebitda_median"] is not None
    assert pack["n_pe"] >= 3
    assert "DHG" not in pack["peers_used"]
    assert pack["peer_data_source"].startswith("vnstock")


def test_build_peer_pack_stays_pending_with_too_few_peers():
    pack = pm.build_peer_pack(
        "DHG", peer_tickers=["IMP", "OPC"],
        price_loader=lambda t: (40000.0, 1000.0),
        fact_loader=lambda t: {"eps": 4000.0, "ebitda": 100.0, "total_debt": 0.0, "cash_sti": 50.0},
    )
    assert pack["peer_pe_median"] is None
    assert pack["relative_valuation_status"] == "pending_peer_dataset"


def test_min_peers_is_defined_and_median_requires_it():
    # Regression: MIN_PEERS was referenced but never defined, raising NameError
    # on every build_peer_pack call and silently disabling relative valuation.
    assert isinstance(pm.MIN_PEERS, int) and pm.MIN_PEERS >= 1
    assert pm._median([10.0] * pm.MIN_PEERS) is not None
    assert pm._median([10.0] * (pm.MIN_PEERS - 1)) is None


def test_offline_price_loader_reads_manual_csv(tmp_path):
    csv = tmp_path / "market_prices.csv"
    csv.write_text(
        "as_of_date,ticker,price,status,source\n"
        "2026-06-19,IMP,45500,accepted,cafef_price_history\n",
        encoding="utf-8",
    )
    loaded = pm._offline_price_loader("IMP", manual_csv_path=csv)
    assert loaded is not None
    price, _market_cap = loaded
    assert price == pytest.approx(45500.0)


def test_offline_price_loader_returns_none_when_absent(tmp_path):
    csv = tmp_path / "market_prices.csv"
    csv.write_text("as_of_date,ticker,price,status,source\n", encoding="utf-8")
    assert pm._offline_price_loader("ZZZ", manual_csv_path=csv) is None


def test_build_peer_pack_offline_wires_injected_loaders():
    # build_peer_pack_offline must accept injected loaders so the median math is
    # the same proven path as build_peer_pack — only the default source differs.
    prices = {"IMP": (46150.0, 7107.0), "OPC": (40000.0, 2000.0), "TRA": (90000.0, 3000.0)}
    facts = {
        "IMP": {"eps": 4000.0, "ebitda": 500.0, "total_debt": 100.0, "cash_sti": 200.0},
        "OPC": {"eps": 3500.0, "ebitda": 250.0, "total_debt": 50.0, "cash_sti": 80.0},
        "TRA": {"eps": 6000.0, "ebitda": 400.0, "total_debt": 0.0, "cash_sti": 300.0},
    }
    pack = pm.build_peer_pack_offline(
        "DHG",
        peer_tickers=list(prices),
        price_loader=lambda t: prices.get(t),
        fact_loader=lambda t: facts.get(t),
    )
    assert pack["peer_pe_median"] is not None
    assert pack["relative_valuation_status"] == "peer_data_available"
