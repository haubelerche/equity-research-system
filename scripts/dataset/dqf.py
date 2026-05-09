from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.dataset.config_io import ROOT, load_catalyst_taxonomy


CONTRACTS_DIR = ROOT / "dataset" / "contracts"


@dataclass(frozen=True)
class DQFResult:
    status: str
    confidence: float
    materiality: str | None = None
    errors: list[str] | None = None


def _load_contract(name: str) -> dict[str, Any]:
    with (CONTRACTS_DIR / name).open("r", encoding="utf-8") as f:
        return json.load(f)


def _validate_required_fields(payload: dict[str, Any], required: list[str]) -> list[str]:
    return [field for field in required if field not in payload or payload[field] in (None, "")]


def validate_financial_fact(payload: dict[str, Any]) -> DQFResult:
    schema = _load_contract("financial_fact.schema.json")
    missing = _validate_required_fields(payload, schema["required"])
    if missing:
        return DQFResult(status="rejected", confidence=0.0, errors=[f"Missing: {', '.join(missing)}"])

    value = payload.get("value")
    if isinstance(value, (int, float)) and abs(value) > 1_000_000_000_000:
        return DQFResult(status="needs_review", confidence=0.5, errors=["Value outlier over sanity threshold"])

    return DQFResult(status="accepted", confidence=0.98)


def infer_materiality(event_type: str, title: str = "") -> str:
    title_lower = title.lower()
    if event_type in {"regulatory_recall", "tender_award", "bhyt_reimbursement_rate_change"}:
        return "high"
    if any(word in title_lower for word in ("thu hoi", "recall", "tam dung", "dinh chi")):
        return "high"
    if event_type in {"company_guidance_update", "capacity_expansion", "management_change"}:
        return "medium"
    return "low"


def validate_catalyst_event(payload: dict[str, Any]) -> DQFResult:
    schema = _load_contract("catalyst_event.schema.json")
    missing = _validate_required_fields(payload, schema["required"])
    if missing:
        return DQFResult(status="rejected", confidence=0.0, errors=[f"Missing: {', '.join(missing)}"])

    materiality = payload.get("materiality_hint") or infer_materiality(payload["event_type"], payload.get("title", ""))
    if materiality not in {"low", "medium", "high"}:
        materiality = "low"
    return DQFResult(status="accepted", confidence=0.9, materiality=materiality)


def stages_to_invalidate(event_type: str) -> list[str]:
    taxonomy = load_catalyst_taxonomy()
    mapping = taxonomy.get("link_to_pipeline", {}).get("triggers_recompute", [])
    for item in mapping:
        if event_type in item.get("event_types", []):
            return item.get("invalidates_stages", [])
    return ["ANALYZING"]

