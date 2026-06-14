from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Iterable

# Ensure pip-installed vnstock is found before the local vnstock/ namespace folder.
if "" in sys.path:
    sys.path = [p for p in sys.path if p != ""] + [""]

import pandas as pd
from vnstock.api.quote import Quote

from backend.dataset.config_io import ROOT, load_universe_tickers
from backend.database.fact_store import PostgresFactStore, PriceRow
from backend.database.source_registry import SourceInput, SourceRegistry


CONNECTOR_VERSION = "vn_price_v1"


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
                trade_date=dt,
                open=_to_float(row.get("open")),
                high=_to_float(row.get("high")),
                low=_to_float(row.get("low")),
                close=_to_float(row.get("close")),
                adjusted_close=_to_float(row.get("adjusted_close") or row.get("adj_close")),
                volume=_to_int(row.get("volume")),
                traded_value=_to_float(row.get("value")),
                market_cap=_to_float(row.get("market_cap")),
                source_id=source_version_id,
                ingested_at=now,
            )
        )
    return rows


def _fetch_history(ticker: str, start: date, end: date, source: str) -> pd.DataFrame:
    client = Quote(source=source, symbol=ticker)
    return client.history(start=start.isoformat(), end=end.isoformat(), interval="1D")


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
    raw_path = ROOT / "data" / "raw" / "market" / end.isoformat() / f"{ticker}_quote_history.json"
    checksum = registry.save_raw_snapshot(payload=payload, out_path=raw_path)

    latest = registry.get_latest_by_uri("price_history", source_uri)
    if latest and latest[1] == checksum:
        return 0

    source_id = registry.register_source(
        SourceInput(
            logical_id="price_history",
            ticker=ticker,
            source_uri=source_uri,
            source_type="vnstock_price",
            source_tier=3,
            source_title=f"Dữ liệu giá {ticker} — vnstock ({provider_used})",
            checksum=checksum,
            connector_version=CONNECTOR_VERSION,
            raw_path=str(raw_path),
            published_at=datetime.now(UTC).isoformat(),
            metadata_json={"start": str(start), "end": str(end), "provider": provider_used},
        )
    )
    registry.register_raw_payload(
        source_id=source_id,
        content_type="application/json",
        checksum=checksum,
        storage_path=str(raw_path),
        connector_name="vnstock_price_connector",
        connector_version=CONNECTOR_VERSION,
        request_uri=source_uri,
        request_params={"ticker": ticker, "start": str(start), "end": str(end)},
    )
    rows = _normalize_history(df=frame, ticker=ticker, source_version_id=source_id)
    return store.upsert_price_rows(rows)


def sync_price_for_universe(days_back: int, tickers: Iterable[str] | None = None) -> dict[str, int]:
    tickers = list(tickers or load_universe_tickers())
    end = datetime.now(UTC).date()
    start = end - timedelta(days=days_back)
    store = PostgresFactStore()
    registry = SourceRegistry(store=store)
    result: dict[str, int] = {}
    for ticker in tickers:
        try:
            inserted = sync_ticker_price(ticker=ticker, start=start, end=end, store=store, registry=registry)
        except Exception as exc:  # noqa: BLE001 - one illiquid/unavailable ticker must not stop the universe sync
            result[ticker] = -1
            print(f"[price] {ticker}: failed: {exc}")
            continue
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

