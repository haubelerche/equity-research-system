from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
UNIVERSE_CSV = ROOT / "dataset" / "universe" / "pharma_vn_universe.csv"
EXPECTED_UNIVERSE_COUNT = 23
EXPECTED_MVP = {"DHG", "IMP", "DMC", "TRA", "DBD"}


def main() -> None:
    with UNIVERSE_CSV.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    tickers = {row["ticker"].strip().upper() for row in rows}
    mvp_tickers = {
        row["ticker"].strip().upper()
        for row in rows
        if row["is_mvp"].strip().lower() == "true"
    }

    assert len(rows) == EXPECTED_UNIVERSE_COUNT, (
        f"Expected {EXPECTED_UNIVERSE_COUNT} rows, got {len(rows)}"
    )
    assert len(tickers) == len(rows), "Universe contains duplicate tickers"
    assert mvp_tickers == EXPECTED_MVP, (
        f"MVP set mismatch. Expected {sorted(EXPECTED_MVP)}, got {sorted(mvp_tickers)}"
    )

    print("Universe validation passed")
    print(f"Total companies: {len(rows)}")
    print(f"MVP tickers: {', '.join(sorted(mvp_tickers))}")


if __name__ == "__main__":
    main()
