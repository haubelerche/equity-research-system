"""Validate configured universe tickers against vnstock listing masters.

This is the non-manual alternative to filling market_prices.csv by hand. It
checks whether a ticker exists in provider security masters and whether the
provider company name resembles the configured universe company name.
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
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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


def _load_universe(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [
            {str(k): str(v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(handle)
            if str(row.get("ticker") or "").strip()
        ]


def _normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.lower())
    ascii_text = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    ascii_text = ascii_text.replace("đ", "d")
    ascii_text = re.sub(r"\b(cong ty|co phan|ctcp|tong cong ty|tap doan|corporation|jsc)\b", " ", ascii_text)
    ascii_text = re.sub(r"[^a-z0-9]+", " ", ascii_text)
    return re.sub(r"\s+", " ", ascii_text).strip()


def _name_score(left: str, right: str) -> float:
    left_norm = _normalize_name(left)
    right_norm = _normalize_name(right)
    if not left_norm or not right_norm:
        return 0.0
    return round(difflib.SequenceMatcher(None, left_norm, right_norm).ratio(), 4)


def _load_listing_master(sources: list[str]) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    errors: list[str] = []
    master: dict[str, list[dict[str, Any]]] = {}
    from vnstock.api.listing import Listing

    for source in sources:
        try:
            frame = Listing(source=source).all_symbols()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source}: {type(exc).__name__}: {exc}")
            continue
        for _, row in frame.iterrows():
            ticker = str(row.get("symbol") or row.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            name = str(row.get("organ_name") or row.get("name") or row.get("company_name") or "").strip()
            master.setdefault(ticker, []).append(
                {
                    "source": source,
                    "ticker": ticker,
                    "organ_name": name,
                    "raw": {str(k): (None if row.get(k) != row.get(k) else row.get(k)) for k in frame.columns},
                }
            )
    return master, errors


def _replacement_candidates(
    configured_name: str,
    master: dict[str, list[dict[str, Any]]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for ticker, matches in master.items():
        for match in matches:
            name = str(match.get("organ_name") or "")
            key = (ticker, name)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    "ticker": ticker,
                    "organ_name": name,
                    "source": match.get("source"),
                    "name_score": _name_score(configured_name, name),
                }
            )
    return sorted(candidates, key=lambda item: item["name_score"], reverse=True)[:limit]


def audit_listing_master(
    *,
    universe_path: Path,
    sources: list[str],
    name_match_threshold: float,
    candidate_limit: int,
) -> dict[str, Any]:
    universe = _load_universe(universe_path)
    master, errors = _load_listing_master(sources)
    records: list[dict[str, Any]] = []
    for row in universe:
        ticker = row["ticker"].upper()
        matches = master.get(ticker, [])
        scored = [
            {
                **match,
                "name_score": _name_score(row.get("company_name", ""), str(match.get("organ_name") or "")),
            }
            for match in matches
        ]
        best = max(scored, key=lambda item: item["name_score"], default=None)
        if not scored:
            status = "missing_from_listing_master"
        elif best and best["name_score"] < name_match_threshold:
            status = "identity_mismatch"
        else:
            status = "validated"
        replacement_candidates = (
            _replacement_candidates(
                row.get("company_name", ""),
                master,
                limit=candidate_limit,
            )
            if status != "validated"
            else []
        )
        records.append(
            {
                "ticker": ticker,
                "configured_company_name": row.get("company_name", ""),
                "exchange": row.get("exchange", ""),
                "segment": row.get("segment", ""),
                "status": status,
                "best_name_score": best["name_score"] if best else None,
                "best_listing_name": best["organ_name"] if best else None,
                "best_listing_source": best["source"] if best else None,
                "listing_matches": scored,
                "replacement_candidates": replacement_candidates,
            }
        )

    status_tickers: dict[str, list[str]] = {}
    for record in records:
        status_tickers.setdefault(record["status"], []).append(record["ticker"])
    summary = {
        "universe_count": len(records),
        "sources": sources,
        "name_match_threshold": name_match_threshold,
        "listing_master_ticker_count": len(master),
        "provider_errors": errors,
        "status_counts": {key: len(value) for key, value in sorted(status_tickers.items())},
        "status_tickers": {key: sorted(value) for key, value in sorted(status_tickers.items())},
    }
    return {"summary": summary, "records": records}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate universe tickers against vnstock provider listing masters.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--universe", default="config/dataset/universe/pharma_vn_universe.csv")
    parser.add_argument("--sources", default="vci,kbs", help="Comma-separated listing providers.")
    parser.add_argument("--name-match-threshold", type=float, default=0.42)
    parser.add_argument("--candidate-limit", type=int, default=5)
    parser.add_argument("--vnstock-home", default=".vnstock_runtime")
    parser.add_argument("--write-json", default="output/universe_listing_master_audit.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = parse_args(argv)
    vnstock_home = Path(args.vnstock_home)
    if not vnstock_home.is_absolute():
        vnstock_home = ROOT / vnstock_home
    _force_vnstock_home(vnstock_home)

    universe = Path(args.universe)
    if not universe.is_absolute():
        universe = ROOT / universe
    result = audit_listing_master(
        universe_path=universe,
        sources=[item.strip().lower() for item in args.sources.split(",") if item.strip()],
        name_match_threshold=float(args.name_match_threshold),
        candidate_limit=max(0, int(args.candidate_limit or 0)),
    )
    out = Path(args.write_json)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2, default=str))
    print(f"[listing-master-audit] wrote {out}")
    return 0 if not result["summary"]["provider_errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
