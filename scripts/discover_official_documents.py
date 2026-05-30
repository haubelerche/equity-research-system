"""Official document discovery + fetching — Source-Provenance Rebuild, Phase 3A/3B.

Controlled discovery of public official documents for a ticker (company IR + HOSE/HNX/SSC),
ranking by source priority, then fetching approved candidates.

Usage:
    python scripts/discover_official_documents.py --ticker DHG --from-year 2021 --to-year 2025
    python scripts/discover_official_documents.py --ticker DHG --from-year 2021 --to-year 2025 --fetch
    python scripts/discover_official_documents.py --ticker DHG --from-year 2021 --to-year 2025 --fetch --types annual_report,audited_financial_statement

Outputs:
    data/discovered_documents/<TICKER>/document_candidates.json
    artifacts/official_sources/<TICKER>_document_discovery.md
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

ROOT = Path(_PROJECT_ROOT)
DISCOVERED_DIR = ROOT / "data" / "discovered_documents"
ARTIFACT_DIR = ROOT / "artifacts" / "official_sources"


def write_outputs(result, fetched: list, fetch_errors: list) -> tuple[Path, Path]:
    ticker = result.ticker
    out_json_dir = DISCOVERED_DIR / ticker
    out_json_dir.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    payload["fetched"] = [f.to_dict() for f in fetched]
    payload["fetch_errors"] = fetch_errors
    json_path = out_json_dir / "document_candidates.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = ARTIFACT_DIR / f"{ticker}_document_discovery.md"
    sel = result.ranking.selected
    lines = [
        f"# {ticker} Official Document Discovery (Phase 3A/3B)",
        "",
        f"- Generated: {datetime.now(UTC).isoformat()}",
        f"- Year range: {result.from_year}–{result.to_year}",
        f"- Candidates discovered: {len(result.candidates)}",
        f"- Selected (auto-promotable): {len(sel)}",
        f"- Needs review (low confidence): {len(result.ranking.needs_review)}",
        f"- Superseded duplicates: {len(result.ranking.superseded)}",
        f"- Fetched: {len(fetched)}",
        "",
        "## Per-source counts",
        "",
    ]
    for src, n in result.per_source.items():
        lines.append(f"- {src}: {n}")
    lines += ["", "## Selected candidates (ranked)", "",
              "| FY | Type | Source | Conf | Title |",
              "|----|------|--------|------|-------|"]
    for c in sorted(sel, key=lambda c: (c.fiscal_year or 0, c.document_type)):
        lines.append(f"| {c.fiscal_year} | {c.document_type} | {c.source_name} | "
                     f"{c.confidence:.2f} | {c.title[:48]} |")
    if result.ranking.needs_review:
        lines += ["", "## Needs review (NOT auto-promoted)", ""]
        for c in result.ranking.needs_review:
            lines.append(f"- {c.fiscal_year}/{c.document_type} — {c.source_name} "
                         f"conf={c.confidence:.2f}: {c.ranking_reason}")
    if fetched:
        lines += ["", "## Fetched documents (Phase 3B)", "",
                  "| FY | Type | Hash (sha256) | Local path |",
                  "|----|------|---------------|------------|"]
        for f in fetched:
            lines.append(f"| {f.fiscal_year} | {f.document_type} | `{f.file_hash[:16]}…` | {f.local_path} |")
    if fetch_errors:
        lines += ["", "## Fetch errors", ""] + [f"- {e}" for e in fetch_errors]
    lines += [
        "",
        "## Notes",
        "",
        "- Controlled discovery only: sources come from the company registry + approved",
        "  exchange/SSC connectors. No uncontrolled generic crawling.",
        "- company IR is P0; HOSE/HNX/SSC are P1 (best-effort: their portals are JS/API-",
        "  driven and may need official APIs to yield direct file links).",
        "- Low-confidence candidates are flagged needs_review and NOT auto-fetched.",
        "- Fetched files feed the existing `scripts/ingest_official_documents.py` pipeline",
        "  (place/point extracted_facts.csv at the fetched PDF, then ingest → reconcile).",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Discover + fetch official documents for a ticker.")
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--from-year", type=int, required=True, dest="from_year")
    ap.add_argument("--to-year", type=int, required=True, dest="to_year")
    ap.add_argument("--fetch", action="store_true", help="Download approved (selected) candidates")
    ap.add_argument("--min-confidence", type=float, default=0.6, dest="min_confidence")
    ap.add_argument("--types", default="", help="Comma list to restrict fetch (e.g. annual_report,audited_financial_statement)")
    args = ap.parse_args()
    ticker = args.ticker.strip().upper()

    from backend.documents.official_document_discovery import discover_documents, fetch_candidate

    result = discover_documents(ticker, args.from_year, args.to_year, min_confidence=args.min_confidence)
    print(f"[discover] {ticker}: {len(result.candidates)} candidates "
          f"({len(result.ranking.selected)} selected); per-source={result.per_source}")

    fetched, fetch_errors = [], []
    if args.fetch:
        type_filter = {t.strip() for t in args.types.split(",") if t.strip()}
        for c in result.ranking.selected:
            if type_filter and c.document_type not in type_filter:
                continue
            try:
                rec = fetch_candidate(c)
                fetched.append(rec)
                print(f"[fetch] {c.fiscal_year}/{c.document_type} -> {rec.local_path} "
                      f"(sha256 {rec.file_hash[:16]}…)")
            except Exception as e:  # noqa: BLE001
                fetch_errors.append(f"{c.source_url}: {type(e).__name__}: {e}")
                print(f"[fetch] FAILED {c.source_url}: {e}")

    json_path, md_path = write_outputs(result, fetched, fetch_errors)
    print(f"[discover] candidates JSON: {json_path}")
    print(f"[discover] artifact: {md_path}")


if __name__ == "__main__":
    main()
