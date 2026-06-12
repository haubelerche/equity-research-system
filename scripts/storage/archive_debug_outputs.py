"""Archive debug, browser-profile, audit-image, and agent-output files."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.storage.common import safe_move, write_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    legacy = ROOT / "artifacts"
    actions = []
    if legacy.exists():
        for source in sorted(item for item in legacy.rglob("*") if item.is_file()):
            lowered = str(source).lower()
            if any(token in lowered for token in ("agent_outputs", "pdf_compare", ".chrome-profile-", "layout_audit", "visual_check", "preview", "page")):
                destination = ROOT / "storage" / "archive" / "debug" / source.relative_to(legacy)
                actions.append(safe_move(source, destination, dry_run=args.dry_run))
    manifest = write_manifest("debug_outputs", actions, dry_run=args.dry_run)
    print(f"actions={len(actions)} manifest={manifest}")


if __name__ == "__main__":
    main()
