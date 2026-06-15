"""Backfill fact.price_history from already-crawled quote history JSON files.

This is the non-manual remediation path for tickers whose raw market cache
exists under data/raw/market but whose database price rows are missing.
It never fabricates prices and never reads data/manual/market_prices.csv.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database.fact_store import PostgresFactStore, PriceRow
from backend.dataset.config_io import load_universe_tickers


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _parse_tickers(raw: str | None, *, all_tickers: bool) -> list[str]:
    if all_tickers:
        return [ticker.upper() for ticker in load_universe_tickers()]
    if not raw:
        raise SystemExit("Provide --tickers A,B,C or --all.")
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _parse_trade_date(row: dict[str, Any]) -> datetime.date:
    raw = row.get("date") or row.get("time") or row.get("datetime") or row.get("timestamp")
    if raw is None:
        raise ValueError("quote row missing date/time")
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()


def _quote_files_for_ticker(raw_root: Path, ticker: str) -> list[Path]:
    pattern = f"{ticker.upper()}_quote_history.json"
    return sorted(raw_root.glob(f"**/{pattern}"))


def _load_quote_rows(path: Path, ticker: str) -> list[PriceRow]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            records = payload["data"]
        elif isinstance(payload.get("records"), list):
            records = payload["records"]
        else:
            records = []
    elif isinstance(payload, list):
        records = payload
    else:
        records = []

    rows: list[PriceRow] = []
    now = datetime.now(UTC)
    for record in records:
        if not isinstance(record, dict):
            continue
        close = _to_float(record.get("close"))
        trade_date = _parse_trade_date(record)
        rows.append(
            PriceRow(
                ticker=ticker,
                trade_date=trade_date,
                open=_to_float(record.get("open")),
                high=_to_float(record.get("high")),
                low=_to_float(record.get("low")),
                close=close,
                adjusted_close=_to_float(record.get("adjusted_close") or record.get("adj_close")) or close,
                volume=_to_int(record.get("volume")),
                traded_value=_to_float(record.get("value") or record.get("traded_value")),
                market_cap=_to_float(record.get("market_cap")),
                source_id=None,
                ingested_at=now,
            )
        )
    return rows


def ingest_cached_market_prices(
    *,
    tickers: Iterable[str],
    raw_root: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    selected = [ticker.upper() for ticker in tickers]
    store = PostgresFactStore()
    results: list[dict[str, Any]] = []
    all_rows: list[PriceRow] = []

    for ticker in selected:
        files = _quote_files_for_ticker(raw_root, ticker)
        ticker_rows: list[PriceRow] = []
        errors: list[str] = []
        for path in files:
            try:
                ticker_rows.extend(_load_quote_rows(path, ticker))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{path}: {type(exc).__name__}: {exc}")
        deduped = {(row.ticker, row.trade_date): row for row in ticker_rows}
        rows = list(deduped.values())
        all_rows.extend(rows)
        results.append(
            {
                "ticker": ticker,
                "raw_files": [str(path) for path in files],
                "cached_rows": len(rows),
                "first_date": min((row.trade_date for row in rows), default=None),
                "last_date": max((row.trade_date for row in rows), default=None),
                "errors": errors,
                "status": "ready_from_cache" if rows else "no_cached_quote_history",
            }
        )

    inserted = 0 if dry_run else store.upsert_price_rows(all_rows)
    return {
        "raw_root": str(raw_root),
        "dry_run": dry_run,
        "tickers_requested": len(selected),
        "tickers_with_cache": sum(1 for item in results if item["cached_rows"] > 0),
        "cached_rows": len(all_rows),
        "inserted_rows": inserted,
        "results": results,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Insert cached data/raw/market/*/*_quote_history.json rows into fact.price_history.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--tickers", default="", help="Comma-separated ticker filter.")
    parser.add_argument("--all", action="store_true", help="Use every ticker in the configured universe.")
    parser.add_argument("--raw-root", default="data/raw/market")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write-json", default="output/cached_market_price_ingest.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = parse_args(argv)
    tickers = _parse_tickers(args.tickers, all_tickers=bool(args.all))
    raw_root = Path(args.raw_root)
    if not raw_root.is_absolute():
        raw_root = ROOT / raw_root
    result = ingest_cached_market_prices(
        tickers=tickers,
        raw_root=raw_root,
        dry_run=bool(args.dry_run),
    )
    out = Path(args.write_json)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "results"}, ensure_ascii=False, indent=2, default=str))
    print(f"[cached-price] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
