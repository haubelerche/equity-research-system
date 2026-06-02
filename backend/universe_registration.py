from __future__ import annotations

from typing import Any

from backend.dataset.config_io import UNIVERSE_FILE, load_universe_rows


DEFAULT_UNIVERSE_ID = "vietnam_pharma_full"
DEFAULT_UNIVERSE_NAME = "Vietnam Pharma Full Universe"
DEFAULT_ENABLED_METHODS = ["dcf", "pe", "pb", "ev_ebitda"]


def universe_row_for_ticker(ticker: str) -> dict[str, str] | None:
    normalized = ticker.strip().upper()
    for row in load_universe_rows():
        if row.get("ticker", "").strip().upper() == normalized:
            return row
    return None


def ensure_ticker_registered_from_universe(store: Any, ticker: str) -> dict[str, Any]:
    """Ensure a universe ticker exists in ref.companies before creating a run."""
    normalized = ticker.strip().upper()
    row = universe_row_for_ticker(normalized)
    if row is None:
        raise ValueError(
            f"Ticker {normalized} is not present in {UNIVERSE_FILE}. "
            "Add it to the configured universe before submitting a research run."
        )

    company_name = row.get("company_name") or normalized
    exchange = row.get("exchange") or None
    segment = row.get("segment") or "unknown"
    store.ensure_company_reference(
        ticker=normalized,
        company_name_vi=company_name,
        company_name_en=None,
        exchange=exchange,
        sector=segment,
        subsector=segment,
        universe_id=DEFAULT_UNIVERSE_ID,
        universe_name=DEFAULT_UNIVERSE_NAME,
        peer_group=segment,
        enabled_methods=DEFAULT_ENABLED_METHODS,
    )
    return {
        "ticker": normalized,
        "company_name_vi": company_name,
        "exchange": exchange,
        "sector": segment,
    }
