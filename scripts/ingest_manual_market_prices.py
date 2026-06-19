"""Load accepted manual market prices into fact.price_history.

The manual pack contract stores price in VND by default. fact.price_history is
kept compatible with vnstock quote history, where Vietnamese equity prices are
stored in thousand VND; values >= 1000 are therefore divided by 1000 on write.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database.fact_store import PostgresFactStore, PriceRow
from backend.universe_registration import ensure_ticker_registered_from_universe
from backend.runtime_store import RuntimeStore


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


def _parse_date(value: str) -> date:
    return datetime.fromisoformat(value.strip()).date()


def _parse_price_to_thousand_vnd(value: Any) -> float:
    price = float(str(value).strip().replace(",", ""))
    if price <= 0:
        raise ValueError("price must be positive")
    return price / 1000.0 if price >= 1000 else price


def _parse_optional_price_to_thousand_vnd(value: Any, fallback: float) -> float:
    if value is None or str(value).strip() == "":
        return fallback
    return _parse_price_to_thousand_vnd(value)


def _parse_optional_int(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return int(float(str(value).strip().replace(",", "")))


def _selected_tickers(raw: str | None) -> set[str] | None:
    if not raw:
        return None
    selected = {item.strip().upper() for item in raw.split(",") if item.strip()}
    return selected or None


def load_manual_market_prices(
    *,
    csv_path: Path,
    tickers: set[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    rows: list[PriceRow] = []
    rejected: list[dict[str, Any]] = []
    store = PostgresFactStore()
    runtime_store = RuntimeStore()

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"as_of_date", "ticker", "price", "status", "source"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{csv_path} missing columns: {sorted(missing)}")
        for line_no, row in enumerate(reader, start=2):
            ticker = (row.get("ticker") or "").strip().upper()
            status = (row.get("status") or "").strip().lower()
            source = (row.get("source") or "").strip()
            if tickers is not None and ticker not in tickers:
                continue
            if status != "accepted":
                continue
            if not ticker or not source:
                rejected.append({"line": line_no, "reason": "missing_ticker_or_source", "row": row})
                continue
            try:
                ensure_ticker_registered_from_universe(runtime_store, ticker)
                trade_date = _parse_date(row["as_of_date"])
                close = _parse_price_to_thousand_vnd(row["price"])
                open_price = _parse_optional_price_to_thousand_vnd(row.get("open"), close)
                high = _parse_optional_price_to_thousand_vnd(row.get("high"), close)
                low = _parse_optional_price_to_thousand_vnd(row.get("low"), close)
                volume = _parse_optional_int(row.get("volume"))
            except Exception as exc:  # noqa: BLE001
                rejected.append({"line": line_no, "reason": str(exc), "row": row})
                continue
            rows.append(
                PriceRow(
                    ticker=ticker,
                    trade_date=trade_date,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    adjusted_close=close,
                    volume=volume,
                    traded_value=None,
                    market_cap=None,
                    source_id=None,
                    ingested_at=datetime.now(UTC),
                )
            )

    inserted = 0 if dry_run else store.upsert_price_rows(rows)
    return {
        "csv_path": str(csv_path),
        "dry_run": dry_run,
        "accepted_rows": len(rows),
        "inserted_rows": inserted,
        "rejected": rejected,
        "tickers": sorted({row.ticker for row in rows}),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Insert accepted data/manual/market_prices.csv rows into fact.price_history.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--csv", default="data/manual/market_prices.csv")
    parser.add_argument("--tickers", default="", help="Optional comma-separated ticker filter.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write-json", default="output/manual_market_price_ingest.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = parse_args(argv)
    result = load_manual_market_prices(
        csv_path=(ROOT / args.csv).resolve() if not Path(args.csv).is_absolute() else Path(args.csv),
        tickers=_selected_tickers(args.tickers),
        dry_run=args.dry_run,
    )
    out = Path(args.write_json)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(__import__("json").dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(__import__("json").dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if not result["rejected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
