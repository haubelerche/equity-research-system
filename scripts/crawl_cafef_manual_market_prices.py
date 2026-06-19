"""Fill data/manual/market_prices.csv from CafeF price history.

This is the controlled batch path for current-price overrides used by valuation
recompute. Existing accepted manual rows are preserved by default.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.dataset.config_io import load_universe_tickers
from backend.documents.connectors.cafef_market_connector import CafeFQuote, fetch_latest_price
from backend.valuation.market_price_resolver import MarketPriceResolution, resolve_market_price

FIELDNAMES = [
    "as_of_date",
    "ticker",
    "price",
    "status",
    "source",
    "open",
    "high",
    "low",
    "volume",
    "high_52w",
    "low_52w",
]


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


def _parse_tickers(raw: str, *, all_tickers: bool) -> list[str]:
    if all_tickers:
        return load_universe_tickers()
    tickers = [item.strip().upper() for item in raw.split(",") if item.strip()]
    if not tickers:
        raise ValueError("Provide --tickers A,B,C or --all.")
    return tickers


def _read_existing(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, str]] = []
        for row in reader:
            rows.append({field: str(row.get(field) or "") for field in FIELDNAMES})
        return rows


def _fmt_number(value: float | None) -> str:
    if value is None:
        return ""
    return str(int(round(value)))


def _row_from_quote(quote: CafeFQuote) -> dict[str, str] | None:
    if quote.last_price is None or quote.last_price <= 0 or not quote.as_of_date:
        return None
    return {
        "as_of_date": quote.as_of_date,
        "ticker": quote.ticker.upper(),
        "price": _fmt_number(quote.last_price),
        "status": "accepted",
        "source": "cafef_price_history",
        "open": _fmt_number(quote.open_price or quote.last_price),
        "high": _fmt_number(quote.high_price or quote.last_price),
        "low": _fmt_number(quote.low_price or quote.last_price),
        "volume": _fmt_number(quote.volume),
        "high_52w": _fmt_number(quote.high_52w),
        "low_52w": _fmt_number(quote.low_52w),
    }


def _row_from_resolution(resolution: MarketPriceResolution) -> dict[str, str] | None:
    if resolution.current_price is None:
        return None
    return {
        "as_of_date": resolution.price_as_of,
        "ticker": resolution.ticker.upper(),
        "price": _fmt_number(resolution.current_price),
        "status": "accepted",
        "source": resolution.source or "market_price_resolver",
        "open": _fmt_number(resolution.open or resolution.current_price),
        "high": _fmt_number(resolution.high or resolution.current_price),
        "low": _fmt_number(resolution.low or resolution.current_price),
        "volume": _fmt_number(resolution.volume),
        "high_52w": _fmt_number(resolution.high_52w),
        "low_52w": _fmt_number(resolution.low_52w),
    }


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDNAMES})


def crawl_cafef_manual_market_prices(
    *,
    csv_path: Path,
    tickers: list[str],
    fetcher: Callable[[str], CafeFQuote] = fetch_latest_price,
    overwrite: bool = False,
    fallback_local: bool = True,
    sleep_seconds: float = 0.2,
) -> dict[str, object]:
    existing = _read_existing(csv_path)
    by_ticker = {str(row.get("ticker") or "").strip().upper(): row for row in existing if row.get("ticker")}
    fetched: list[str] = []
    failed: list[str] = []
    skipped: list[str] = []

    for ticker in [item.strip().upper() for item in tickers if item.strip()]:
        if ticker in by_ticker and not overwrite:
            skipped.append(ticker)
            continue
        quote = fetcher(ticker)
        row = _row_from_quote(quote)
        if row is not None:
            by_ticker[ticker] = row
            fetched.append(ticker)
        elif fallback_local:
            resolution = resolve_market_price(
                ticker,
                allow_live=False,
                manual_csv_path=csv_path,
            )
            fallback_row = _row_from_resolution(resolution)
            if fallback_row is None:
                failed.append(ticker)
            else:
                by_ticker[ticker] = fallback_row
                fetched.append(ticker)
        else:
            failed.append(ticker)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    universe_order = {ticker: idx for idx, ticker in enumerate(load_universe_tickers())}
    ordered = sorted(
        by_ticker.values(),
        key=lambda row: (universe_order.get(str(row.get("ticker") or "").upper(), 9999), str(row.get("ticker") or "")),
    )
    _write_rows(csv_path, ordered)
    return {
        "csv_path": str(csv_path),
        "requested": len(tickers),
        "fetched": fetched,
        "skipped_existing": skipped,
        "failed": failed,
        "rows_written": len(ordered),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch CafeF latest market prices and write data/manual/market_prices.csv.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--tickers", default="", help="Comma-separated ticker filter.")
    parser.add_argument("--all", action="store_true", help="Use every ticker in configured universe.")
    parser.add_argument("--csv", default="data/manual/market_prices.csv")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing accepted manual rows.")
    parser.add_argument(
        "--no-local-fallback",
        action="store_true",
        help="Do not use fact.price_history/raw-cache fallback for CafeF-empty tickers.",
    )
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = parse_args(argv)
    tickers = _parse_tickers(args.tickers, all_tickers=bool(args.all))
    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = ROOT / csv_path
    result = crawl_cafef_manual_market_prices(
        csv_path=csv_path,
        tickers=tickers,
        overwrite=bool(args.overwrite),
        fallback_local=not bool(args.no_local_fallback),
        sleep_seconds=max(float(args.sleep_seconds), 0.0),
    )
    print(
        f"[cafef-market-prices] rows={result['rows_written']} "
        f"fetched={len(result['fetched'])} skipped={len(result['skipped_existing'])} "
        f"failed={len(result['failed'])} csv={result['csv_path']}"
    )
    if result["failed"]:
        print("[cafef-market-prices] failed=" + ",".join(result["failed"]))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
