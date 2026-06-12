"""Move immutable official PDFs into storage/sources/official_documents."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.storage.layout import source_document_path
from scripts.storage.common import file_count, safe_move, sha256, write_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    roots = [ROOT / "data" / "raw" / "official_documents", ROOT / "backend" / "data" / "raw" / "official_documents"]
    before = sum(file_count(path) for path in roots)
    actions = []
    for base in roots:
        if not base.exists():
            continue
        for pdf in sorted(base.rglob("*.pdf")):
            relative = pdf.relative_to(base)
            ticker = relative.parts[0]
            year = relative.parts[1]
            destination = source_document_path(ticker, year, sha256(pdf))
            actions.append(safe_move(pdf, destination, dry_run=args.dry_run))
            sidecar = pdf.with_suffix(pdf.suffix + ".sha256")
            if sidecar.exists() and not args.dry_run:
                sidecar.unlink()
    manifest = write_manifest("official_documents", actions, dry_run=args.dry_run)
    after = sum(file_count(path) for path in roots)
    print(f"before={before} after={after} actions={len(actions)} manifest={manifest}")


if __name__ == "__main__":
    main()
