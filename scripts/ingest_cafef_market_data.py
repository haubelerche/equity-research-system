"""Fast CafeF market-price ingest for report rendering.

This script fetches CafeF once and writes a run-scoped market_data cache file.
The PDF renderer then reads the cache without making live network calls.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.dataset.config_io import load_universe_rows
from backend.documents.connectors.cafef_market_connector import CafeFQuote, fetch_latest_price
from backend.reporting.market_data_artifact import (
    PERIODS,
    MarketDataArtifact,
    MetricAvailability,
    TradingPerformance,
    TradingStatistics,
    benchmark_for_exchange,
    write_market_data_artifact,
)


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


def _exchange_for_ticker(ticker: str) -> str:
    ticker = ticker.strip().upper()
    for row in load_universe_rows():
        if str(row.get("ticker") or "").strip().upper() == ticker:
            return str(row.get("exchange") or "HOSE").strip().upper()
    return "HOSE"


def market_data_from_cafef_quote(
    quote: CafeFQuote,
    *,
    exchange: str,
    retrieved_at: str | None = None,
) -> MarketDataArtifact:
    if quote.last_price is None or quote.last_price <= 0:
        raise ValueError(f"CafeF returned no positive price for {quote.ticker}")
    as_of = quote.as_of_date or datetime.now(UTC).date().isoformat()
    retrieved = retrieved_at or datetime.now(UTC).isoformat()
    benchmark = benchmark_for_exchange(exchange)
    returns = {period: None for period in PERIODS}
    price_row = {
        "trade_date": as_of,
        "open": quote.open_price,
        "high": quote.high_price,
        "low": quote.low_price,
        "close": float(quote.last_price),
        "adjusted_close": float(quote.last_price),
        "volume": quote.volume,
        "traded_value": None,
        "market_cap": None,
    }
    return MarketDataArtifact(
        ticker=quote.ticker.upper(),
        exchange=exchange.upper(),
        primary_benchmark=benchmark,
        secondary_benchmark="VNINDEX",
        as_of_date=as_of,
        retrieved_at=retrieved,
        source=quote.source,
        price_history=[price_row],
        primary_benchmark_history=[],
        secondary_benchmark_history=[],
        trading_performance=TradingPerformance(
            periods=list(PERIODS),
            absolute_returns=returns.copy(),
            relative_returns=returns.copy(),
            benchmark_returns=returns.copy(),
            benchmark_symbol=benchmark,
        ),
        trading_statistics=TradingStatistics(
            last_close=float(quote.last_price),
            high_52w=quote.high_52w,
            low_52w=quote.low_52w,
            avg_volume_30d=quote.volume,
        ),
        availability={
            "price_history": MetricAvailability(True, quote.source, as_of, ""),
            "primary_benchmark": MetricAvailability(False, quote.source, as_of, f"Không có dữ liệu {benchmark} từ CafeF quick ingest"),
            "secondary_benchmark": MetricAvailability(False, quote.source, as_of, "Không có dữ liệu VNINDEX từ CafeF quick ingest"),
        },
        warnings=["CafeF quick ingest supplies latest close only; trading-performance history is unavailable."],
    )


def ingest_cafef_market_data(
    *,
    ticker: str,
    run_id: str,
    base_dir: Path | str | None = None,
    fetcher: Callable[[str], CafeFQuote] = fetch_latest_price,
) -> dict:
    ticker = ticker.strip().upper()
    run_id = run_id.strip()
    if not run_id:
        raise ValueError("run_id is required for run-scoped market_data cache")
    exchange = _exchange_for_ticker(ticker)
    quote = fetcher(ticker)
    artifact = market_data_from_cafef_quote(quote, exchange=exchange)
    path = write_market_data_artifact(artifact, run_id=run_id, base_dir=base_dir)
    return {
        "ticker": ticker,
        "run_id": run_id,
        "exchange": exchange,
        "as_of_date": artifact.as_of_date,
        "last_close": artifact.trading_statistics.last_close,
        "source": artifact.source,
        "path": str(path),
    }


def _resolve_run_id(ticker: str, run_id: str, latest_report_run: bool) -> str:
    if run_id.strip():
        return run_id.strip()
    if not latest_report_run:
        raise ValueError("Provide --run-id or --latest-report-run")
    from scripts.generate_fast_report import _latest_report_run_ids

    run_ids = _latest_report_run_ids(ticker)
    if not run_ids:
        raise ValueError(f"No prior report run found for {ticker}")
    return str(run_ids[0])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch CafeF latest close and write artifacts/market_data/<run_id>/market_data.json.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol, e.g. DPP")
    parser.add_argument("--run-id", default="", help="Run id whose report will be rendered")
    parser.add_argument(
        "--latest-report-run",
        action="store_true",
        help="Resolve the newest renderable run id for the ticker.",
    )
    parser.add_argument("--base-dir", default=str(ROOT / "artifacts" / "market_data"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = parse_args(argv)
    run_id = _resolve_run_id(args.ticker.strip().upper(), args.run_id, bool(args.latest_report_run))
    result = ingest_cafef_market_data(
        ticker=args.ticker,
        run_id=run_id,
        base_dir=Path(args.base_dir),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
