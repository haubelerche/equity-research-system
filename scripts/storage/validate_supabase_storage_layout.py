"""Validate private buckets, object references, checksums, and local cleanup."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import psycopg2

from backend.storage import REQUIRED_BUCKETS, SupabaseStorageAdapter
from backend.settings import settings
from scripts.storage.common import ROOT, files_under

LOCAL_PRODUCTION_ROOTS = (ROOT / "backend" / "data", ROOT / "artifacts", ROOT / "storage")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-db", action="store_true")
    args = parser.parse_args()
    adapter = SupabaseStorageAdapter()
    buckets = {row["id"]: row for row in adapter.list_buckets()}
    errors = [f"missing_bucket:{name}" for name in REQUIRED_BUCKETS if name not in buckets]
    errors += [f"public_bucket:{name}" for name in REQUIRED_BUCKETS if buckets.get(name, {}).get("public")]
    local_files = files_under(LOCAL_PRODUCTION_ROOTS)
    errors += [f"local_production_files:{len(local_files)}"] if local_files else []
    checked = 0
    if not args.skip_db:
        with psycopg2.connect(settings.database_url) as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT storage_bucket, storage_path, checksum FROM ingest.source_documents
                WHERE storage_bucket IS NOT NULL
                UNION ALL
                SELECT storage_bucket, storage_path, checksum FROM research.run_artifacts
                WHERE storage_bucket IS NOT NULL
            """)
            for bucket, path, checksum in cur.fetchall():
                checked += 1
                if not adapter.exists(bucket, path):
                    errors.append(f"missing_object:{bucket}/{path}")
                elif checksum and not adapter.validate_checksum(bucket, path, checksum):
                    errors.append(f"checksum_mismatch:{bucket}/{path}")
    result = {"required_buckets": REQUIRED_BUCKETS, "metadata_objects_checked": checked, "local_file_count": len(local_files), "errors": errors}
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
