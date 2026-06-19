"""Deterministic market-price resolution for valuation and report gates.

All public values returned by this module are VND/share. Storage-facing sources
such as fact.price_history and raw vnstock quote caches store Vietnamese equity
prices in thousand VND, so normalization is centralized here.
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class MarketPriceResolution:
    ticker: str
    current_price: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    volume: float | None = None
    price_as_of: str = ""
    source: str = ""
    staleness_days: int | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def has_required_intraday_fields(self) -> bool:
        return self.current_price is not None and self.high is not None and self.low is not None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _positive_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None
    if number != number or number <= 0:
        return None
    return number


def _storage_price_to_vnd(value: Any) -> float | None:
    number = _positive_float(value)
    if number is None:
        return None
    return number * 1000.0 if number < 1000.0 else number


def _manual_price_to_vnd(value: Any) -> float | None:
    return _positive_float(value)


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    raw = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        return None


def _staleness(as_of: date | None, today: date) -> int | None:
    if as_of is None:
        return None
    return max((today - as_of).days, 0)


def _resolution(
    *,
    ticker: str,
    current_price: float | None,
    open_price: float | None,
    high: float | None,
    low: float | None,
    high_52w: float | None,
    low_52w: float | None,
    volume: float | None,
    as_of: date | None,
    source: str,
    today: date,
    warnings: list[str] | None = None,
) -> MarketPriceResolution | None:
    if current_price is None:
        return None
    return MarketPriceResolution(
        ticker=ticker.upper(),
        current_price=current_price,
        open=open_price,
        high=high,
        low=low,
        high_52w=high_52w,
        low_52w=low_52w,
        volume=volume,
        price_as_of=as_of.isoformat() if as_of else "",
        source=source,
        staleness_days=_staleness(as_of, today),
        warnings=warnings or [],
    )


def _from_manual_csv(ticker: str, *, today: date, path: Path) -> MarketPriceResolution | None:
    if not path.exists():
        return None
    accepted: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if (row.get("ticker") or "").strip().upper() != ticker:
                continue
            if (row.get("status") or "").strip().lower() != "accepted":
                continue
            accepted.append(row)
    if not accepted:
        return None

    def key(row: dict[str, Any]) -> date:
        return _parse_date(row.get("as_of_date")) or date.min

    row = sorted(accepted, key=key)[-1]
    as_of = _parse_date(row.get("as_of_date"))
    price = _manual_price_to_vnd(row.get("price"))
    open_price = _manual_price_to_vnd(row.get("open")) or price
    high = _manual_price_to_vnd(row.get("high")) or price
    low = _manual_price_to_vnd(row.get("low")) or price
    high_52w = _manual_price_to_vnd(row.get("high_52w")) or high
    low_52w = _manual_price_to_vnd(row.get("low_52w")) or low
    return _resolution(
        ticker=ticker,
        current_price=price,
        open_price=open_price,
        high=high,
        low=low,
        high_52w=high_52w,
        low_52w=low_52w,
        volume=_positive_float(row.get("volume")),
        as_of=as_of,
        source=f"manual_market_prices:{row.get('source') or 'manual'}",
        today=today,
    )


def _from_fact_store(ticker: str, *, today: date, days: int, store: Any | None) -> MarketPriceResolution | None:
    try:
        if store is None:
            from backend.database.fact_store import PostgresFactStore

            store = PostgresFactStore()
        start = today - timedelta(days=days)
        frame = store.get_price_history(ticker=ticker, start=start.isoformat(), end=today.isoformat())
    except Exception as exc:  # noqa: BLE001
        return MarketPriceResolution(ticker=ticker, source="fact.price_history", warnings=[f"fact_store_failed:{exc}"])

    if frame is None or frame.empty:
        return None
    df = frame.copy()
    if "trade_date" not in df.columns:
        return None
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
    df = df.dropna(subset=["trade_date"]).sort_values("trade_date")
    if df.empty:
        return None
    latest = df.iloc[-1]
    as_of = latest["trade_date"]
    high_series = df.get("high")
    low_series = df.get("low")
    return _resolution(
        ticker=ticker,
        current_price=_storage_price_to_vnd(latest.get("adjusted_close") or latest.get("close")),
        open_price=_storage_price_to_vnd(latest.get("open")),
        high=_storage_price_to_vnd(latest.get("high")),
        low=_storage_price_to_vnd(latest.get("low")),
        high_52w=_storage_price_to_vnd(pd.to_numeric(high_series, errors="coerce").max()) if high_series is not None else None,
        low_52w=_storage_price_to_vnd(pd.to_numeric(low_series, errors="coerce").min()) if low_series is not None else None,
        volume=_positive_float(latest.get("volume")),
        as_of=as_of,
        source="fact.price_history",
        today=today,
    )


def _quote_files(raw_root: Path, ticker: str) -> list[Path]:
    if not raw_root.exists():
        return []
    return sorted(raw_root.glob(f"**/{ticker.upper()}_quote_history.json"))


def _rows_from_quote_file(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get("data") or payload.get("records") or []
        return [row for row in rows if isinstance(row, dict)]
    return []


def _from_raw_cache(ticker: str, *, today: date, raw_root: Path) -> MarketPriceResolution | None:
    rows: list[dict[str, Any]] = []
    selected_path: Path | None = None
    for path in _quote_files(raw_root, ticker):
        try:
            parsed = _rows_from_quote_file(path)
        except Exception:
            continue
        if parsed:
            rows = parsed
            selected_path = path
    if not rows:
        return None

    parsed_rows: list[tuple[date, dict[str, Any]]] = []
    for row in rows:
        trade_date = _parse_date(row.get("date") or row.get("time") or row.get("datetime") or row.get("timestamp"))
        if trade_date:
            parsed_rows.append((trade_date, row))
    if not parsed_rows:
        return None
    parsed_rows.sort(key=lambda item: item[0])
    as_of, latest = parsed_rows[-1]
    highs = [_storage_price_to_vnd(row.get("high")) for _d, row in parsed_rows]
    lows = [_storage_price_to_vnd(row.get("low")) for _d, row in parsed_rows]
    rel_path = selected_path.relative_to(ROOT) if selected_path and selected_path.is_relative_to(ROOT) else selected_path
    return _resolution(
        ticker=ticker,
        current_price=_storage_price_to_vnd(latest.get("adjusted_close") or latest.get("adj_close") or latest.get("close")),
        open_price=_storage_price_to_vnd(latest.get("open")),
        high=_storage_price_to_vnd(latest.get("high")),
        low=_storage_price_to_vnd(latest.get("low")),
        high_52w=max((v for v in highs if v is not None), default=None),
        low_52w=min((v for v in lows if v is not None), default=None),
        volume=_positive_float(latest.get("volume")),
        as_of=as_of,
        source=f"raw_market_cache:{rel_path}",
        today=today,
        warnings=[] if len(parsed_rows) >= 200 else ["raw_cache_short_history_for_52w"],
    )


def _from_cached_artifact(
    ticker: str,
    *,
    today: date,
    run_id: str,
    base_dir: Path | str | None,
) -> MarketPriceResolution | None:
    if not run_id:
        return None
    try:
        from backend.reporting.market_data_artifact import load_cached_market_data

        artifact = load_cached_market_data(ticker, run_id=run_id, base_dir=base_dir)
    except Exception:
        return None
    if artifact is None:
        return None
    stats = artifact.trading_statistics
    latest = artifact.price_history[-1] if artifact.price_history else {}
    as_of = _parse_date(artifact.as_of_date or latest.get("trade_date"))
    return _resolution(
        ticker=ticker,
        current_price=_storage_price_to_vnd(stats.last_close or latest.get("close")),
        open_price=_storage_price_to_vnd(latest.get("open")),
        high=_storage_price_to_vnd(latest.get("high")),
        low=_storage_price_to_vnd(latest.get("low")),
        high_52w=_storage_price_to_vnd(stats.high_52w),
        low_52w=_storage_price_to_vnd(stats.low_52w),
        volume=_positive_float(latest.get("volume")),
        as_of=as_of,
        source=f"market_data_artifact:{run_id}",
        today=today,
    )


def _from_live_cafef(ticker: str, *, today: date) -> MarketPriceResolution | None:
    try:
        from backend.documents.connectors.cafef_market_connector import fetch_latest_price

        quote = fetch_latest_price(ticker)
    except Exception as exc:  # noqa: BLE001
        return MarketPriceResolution(ticker=ticker, source="cafef_price_history", warnings=[f"cafef_failed:{exc}"])
    if not quote.last_price:
        return None
    as_of = _parse_date(quote.as_of_date)
    return _resolution(
        ticker=ticker,
        current_price=quote.last_price,
        open_price=None,
        high=None,
        low=None,
        high_52w=None,
        low_52w=None,
        volume=quote.volume,
        as_of=as_of,
        source=quote.source,
        today=today,
        warnings=["live_price_missing_intraday_fields"],
    )


def resolve_market_price(
    ticker: str,
    *,
    as_of_date: date | None = None,
    allow_live: bool = False,
    store: Any | None = None,
    manual_csv_path: Path | str | None = None,
    raw_root: Path | str | None = None,
    run_id: str = "",
    market_data_base_dir: Path | str | None = None,
    days: int = 400,
) -> MarketPriceResolution:
    """Resolve the latest market price without live I/O unless explicitly allowed."""
    symbol = ticker.strip().upper()
    today = as_of_date or datetime.now(UTC).date()
    manual_path = Path(manual_csv_path) if manual_csv_path else ROOT / "data" / "manual" / "market_prices.csv"
    raw_path = Path(raw_root) if raw_root else ROOT / "data" / "raw" / "market"

    warnings: list[str] = []
    for candidate in (
        _from_manual_csv(symbol, today=today, path=manual_path),
        _from_fact_store(symbol, today=today, days=days, store=store),
        _from_raw_cache(symbol, today=today, raw_root=raw_path),
        _from_cached_artifact(symbol, today=today, run_id=run_id, base_dir=market_data_base_dir),
    ):
        if candidate is None:
            continue
        if candidate.current_price is None:
            warnings.extend(candidate.warnings)
            continue
        if warnings:
            return MarketPriceResolution(**{**candidate.to_dict(), "warnings": warnings + candidate.warnings})
        return candidate

    if allow_live:
        live = _from_live_cafef(symbol, today=today)
        if live and live.current_price is not None:
            return live
        if live:
            warnings.extend(live.warnings)

    return MarketPriceResolution(
        ticker=symbol,
        source="missing_market_price",
        warnings=warnings + ["missing_current_price"],
    )
