"""Phase 5 — source registry loading & validation."""
from __future__ import annotations

import pytest

from backend.sources.source_registry import (
    SourceRegistryError,
    enabled_sources,
    load_source_registry,
)


# 1. Source registry loads and validates
def test_registry_loads_and_validates():
    sources = load_source_registry()
    assert sources, "registry should not be empty"
    names = {s.name for s in sources}
    assert "hose_disclosure" in names
    for s in sources:
        assert 0 <= s.source_tier <= 2
        assert s.allowed_event_types


# 2. Disabled source is skipped
def test_disabled_source_skipped():
    all_src = load_source_registry()
    enabled = enabled_sources()
    disabled = {s.name for s in all_src if not s.enabled}
    enabled_names = {s.name for s in enabled}
    assert disabled, "fixture should contain at least one disabled source"
    assert disabled.isdisjoint(enabled_names)
    assert "broker_research" not in enabled_names  # disabled in fixture


def test_malformed_registry_raises(tmp_path):
    bad = tmp_path / "reg.yaml"
    bad.write_text(
        "sources:\n  - name: x\n    source_type: not_a_type\n    source_tier: 0\n"
        "    base_url: http://x\n    allowed_event_types: [media_article]\n"
        "    fetch_method: http\n    enabled: true\n",
        encoding="utf-8",
    )
    with pytest.raises(SourceRegistryError):
        load_source_registry(bad)


def test_tier3_source_rejected(tmp_path):
    bad = tmp_path / "reg.yaml"
    bad.write_text(
        "sources:\n  - name: x\n    source_type: financial_media\n    source_tier: 3\n"
        "    base_url: http://x\n    allowed_event_types: [media_article]\n"
        "    fetch_method: http\n    enabled: true\n",
        encoding="utf-8",
    )
    with pytest.raises(SourceRegistryError):
        load_source_registry(bad)
