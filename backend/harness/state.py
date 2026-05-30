from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


NodeStatus = Literal["completed", "needs_review", "failed", "skipped"]
RunDbStatus = Literal[
    "initialized",
    "running",
    "data_ready",
    "analysis_ready",
    "valuation_ready",
    "report_ready",
    "needs_human_review",
    "approved",
    "failed",
    "cancelled",
]


class ArtifactRef(BaseModel):
    artifact_id: str
    artifact_type: str = "run_log_json"
    section_key: str | None = None
    version: int = 1
    storage_path: str | None = None
    checksum: str | None = None
    is_locked: bool = False


class EvidenceRef(BaseModel):
    evidence_type: str
    evidence_id: str | None = None
    source_id: str | None = None
    source_tier: int | None = None
    support_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ServiceNodeResult(BaseModel):
    node_name: str
    status: NodeStatus
    summary: dict[str, Any] = Field(default_factory=dict)
    artifact_refs: list[ArtifactRef] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    blocking_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
    input_hash: str | None = None
    output_hash: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class AgentResult(BaseModel):
    status: NodeStatus
    payload: dict[str, Any] = Field(default_factory=dict)
    artifact_refs: list[Any] = Field(default_factory=list)
    evidence_refs: list[Any] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    confidence_breakdown: dict[str, float] = Field(default_factory=dict)
    requires_human: bool = False
    review_reason: str | None = None
    blocking_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ResearchGraphState(BaseModel):
    run_id: str
    ticker: str
    run_type: str = "full_report"
    objective: str
    policy: dict[str, Any] = Field(default_factory=dict)
    flags: dict[str, Any] = Field(default_factory=dict)
    current_stage: str = "INIT"
    status: RunDbStatus = "initialized"
    snapshot_id: str | None = None
    from_year: int = 2021
    to_year: int = 2025
    artifacts: dict[str, Any] = Field(default_factory=dict)
    artifact_refs: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    gate_results: dict[str, dict[str, Any]] = Field(default_factory=dict)
    approvals: dict[str, str] = Field(default_factory=dict)
    requires_human: bool = False
    blocking_reason: str | None = None
    errors: list[str] = Field(default_factory=list)
    next_resume_stage: str | None = None
    checkpoint_version: int = 0

    def stable_hash(self) -> str:
        payload = self.model_dump(mode="json")
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
