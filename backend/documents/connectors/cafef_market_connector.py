"""CafeF current market-price connector.

vnstock's VCI overview is the primary market-data source but returns nothing for
many thin UPCOM names. CafeF publishes a machine-readable daily price-history
endpoint that covers HOSE/HNX/UPCOM, so it is the hard-wired fallback for the
*current market price* (and trading volume) that the valuation needs for
upside / relative multiples.

    GET https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/PriceHistory.ashx
        ?Symbol=<TICKER>&StartDate=&EndDate=&PageIndex=1&PageSize=<n>

The legacy ``s.cafef.vn/Ajax/...`` host now rejects every request with
``{"Success":false,"Message":"symbol is null or empty"}`` regardless of the
``Symbol`` query param; the live handler moved under ``cafef.vn/du-lieu/``. The
JSON shape (``Data.Data`` rows with ``GiaDieuChinh`` / ``GiaDongCua`` / ``Ngay`` /
``KhoiLuongKhopLenh``) is unchanged.

Prices are returned in thousand VND (e.g. 97.5 → 97,500 VND/share).
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

_BASE_URL = (
    "https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/PriceHistory.ashx"
    "?Symbol={symbol}&StartDate=&EndDate=&PageIndex=1&PageSize={page_size}"
)
SOURCE_NAME = "cafef_price_history"


@dataclass
class CafeFQuote:
    ticker: str
    last_price: Optional[float]   # VND/share (already scaled from thousand VND)
    as_of_date: Optional[str]     # trade date, ISO YYYY-MM-DD
    volume: Optional[float]       # matched volume (shares)
    source_url: str
    source: str = SOURCE_NAME


def build_url(ticker: str, page_size: int = 5) -> str:
    return _BASE_URL.format(symbol=ticker.strip().upper(), page_size=page_size)


def _default_http_get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "maer-cafef-market/1.0",
            "Referer": "https://cafef.vn/",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (TLS verified)
        return resp.read().decode("utf-8", errors="replace")


def _f(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.replace(",", "").strip()
        if not value:
            return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if v != v else v


def _iso_date(raw: Any) -> Optional[str]:
    """CafeF dates are dd/mm/yyyy → ISO YYYY-MM-DD."""
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(raw).strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _rows_from_payload(payload: dict) -> list[dict]:
    """CafeF nests rows under Data.Data; tolerate a few shapes."""
    data = payload.get("Data", payload)
    if isinstance(data, dict):
        rows = data.get("Data") or data.get("data") or []
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    return [r for r in rows if isinstance(r, dict)]


def parse_quote(ticker: str, raw_json: str, source_url: str) -> CafeFQuote:
    """Parse the most-recent close from a CafeF price-history JSON response."""
    empty = CafeFQuote(ticker.upper(), None, None, None, source_url)
    try:
        payload = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return empty
    rows = _rows_from_payload(payload)
    if not rows:
        return empty
    row = rows[0]  # most recent trading day first
    # Prefer adjusted close, then raw close; CafeF reports them in thousand VND.
    price_k = _f(row.get("GiaDieuChinh")) or _f(row.get("GiaDongCua")) or _f(row.get("GiaDongCuaShow"))
    last_price = price_k * 1000 if price_k is not None else None
    return CafeFQuote(
        ticker=ticker.upper(),
        last_price=last_price,
        as_of_date=_iso_date(row.get("Ngay") or row.get("NgayDuLieu")),
        volume=_f(row.get("KhoiLuongKhopLenh")),
        source_url=source_url,
    )


def fetch_latest_price(
    ticker: str, http_get: Optional[Callable[[str], str]] = None
) -> CafeFQuote:
    """Fetch the latest CafeF close for *ticker*. http_get injectable for tests.

    Never raises: returns an empty quote (last_price=None) on any failure.
    """
    url = build_url(ticker)
    get = http_get or _default_http_get
    try:
        raw = get(url)
    except Exception:  # noqa: BLE001 — network/provider errors are non-fatal
        return CafeFQuote(ticker.upper(), None, None, None, url)
    return parse_quote(ticker, raw, url)
