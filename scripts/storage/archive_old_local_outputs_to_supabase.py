"""Upload debug, failed-run, noisy, and unknown legacy files to archive."""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.storage import ARCHIVE_BUCKET, archive_key
from scripts.storage.common import FileAction, ROOT, adapter_for, add_common_args, checksum_file, date_key, files_under, infer_run_id, upload_no_overwrite, write_audit

ROOTS = (ROOT / "backend" / "data", ROOT / "artifacts", ROOT / "storage", ROOT / "output")


def target(source: Path) -> str:
    run_id = infer_run_id(source)
    lowered = source.as_posix().lower()
    relative = next(source.relative_to(root).as_posix() for root in ROOTS if source.is_relative_to(root))
    root_name = next(root.name for root in ROOTS if source.is_relative_to(root))
    if run_id and ("failed" in lowered or "error" in lowered):
        return archive_key("failed_runs", f"{run_id}/{root_name}/{relative}")
    if any(token in lowered for token in ("debug", "preview", "audit", "eval", "log")):
        return archive_key("debug", f"{date_key()}/{root_name}/{relative}")
    original_hash = hashlib.sha256(str(source).encode()).hexdigest()
    return archive_key("legacy", f"{original_hash}/{source.name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    args = parser.parse_args()
    sources = files_under(ROOTS)
    adapter = adapter_for(args.dry_run)
    actions = []
    for index, source in enumerate(sources, start=1):
        key = target(source)
        try:
            actions.append(upload_no_overwrite(adapter, source, ARCHIVE_BUCKET, key, dry_run=args.dry_run))
        except Exception as exc:  # continue so the audit report is complete
            actions.append(FileAction(
                str(source), ARCHIVE_BUCKET, key, "error", checksum_file(source),
                source.stat().st_size, "application/octet-stream", False, str(exc),
            ))
        if index % 100 == 0:
            print(f"processed={index}/{len(sources)}")
    audit = write_audit(args.audit_name or "archive_local_outputs", actions, len(sources), len(sources), args.dry_run)
    print(f"before={len(sources)} after={len(sources)} actions={len(actions)} audit={audit}")


if __name__ == "__main__":
    main()
