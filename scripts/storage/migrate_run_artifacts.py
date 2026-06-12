"""Move recognizable legacy artifacts into deterministic run-scoped directories."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.storage.common import file_count, safe_move, write_manifest

RUN_RE = re.compile(r"(run_[A-Za-z0-9_.-]+)")
TIMESTAMP_RE = re.compile(r"((?:20)\d{6}T\d{6})")


def inferred_run_id(path: Path) -> str:
    run_match = RUN_RE.search(path.name)
    if run_match:
        return run_match.group(1).rstrip("_")
    ts_match = TIMESTAMP_RE.search(path.name)
    ticker = path.name.split("_", 1)[0].lower()
    if ts_match:
        return f"legacy_{ticker}_{ts_match.group(1)}"
    return f"legacy_unscoped_{ticker}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    legacy = ROOT / "artifacts"
    before = file_count(legacy)
    actions = []
    if legacy.exists():
        for source in sorted(item for item in legacy.rglob("*") if item.is_file()):
            run_id = inferred_run_id(source)
            destination = ROOT / "storage" / "runs" / run_id / "legacy" / source.relative_to(legacy)
            actions.append(safe_move(source, destination, dry_run=args.dry_run))
    manifest = write_manifest("run_artifacts", actions, dry_run=args.dry_run)
    print(f"before={before} after={file_count(legacy)} actions={len(actions)} manifest={manifest}")


if __name__ == "__main__":
    main()
