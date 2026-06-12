"""Run manifest backed exclusively by the private ``runs`` Supabase bucket."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from backend.storage import RUNS_BUCKET, SupabaseStorageAdapter, run_artifact_key

CURRENT_SCHEMA_VERSION = 1
_SAFE_RUN_ID_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,200}$")


@dataclass
class ArtifactManifest:
    run_id: str
    ticker: str
    created_at: str
    schema_version: int
    artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    adapter: SupabaseStorageAdapter | None = field(default=None, repr=False)

    def resolve(self, key: str) -> Optional[str]:
        entry = self.artifacts.get(key)
        return entry["path"] if entry else None

    def load_json(self, key: str) -> dict[str, Any]:
        path = self.resolve(key)
        if not path:
            return {}
        payload = (self.adapter or SupabaseStorageAdapter()).download_json(RUNS_BUCKET, path)
        return payload if isinstance(payload, dict) else {}


def _payload(manifest: ArtifactManifest) -> dict[str, Any]:
    return {
        "schema_version": manifest.schema_version,
        "run_id": manifest.run_id,
        "ticker": manifest.ticker,
        "created_at": manifest.created_at,
        "artifacts": manifest.artifacts,
    }


def write_manifest(
    manifest: ArtifactManifest,
    base_dir: Path | None = None,
    adapter: SupabaseStorageAdapter | None = None,
) -> str:
    if not _SAFE_RUN_ID_RE.match(manifest.run_id):
        raise ValueError(f"Unsafe run_id={manifest.run_id!r}")
    client = adapter or SupabaseStorageAdapter()
    key = run_artifact_key(manifest.run_id, "manifest.json")
    if client.exists(RUNS_BUCKET, key):
        if client.download_json(RUNS_BUCKET, key) != _payload(manifest):
            raise FileExistsError(f"Refusing overwrite with different manifest: {RUNS_BUCKET}/{key}")
    else:
        client.upload_json(RUNS_BUCKET, key, _payload(manifest))
    return key


def read_manifest(
    run_id: str,
    base_dir: Path | None = None,
    adapter: SupabaseStorageAdapter | None = None,
) -> Optional[ArtifactManifest]:
    if not _SAFE_RUN_ID_RE.match(run_id):
        return None
    client = adapter or SupabaseStorageAdapter()
    key = run_artifact_key(run_id, "manifest.json")
    if not client.exists(RUNS_BUCKET, key):
        return None
    data = client.download_json(RUNS_BUCKET, key)
    return ArtifactManifest(
        run_id=data["run_id"],
        ticker=data["ticker"],
        created_at=data["created_at"],
        schema_version=data.get("schema_version", 0),
        artifacts=data.get("artifacts", {}),
        adapter=client,
    )


def build_manifest_from_artifact_refs(
    run_id: str,
    ticker: str,
    created_at: str,
    artifact_refs: list[dict[str, Any]],
) -> ArtifactManifest:
    artifacts = {
        ref["key"]: {
            "path": ref["path"],
            "producer": ref.get("producer", "unknown"),
            "artifact_type": ref.get("artifact_type", "other"),
            "version": ref.get("version", 1),
            "checksum": ref.get("checksum"),
            "input_refs": ref.get("input_refs", []),
        }
        for ref in artifact_refs
        if ref.get("key") and ref.get("path")
    }
    return ArtifactManifest(run_id, ticker, created_at, CURRENT_SCHEMA_VERSION, artifacts)
