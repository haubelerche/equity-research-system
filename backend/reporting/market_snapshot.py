"""Market snapshot artifact: shares outstanding + sidebar market data.

This module produces a :class:`MarketSnapshot` for a ticker from the vnstock VCI
company-overview endpoint, which is the canonical *market-source* provider for
fields that do NOT come from the financial statements:

- ``shares_outstanding`` (issue_share) — required to unblock the FCFF/FCFE target
  price (the valuation engines intentionally block target price when the
  shares-outstanding fact is missing, to avoid EPS-implied share-count errors);
- last price, market cap, 52-week range, foreign room, average volume, etc.

Design goals:
- **Code-first / sourced**: every field records its provider in ``provenance``;
  we never fabricate. Missing fields stay ``None``.
- **Reproducible**: snapshots are persisted through the run storage contract.
- **Ticker-agnostic**: no per-ticker branching. The only ticker-specific input is
  the symbol passed to the provider.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]

SOURCE_VCI_OVERVIEW = "vnstock_overview_vci"


@dataclass
class MarketSnapshot:
    ticker: str
    as_of_date: str
    retrieved_at: str
    source: str
    last_price: float | None = None          # VND/share
    market_cap: float | None = None          # VND (absolute)
    shares_outstanding: float | None = None  # absolute share count
    high_52w: float | None = None            # VND/share
    low_52w: float | None = None             # VND/share
    foreign_pct: float | None = None         # fraction 0..1
    free_float: float | None = None          # absolute share count
    avg_volume_1m: float | None = None       # shares/session
    dividend_per_share: float | None = None  # VND/share
    vendor_target_price: float | None = None  # third-party target; NOT our model output
    provenance: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def shares_outstanding_fact(self) -> float | None:
        """Absolute shares-outstanding count suitable for the canonical fact table."""
        if self.shares_outstanding and self.shares_outstanding > 0:
            return float(self.shares_outstanding)
        return None


def _f(value: Any) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    # pandas NaN guard
    return None if v != v else v


def _fetch_overview_row(ticker: str) -> dict[str, Any]:
    """Fetch the one-row vnstock VCI company overview as a plain dict.

    Raises on any provider/network error so the caller can fall back to cache.
    """
    from vnstock.api.company import Company  # local import: optional/heavy dependency

    overview = Company(symbol=ticker, source="VCI").overview()
    if overview is None or len(overview) == 0:
        raise ValueError(f"Empty overview for {ticker}")
    row = overview.iloc[0]
    return {col: row.get(col) for col in overview.columns}


def fetch_market_snapshot(ticker: str) -> MarketSnapshot:
    """Build a MarketSnapshot from the live vnstock VCI overview. May raise."""
    ticker = ticker.strip().upper()
    row = _fetch_overview_row(ticker)
    now = datetime.now(timezone.utc).isoformat()

    last_price = _f(row.get("current_price"))
    market_cap = _f(row.get("market_cap"))
    shares = _f(row.get("issue_share"))

    snap = MarketSnapshot(
        ticker=ticker,
        as_of_date=now[:10],
        retrieved_at=now,
        source=SOURCE_VCI_OVERVIEW,
        last_price=last_price,
        market_cap=market_cap,
        shares_outstanding=shares,
        high_52w=_f(row.get("highest_price1_year")),
        low_52w=_f(row.get("lowest_price1_year")),
        foreign_pct=_f(row.get("foreigner_percentage")),
        free_float=_f(row.get("free_float")),
        avg_volume_1m=_f(row.get("average_match_volume1_month")),
        dividend_per_share=_f(row.get("dividend_per_share_tsr")),
        vendor_target_price=_f(row.get("target_price")),
    )
    for key in (
        "last_price", "market_cap", "shares_outstanding", "high_52w", "low_52w",
        "foreign_pct", "free_float", "avg_volume_1m", "dividend_per_share",
        "vendor_target_price",
    ):
        if getattr(snap, key) is not None:
            snap.provenance[key] = SOURCE_VCI_OVERVIEW

    _check_consistency(snap)
    return snap


def _check_consistency(snap: MarketSnapshot) -> None:
    """Record a warning when market_cap deviates from last_price * shares by >2%."""
    if snap.market_cap and snap.last_price and snap.shares_outstanding:
        implied = snap.last_price * snap.shares_outstanding
        if implied > 0:
            dev = abs(snap.market_cap - implied) / implied
            if dev > 0.02:
                snap.warnings.append(
                    f"market_cap deviates {dev:.1%} from last_price*shares "
                    f"({snap.market_cap:,.0f} vs {implied:,.0f})"
                )


def write_snapshot_artifact(snap: MarketSnapshot, base_dir: Path | str | None = None) -> Path:
    """Persist a snapshot inside an explicitly supplied run directory."""
    if base_dir is None:
        raise ValueError("base_dir must be an explicit temporary working directory")
    out_dir = Path(base_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "market_snapshot.json"
    path.write_text(json.dumps(snap.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_cached_snapshot(ticker: str, base_dir: Path | str | None = None) -> MarketSnapshot | None:
    """Load the run-scoped market snapshot, or None if none exists."""
    ticker = ticker.strip().upper()
    if base_dir is None:
        return None
    path = Path(base_dir) / "market_snapshot.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    known = MarketSnapshot.__dataclass_fields__.keys()
    return MarketSnapshot(**{k: v for k, v in data.items() if k in known})


def get_market_snapshot(
    ticker: str,
    *,
    persist: bool = True,
    allow_cache_fallback: bool = True,
    base_dir: Path | str | None = None,
) -> MarketSnapshot | None:
    """Return a market snapshot, preferring a fresh fetch, falling back to cache.

    Returns ``None`` only when both the live fetch fails and no cache exists.
    """
    ticker = ticker.strip().upper()
    try:
        snap = fetch_market_snapshot(ticker)
        if persist and base_dir is not None:
            try:
                write_snapshot_artifact(snap, base_dir)
            except OSError as exc:  # pragma: no cover - disk failure is non-fatal
                _logger.warning("market snapshot persist failed for %s: %s", ticker, exc)
        return snap
    except Exception as exc:  # noqa: BLE001 - provider/network errors are expected offline
        _logger.warning("live market snapshot fetch failed for %s: %s", ticker, exc)
        if allow_cache_fallback:
            cached = load_cached_snapshot(ticker, base_dir)
            if cached is not None:
                cached.warnings.append("served from cache; live fetch failed")
                return cached
        return None
