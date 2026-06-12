"""Shares outstanding helpers for valuation and report calculations.

Report-facing valuation must prefer explicit share-count facts. EPS-implied
shares are useful for reconciliation diagnostics, but they are not a reliable
source for current diluted shares or target-price division.
"""
from __future__ import annotations

from typing import Any

from backend.analytics._entry import entry_value
from backend.facts.normalizer import FactTable

_SHARE_FACT_KEYS = (
    "shares_outstanding.ending",
    "shares_outstanding.weighted_avg",
    "shares_outstanding.total",
)


def _entry_value(entry: Any) -> float | None:
    try:
        return entry_value(entry)
    except TypeError:
        return None


def _normalise_share_value_to_mn(value: float | None) -> float | None:
    """Return shares in millions.

    Canonical share facts are normally absolute share counts. A small number is
    treated as already expressed in millions to support legacy fixtures.
    """
    if value is None or value <= 0:
        return None
    if value > 1_000_000:
        return value / 1_000_000
    return value


def explicit_shares_mn(fact_table: FactTable, latest_fy: str | None) -> float | None:
    """Read explicit shares outstanding from canonical facts, in millions."""
    if not latest_fy:
        return None
    for key in _SHARE_FACT_KEYS:
        value = _entry_value(fact_table.get(key, {}).get(latest_fy))
        shares_mn = _normalise_share_value_to_mn(value)
        if shares_mn is not None:
            return shares_mn
    return None


def eps_implied_shares_mn(fact_table: FactTable, latest_fy: str | None) -> float | None:
    """Compute EPS-implied shares in millions for diagnostics only."""
    if not latest_fy:
        return None
    ni = _entry_value(fact_table.get("net_income.parent", {}).get(latest_fy))
    eps = _entry_value(fact_table.get("eps.basic", {}).get(latest_fy))
    if ni and eps and eps > 0:
        return (ni * 1_000) / eps
    return None


def reportable_shares_mn(fact_table: FactTable, latest_fy: str | None) -> float | None:
    """Return shares that are safe for target-price and market-cap arithmetic."""
    return explicit_shares_mn(fact_table, latest_fy)


def eps_reconciles(
    net_income_bn: float | None,
    weighted_avg_shares_mn: float | None,
    eps_vnd: float | None,
    tol: float = 0.03,
) -> bool:
    """Check that reported EPS matches net income / weighted-average shares.

    Audit NUMERIC-01: EPS (VND/share) must reconcile with NPATMI and the share
    basis actually used. net_income_bn is in VND billion, shares in millions, so
    implied EPS = net_income_bn * 1_000 / shares_mn (VND/share).

    Returns True only when |reported - implied| / |reported| <= tol. Returns
    False if any input is missing or non-positive (cannot be verified → block).
    """
    if not net_income_bn or not weighted_avg_shares_mn or not eps_vnd:
        return False
    if weighted_avg_shares_mn <= 0 or eps_vnd <= 0:
        return False
    implied = net_income_bn * 1_000.0 / weighted_avg_shares_mn
    return abs(eps_vnd - implied) / abs(eps_vnd) <= tol
