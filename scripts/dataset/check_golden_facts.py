from __future__ import annotations

import csv
from pathlib import Path
from collections import defaultdict

import yaml


ROOT = Path(__file__).resolve().parents[2]
SCOPE_FILE = ROOT / "dataset" / "mvp" / "mvp5_scope.yaml"
GOLDEN_SPEC = ROOT / "dataset" / "mvp" / "golden_facts_spec.yaml"
FACTS_FILE = ROOT / "dataset" / "mvp" / "financial_facts_bootstrap.csv"


def main() -> None:
    with SCOPE_FILE.open("r", encoding="utf-8") as f:
        scope = yaml.safe_load(f)
    with GOLDEN_SPEC.open("r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    if not FACTS_FILE.exists():
        raise FileNotFoundError(
            f"{FACTS_FILE} not found. Run scripts/dataset/bootstrap_mvp_facts.py first."
        )

    with FACTS_FILE.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    years_by_ticker: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        years_by_ticker[row["company_ticker"]].add(int(row["fiscal_year"]))

    tickers = set(years_by_ticker.keys())
    expected_tickers = set(scope["tickers"])
    if tickers != expected_tickers:
        raise ValueError(f"Ticker mismatch. Expected {expected_tickers}, got {tickers}")

    min_years = int(spec["required_coverage"]["min_years_per_ticker"])
    for ticker, years in years_by_ticker.items():
        if len(years) < min_years:
            raise ValueError(f"{ticker} has {len(years)} years, expected at least {min_years}")

    print("Golden fact coverage check passed")
    print(f"Tickers: {len(tickers)}")
    print(f"Rows: {len(rows)}")


if __name__ == "__main__":
    main()
