"""Create the four required private Supabase Storage buckets."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.storage import REQUIRED_BUCKETS, SupabaseStorageAdapter
from scripts.storage.common import add_common_args


def main() -> None:
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps({"dry_run": True, "would_create_private_buckets": REQUIRED_BUCKETS}, indent=2))
        return
    adapter = SupabaseStorageAdapter()
    existing = {row["id"]: row for row in adapter.list_buckets()}
    for bucket in REQUIRED_BUCKETS:
        if bucket not in existing:
            adapter.create_private_bucket(bucket)
        elif existing[bucket].get("public"):
            raise RuntimeError(f"Bucket must be private: {bucket}")
    print(json.dumps({"buckets": REQUIRED_BUCKETS, "private": True}, indent=2))


if __name__ == "__main__":
    main()
