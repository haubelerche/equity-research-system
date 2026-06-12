"""Phase 3 â€” Canonical Facts and Data Quality Gates.

Reads canonical financial facts from the v2 production facts view (fact.production_facts),
filters to FY-only periods within the required MVP range (2021â€“2025), scores completeness,
and saves a structured fact-report artifact.

v2 data path (only path â€” no legacy fallback):
  fact.production_facts â†’ build_fact_table() â†’ valuation/report pipeline

Usage:
    PYTHONUTF8=1 python scripts/build_facts.py --ticker DHG
    PYTHONUTF8=1 python scripts/build_facts.py --ticker DHG --strict-completeness
    PYTHONUTF8=1 python scripts/build_facts.py --ticker DHG --from-year 2021 --to-year 2025

Outputs:
    storage/runs/{run_id}/facts_snapshot.json
    stdout: completeness / freshness summary
"""
from __future__ import annotations

import re
import sys as _sys
from pathlib import Path as _Path

_PROJECT_ROOT = str(_Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)
if "" in _sys.path:
    _sys.path = [p for p in _sys.path if p != ""] + [""]

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

_env_file = _Path(__file__).resolve().parents[1] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip(chr(34)).strip(chr(39)))

ROOT = _Path(__file__).resolve().parents[1]
FACTS_DIR = ROOT / "storage" / "runs" / os.environ.get("RUN_ID", "missing_run_id")

from backend.period_scope import DEFAULT_FROM_YEAR as MVP_FROM_YEAR
from backend.period_scope import DEFAULT_TO_YEAR as MVP_TO_YEAR

_ALLOWED_FY_RE = re.compile(r"^(20\d{2})FY$")


def _is_allowed_fy(period_key: str, from_year: int, to_year: int) -> bool:
    m = _ALLOWED_FY_RE.match(period_key)
    if not m:
        return False
    return from_year <= int(m.group(1)) <= to_year


def _canonical_facts_to_normalizer_shape(canonical_rows: list[dict]) -> list[dict]:
    """Map fact.production_facts rows â†’ shape expected by build_fact_table().

    v2 row fields: fact_id, ticker, period ("2023FY"), metric, value, unit,
                   currency, confidence, source_tier, reconciliation_status, updated_at

    Legacy shape fields: line_item_code, fiscal_year (int), fiscal_period ("FY"),
                         value, unit, currency, source_tier, confidence,
                         fact_id, source_id, ingested_at
    """
    mapped = []
    for row in canonical_rows:
        period = row.get("period", "")
        m = _ALLOWED_FY_RE.match(period)
        if not m:
            continue
        mapped.append({
            "line_item_code": row["metric"],
            "fiscal_year": int(m.group(1)),
            "fiscal_period": "FY",
            "value": row["value"],
            "unit": row.get("unit", "vnd_bn"),
            "currency": row.get("currency", "VND"),
            "source_tier": row.get("source_tier"),
            "confidence": row.get("confidence"),
            "validation_status": row.get("quality_status", "unknown"),
            "fact_id": row.get("fact_id", ""),
            "source_id": row.get("source_doc_id") or row.get("fact_id", ""),
            "source_doc_id": row.get("source_doc_id"),
            "source_uri": row.get("source_uri") or "",
            "source_title": row.get("source_title") or "",
            "ingestion_version": row.get("ingestion_version"),
            "ingested_at": row.get("updated_at"),
        })
    return mapped


def _filter_facts(
    raw_facts: list[dict],
    from_year: int,
    to_year: int,
) -> tuple[list[dict], list[str]]:
    """Split raw_facts into (fy_only_facts, forbidden_period_keys)."""
    fy_facts: list[dict] = []
    forbidden_set: set[str] = set()
    for row in raw_facts:
        period_key = f"{row['fiscal_year']}{row['fiscal_period']}"
        if _is_allowed_fy(period_key, from_year, to_year):
            fy_facts.append(row)
        else:
            forbidden_set.add(period_key)
    return fy_facts, sorted(forbidden_set)


def build_facts(
    ticker: str,
    from_year: int = MVP_FROM_YEAR,
    to_year: int = MVP_TO_YEAR,
    strict_completeness: bool = False,
    run_id: str | None = None,
) -> dict:
    from backend.database.canonical.fact_dal import get_production_facts
    from backend.facts.normalizer import (
        build_fact_table, build_validation_status_table, compute_derived,
        periods_sorted, build_source_conflict_report, build_source_tier_coverage,
    )
    from backend.facts.completeness import build_fy_validation_report

    ticker = ticker.strip().upper()
    generated_at = datetime.now(UTC)
    required_years = list(range(from_year, to_year + 1))
    required_periods = [f"{y}FY" for y in required_years]

    print(f"[build_facts] {ticker} â€” v2 data path (fact.production_facts)")
    print(f"[build_facts] {ticker} required periods: {', '.join(required_periods)}")

    # â”€â”€ Load canonical facts from v2 production view â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    canonical_rows = get_production_facts(
        ticker=ticker,
        from_year=from_year,
        to_year=to_year,
    )

    if not canonical_rows:
        print(
            f"[build_facts] ERROR: No v2 production facts found for {ticker}. "
            "Run ingest_ticker.py â†’ migrate_clean_data_to_v2.py â†’ fact_promotion first."
        )
        sys.exit(1)

    # Map v2 shape â†’ legacy shape expected by build_fact_table()
    raw_facts = _canonical_facts_to_normalizer_shape(canonical_rows)
    print(f"[build_facts] {ticker} â€” {len(raw_facts)} canonical facts loaded from fact.production_facts")

    # Separate FY-only facts from forbidden periods
    fy_facts, forbidden_periods = _filter_facts(raw_facts, from_year, to_year)

    if forbidden_periods:
        print(f"[build_facts] {ticker} forbidden quarterly periods ignored: {', '.join(forbidden_periods)}")
    print(f"[build_facts] {ticker} â€” {len(fy_facts)} facts remain after FY-only filter")

    if not fy_facts:
        print(
            f"[build_facts] ERROR: No FY facts found for {ticker} in {from_year}â€“{to_year}. "
            "Re-ingest and re-promote with appropriate year range."
        )
        sys.exit(1)

    # Build fact table â€” returns FactEntry objects with source provenance
    base_table = build_fact_table(fy_facts)
    vstatus_table = build_validation_status_table(fy_facts)
    full_table = compute_derived(base_table)
    periods = periods_sorted(full_table)

    # Source conflict report (v2 production_facts already has one winner per metric/period,
    # so conflicts should be zero â€” but still run for safety and logging)
    source_conflicts = build_source_conflict_report(ticker=ticker, raw_facts=fy_facts)
    source_tier_coverage = build_source_tier_coverage(
        raw_facts=fy_facts, required_periods=required_periods
    )
    if source_conflicts:
        print(f"[build_facts] {ticker} source conflicts detected: {len(source_conflicts)}")
        for c in source_conflicts[:5]:
            flag = " [REQUIRES REVIEW]" if c.requires_review else ""
            print(f"  {c.metric} {c.period}: variance={c.variance_pct:.1f}%{flag}")
    else:
        print(f"[build_facts] {ticker} no source conflicts detected")

    periods_available = [p for p in required_periods if p in periods]
    periods_missing = [p for p in required_periods if p not in periods]

    print(f"[build_facts] {ticker} periods available: {', '.join(periods_available) or 'none'}")
    if periods_missing:
        print(f"[build_facts] {ticker} periods missing: {', '.join(periods_missing)}")

    latest_fy = max((int(p[:4]) for p in periods_available), default=None)
    print(f"[build_facts] {ticker} latest fiscal year: {latest_fy}")

    source_tiers_by_period = {
        period: cov["tiers_present"]
        for period, cov in source_tier_coverage.items()
    }

    for period, cov in sorted(source_tier_coverage.items()):
        tier_label = "Tier 0/1 âœ“" if cov["has_tier01"] else f"Tier 3-only (tiers={cov['tiers_present']})"
        print(f"[build_facts] {ticker} {period}: {tier_label}")

    report = build_fy_validation_report(
        ticker=ticker,
        table=full_table,
        raw_facts=fy_facts,
        required_periods=required_periods,
        periods_available=periods_available,
        periods_missing=periods_missing,
        forbidden_periods=forbidden_periods,
        generated_at=generated_at,
        validation_status_table=vstatus_table,
        source_tiers_by_period=source_tiers_by_period,
    )

    print(f"[build_facts] {ticker} annual_reports_collected: {report['annual_reports_collected']}")
    print(f"[build_facts] {ticker} coverage_gate: {report['coverage_gate']}")
    print(f"[build_facts] {ticker} core_keys_gate: {report['core_keys_gate']}")
    print(f"[build_facts] {ticker} source_tier_coverage_status: {report['source_tier_coverage_status']}")
    print(f"[build_facts] {ticker} valuation_gate: {report['valuation_gate']}")
    print(f"[build_facts] {ticker} valuation_ready: {report['valuation_ready']}")
    print(f"[build_facts] {ticker} run_status: {report['run_status']}")
    if report.get("blocking_reasons"):
        for reason in report["blocking_reasons"]:
            print(f"[build_facts] {ticker} BLOCKED: {reason}")

    print(f"\n[build_facts] Fact table (v2 canonical facts):")
    for key in sorted(base_table.keys()):
        values = base_table[key]
        row_str = "  ".join(
            f"{p}={e.value:,.1f}[T{e.source_tier if e.source_tier is not None else '?'}]"
            for p, e in sorted(values.items())
        )
        print(f"  {key:<35} {row_str}")

    print(f"\n[build_facts] Derived metrics:")
    derived_keys = [k for k in full_table if k not in base_table]
    for key in sorted(derived_keys):
        values = full_table[key]
        row_str = "  ".join(f"{p}={e.value:.4f}" for p, e in sorted(values.items()))
        print(f"  {key:<35} {row_str}")

    def _entry_to_dict(entry) -> dict:
        return {
            "value": entry.value,
            "fact_id": entry.fact_id or "",
            "source_id": entry.source_id or "",
            "source_uri": entry.source_uri or "",
            "source_title": entry.source_title or "",
            "source_tier": entry.source_tier,
            "confidence": entry.confidence,
        }

    artifact = {
        "ticker": ticker,
        "generated_at": generated_at.isoformat(),
        "source": "fact.production_facts",
        "period_mode": "year",
        "from_year": from_year,
        "to_year": to_year,
        "required_periods": required_periods,
        "periods_available": periods_available,
        "periods_missing": periods_missing,
        "forbidden_periods_ignored": forbidden_periods,
        "facts": {
            k: {p: _entry_to_dict(e) for p, e in sorted(v.items())}
            for k, v in sorted(full_table.items())
        },
        "source_conflicts": [
            {
                "ticker": c.ticker,
                "period": c.period,
                "metric": c.metric,
                "candidate_values": c.candidate_values,
                "selected_source_id": c.selected_source_id,
                "variance_pct": c.variance_pct,
                "requires_review": c.requires_review,
                "decision_reason": c.decision_reason,
            }
            for c in source_conflicts
        ],
        "source_tier_coverage": source_tier_coverage,
        "validation": report,
    }

    effective_run_id = (run_id or os.environ.get("RUN_ID") or "").strip()
    if not effective_run_id:
        raise ValueError("RUN_ID is required for facts snapshot output")
    facts_dir = ROOT / "storage" / "runs" / effective_run_id
    facts_dir.mkdir(parents=True, exist_ok=True)
    out_path = facts_dir / "facts_snapshot.json"
    out_path.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
    artifact["artifact_path"] = str(out_path)
    print(f"\n[build_facts] Artifact saved: {out_path}")

    # Create v2 snapshot if valuation gate passed
    if report.get("valuation_gate") == "pass":
        try:
            from backend.database.canonical.snapshot_dal import create_snapshot
            snap = create_snapshot(
                ticker=ticker,
                from_year=from_year,
                to_year=to_year,
                created_by="build_facts",
            )
            artifact["snapshot_id"] = snap["snapshot_id"]
            print(
                f"[build_facts] v2 snapshot created: {snap['snapshot_id']} "
                f"({snap['facts_count']} facts, periods={snap['periods']})"
            )
        except Exception as _exc:  # noqa: BLE001
            print(f"[build_facts] WARNING: v2 snapshot creation retrying after error: {_exc}")
            time.sleep(1)
            try:
                snap = create_snapshot(
                    ticker=ticker,
                    from_year=from_year,
                    to_year=to_year,
                    created_by="build_facts",
                )
                artifact["snapshot_id"] = snap["snapshot_id"]
                print(
                    f"[build_facts] v2 snapshot created on retry: {snap['snapshot_id']} "
                    f"({snap['facts_count']} facts, periods={snap['periods']})"
                )
            except Exception as retry_exc:  # noqa: BLE001
                print(f"[build_facts] WARNING: v2 snapshot creation skipped: {retry_exc}")

    if strict_completeness and report["valuation_gate"] != "pass":
        print(
            f"[build_facts] STRICT COMPLETENESS FAIL â€” "
            f"valuation_gate={report['valuation_gate']} reasons={report.get('blocking_reasons', [])}"
        )
        sys.exit(2)

    return artifact


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build canonical fact report for a ticker from v2 production facts (FY-only, 2021â€“2025).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol, e.g. DHG")
    parser.add_argument(
        "--from-year",
        type=int,
        default=MVP_FROM_YEAR,
        dest="from_year",
        help=f"First required fiscal year (default: {MVP_FROM_YEAR}).",
    )
    parser.add_argument(
        "--to-year",
        type=int,
        default=MVP_TO_YEAR,
        dest="to_year",
        help=f"Last required fiscal year (default: {MVP_TO_YEAR}).",
    )
    parser.add_argument(
        "--strict-completeness",
        action="store_true",
        help="Exit code 2 if valuation_gate != pass.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Alias for --strict-completeness.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_facts(
        ticker=args.ticker,
        from_year=args.from_year,
        to_year=args.to_year,
        strict_completeness=args.strict_completeness or args.strict,
    )
    print("\n[build_facts] done")


if __name__ == "__main__":
    main()
