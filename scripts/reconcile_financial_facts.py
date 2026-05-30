"""Reconcile vnstock/provider facts against official-document facts — Phase 4.

Usage:
    python scripts/reconcile_financial_facts.py --ticker DHG --from-year 2021 --to-year 2025
    python scripts/reconcile_financial_facts.py --ticker DHG --from-year 2021 --to-year 2025 --no-promote
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_env_file = Path(_PROJECT_ROOT) / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

ARTIFACT_DIR = Path(_PROJECT_ROOT) / "artifacts" / "reconciliation"


def write_artifact(summary, from_year: int, to_year: int) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out = ARTIFACT_DIR / f"{summary.ticker}_financial_fact_reconciliation.md"
    lines = [
        f"# {summary.ticker} Financial Fact Reconciliation (Phase 4)",
        "",
        f"- Generated: {datetime.now(UTC).isoformat()}",
        f"- Year range: {from_year}–{to_year}",
        f"- Tolerance: 0.5% (diff ≤ tolerance → matched_official)",
        "",
        "| Metric | Total compared | Matched | Mismatch | Missing official | Missing API | Manual review | Promoted |",
        "|--------|----------------|---------|----------|------------------|-------------|---------------|----------|",
        f"| **ALL** | {summary.total} | {summary.matched} | {summary.mismatch} | "
        f"{summary.missing_official} | {summary.missing_api} | "
        f"{summary.manual_review_required} | {summary.promoted} |",
        "",
        "## Promoted verified facts",
        "",
        f"- **{summary.promoted}** fact(s) promoted to `fact.verified_financial_facts` "
        "(matched_official / manual_reviewed only).",
        "",
        "## Detail (first 40)",
        "",
        "| Year | Metric | API value | Official value | diff % | Status |",
        "|------|--------|-----------|----------------|--------|--------|",
    ]
    for r in summary.results[:40]:
        api = f"{r.api_value:,.1f}" if r.api_value is not None else "—"
        off = f"{r.official_value:,.1f}" if r.official_value is not None else "—"
        dp = f"{r.diff_pct:.2f}" if r.diff_pct is not None else "—"
        lines.append(f"| {r.fiscal_year} | {r.metric_id} | {api} | {off} | {dp} | {r.status} |")
    if summary.missing_official == summary.total and summary.total > 0:
        lines += [
            "",
            "> **All facts are `missing_official`** — no official documents have been ingested "
            "yet (Phase 3). Until official facts exist, nothing is promoted and final export "
            "stays blocked. This is the intended state.",
        ]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile API facts vs official facts.")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--from-year", type=int, required=True, dest="from_year")
    parser.add_argument("--to-year", type=int, required=True, dest="to_year")
    parser.add_argument("--tolerance-pct", type=float, default=0.5, dest="tolerance_pct")
    parser.add_argument("--no-promote", action="store_true",
                        help="Compute reconciliation without promoting facts")
    parser.add_argument("--canonical-version", default="v_legacy", dest="canonical_version")
    args = parser.parse_args()
    ticker = args.ticker.strip().upper()

    from backend.reconciliation.financial_fact_reconciler import reconcile_ticker

    summary = reconcile_ticker(
        ticker, args.from_year, args.to_year,
        tolerance_pct=args.tolerance_pct,
        canonical_version=args.canonical_version,
        promote=not args.no_promote,
    )
    artifact = write_artifact(summary, args.from_year, args.to_year)
    print(f"[reconcile_financial_facts] {ticker}: {summary.to_dict()}")
    print(f"[reconcile_financial_facts] artifact: {artifact}")


if __name__ == "__main__":
    main()
