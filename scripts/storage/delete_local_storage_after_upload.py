"""Delete local production storage only after audit manifests prove checksum validation."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.storage.common import AUDIT_ROOT, ROOT, files_under

TARGETS = (ROOT / "backend" / "data", ROOT / "artifacts", ROOT / "storage")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    manifests = list(AUDIT_ROOT.glob("*.json")) if AUDIT_ROOT.exists() else []
    validated_sources = set()
    for manifest in manifests:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        for action in payload.get("actions", []):
            if action.get("checksum_validated"):
                validated_sources.add(action["source"])
    local_files = files_under(TARGETS)
    unvalidated = [path for path in local_files if str(path) not in validated_sources]
    if unvalidated:
        raise RuntimeError(f"Refusing deletion: {len(unvalidated)} local files lack successful checksum validation")
    if not args.dry_run:
        for target in TARGETS:
            if target.exists():
                shutil.rmtree(target)
    print(f"before={len(local_files)} after={len(local_files) if args.dry_run else 0} dry_run={args.dry_run}")


if __name__ == "__main__":
    main()
