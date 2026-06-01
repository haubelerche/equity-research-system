"""Per-run artifact manifest — locks artifact paths to the run that produced them.

Eliminates 'latest artifact wins' by requiring tools to report the paths they
actually wrote, then storing those paths keyed by run_id.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 1


@dataclass
class ArtifactManifest:
    run_id: str
    ticker: str
    created_at: str
    schema_version: int
    # artifacts: key → {"path": str, "producer": str}
    artifacts: dict[str, dict[str, str]] = field(default_factory=dict)

    def resolve(self, key: str) -> Optional[str]:
        """Return file path for *key*, or None if not registered."""
        entry = self.artifacts.get(key)
        return entry["path"] if entry else None

    def load_json(self, key: str) -> dict[str, Any]:
        """Load and return the JSON file for *key*.

        Returns {} on any failure and logs a warning — never silently swallows errors.
        """
        path_str = self.resolve(key)
        if not path_str:
            _logger.warning(
                "ArtifactManifest: key '%s' not registered in run %s", key, self.run_id
            )
            return {}
        path = Path(path_str)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            _logger.warning(
                "ArtifactManifest: artifact file missing — key=%s path=%s run=%s",
                key, path_str, self.run_id,
            )
        except json.JSONDecodeError as exc:
            _logger.warning(
                "ArtifactManifest: artifact JSON invalid — key=%s path=%s run=%s error=%s",
                key, path_str, self.run_id, exc,
            )
        return {}


def write_manifest(manifest: ArtifactManifest, base_dir: Path) -> Path:
    """Write manifest to ``<base_dir>/manifests/<run_id>_manifest.json``."""
    target_dir = Path(base_dir) / "manifests"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{manifest.run_id}_manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": manifest.schema_version,
                "run_id": manifest.run_id,
                "ticker": manifest.ticker,
                "created_at": manifest.created_at,
                "artifacts": manifest.artifacts,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def read_manifest(run_id: str, base_dir: Path) -> Optional[ArtifactManifest]:
    """Load manifest by run_id. Returns None if not found."""
    path = Path(base_dir) / "manifests" / f"{run_id}_manifest.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return ArtifactManifest(
        run_id=data["run_id"],
        ticker=data["ticker"],
        created_at=data["created_at"],
        schema_version=data.get("schema_version", 0),
        artifacts=data.get("artifacts", {}),
    )


def build_manifest_from_artifact_refs(
    run_id: str,
    ticker: str,
    created_at: str,
    artifact_refs: list[dict[str, str]],
) -> ArtifactManifest:
    """Build a manifest from a list of {key, path, producer} dicts.

    Entries with empty key or empty path are skipped. This is the canonical
    way to build a manifest — from paths tools actually reported, not glob.
    """
    artifacts: dict[str, dict[str, str]] = {}
    for ref in artifact_refs:
        key = ref.get("key", "")
        path = ref.get("path", "")
        if key and path:
            artifacts[key] = {"path": path, "producer": ref.get("producer", "unknown")}
    return ArtifactManifest(
        run_id=run_id,
        ticker=ticker,
        created_at=created_at,
        schema_version=CURRENT_SCHEMA_VERSION,
        artifacts=artifacts,
    )
