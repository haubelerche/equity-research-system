"""Upload legacy official PDFs to sources and register canonical DB metadata."""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.database.canonical.source_dal import upsert_source_document
from backend.storage import SOURCES_BUCKET, source_document_key
from scripts.storage.common import ROOT, adapter_for, add_common_args, files_under, upload_no_overwrite, write_audit

ROOTS = (ROOT / "backend" / "data" / "official_documents", ROOT / "backend" / "data" / "raw" / "official_documents")


def metadata(path: Path) -> tuple[str, int]:
    relative = next(path.relative_to(root) for root in ROOTS if path.is_relative_to(root))
    ticker = relative.parts[0].upper() if relative.parts else "UNKNOWN"
    year = next((int(part) for part in relative.parts if part.isdigit() and len(part) == 4), 0)
    if not year:
        raise ValueError(f"Cannot infer fiscal year from {path}")
    return ticker, year


def main() -> None:
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    args = parser.parse_args()
    sources = [path for path in files_under(ROOTS) if path.suffix.lower() == ".pdf"]
    adapter = adapter_for(args.dry_run)
    actions = []
    for source in sources:
        ticker, year = metadata(source)
        source_doc_id = __import__("hashlib").sha256(source.read_bytes()).hexdigest()
        key = source_document_key(ticker, year, source_doc_id)
        action = upload_no_overwrite(adapter, source, SOURCES_BUCKET, key, dry_run=args.dry_run)
        actions.append(action)
        if not args.dry_run:
            upsert_source_document(
                ticker=ticker,
                source_type="annual_report",
                source_tier=0,
                source_uri=f"supabase://{SOURCES_BUCKET}/{key}",
                checksum=action.checksum,
                source_title=source.stem,
                fiscal_year=year,
                storage_bucket=SOURCES_BUCKET,
                storage_path=key,
                content_type=action.content_type,
                file_size_bytes=action.file_size_bytes,
                uploaded_at=datetime.now(UTC),
                fetch_status="verified",
                metadata={"migrated_from": str(source)},
            )
    audit = write_audit(args.audit_name or "official_documents", actions, len(sources), len(sources), args.dry_run)
    print(f"before={len(sources)} after={len(sources)} actions={len(actions)} audit={audit}")


if __name__ == "__main__":
    main()
