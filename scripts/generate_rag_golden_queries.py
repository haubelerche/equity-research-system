"""Generate RAG golden query YAML files for tickers missing them.

Usage:
    python scripts/generate_rag_golden_queries.py          # generates all missing
    python scripts/generate_rag_golden_queries.py --tickers PME BVP
    python scripts/generate_rag_golden_queries.py --force  # regenerate configured universe
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.dataset.config_io import load_universe_rows  # noqa: E402
from backend.evaluation.benchmark_paths import RAG_GOLDEN_QUERY_DIR  # noqa: E402

OUTPUT_DIR = RAG_GOLDEN_QUERY_DIR

# 8 canonical metrics × 3 fiscal years = 24 queries per ticker.
# Uses canonical key format (e.g. "revenue.net") because most tickers only have
# VNStock Tier-3 data whose chunks are keyed by canonical field name.
# expected_source_tiers: [3] reflects VNStock aggregator as the only available source.
TEMPLATE_QUERIES: list[tuple[str, str]] = [
    ("revenue_net", "revenue.net"),
    ("cogs", "cogs.total"),
    ("gross_profit", "gross_profit.total"),
    ("net_income", "net_income.parent"),
    ("total_assets", "total_assets.ending"),
    ("equity", "equity.parent"),
    ("total_liabilities", "total_liabilities.ending"),
    ("operating_cash_flow", "operating_cash_flow.total"),
]

FISCAL_YEARS = [2023, 2024, 2025]


def _generate_yaml(ticker: str) -> str:
    t = ticker.upper()
    tl = ticker.lower()
    lines = [
        f"version: rag_golden_{tl}_auto_v1",
        f"ticker: {t}",
        "schema: live_term_match_v2",
        "cohort_role: full_universe_auto",
        "queries:",
    ]
    for year in FISCAL_YEARS:
        for id_suffix, canonical_key in TEMPLATE_QUERIES:
            qid = f"{tl}_{id_suffix}_{year}"
            query = f"{t} {canonical_key} {year}"
            lines.append(
                f"  - {{id: {qid}, query: \"{query}\", "
                f"fiscal_year: {year}, "
                f"expected_terms: [\"{canonical_key}\"], "
                f"expected_source_tiers: [3], "
                f"material: true}}"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="+", help="Specific tickers to generate")
    parser.add_argument("--force", action="store_true", help="Regenerate even if file exists")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        tickers = [
            str(row.get("ticker") or "").strip().upper()
            for row in load_universe_rows()
            if row.get("ticker")
        ]

    generated = []
    skipped = []
    for ticker in tickers:
        out_path = OUTPUT_DIR / f"{ticker}.yaml"
        if out_path.exists() and not args.force:
            skipped.append(ticker)
            continue
        out_path.write_text(_generate_yaml(ticker), encoding="utf-8")
        generated.append(ticker)

    print(f"Generated {len(generated)} new, skipped {len(skipped)} (already existed)")
    if generated:
        print(f"  New: {generated}")
    if skipped:
        print(f"  Kept: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
