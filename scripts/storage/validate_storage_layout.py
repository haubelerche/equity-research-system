"""Fail when production files exist outside the canonical storage contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = (
    "sources/official_documents",
    "runs",
    "exports/approved_reports",
    "archive/legacy",
    "archive/debug",
    "archive/failed_runs",
)
LEGACY = ("artifacts", "backend/data/official_documents", "backend/data/raw/official_documents", "data/official_documents", "data/raw/official_documents")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    storage = ROOT / "storage"
    missing = [path for path in REQUIRED if not (storage / path).exists()]
    legacy_files = {
        path: sum(1 for item in (ROOT / path).rglob("*") if item.is_file())
        for path in LEGACY
        if (ROOT / path).exists()
    }
    result = {"missing_required_directories": missing, "legacy_file_counts": legacy_files}
    print(json.dumps(result, indent=2) if args.json else result)
    raise SystemExit(1 if missing or any(legacy_files.values()) else 0)


if __name__ == "__main__":
    main()
