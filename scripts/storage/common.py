"""Checksum-safe Supabase Storage migration primitives."""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from backend.storage.supabase_adapter import SupabaseStorageAdapter

ROOT = Path(__file__).resolve().parents[2]
AUDIT_ROOT = ROOT / "audits" / "storage_migrations"
RUN_RE = re.compile(r"(run_[A-Za-z0-9_.-]+)")


def _load_env_file() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()


@dataclass
class FileAction:
    source: str
    bucket: str
    storage_path: str
    action: str
    checksum: str
    file_size_bytes: int
    content_type: str
    checksum_validated: bool
    error: str | None = None


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--audit-name", default=None)


def checksum_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def files_under(paths: Iterable[Path]) -> list[Path]:
    return sorted(item for root in paths if root.exists() for item in root.rglob("*") if item.is_file())


def infer_run_id(path: Path) -> str | None:
    match = RUN_RE.search(path.as_posix())
    return match.group(1).rstrip("_") if match else None


def upload_no_overwrite(
    adapter: SupabaseStorageAdapter | None,
    source: Path,
    bucket: str,
    storage_path: str,
    *,
    dry_run: bool,
) -> FileAction:
    checksum = checksum_file(source)
    content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    if dry_run:
        return FileAction(str(source), bucket, storage_path, "would_upload", checksum, source.stat().st_size, content_type, False)
    assert adapter is not None
    if adapter.exists(bucket, storage_path):
        if not adapter.validate_checksum(bucket, storage_path, checksum):
            raise FileExistsError(f"Refusing overwrite with different checksum: {bucket}/{storage_path}")
        action = "skip_checksum_match"
    else:
        adapter.upload_file(bucket, storage_path, source, content_type)
        action = "uploaded"
    validated = adapter.validate_checksum(bucket, storage_path, checksum)
    if not validated:
        raise RuntimeError(f"Post-upload checksum mismatch: {bucket}/{storage_path}")
    return FileAction(str(source), bucket, storage_path, action, checksum, source.stat().st_size, content_type, True)


def write_audit(name: str, actions: list[FileAction], before_count: int, after_count: int, dry_run: bool) -> Path:
    AUDIT_ROOT.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = AUDIT_ROOT / f"{name}_{timestamp}.json"
    document = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dry_run": dry_run,
        "before_file_count": before_count,
        "after_file_count": after_count,
        "actions": [asdict(action) for action in actions],
        "rollback_manifest": [
            {"operation": "remove_object", "bucket": action.bucket, "storage_path": action.storage_path, "checksum": action.checksum}
            for action in actions
            if action.action == "uploaded"
        ],
        "summary": {
            "uploaded": sum(action.action == "uploaded" for action in actions),
            "checksum_matches": sum(action.action == "skip_checksum_match" for action in actions),
            "errors": sum(bool(action.error) for action in actions),
        },
    }
    target.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return target


def adapter_for(dry_run: bool) -> SupabaseStorageAdapter | None:
    return None if dry_run else SupabaseStorageAdapter()


def date_key() -> str:
    return datetime.now(UTC).date().isoformat()


def register_run_artifact(run_id: str, action: FileAction, artifact_type: str = "other") -> bool:
    """Register metadata when the referenced research run exists."""
    import psycopg2
    from backend.settings import settings

    artifact_id = hashlib.sha256(f"{run_id}|{action.bucket}|{action.storage_path}|{action.checksum}".encode()).hexdigest()
    with psycopg2.connect(settings.database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM research.runs WHERE run_id = %s", (run_id,))
        if cur.fetchone() is None:
            return False
        cur.execute(
            """
            INSERT INTO research.run_artifacts (
                artifact_id, run_id, artifact_type, version, payload_json,
                storage_bucket, storage_path, checksum, content_type,
                file_size_bytes, is_locked
            )
            VALUES (%s, %s, %s, 1, '{}'::jsonb, %s, %s, %s, %s, %s, FALSE)
            ON CONFLICT (artifact_id) DO UPDATE SET
                storage_bucket = EXCLUDED.storage_bucket,
                storage_path = EXCLUDED.storage_path,
                checksum = EXCLUDED.checksum,
                content_type = EXCLUDED.content_type,
                file_size_bytes = EXCLUDED.file_size_bytes
            """,
            (
                artifact_id, run_id, artifact_type, action.bucket, action.storage_path,
                action.checksum, action.content_type, action.file_size_bytes,
            ),
        )
    return True
