"""Verify DHG facts against official documents and promote verified observations.

Dry-run is the default. Pass --apply only after reviewing the verification list.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.dataops.official_fact_verifier import load_metric_patterns, verify_fact_in_chunk
from backend.database.canonical.connection import get_conn
from backend.database.canonical.fact_dal import get_production_facts
from backend.database.canonical.fact_promotion import promote_accepted_facts
from backend.database.canonical.observation_dal import insert_observations
from backend.period_scope import DEFAULT_FROM_YEAR, DEFAULT_TO_YEAR


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    import os

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _official_chunks(ticker: str, from_year: int, to_year: int) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT dc.source_doc_id, dc.chunk_index, dc.chunk_text,
                       sd.source_tier, sd.fiscal_year, sd.source_uri
                FROM ingest.document_chunks dc
                JOIN ingest.source_documents sd ON sd.source_doc_id = dc.source_doc_id
                WHERE dc.ticker = %s
                  AND sd.source_tier <= 1
                  AND sd.fiscal_year BETWEEN %s AND %s
                ORDER BY sd.fiscal_year, dc.chunk_index
                """,
                (ticker, from_year, to_year + 1),
            )
            columns = [column.name for column in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]


def verify(ticker: str, from_year: int, to_year: int) -> tuple[list[dict], list[dict]]:
    facts = get_production_facts(ticker, from_year, to_year)
    chunks = _official_chunks(ticker, from_year, to_year)
    patterns = load_metric_patterns(ROOT / "config" / "financial_metric_dictionary.yaml")
    verified: list[dict] = []
    missing: list[dict] = []

    for fact in facts:
        year = int(fact["period"][:4])
        match = None
        for chunk in chunks:
            # A following-year audited report may verify a prior-year comparative column.
            if chunk["fiscal_year"] not in {year, year + 1}:
                continue
            match = verify_fact_in_chunk(fact, chunk, patterns)
            if match:
                break
        if match:
            verified.append(
                {
                    "ticker": ticker,
                    "period": fact["period"],
                    "metric": fact["metric"],
                    "value": fact["value"],
                    "unit": fact["unit"],
                    "currency": fact.get("currency") or "VND",
                    "source_doc_id": match.source_doc_id,
                    "source_tier": match.source_tier,
                    "extraction_method": "exact_official_document_match_v1",
                    "confidence": 1.0,
                    "page_number": match.page_number,
                    "table_name": "official_financial_statement",
                    "extracted_text": match.extracted_text,
                }
            )
        else:
            missing.append(fact)
    return verified, missing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="DHG")
    parser.add_argument("--from-year", type=int, default=DEFAULT_FROM_YEAR)
    parser.add_argument("--to-year", type=int, default=DEFAULT_TO_YEAR)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    _load_dotenv()

    verified, missing = verify(args.ticker.upper(), args.from_year, args.to_year)
    by_period: dict[str, int] = {}
    for row in verified:
        by_period[row["period"]] = by_period.get(row["period"], 0) + 1
        print(
            f"VERIFIED {row['period']} {row['metric']} tier={row['source_tier']} "
            f"source_doc_id={row['source_doc_id']} page={row['page_number']}"
        )
    print(f"verified={len(verified)} missing={len(missing)} by_period={by_period}")

    if not args.apply:
        print("dry_run=true; no database changes")
        return 0
    if any(by_period.get(f"{year}FY", 0) == 0 for year in range(args.from_year, args.to_year + 1)):
        print("REFUSED: every required period must have at least one exact official verification")
        return 2

    insert_observations(verified)
    result = promote_accepted_facts(
        ticker=args.ticker.upper(),
        from_year=args.from_year,
        to_year=args.to_year,
        canonical_version="prod_official_verified_v1",
    )
    print(
        f"applied=true promoted={result.promoted} "
        f"low_confidence={result.skipped_low_confidence} errors={result.errors}"
    )
    return 0 if not result.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())

