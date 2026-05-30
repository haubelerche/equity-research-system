"""Ticker mapping for catalyst events — Source-Provenance Rebuild, Phase 5.

Maps an event to a specific ticker (explicit) or to a sector when no single ticker can
be attributed (sector_level). An event must be one or the other — never unmapped.
"""
from __future__ import annotations

from dataclasses import dataclass

# MVP pharma universe and simple alias hints.
PHARMA_TICKERS: frozenset[str] = frozenset({"DHG", "IMP", "DMC", "TRA", "DBD"})

_NAME_HINTS: dict[str, str] = {
    "dược hậu giang": "DHG", "dhg pharma": "DHG", "dhg": "DHG",
    "imexpharm": "IMP", "imp": "IMP",
    "domesco": "DMC", "dmc": "DMC",
    "traphaco": "TRA", "tra": "TRA",
    "bidiphar": "DBD", "dbd": "DBD",
}

SECTOR = "pharma_vn"


@dataclass
class TickerMapping:
    ticker: str | None
    level: str  # "explicit" | "sector_level"


def map_event_to_ticker(text: str, explicit_ticker: str | None = None) -> TickerMapping:
    """Resolve a ticker mapping for an event.

    If an explicit ticker is given (and valid) → explicit. Else scan text for a company
    name/ticker hint. If none found → sector_level (never silently unmapped).
    """
    if explicit_ticker and explicit_ticker.strip().upper() in PHARMA_TICKERS:
        return TickerMapping(ticker=explicit_ticker.strip().upper(), level="explicit")

    haystack = (text or "").lower()
    for hint, ticker in _NAME_HINTS.items():
        if hint in haystack:
            return TickerMapping(ticker=ticker, level="explicit")

    return TickerMapping(ticker=None, level="sector_level")
