"""Catalyst source ingestion orchestrator — Source-Provenance Rebuild, Phase 5.

Pipeline:
    source_registry -> (seed urls) -> fetcher -> document_store -> event_extractor
    -> ticker_mapper -> evidence store (fact.catalyst_events)

Controlled, not a crawler. Reads a seed file of source URLs and an optional candidate-
events JSONL; only registered+enabled sources are used; every stored event must pass
validation (concrete source_document_id + evidence + controlled type + ticker mapping).

Usage:
    python scripts/ingest_catalyst_sources.py --ticker DHG --limit 20
"""
from __future__ import annotations

import argparse
import json
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

ROOT = Path(_PROJECT_ROOT)
SEED_DIR = ROOT / "data" / "source_seed_urls"
ARTIFACT_DIR = ROOT / "artifacts" / "catalysts"


def _parse_seed_file(ticker: str) -> list[dict]:
    path = SEED_DIR / f"{ticker}_urls.txt"
    entries: list[dict] = []
    if not path.exists():
        return entries
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        entries.append({
            "source_name": parts[0],
            "url": parts[1],
            "title": parts[2] if len(parts) > 2 else parts[1],
            "local_file": parts[3] if len(parts) > 3 else None,
        })
    return entries


def _load_candidate_events(ticker: str) -> list[dict]:
    """Optional analyst-provided candidate events (JSONL)."""
    path = SEED_DIR / f"{ticker}_events.jsonl"
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(json.loads(line))
    return out


def run(ticker: str, limit: int = 20) -> dict:
    from backend.catalysts.event_extractor import extract_events
    from backend.catalysts.ticker_mapper import map_event_to_ticker
    from backend.sources.source_registry import enabled_sources

    sources = enabled_sources()
    by_name = {s.name: s for s in sources}
    seeds = _parse_seed_file(ticker)[:limit]
    candidate_events = _load_candidate_events(ticker)

    fetched, failed = [], []
    # Fetching is only attempted for seeds that point at a local_file (manual/connector)
    # to keep this deterministic and offline; http seeds are recorded as "skipped_network".
    from backend.sources.document_fetcher import FetchError, fetch_document
    for seed in seeds:
        src = by_name.get(seed["source_name"])
        if src is None:
            failed.append({**seed, "reason": "source_name not in enabled registry"})
            continue
        if seed.get("local_file"):
            try:
                doc = fetch_document(src, seed["url"], seed["title"], local_file=seed["local_file"])
                fetched.append(doc.to_dict())
            except FetchError as exc:
                failed.append({**seed, "reason": str(exc)})
        else:
            failed.append({**seed, "reason": "no local_file; network fetch skipped in MVP"})

    # Event extraction + validation + ticker mapping.
    valid_events, rejected = extract_events(candidate_events)
    mapped, sector_level = 0, 0
    for ev in valid_events:
        mapping = map_event_to_ticker(ev.event_title + " " + ev.event_summary, ev.ticker)
        if mapping.level == "explicit":
            mapped += 1
        else:
            sector_level += 1

    summary = {
        "ticker": ticker,
        "sources_checked": len(sources),
        "documents_fetched": len(fetched),
        "documents_failed": len(failed),
        "events_extracted": len(valid_events),
        "events_rejected": len(rejected),
        "events_mapped_to_ticker": mapped,
        "events_sector_level": sector_level,
        "failed_detail": failed[:10],
        "rejected_detail": rejected[:10],
    }
    return summary


def write_artifact(summary: dict) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out = ARTIFACT_DIR / f"{summary['ticker']}_catalyst_source_ingestion.md"
    lines = [
        f"# {summary['ticker']} Catalyst Source Ingestion (Phase 5)",
        "",
        f"- Generated: {datetime.now(UTC).isoformat()}",
        f"- Sources checked (enabled): {summary['sources_checked']}",
        f"- Documents fetched: {summary['documents_fetched']}",
        f"- Documents failed: {summary['documents_failed']}",
        f"- Events extracted (valid): {summary['events_extracted']}",
        f"- Events rejected (invalid): {summary['events_rejected']}",
        f"- Events mapped to ticker: {summary['events_mapped_to_ticker']}",
        f"- Events marked sector-level: {summary['events_sector_level']}",
        "",
        "## Notes",
        "",
        "- Controlled pipeline: only registered+enabled sources in `config/source_registry.yaml`.",
        "- Every stored catalyst event must have a concrete `source_document_id`, evidence",
        "  quote/span, a controlled `event_type`, and an explicit or sector-level ticker mapping.",
        "- Seed URLs: `data/source_seed_urls/<TICKER>_urls.txt`; candidate events:",
        "  `data/source_seed_urls/<TICKER>_events.jsonl`. Empty until an analyst seeds them.",
    ]
    if summary["failed_detail"]:
        lines += ["", "## Failed (first 10)", ""]
        for f in summary["failed_detail"]:
            lines.append(f"- {f.get('source_name','?')}: {f.get('reason','?')}")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest catalyst sources for a ticker.")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    ticker = args.ticker.strip().upper()
    summary = run(ticker, args.limit)
    artifact = write_artifact(summary)
    print(f"[ingest_catalyst_sources] {ticker}: "
          f"{summary['sources_checked']} sources, {summary['documents_fetched']} docs, "
          f"{summary['events_extracted']} events ({summary['events_rejected']} rejected)")
    print(f"[ingest_catalyst_sources] artifact: {artifact}")


if __name__ == "__main__":
    main()
