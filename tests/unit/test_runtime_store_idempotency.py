from __future__ import annotations

import inspect

from backend.runtime_store import RuntimeStore


def test_save_artifact_upserts_by_logical_key():
    source = inspect.getsource(RuntimeStore.save_artifact)

    assert "UPDATE research.run_artifacts" in source
    assert "COALESCE(section_key, '') = COALESCE(%s, '')" in source
    assert "RETURNING artifact_id" in source
    assert "SELECT COALESCE(MAX(version), 0) + 1" in source
    assert "ON CONFLICT (artifact_id) DO UPDATE" in source
    assert "SET payload_json" in source
