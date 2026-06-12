"""Delete checksum-identical duplicate files while preserving one canonical copy."""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.storage.common import FileAction, sha256, write_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in (ROOT / "storage").rglob("*"):
        if path.is_file() and "migration_manifests" not in path.parts:
            grouped[sha256(path)].append(path)
    actions = []
    for checksum, paths in grouped.items():
        for duplicate in sorted(paths)[1:]:
            actions.append(FileAction(str(duplicate), str(sorted(paths)[0]), "delete_duplicate", checksum, duplicate.stat().st_size))
            if not args.dry_run:
                duplicate.unlink()
    manifest = write_manifest("duplicate_deletion", actions, dry_run=args.dry_run)
    print(f"duplicates={len(actions)} manifest={manifest}")


if __name__ == "__main__":
    main()
