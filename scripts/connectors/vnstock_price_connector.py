from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd
from vnstock import Vnstock

from scripts.dataset.config_io import ROOT, load_universe_tickers
from scripts.db.fact_store import PostgresFactStore, PriceRow
from scripts.db.source_registry import SourceRegistry, SourceVersionInput


CONNECTOR_VERSION = "vnstock_price_connector_v1"


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _normalize_history(df: pd.DataFrame, ticker: str, source_version_id: str | None) -> list[PriceRow]:
    if df.empty:
        return []

    column_aliases = {
        "time": "date",
        "datetime": "date",
        "timestamp": "date",
    }
    frame = df.rename(columns=column_aliases).copy()
    if "date" not in frame.columns:
        raise ValueError(f"Ticker {ticker} quote response missing date/time column")

    rows: list[PriceRow] = []
    now = datetime.now(UTC)
    for _, row in frame.iterrows():
        dt = pd.to_datetime(row["date"]).date()
        rows.append(
            PriceRow(
                ticker=ticker,
                date=dt,
                open=_to_float(row.get("open")),
                high=_to_float(row.get("high")),
                low=_to_float(row.get("low")),
                close=_to_float(row.get("close")),
                volume=_to_int(row.get("volume")),
                value=_to_float(row.get("value")),
                source_version_id=source_version_id,
                ingested_at=now,
            )
        )
    return rows


def _fetch_history(ticker: str, start: date, end: date, source: str) -> pd.DataFrame:
    client = Vnstock(symbol=ticker, source=source)
    return client.quote.history(start=start.isoformat(), end=end.isoformat(), interval="1D")


def sync_ticker_price(
    ticker: str,
    start: date,
    end: date,
    store: PostgresFactStore,
    registry: SourceRegistry,
) -> int:
    errors: list[Exception] = []
    frame: pd.DataFrame | None = None
    provider_used = "KBS"
    for provider in ("KBS", "VCI"):
        try:
            frame = _fetch_history(ticker=ticker, start=start, end=end, source=provider)
            provider_used = provider
            break
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
    if frame is None:
        error_text = "; ".join(str(e) for e in errors)
        raise RuntimeError(f"Unable to fetch price history for {ticker}: {error_text}")

    payload_json = frame.to_json(date_format="iso", orient="records")
    payload = payload_json.encode("utf-8")
    source_uri = f"vnstock://{provider_used.lower()}/quote/history/{ticker}?start={start}&end={end}&interval=1D"
    raw_path = ROOT / "dataset" / "raw" / "market" / end.isoformat() / f"{ticker}_quote_history.json"
    checksum = registry.save_raw_snapshot(payload=payload, out_path=raw_path)

    latest = registry.get_latest_by_uri(source_id="price_history", source_uri=source_uri)
    if latest and latest[1] == checksum:
        return 0

    source_version_id = registry.register_version(
        SourceVersionInput(
            source_id="price_history",
            source_uri=source_uri,
            source_type="market_reference",
            checksum=checksum,
            connector_version=CONNECTOR_VERSION,
            raw_path=str(raw_path),
            effective_date=end.isoformat(),
            published_at=datetime.now(UTC).isoformat(),
        )
    )
    rows = _normalize_history(df=frame, ticker=ticker, source_version_id=source_version_id)
    return store.upsert_price_rows(rows)


def sync_price_for_universe(days_back: int, tickers: Iterable[str] | None = None) -> dict[str, int]:
    tickers = list(tickers or load_universe_tickers())
    end = datetime.now(UTC).date()
    start = end - timedelta(days=days_back)
    store = PostgresFactStore()
    registry = SourceRegistry(store=store)
    result: dict[str, int] = {}
    for ticker in tickers:
        inserted = sync_ticker_price(ticker=ticker, start=start, end=end, store=store, registry=registry)
        result[ticker] = inserted
        print(f"[price] {ticker}: upserted {inserted} rows")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync VN stock EOD price history into PostgreSQL.")
    parser.add_argument("--days-back", type=int, default=7, help="Number of calendar days to sync backward from today.")
    parser.add_argument("--tickers", type=str, default="", help="Comma-separated ticker override.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tickers = [x.strip().upper() for x in args.tickers.split(",") if x.strip()] or None
    sync_price_for_universe(days_back=args.days_back, tickers=tickers)


if __name__ == "__main__":
    main()

