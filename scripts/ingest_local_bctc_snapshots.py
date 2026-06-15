"""Promote local data/raw/bctc JSON files into canonical facts and snapshots.

This is a no-network remediation path for tickers whose vnstock raw snapshots
already exist on disk but do not yet have an active research snapshot.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database.canonical.fact_dal import get_production_facts
from backend.database.canonical.fact_promotion import promote_accepted_facts
from backend.database.canonical.observation_dal import insert_observations
from backend.database.canonical.snapshot_dal import create_snapshot
from backend.database.fact_store import FinancialFact
from backend.database.source_registry import SourceInput, SourceRegistry
from backend.period_scope import DEFAULT_FROM_YEAR, DEFAULT_TO_YEAR
from backend.universe_registration import ensure_ticker_registered_from_universe
from backend.runtime_store import RuntimeStore
from scripts.connectors.vnstock_finance_connector import (
    _build_alias_map,
    _extract_facts_from_frame,
    _fact_to_observation,
    _resolve_fact_collisions,
)


STATEMENT_FILES = {
    "income_statement": "income_statement_year.json",
    "balance_sheet": "balance_sheet_year.json",
    "cash_flow": "cash_flow_year.json",
    "ratio": "ratio_year.json",
}

STATEMENT_TAXONOMY = {
    "income_statement": "income_statement",
    "balance_sheet": "balance_sheet",
    "cash_flow": "cash_flow",
    "ratio": "derived",
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


def _read_split_json(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return pd.DataFrame(payload["data"], columns=payload["columns"], index=payload.get("index"))


def _register_local_source(
    *,
    registry: SourceRegistry,
    ticker: str,
    statement: str,
    path: Path,
) -> str:
    payload = path.read_bytes()
    checksum = registry.compute_checksum(payload)
    rel = path.relative_to(ROOT).as_posix()
    source_uri = f"local://{rel}"
    source_id = registry.register_source(
        SourceInput(
            logical_id="bctc_disclosure",
            source_uri=source_uri,
            source_type="financial_statement",
            source_tier=3,
            source_title=f"Local vnstock raw BCTC {ticker} - {statement}",
            checksum=checksum,
            connector_version="local_bctc_raw_v1",
            ticker=ticker,
            raw_path=rel,
            published_at=datetime.now(UTC).isoformat(),
            metadata_json={"provider": "local_raw_cache", "statement": statement},
        )
    )
    registry.register_raw_payload(
        source_id=source_id,
        content_type="application/json",
        checksum=checksum,
        storage_path=rel,
        connector_name="ingest_local_bctc_snapshots",
        connector_version="local_bctc_raw_v1",
        request_uri=source_uri,
    )
    return source_id


def _filter_facts(
    facts: list[FinancialFact],
    *,
    from_year: int,
    to_year: int,
) -> list[FinancialFact]:
    return [
        fact
        for fact in facts
        if fact.fiscal_period == "FY" and from_year <= fact.fiscal_year <= to_year
    ]


def ingest_local_bctc_snapshot(
    ticker: str,
    *,
    from_year: int,
    to_year: int,
    raw_root: Path,
) -> dict[str, Any]:
    ticker = ticker.upper()
    ensure_ticker_registered_from_universe(RuntimeStore(), ticker)
    ticker_dir = raw_root / ticker
    if not ticker_dir.is_dir():
        return {
            "ticker": ticker,
            "status": "missing_local_bctc_dir",
            "raw_dir": str(ticker_dir),
        }

    registry = SourceRegistry()
    all_facts: list[FinancialFact] = []
    statement_counts: dict[str, int] = {}
    missing_files: list[str] = []

    for statement, file_name in STATEMENT_FILES.items():
        path = ticker_dir / file_name
        if not path.exists():
            missing_files.append(file_name)
            continue
        frame = _read_split_json(path)
        source_id = _register_local_source(
            registry=registry,
            ticker=ticker,
            statement=statement,
            path=path,
        )
        alias_map = _build_alias_map(statement=STATEMENT_TAXONOMY[statement])
        facts = _extract_facts_from_frame(
            ticker=ticker,
            frame=frame,
            source_id=source_id,
            parser_version="local_bctc_parser_v1",
            alias_map=alias_map,
            run_id=f"local_bctc_{ticker}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}",
            provider="local_raw_cache",
            statement_type=statement,
            period_type="year",
        )
        facts = _filter_facts(facts, from_year=from_year, to_year=to_year)
        statement_counts[statement] = len(facts)
        all_facts.extend(facts)

    resolved = _resolve_fact_collisions(all_facts)
    inserted = insert_observations(_fact_to_observation(fact) for fact in resolved)
    promotion = promote_accepted_facts(ticker=ticker, from_year=from_year, to_year=to_year)
    if promotion.promoted <= 0:
        return {
            "ticker": ticker,
            "status": "no_promoted_facts",
            "missing_files": missing_files,
            "statement_fact_counts": statement_counts,
            "observations_inserted": inserted,
            "promoted": promotion.promoted,
            "promotion_warnings": promotion.warnings,
            "promotion_errors": promotion.errors,
            "snapshot": None,
            "production_fact_rows": 0,
            "production_metrics": [],
        }
    snapshot = create_snapshot(
        ticker=ticker,
        from_year=from_year,
        to_year=to_year,
        created_by="ingest_local_bctc_snapshots",
    )
    production_facts = get_production_facts(ticker=ticker, from_year=from_year, to_year=to_year)
    return {
        "ticker": ticker,
        "status": "snapshot_created" if snapshot.get("facts_count", 0) else "no_snapshot_facts",
        "missing_files": missing_files,
        "statement_fact_counts": statement_counts,
        "observations_inserted": inserted,
        "promoted": promotion.promoted,
        "promotion_warnings": promotion.warnings,
        "promotion_errors": promotion.errors,
        "snapshot": snapshot,
        "production_fact_rows": len(production_facts),
        "production_metrics": sorted({row["metric"] for row in production_facts}),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build canonical facts and active snapshots from local data/raw/bctc JSON files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--tickers", required=True, help="Comma-separated tickers.")
    parser.add_argument("--from-year", type=int, default=DEFAULT_FROM_YEAR, dest="from_year")
    parser.add_argument("--to-year", type=int, default=DEFAULT_TO_YEAR, dest="to_year")
    parser.add_argument("--raw-root", default="data/raw/bctc")
    parser.add_argument("--write-json", default="output/local_bctc_snapshot_ingest.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = parse_args(argv)
    raw_root = Path(args.raw_root)
    if not raw_root.is_absolute():
        raw_root = ROOT / raw_root
    results = [
        ingest_local_bctc_snapshot(
            ticker.strip().upper(),
            from_year=args.from_year,
            to_year=args.to_year,
            raw_root=raw_root,
        )
        for ticker in args.tickers.split(",")
        if ticker.strip()
    ]
    summary = {
        "processed": len(results),
        "snapshot_created": sum(1 for r in results if r.get("status") == "snapshot_created"),
        "missing_local_bctc_dir": [r["ticker"] for r in results if r.get("status") == "missing_local_bctc_dir"],
        "no_promoted_facts": [r["ticker"] for r in results if r.get("status") == "no_promoted_facts"],
    }
    payload = {"summary": summary, "results": results}
    out = Path(args.write_json)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    print(f"[local-bctc] wrote {out}")
    return 0 if not summary["missing_local_bctc_dir"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
