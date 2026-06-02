"""Manual Upload Connector — Phase 1B.

Registers analyst-uploaded documents (audited BCTC PDFs, annual reports,
HOSE filing PDFs) as Tier 0 or Tier 1 source records in ingest.sources.

Each uploaded file MUST have a companion provenance JSON file at:
    <same_dir>/<filename>_provenance.json

Without a provenance file the upload is registered as Tier 3 and a warning
is printed. The build_facts.py script will refuse to treat such a source as
Tier 1 when checking source tier coverage.

Provenance JSON schema:
    {
        "verified_by": "<analyst_id>",
        "verification_date": "YYYY-MM-DD",
        "source_document_type": "bctc_audited | annual_report | hose_filing | ...",
        "source_tier": 0,
        "fiscal_year": 2023,
        "fiscal_period": "FY",
        "ticker": "DHG",
        "publisher": "DHG Pharma",
        "published_at": "2024-03-15",
        "notes": "Revenue 2023FY verified from page 42 of audited statement.",
        "source_documents_used": ["DHG Annual Report 2023 HOSE Filing"]
    }

Usage:
    python scripts/connectors/manual_upload_connector.py \\
        --file config/dataset/golden/docs/DHG_BCTC_2023.pdf \\
        --ticker DHG

    python scripts/connectors/manual_upload_connector.py \\
        --dir config/dataset/golden/docs/DHG/ \\
        --ticker DHG
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.database.fact_store import PostgresFactStore
from backend.database.source_registry import SourceInput, SourceRegistry

CONNECTOR_VERSION = "manual_upload_v1"
_SUPPORTED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".csv", ".html", ".htm", ".json"}


def _load_provenance(file_path: Path) -> dict | None:
    provenance_path = file_path.parent / f"{file_path.name}_provenance.json"
    if not provenance_path.exists():
        return None
    try:
        return json.loads(provenance_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[manual_upload] WARNING: Could not parse provenance file {provenance_path}: {exc}")
        return None


def _content_type(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    return {
        ".pdf": "application/pdf",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".csv": "text/csv",
        ".html": "text/html",
        ".htm": "text/html",
        ".json": "application/json",
    }.get(ext, "application/octet-stream")


def register_file(
    file_path: Path,
    ticker: str,
    registry: SourceRegistry,
) -> tuple[str, int]:
    """Register one file as a source record. Returns (source_id, resolved_tier)."""
    payload = file_path.read_bytes()
    checksum = hashlib.sha256(payload).hexdigest()
    checksum_path = file_path.with_suffix(file_path.suffix + ".sha256")
    checksum_path.write_text(checksum, encoding="utf-8")

    prov = _load_provenance(file_path)
    if prov is None:
        print(
            f"[manual_upload] WARNING: No provenance file found for {file_path.name}. "
            "Registering as Tier 3. Create a <filename>_provenance.json to classify as Tier 0/1."
        )

    source_tier = int(prov.get("source_tier", 3)) if prov else 3
    source_type = prov.get("source_document_type", "manual") if prov else "manual"
    fiscal_year = int(prov["fiscal_year"]) if prov and prov.get("fiscal_year") else None
    fiscal_period = prov.get("fiscal_period") if prov else None
    published_at = prov.get("published_at") if prov else None
    publisher = prov.get("publisher", "") if prov else ""
    notes = prov.get("notes", "") if prov else ""
    verified_by = prov.get("verified_by", "") if prov else ""

    source_title = (
        f"{source_type.replace('_', ' ').title()} — {ticker} {fiscal_year or ''}"
        if not publisher
        else f"{publisher} — {source_type.replace('_', ' ').title()} {fiscal_year or ''}"
    )

    source_uri = f"file://{file_path.resolve()}"

    source_id = registry.register_source(
        SourceInput(
            logical_id=f"manual_{source_type}_{ticker}_{fiscal_year or 'unknown'}",
            ticker=ticker,
            source_uri=source_uri,
            source_type=source_type if source_type in {
                "manual", "annual_report", "disclosure", "regulatory_filing",
                "financial_statement", "industry_report"
            } else "manual",
            source_tier=source_tier,
            source_title=source_title,
            checksum=checksum,
            connector_version=CONNECTOR_VERSION,
            raw_path=str(file_path.resolve()),
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            published_at=published_at,
            metadata_json={
                "verified_by": verified_by,
                "verification_date": prov.get("verification_date", "") if prov else "",
                "notes": notes,
                "original_filename": file_path.name,
            },
        )
    )

    registry.register_raw_payload(
        source_id=source_id,
        content_type=_content_type(file_path),
        checksum=checksum,
        storage_path=str(file_path.resolve()),
        connector_name="manual_upload_connector",
        connector_version=CONNECTOR_VERSION,
        request_uri=source_uri,
    )

    tier_label = {0: "Tier 0 (audited filing)", 1: "Tier 1 (company IR)", 3: "Tier 3 (unverified)"}.get(
        source_tier, f"Tier {source_tier}"
    )
    print(f"[manual_upload] Registered {file_path.name} → {source_id[:12]}... [{tier_label}]")
    return source_id, source_tier


def upload_files(
    files: list[Path],
    ticker: str,
) -> list[dict]:
    store = PostgresFactStore()
    registry = SourceRegistry(store=store)
    results = []
    for f in files:
        if f.suffix.lower() not in _SUPPORTED_EXTENSIONS:
            print(f"[manual_upload] Skipping unsupported file type: {f.name}")
            continue
        if not f.exists():
            print(f"[manual_upload] ERROR: File not found: {f}")
            continue
        source_id, tier = register_file(file_path=f, ticker=ticker, registry=registry)
        results.append({"file": str(f), "source_id": source_id, "source_tier": tier})
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Register manually uploaded documents as Tier 0/1 source records.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol, e.g. DHG")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=Path, help="Single file to register")
    group.add_argument("--dir", type=Path, help="Directory of files to register")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ticker = args.ticker.strip().upper()
    if args.file:
        files = [args.file]
    else:
        files = [
            f for f in args.dir.iterdir()
            if f.is_file() and f.suffix.lower() in _SUPPORTED_EXTENSIONS
            and not f.name.endswith("_provenance.json")
            and not f.name.endswith(".sha256")
        ]
        files = sorted(files)

    if not files:
        print("[manual_upload] No supported files found.")
        sys.exit(1)

    results = upload_files(files=files, ticker=ticker)
    tier0 = sum(1 for r in results if r["source_tier"] == 0)
    tier1 = sum(1 for r in results if r["source_tier"] == 1)
    tier3 = sum(1 for r in results if r["source_tier"] == 3)
    print(f"\n[manual_upload] Done: {len(results)} files — Tier 0: {tier0}, Tier 1: {tier1}, Tier 3 (no provenance): {tier3}")


if __name__ == "__main__":
    main()
