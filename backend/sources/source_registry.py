"""Catalyst source registry loader — Source-Provenance Rebuild, Phase 5.

Loads + validates config/source_registry.yaml. Only enabled, well-formed sources are
returned for fetching. This is the controlled allow-list — nothing outside it is fetched.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.catalysts.event_extractor import EVENT_TYPES

_VALID_SOURCE_TYPES: frozenset[str] = frozenset({
    "exchange_disclosure", "company_ir", "regulatory_notice",
    "official_tender", "bhyt_policy", "financial_media", "broker_report",
})

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "source_registry.yaml"


@dataclass
class RegisteredSource:
    name: str
    source_type: str
    source_tier: int
    base_url: str
    allowed_event_types: list[str]
    fetch_method: str
    enabled: bool
    notes: str = ""


class SourceRegistryError(ValueError):
    pass


def _validate(raw: dict) -> RegisteredSource:
    required = ("name", "source_type", "source_tier", "base_url",
                "allowed_event_types", "fetch_method", "enabled")
    missing = [k for k in required if k not in raw]
    if missing:
        raise SourceRegistryError(f"source missing fields {missing}: {raw.get('name', raw)}")
    if raw["source_type"] not in _VALID_SOURCE_TYPES:
        raise SourceRegistryError(f"invalid source_type '{raw['source_type']}' for {raw['name']}")
    if not (0 <= int(raw["source_tier"]) <= 2):
        raise SourceRegistryError(
            f"source_tier for catalyst source {raw['name']} must be 0-2 (got {raw['source_tier']})"
        )
    bad_events = [e for e in raw["allowed_event_types"] if e not in EVENT_TYPES]
    if bad_events:
        raise SourceRegistryError(f"{raw['name']}: unknown allowed_event_types {bad_events}")
    return RegisteredSource(
        name=raw["name"], source_type=raw["source_type"], source_tier=int(raw["source_tier"]),
        base_url=raw["base_url"], allowed_event_types=list(raw["allowed_event_types"]),
        fetch_method=raw["fetch_method"], enabled=bool(raw["enabled"]), notes=raw.get("notes", ""),
    )


def load_source_registry(path: Path | str | None = None) -> list[RegisteredSource]:
    """Load and validate all sources. Raises SourceRegistryError on malformed entries."""
    import yaml  # type: ignore[import-untyped]
    p = Path(path) if path else _DEFAULT_PATH
    if not p.exists():
        raise SourceRegistryError(f"source registry not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    sources = data.get("sources", [])
    if not isinstance(sources, list) or not sources:
        raise SourceRegistryError("source registry has no 'sources' list")
    return [_validate(s) for s in sources]


def enabled_sources(path: Path | str | None = None) -> list[RegisteredSource]:
    """Return only enabled sources (disabled ones are skipped)."""
    return [s for s in load_source_registry(path) if s.enabled]
