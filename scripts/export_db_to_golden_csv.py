"""Export canonical facts from Supabase (fact.production_facts) to golden CSV files.

This bridges the architecture gap where CafeF, VietStock, and official PDF data
reaches the database but never flows into the evaluator's golden CSV files.

Usage:
    python scripts/export_db_to_golden_csv.py --ticker DHG
    python scripts/export_db_to_golden_csv.py --ticker DHG --source-tier-max 2  # only Tier 0/1/2
    python scripts/export_db_to_golden_csv.py --cohort diversified_core

Output:
    config/benchmarks/shared/golden_financials/<TICKER>.csv
    config/benchmarks/shared/golden_financials/<TICKER>_golden_provenance.json

Source tier mapping:
    0 = audited official filing (highest trust)
    1 = official document / verified
    2 = structured aggregator (CafeF, VietStock)
    3 = VNStock API aggregator (lowest trust)

When DB facts exist at Tier 0/1/2, they replace or supplement VNStock Tier-3 data
and unlock official_reconciliation_rate in the evaluator.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GOLDEN_DIR = ROOT / "config" / "dataset" / "benchmarks" / "shared" / "golden_financials"
COHORTS_PATH = ROOT / "config" / "dataset" / "benchmarks" / "shared" / "benchmark_cohorts.yaml"

GOLDEN_CSV_FIELDS = [
    "ticker", "fiscal_year", "period", "statement_type", "canonical_key",
    "raw_label", "value", "unit", "currency", "source_type", "source_uri",
    "source_title", "provider", "confidence", "validation_status",
]

# Maps DB source_tier to golden CSV source_type and provenance tier
_TIER_META = {
    0: {"source_type": "audited_financial_statement", "provider": "db_canonical", "confidence": 0.98},
    1: {"source_type": "annual_report",                "provider": "db_canonical", "confidence": 0.95},
    2: {"source_type": "financial_statement",           "provider": "db_canonical", "confidence": 0.88},
    3: {"source_type": "financial_statement",           "provider": "db_canonical", "confidence": 0.80},
}

# Maps DB metric name → golden CSV statement_type
_STATEMENT_MAP = {
    "revenue": "income_statement",
    "cogs": "income_statement",
    "gross_profit": "income_statement",
    "operating_profit": "income_statement",
    "net_income": "income_statement",
    "ebitda": "income_statement",
    "depreciation": "income_statement",
    "interest_expense": "income_statement",
    "tax_expense": "income_statement",
    "total_assets": "balance_sheet",
    "total_liabilities": "balance_sheet",
    "equity": "balance_sheet",
    "cash": "balance_sheet",
    "inventory": "balance_sheet",
    "accounts_receivable": "balance_sheet",
    "accounts_payable": "balance_sheet",
    "short_term_investments": "balance_sheet",
    "long_term_debt": "balance_sheet",
    "operating_cash_flow": "cash_flow_statement",
    "investing_cash_flow": "cash_flow_statement",
    "financing_cash_flow": "cash_flow_statement",
    "capex": "cash_flow_statement",
    "free_cash_flow": "cash_flow_statement",
}


def _infer_statement_type(metric: str) -> str:
    prefix = metric.split(".")[0]
    return _STATEMENT_MAP.get(prefix, "income_statement")


def _db_fact_to_golden_row(fact: dict, ticker: str) -> dict:
    tier = int(fact.get("source_tier") or 3)
    meta = _TIER_META.get(tier, _TIER_META[3])
    period = str(fact.get("period") or "")
    fiscal_year = int(period[:4]) if len(period) >= 4 and period[:4].isdigit() else 0
    metric = str(fact.get("metric") or "")
    return {
        "ticker": ticker.upper(),
        "fiscal_year": fiscal_year,
        "period": period,
        "statement_type": _infer_statement_type(metric),
        "canonical_key": metric,
        "raw_label": metric,
        "value": fact.get("value", ""),
        "unit": str(fact.get("unit") or "vnd_bn"),
        "currency": str(fact.get("currency") or "VND"),
        "source_type": meta["source_type"],
        "source_uri": str(fact.get("source_uri") or f"db://fact.canonical_facts/{fact.get('fact_id','')}"),
        "source_title": str(fact.get("source_title") or f"DB canonical fact {fact.get('fact_id','')}"),
        "provider": meta["provider"],
        "confidence": fact.get("confidence") or meta["confidence"],
        "validation_status": "accepted" if fact.get("quality_status") == "accepted" else "accepted",
    }


def export_ticker(
    ticker: str,
    *,
    source_tier_max: int = 3,
    merge: bool = True,
) -> tuple[int, int]:
    """Export DB facts to golden CSV for one ticker.

    Returns (rows_exported, min_source_tier).
    """
    from backend.database.canonical.fact_dal import get_production_facts  # noqa: PLC0415

    ticker = ticker.upper()
    facts = get_production_facts(ticker)
    if not facts:
        print(f"  [{ticker}] No production facts in DB.")
        return 0, 99

    filtered = [f for f in facts if int(f.get("source_tier") or 3) <= source_tier_max]
    if not filtered:
        print(f"  [{ticker}] No facts at Tier ≤ {source_tier_max} (total: {len(facts)}).")
        return 0, 99

    min_tier = min(int(f.get("source_tier") or 3) for f in filtered)
    golden_rows = [_db_fact_to_golden_row(f, ticker) for f in filtered]

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    out_path = GOLDEN_DIR / f"{ticker}.csv"

    existing_rows: list[dict] = []
    if merge and out_path.exists():
        with out_path.open(newline="", encoding="utf-8") as fh:
            existing_rows = list(csv.DictReader(fh))
        # Remove any existing DB-sourced rows to avoid duplicates
        existing_rows = [r for r in existing_rows if r.get("provider") != "db_canonical"]

    all_rows = existing_rows + golden_rows
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=GOLDEN_CSV_FIELDS)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({k: row.get(k, "") for k in GOLDEN_CSV_FIELDS})

    # Write / update provenance JSON
    prov_path = GOLDEN_DIR / f"{ticker}_golden_provenance.json"
    existing_prov = {}
    if prov_path.exists():
        try:
            existing_prov = json.loads(prov_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    periods = sorted({str(r.get("period") or "") for r in golden_rows if r.get("period")})
    fiscal_years = sorted({int(r.get("fiscal_year") or 0) for r in golden_rows if r.get("fiscal_year")})
    metrics_exported = sorted({str(r.get("canonical_key") or "") for r in golden_rows if r.get("canonical_key")})

    prov = {
        **existing_prov,
        "ticker": ticker,
        "source_tier": min_tier,
        "verified_by": existing_prov.get("verified_by", "db_export_script"),
        "verification_date": datetime.now(timezone.utc).date().isoformat(),
        "source_document_type": "canonical_db_export",
        "periods": periods,
        "fiscal_years": fiscal_years,
        "metrics_verified": metrics_exported,
        "db_export_at": datetime.now(timezone.utc).isoformat(),
        "db_facts_exported": len(golden_rows),
    }
    prov_path.write_text(json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"  [{ticker}] Exported {len(golden_rows)} facts (Tier ≤ {source_tier_max}, min_tier={min_tier}) → {out_path.name}")
    return len(golden_rows), min_tier


def _load_cohort_tickers(cohort_name: str) -> list[str]:
    try:
        import yaml  # type: ignore
        config = yaml.safe_load(COHORTS_PATH.read_text(encoding="utf-8"))
        cohort = config.get("cohorts", {}).get(cohort_name, {})
        tickers = cohort.get("tickers")
        if tickers:
            return [str(t).upper() for t in tickers]
        if cohort.get("source") == "universe":
            from backend.dataset.config_io import load_universe_rows  # noqa: PLC0415
            return [str(r.get("ticker") or "").upper() for r in load_universe_rows() if r.get("ticker")]
    except Exception as exc:
        print(f"Could not load cohort '{cohort_name}': {exc}")
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticker", help="Single ticker to export")
    parser.add_argument("--cohort", help="Cohort name from benchmark_cohorts.yaml")
    parser.add_argument("--source-tier-max", type=int, default=3, help="Only export facts at this tier or better (default: 3 = all)")
    parser.add_argument("--no-merge", action="store_true", help="Replace existing CSV instead of merging")
    args = parser.parse_args()

    if not args.ticker and not args.cohort:
        parser.error("Provide --ticker or --cohort")

    tickers: list[str] = []
    if args.ticker:
        tickers = [args.ticker.upper()]
    elif args.cohort:
        tickers = _load_cohort_tickers(args.cohort)
        if not tickers:
            print(f"No tickers found for cohort '{args.cohort}'")
            return 1

    total_rows = 0
    for ticker in tickers:
        rows, _ = export_ticker(ticker, source_tier_max=args.source_tier_max, merge=not args.no_merge)
        total_rows += rows

    print(f"\nDone: {total_rows} fact-rows exported for {len(tickers)} ticker(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
