"""Sync KBS listing-master reference prices into fact.price_history.

This connector is an automated fallback for tickers where Quote.history is not
available but the ticker is present in KBS security master with a reference
price. It validates configured universe names by default to avoid ticker
identity collisions.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import json
import os
import re
import sys
import unicodedata
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database.fact_store import PostgresFactStore, PriceRow


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


def _force_vnstock_home(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(path)
    os.environ["USERPROFILE"] = str(path)
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFD", value.lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn").replace("đ", "d")
    text = re.sub(r"\b(cong ty|co phan|ctcp|tong cong ty|tap doan)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _name_score(left: str, right: str) -> float:
    left_norm = _normalize(left)
    right_norm = _normalize(right)
    if not left_norm or not right_norm:
        return 0.0
    return difflib.SequenceMatcher(None, left_norm, right_norm).ratio()


def _load_universe(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return {
            str(row.get("ticker") or "").strip().upper(): {
                str(k): str(v or "").strip() for k, v in row.items()
            }
            for row in csv.DictReader(handle)
            if str(row.get("ticker") or "").strip()
        }


def _tickers_from_file(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        records = payload.get("records", payload) if isinstance(payload, dict) else payload
        return {
            str(row.get("ticker") or row.get("symbol") or "").strip().upper()
            for row in records
            if isinstance(row, dict) and str(row.get("ticker") or row.get("symbol") or "").strip()
        }
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames:
            key = "ticker" if "ticker" in reader.fieldnames else "symbol"
            return {
                str(row.get(key) or "").strip().upper()
                for row in reader
                if str(row.get(key) or "").strip()
            }
    return set()


def _selected_tickers(
    raw: str | None,
    universe: dict[str, dict[str, str]],
    tickers_file: Path | None,
) -> set[str] | None:
    if tickers_file is not None:
        return _tickers_from_file(tickers_file)
    if raw:
        return {item.strip().upper() for item in raw.split(",") if item.strip()}
    return set(universe) if universe else None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def sync_kbs_reference_prices(
    *,
    tickers: set[str] | None,
    universe: dict[str, dict[str, str]],
    trade_date: date,
    name_match_threshold: float,
    validate_universe_name: bool,
    dry_run: bool,
) -> dict[str, Any]:
    from vnstock.api.listing import Listing

    frame = Listing(source="kbs").symbols_by_exchange("HOSE")
    rows: list[PriceRow] = []
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, row in frame.iterrows():
        ticker = str(row.get("symbol") or "").strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        if tickers is not None and ticker not in tickers:
            continue
        reference_price_vnd = _to_float(row.get("re"))
        listing_name = str(row.get("organ_name") or "").strip()
        configured = universe.get(ticker, {})
        score = _name_score(configured.get("company_name", ""), listing_name) if configured else None
        if not reference_price_vnd:
            results.append({"ticker": ticker, "status": "skipped_no_reference_price"})
            continue
        if validate_universe_name and configured and score is not None and score < name_match_threshold:
            results.append(
                {
                    "ticker": ticker,
                    "status": "skipped_identity_mismatch",
                    "configured_company_name": configured.get("company_name", ""),
                    "listing_name": listing_name,
                    "name_score": round(score, 4),
                }
            )
            continue
        close = reference_price_vnd / 1000.0
        rows.append(
            PriceRow(
                ticker=ticker,
                trade_date=trade_date,
                open=close,
                high=close,
                low=close,
                close=close,
                adjusted_close=close,
                volume=None,
                traded_value=None,
                market_cap=None,
                source_id=None,
                ingested_at=datetime.now(UTC),
            )
        )
        results.append(
            {
                "ticker": ticker,
                "status": "ready",
                "trade_date": trade_date.isoformat(),
                "reference_price_vnd": reference_price_vnd,
                "listing_name": listing_name,
                "exchange": row.get("exchange"),
                "name_score": round(score, 4) if score is not None else None,
            }
        )

    requested_missing = sorted((tickers or set()) - seen) if tickers else []
    inserted = 0 if dry_run else PostgresFactStore().upsert_price_rows(rows)
    return {
        "dry_run": dry_run,
        "trade_date": trade_date.isoformat(),
        "requested_tickers": sorted(tickers) if tickers else None,
        "requested_missing_from_kbs": requested_missing,
        "ready_rows": len(rows),
        "inserted_rows": inserted,
        "results": results,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Insert KBS listing-master reference prices into fact.price_history.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--tickers", default="", help="Comma-separated tickers. Default: configured universe.")
    parser.add_argument("--tickers-file", default="", help="CSV/JSON containing ticker or symbol column.")
    parser.add_argument("--universe", default="config/dataset/universe/pharma_vn_universe.csv")
    parser.add_argument("--trade-date", default="", help="Default: today UTC.")
    parser.add_argument("--name-match-threshold", type=float, default=0.42)
    parser.add_argument("--no-validate-universe-name", action="store_true")
    parser.add_argument("--vnstock-home", default=".vnstock_runtime")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write-json", default="output/kbs_reference_price_ingest.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = parse_args(argv)
    vnstock_home = Path(args.vnstock_home)
    if not vnstock_home.is_absolute():
        vnstock_home = ROOT / vnstock_home
    _force_vnstock_home(vnstock_home)
    universe_path = Path(args.universe)
    if not universe_path.is_absolute():
        universe_path = ROOT / universe_path
    universe = _load_universe(universe_path)
    tickers_file = Path(args.tickers_file) if args.tickers_file else None
    if tickers_file is not None and not tickers_file.is_absolute():
        tickers_file = ROOT / tickers_file
    trade_date = datetime.fromisoformat(args.trade_date).date() if args.trade_date else datetime.now(UTC).date()
    result = sync_kbs_reference_prices(
        tickers=_selected_tickers(args.tickers, universe, tickers_file),
        universe=universe,
        trade_date=trade_date,
        name_match_threshold=float(args.name_match_threshold),
        validate_universe_name=not bool(args.no_validate_universe_name),
        dry_run=bool(args.dry_run),
    )
    out = Path(args.write_json)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "results"}, ensure_ascii=False, indent=2, default=str))
    print(f"[kbs-reference-price] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
