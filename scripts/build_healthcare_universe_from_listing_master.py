"""Build a machine-generated healthcare/pharma universe from listing master.

The output is a candidate artifact for replacing stale or invalid configured
tickers. It does not overwrite config/dataset/universe/pharma_vn_universe.csv.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
import difflib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HEALTHCARE_ICB_CODES = {
    "4000",  # Health Care
    "4500",  # Health Care
    "4530",  # Health Care Equipment & Services
    "4533",  # Health Care Providers
    "4535",  # Medical Equipment
    "4537",  # Medical Supplies
    "4570",  # Pharmaceuticals & Biotechnology
    "4577",  # Pharmaceuticals
    "5333",  # Drug Retailers
}


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
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _segment(name: str, icb_code: str, icb_name: str) -> str:
    normalized = _normalize(f"{name} {icb_name}")
    if icb_code == "4533" or "benh vien" in normalized or "cham soc y te" in normalized:
        return "healthcare_services"
    if icb_code in {"4535", "4537"} or "thiet bi y" in normalized or "vat tu y" in normalized:
        return "medical_equipment"
    if icb_code == "5333" or "xuat nhap khau y te" in normalized or "nha thuoc" in normalized:
        return "medical_distribution"
    return "pharma"


def _name_score(left: str, right: str) -> float:
    left_norm = _normalize(left)
    right_norm = _normalize(right)
    if not left_norm or not right_norm:
        return 0.0
    return difflib.SequenceMatcher(None, left_norm, right_norm).ratio()


def _load_current_universe(path: Path) -> dict[str, dict[str, str]]:
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


def build_healthcare_universe(
    *,
    current_universe_path: Path,
    source: str,
    only_priced: bool,
    current_name_match_threshold: float,
) -> dict[str, Any]:
    from vnstock.api.listing import Listing

    current = _load_current_universe(current_universe_path)
    industry_frame = Listing(source="vci").symbols_by_industries()
    price_frame = Listing(source=source).symbols_by_exchange("HOSE")
    price_by_ticker: dict[str, dict[str, Any]] = {}
    for _, row in price_frame.iterrows():
        ticker = str(row.get("symbol") or "").strip().upper()
        if ticker and ticker not in price_by_ticker:
            price_by_ticker[ticker] = {str(k): row.get(k) for k in price_frame.columns}

    eligible_rows: dict[str, dict[str, Any]] = {}
    for _, row in industry_frame.iterrows():
        ticker = str(row.get("symbol") or "").strip().upper()
        icb_code = str(row.get("icb_code") or "").strip()
        if not ticker or icb_code not in HEALTHCARE_ICB_CODES:
            continue
        existing = eligible_rows.get(ticker)
        level = int(row.get("icb_level") or 0)
        existing_level = int(existing.get("icb_level") or 0) if existing else -1
        if existing is None or level >= existing_level:
            eligible_rows[ticker] = {str(k): row.get(k) for k in industry_frame.columns}

    records: list[dict[str, Any]] = []
    for ticker, industry_row in eligible_rows.items():
        price_row = price_by_ticker.get(ticker, {})
        name = str(price_row.get("organ_name") or industry_row.get("organ_name") or "").strip()
        current_row = current.get(ticker, {})
        in_current = ticker in current
        name_score = _name_score(current_row.get("company_name", ""), name) if in_current else None
        reference_price = price_row.get("re")
        try:
            reference_price = float(reference_price) if reference_price is not None else None
        except (TypeError, ValueError):
            reference_price = None
        if only_priced and not (reference_price and reference_price > 0):
            continue
        current_validated = bool(in_current and name_score is not None and name_score >= current_name_match_threshold)
        if current_validated:
            included_reason = "icb_healthcare_and_current_validated"
        elif in_current:
            included_reason = "icb_healthcare_current_name_mismatch"
        else:
            included_reason = "icb_healthcare"
        icb_code = str(industry_row.get("icb_code") or "")
        icb_name = str(industry_row.get("icb_name") or "")
        records.append(
            {
                "ticker": ticker,
                "company_name": name,
                "exchange": str(price_row.get("exchange") or current_row.get("exchange") or "").strip().upper(),
                "segment": _segment(name, icb_code, icb_name),
                "is_mvp": str(current_row.get("is_mvp") or "false").lower(),
                "notes": included_reason,
                "reference_price_vnd": reference_price,
                "source": f"vnstock_vci_icb+vnstock_{source}_listing_master",
                "in_current_universe": ticker in current,
                "current_company_name": current_row.get("company_name", ""),
                "current_name_score": round(name_score, 4) if name_score is not None else None,
                "icb_code": icb_code,
                "icb_name": icb_name,
            }
        )
    records.sort(key=lambda item: (item["segment"], item["ticker"]))
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": source,
        "industry_source": "vci",
        "included_icb_codes": sorted(HEALTHCARE_ICB_CODES),
        "only_priced": only_priced,
        "current_name_match_threshold": current_name_match_threshold,
        "candidate_count": len(records),
        "current_overlap_count": sum(1 for row in records if row["in_current_universe"]),
        "new_candidate_tickers": [row["ticker"] for row in records if not row["in_current_universe"]],
        "missing_current_tickers": sorted(set(current) - {row["ticker"] for row in records}),
        "records": records,
    }


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "ticker",
        "company_name",
        "exchange",
        "segment",
        "is_mvp",
        "notes",
        "reference_price_vnd",
        "source",
        "in_current_universe",
        "current_company_name",
        "current_name_score",
        "icb_code",
        "icb_name",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for record in records:
            writer.writerow({column: record.get(column, "") for column in columns})


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate healthcare/pharma universe candidates from vnstock KBS listing master.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--current-universe", default="config/dataset/universe/pharma_vn_universe.csv")
    parser.add_argument("--source", default="kbs")
    parser.add_argument("--only-priced", action="store_true")
    parser.add_argument("--current-name-match-threshold", type=float, default=0.42)
    parser.add_argument("--vnstock-home", default=".vnstock_runtime")
    parser.add_argument("--write-json", default="output/healthcare_universe_listing_candidates.json")
    parser.add_argument("--write-csv", default="output/healthcare_universe_listing_candidates.csv")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = parse_args(argv)
    vnstock_home = Path(args.vnstock_home)
    if not vnstock_home.is_absolute():
        vnstock_home = ROOT / vnstock_home
    _force_vnstock_home(vnstock_home)

    current_universe = Path(args.current_universe)
    if not current_universe.is_absolute():
        current_universe = ROOT / current_universe
    result = build_healthcare_universe(
        current_universe_path=current_universe,
        source=str(args.source).lower(),
        only_priced=bool(args.only_priced),
        current_name_match_threshold=float(args.current_name_match_threshold),
    )
    out_json = Path(args.write_json)
    out_csv = Path(args.write_csv)
    if not out_json.is_absolute():
        out_json = ROOT / out_json
    if not out_csv.is_absolute():
        out_csv = ROOT / out_csv
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    _write_csv(out_csv, result["records"])
    print(json.dumps({k: v for k, v in result.items() if k != "records"}, ensure_ascii=False, indent=2, default=str))
    print(f"[listing-universe] wrote {out_json}")
    print(f"[listing-universe] wrote {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
