"""Build golden financial CSV fixtures from local raw BCTC cache.

No network path: reads ``data/raw/bctc/<ticker>/*_year.json`` and writes
``config/benchmarks/shared/golden_financials/<ticker>.csv`` plus provenance JSON for every
ticker that has the required local raw files. Universe tickers without raw cache
are written to the audit report rather than silently skipped.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.dataset.config_io import load_universe_rows  # noqa: E402
from backend.evaluation.benchmark_paths import GOLDEN_FINANCIALS_DIR
from scripts.connectors.vnstock_finance_connector import (  # noqa: E402
    _build_alias_map,
    _extract_facts_from_frame,
    _resolve_fact_collisions,
)
from scripts.ingest_local_bctc_snapshots import (  # noqa: E402
    STATEMENT_FILES,
    STATEMENT_TAXONOMY,
    _read_split_json,
)

FIELDNAMES = [
    "ticker",
    "fiscal_year",
    "period",
    "statement_type",
    "canonical_key",
    "raw_label",
    "value",
    "unit",
    "currency",
    "source_type",
    "source_uri",
    "source_title",
    "provider",
    "confidence",
    "validation_status",
]


def _statement_for_metric(metric: str) -> str:
    if metric.startswith("eps."):
        return "income_statement"
    if metric.endswith(".ending") or metric in {
        "total_assets.ending",
        "total_liabilities.ending",
        "equity.parent",
        "cash_and_equivalents.ending",
    }:
        return "balance_sheet"
    if metric in {
        "operating_cash_flow.total",
        "capex.total",
        "depreciation.total",
        "proceeds_from_borrowings.total",
        "repayment_of_borrowings.total",
        "dividends_paid.total",
    }:
        return "cash_flow"
    if metric.startswith(("pe.", "roe.", "roa.")):
        return "income_statement"
    return "income_statement"


def _format_value(value: float, unit: str) -> str:
    if unit == "shares":
        return str(int(round(value)))
    if unit == "vnd":
        return str(round(value, 4)).rstrip("0").rstrip(".")
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _build_rows_for_ticker(ticker: str, raw_root: Path, from_year: int, to_year: int) -> tuple[list[dict[str, str]], list[str]]:
    ticker_dir = raw_root / ticker
    missing_files = [name for name in STATEMENT_FILES.values() if not (ticker_dir / name).is_file()]
    if missing_files:
        return [], missing_files

    facts = []
    for statement, file_name in STATEMENT_FILES.items():
        path = ticker_dir / file_name
        frame = _read_split_json(path)
        facts.extend(
            _extract_facts_from_frame(
                ticker=ticker,
                frame=frame,
                source_id=f"local_raw_bctc:{ticker}:{statement}",
                parser_version="golden_raw_builder_v1",
                alias_map=_build_alias_map(statement=STATEMENT_TAXONOMY[statement]),
                run_id=f"golden_raw_{ticker}",
                provider="local_raw_cache",
                statement_type=statement,
                period_type="year",
            )
        )

    facts = [
        fact for fact in _resolve_fact_collisions(facts)
        if fact.fiscal_period == "FY" and from_year <= fact.fiscal_year <= to_year
    ]
    rows: list[dict[str, str]] = []
    for fact in sorted(facts, key=lambda item: (item.fiscal_year, item.line_item_code)):
        statement = _statement_for_metric(fact.line_item_code)
        source_file = STATEMENT_FILES.get(statement if statement != "derived" else "ratio", "income_statement_year.json")
        source_uri = f"local://data/raw/bctc/{ticker}/{source_file}"
        rows.append({
            "ticker": ticker,
            "fiscal_year": str(fact.fiscal_year),
            "period": f"{fact.fiscal_year}{fact.fiscal_period}",
            "statement_type": statement,
            "canonical_key": fact.line_item_code,
            "raw_label": fact.line_item_code,
            "value": _format_value(fact.value, fact.unit),
            "unit": fact.unit,
            "currency": fact.currency,
            "source_type": "financial_statement",
            "source_uri": source_uri,
            "source_title": f"Local raw BCTC cache {ticker} {fact.fiscal_year}FY",
            "provider": "local_raw_cache",
            "confidence": f"{min(fact.confidence, 0.92):.2f}",
            "validation_status": fact.validation_status,
        })
    existing_keys = {(row["period"], row["canonical_key"]) for row in rows}
    by_period_metric = {
        (row["period"], row["canonical_key"]): row
        for row in rows
        if row["validation_status"] == "accepted"
    }
    periods = sorted({row["period"] for row in rows})
    for period in periods:
        if (period, "shares_outstanding.ending") in existing_keys:
            continue
        net_income = by_period_metric.get((period, "net_income.parent"))
        eps = by_period_metric.get((period, "eps.basic"))
        if not net_income or not eps:
            continue
        try:
            net_income_vnd_bn = float(net_income["value"])
            eps_vnd = float(eps["value"])
        except ValueError:
            continue
        if eps_vnd == 0:
            continue
        shares = abs(net_income_vnd_bn * 1_000_000_000.0 / eps_vnd)
        fiscal_year = period[:4]
        rows.append({
            "ticker": ticker,
            "fiscal_year": fiscal_year,
            "period": period,
            "statement_type": "capital_structure",
            "canonical_key": "shares_outstanding.ending",
            "raw_label": "shares_outstanding_derived_from_net_income_and_eps",
            "value": str(int(round(shares))),
            "unit": "shares",
            "currency": "VND",
            "source_type": "financial_statement",
            "source_uri": f"local://data/raw/bctc/{ticker}/ratio_year.json",
            "source_title": f"Derived shares from local raw BCTC cache {ticker} {period}",
            "provider": "local_raw_cache",
            "confidence": "0.85",
            "validation_status": "accepted",
        })
    rows.sort(key=lambda item: (item["fiscal_year"], item["statement_type"], item["canonical_key"]))
    return rows, []


def _existing_source_tier(output_dir: Path, ticker: str) -> int | None:
    path = output_dir / f"{ticker}_golden_provenance.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return int(payload.get("source_tier"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def build_golden_financials(
    raw_root: Path,
    output_dir: Path,
    from_year: int,
    to_year: int,
    *,
    missing_only: bool = False,
    preserve_better_tier: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC).isoformat()
    built: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in load_universe_rows():
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        csv_path = output_dir / f"{ticker}.csv"
        if missing_only and csv_path.is_file():
            skipped.append({"ticker": ticker, "reason": "golden_csv_exists"})
            continue
        existing_tier = _existing_source_tier(output_dir, ticker)
        if preserve_better_tier and csv_path.is_file() and existing_tier is not None and existing_tier < 3:
            skipped.append({"ticker": ticker, "reason": f"existing_source_tier_{existing_tier}_is_better_than_local_raw"})
            continue
        rows, missing_files = _build_rows_for_ticker(ticker, raw_root, from_year, to_year)
        if missing_files:
            missing.append({"ticker": ticker, "missing_files": missing_files})
            continue
        if not rows:
            for suffix in (".csv", "_golden_provenance.json"):
                stale = output_dir / f"{ticker}{suffix}"
                if stale.exists():
                    stale.unlink()
            missing.append({"ticker": ticker, "missing_files": [], "reason": "no_mapped_facts_in_raw_cache"})
            continue
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
        metrics_verified = sorted({item["canonical_key"] for item in rows if item["validation_status"] == "accepted"})
        latest_year = max(int(item["fiscal_year"]) for item in rows)
        provenance = {
            "ticker": ticker,
            "verified_by": "build_golden_financials_from_raw",
            "verification_date": generated_at[:10],
            "source_tier": 3,
            "source_document_type": "financial_statement",
            "fiscal_year": latest_year,
            "fiscal_period": "FY",
            "publisher": row.get("company_name") or ticker,
            "published_at": generated_at,
            "source_documents_used": [f"data/raw/bctc/{ticker}/{name}" for name in STATEMENT_FILES.values()],
            "source_urls": [f"local://data/raw/bctc/{ticker}"],
            "notes": (
                "Generated deterministically from local raw BCTC cache for full-universe benchmarking. "
                "Confidence is capped below 1.0 to avoid perfect-score overfitting; official PDF sourcing can supersede these rows."
            ),
            "metrics_verified": metrics_verified,
            "checksum": "sha256:pending",
        }
        (output_dir / f"{ticker}_golden_provenance.json").write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        built.append({"ticker": ticker, "rows": len(rows), "metrics": len(metrics_verified)})
    return {
        "generated_at": generated_at,
        "universe_count": len(load_universe_rows()),
        "built_count": len(built),
        "missing_count": len(missing),
        "skipped_count": len(skipped),
        "built": built,
        "missing": missing,
        "skipped": skipped,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", default="data/raw/bctc")
    parser.add_argument("--output-dir", default=str(GOLDEN_FINANCIALS_DIR))
    parser.add_argument("--from-year", type=int, default=2022)
    parser.add_argument("--to-year", type=int, default=2025)
    parser.add_argument("--audit-json", default="output/golden_financials_build_audit.json")
    parser.add_argument("--missing-only", action="store_true", help="Only build tickers whose golden CSV is absent.")
    parser.add_argument(
        "--preserve-better-tier",
        action="store_true",
        help="Do not overwrite an existing golden CSV whose provenance source_tier is better than local raw Tier 3.",
    )
    args = parser.parse_args()

    raw_root = Path(args.raw_root)
    if not raw_root.is_absolute():
        raw_root = ROOT / raw_root
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    audit = Path(args.audit_json)
    if not audit.is_absolute():
        audit = ROOT / audit

    payload = build_golden_financials(
        raw_root=raw_root,
        output_dir=output_dir,
        from_year=args.from_year,
        to_year=args.to_year,
        missing_only=args.missing_only,
        preserve_better_tier=args.preserve_better_tier,
    )
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "universe_count": payload["universe_count"],
        "built_count": payload["built_count"],
        "missing_count": payload["missing_count"],
        "skipped_count": payload["skipped_count"],
        "missing": [item["ticker"] for item in payload["missing"]],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
